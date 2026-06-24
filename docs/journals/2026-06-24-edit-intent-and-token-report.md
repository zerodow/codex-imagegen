# Edit Intent + Token Reporting, Scoped for Free Codex Path

**Date**: 2026-06-24 14:47
**Severity**: Medium (new user-facing feature, internally clean, one deferred scope gate)
**Component**: Core intents (GenIntent.EDIT), CLI commands (imagegen-edit), token reporting (per-image, batch), image analysis (dimension reader)
**Status**: Completed, all tests passing (156 passing, was 137)

## What Shipped

Three commits added image editing + cost transparency across the CLI:

1. **Image dimension reader + output report** (`core/image_dims.py`, `core/output_report.py`): Stdlib-only PNG/JPEG/WebP/GIF header parser (returns `None` on malformed, never raises); structured human + `--json` output showing per-image token usage and batch totals. Missing usage degrades to `n/a` (no fabrication).

2. **imagegen-edit command + token capture** (`GenIntent.EDIT`, `imagegen-edit` CLI, `--json`): Instruction-only edit on the free Codex subscription path (regeneration with a PRESERVATION TEMPLATE wrapping the user delta). Captured image-gen + orchestration token usage from the `response.completed` SSE event. `merge.run()` returns `(path, meta)` instead of path alone; all callers updated.

3. **Edit-quality eval harness + self-judge probe** (dev-only `scripts/`): Cost-safe `--dry-run` template-vs-raw side-by-side HTML comparison. Empirical finding: Codex backend can return a text verdict about an image (no vision tool needed), making free automated edit-quality judging feasible.

## Key Architectural Decisions

### Edit Is Free (Via Regeneration + Preservation Template)

The Codex `/v1/images/generations` endpoint does not have a native edit action. Free subscribers cannot call `/v1/images/edits` (paid-only). Instead, edit is implemented as **regeneration with a deterministic PRESERVATION TEMPLATE**: the user provides an instruction (e.g., "make the hat red"), the template wraps it as _"[PRESERVATION] Apply ONLY this change; preserve everything else: <user instruction>"_. The template is load-bearing — without it, the model drifts and produces a completely new image. With it, edit-quality probes confirmed all changes were scoped (recolor, add object, remove element). This unlocks edit capability at zero marginal cost.

### Scope Discipline: Mask and Raw Deferred to v2

Two features were explicitly cut:

- **Mask support (inpaint/outpaint)**: Would require a new `mask` parameter threading through 5 layers (CLI → command → provider.edit → client → request builder).
- **`--raw` flag (no template)**: Side-by-side with template-wrapped edits would require conditional logic at the same 5 layers.

V1 ships instruction-only (covers recolor/add/remove). The eval harness was built as a dev tool so that any future LLM-powered prompt optimization is measured, not speculated. Both features are trivial post-refactor; deferring reduces cliff risk.

### Token Meters Surfaced Separately

The API returns two distinct token counts:

- **`tool_usage.image_gen`**: Per-image cost (e.g., 229 output tokens for one image). Real, image-specific.
- **`usage` (top-level)**: GPT orchestration tokens (~2.3k input + ~100 output per generation call). Shared across all images in a batch.

The report shows image-gen cost prominently (per-image line, bold), with a one-line orchestration summary below. This prevents confusion (users see why image N costs Y, not just "total is Z"). Missing usage never triggers fabrication—fields become `n/a`, and batch totals degrade gracefully.

### Measurement Before Optimization

Rather than speculatively adding a vision-grounding layer or prompt optimizer, the deterministic template (which proved sufficient for edit probes) ships first. The eval harness captures the decision-making surface: future work can run the harness, measure the delta, and decide if a paid VLM is warranted. The self-judge finding (Codex CAN return a text image verdict with no vision tool) means free automated edit-quality grading is plausible—no MiniMax dependency required.

## Technical Decisions Worth Locking

### Image Dimension Reader: Fail-Safe Design

`core/image_dims.py` reads PNG/JPEG/WebP/GIF headers without any external library (stdlib only). Malformed files return `None` (not an exception). This prevents eval harness crashes on garbage test files. Tested with VP8/VP8L edge cases; only valid dimension writes propagate to the report.

### Token Usage Capture from SSE

The Codex client listens for `response.completed` in the SSE stream (already parsed for image paths). The `completed_event` contains `usage.image_gen` + `usage.input_tokens` + `usage.output_tokens`. Captured at the orchestration layer and returned via `(path, meta)` from `merge.run()`. Single source of truth: all callers (CLI, batch, merge) use the same meta structure.

### No Public-Contract Breaks

- `ImageProvider.generate()` signature unchanged.
- `build_payload()` signature unchanged.
- `merge.run()` returns `(path, meta)` (was `path`); all 8 callers + 12 tests updated in the same commit.

Internal-only change; no user-visible CLI contract break.

## Test Coverage

**156 tests passing** (19 new). Coverage includes:

- Image dimension reader: valid PNG/JPEG/WebP/GIF, malformed fallback
- Output report: human format (alignment, token aggregation), `--json` (no extras), empty batch edge case
- imagegen-edit command: success path, provider-capability guard (edit-incapable provider fails loudly), `--json` mode
- Token capture: orchestration + image-gen isolation, missing usage degradation
- merge.run() callers: all 8 updated and tested (imagegen, imagegen-character, imagegen-merge CLIs; test utilities)
- eval harness: dry-run, HTML output, template-vs-raw side-by-side

**Code reviews** (3 independent, one per commit) found no CRITICAL/HIGH issues. MEDIUMs addressed:

- Commit 1: Added budgeted single-source image-dim loader; empty-batch `--json` output clarified.
- Commit 2: VP8/VP8L test coverage added; capability guard phrased clearly ("image editing not available on this provider").
- Commit 3: Eval script output gitignored; raw arm (no template) derived correctly from build_payload.

## Open Risk: Preservation Template Effectiveness

The template _"[PRESERVATION] Apply ONLY this change; preserve everything else: <user instruction>"_ was validated on Codex edits in the self-judge probe. Behavior is deterministic for the six probe cases (recolor hat, add background, remove person, etc.). However:

- **Generalization unknown**: No large-scale A/B test across diverse edit types (e.g., subtle style shifts, multi-object changes).
- **Regression potential**: If Codex backend behavior changes or if the template is used with a different LLM, edit quality may degrade.

Mitigation: The eval harness is checked in; future cost-safe regression runs are trivial (`--dry-run` uses cached images). Recommend running the harness quarterly or before any Codex backend change announcement.

## Decisions Deferred (YAGNI)

- **Mask support (inpaint/outpaint)**: Requires parameter threading + backend capability verification. Deferred until user request or clear quality gap vs. regeneration-only.
- **`--raw` flag (no template)**: Feature gate already in place (`GenIntent.EDIT` + `preservation=True` by default). Raw arm is trivial to flip on; deferred pending user evaluation of template quality.
- **Vision-grounded prompt optimization**: Self-judge probe shows Codex can return free text verdicts. Vision-powered edit-quality optimizer is a future bet; ship deterministic template first (lower cost, unblocks feedback).

## Behavioral Note: Edit Determinism

Users should expect:

- **Same instruction, same input → same output** (determinism within Codex backend limits). The preservation template locks the delta.
- **Non-destructive**: Original image is never modified; edit produces a new file.
- **Cost**: One full image generation (not cheaper than a fresh image). Edit is a UX feature, not a cost optimization.

## Status

All three commits landed. 156 tests green. No CRITICAL/HIGH code-review findings. Branch `feat/edit-intent-and-output-report` ready to merge to `main`.

---

**Status**: DONE
**Summary**: imagegen-edit + token reporting shipped (free Codex path via preservation template, per-image costs transparent, eval harness for regression testing). All 156 tests passing, no blockers.
