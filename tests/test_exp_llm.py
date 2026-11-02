"""Tests for exp/llm.py: reply parser, cache, throttle/retries, quota stop.

All offline: a fake OpenAI-style client stands in for the providers.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from originscan.exp import llm
from originscan.exp.llm import (
    STATUS_ERROR,
    STATUS_OK,
    STATUS_PARSE_ERROR,
    STATUS_TOO_LARGE,
    LLMDetector,
    QuotaExhaustedError,
    normalize_cwe,
    parse_reply,
)
from originscan.interfaces import Context, DetectorAdapter

CTX = Context(text="// === TARGET FUNCTION (a.c:1-3) ===\nint f(){return 0;}", tokens=20, items=[])

# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("reply", "vulnerable", "cwe", "line", "conf"),
    [
        ('{"vulnerable": true, "cwe": "CWE-787", "line": 4, "confidence": 0.9}',
         True, "CWE-787", 4, 0.9),
        ('```json\n{"vulnerable": false, "cwe": null, "line": null, "confidence": 0.7}\n```',
         False, None, None, 0.7),
        ('<thought>check bounds {not json}</thought>\n{"vulnerable": "yes", "cwe": "787", '
         '"line": "12", "confidence": "80%"}', True, "CWE-787", 12, 0.8),
        ('Sure! Here is my answer: {"Vulnerable": true, "CWE": "cwe_120", "confidence": 65}',
         True, "CWE-120", None, 0.65),
        ('{"verdict": false, "cwe": "CWE-787", "line": 3, "confidence": 1.4}',
         False, None, None, 1.0),
        ('{"reason": "has {braces} in \\"text\\"", "vulnerable": true, "cwe": null}',
         True, None, None, None),
    ],
)
def test_parse_reply_variants(reply, vulnerable, cwe, line, conf) -> None:
    p = parse_reply(reply)
    assert p.ok
    assert (p.vulnerable, p.cwe, p.line, p.confidence) == (vulnerable, cwe, line, conf)


@pytest.mark.parametrize(
    "reply",
    [None, "", "I think it is vulnerable.", '{"cwe": "CWE-787"}',
     '<think>long reasoning cut off by max_tokens {"vulnerable": true',
     '{"vulnerable": "maybe"}'],
)
def test_parse_reply_failures_never_raise(reply) -> None:
    assert parse_reply(reply).ok is False


def test_normalize_cwe() -> None:
    assert normalize_cwe("CWE-787") == "CWE-787"
    assert normalize_cwe(" cwe 0416 ") == "CWE-416"
    assert normalize_cwe(476) == "CWE-476"
    assert normalize_cwe("buffer overflow") is None
    assert normalize_cwe(True) is None


# ---------------------------------------------------------------------------
# Fake client
# ---------------------------------------------------------------------------


class FakeHTTPError(Exception):
    def __init__(self, status_code: int, message: str = "", headers=None) -> None:
        super().__init__(message or f"HTTP {status_code}")
        self.status_code = status_code
        self.response = SimpleNamespace(status_code=status_code, headers=headers or {})


class FakeClient:
    """Plays back a script of replies (str) or exceptions, recording requests."""

    def __init__(self, script) -> None:
        self.script = list(script)
        self.requests: list[dict] = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.requests.append(kwargs)
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        msg = SimpleNamespace(content=item)
        usage = SimpleNamespace(prompt_tokens=111, completion_tokens=22)
        return SimpleNamespace(choices=[SimpleNamespace(message=msg)], usage=usage)


GOOD = '{"vulnerable": true, "cwe": "CWE-787", "line": 2, "confidence": 0.75}'


def make(script, tmp_path=None, **kw) -> tuple[LLMDetector, FakeClient, list[float]]:
    llm._LAST_CALL.clear()
    sleeps: list[float] = []
    client = FakeClient(script)
    det = LLMDetector(
        name="strong", provider="fake", model_id="org/model:free",
        base_url="http://fake", api_key="k", client=client,
        cache_dir=tmp_path, sleep=sleeps.append, **kw,
    )
    return det, client, sleeps


# ---------------------------------------------------------------------------
# Detector
# ---------------------------------------------------------------------------


def test_call_ok_and_adapter_protocol() -> None:
    det, client, _ = make([GOOD])
    res = det.call(CTX, run=0)
    assert res.status == STATUS_OK and res.parse_ok and not res.cached
    assert res.finding == {"verdict": True, "cwe": "CWE-787", "line": 2, "confidence": 0.75,
                           "input_tokens": 111, "output_tokens": 22}
    assert res.model_id == "org/model:free" and res.prompt_version == llm.PROMPT_VERSION
    assert client.requests[0]["messages"][0]["role"] == "system"
    assert "temperature" not in client.requests[0]  # null in config -> provider default
    assert isinstance(det, DetectorAdapter)


def test_cache_hit_makes_no_request(tmp_path) -> None:
    det, client, _ = make([GOOD], tmp_path)
    first = det.call(CTX, run=1)
    det2, client2, _ = make([], tmp_path)  # empty script: any request would fail
    second = det2.call(CTX, run=1)
    assert second.cached and second.finding == first.finding
    assert len(client.requests) == 1 and client2.requests == []
    # A different run index is a different call.
    det3, client3, _ = make([GOOD], tmp_path)
    assert det3.call(CTX, run=2).cached is False
    assert list(tmp_path.rglob("*.json"))


def test_retries_on_429_and_5xx_then_succeeds() -> None:
    det, client, sleeps = make(
        [FakeHTTPError(429, "rate limited upstream"), FakeHTTPError(503), GOOD]
    )
    res = det.call(CTX, run=0)
    assert res.status == STATUS_OK and len(client.requests) == 3
    assert sleeps[:2] == [5.0, 10.0]  # exponential backoff


def test_retry_after_header_is_respected() -> None:
    det, _, sleeps = make([FakeHTTPError(429, "slow down", {"retry-after": "7"}), GOOD])
    det.call(CTX, run=0)
    assert sleeps == [7.0]


def test_daily_quota_stops_the_run() -> None:
    err = FakeHTTPError(429, "Rate limit reached on tokens per day (TPD): Limit 200000")
    det, client, _ = make([err, GOOD])
    with pytest.raises(QuotaExhaustedError):
        det.call(CTX, run=0)
    assert len(client.requests) == 1


def test_gives_up_after_max_retries() -> None:
    det, client, _ = make([FakeHTTPError(500)] * 3, max_retries=2)
    res = det.call(CTX, run=0)
    assert res.status == STATUS_ERROR and res.finding is None and len(client.requests) == 3


def test_non_retryable_error_and_413() -> None:
    det, client, _ = make([FakeHTTPError(401, "bad key")])
    assert det.call(CTX, run=0).status == STATUS_ERROR and len(client.requests) == 1
    det, _, _ = make([FakeHTTPError(413, "Request too large")])
    assert det.call(CTX, run=0).status == STATUS_TOO_LARGE


def test_too_large_is_skipped_without_a_request() -> None:
    det, client, _ = make([GOOD], max_input_tokens=10)
    res = det.call(CTX, run=0)
    assert res.status == STATUS_TOO_LARGE and client.requests == []


def test_parse_error_is_recorded_and_run_falls_back() -> None:
    det, _, _ = make(["I cannot tell."])
    res = det.call(CTX, run=0)
    assert res.status == STATUS_PARSE_ERROR and res.parse_ok is False and res.raw
    det, _, _ = make(["I cannot tell."])
    f = det.run(CTX, run=0)
    assert f["verdict"] is False and f["confidence"] == 0.0


def test_throttle_spaces_requests() -> None:
    det, _, sleeps = make([GOOD, GOOD], rpm=60_000)  # 1 ms gap: only checks it sleeps
    det.call(CTX, run=0)
    det.call(CTX, run=1)
    assert len(sleeps) <= 1
    det, _, sleeps = make([GOOD, GOOD], rpm=1)  # 60 s gap
    det.call(CTX, run=0)
    det.call(CTX, run=1)
    assert sleeps and 59.0 < sleeps[-1] <= 60.0


def test_temperature_and_extra_body_are_sent() -> None:
    det, client, _ = make([GOOD], temperature=0.7, extra_body={"reasoning": {"effort": "low"}})
    det.call(CTX, run=0)
    assert client.requests[0]["temperature"] == 0.7
    assert client.requests[0]["extra_body"] == {"reasoning": {"effort": "low"}}


# ---------------------------------------------------------------------------
# from_config
# ---------------------------------------------------------------------------

CFG = {
    "paths": {"cache_dir": "data/cache"},
    "detectors": {
        "cheap": {"provider": "vllm", "model_id": None},
        "strong": {"provider": "openrouter", "model_id": "nvidia/x:free"},
    },
    "providers": {
        "openrouter": {"base_url": "https://openrouter.ai/api/v1",
                       "api_key_env": "OPENROUTER_API_KEY", "rpm": 20},
        "vllm": {"base_url": "http://localhost:8000/v1", "api_key_env": "VLLM_API_KEY"},
    },
    "temperature": {"detector": None},
}


def test_from_config() -> None:
    det = LLMDetector.from_config("strong", CFG, env={"OPENROUTER_API_KEY": "sk"})
    assert (det.provider, det.model_id, det.rpm, det.api_key) == (
        "openrouter", "nvidia/x:free", 20, "sk")
    assert str(det.cache_dir).replace("\\", "/") == "data/cache"


def test_from_config_errors_are_clear() -> None:
    with pytest.raises(ValueError, match="no model_id"):
        LLMDetector.from_config("cheap", CFG, env={})
    with pytest.raises(ValueError, match="OPENROUTER_API_KEY is empty"):
        LLMDetector.from_config("strong", CFG, env={})
