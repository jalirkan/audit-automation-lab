"""Language guards, enforced at the rendering boundary (DECISIONS D-003;
discipline per toolkit D-025/D-030: structural checks plus companion tests
proving each guard actually fires).

Two guards:

1. Conclusory language. Analytics produce leads; auditors conclude. The
   renderers refuse to emit phrases that assert fraud, guilt, or violation
   as established fact. The word "fraud" alone is not banned — rule
   references legitimately describe AU-C 240 / ISA 240 as fraud-related
   standards — but conclusory collocations are.

2. Bare rates. Any line showing a numeric percentage must carry its sample
   size on the same line — an "n=" or a k/n fraction. Intervals attach to
   inferential rates (report card, Benford, sampling); complete-examination
   counts are exact and state their population instead (DECISIONS D-023).
"""

import re

PROHIBITED_PHRASES = (
    "fraud detected",
    "fraud identified",
    "fraud found",
    "fraud confirmed",
    "confirmed fraud",
    "committed fraud",
    "commits fraud",
    "is fraudulent",
    "was fraudulent",
    "are fraudulent",
    "fraudulent entry",
    "fraudulent transaction",
    "evidence of fraud",
    "proof of fraud",
    "proves fraud",
    "proven fraud",
    "indicates fraud",
    "indicative of fraud",
    "constitutes fraud",
    "this is fraud",
    "violation detected",
    "violation found",
    "violation confirmed",
    "confirmed violation",
    "guilty",
    "embezzle",
    "misappropriated funds",
)

_PERCENT_RE = re.compile(r"\d(?:\.\d+)?%")
_FRACTION_RE = re.compile(r"\d+/\d+")


class ProhibitedLanguageError(ValueError):
    pass


def find_prohibited(text: str) -> list:
    low = text.lower()
    return sorted(p for p in PROHIBITED_PHRASES if p in low)


def find_bare_rates(text: str) -> list:
    """Lines with a numeric percent but no n= and no k/n fraction."""
    bad = []
    for line in text.splitlines():
        if _PERCENT_RE.search(line):
            if "n=" not in line and not _FRACTION_RE.search(line):
                bad.append(line.strip())
    return bad


def guard_document(doc) -> None:
    """Raise if any document text contains conclusory language. Called by
    every renderer before emitting a byte."""
    hits = []
    for text in doc.texts():
        for phrase in find_prohibited(str(text)):
            hits.append((phrase, str(text)[:80]))
    if hits:
        raise ProhibitedLanguageError(
            "conclusory language refused at render time: "
            + "; ".join(f"{p!r} in {t!r}" for p, t in hits[:5])
        )
