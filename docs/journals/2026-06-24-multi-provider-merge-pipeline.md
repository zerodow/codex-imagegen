# Multi-Provider Refactor + Merge Pipeline Complete

**Date**: 2026-06-24 12:23
**Severity**: Medium (scope large, risk well-contained)
**Component**: Core architecture, CLI routing, provider abstraction, new merge feature
**Status**: Completed, uncommitted pending user decision

## What Shipped

A Codex-only image-generation CLI was refactored into a small multi-provider system over four phases:

1. **Phase 1: Provider boundary refactor** — moved code from flat layout (`auth.py`, `responses_client.py`, `generator.py`, `pipeline.py`) into a feature-driven tree (`core/`, `providers/generate/{base,codex}`, `providers/registry`, `features/character`). Behavior unchanged; all tests green (61→117 total).

2. **Phase 2: Merge feature on Codex** — built `imagegen-merge` command; takes 2+ reference images + a text prompt, returns one composed image via Codex's native multi-reference framing. Capability guard rejects providers that don't support multi-subject (e.g., single-face MiniMax Image-01).

3. **Phase 3: MiniMax M3 vision assist** — optional image captioning (before generation) + verify-after loop (retry up to N times if generation verification fails). Vision off by default; enabled via `--vision minimax`. Lazy credential loading; never touches env/network until first vision call.

4. **Phase 4: MiniMax Image-01 fallback** — second generation provider (single-face only, pay-as-you-go). Capability guard proven: `imagegen-merge --provider minimax` exits code 2 (InputError) without network calls, because merge requires multi_subject=True.

**All changes are uncommitted on `main` as of 12:24 UTC.** Phase 1 + `pipeline.py` shim must land together (they own the import paths).

## Key Architectural Decision

**Capability declaration + provider routing, not lowest-common-denominator fallback.**

Each `ImageProvider` exports a `GenCapabilities` struct (`max_refs`, `multi_subject`, supported `intents`, billing model). Features (like merge) declare what they need and route to the strongest provider. If a provider can't deliver, the feature refuses it with a clear `InputError`, never silently degrades.

Example: `imagegen-merge` asserts `provider.capabilities.multi_subject == True` before any API call. Codex passes; MiniMax Image-01 fails immediately (exit 2), preserving Codex's multi-reference strength as a non-negotiable merge requirement.

## Technical Decisions Worth Locking

### Credential Isolation

Three separate credentials, never mixed:

- **`~/.codex/auth.json`** → Codex subscription (used by `codex` CLI, stored locally).
- **`MINIMAX_API_KEY`** → MiniMax token-plan (vision only, token-metered, covered by plan).
- **`MINIMAX_IMAGE_API_KEY`** → MiniMax pay-as-you-go (image gen only, separate PAYG balance).

Why: MiniMax charges vision per-token (within the token plan) but images per-image (separate balance). Conflating keys would mask billing and make quota tracking impossible.

### Behavior-Neutral Refactor as a Gate

Phase 1 was a hard prerequisite: moved code but preserved byte-for-byte output for `PLAIN` and `CONSISTENCY` intents (verified by extracting the exact payloads and comparing strings). `COMPOSE` is stubbed with `NotImplementedError`, unreachable in Phase 1 CLI paths. Both entry points (`codex_imagegen.cli:main`, `codex_imagegen.pipeline:main`) unchanged; the `pipeline.py` is a thin shim re-exporting `features.character.main`.

One deviation accepted and documented: **credential validation moved from eager to lazy** (Phase 1 code review Medium #1). In the missing-auth + `--baseline-image` case, the exit code is still 3 (AuthError), but stderr lines now interleave differently (the "[baseline] ready" message prints before the error instead of after). Not a regression — documented as acceptable for a refactor.

### Vision in the Middle

Captions become generation labels (binding image identity before composition). Verification loop is defensive: malformed JSON replies set `ok=False` + `reasons=raw` without crashing. Best-effort approach: the verify step improves quality but is not a hard block.

## Test Coverage

**117 tests passing** (was 32 in the monolithic version). All mocked (no network, no Codex/MiniMax calls). Organized by provider + feature:

- Core: orchestrator, image_loader, image_writer, errors
- Providers: Codex client + provider, MiniMax vision client + provider, MiniMax image client + provider
- Features: character batch, merge feature
- CLI: imagegen, imagegen-character, imagegen-merge, registry dispatch
- Merge + vision integration (separate scenarios)

Code reviews (4 independent, one per phase) all came back with no CRITICAL/HIGH issues. MEDIUMs addressed or deferred:

- Phase 1: lazy credential validation documented (no fix); provider-reuse test instrumented
- Phase 2: whitespace-label fallback fixed; label-count guard locked
- Phase 3: missing-key exit code tested; captions-override-labels clarified in README
- Phase 4: stale README `--model` note fixed; registry dict-factory recommendation deferred (YAGNI)

## Open Risk: MiniMax Endpoint Shape

The two MiniMax `client.py` files (vision and image gen) contain hardcoded endpoint URLs, model IDs, and response JSON shapes:

- Vision: endpoint, M3 model ID, verdict JSON keys
- Image Gen: endpoint, Image-01 model ID, request shape, response keys

**These are not verified against a live key** (no key available for testing). They are isolated to one module each, but future deployments must confirm against the platform (`platform.minimax.io` API reference) before trusting them. The shapes are derived from official docs (vision structured output workaround, image-01 single-subject restriction), so high confidence they match, but no integration test proves it.

## Decisions Deferred (YAGNI)

- **Codex-quota auto-fallback** — `--provider` is manual selection; no auto-escalation to MiniMax if Codex quota depletes.
- **Character batch consistency-verify hook** — merge demonstrates the full vision pattern; character feature doesn't yet use verify in the loop (only merge does). Can revisit if batch drift becomes painful.
- **Registry as a dict factory** — currently `if name == "codex": … elif name == "minimax": …`. Recommend moving to a dict before many more providers; deferred for Phase 4 summary.

## Status

All four phases completed. Uncommitted on `main`. Next step: user decision on commit + push to remote.

---

**Status**: DONE_WITH_CONCERNS
**Summary**: Four-phase refactor + feature complete; 117 tests green, no CRITICAL/HIGH in code reviews; multi-provider system live with capability-driven routing (proven: merge refuses single-subject). Unverified risk: MiniMax endpoint shapes not tested against live keys.
**Concerns**:
- MiniMax vision/image-gen endpoint URLs and model IDs are hardcoded (isolated modules) but not verified against live API; confirm before production use.
- Lazy credential validation (acceptable per review) means stderr line order differs in edge case (missing auth + baseline image); not a backward-compat issue but worth noting for downstream snapshot tests.
