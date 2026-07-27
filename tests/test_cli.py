import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
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
