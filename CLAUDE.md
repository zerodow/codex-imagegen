# codex-imagegen

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

Exit codes: `0` ok · `2` bad input · `3` auth · `4` backend/stream · `1` unexpected.

## Architecture

Split by **role**, with a thin orchestration layer; providers declare capabilities so features
route to the strongest backend instead of flattening to a lowest common denominator.

```
core/        errors · image_loader · image_writer · orchestrator   (provider-agnostic)
providers/
  registry.py                         # name -> provider
  generate/ base.py (ImageProvider, GenCapabilities, GenIntent)
            codex/{auth,client,provider}      minimax/{client,provider}
  vision/   base.py (VisionProvider)          minimax/{client,provider}
features/   character · merge          # multi-step orchestration
cli · pipeline · merge_cli             # thin CLI entry points (the 3 commands above)
```

- **`GenIntent`** = `PLAIN | CONSISTENCY | COMPOSE`. The caller picks intent; the provider owns
  the exact prompt wording. COMPOSE (merge) is Codex-only.
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
- **Tests are fully mocked** (no network, no quota). Run: `PYTHONPATH=src python3 -m pytest tests/ -q`.
  Mock at the client/provider boundary; never assert on generated pixels (no seed → non-deterministic).
- **`plans/` is gitignored** (local working area; see `.gitignore`). Plans, reports, and HTML
  previews live there and are NOT committed. Tracked docs go in `docs/`.
- Commits: conventional format, **no AI attribution**.

## Caveats

- The Codex `codex/responses` endpoint is **unofficial** (the Codex CLI's backend) — may change; ToS gray area.
- MiniMax endpoint URLs / model ids / response shapes are **isolated in each `client.py` and NOT yet
  verified against a live key** — confirm against platform.minimax.io before relying on MiniMax paths.
- `--size` is a hint (gpt-image-2 picks its own dimensions). MiniMax picks its own output encoding, so
  `--format` may mismatch (fails cleanly, exit 4) — use `codex` for strict format control.
