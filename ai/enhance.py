import os
import json
import sys
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict
from queue import Queue
from threading import Lock
# INSERT_YOUR_CODE
import requests

import dotenv
import argparse
from tqdm import tqdm

import langchain_core.exceptions
from langchain_openai import ChatOpenAI
from langchain.prompts import (
    ChatPromptTemplate,
    SystemMessagePromptTemplate,
    HumanMessagePromptTemplate,
)
from structure import Structure

if os.path.exists('.env'):
    dotenv.load_dotenv()
template = open("template.txt", "r").read()
system = open("system.txt", "r").read()

def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=str, required=True, help="jsonline data file")
    parser.add_argument(
        "--max_workers",
        type=int,
        default=int(os.environ.get("MAX_AI_WORKERS") or "1"),
        help="Maximum number of parallel workers",
    )
    return parser.parse_args()

def process_single_item(chain, item: Dict, language: str) -> Dict:
    sensitive_check_enabled = os.environ.get(
        "ENABLE_SENSITIVE_CHECK", "false"
    ).casefold() in {"1", "true", "yes"}

    def metadata_only_ai_fields() -> Dict:
        title = item.get("title", "This journal record")
        journal = item.get("journal", "the configured journal")
        unavailable = "Crossref metadata does not provide an abstract."
        if language.casefold().startswith("chinese"):
            unavailable = "Crossref 元数据未提供摘要，无法据此确认技术细节。"
            return {
                "tldr": f"《{title}》是来自《{journal}》的期刊元数据记录，尚未获得可分析的摘要。",
                "research_relevance": "题名匹配当前研究画像；请先在 DOI 或出版社页面核验其与遥感目标检测、轻量化或星上部署的实际关系。",
                "task_and_scene": unavailable,
                "model_architecture": unavailable,
                "lightweight_method": unavailable,
                "onboard_deployability": unavailable,
                "datasets_and_metrics": unavailable,
                "experiments": unavailable,
                "limitations": "没有摘要或全文时，不能把该记录作为技术结论的依据。",
                "ideas_for_my_research": "打开 DOI/出版社页面获取摘要，再决定是否加入全文精读队列。",
                "reading_priority": "3/5：仅题名层面匹配，必须先核验摘要。",
            }
        return {
            "tldr": f"{title} is a metadata-only record from {journal}.",
            "research_relevance": "The title matched the configured research profile; verify relevance from the DOI or publisher page.",
            "task_and_scene": unavailable,
            "model_architecture": unavailable,
            "lightweight_method": unavailable,
            "onboard_deployability": unavailable,
            "datasets_and_metrics": unavailable,
            "experiments": unavailable,
            "limitations": "Do not treat this record as evidence until the paper abstract or full text is read.",
            "ideas_for_my_research": "Open the DOI/publisher page and decide whether to add the paper to the full-text reading queue.",
            "reading_priority": "3/5: title-level match only; abstract verification required.",
        }

    def is_sensitive(content: str) -> bool:
        """
        调用 spam.dw-dengwei.workers.dev 接口检测内容是否包含敏感词。
        返回 True 表示触发敏感词，False 表示未触发。
        """
        try:
            resp = requests.post(
                "https://spam.dw-dengwei.workers.dev",
                json={"text": content},
                timeout=5
            )
            if resp.status_code == 200:
                result = resp.json()
                # 约定接口返回 {"sensitive": true/false, ...}
                return result.get("sensitive", False)
            else:
                # A service outage must not silently discard a research paper.
                print(f"Sensitive check failed with status {resp.status_code}", file=sys.stderr)
                return False
        except Exception as e:
            print(f"Sensitive check error: {e}", file=sys.stderr)
            return False

    def build_source_content() -> str:
        categories = item.get("categories", [])
        category_text = ", ".join(categories) if isinstance(categories, list) else str(categories)
        relevance_matches = item.get("relevance_matches", [])
        match_text = "; ".join(relevance_matches) if isinstance(relevance_matches, list) else str(relevance_matches)
        metadata = [
            f"Title: {item.get('title', '')}",
            f"Source: {item.get('source_label', item.get('source', ''))}",
            f"Journal: {item.get('journal', '')}",
            f"Abstract provenance: {item.get('abstract_source', '')}",
            f"Categories: {category_text}",
            f"Deterministic relevance score: {item.get('relevance_score', '')}",
            f"Matched research-profile terms: {match_text}",
            "Abstract:",
            item.get("summary", ""),
        ]
        return "\n".join(line for line in metadata if line is not None)

    def check_github_code(content: str) -> Dict:
        """提取并验证 GitHub 链接"""
        code_info = {}

        # 1. 优先匹配 github.com/owner/repo 格式
        github_pattern = r"https?://github\.com/([a-zA-Z0-9-_]+)/([a-zA-Z0-9-_\.]+)"
        match = re.search(github_pattern, content)
        
        if match:
            owner, repo = match.groups()
            # 清理 repo 名称，去掉可能的 .git 后缀或末尾的标点
            repo = repo.rstrip(".git").rstrip(".,)")
            
            full_url = f"https://github.com/{owner}/{repo}"
            code_info["code_url"] = full_url
            
            # 尝试调用 GitHub API 获取信息
            github_token = os.environ.get("TOKEN_GITHUB")
            headers = {"Accept": "application/vnd.github.v3+json"}
            if github_token:
                headers["Authorization"] = f"token {github_token}"
            
            try:
                api_url = f"https://api.github.com/repos/{owner}/{repo}"
                resp = requests.get(api_url, headers=headers, timeout=5)
                if resp.status_code == 200:
                    data = resp.json()
                    code_info["code_stars"] = data.get("stargazers_count", 0)
                    code_info["code_last_update"] = data.get("pushed_at", "")[:10]
            except Exception:
                # API 调用失败不影响主流程
                pass
            return code_info

        # 2. 如果没有 github.com，尝试匹配 github.io
        github_io_pattern = r"https?://[a-zA-Z0-9-_]+\.github\.io(?:/[a-zA-Z0-9-_\.]+)*"
        match_io = re.search(github_io_pattern, content)
        
        if match_io:
            url = match_io.group(0)
            # 清理末尾标点
            url = url.rstrip(".,)")
            code_info["code_url"] = url
            # github.io 不进行 star 和 update 判断
                
        return code_info

    # 检查 summary 字段
    if item.get("source") == "crossref" and not item.get("abstract_available", False):
        item["AI"] = metadata_only_ai_fields()
        return item

    if sensitive_check_enabled and is_sensitive(item.get("summary", "")):
        return None

    # 检测代码可用性
    code_info = check_github_code(item.get("summary", ""))
    if code_info:
        item.update(code_info)

    """处理单个数据项"""
    # Default structure with meaningful fallback values
    default_ai_fields = {
        "tldr": "Summary generation failed",
        "research_relevance": "Relevance analysis unavailable",
        "task_and_scene": "Task and scene extraction unavailable",
        "model_architecture": "Model architecture extraction unavailable",
        "lightweight_method": "Lightweight method extraction unavailable",
        "onboard_deployability": "Onboard deployability analysis unavailable",
        "datasets_and_metrics": "Datasets and metrics extraction unavailable",
        "experiments": "Experimental analysis unavailable",
        "limitations": "Limitations analysis unavailable",
        "ideas_for_my_research": "Research ideas unavailable",
        "reading_priority": "Priority unavailable",
    }
    
    try:
        response: Structure = chain.invoke({
            "language": language,
            "content": build_source_content(),
        })
        item['AI'] = response.model_dump()
    except langchain_core.exceptions.OutputParserException as e:
        # 尝试从错误信息中提取 JSON 字符串并修复
        error_msg = str(e)
        partial_data = {}
        
        if "Function Structure arguments:" in error_msg:
            try:
                # 提取 JSON 字符串
                json_str = error_msg.split("Function Structure arguments:", 1)[1].strip().split('are not valid JSON')[0].strip()
                # 预处理 LaTeX 数学符号 - 使用四个反斜杠来确保正确转义
                json_str = json_str.replace('\\', '\\\\')
                # 尝试解析修复后的 JSON
                partial_data = json.loads(json_str)
            except Exception as json_e:
                print(f"Failed to parse JSON for {item.get('id', 'unknown')}: {json_e}", file=sys.stderr)
        
        # Merge partial data with defaults to ensure all fields exist
        item['AI'] = {**default_ai_fields, **partial_data}
        print(f"Using partial AI data for {item.get('id', 'unknown')}: {list(partial_data.keys())}", file=sys.stderr)
    except Exception as e:
        # Catch any other exceptions and provide default values
        print(f"Unexpected error for {item.get('id', 'unknown')}: {e}", file=sys.stderr)
        item['AI'] = default_ai_fields
    
    # Final validation to ensure all required fields exist
    for field in default_ai_fields.keys():
        if field not in item['AI']:
            item['AI'][field] = default_ai_fields[field]

    if sensitive_check_enabled:
        for value in item.get("AI", {}).values():
            if is_sensitive(str(value)):
                return None

    return item

def process_all_items(data: List[Dict], model_name: str, language: str, max_workers: int) -> List[Dict]:
    """并行处理所有数据项"""
    llm = ChatOpenAI(
        model=model_name,
        temperature=0.2,
        max_tokens=int(os.environ.get("MAX_SUMMARY_TOKENS") or "1800"),
        model_kwargs={"extra_body": {"thinking": {"type": "disabled"}}},
    ).with_structured_output(Structure, method="function_calling")

    print('Connect to:', model_name, file=sys.stderr)
    
    prompt_template = ChatPromptTemplate.from_messages([
        SystemMessagePromptTemplate.from_template(system),
        HumanMessagePromptTemplate.from_template(template=template)
    ])

    chain = prompt_template | llm
    
    # 使用线程池并行处理
    processed_data = [None] * len(data)  # 预分配结果列表
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # 提交所有任务
        future_to_idx = {
            executor.submit(process_single_item, chain, item, language): idx
            for idx, item in enumerate(data)
        }
        
        # 使用tqdm显示进度
        for future in tqdm(
            as_completed(future_to_idx),
            total=len(data),
            desc="Processing items"
        ):
            idx = future_to_idx[future]
            try:
                result = future.result()
                processed_data[idx] = result
            except Exception as e:
                print(f"Item at index {idx} generated an exception: {e}", file=sys.stderr)
                # Add default AI fields to ensure consistency
                processed_data[idx] = data[idx]
                processed_data[idx]['AI'] = {
                    "tldr": "Processing failed",
                    "research_relevance": "Processing failed",
                    "task_and_scene": "Processing failed",
                    "model_architecture": "Processing failed",
                    "lightweight_method": "Processing failed",
                    "onboard_deployability": "Processing failed",
                    "datasets_and_metrics": "Processing failed",
                    "experiments": "Processing failed",
                    "limitations": "Processing failed",
                    "ideas_for_my_research": "Processing failed",
                    "reading_priority": "Processing failed",
                }
    
    return processed_data

def main():
    args = parse_args()
    model_name = os.environ.get("MODEL_NAME") or "deepseek-chat"
    language = os.environ.get("LANGUAGE") or "Chinese"

    # 检查并删除目标文件
    target_file = args.data.replace('.jsonl', f'_AI_enhanced_{language}.jsonl')
    if os.path.exists(target_file):
        os.remove(target_file)
        print(f'Removed existing file: {target_file}', file=sys.stderr)

    # 读取数据
    data = []
    with open(args.data, "r") as f:
        for line in f:
            data.append(json.loads(line))

    # 去重
    seen_ids = set()
    unique_data = []
    for item in data:
        if item['id'] not in seen_ids:
            seen_ids.add(item['id'])
            unique_data.append(item)

    data = unique_data
    print('Open:', args.data, file=sys.stderr)
    
    # 并行处理所有数据
    processed_data = process_all_items(
        data,
        model_name,
        language,
        args.max_workers
    )
    
    # 保存结果
    with open(target_file, "w") as f:
        for item in processed_data:
            if item is not None:
                f.write(json.dumps(item) + "\n")

if __name__ == "__main__":
    main()
