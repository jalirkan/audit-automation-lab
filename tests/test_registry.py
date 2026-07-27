import unittest

from ledger.anomalies import ANOMALY_CLASSES, default_plan, generate_with_anomalies
from ledger.generate import GeneratorConfig
from rules.base import REFERENCES
from rules.registry import build_rules, default_rules, evaluate_all


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
