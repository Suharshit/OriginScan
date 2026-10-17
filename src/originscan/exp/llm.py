"""D2 zero-shot LLMDetector and its robust JSON reply parser.

Returns interfaces.Finding; extra fields (parse_ok, raw reply, latency, model)
go into grid.CallRecord. Retries with backoff and a response cache keyed by
(prompt hash, model, run).

Phase 3.
"""
