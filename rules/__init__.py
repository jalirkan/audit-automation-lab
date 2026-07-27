"""Deterministic journal-entry testing rules. Each rule declares its
population, criterion, limitations, and the anomaly classes it is designed
to catch; `evaluate(ledger)` returns per-entry flags with specific
rationales. Flags are leads for auditor follow-up, never conclusions
(DECISIONS D-003). Depends only on `core` and `ledger`.
"""
