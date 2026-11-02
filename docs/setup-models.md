# Model setup (everyone, ~20 minutes)

All models are open-weight and run on free tiers. Each person uses **their own** accounts;
never create extra accounts to get around limits, and never commit a key.

## 1. Create two accounts and keys
| Provider | Sign up | Where the key is |
|---|---|---|
| Groq | https://console.groq.com | API Keys → Create API Key |
| OpenRouter | https://openrouter.ai | Keys → Create Key |
| Google AI Studio | https://aistudio.google.com | Get API key → Create API key (free, no card) |

OpenRouter: open **Settings → Privacy** and allow free-model providers, otherwise free
models fail with "no endpoints found matching your data policy". This is fine for us:
we only send public CVE code.

Cerebras is not needed for now (it requires a card).

## 2. Put the keys in `.env`
```
copy .env.example .env      # Windows   (macOS/Linux: cp .env.example .env)
```
Fill in `GROQ_API_KEY`, `OPENROUTER_API_KEY` and `GEMINI_API_KEY`. `.env` is git-ignored.

## 3. Install and run the smoke test
```
pip install -e ".[dev,exp]"
python scripts/smoke_models.py
```
Expected: one `OK` line per configured model, and `SKIP detector:cheap` until the
Kaggle model is chosen. Paste any `FAIL` line in the team chat.

If you see `CERTIFICATE_VERIFY_FAILED ... self-signed certificate in certificate chain`,
your network or antivirus is inspecting HTTPS. Run `pip install truststore` (already in
the `exp` extras) and retry. Never turn certificate checks off.
On the **college Wi-Fi** this still fails (it inspects HTTPS): use a personal network
or phone hotspot for API calls, or run them on Kaggle.

## 4. Kaggle GPU (P4 and P5 only)
1. Kaggle → profile → **Settings → Phone Verification**.
2. **Create → New Notebook** → right panel **Session options** →
   Accelerator **GPU T4 x2**, **Internet on**.
3. Run `!nvidia-smi`: two Tesla T4 cards (15 GB each). Quota: 30 GPU hours/week.
4. Always **Stop session** when finished; the quota runs while the session is on.

## Which model does what
See `config/experiment.yaml` (`detectors`, `generators`, `providers`) and the
2026-11-02 entry in `docs/decisions.md`. Free limits seen on Nov 2:
Groq 30 req/min, 1,000 req/day, 8k tokens/min, 200k tokens/day per model (no prompt
over ~8k tokens); OpenRouter free models 50 req/day (1,000 after a one-time $10 top-up).
