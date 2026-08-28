"""Continuous mode: monthly batches, population-profile drift against a
baseline period, and exception aging (PLAN.md Stretch item 1).

The point-in-time battery asks "what is wrong in this ledger?". Continuous
mode asks the question a monitoring programme asks instead: "what changed
about this population, and how long has this lead been sitting there?".
Both answers are still leads (DECISIONS D-003) — a composition shift is a
direction to look, never a finding about an entry.

Depends on `analytics`, `ledger` and `core`; the drift *rule* that wraps
this lives in `rules/drift.py`, and the planted drift that grades it lives
in `ledger/drift.py`.
"""
