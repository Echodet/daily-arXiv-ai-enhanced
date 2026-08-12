import argparse
import json
import os
from itertools import count


REQUIRED_AI_FIELDS = [
    "tldr",
    "research_relevance",
    "task_and_scene",
    "model_architecture",
    "lightweight_method",
    "onboard_deployability",
    "datasets_and_metrics",
    "experiments",
    "limitations",
    "ideas_for_my_research",
    "reading_priority",
]


def category_rank(category: str, preferences: list[str]) -> int:
    if category in preferences:
        return preferences.index(category)
    return len(preferences)


def journal_line(item: dict) -> str:
    journal = item.get("journal", "")
    tier = item.get("journal_tier", "")
    if not journal:
        return ""
    tier_label = f" ({tier} tier)" if tier else ""
    return f"; journal: {journal}{tier_label}"


def abstract_source_line(item: dict) -> str:
    source = item.get("abstract_source", "")
    if not source:
        return ""
    return f"; abstract: {source}"


def format_authors(authors: object) -> str:
    if isinstance(authors, list):
        return ",".join(str(author) for author in authors)
    return str(authors or "")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=str, required=True, help="Path to the JSONL file")
    args = parser.parse_args()

    with open(args.data, "r", encoding="utf-8") as handle:
        data = [json.loads(line) for line in handle if line.strip()]

    preferences = [
        value.strip()
        for value in os.environ.get("CATEGORIES", "cs.CV,cs.CL").split(",")
        if value.strip()
    ]
    categories = sorted(
        {item["categories"][0] for item in data if item.get("categories")},
        key=lambda category: category_rank(category, preferences),
    )
    template = open("paper_template.md", "r", encoding="utf-8").read()
    counts = {category: 0 for category in categories}
    for item in data:
        if item.get("categories") and item["categories"][0] in counts:
            counts[item["categories"][0]] += 1

    markdown = "<div id=toc></div>\n\n# Table of Contents\n\n"
    for category in categories:
        markdown += f"- [{category}](#{category}) [Total: {counts[category]}]\n"

    index = count(1)
    for category in categories:
        markdown += f"\n\n<div id='{category}'></div>\n\n"
        markdown += f"# {category} [[Back]](#toc)\n\n"
        papers = []
        for item in data:
            if not item.get("categories") or item["categories"][0] != category:
                continue
            ai_data = item.get("AI", {})
            if not isinstance(ai_data, dict) or not all(
                field in ai_data for field in REQUIRED_AI_FIELDS
            ):
                print(
                    f"Skipping '{item.get('title', 'Unknown')}' because AI fields are incomplete"
                )
                continue
            papers.append(
                template.format(
                    title=item.get("title", "Untitled"),
                    authors=format_authors(item.get("authors", [])),
                    summary=item.get("summary", ""),
                    url=item.get("abs") or item.get("pdf", ""),
                    source=item.get("source_label", item.get("source", "Unknown")),
                    journal_line=journal_line(item),
                    abstract_source_line=abstract_source_line(item),
                    relevance_score=item.get("relevance_score", "N/A"),
                    cate=item["categories"][0],
                    idx=next(index),
                    **{field: ai_data.get(field, "") for field in REQUIRED_AI_FIELDS},
                )
            )
        markdown += "\n\n".join(papers)

    output_path = args.data.split("_AI_enhanced_")[0] + ".md"
    with open(output_path, "w", encoding="utf-8") as handle:
        handle.write(markdown)


if __name__ == "__main__":
    main()
