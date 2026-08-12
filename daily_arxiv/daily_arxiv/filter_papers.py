#!/usr/bin/env python3
"""Filter and rank mixed arXiv and journal candidates using a research profile."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from daily_arxiv.relevance import enrich_and_filter, load_profile


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", required=True, help="Candidate JSONL path")
    parser.add_argument(
        "--profile-file",
        default=os.environ.get("RESEARCH_PROFILE_FILE", ""),
        help="Research profile JSON path",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    data_path = Path(args.data)
    profile = load_profile(args.profile_file or None)
    with data_path.open("r", encoding="utf-8") as handle:
        candidates = [json.loads(line) for line in handle if line.strip()]

    selected, stats = enrich_and_filter(candidates, profile)
    with data_path.open("w", encoding="utf-8") as handle:
        for paper in selected:
            handle.write(json.dumps(paper, ensure_ascii=False) + "\n")

    print(
        "Research-profile filtering finished: "
        f"{len(selected)}/{stats['candidates']} candidates kept; "
        f"minimum_score={stats['minimum_score']}.",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
