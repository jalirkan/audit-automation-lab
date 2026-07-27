"""The committed example is load-bearing documentation: these tests keep it
honest (toolkit D-034's lesson — committed artifacts and the code that
regenerates them must not be able to diverge silently)."""

import json
import unittest
from pathlib import Path

from cli import EXAMPLE_ENTRIES, EXAMPLE_SEED, _example_pack_plan
from core.canonical import canonical_bytes
from ledger.anomalies import Manifest, generate_with_anomalies
from ledger.generate import GeneratorConfig
from report.language import find_bare_rates, find_prohibited

RUN = Path(__file__).resolve().parent.parent / "examples" / "run-001"


def _load(name):
    with open(RUN / name, "r", encoding="utf-8") as fh:
        return json.load(fh)


class CommittedArtifactTests(unittest.TestCase):
    def test_expected_files_committed(self):
        for name in (
            "README.md",
            "manifest.json",
            "flags.json",
            "report-card.json",
            "report-card.md",
            "report-card.html",
            "run-meta.json",
            "pack-summary.json",
        ):
            self.assertTrue((RUN / name).exists(), name)
        md = sorted(p.name for p in (RUN / "workpapers").glob("*.md"))
        html = sorted(p.name for p in (RUN / "workpapers").glob("*.html"))
        self.assertEqual(len(md), 14)
        self.assertEqual(len(html), 14)

    def test_summary_figures_are_consistent(self):
        flags = _load("flags.json")
        summary = _load("pack-summary.json")
        self.assertEqual(
            summary["n_flags"],
            sum(r["n_flags"] for r in flags["results"].values()),
        )
        readme = (RUN / "README.md").read_text(encoding="utf-8")
        self.assertIn(str(summary["n_flags"]), readme)
        card = _load("report-card.json")
        self.assertIn(card["pooled_precision"]["rendered"], readme)

    def test_committed_documents_pass_both_guards(self):
        texts = [RUN / "README.md", RUN / "report-card.md", RUN / "report-card.html"]
        texts += sorted((RUN / "workpapers").glob("*"))
        for p in texts:
            content = p.read_text(encoding="utf-8")
            self.assertEqual(find_prohibited(content), [], p.name)
            self.assertEqual(find_bare_rates(content), [], p.name)

    def test_report_card_shows_honest_outcomes(self):
        card = _load("report-card.json")
        outcomes = {c["anomaly_class"]: c["decision"]["outcome"]
                    for c in card["pooled_classes"]}
        # The capped-pair class cannot reach the sample size a pass needs.
        self.assertEqual(outcomes["unusual_pairing"], "inconclusive")
        # At least one class demonstrates a pass at n=40.
        self.assertIn("pass", outcomes.values())


class RegenerationTests(unittest.TestCase):
    def test_manifest_regenerates_byte_identically(self):
        """Ground truth must be reproducible from the seed alone. A mismatch
        here means the generator changed under the committed example (or a
        platform's libm rounds transcendentals differently — see DECISIONS
        D-026; either way, a human should look)."""
        cfg = GeneratorConfig(seed=EXAMPLE_SEED, n_entries=EXAMPLE_ENTRIES)
        _ledger, manifest = generate_with_anomalies(cfg, _example_pack_plan())
        committed = Manifest.from_dict(_load("manifest.json"))
        self.assertEqual(
            canonical_bytes(manifest.to_dict()),
            canonical_bytes(committed.to_dict()),
        )

    def test_manifest_ids_exist_in_regenerated_ledger(self):
        cfg = GeneratorConfig(seed=EXAMPLE_SEED, n_entries=EXAMPLE_ENTRIES)
        ledger, manifest = generate_with_anomalies(cfg, _example_pack_plan())
        for a in manifest.anomalies:
            for eid in a.entry_ids:
                self.assertIn(eid, ledger, a.anomaly_id)


if __name__ == "__main__":
    unittest.main()
