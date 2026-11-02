"""Smoke test: one tiny call to every model in config/experiment.yaml.

Usage (from the repo root, with your .env filled in):
    python scripts/smoke_models.py           # one short call per model
    python scripts/smoke_models.py --list google gemma   # print exact model IDs
    python scripts/smoke_models.py --big     # also confirm Groq refuses an L3-size prompt

Uses only the standard library + PyYAML (+ truststore if installed, so HTTPS works behind
college or antivirus TLS inspection). Works before the exp extras are installed.
Never prints keys. Exit code 1 if any configured model fails.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import yaml

try:  # verify TLS with the OS certificate store (needed behind college/antivirus HTTPS inspection)
    import truststore

    truststore.inject_into_ssl()
except ImportError:
    pass

ROOT = Path(__file__).resolve().parents[1]


def load_env(path: Path) -> None:
    if not path.exists():
        sys.exit(f"Missing {path}. Copy .env.example to .env and add your keys.")
    for line in path.read_text().splitlines():
        line = line.split(" #")[0].strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip("\"'"))


def call(base_url: str, key: str, model: str, prompt: str, max_tokens: int) -> str:
    body = json.dumps(
        {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": 0,
        }
    ).encode()
    req = urllib.request.Request(
        base_url.rstrip("/") + "/chat/completions",
        data=body,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            # Cloudflare (Groq) blocks Python's default User-Agent with "error code: 1010"
            "User-Agent": "originscan-smoke/0.1",
        },
    )
    t = time.time()
    for attempt in range(3):  # free models are often busy (429) or flaky (5xx): wait and retry
        try:
            r = json.load(urllib.request.urlopen(req, timeout=180))
            break
        except urllib.error.HTTPError as e:
            if e.code not in (429, 500, 502, 503) or attempt == 2:
                raise
            time.sleep(15 * (attempt + 1))
    u = r.get("usage", {})
    text = (r["choices"][0]["message"].get("content") or "").strip().replace("\n", " ")
    return f"{time.time() - t:5.1f}s  tokens in/out={u.get('prompt_tokens')}/{u.get('completion_tokens')}  reply={text[:40]!r}"


def list_models(p: dict, filt: str) -> int:
    req = urllib.request.Request(
        p["base_url"].rstrip("/") + "/models",
        headers={"Authorization": f"Bearer {os.environ.get(p['api_key_env'], '')}",
                 "User-Agent": "originscan-smoke/0.1"},
    )
    data = json.load(urllib.request.urlopen(req, timeout=60)).get("data", [])
    for m in data:
        if filt.lower() in m.get("id", "").lower():
            print(m["id"])
    return 0


def main() -> int:
    load_env(ROOT / ".env")
    cfg = yaml.safe_load((ROOT / "config/experiment.yaml").read_text())
    providers = cfg["providers"]
    if "--list" in sys.argv:  # e.g. --list google gemma
        args = sys.argv[sys.argv.index("--list") + 1 :]
        return list_models(providers[args[0]], args[1] if len(args) > 1 else "")
    targets = [(f"detector:{k}", d) for k, d in cfg["detectors"].items()]
    targets += [(f"generator:{g['key']}", g) for g in cfg["generators"]]

    failed = 0
    for role, m in targets:
        if not m or not m.get("model_id"):
            print(f"SKIP {role:15} (model_id not set yet)")
            continue
        p = providers[m["provider"]]
        key = os.environ.get(p["api_key_env"], "")
        if not key:
            print(f"FAIL {role:15} {p['api_key_env']} is empty in .env")
            failed += 1
            continue
        try:
            out = call(p["base_url"], key, m["model_id"], "Reply with the single word OK.", 300)
            print(f"OK   {role:15} {m['provider']:10} {m['model_id']:42} {out}")
        except urllib.error.HTTPError as e:
            print(f"FAIL {role:15} {m['model_id']} HTTP {e.code}: {e.read().decode()[:300]}")
            failed += 1
        except Exception as e:  # noqa: BLE001
            print(f"FAIL {role:15} {m['model_id']} {type(e).__name__}: {e}")
            failed += 1

    if "--big" in sys.argv:
        p = providers["groq"]
        big = "int f(int x) { return x + 1; }\n" * 1100 + "\nIs this vulnerable? Reply YES or NO."
        try:
            out = call(p["base_url"], os.environ[p["api_key_env"]], "openai/gpt-oss-120b", big, 20)
            print(f"NOTE groq L3-size prompt was ACCEPTED ({out}) - update decisions.md")
        except urllib.error.HTTPError as e:
            msg = e.read().decode()[:200]
            if e.code == 413 or "too large" in msg.lower():
                print(f"OK   groq L3-size prompt refused as expected: HTTP {e.code} {msg}")
            else:
                print(f"FAIL groq L3-size check got an unexpected error: HTTP {e.code} {msg}")
                failed += 1
        except Exception as e:  # noqa: BLE001
            print(f"FAIL groq L3-size check could not connect: {type(e).__name__}: {e}")
            failed += 1
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
