import json
import argparse
import os
from itertools import count

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=str, help="Path to the jsonline file")
    args = parser.parse_args()
    data = []
    preference = os.environ.get('CATEGORIES', 'cs.CV, cs.CL').split(',')
    preference = list(map(lambda x: x.strip(), preference))
    def rank(cate):
        if cate in preference:
            return preference.index(cate)
        else:
            return len(preference)

    with open(args.data, "r") as f:
        for line in f:
            data.append(json.loads(line))

    categories = set([item["categories"][0] for item in data])
    template = open("paper_template.md", "r").read()
    categories = sorted(categories, key=rank)
    cnt = {cate: 0 for cate in categories}
    for item in data:
        if item["categories"][0] not in cnt.keys():
            continue
        cnt[item["categories"][0]] += 1

    markdown = f"<div id=toc></div>\n\n# Table of Contents\n\n"
    for idx, cate in enumerate(categories):
        markdown += f"- [{cate}](#{cate}) [Total: {cnt[cate]}]\n"

    idx = count(1)
    for cate in categories:
        markdown += f"\n\n<div id='{cate}'></div>\n\n"
        markdown += f"# {cate} [[Back]](#toc)\n\n"
        papers = []
        for item in data:
            if item["categories"][0] == cate:
                # Safely access AI fields with default values
                ai_data = item.get('AI', {})
                if not ai_data or not isinstance(ai_data, dict):
                    print(f"Skipping item '{item.get('title', 'Unknown')}' due to missing or invalid AI data")
                    continue
                
                # Check if all required AI fields are present
                required_fields = [
                    'tldr',
                    'research_relevance',
                    'task_and_scene',
                    'model_architecture',
                    'lightweight_method',
                    'onboard_deployability',
                    'datasets_and_metrics',
                    'experiments',
                    'limitations',
                    'ideas_for_my_research',
                    'reading_priority'
                ]
                if not all(field in ai_data for field in required_fields):
                    print(f"Skipping item '{item.get('title', 'Unknown')}' due to incomplete AI fields")
                    continue
                
                papers.append(
                    template.format(
                        title=item["title"],
                        authors=",".join(item["authors"]),
                        summary=item["summary"],
                        url=item['abs'],
                        tldr=ai_data.get('tldr', ''),
                        motivation=ai_data.get('motivation', ''),
                        method=ai_data.get('method', ''),
                        result=ai_data.get('result', ''),
                        conclusion=ai_data.get('conclusion', ''),
                        cate=item['categories'][0],
                        research_relevance=ai_data.get('research_relevance', ''),
                        task_and_scene=ai_data.get('task_and_scene', ''),
                        model_architecture=ai_data.get('model_architecture', ''),
                        lightweight_method=ai_data.get('lightweight_method', ''),
                        onboard_deployability=ai_data.get('onboard_deployability', ''),
                        datasets_and_metrics=ai_data.get('datasets_and_metrics', ''),
                        experiments=ai_data.get('experiments', ''),
                        limitations=ai_data.get('limitations', ''),
                        ideas_for_my_research=ai_data.get('ideas_for_my_research', ''),
                        reading_priority=ai_data.get('reading_priority', ''),
                        idx=next(idx)
                    )
                )
        markdown += "\n\n".join(papers)
    with open(args.data.split('_')[0] + '.md', "w") as f:
        f.write(markdown)
