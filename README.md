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
| `--size` | `1024x1024` | **hint only** — gpt-image-2 picks its own dimensions/aspect |
| `--format` | `png` | `png` / `jpeg` / `webp` |
| `--model` | `gpt-5.5` | parent model that hosts the image tool |
| `--timeout` | `300` | total seconds; large images take 1–3 min |
| `--stall-timeout` | `120` | abort if the stream goes silent this long |
| `--quiet` | off | print only the saved path (no progress on stderr) |

Examples:
```bash
imagegen "coffee shop logo, minimal, gold on black" -o brand/logo.png
imagegen "isometric city block, low-poly" --size 1536x1024 --quiet
```

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
