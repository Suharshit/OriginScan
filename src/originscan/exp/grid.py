"""CallRecord (one results-grid row per detector call), Parquet writer,
resume support and the completeness check.

Labels are never stored in the grid; they are joined later by version_id.

Phase 1 (CallRecord) and Phase 5 (writer, resume, check).
"""
