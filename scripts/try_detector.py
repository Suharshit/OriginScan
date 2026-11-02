"""Run the real D2 LLMDetector once on a toy vulnerable C function.

Usage (repo root, .env filled in, personal network):
    python scripts/try_detector.py              # strong detector from experiment.yaml
    python scripts/try_detector.py strong 2     # role, number of runs

Run it twice: the second time every call should say cached=True (no API use).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import yaml

try:  # verify TLS with the OS certificate store (campus/antivirus HTTPS inspection)
    import truststore

    truststore.inject_into_ssl()
except ImportError:
    pass

from originscan.exp.llm import LLMDetector, QuotaExhaustedError
from originscan.interfaces import Context

ROOT = Path(__file__).resolve().parents[1]

TOY = """// === TARGET FUNCTION (toy/greet.c:3-9) ===
void greet(const char *name) {
    char buf[16];
    strcpy(buf, "Hello, ");
    strcat(buf, name);
    printf("%s\\n", buf);
}"""


def load_env(path: Path) -> None:
    for line in path.read_text().splitlines() if path.exists() else []:
        line = line.split(" #")[0].strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip("\"'"))


def main() -> int:
    role = sys.argv[1] if len(sys.argv) > 1 else "strong"
    runs = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    load_env(ROOT / ".env")
    cfg = yaml.safe_load((ROOT / "config/experiment.yaml").read_text())
    det = LLMDetector.from_config(role, cfg, cache_dir=ROOT / cfg["paths"]["cache_dir"])
    ctx = Context(text=TOY, tokens=len(TOY.split()), items=["func:greet@toy/greet.c:3-9"])
    print(f"{role}: {det.provider} {det.model_id}")
    for run in range(runs):
        try:
            r = det.call(ctx, run)
        except QuotaExhaustedError as e:
            print(f"STOP daily quota used up: {e}")
            return 2
        print(f"run={run} status={r.status} cached={r.cached} parse_ok={r.parse_ok} "
              f"latency_ms={r.latency_ms and round(r.latency_ms)} "
              f"tokens={r.input_tokens}/{r.output_tokens}")
        print(f"  finding={r.finding}")
        if not r.parse_ok:
            print(f"  raw={(r.raw or r.error or '')[:300]!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
