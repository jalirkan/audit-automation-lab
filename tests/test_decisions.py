"""The decision ledger is navigable by number: source cites a decision as
D-NNN and a reader follows the citation to the entry. These tests keep that
promise mechanical rather than conventional (toolkit D-030 discipline:
structural checks plus companion tests proving each check actually fires).

Four guards over DECISIONS.md:

1. Every `## ` line is a well-formed heading — `## D-NNN · YYYY-MM-DD ·
   title`, the ledger's established format.
2. Ids run 001..N in file order: ascending, no gaps, no duplicates. The
   ledger appends as it goes, so file order and numeric order are the same
   order, and a citation's number is enough to find its entry.
3. No orphaned heading tail: the ` · date · ` signature appears only in
   headings. A heading whose `## D-NNN` token is consumed by an edit leaves
   its title fused onto the end of the previous entry's body, where it reads
   as prose belonging to the wrong decision.
4. Every decision cited from source resolves to a real entry. Citations to
   the sibling ai-audit-toolkit's ledger are excluded by the marker the repo
   already uses for them ("toolkit D-NNN", "D-NNN there") — those number a
   ledger in another repo and cannot be checked from here.

Written against a real defect: the Phase 6 insertion of D-025/D-026 consumed
the `## D-023` heading token, fusing "Exact counts state their n; intervals
attach to inference" onto the tail of D-026's body and stranding the entry
that report.workpapers and report.language both cite. Guards 2, 3 and 4 each
fire on that file; the companion tests below reconstruct it to prove it.
"""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DECISIONS = ROOT / "DECISIONS.md"

# The ledger's heading format, pinned: `## D-NNN · YYYY-MM-DD · title`.
HEADING_RE = re.compile(r"^## D-(\d{3}) · (\d{4}-\d{2}-\d{2}) · (\S.*)$")
# The ` · date · ` signature, wherever it lands.
SIGNATURE_RE = re.compile(r" · \d{4}-\d{2}-\d{2} · ")

CITATION_RE = re.compile(r"D-(\d{3})")
# "toolkit D-029", "ai-audit-toolkit D-009", and the second half of a
# "toolkit D-025/D-030" chain: the marker sits before the run of D-NNN/.
_FOREIGN_BEFORE_RE = re.compile(r"toolkit\s+(?:D-\d{3}/)*$", re.IGNORECASE)
# "D-011 there" — the toolkit's ledger, named positionally.
_FOREIGN_AFTER_RE = re.compile(r"^\s*there\b")

# Documents and modules that cite decisions. Directories the repo does not
# author (.venv, .git) and generated caches stay out.
_SCAN_SUFFIXES = (".py", ".md")
_SKIP_DIRS = {".git", ".venv", "__pycache__", ".pytest_cache"}
# This module carries deliberately malformed and deliberately foreign
# citations as fixtures; they are specimens, not references to resolve.
_SKIP_FILES = {"tests/test_decisions.py"}


def read_ledger() -> str:
    return DECISIONS.read_text(encoding="utf-8")


def source_files() -> list:
    """Every repo-authored .py and .md file, DECISIONS.md included — the
    ledger cross-references itself and those citations resolve too."""
    found = []
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file() or path.suffix not in _SCAN_SUFFIXES:
            continue
        rel = path.relative_to(ROOT)
        if _SKIP_DIRS & set(rel.parts) or rel.as_posix() in _SKIP_FILES:
            continue
        found.append(path)
    return found


def headings(text: str) -> list:
    """(id, lineno) for each well-formed heading, in file order."""
    out = []
    for lineno, line in enumerate(text.splitlines(), 1):
        m = HEADING_RE.match(line)
        if m:
            out.append((int(m.group(1)), lineno))
    return out


def malformed_headings(text: str) -> list:
    """(lineno, line) for each `## ` line that is not a well-formed heading."""
    return [
        (lineno, line)
        for lineno, line in enumerate(text.splitlines(), 1)
        if line.startswith("## ") and not HEADING_RE.match(line)
    ]


def orphaned_heading_tails(text: str) -> list:
    """(lineno, line) for each line carrying the heading signature that is
    not itself a heading — the shape a consumed `## D-NNN` token leaves."""
    return [
        (lineno, line)
        for lineno, line in enumerate(text.splitlines(), 1)
        if SIGNATURE_RE.search(line) and not HEADING_RE.match(line)
    ]


def local_citations(text: str) -> list:
    """Decision numbers this repo's ledger is expected to answer for.
    Citations marked as the sibling toolkit's are skipped."""
    out = []
    for m in CITATION_RE.finditer(text):
        if _FOREIGN_BEFORE_RE.search(text[: m.start()]):
            continue
        if _FOREIGN_AFTER_RE.match(text[m.end():]):
            continue
        out.append(int(m.group(1)))
    return out


def _fuse_heading(text: str, decision_id: int) -> str:
    """Reproduce the defect: consume the `## D-NNN` token of an entry so its
    title fuses onto the end of the previous entry's body."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        m = HEADING_RE.match(line)
        if not m or int(m.group(1)) != decision_id:
            continue
        tail = line[m.end(1):]               # " · date · title"
        prev = i - 1
        while prev >= 0 and not lines[prev].strip():
            prev -= 1
        lines[prev] += tail
        del lines[prev + 1: i + 1]           # blank run and the heading line
        return "\n".join(lines) + "\n"
    raise AssertionError("D-%03d has no heading to fuse" % decision_id)


class LedgerStructureTests(unittest.TestCase):
    def test_every_heading_is_well_formed(self):
        self.assertEqual(malformed_headings(read_ledger()), [])

    def test_ids_are_dense_ascending_and_unique(self):
        ids = [d for d, _ in headings(read_ledger())]
        self.assertTrue(ids, "the ledger has no entries")
        self.assertEqual(ids, list(range(1, len(ids) + 1)))

    def test_no_orphaned_heading_tail(self):
        self.assertEqual(orphaned_heading_tails(read_ledger()), [])


class CitationTests(unittest.TestCase):
    def test_every_cited_decision_resolves(self):
        known = {d for d, _ in headings(read_ledger())}
        unresolved = {}
        for path in source_files():
            missing = sorted(
                set(local_citations(path.read_text(encoding="utf-8"))) - known
            )
            if missing:
                unresolved[str(path.relative_to(ROOT))] = missing
        self.assertEqual(unresolved, {})

    def test_the_cited_entries_are_actually_cited(self):
        """The two citations this lint was written for. If D-023 is ever
        renumbered, these fail loudly instead of drifting."""
        for name in ("report/workpapers.py", "report/language.py"):
            text = (ROOT / name).read_text(encoding="utf-8")
            self.assertIn(23, local_citations(text), name)


class GuardsFireTests(unittest.TestCase):
    """Companion tests: each guard is proved to fire on the defect it exists
    for, so a green suite means the checks ran, not that they cannot fail."""

    def setUp(self):
        self.broken = _fuse_heading(read_ledger(), 23)

    def test_gap_check_fires_on_a_consumed_heading(self):
        ids = [d for d, _ in headings(self.broken)]
        self.assertNotIn(23, ids)
        self.assertNotEqual(ids, list(range(1, len(ids) + 1)))

    def test_orphan_check_fires_on_a_consumed_heading(self):
        tails = orphaned_heading_tails(self.broken)
        self.assertEqual(len(tails), 1)
        self.assertIn("Exact counts state their n", tails[0][1])

    def test_citation_check_fires_on_a_consumed_heading(self):
        known = {d for d, _ in headings(self.broken)}
        cited = local_citations(
            (ROOT / "report" / "workpapers.py").read_text(encoding="utf-8")
        )
        self.assertTrue(set(cited) - known)

    def test_malformed_check_fires_on_a_broken_heading(self):
        self.assertEqual(
            malformed_headings("## D-023 - 2026-07-27 - title\n"),
            [(1, "## D-023 - 2026-07-27 - title")],
        )

    def test_out_of_order_ids_are_caught(self):
        out_of_order = "## D-002 · 2026-07-27 · b\n\n## D-001 · 2026-07-27 · a\n"
        ids = [d for d, _ in headings(out_of_order)]
        self.assertEqual(ids, [2, 1])
        self.assertNotEqual(ids, list(range(1, len(ids) + 1)))


class ForeignCitationTests(unittest.TestCase):
    """The toolkit marker is what keeps guard 4 honest: over-matching would
    demand entries this repo never made, under-matching would let a dangling
    local citation through."""

    def test_toolkit_citations_are_excluded(self):
        self.assertEqual(local_citations("(toolkit D-029, re-implemented)"), [])
        self.assertEqual(local_citations("per toolkit D-025/D-030: checks"), [])
        self.assertEqual(local_citations("ai-audit-toolkit D-009 (see this"), [])
        self.assertEqual(local_citations("- D-011 there: decisions compare"), [])
        self.assertEqual(local_citations("(toolkit\nD-031 framing: these are"), [])

    def test_local_citations_are_kept(self):
        keep = local_citations
        self.assertEqual(keep("intervals attach — DECISIONS\n  D-023."), [23])
        self.assertEqual(keep("timestamps (D-019): identity is"), [19])
        self.assertEqual(keep("D-008 there / D-004 here: a"), [4])
        self.assertEqual(keep("this repo's\nD-005): exact integer"), [5])


if __name__ == "__main__":
    unittest.main()
