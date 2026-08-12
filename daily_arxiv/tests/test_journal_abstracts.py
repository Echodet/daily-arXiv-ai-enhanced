"""Regression tests for supplemental journal-abstract retrieval."""

from __future__ import annotations

import unittest

from daily_arxiv.enrich_journal_abstracts import (
    enrich_missing_abstracts,
    reconstruct_openalex_abstract,
)


class FakeResponse:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self.payload


class FakeSession:
    headers: dict[str, str] = {}

    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.calls: list[tuple[str, dict | None]] = []

    def get(self, url: str, params: dict | None, timeout: int) -> FakeResponse:
        self.calls.append((url, params))
        return FakeResponse(self.payload)


class JournalAbstractTests(unittest.TestCase):
    def test_reconstructs_openalex_inverted_index(self) -> None:
        abstract = reconstruct_openalex_abstract(
            {"detection": [2], "Remote": [0], "sensing": [1]}
        )

        self.assertEqual(abstract, "Remote sensing detection")

    def test_enriches_only_metadata_only_crossref_records(self) -> None:
        papers = [
            {
                "id": "doi:10.1000/example",
                "source": "crossref",
                "doi": "10.1000/example",
                "summary": "Abstract unavailable in Crossref metadata.",
                "abstract_available": False,
            },
            {
                "id": "arxiv:1",
                "source": "arxiv",
                "summary": "Existing arXiv abstract.",
                "abstract_available": True,
            },
        ]
        session = FakeSession(
            {
                "doi": "https://doi.org/10.1000/example",
                "id": "https://openalex.org/W123",
                "abstract_inverted_index": {"Remote": [0], "detection": [2], "sensing": [1]},
            }
        )

        stats = enrich_missing_abstracts(
            papers,
            limit=12,
            delay_seconds=0,
            mailto="researcher@example.edu",
            session=session,
        )

        self.assertEqual(stats["enriched"], 1)
        self.assertEqual(len(session.calls), 1)
        self.assertIn("doi:10.1000%2Fexample", session.calls[0][0])
        self.assertEqual(papers[0]["summary"], "Remote sensing detection")
        self.assertTrue(papers[0]["abstract_available"])
        self.assertEqual(papers[0]["abstract_source"], "OpenAlex")
        self.assertEqual(papers[1]["summary"], "Existing arXiv abstract.")


if __name__ == "__main__":
    unittest.main()
