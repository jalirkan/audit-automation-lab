import math
import unittest

from core.canonical import canonical_bytes, canonical_json


class CanonicalTests(unittest.TestCase):
    def test_known_vector(self):
        """The encoding is pinned: if this vector ever changes, every
        byte-identity claim in the project changes meaning."""
        value = {"b": 1, "a": [1.5, "é", None, True]}
        self.assertEqual(
            canonical_json(value), '{"a":[1.5,"\\u00e9",null,true],"b":1}'
        )

    def test_bytes_are_utf8_of_text(self):
        value = {"k": [1, 2, 3]}
        self.assertEqual(canonical_bytes(value), canonical_json(value).encode("utf-8"))

    def test_nan_rejected(self):
        with self.assertRaises(ValueError):
            canonical_json({"x": math.nan})
        with self.assertRaises(ValueError):
            canonical_json({"x": math.inf})

    def test_key_order_irrelevant(self):
        self.assertEqual(
            canonical_bytes({"a": 1, "b": 2}), canonical_bytes({"b": 2, "a": 1})
        )


if __name__ == "__main__":
    unittest.main()
