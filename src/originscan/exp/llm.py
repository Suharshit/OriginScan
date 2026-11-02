"""D2 zero-shot LLMDetector and its robust JSON reply parser.

One class serves every provider in ``config/experiment.yaml`` (Groq, OpenRouter,
Google AI Studio, Cerebras, self-hosted vLLM): they all speak the OpenAI chat API.

- ``LLMDetector.call(ctx, run)`` returns an ``LLMCall`` with everything the grid row
  (``grid.CallRecord``) needs: finding, ``parse_ok``, ``status``, tokens, latency.
- ``LLMDetector.run(ctx, run)`` satisfies ``interfaces.DetectorAdapter`` for the CLI
  and escalation loop; a failed or unparsable call becomes a "not vulnerable, zero
  confidence" ``Finding`` so a scan never crashes.

Reliability on free tiers:
- per-provider throttle (``rpm`` in config), shared by every detector in the process;
- retries with exponential backoff on HTTP 429 and 5xx, and on timeouts;
- a 429 that names a *daily* limit raises ``QuotaExhaustedError`` so a run stops cleanly
  and resumes the next day (resume skips calls already in the cache/grid);
- prompts over the provider's ``max_input_tokens`` are skipped (``status="too_large"``);
- every reply is cached on disk, keyed by (prompt, model, run, sampling settings), so
  no call is ever paid for twice.

Phase 3.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from originscan.interfaces import Finding

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from originscan.interfaces import Context

PROMPT_VERSION = "d2_v1"
"""Bump whenever SYSTEM_PROMPT or USER_TEMPLATE change; it is part of the cache key."""

SYSTEM_PROMPT = """\
You are a security auditor for C and C++ code. You are shown one TARGET FUNCTION,
sometimes with surrounding context from the same repository. Decide whether the
TARGET FUNCTION contains a security vulnerability. Use the context only to
understand the target; do not report problems that are only in the context.

Answer with exactly one JSON object and nothing else:
{"vulnerable": true or false,
 "cwe": "CWE-<number>" or null,
 "line": <line number inside the target function, counting its first line as 1> or null,
 "confidence": <number from 0 to 1>,
 "reason": "<one short sentence>"}"""

USER_TEMPLATE = """\
{context}

Is the TARGET FUNCTION vulnerable? Reply with the JSON object only."""

STATUS_OK = "ok"
STATUS_PARSE_ERROR = "parse_error"
STATUS_TOO_LARGE = "too_large"
STATUS_ERROR = "error"

_RETRY_CODES = frozenset({408, 409, 429, 500, 502, 503, 504})
_DAILY_HINTS = ("per day", "per-day", "tokens per day", "requests per day", "(tpd)", "(rpd)",
                "daily", "free-models-per-day")


class QuotaExhaustedError(RuntimeError):
    """A provider's daily quota is used up. Stop the run and resume tomorrow."""


# ---------------------------------------------------------------------------
# Reply parsing
# ---------------------------------------------------------------------------

_THINK_RE = re.compile(r"<(think|thought|thinking|reasoning)>.*?</\1>", re.S | re.I)
_OPEN_THINK_RE = re.compile(r"^\s*<(think|thought|thinking|reasoning)>.*", re.S | re.I)
_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.S | re.I)
_CWE_RE = re.compile(r"(?:cwe)?[\s_-]*(\d{1,4})", re.I)


@dataclass(frozen=True, slots=True)
class ParsedReply:
    """Fields read from one model reply. ``ok`` is False if no verdict was found."""

    ok: bool
    vulnerable: bool | None = None
    cwe: str | None = None
    line: int | None = None
    confidence: float | None = None


def strip_reasoning(text: str) -> str:
    """Remove <think>/<thought> blocks (Gemma 4, reasoning models) from a reply."""
    text = _THINK_RE.sub("", text)
    # An unclosed block (reply cut off by max_tokens) has no answer after it.
    return _OPEN_THINK_RE.sub("", text).strip()


def _first_json_object(text: str) -> dict[str, Any] | None:
    """Return the first balanced {...} in *text* that parses as a JSON object."""
    for start in (i for i, ch in enumerate(text) if ch == "{"):
        depth = 0
        in_str = False
        escape = False
        for end in range(start, len(text)):
            ch = text[end]
            if in_str:
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == '"':
                    in_str = False
            elif ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        obj = json.loads(text[start : end + 1])
                    except json.JSONDecodeError:
                        break
                    if isinstance(obj, dict):
                        return obj
                    break
    return None


def _as_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        v = value.strip().lower()
        if v in {"true", "yes", "vulnerable", "1"}:
            return True
        if v in {"false", "no", "safe", "not vulnerable", "0"}:
            return False
    return None


def normalize_cwe(value: Any) -> str | None:
    """'CWE-787', 'cwe787', '787', 787 -> 'CWE-787'. Anything else -> None."""
    if value is None or isinstance(value, bool):
        return None
    m = _CWE_RE.fullmatch(str(value).strip())
    return f"CWE-{int(m.group(1))}" if m else None


def _as_line(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        line = int(str(value).strip())
    except ValueError:
        return None
    return line if line > 0 else None


def _as_confidence(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    text = str(value).strip()
    try:
        conf = float(text.rstrip("%").strip())
    except ValueError:
        return None
    # "80%" or a whole number 2..100 means a percentage; 1.4 is an overshoot, capped at 1.
    if text.endswith("%") or (conf > 1.0 and conf <= 100.0 and conf.is_integer()):
        conf /= 100.0
    return min(1.0, max(0.0, conf))


def parse_reply(text: str | None) -> ParsedReply:
    """Read verdict, CWE, line and confidence from a model reply. Never raises."""
    if not text:
        return ParsedReply(ok=False)
    body = strip_reasoning(text)
    candidates = [m.group(1) for m in _FENCE_RE.finditer(body)] + [body]
    for cand in candidates:
        obj = _first_json_object(cand)
        if obj is None:
            continue
        lower = {str(k).lower(): v for k, v in obj.items()}
        vulnerable = _as_bool(lower.get("vulnerable", lower.get("verdict")))
        if vulnerable is None:
            continue
        return ParsedReply(
            ok=True,
            vulnerable=vulnerable,
            cwe=normalize_cwe(lower.get("cwe")) if vulnerable else None,
            line=_as_line(lower.get("line")) if vulnerable else None,
            confidence=_as_confidence(lower.get("confidence")),
        )
    return ParsedReply(ok=False)


# ---------------------------------------------------------------------------
# Throttle and cache
# ---------------------------------------------------------------------------

_LAST_CALL: dict[str, float] = {}
"""provider -> monotonic time of the last request (shared across detectors)."""


def _throttle(provider: str, rpm: float | None, sleep: Callable[[float], None]) -> None:
    if not rpm:
        return
    gap = 60.0 / float(rpm)
    last = _LAST_CALL.get(provider)
    now = time.monotonic()
    if last is not None and now - last < gap:
        sleep(gap - (now - last))
    _LAST_CALL[provider] = time.monotonic()


def _safe(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("_") or "x"


# ---------------------------------------------------------------------------
# Detector
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class LLMCall:
    """Everything one detector call produced (feeds ``grid.CallRecord``)."""

    finding: Finding | None
    """None when the call failed or the reply did not parse."""
    parse_ok: bool
    status: str
    input_tokens: int | None
    output_tokens: int | None
    latency_ms: float | None
    cached: bool
    raw: str | None
    error: str | None
    model_id: str
    provider: str
    prompt_version: str = PROMPT_VERSION


@dataclass
class LLMDetector:
    """Zero-shot (D2) LLM detector over any OpenAI-compatible endpoint."""

    name: str
    provider: str
    model_id: str
    base_url: str
    api_key: str
    rpm: float | None = None
    max_input_tokens: int | None = None
    temperature: float | None = None
    max_tokens: int = 2048
    timeout_s: float = 300.0
    max_retries: int = 5
    cache_dir: Path | None = None
    extra_body: dict[str, Any] = field(default_factory=dict)
    client: Any = None
    """OpenAI-style client; built lazily. Tests pass a fake."""
    sleep: Callable[[float], None] = time.sleep

    # -- construction -------------------------------------------------------

    @classmethod
    def from_config(
        cls,
        role: str,
        cfg: Mapping[str, Any],
        *,
        env: Mapping[str, str] | None = None,
        cache_dir: Path | str | None = None,
    ) -> LLMDetector:
        """Build the detector ``cfg["detectors"][role]`` (e.g. "cheap", "strong")."""
        spec = (cfg.get("detectors") or {}).get(role)
        if not spec or not spec.get("model_id"):
            raise ValueError(f"detectors.{role} has no model_id in experiment.yaml")
        prov_name = spec["provider"]
        prov = (cfg.get("providers") or {}).get(prov_name)
        if not prov:
            raise ValueError(f"provider {prov_name!r} is not defined under providers:")
        env = os.environ if env is None else env
        key_name = prov.get("api_key_env", "")
        api_key = env.get(key_name, "")
        if not api_key:
            raise ValueError(f"{key_name} is empty; add it to .env (see docs/setup-models.md)")
        temps = cfg.get("temperature") or {}
        if cache_dir is None:
            cache_dir = (cfg.get("paths") or {}).get("cache_dir")
        return cls(
            name=role,
            provider=prov_name,
            model_id=spec["model_id"],
            base_url=prov["base_url"],
            api_key=api_key,
            rpm=prov.get("rpm"),
            max_input_tokens=prov.get("max_input_tokens"),
            temperature=temps.get("detector"),
            max_tokens=int(spec.get("max_tokens", 2048)),
            cache_dir=Path(cache_dir) if cache_dir else None,
            extra_body=dict(spec.get("extra_body") or {}),
        )

    def _client(self) -> Any:
        if self.client is None:
            from openai import OpenAI  # lazy: core installs don't need the exp extras

            self.client = OpenAI(
                base_url=self.base_url,
                api_key=self.api_key,
                timeout=self.timeout_s,
                max_retries=0,  # retries are ours, so we can spot daily quotas
                default_headers={"User-Agent": "originscan/0.1"},
            )
        return self.client

    # -- prompt and cache ---------------------------------------------------

    @staticmethod
    def messages(ctx: Context) -> list[dict[str, str]]:
        return [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": USER_TEMPLATE.format(context=ctx["text"])},
        ]

    def cache_key(self, ctx: Context, run: int) -> str:
        payload = json.dumps(
            {
                "prompt_version": PROMPT_VERSION,
                "provider": self.provider,
                "model": self.model_id,
                "messages": self.messages(ctx),
                "run": run,
                "temperature": self.temperature,
                "max_tokens": self.max_tokens,
                "extra_body": self.extra_body,
            },
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _cache_path(self, key: str) -> Path | None:
        if self.cache_dir is None:
            return None
        return self.cache_dir / _safe(self.provider) / _safe(self.model_id) / f"{key}.json"

    # -- calling ------------------------------------------------------------

    def _request(self, ctx: Context) -> tuple[str, int | None, int | None]:
        kwargs: dict[str, Any] = {
            "model": self.model_id,
            "messages": self.messages(ctx),
            "max_tokens": self.max_tokens,
        }
        if self.temperature is not None:
            kwargs["temperature"] = self.temperature
        if self.extra_body:
            kwargs["extra_body"] = self.extra_body
        resp = self._client().chat.completions.create(**kwargs)
        msg = resp.choices[0].message
        text = getattr(msg, "content", None) or ""
        usage = getattr(resp, "usage", None)
        return (
            text,
            getattr(usage, "prompt_tokens", None),
            getattr(usage, "completion_tokens", None),
        )

    def _request_with_retries(self, ctx: Context) -> tuple[str, int | None, int | None]:
        delay = 5.0
        for attempt in range(self.max_retries + 1):
            _throttle(self.provider, self.rpm, self.sleep)
            try:
                return self._request(ctx)
            except Exception as exc:
                code = _status_code(exc)
                message = str(exc)
                if code == 429 and any(h in message.lower() for h in _DAILY_HINTS):
                    who = f"{self.provider}/{self.model_id}"
                    raise QuotaExhaustedError(f"{who}: {message}") from exc
                retryable = code in _RETRY_CODES or _is_timeout(exc)
                if not retryable or attempt == self.max_retries:
                    raise
                self.sleep(_retry_after(exc) or delay)
                delay = min(delay * 2, 120.0)
        raise AssertionError("unreachable")

    def call(self, ctx: Context, run: int) -> LLMCall:
        """Run the detector once. Never raises, except ``QuotaExhaustedError``."""
        base = {"model_id": self.model_id, "provider": self.provider}
        if self.max_input_tokens and ctx["tokens"] > self.max_input_tokens:
            return LLMCall(None, False, STATUS_TOO_LARGE, None, None, None, False, None,
                           f"context {ctx['tokens']} > {self.max_input_tokens} tokens", **base)

        key = self.cache_key(ctx, run)
        path = self._cache_path(key)
        if path is not None and path.exists():
            rec = json.loads(path.read_text(encoding="utf-8"))
            return self._result(ctx, rec["raw"], rec.get("input_tokens"),
                                rec.get("output_tokens"), rec.get("latency_ms"), True)

        start = time.perf_counter()
        try:
            raw, tin, tout = self._request_with_retries(ctx)
        except QuotaExhaustedError:
            raise
        except Exception as exc:
            code = _status_code(exc)
            status = STATUS_TOO_LARGE if code == 413 else STATUS_ERROR
            return LLMCall(None, False, status, None, None, None, False, None,
                           f"{type(exc).__name__}: {str(exc)[:500]}", **base)
        latency_ms = (time.perf_counter() - start) * 1000.0

        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps({
                "key": key, "provider": self.provider, "model_id": self.model_id,
                "prompt_version": PROMPT_VERSION, "run": run, "raw": raw,
                "input_tokens": tin, "output_tokens": tout, "latency_ms": latency_ms,
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }), encoding="utf-8")
            tmp.replace(path)
        return self._result(ctx, raw, tin, tout, latency_ms, False)

    def _result(self, ctx: Context, raw: str, tin: int | None, tout: int | None,
                latency_ms: float | None, cached: bool) -> LLMCall:
        parsed = parse_reply(raw)
        tin = tin if tin is not None else ctx["tokens"]
        tout = tout if tout is not None else 0
        finding: Finding | None = None
        if parsed.ok:
            finding = Finding(
                verdict=bool(parsed.vulnerable),
                cwe=parsed.cwe,
                line=parsed.line,
                confidence=parsed.confidence if parsed.confidence is not None else 0.5,
                input_tokens=tin,
                output_tokens=tout,
            )
        return LLMCall(
            finding=finding,
            parse_ok=parsed.ok,
            status=STATUS_OK if parsed.ok else STATUS_PARSE_ERROR,
            input_tokens=tin,
            output_tokens=tout,
            latency_ms=latency_ms,
            cached=cached,
            raw=raw,
            error=None,
            model_id=self.model_id,
            provider=self.provider,
        )

    def run(self, ctx: Context, run: int) -> Finding:
        """``DetectorAdapter`` entry point; failures become a zero-confidence 'safe'."""
        result = self.call(ctx, run)
        if result.finding is not None:
            return result.finding
        return Finding(
            verdict=False,
            cwe=None,
            line=None,
            confidence=0.0,
            input_tokens=result.input_tokens or 0,
            output_tokens=result.output_tokens or 0,
        )


def _status_code(exc: BaseException) -> int | None:
    code = getattr(exc, "status_code", None)
    if code is None:
        code = getattr(getattr(exc, "response", None), "status_code", None)
    return int(code) if isinstance(code, int) else None


def _is_timeout(exc: BaseException) -> bool:
    name = type(exc).__name__.lower()
    return "timeout" in name or "connection" in name


def _retry_after(exc: BaseException) -> float | None:
    headers = getattr(getattr(exc, "response", None), "headers", None) or {}
    try:
        value = headers.get("retry-after")
        return min(float(value), 300.0) if value else None
    except (TypeError, ValueError):
        return None
