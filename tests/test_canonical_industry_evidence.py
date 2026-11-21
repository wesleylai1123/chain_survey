from __future__ import annotations

import unittest

from scripts.build_canonical_industry_evidence import build_canonical_evidence


class CanonicalIndustryEvidenceTests(unittest.TestCase):
    def test_combines_official_and_free_sources(self) -> None:
        frame = build_canonical_evidence()
        self.assertGreater(len(frame), 3)
        self.assertIn("REAL_POINT_IN_TIME", set(frame["provenance"]))
        self.assertIn("REAL_POINT_IN_TIME_FREE", set(frame["provenance"]))
        self.assertIn("ABF", set(frame["chain"]))
        self.assertIn("Memory", set(frame["chain"]))
        self.assertIn("CCL", set(frame["chain"]))

    def test_no_duplicate_evidence_ids(self) -> None:
        frame = build_canonical_evidence()
        self.assertEqual(frame["evidence_id"].nunique(), len(frame))

    def test_as_of_never_precedes_publication(self) -> None:
        frame = build_canonical_evidence()
        self.assertTrue((frame["as_of_date"] >= frame["published_at"]).all())


if __name__ == "__main__":
    unittest.main()
