"""D3 RagDetector: retrieve top-k known-vulnerable examples, then reuse D2's parser.

The example index excludes every repo and CVE in slots.csv (leak check).
Example tokens are logged separately from L1/L2/L3 context tokens.

Phase 4.
"""
