#!/usr/bin/env python3
"""Enrich selected journal metadata records with available OpenAlex abstracts."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests


OPENALEX_WORKS_URL = "https://api.openalex.org/works/"
REQUEST_TIMEOUT_SECONDS = 20
DEFAULT_LIMIT = 12
DEFAULT_DELAY_SECONDS = 0.75


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Enrich selected Crossref records with OpenAlex abstracts when available."
    )
    parser.add_argument("--data", required=True, help="Selected literature JSONL file")
    parser.add_argument(
        "--limit",
        type=int,
        default=int(
            os.environ.get("JOURNAL_ABSTRACT_ENRICHMENT_LIMIT") or DEFAULT_LIMIT
        ),
        help="Maximum metadata-only journal records to query; zero disables enrichment.",
    )
    parser.add_argument(
        "--delay-seconds",
        type=float,
        default=float(
            os.environ.get("OPENALEX_REQUEST_DELAY_SECONDS") or DEFAULT_DELAY_SECONDS
        ),
        help="Delay between OpenAlex requests.",
    )
    return parser.parse_args()


def normalize_doi(value: object) -> str:
    """Normalize canonical DOI values from Crossref and OpenAlex."""
    doi = str(value or "").strip().casefold()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if doi.startswith(prefix):
            return doi[len(prefix) :]
    return doi


def reconstruct_openalex_abstract(inverted_index: object) -> str:
    """Rebuild OpenAlex's inverted-index representation without altering wording."""
    if not isinstance(inverted_index, dict):
        return ""

    positioned_words: list[tuple[int, str]] = []
    for word, positions in inverted_index.items():
        if not isinstance(word, str) or not isinstance(positions, list):
            continue
        for position in positions:
            if isinstance(position, int) and position >= 0:
                positioned_words.append((position, word))

    positioned_words.sort(key=lambda item: item[0])
    return " ".join(word for _, word in positioned_words).strip()


def fetch_openalex_abstract(
    session: requests.Session, doi: str, mailto: str
) -> tuple[str, str]:
    """Return an abstract and its OpenAlex work URL for an exact DOI match."""
    normalized_doi = normalize_doi(doi)
    if not normalized_doi:
        return "", ""

    endpoint = f"{OPENALEX_WORKS_URL}{quote(f'doi:{normalized_doi}', safe=':')}"
    params = {"mailto": mailto} if mailto else None
    response = session.get(endpoint, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
    response.raise_for_status()
    work = response.json()
    if normalize_doi(work.get("doi")) != normalized_doi:
        return "", ""

    abstract = reconstruct_openalex_abstract(work.get("abstract_inverted_index"))
    return abstract, str(work.get("id", ""))


def enrich_missing_abstracts(
    papers: list[dict[str, Any]],
    *,
    limit: int,
    delay_seconds: float,
    mailto: str,
    session: requests.Session | None = None,
) -> dict[str, int]:
    """Enrich only already-selected Crossref records and tolerate lookup failures."""
    candidates = [
        paper
        for paper in papers
        if paper.get("source") == "crossref"
        and not paper.get("abstract_available", False)
        and normalize_doi(paper.get("doi"))
    ]
    stats = {
        "eligible": len(candidates),
        "attempted": 0,
        "enriched": 0,
        "unavailable": 0,
        "failed": 0,
        "skipped_by_limit": max(len(candidates) - max(limit, 0), 0),
    }
    if limit <= 0:
        return stats

    client = session or requests.Session()
    client.headers.setdefault(
        "User-Agent", "daily-arxiv-ai-enhanced/1.0 (journal-abstract-enrichment)"
    )
    for index, paper in enumerate(candidates[:limit]):
        doi = normalize_doi(paper.get("doi"))
        stats["attempted"] += 1
        try:
            abstract, work_url = fetch_openalex_abstract(client, doi, mailto)
        except (requests.RequestException, ValueError) as exc:
            paper["abstract_enrichment_status"] = "lookup_failed"
            print(f"OpenAlex lookup failed for DOI {doi}: {exc}", file=sys.stderr)
            stats["failed"] += 1
        else:
            if abstract:
                paper["summary"] = abstract
                paper["abstract_available"] = True
                paper["abstract_source"] = "OpenAlex"
                paper["abstract_enrichment_status"] = "enriched"
                if work_url:
                    paper["abstract_source_url"] = work_url
                stats["enriched"] += 1
            else:
                paper["abstract_enrichment_status"] = "not_available"
                stats["unavailable"] += 1

        if index < len(candidates[:limit]) - 1 and delay_seconds > 0:
            time.sleep(delay_seconds)

    return stats


def main() -> int:
    args = parse_args()
    if args.limit < 0:
        raise ValueError("--limit must be zero or greater")
    if args.delay_seconds < 0:
        raise ValueError("--delay-seconds must be zero or greater")

    path = Path(args.data)
    with path.open("r", encoding="utf-8") as handle:
        papers = [json.loads(line) for line in handle if line.strip()]

    stats = enrich_missing_abstracts(
        papers,
        limit=args.limit,
        delay_seconds=args.delay_seconds,
        mailto=os.environ.get("OPENALEX_MAILTO", "").strip(),
    )
    with path.open("w", encoding="utf-8") as handle:
        for paper in papers:
            handle.write(json.dumps(paper, ensure_ascii=False) + "\n")

    print(
        "Journal abstract enrichment finished: "
        f"enriched={stats['enriched']}, unavailable={stats['unavailable']}, "
        f"failed={stats['failed']}, skipped_by_limit={stats['skipped_by_limit']}.",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
