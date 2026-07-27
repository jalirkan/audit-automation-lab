"""Canonical JSON encoding — one logical value, one byte sequence.

Re-implements the discipline of ai-audit-toolkit D-009 (see this repo's
DECISIONS.md): sorted keys, tight separators, ASCII escapes, UTF-8 bytes,
NaN/Infinity rejected outright. Every determinism claim in this lab
("same seed, byte-identical ledger") is checked by comparing bytes produced
here, so the encoding is pinned in one place and covered by a known-vector
test that fails loudly if it ever changes.
"""

import json


def canonical_json(value) -> str:
    """Render *value* as canonical JSON text.

    Raises ValueError on NaN/Infinity: a non-finite number in a record is a
    bug at the point of construction, and rejecting it here keeps the
    offending value traceable.
    """
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )


def canonical_bytes(value) -> bytes:
    """Canonical JSON as UTF-8 bytes — the unit of byte-identity tests."""
    return canonical_json(value).encode("utf-8")
