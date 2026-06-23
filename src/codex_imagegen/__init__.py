"""codex-imagegen: prompt -> image via the Codex subscription (gpt-image-2).

Generates images by POSTing to the Codex Responses backend with the
`image_generation` tool, reusing the ChatGPT OAuth token from
`~/.codex/auth.json`. No API key, no per-image API billing (uses plan quota).
"""

__version__ = "0.1.0"
