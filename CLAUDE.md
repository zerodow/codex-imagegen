# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## codex-imagegen

Generate images from text prompts using a **ChatGPT subscription** (gpt-image-2 via the
Codex Responses backend) — no `OPENAI_API_KEY`, no per-image API billing. Now multi-provider:
optional MiniMax backends for a single-subject image fallback and for a vision (caption/verify)
step. Python 3.13, **stdlib-only** (no third-party runtime deps).

## Commands

- `imagegen "<prompt>" [-o out.png] [-i ref.png ...] [--provider codex|minimax] [--size] [--format]`
  — one prompt → one image. `-i` adds a subject reference (consistency).
- `imagegen-character --name X (--baseline-prompt … | --baseline-image …) --scenes file.txt`
  — render many scenes of ONE consistent character (baseline reused as reference).
- `imagegen-merge "<scene>" -i a.png -i b.png [--label …] [--relation …] [--vision off|minimax] [--verify] [--max-retries N]`
  — combine 2+ subjects into ONE image. `--vision` captions refs before + verifies after.
- `imagegen-edit "<delta>" -i src.png [-o out.png]`
  — modify ONE source image (recolor/add/remove), applying only the delta. Codex-only (EDIT intent).

Every command prints a structured output + per-image token-cost block on success; `--quiet` prints
only the saved path, `--json` emits the same data as machine-readable JSON (wins over `--quiet`).

Exit codes: `0` ok · `2` bad input · `3` auth · `4` backend/stream · `1` unexpected.

## Architecture

Split by **role**, with a thin orchestration layer; providers declare capabilities so features
route to the strongest backend instead of flattening to a lowest common denominator.

```
core/        errors · image_loader · image_writer · image_dims · output_report
             env_file · orchestrator                            (provider-agnostic)
providers/
  registry.py                         # name -> provider
  generate/ base.py (ImageProvider, GenCapabilities, GenIntent)
            codex/{auth,client,provider}      minimax/{client,provider}
  vision/   base.py (VisionProvider)          minimax/{client,provider}
features/   character · merge · edit   # multi-step orchestration
cli · pipeline · merge_cli · edit_cli  # thin CLI entry points (the 4 commands above)
```

- **`GenIntent`** = `PLAIN | CONSISTENCY | COMPOSE | EDIT`. The caller picks intent; the provider
  owns the exact prompt wording. COMPOSE (merge) and EDIT are Codex-only — features REFUSE a
  provider whose `capabilities.intents` lacks the requested intent rather than degrading silently.
- **EDIT is regeneration, not pixel-lock**: the backend redraws conditioned on the source, so the
  provider's preservation template (in its payload builder) is what keeps unmodified regions intact.
- **`GenCapabilities`** (`max_refs`, `multi_subject`, `intents`, `metered`) lets `features/merge`
  REFUSE a provider that can't composite multiple subjects (e.g. MiniMax Image-01) rather than
  silently dropping one. Do not weaken this guard.
- A provider instance holds its own credentials and is reused across a batch so a mid-batch token
  refresh persists.

## Providers & credentials — split by billing METER, not auth type

All keys are just Bearer credentials; what differs is the meter and what covers it.

| Provider | Role | Multi-subject | Credential | Meter / coverage |
|----------|------|---------------|------------|------------------|
| `codex` (default) | image gen | yes (≤4 refs) | `~/.codex/auth.json` | ChatGPT plan quota, no per-image cost |
| `minimax` (Image-01) | image gen | no (1 face) | `MINIMAX_IMAGE_API_KEY` | per-image, **pay-as-you-go** |
| MiniMax M3 | vision (caption/verify) | — | `MINIMAX_API_KEY` | per-**token**, **covered by the token plan** |

Key facts to remember:
- **Vision (M3) is token-metered → the MiniMax token plan covers it.** Put your token-plan
  subscription key in `MINIMAX_API_KEY`. "API key" is just the credential string, not a billing tier.
- **Image gen (Image-01) is per-image → the token plan does NOT cover it** → needs a PAYG balance
  (`MINIMAX_IMAGE_API_KEY`). This per-meter difference is the only reason the two MiniMax keys are
  separate env vars; one key with both balances can be reused for both.
- Keys are resolved **lazily** (first use) — constructing a provider never reads env or hits the network.

## Conventions

- **stdlib-only**: MiniMax/Codex HTTP uses `urllib`. Don't add runtime deps.
- **Dev install** exposes the 4 `imagegen*` commands from `[project.scripts]`: `pip install -e ".[dev]"`.
  The commands don't exist until installed; tests run without install via `PYTHONPATH=src`.
- **Tests are fully mocked** (no network, no quota). Run all: `PYTHONPATH=src python3 -m pytest tests/ -q`.
  One file: append the path; one test: `… tests/test_edit_feature.py::test_name -q`. Mock at the
  client/provider boundary; never assert on generated pixels (no seed → non-deterministic).
- **`scripts/` holds dev/eval tooling** that reuses the package directly (not the CLI): `eval_edit_quality.py`
  (TEMPLATE-vs-RAW edit quality on the free Codex path → HTML in `eval-out/`), `validate_responses.py`
  (live smoke test, **consumes 1 quota image**), `probe_codex_self_judge.py` (can Codex self-judge for free?).
- **Credentials load from a project-local `.env`** — every CLI entry point calls `env_file.load_dotenv()`
  first (stdlib parser, no python-dotenv). A real exported var always wins; `.env` is gitignored.
- **`plans/` is gitignored** (local working area; see `.gitignore`). Plans, reports, and HTML
  previews live there and are NOT committed. Tracked docs go in `docs/`.
- Commits: conventional format, **no AI attribution**.

## Caveats

- The Codex `codex/responses` endpoint is **unofficial** (the Codex CLI's backend) — may change; ToS gray area.
- MiniMax endpoint URLs / model ids / response shapes are **isolated in each `client.py`**. The
  **vision (M3 chat) path is verified live** (2026-06-24); the **Image-01 generate path is still
  unverified** against a live key — confirm against platform.minimax.io before relying on it.
- MiniMax **M3 is a reasoning model**: it can emit `<think>…</think>` chain-of-thought. The vision
  provider strips that (`_strip_reasoning`) before using captions/verdicts — keep that guard.
- The vision **caption-before** step imports the reference's outfit/setting/pose, which can override
  the target scene — a tradeoff (good for likeness, weak for scene control), not a bug.
- `--size` is a hint (gpt-image-2 picks its own dimensions). MiniMax picks its own output encoding, so
  `--format` may mismatch (fails cleanly, exit 4) — use `codex` for strict format control.
