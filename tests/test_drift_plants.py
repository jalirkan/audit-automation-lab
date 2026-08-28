import unittest

from continuous.drift import DriftParams, analyze
from continuous.periods import period_of
from core.canonical import canonical_bytes
from ledger.anomalies import ANOMALY_CLASSES, Manifest
from ledger.drift import (
    DEFAULT_BASELINE_PERIODS,
    DRIFT_CLASSES,
    default_drift_plan,
    generate_with_drift,
)
from ledger.generate import GeneratorConfig, generate

CFG = GeneratorConfig(seed=511, n_entries=2400)


def _shares(ledger, key_fn, periods):
    """{category: (count, total)} over the given periods."""
    counts = {}
    total = 0
    for e in ledger.entries:
        if period_of(e) not in periods:
            continue
        total += 1
        k = key_fn(e)
        counts[k] = counts.get(k, 0) + 1
    return counts, total


class PlantingBasicsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan = default_drift_plan()
        cls.led, cls.man = generate_with_drift(CFG, cls.plan)
        cls.by_class = cls.man.by_class()

    def test_classes_are_disjoint_from_point_in_time_anomalies(self):
        """Drift classes must not collide with anomaly classes: the report
        card keys its per-class rows on the name, and a collision would pool
        two different plants graded by two different batteries."""
        self.assertEqual(set(DRIFT_CLASSES) & set(ANOMALY_CLASSES), set())

    def test_manifest_ids_exist_and_match_the_plan(self):
        for a in self.man.anomalies:
            self.assertIn(a.anomaly_class, DRIFT_CLASSES)
            self.assertTrue(a.entry_ids)
            for eid in a.entry_ids:
                self.assertIn(eid, self.led, f"{a.anomaly_id} references {eid}")
        for cls in DRIFT_CLASSES:
            self.assertEqual(len(self.by_class[cls]), self.plan[cls], cls)

    def test_every_instance_gets_its_own_period_outside_the_baseline(self):
        """Two plants in one month would each move the other's denominator;
        a plant inside the baseline would move the base it is measured
        against. Both are ruled out by construction and asserted here."""
        periods = []
        for a in self.man.anomalies:
            months = {period_of(self.led.entry(eid)) for eid in a.entry_ids}
            self.assertEqual(len(months), 1, a.anomaly_id)
            periods.append(months.pop())
        self.assertEqual(len(periods), len(set(periods)))
        baseline = sorted({period_of(e) for e in self.led.entries})[
            :DEFAULT_BASELINE_PERIODS
        ]
        for p in periods:
            self.assertNotIn(p, baseline)
        self.assertEqual(
            sorted(periods), self.led.meta["drift"]["planted_periods"]
        )

    def test_deterministic(self):
        led2, man2 = generate_with_drift(CFG, self.plan)
        self.assertEqual(
            canonical_bytes(self.led.to_dict()), canonical_bytes(led2.to_dict())
        )
        self.assertEqual(
            canonical_bytes(self.man.to_dict()), canonical_bytes(man2.to_dict())
        )

    def test_clean_generation_unaffected_by_planting(self):
        """The drift injector draws from its own stream (D-010): a clean
        generate() before and after is byte-identical, and differs from the
        drifted ledger."""
        clean_a = canonical_bytes(generate(CFG).to_dict())
        generate_with_drift(CFG, self.plan)
        clean_b = canonical_bytes(generate(CFG).to_dict())
        self.assertEqual(clean_a, clean_b)
        self.assertNotEqual(clean_a, canonical_bytes(self.led.to_dict()))

    def test_manifest_roundtrip(self):
        again = Manifest.from_dict(self.man.to_dict())
        self.assertEqual(
            canonical_bytes(self.man.to_dict()), canonical_bytes(again.to_dict())
        )

    def test_bad_plans_rejected(self):
        with self.assertRaises(ValueError):
            generate_with_drift(CFG, {"no_such_class": 1})
        with self.assertRaises(ValueError):
            generate_with_drift(CFG, {"manual_source_surge": -1})

    def test_more_instances_than_eligible_months_is_refused(self):
        """Nine months are eligible after a three-period baseline; asking for
        ten distinct-month plants fails loudly rather than doubling up."""
        with self.assertRaises(ValueError) as ctx:
            generate_with_drift(CFG, {"manual_source_surge": 10})
        self.assertIn("eligible months", str(ctx.exception))


class PlantedPropertyTests(unittest.TestCase):
    """Each planted class actually has the property its manifest note
    claims. The manifest is ground truth only if the plants are real —
    a plant that drifted from its own description would silently corrupt
    every recall number downstream (D-010's discipline, drift edition)."""

    @classmethod
    def setUpClass(cls):
        cls.led, cls.man = generate_with_drift(CFG, default_drift_plan())
        cls.by_class = cls.man.by_class()
        cls.baseline = sorted({period_of(e) for e in cls.led.entries})[
            :DEFAULT_BASELINE_PERIODS
        ]

    def _planted_period(self, anomaly):
        return period_of(self.led.entry(anomaly.entry_ids[0]))

    def test_preparer_concentration_actually_concentrates(self):
        for a in self.by_class["preparer_concentration_drift"]:
            period = self._planted_period(a)
            preparers = {self.led.entry(eid).preparer_id for eid in a.entry_ids}
            self.assertEqual(len(preparers), 1, a.anomaly_id)
            target = preparers.pop()

            period_counts, period_n = _shares(
                self.led, lambda e: e.preparer_id, {period}
            )
            base_counts, base_n = _shares(
                self.led, lambda e: e.preparer_id, set(self.baseline)
            )
            period_share = period_counts[target] / period_n
            base_share = base_counts.get(target, 0) / base_n
            # Designed margin is 0.22 over baseline with a 0.35 floor; the
            # detector's default materiality gate is 0.15, so the plant
            # clears it with room rather than by luck.
            self.assertGreaterEqual(period_share, 0.35, a.anomaly_id)
            self.assertGreaterEqual(period_share - base_share, 0.20, a.anomaly_id)

    def test_preparer_concentration_moves_no_volume(self):
        """Reassignment, not addition: the drifted month has exactly the
        entries the clean ledger gave it, so no volume test could take
        credit for detecting this plant."""
        clean = generate(CFG)
        clean_counts = {}
        for e in clean.entries:
            clean_counts[period_of(e)] = clean_counts.get(period_of(e), 0) + 1
        drift_counts = {}
        for e in self.led.entries:
            drift_counts[period_of(e)] = drift_counts.get(period_of(e), 0) + 1
        for a in self.by_class["preparer_concentration_drift"]:
            period = self._planted_period(a)
            self.assertEqual(drift_counts[period], clean_counts[period], period)

    def test_preparer_concentration_plants_no_self_approval(self):
        """A reassigned entry must not become one its approver also
        prepared: that is a different scenario with its own rule."""
        for a in self.by_class["preparer_concentration_drift"]:
            for eid in a.entry_ids:
                e = self.led.entry(eid)
                self.assertNotEqual(e.preparer_id, e.approver_id, eid)

    def test_manual_source_surge_actually_surges(self):
        for a in self.by_class["manual_source_surge"]:
            period = self._planted_period(a)
            for eid in a.entry_ids:
                self.assertEqual(self.led.entry(eid).source, "GL", eid)

            period_counts, period_n = _shares(self.led, lambda e: e.source, {period})
            base_counts, base_n = _shares(
                self.led, lambda e: e.source, set(self.baseline)
            )
            period_share = period_counts["GL"] / period_n
            base_share = base_counts.get("GL", 0) / base_n
            self.assertGreaterEqual(period_share, 0.35, a.anomaly_id)
            self.assertGreaterEqual(period_share - base_share, 0.20, a.anomaly_id)

    def test_manual_source_surge_leaves_the_preparer_mix_alone(self):
        """The surge is round-robined across preparers on purpose: the two
        drift classes must move different dimensions, or a detection could
        not be attributed to the dimension it was designed to test."""
        for a in self.by_class["manual_source_surge"]:
            period = self._planted_period(a)
            counts, total = _shares(self.led, lambda e: e.preparer_id, {period})
            base_counts, base_n = _shares(
                self.led, lambda e: e.preparer_id, set(self.baseline)
            )
            for preparer, k in counts.items():
                shift = k / total - base_counts.get(preparer, 0) / base_n
                self.assertLess(abs(shift), DriftParams().min_shift,
                                f"{a.anomaly_id}: {preparer}")

    def test_planted_amounts_are_never_exactly_round(self):
        """Added entries carry non-zero cents (D-008), so a drift plant can
        never double as an accidental round-dollar plant."""
        for a in self.by_class["manual_source_surge"]:
            for eid in a.entry_ids:
                self.assertNotEqual(self.led.entry(eid).amount_cents % 100, 0, eid)


class PlantedDriftIsDetectedTests(unittest.TestCase):
    """End-to-end at fixed seeds: the screen finds every plant, and fires
    nowhere else. Measured recall with intervals is the report card's job."""

    def test_every_plant_is_found_and_no_clean_period_fires(self):
        for seed in (511, 512, 513):
            cfg = GeneratorConfig(seed=seed, n_entries=2400)
            led, man = generate_with_drift(cfg, default_drift_plan())
            report = analyze(led)
            flagged = set(report.flagged_entry_ids())
            for a in man.anomalies:
                self.assertTrue(
                    set(a.entry_ids) & flagged,
                    f"seed {seed}: {a.anomaly_id} ({a.anomaly_class}) missed",
                )
            planted_periods = set(led.meta["drift"]["planted_periods"])
            for f in report.findings:
                self.assertIn(f.period, planted_periods, f.statement)

    def test_flagged_but_unplanted_entries_are_all_inside_drifted_cells(self):
        """The screen's false positives are a stated property of what it
        does — the legitimate members of a drifted cell — not stray hits
        elsewhere in the ledger."""
        led, man = generate_with_drift(CFG, default_drift_plan())
        report = analyze(led)
        planted = man.all_entry_ids()
        cells = {
            (f.period, f.dimension, f.category): set(f.entry_ids)
            for f in report.findings
        }
        false_positives = set(report.flagged_entry_ids()) - planted
        self.assertGreater(len(false_positives), 0)  # the cost is real
        for eid in false_positives:
            self.assertTrue(
                any(eid in members for members in cells.values()), eid
            )


if __name__ == "__main__":
    unittest.main()
