# codex-imagegen

Generate an image from a text prompt using **your ChatGPT subscription** — no
`OPENAI_API_KEY`, no per-image API billing. One command:

```bash
imagegen "a watercolor cat sitting on a sunny windowsill" -o cat.png
```

It calls `gpt-image-2` through the Codex Responses backend, reusing the OAuth
token Codex already stored when you ran `codex login`. Image generation consumes
your ChatGPT plan quota (it does **not** hit the paid Images API).

## How it works

```
prompt ─► imagegen ─► POST chatgpt.com/backend-api/codex/responses
                       (tool: image_generation, stream: true,
                        Bearer token from ~/.codex/auth.json)
                     ─► SSE stream ─► base64 PNG ─► validated, written to -o
```

It does **not** shell out to `codex exec` — that path does not materialize a
real image file headlessly (it returns the image only into the model context).
This tool talks to the same backend the Codex CLI uses, directly.

## Prerequisites

- [Codex CLI](https://developers.openai.com/codex/cli) installed and logged in
  with a **ChatGPT account** (Plus/Pro/Team/Enterprise — free tier may work):
  ```bash
  codex login          # sign in with ChatGPT, NOT an API key
  codex login status   # should print: Logged in using ChatGPT
  ```
- Python 3.13+. No third-party runtime dependencies (stdlib only).

## Install

```bash
pip install -e .          # exposes the `imagegen` command
```

## Usage

```bash
imagegen "<prompt>" [-o OUTPUT] [--size SIZE] [--format png|jpeg|webp] [--quiet]
```

| Flag | Default | Notes |
|------|---------|-------|
| `-o, --output` | `./generated/<date>/<slug>-<time>.<ext>` | output path; parent dirs created |
| `-i, --reference` | — | reference image for character/subject consistency (repeatable) |
| `--size` | `1024x1024` | **hint only** — gpt-image-2 picks its own dimensions/aspect |
| `--format` | `png` | `png` / `jpeg` / `webp` |
| `--provider` | `codex` | image backend: `codex` \| `minimax` (see Providers below) |
| `--model` | provider default | model override (codex → `gpt-5.5`, minimax → `image-01`) |
| `--timeout` | `300` | total seconds; large images take 1–3 min |
| `--stall-timeout` | `120` | abort if the stream goes silent this long |
| `--quiet` | off | print only the saved path (no progress on stderr) |

Examples:
```bash
imagegen "coffee shop logo, minimal, gold on black" -o brand/logo.png
imagegen "isometric city block, low-poly" --size 1536x1024 --quiet
```

## Character consistency (same character across images)

`gpt-image-2` accepts reference images. Use `-i/--reference` to keep a subject's
appearance when placing it in a new scene (repeat `-i` for multiple angles):

```bash
# 1) baseline character
imagegen "a friendly robot mascot, mint accents, big cyan eyes, flat vector" -o robo.png
# 2) reuse it as reference in new scenes
imagegen "the same robot waving, holding a paintbrush, in an art studio" -i robo.png -o robo-studio.png
```

### Batch a whole set: `imagegen-character`

Generate a baseline once, then render many scenes that all reuse it as reference:

```bash
# scenes.txt — one scene prompt per line (# comments and blank lines ignored)
imagegen-character --name Robo \
  --baseline-prompt "a friendly robot mascot, mint accents, big cyan eyes, flat vector" \
  --scenes scenes.txt --outdir characters/robo
# ...or start from an existing image:
imagegen-character --name Robo --baseline-image robo.png --scenes scenes.txt
```

Output: `<outdir>/00-baseline.<ext>` + `NN-<slug>.<ext>` per scene. Runs sequentially
(image gen is slow + quota-limited); a failed scene is reported and the batch
continues — exit `4` if any scene failed, `0` otherwise.

> **Consistency is strong but not perfect.** Subject identity (face, colors, outfit)
> carries well; expect minor style/pose/detail drift between images. Passing multiple
> reference angles (`-i a.png -i b.png`) improves it.

## Merge characters (combine subjects from different images): `imagegen-merge`

Take a subject from each of two or more images and render **one new image with all
of them**. Pass `-i` per subject (≥2), describe the scene, and optionally label each
reference (in order) and say how they should be arranged:

```bash
imagegen-merge "two friends in a sunlit cafe" \
  -i alice.png -i robot.png \
  --label "the woman in the red coat" --label "the robot mascot" \
  --relation "sitting across a table, shaking hands" \
  -o cafe.png
```

| Flag | Notes |
|------|-------|
| `-i, --reference` | subject image; repeat for each subject (need ≥2) |
| `--label` | short label per `-i`, **same order** — disambiguates which subject is which (omit all, or one per reference) |
| `--relation` | how the subjects are arranged / interact |
| `--provider` | image backend (default `codex`) |

Other flags (`-o`, `--size`, `--format`, `--model`, `--timeout`, `--quiet`) match `imagegen`.

> **Both subjects must appear and keep their own faces** — the prompt explicitly asks
> the model not to blend identities. It's still a generative model with no seed:
> expect to re-roll occasionally, and label each subject to reduce mix-ups. Quality
> degrades with too many subjects (capped per provider; Codex allows up to 4).

### Vision assist (optional): caption + verify

Add a vision model "in the middle" to improve merge quality. It **captions each
reference** before generation (richer identity binding than manual `--label`s) and,
with `--verify`, **checks the result** and regenerates with a correction if a subject
is missing or faces are blended:

```bash
export MINIMAX_API_KEY=...          # MiniMax token-plan key (NOT the image PAYG key)
imagegen-merge "two friends in a cafe" -i alice.png -i robot.png \
  --vision minimax --verify --max-retries 2
```

| Flag | Notes |
|------|-------|
| `--vision {off,minimax}` | caption references before generating (default `off`); when on, captions replace `--label` |
| `--verify` | check the result; retry on failure (requires `--vision`) |
| `--max-retries N` | regeneration attempts when `--verify` fails (default 1) |

> **Billing:** vision uses your MiniMax **token-plan** key (`MINIMAX_API_KEY`),
> billed per token — separate from Codex image quota. Each `--verify` failure costs
> one extra Codex image turn, so retries are capped and off by default.

## Providers & billing

`imagegen` / `imagegen-merge` take `--provider`. Each declares what it can do, and the
merge command refuses any provider that can't composite multiple distinct subjects.

| Provider | Generation | Multi-subject (merge) | Key / meter |
|----------|-----------|------------------------|-------------|
| `codex` (default) | gpt-image-2 via ChatGPT | ✅ up to 4 refs | `~/.codex/auth.json` — ChatGPT plan quota, no per-image cost |
| `minimax` | Image-01 | ❌ single face only | `MINIMAX_IMAGE_API_KEY` — pay-as-you-go (~$0.0035/image) |

> **`--format` with `minimax`:** Image-01 chooses its own encoding; if it doesn't
> match `--format`, the byte check fails cleanly (exit 4) rather than writing a
> mislabeled file. Use the format MiniMax returns, or stick with `codex` for strict
> format control.

```bash
imagegen "a portrait, studio light" --provider minimax        # PAYG single image
imagegen-merge ... --provider minimax                          # rejected: minimax can't merge
```

> **Three separate credentials, do not mix them:** Codex uses `~/.codex/auth.json`
> (subscription); MiniMax **vision** uses `MINIMAX_API_KEY` (token plan); MiniMax
> **image generation** uses `MINIMAX_IMAGE_API_KEY` (pay-as-you-go) — different meters,
> different balances.

## Exit codes

| Code | Meaning |
|------|---------|
| 0 | success — path printed to stdout |
| 2 | bad input (empty prompt, unknown `--size`, non-positive timeout) |
| 3 | auth problem (not logged in / API-key-only / refresh expired → run `codex login`) |
| 4 | backend/stream failure (quota, moderation, network, timeout) |

## Limits & caveats

- **Size is a hint**, not a constraint — the model may return a different aspect.
- **Quota**: image turns draw on your ChatGPT plan and consume it faster than
  text. Avoid sustained batches (rule of thumb: < ~10 images/min).
- **Latency**: 1–3 minutes is normal for detailed images.
- **Unofficial endpoint**: `codex/responses` is the Codex CLI's backend, not a
  documented public API. It can change without notice and may be subject to
  OpenAI's terms for your account. Use accordingly.

## Manual smoke test (consumes 1 quota image)

```bash
python3 scripts/validate_responses.py    # writes /tmp/validate-cat.png
```

## Run the tests (no quota, no network)

```bash
pip install -e ".[dev]"
PYTHONPATH=src python3 -m pytest tests/ -q
```
