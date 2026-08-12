#!/usr/bin/env python3
"""Collect recent metadata for selected journals through Crossref."""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import requests

from daily_arxiv.relevance import enrich_and_filter, load_profile


BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_SOURCES_PATH = BASE_DIR / "journal_sources.json"
REQUEST_TIMEOUT_SECONDS = 30


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Collect focused journal metadata from Crossref."
    )
    parser.add_argument("--output", required=True, help="Output JSONL path")
    parser.add_argument(
        "--sources-file",
        default=str(DEFAULT_SOURCES_PATH),
        help="Journal source configuration JSON path",
    )
    parser.add_argument(
        "--profile-file",
        default=os.environ.get("RESEARCH_PROFILE_FILE", ""),
        help="Research profile JSON path",
    )
    parser.add_argument(
        "--lookback-days",
        type=int,
        default=int(os.environ.get("JOURNAL_LOOKBACK_DAYS") or "14"),
        help="Number of Crossref index days to fetch",
    )
    parser.add_argument(
        "--rows-per-journal",
        type=int,
        default=int(os.environ.get("JOURNAL_ROWS_PER_SOURCE") or "25"),
        help="Maximum Crossref records to request per journal",
    )
    return parser.parse_args()


def clean_html(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value or "")
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


def authors_from_crossref(item: dict[str, Any]) -> list[str]:
    authors = []
    for author in item.get("author", []):
        name = " ".join(
            part for part in [author.get("given", ""), author.get("family", "")] if part
        ).strip()
        if name:
            authors.append(name)
    return authors or ["Authors unavailable in Crossref metadata"]


def published_date(item: dict[str, Any]) -> str:
    for key in ("published-online", "published-print", "published", "issued"):
        parts = item.get(key, {}).get("date-parts", [[]])
        if parts and parts[0]:
            values = parts[0]
            year = int(values[0])
            month = int(values[1]) if len(values) > 1 else 1
            day = int(values[2]) if len(values) > 2 else 1
            return f"{year:04d}-{month:02d}-{day:02d}"
    return ""


def canonical_url(item: dict[str, Any]) -> str:
    resource = item.get("resource", {}).get("primary", {}).get("URL")
    if resource:
        return resource
    doi = item.get("DOI", "")
    return f"https://doi.org/{doi}" if doi else ""


def crossref_item_to_paper(item: dict[str, Any], journal: dict[str, Any]) -> dict[str, Any]:
    doi = item.get("DOI", "").strip()
    title = clean_html(" ".join(item.get("title", [])))
    abstract = clean_html(item.get("abstract", ""))
    journal_title = clean_html(" ".join(item.get("container-title", []))) or journal["title"]
    abstract_text = abstract or "Abstract unavailable in Crossref metadata. Open the DOI page for the publisher abstract or full text."
    return {
        "id": f"doi:{doi.lower()}" if doi else f"crossref:{journal['issn']}:{title.casefold()}",
        "source": "crossref",
        "source_label": "Journal",
        "journal": journal_title,
        "journal_tier": journal.get("tier", ""),
        "issn": journal["issn"],
        "doi": doi,
        "title": title or "Untitled Crossref record",
        "authors": authors_from_crossref(item),
        "categories": [f"Journal: {journal_title}"],
        "summary": abstract_text,
        "abstract_available": bool(abstract),
        "abstract_source": "Crossref" if abstract else "Unavailable",
        "abs": canonical_url(item),
        "pdf": "",
        "published_date": published_date(item),
        "metadata_date": item.get("indexed", {}).get("date-time", ""),
    }


def fetch_journal_items(
    session: requests.Session,
    journal: dict[str, Any],
    from_date: date,
    until_date: date,
    rows: int,
) -> list[dict[str, Any]]:
    endpoint = f"https://api.crossref.org/journals/{journal['issn']}/works"
    params = {
        "filter": ",".join(
            [
                f"from-index-date:{from_date.isoformat()}",
                f"until-index-date:{until_date.isoformat()}",
                "type:journal-article",
            ]
        ),
        "rows": min(max(rows, 1), 1000),
        "sort": "indexed",
        "order": "desc",
        "select": "DOI,title,abstract,container-title,published,published-online,published-print,issued,author,resource,indexed",
    }
    response = session.get(endpoint, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
    response.raise_for_status()
    message = response.json().get("message", {})
    return [crossref_item_to_paper(item, journal) for item in message.get("items", [])]


def load_journals(sources_path: str) -> list[dict[str, Any]]:
    with Path(sources_path).open("r", encoding="utf-8") as handle:
        config = json.load(handle)
    return [
        journal
        for journal in config.get("journals", [])
        if journal.get("enabled") and journal.get("issn")
    ]


def resolve_collection_date() -> date:
    """Prefer the workflow's UTC date so every stage handles the same daily file."""
    configured_date = os.environ.get("CRAWL_DATE", "").strip()
    if not configured_date:
        return date.today()
    try:
        return datetime.strptime(configured_date, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError("CRAWL_DATE must use YYYY-MM-DD format") from exc


def main() -> int:
    args = parse_args()
    if args.lookback_days < 1:
        raise ValueError("--lookback-days must be at least 1")
    profile = load_profile(args.profile_file or None)
    journals = load_journals(args.sources_file)
    today = resolve_collection_date()
    from_date = today - timedelta(days=args.lookback_days - 1)
    session = requests.Session()
    contact = os.environ.get("CROSSREF_MAILTO", "")
    session.headers["User-Agent"] = (
        f"daily-arxiv-ai-enhanced/1.0 (mailto:{contact})"
        if contact
        else "daily-arxiv-ai-enhanced/1.0 (research-literature-monitor)"
    )

    candidates: list[dict[str, Any]] = []
    for journal in journals:
        try:
            journal_items = fetch_journal_items(
                session, journal, from_date, today, args.rows_per_journal
            )
            candidates.extend(journal_items)
            print(
                f"Collected {len(journal_items)} candidates from {journal['title']}",
                file=sys.stderr,
            )
        except requests.RequestException as exc:
            print(
                f"Skipping {journal['title']} because Crossref request failed: {exc}",
                file=sys.stderr,
            )

    selected, stats = enrich_and_filter(candidates, profile)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("a", encoding="utf-8") as handle:
        for paper in selected:
            handle.write(json.dumps(paper, ensure_ascii=False) + "\n")

    print(
        "Journal collection finished: "
        f"{len(selected)}/{stats['candidates']} candidates met the profile threshold "
        f"({stats['minimum_score']}).",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
