"""Loaders for slots.csv / labels.csv / split.csv, plus CorpusResolver.

CorpusResolver implements context.builders.SlotResolver: human versions parse
the original file; AI versions parse a temp copy with the AI body swapped in.

Phase 1 (resolver) and Phase 2 (slots, split).
"""
