import unittest

from analytics.benford import benford_for_ledger
from analytics.profile import PopulationProfile
from ledger.anomalies import default_plan, generate_with_anomalies
from ledger.generate import GeneratorConfig
from report.document import Document, Paragraph, Table
from report.language import (
    ProhibitedLanguageError,
    find_bare_rates,
    find_prohibited,
)
from report.renderers import render_html, render_markdown
from report.workpapers import (
    build_report_card_document,
    build_rule_workpaper,
    build_sampling_workpaper,
    build_workpaper_pack,
)
from reportcard.grade import build_report_card
from rules.base import REFERENCES, Flag
from rules.library import ShortDescriptionRule
from rules.registry import evaluate_all
from sampling.attribute import attribute_sample_size, evaluate_attribute_sample


class RenderedPackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cfg = GeneratorConfig(seed=7, n_entries=1200)
        cls.led, cls.man = generate_with_anomalies(cfg, default_plan())
        cls.results = evaluate_all(cls.led)
        cls.benford = benford_for_ledger(cls.led)
        cls.profile = PopulationProfile.build(cls.led)
        cls.pack = build_workpaper_pack(cls.led, cls.results, cls.benford, cls.profile)
        card = build_report_card(
            GeneratorConfig(seed=0, n_entries=1000),
            plan=default_plan(),
            seeds=(301, 302),
        )
        cls.docs = dict(cls.pack)
        cls.docs["report-card"] = build_report_card_document(card)
        cls.docs["wp-sampling"] = build_sampling_workpaper(
            size=attribute_sample_size(0.05, 0.05),
            evaluation=evaluate_attribute_sample(60, 1, 0.05, 0.05),
        )
        cls.md = {name: render_markdown(d) for name, d in cls.docs.items()}
        cls.html = {name: render_html(d) for name, d in cls.docs.items()}

    def test_pack_contents(self):
        self.assertIn("lead-sheet", self.pack)
        self.assertIn("wp-benford", self.pack)
        self.assertEqual(
            sum(1 for k in self.pack if k.startswith("wp-r-")), 11
        )

    def test_markdown_and_html_shapes(self):
        for name, md in self.md.items():
            self.assertTrue(md.startswith("# "), name)
        for name, html in self.html.items():
            self.assertTrue(html.startswith("<!DOCTYPE html>"), name)
            self.assertIn("<style>", html)

    def test_html_is_self_contained(self):
        """Audit artifacts must render from an archive with no network
        (toolkit D-029)."""
        for name, html in self.html.items():
            for banned in ("http://", "https://", "<script", "<link"):
                self.assertNotIn(banned, html, name)

    def test_no_prohibited_language_anywhere(self):
        for name, md in self.md.items():
            self.assertEqual(find_prohibited(md), [], name)

    def test_no_bare_rates_anywhere(self):
        for name, text in list(self.md.items()) + list(self.html.items()):
            self.assertEqual(find_bare_rates(text), [], name)

    def test_rule_workpaper_structure(self):
        md = self.md["wp-r-004"]
        for section in (
            "Population",
            "Procedure and criterion",
            "References",
            "Results",
            "Limitations",
            "Conclusion (as lead)",
        ):
            self.assertIn(section, md)
        self.assertIn("complete examination", md)
        self.assertIn("leads for auditor follow-up", md)

    def test_lead_sheet_summarizes_outcomes(self):
        md = self.md["lead-sheet"]
        self.assertIn("exception", md)
        self.assertIn("Distinct entries flagged", md)
        self.assertIn("Digit conformity", md)

    def test_report_card_document_shows_honest_outcomes(self):
        md = self.md["report-card"]
        self.assertIn("inconclusive", md)  # small pools cannot pass a 0.9 floor
        self.assertIn("Per-rule precision", md)
        self.assertIn("never rounded up to pass", md)
        self.assertIn("wilson", md)

    def test_sampling_workpaper_carries_bridge(self):
        md = self.md["wp-sampling"]
        self.assertIn("complete examination", md)
        self.assertIn("n=59", md)
        self.assertIn("one-sided confidence", md)

    def test_rendering_is_deterministic(self):
        for name, doc in self.docs.items():
            self.assertEqual(render_markdown(doc), self.md[name], name)
            self.assertEqual(render_html(doc), self.html[name], name)


class LanguageGuardTests(unittest.TestCase):
    def test_guard_fires_on_planted_paragraph(self):
        doc = Document(
            title="Test",
            blocks=(Paragraph("Summary: fraud detected in entry JE-000001."),),
        )
        with self.assertRaises(ProhibitedLanguageError):
            render_markdown(doc)
        with self.assertRaises(ProhibitedLanguageError):
            render_html(doc)

    def test_guard_fires_inside_table_cells(self):
        doc = Document(
            title="Test",
            blocks=(
                Table(
                    headers=("Entry", "Note"),
                    rows=(("JE-000001", "This is fraudulent entry activity"),),
                ),
            ),
        )
        with self.assertRaises(ProhibitedLanguageError):
            render_markdown(doc)

    def test_reference_summaries_are_legitimate(self):
        for ref, summary in REFERENCES.items():
            self.assertEqual(find_prohibited(summary), [], ref)

    def test_bare_rate_scanner_fires_on_planted_violation(self):
        self.assertEqual(
            find_bare_rates("The deviation rate was 12.5% overall."),
            ["The deviation rate was 12.5% overall."],
        )
        self.assertEqual(
            find_bare_rates("Flagged 12/960 (1.25%) of the population."), []
        )
        self.assertEqual(find_bare_rates("rate 0.0125 (95% wilson, n=960)"), [])


class ExceptionCapTests(unittest.TestCase):
    def test_rows_capped_with_note(self):
        led = generate_with_anomalies(
            GeneratorConfig(seed=7, n_entries=1200), default_plan()
        )[0]
        rule = ShortDescriptionRule()
        flags = [
            Flag(rule.rule_id, e.entry_id, "test rationale")
            for e in led.entries[:30]
        ]
        res = {
            "rule": rule,
            "applicable": True,
            "reason": "",
            "population_size": len(led),
            "flags": flags,
        }
        md = render_markdown(build_rule_workpaper(res, led))
        self.assertIn("first 25 of 30", md)
        self.assertEqual(md.count("test rationale"), 25)


class DocumentModelTests(unittest.TestCase):
    def test_row_width_validated(self):
        with self.assertRaises(ValueError):
            Table(headers=("a", "b"), rows=(("only one",),))

    def test_html_escapes_markup(self):
        doc = Document(
            title="T", blocks=(Paragraph("amount <b>5</b> & more"),)
        )
        html = render_html(doc)
        self.assertIn("&lt;b&gt;5&lt;/b&gt; &amp; more", html)

    def test_markdown_escapes_pipes_in_cells(self):
        doc = Document(
            title="T",
            blocks=(Table(headers=("x",), rows=(("a|b",),)),),
        )
        self.assertIn("a\\|b", render_markdown(doc))


if __name__ == "__main__":
    unittest.main()
