#!/usr/bin/env python3
"""Collect recent arXiv records in bounded batches for the daily workflow."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import arxiv


DEFAULT_RESULTS_PER_CATEGORY = 80
DEFAULT_LOOKBACK_DAYS = 3


def configured_int(name: str, default: int, minimum: int = 1) -> int:
    value = os.environ.get(name, "").strip()
    if not value:
        return default
    try:
        return max(int(value), minimum)
    except ValueError:
        return default


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Collect bounded batches of recent arXiv metadata."
    )
    parser.add_argument("--output", required=True, help="Output JSONL path")
    parser.add_argument(
        "--categories",
        default=os.environ.get("CATEGORIES", "cs.CV"),
        help="Comma-separated arXiv categories",
    )
    parser.add_argument(
        "--lookback-days",
        type=int,
        default=configured_int("ARXIV_LOOKBACK_DAYS", DEFAULT_LOOKBACK_DAYS),
        help="Number of recent days to retain",
    )
    parser.add_argument(
        "--results-per-category",
        type=int,
        default=configured_int(
            "ARXIV_RESULTS_PER_CATEGORY", DEFAULT_RESULTS_PER_CATEGORY
        ),
        help="Maximum API results requested for each category",
    )
    return parser.parse_args()


def paper_from_result(result: arxiv.Result) -> dict[str, object]:
    identifier = result.entry_id.rsplit("/", 1)[-1]
    identifier = identifier.rsplit("v", 1)[0]
    return {
        "id": identifier,
        "source": "arxiv",
        "source_label": "arXiv preprint",
        "pdf": f"https://arxiv.org/pdf/{identifier}",
        "abs": f"https://arxiv.org/abs/{identifier}",
        "authors": [author.name for author in result.authors],
        "title": result.title,
        "categories": result.categories,
        "comment": result.comment,
        "summary": result.summary,
        "published_date": result.published.date().isoformat(),
    }


def main() -> int:
    args = parse_args()
    if args.lookback_days < 1:
        raise ValueError("--lookback-days must be at least 1")
    if args.results_per_category < 1:
        raise ValueError("--results-per-category must be at least 1")

    categories = sorted(
        {category.strip() for category in args.categories.split(",") if category.strip()}
    )
    cutoff = datetime.now(timezone.utc) - timedelta(days=args.lookback_days)
    client = arxiv.Client(
        page_size=min(args.results_per_category, 100),
        delay_seconds=1.0,
        num_retries=1,
    )
    papers_by_id: dict[str, dict[str, object]] = {}

    for category in categories:
        search = arxiv.Search(
            query=f"cat:{category}",
            max_results=args.results_per_category,
            sort_by=arxiv.SortCriterion.SubmittedDate,
            sort_order=arxiv.SortOrder.Descending,
        )
        count = 0
        try:
            for result in client.results(search):
                if result.published < cutoff:
                    break
                paper = paper_from_result(result)
                papers_by_id.setdefault(str(paper["id"]), paper)
                count += 1
        except Exception as exc:
            print(f"Skipping arXiv category {category} after API error: {exc}", file=sys.stderr)
        print(f"Collected {count} recent arXiv candidates from {category}", file=sys.stderr)

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as handle:
        for paper in sorted(
            papers_by_id.values(),
            key=lambda item: (str(item.get("published_date", "")), str(item["id"])),
            reverse=True,
        ):
            handle.write(json.dumps(paper, ensure_ascii=False) + "\n")

    print(
        f"arXiv collection finished: {len(papers_by_id)} unique candidates.",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
