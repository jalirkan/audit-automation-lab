import unittest

from ledger.anomalies import ANOMALY_CLASSES, default_plan, generate_with_anomalies
from ledger.ap import AP_DUPLICATE_CLASSES
from ledger.drift import DRIFT_CLASSES
from ledger.generate import GeneratorConfig
from rules.base import REFERENCES
from rules.registry import (
    ap_rules,
    build_rules,
    continuous_rules,
    default_rules,
    evaluate_all,
)


class RegistryTests(unittest.TestCase):
    def test_eleven_rules_with_unique_sorted_ids(self):
        rules = default_rules()
        ids = [r.rule_id for r in rules]
        self.assertEqual(len(ids), 11)
        self.assertEqual(ids, sorted(ids))
        self.assertEqual(len(set(ids)), 11)

    def test_every_anomaly_class_has_a_designed_rule(self):
        covered = set()
        for r in default_rules():
            covered |= set(r.targets)
        self.assertEqual(covered, set(ANOMALY_CLASSES))

    def test_metadata_complete(self):
        for r in default_rules():
            d = r.describe()
            self.assertTrue(d["title"], r.rule_id)
            self.assertTrue(d["population"], r.rule_id)
            self.assertTrue(d["criterion"], r.rule_id)
            self.assertTrue(d["limitations"], r.rule_id)
            for ref in d["references"]:
                self.assertIn(ref, REFERENCES, r.rule_id)

    def test_unknown_rule_id_fails_loudly(self):
        with self.assertRaises(ValueError) as ctx:
            build_rules(["R-999"])
        self.assertIn("R-001", str(ctx.exception))

    def test_subset_build(self):
        rules = build_rules(["R-004", "R-001"])
        self.assertEqual([r.rule_id for r in rules], ["R-001", "R-004"])


class ContinuousBatteryTests(unittest.TestCase):
    """Two batteries, kept apart on purpose (DECISIONS D-030). The
    point-in-time battery must not acquire a rule that needs a year of
    monthly batches to run, and its report card must not acquire a class no
    point-in-time rule targets."""

    def test_continuous_rules_are_not_in_the_default_battery(self):
        default_ids = {r.rule_id for r in default_rules()}
        continuous_ids = {r.rule_id for r in continuous_rules()}
        self.assertEqual(continuous_ids, {"R-012"})
        self.assertEqual(default_ids & continuous_ids, set())

    def test_no_point_in_time_rule_targets_a_drift_class(self):
        for rule in default_rules():
            self.assertEqual(set(rule.targets) & set(DRIFT_CLASSES), set(), rule.rule_id)

    def test_every_drift_class_has_a_designed_continuous_rule(self):
        covered = set()
        for r in continuous_rules():
            covered |= set(r.targets)
        self.assertEqual(covered, set(DRIFT_CLASSES))

    def test_metadata_complete(self):
        for r in continuous_rules():
            d = r.describe()
            self.assertTrue(d["title"], r.rule_id)
            self.assertTrue(d["population"], r.rule_id)
            self.assertTrue(d["criterion"], r.rule_id)
            self.assertTrue(d["limitations"], r.rule_id)
            self.assertTrue(d["params"], r.rule_id)
            for ref in d["references"]:
                self.assertIn(ref, REFERENCES, r.rule_id)

    def test_continuous_rules_are_reachable_by_id(self):
        (rule,) = build_rules(["R-012"])
        self.assertEqual(rule.rule_id, "R-012")


class APBatteryTests(unittest.TestCase):
    """The third battery, kept apart for the reason recorded in D-033: its
    rules read subledger document fields a general ledger does not have, so
    they refuse to run on one, and no GL rule targets an AP duplicate
    class."""

    def test_ap_rules_are_not_in_the_other_batteries(self):
        ap_ids = {r.rule_id for r in ap_rules()}
        self.assertEqual(ap_ids, {"AP-001", "AP-002"})
        self.assertEqual(ap_ids & {r.rule_id for r in default_rules()}, set())
        self.assertEqual(ap_ids & {r.rule_id for r in continuous_rules()}, set())

    def test_no_other_rule_targets_an_ap_duplicate_class(self):
        for rule in default_rules() + continuous_rules():
            self.assertEqual(
                set(rule.targets) & set(AP_DUPLICATE_CLASSES), set(), rule.rule_id
            )

    def test_every_ap_class_has_a_designed_rule(self):
        covered = set()
        for r in ap_rules():
            covered |= set(r.targets)
        self.assertEqual(covered, set(AP_DUPLICATE_CLASSES))

    def test_metadata_complete(self):
        for r in ap_rules():
            d = r.describe()
            self.assertTrue(d["title"], r.rule_id)
            self.assertTrue(d["population"], r.rule_id)
            self.assertTrue(d["criterion"], r.rule_id)
            self.assertTrue(d["limitations"], r.rule_id)
            self.assertTrue(d["params"], r.rule_id)
            for ref in d["references"]:
                self.assertIn(ref, REFERENCES, r.rule_id)

    def test_ap_rules_are_reachable_by_id(self):
        rules = build_rules(["AP-002", "AP-001"])
        self.assertEqual([r.rule_id for r in rules], ["AP-001", "AP-002"])


class BatterySmokeTests(unittest.TestCase):
    """End-to-end: on a planted ledger, every anomaly instance is hit by at
    least one of the rules *designed* for its class. This is the seed-fixed
    smoke check; measured recall with intervals is Phase 3's job."""

    @classmethod
    def setUpClass(cls):
        cfg = GeneratorConfig(seed=7, n_entries=1200)
        cls.led, cls.man = generate_with_anomalies(cfg, default_plan())
        cls.results = evaluate_all(cls.led)

    def test_all_rules_ran(self):
        self.assertEqual(len(self.results), 11)
        for rid, r in self.results.items():
            self.assertTrue(r["applicable"], f"{rid}: {r['reason']}")

    def test_each_planted_instance_hit_by_designed_rule(self):
        rules_by_target = {}
        for rid, res in self.results.items():
            for target in res["rule"].targets:
                rules_by_target.setdefault(target, []).append(res)
        for anomaly in self.man.anomalies:
            hit = False
            for res in rules_by_target.get(anomaly.anomaly_class, []):
                flagged = {f.entry_id for f in res["flags"]}
                if flagged & set(anomaly.entry_ids):
                    hit = True
                    break
            self.assertTrue(
                hit, f"{anomaly.anomaly_id} ({anomaly.anomaly_class}) missed"
            )

    def test_flags_are_deterministic(self):
        again = evaluate_all(self.led)
        for rid in self.results:
            a = [f.to_dict() for f in self.results[rid]["flags"]]
            b = [f.to_dict() for f in again[rid]["flags"]]
            self.assertEqual(a, b, rid)


if __name__ == "__main__":
    unittest.main()
