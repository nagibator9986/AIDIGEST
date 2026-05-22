"""Service layer: ingestion, deduplication, scoring, digest, broadcasting.

Services orchestrate collectors, the AI client and repositories. They own
transaction boundaries and are the units the scheduler and CLI call.
"""
