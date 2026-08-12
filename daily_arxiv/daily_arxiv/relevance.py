"""Deterministic relevance scoring for a focused literature feed."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


DEFAULT_PROFILE_PATH = Path(__file__).resolve().parents[1] / "research_profile.json"


def load_profile(profile_path: str | None = None) -> dict[str, Any]:
    """Load a research profile without requiring a YAML dependency."""
    path = Path(profile_path) if profile_path else DEFAULT_PROFILE_PATH
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def normalize_text(paper: dict[str, Any]) -> str:
    """Build the field set used for deterministic matching."""
    fields = [
        paper.get("title", ""),
        paper.get("summary", ""),
        paper.get("journal", ""),
    ]
    return " ".join(str(field) for field in fields if field).casefold()


def normalize_title(paper: dict[str, Any]) -> str:
    """Return the title alone for main-task relevance checks."""
    return str(paper.get("title", "")).casefold()


def _contains_term(text: str, term: str) -> bool:
    normalized_term = term.casefold().strip()
    if not normalized_term:
        return False
    if re.fullmatch(r"[a-z0-9]+", normalized_term):
        return bool(re.search(rf"\b{re.escape(normalized_term)}\b", text))
    return normalized_term in text


def score_paper(paper: dict[str, Any], profile: dict[str, Any]) -> tuple[int, list[str]]:
    """Return a reproducible relevance score and the matching evidence."""
    text = normalize_text(paper)
    score = 0
    matches: list[str] = []

    for group_name, group in profile.get("keyword_groups", {}).items():
        group_matches = [
            term for term in group.get("terms", []) if _contains_term(text, term)
        ]
        if group_matches:
            score += int(group.get("weight", 1))
            matches.append(f"{group_name}: {', '.join(group_matches[:3])}")

    negative_matches = [
        term for term in profile.get("negative_terms", []) if _contains_term(text, term)
    ]
    if negative_matches:
        penalty = int(profile.get("negative_term_penalty", 0))
        score -= penalty
        matches.append(f"negative: {', '.join(negative_matches[:3])}")

    return score, matches


def _required_group_matches(
    text: str, profile: dict[str, Any], requirement_key: str
) -> list[str] | None:
    """Return evidence for every configured requirement, or ``None`` on failure."""
    keyword_groups = profile.get("keyword_groups", {})
    requirement_matches: list[str] = []

    for alternatives in profile.get(requirement_key, []):
        matched_alternatives: list[str] = []
        for group_name in alternatives:
            group = keyword_groups.get(group_name, {})
            terms = [
                term for term in group.get("terms", []) if _contains_term(text, term)
            ]
            if terms:
                matched_alternatives.append(f"{group_name}: {', '.join(terms[:3])}")
        if not matched_alternatives:
            return None
        requirement_matches.append("; ".join(matched_alternatives))

    return requirement_matches


def meets_required_groups(paper: dict[str, Any], profile: dict[str, Any]) -> bool:
    """Require remote-sensing and detection evidence across the record fields."""
    return _required_group_matches(normalize_text(paper), profile, "require_groups") is not None


def title_focus_matches(paper: dict[str, Any], profile: dict[str, Any]) -> list[str] | None:
    """Require task evidence in the title, not only a background mention in an abstract."""
    return _required_group_matches(
        normalize_title(paper), profile, "title_require_groups"
    )


def enrich_and_filter(
    papers: list[dict[str, Any]], profile: dict[str, Any]
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Annotate papers, retain relevant work, deduplicate, and impose a daily cap."""
    selected: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    minimum_score = int(profile.get("minimum_score", 0))

    for paper in papers:
        identifier = str(paper.get("id", "")).strip()
        if not identifier or identifier in seen_ids:
            continue
        seen_ids.add(identifier)

        score, matches = score_paper(paper, profile)
        paper["relevance_score"] = score
        paper["relevance_matches"] = matches
        paper["research_profile"] = profile.get("profile_name", "custom")
        title_matches = title_focus_matches(paper, profile)
        if title_matches:
            paper["title_relevance_matches"] = title_matches

        if (
            score >= minimum_score
            and meets_required_groups(paper, profile)
            and title_matches is not None
        ):
            selected.append(paper)

    selected.sort(
        key=lambda item: (
            -int(item.get("relevance_score", 0)),
            item.get("source", ""),
            item.get("title", ""),
        )
    )
    limit = int(profile.get("maximum_papers_per_day", 0))
    if limit > 0:
        selected = selected[:limit]

    return selected, {
        "candidates": len(papers),
        "selected": len(selected),
        "minimum_score": minimum_score,
    }
