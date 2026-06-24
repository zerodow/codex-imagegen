"""merge.run vision path: caption-before replaces labels; verify-after retry loop."""

from codex_imagegen.features import merge
from codex_imagegen.providers.generate.base import GenCapabilities, GenIntent
from codex_imagegen.providers.vision.base import CompositionVerdict, SubjectDescription

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
REFS2 = [("AAA", "image/png"), ("BBB", "image/png")]


class _ImgProvider:
    name = "codex"
    capabilities = GenCapabilities(
        max_refs=4, multi_subject=True,
        intents=frozenset({GenIntent.PLAIN, GenIntent.CONSISTENCY, GenIntent.COMPOSE}),
        metered="t",
    )

    def __init__(self):
        self.calls = []

    def generate(self, prompt, *, refs, intent, size, fmt, total_timeout, stall_timeout,
                 progress, labels=None, relation=None):
        self.calls.append({"prompt": prompt, "labels": labels})
        return PNG, {}


class _Vision:
    name = "minimax"

    def __init__(self, *, descriptions=None, verdicts=None):
        self._descriptions = descriptions or ["desc-A", "desc-B"]
        self._verdicts = list(verdicts or [])
        self.describe_calls = 0
        self.verify_calls = 0

    def describe_subject(self, b64, mime):
        text = self._descriptions[self.describe_calls % len(self._descriptions)]
        self.describe_calls += 1
        return SubjectDescription(text=text)

    def verify_composition(self, b64, mime, *, expected):
        v = self._verdicts[self.verify_calls] if self.verify_calls < len(self._verdicts) \
            else CompositionVerdict(ok=True)
        self.verify_calls += 1
        return v


def _run(img, tmp_path, **kw):
    return merge.run(img, "scene", tmp_path / "o.png", refs=REFS2,
                     total_timeout=10, stall_timeout=5, **kw)


def test_vision_off_uses_user_labels_no_vision_calls(tmp_path):
    img = _ImgProvider()
    merge.run(img, "scene", tmp_path / "o.png", refs=REFS2, labels=["x", "y"],
              total_timeout=10, stall_timeout=5)
    assert img.calls[0]["labels"] == ["x", "y"]


def test_caption_before_replaces_labels(tmp_path):
    img, v = _ImgProvider(), _Vision(descriptions=["a woman in red", "a robot"])
    _run(img, tmp_path, vision=v, labels=["IGNORED", "ALSO"])
    assert v.describe_calls == 2
    assert img.calls[0]["labels"] == ["a woman in red", "a robot"]  # captions override user labels


def test_verify_ok_does_single_generate(tmp_path):
    img, v = _ImgProvider(), _Vision(verdicts=[CompositionVerdict(ok=True)])
    _run(img, tmp_path, vision=v, verify=True)
    assert len(img.calls) == 1 and v.verify_calls == 1


def test_verify_retries_with_correction_until_ok(tmp_path):
    img = _ImgProvider()
    v = _Vision(verdicts=[
        CompositionVerdict(ok=False, reasons="missing bob", missing=["bob"]),
        CompositionVerdict(ok=True),
    ])
    _run(img, tmp_path, vision=v, verify=True, max_retries=2)
    assert len(img.calls) == 2  # one retry
    assert "bob" in img.calls[1]["prompt"]  # correction fed into the regenerated scene


def test_verify_gives_up_after_max_retries_keeps_best_effort(tmp_path):
    img = _ImgProvider()
    v = _Vision(verdicts=[CompositionVerdict(ok=False, reasons="nope")] * 5)
    out = _run(img, tmp_path, vision=v, verify=True, max_retries=1)
    assert len(img.calls) == 2  # initial + 1 retry, then stop
    assert out.read_bytes() == PNG


def test_vision_on_without_verify_skips_verification(tmp_path):
    img, v = _ImgProvider(), _Vision()
    _run(img, tmp_path, vision=v, verify=False)
    assert v.describe_calls == 2 and v.verify_calls == 0 and len(img.calls) == 1
