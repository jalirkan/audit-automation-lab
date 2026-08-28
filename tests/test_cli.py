import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from cli import main
from report.language import find_bare_rates, find_prohibited


def run_cli(*argv) -> str:
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = main(list(argv))
    if code != 0:
        raise AssertionError(f"cli exited {code}: {argv}")
    return buf.getvalue()


class GenerateAndTestTests(unittest.TestCase):
    def test_generate_test_report_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "run"
            run_cli(
                "generate", "--seed", "7", "--entries", "900",
                "--plan", "default", "--out", str(out),
            )
            self.assertTrue((out / "ledger.json").exists())
            self.assertTrue((out / "ledger.csv").exists())
            self.assertTrue((out / "manifest.json").exists())

            run_cli("test", "--ledger", str(out))
            flags = json.loads((out / "flags.json").read_text(encoding="utf-8"))
            self.assertEqual(len(flags["results"]), 11)
            self.assertGreater(
                sum(r["n_flags"] for r in flags["results"].values()), 0
            )

            run_cli("report", "--ledger", str(out), "--out", str(out))
            wp = out / "workpapers"
            md_files = sorted(p.name for p in wp.glob("*.md"))
            self.assertIn("lead-sheet.md", md_files)
            self.assertIn("wp-r-001.md", md_files)
            self.assertIn("wp-benford.md", md_files)
            self.assertIn("wp-sampling.md", md_files)
            self.assertEqual(len(md_files), 14)  # lead + 11 rules + benford + sampling
            for p in wp.glob("*"):
                text = p.read_text(encoding="utf-8")
                self.assertEqual(find_prohibited(text), [], p.name)
                self.assertEqual(find_bare_rates(text), [], p.name)
            html = (wp / "lead-sheet.html").read_text(encoding="utf-8")
            for banned in ("http://", "https://", "<script", "<link"):
                self.assertNotIn(banned, html)

    def test_generate_is_deterministic_across_invocations(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b = Path(tmp) / "a", Path(tmp) / "b"
            for out in (a, b):
                run_cli(
                    "generate", "--seed", "11", "--entries", "400",
                    "--plan", "none", "--out", str(out),
                )
            self.assertEqual(
                (a / "ledger.json").read_bytes(), (b / "ledger.json").read_bytes()
            )
            self.assertEqual(
                (a / "ledger.csv").read_bytes(), (b / "ledger.csv").read_bytes()
            )

    def test_clean_plan_writes_no_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "clean"
            run_cli(
                "generate", "--seed", "3", "--entries", "400",
                "--plan", "none", "--out", str(out),
            )
            self.assertFalse((out / "manifest.json").exists())


class ReportCardCliTests(unittest.TestCase):
    def test_reportcard_writes_and_narrates(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "card"
            stdout = run_cli(
                "reportcard", "--entries", "800", "--seeds", "301,302",
                "--out", str(out),
            )
            self.assertIn("precision:", stdout)
            card = json.loads((out / "report-card.json").read_text(encoding="utf-8"))
            self.assertEqual(card["seeds"], [301, 302])
            md = (out / "report-card.md").read_text(encoding="utf-8")
            self.assertEqual(find_bare_rates(md), [])
            self.assertIn("wilson", md)


class ContinuousCliTests(unittest.TestCase):
    def test_generate_drift_then_continuous_pack(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "run"
            run_cli(
                "generate", "--seed", "511", "--entries", "2400",
                "--plan", "none", "--drift-plan", "default", "--out", str(out),
            )
            manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["n_anomalies"], 4)

            stdout = run_cli("continuous", "--ledger", str(out), "--out", str(out))
            self.assertIn("12 monthly batches", stdout)
            self.assertIn("drift: baseline", stdout)
            self.assertIn("aging as of", stdout)

            drift = json.loads((out / "drift.json").read_text(encoding="utf-8"))
            self.assertTrue(drift["applicable"])
            self.assertEqual(len(drift["baseline_periods"]), 3)
            self.assertEqual(drift["n_findings"], 4)
            aging = json.loads((out / "aging.json").read_text(encoding="utf-8"))
            self.assertGreater(aging["n_exceptions"], 0)
            batches = json.loads((out / "batches.json").read_text(encoding="utf-8"))
            self.assertEqual(len(batches["batches"]), 12)

            wp = out / "workpapers"
            names = sorted(p.name for p in wp.glob("*"))
            self.assertEqual(
                names, ["wp-aging.html", "wp-aging.md", "wp-drift.html", "wp-drift.md"]
            )
            for p in wp.glob("*"):
                text = p.read_text(encoding="utf-8")
                self.assertEqual(find_prohibited(text), [], p.name)
                self.assertEqual(find_bare_rates(text), [], p.name)

    def test_two_planting_modes_at_once_are_refused(self):
        """The injectors each rebuild the same raw population; composing
        them would leave each manifest describing a population the other
        had already moved."""
        with tempfile.TemporaryDirectory() as tmp:
            with redirect_stderr(io.StringIO()) as err:
                with self.assertRaises(AssertionError):
                    run_cli(
                        "generate", "--seed", "5", "--entries", "600",
                        "--plan", "default", "--drift-plan", "default",
                        "--out", str(Path(tmp) / "clash"),
                    )
            self.assertIn("--plan none", err.getvalue())
            self.assertFalse((Path(tmp) / "clash").exists())

    def test_continuous_card_writes_and_narrates(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "card"
            stdout = run_cli(
                "continuous-card", "--entries", "2400", "--seeds", "501,502",
                "--out", str(out),
            )
            self.assertIn("preparer_concentration_drift", stdout)
            self.assertIn("precision:", stdout)
            card = json.loads(
                (out / "continuous-report-card.json").read_text(encoding="utf-8")
            )
            self.assertEqual(card["seeds"], [501, 502])
            self.assertEqual(
                [c["anomaly_class"] for c in card["pooled_classes"]],
                ["manual_source_surge", "preparer_concentration_drift"],
            )
            for c in card["pooled_classes"]:
                self.assertEqual(c["designed_rules"], ["R-012"])
            md = (out / "continuous-report-card.md").read_text(encoding="utf-8")
            self.assertEqual(find_bare_rates(md), [])
            self.assertIn("wilson", md)


class SampleSizeCliTests(unittest.TestCase):
    def test_planning(self):
        stdout = run_cli("sample-size", "--tolerable", "0.05", "--risk", "0.05")
        self.assertIn("n=59", stdout)

    def test_evaluation(self):
        stdout = run_cli(
            "sample-size", "--tolerable", "0.05", "--risk", "0.05",
            "--n", "60", "--deviations", "1",
        )
        self.assertIn("outcome: inconclusive", stdout)
        self.assertIn("n=60", stdout)


if __name__ == "__main__":
    unittest.main()
