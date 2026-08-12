"""Focused regression tests for the remote-sensing literature profile."""

from __future__ import annotations

import unittest

from daily_arxiv.relevance import enrich_and_filter, load_profile


class ResearchProfileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.profile = load_profile()

    def test_rejects_background_only_target_detection_reference(self) -> None:
        paper = {
            "id": "sar2agri",
            "title": "SAR2Agri: Learning SAR Intensity Representations for Agricultural Monitoring",
            "summary": (
                "Synthetic aperture radar remote sensing supports agricultural monitoring. "
                "It can support several downstream tasks including crop mapping and "
                "target detection, but this work learns representations for crop monitoring."
            ),
        }

        selected, _ = enrich_and_filter([paper], self.profile)

        self.assertEqual(selected, [])

    def test_keeps_lightweight_remote_sensing_detector(self) -> None:
        paper = {
            "id": "interpruner",
            "title": "InterPruner: Structured Pruning for Multimodal Object Detection",
            "summary": (
                "This remote sensing RGB-infrared detector reduces model cost through "
                "structured pruning for efficient object detection."
            ),
        }

        selected, _ = enrich_and_filter([paper], self.profile)

        self.assertEqual(len(selected), 1)
        self.assertGreaterEqual(selected[0]["relevance_score"], 12)
        self.assertIn("object_detection", selected[0]["title_relevance_matches"][0])

    def test_keeps_journal_metadata_with_detection_in_title(self) -> None:
        paper = {
            "id": "journal-record",
            "title": "Efficient Object Detection in Optical Remote Sensing Imagery",
            "journal": "IEEE Transactions on Geoscience and Remote Sensing",
            "summary": "Abstract unavailable in Crossref metadata.",
        }

        selected, _ = enrich_and_filter([paper], self.profile)

        self.assertEqual(len(selected), 1)
        self.assertIn("object_detection", selected[0]["title_relevance_matches"][0])


if __name__ == "__main__":
    unittest.main()
