"""QA pair retrieval tool for textbook chapter outline."""

import re
import json
from typing import Dict, Any, Optional, List, Union

from src.tools.qa_retrieve.pipeline import retrieve_and_check_qa
from src.utils import sanitize_filename
from src.models import gpt_completion


def extract_keywords_from_outline(
    subchapter_title: str,
    topics: List[str],
    max_keywords: int = 10
) -> List[str]:
    """Extract keywords from subchapter title and topics.

    Args:
        subchapter_title: Subchapter title
        topics: List of topics related to the subchapter
        max_keywords: Maximum number of keywords to extract

    Returns:
        List of keywords
    """
    keywords = []

    # Add subchapter title as a keyword
    if subchapter_title:
        # Remove any parenthetical content for cleaner keywords
        clean_title = re.sub(r'[（(].*?[)）]', '', subchapter_title).strip()
        if clean_title:
            keywords.append(clean_title)

    # Process topics to extract individual keywords
    for topic in topics:
        if not topic:
            continue

        # Split by common Chinese/English separators
        segments = re.split(r'[,，;；、与和及及以及orOR]', topic)
        for segment in segments:
            segment = segment.strip()
            # Only add meaningful keywords (length >= 2)
            if segment and len(segment) >= 2 and segment not in keywords:
                keywords.append(segment)

    # Limit the number of keywords
    return keywords[:max_keywords]

async def extract_keywords_from_online(
    subchapter_title: str,
    topics: List[str],
    max_keywords: int = 10
) -> List[str]:
    words = subchapter_title + " " + " ".join(topics)
    prompt = f"""
    你是一个专业的教材内容索引专家。请从以下文本中提取用于精准检索的关键词：
    "{words}"

    【严格提取规则】
    1. **数量限制**：最多提取 {max_keywords} 个关键词。
    2. **格式要求**：仅返回一个标准的 JSON 列表，例如 ["词1", "词2"]，严禁包含 Markdown 标记或解释。
    3. **三重过滤机制（必须严格执行）**：
    - ❌ **第一重：剔除结构性词汇**
        禁止提取：定义、概念、内涵、背景、历程、概述、总结、引言、结论、展望、演进、历史。
    - ❌ **第二重：剔除宽泛方法论**
        禁止提取：理性设计、经验试错、计算机辅助药物设计、传统方法、现代方法、CADD、药物设计本身（如果是主题词）。
    - ❌ **第三重：剔除通用评价维度/抽象属性**
        禁止提取：有效性、安全性、可及性、经济性、可行性、必要性、重要性、优势、劣势、挑战、机遇、风险、质量、效率。
        *理由：这些是所有项目共有的属性，无法用于定位具体内容。*
    4. **正面标准（只保留高信息量实体）**：
    - ✅ **具体技术/算法**：如 "分子对接"、"自由能微扰"、"QSAR"、"高通量筛选"。
    - ✅ **具体对象/实体**：如 "先导化合物"、"靶点蛋白"、"激酶抑制剂"、"G 蛋白偶联受体"。
    - ✅ **具体属性指标**：如 "IC50 值"、"结合常数"、"血脑屏障透过率"、"代谢半衰期" (必须是具体指标名，而非"有效性")。
    - ✅ **细分流程步骤**：如 "苗头化合物发现"、"先导化合物优化"、"临床前研究"。
    5. **宁缺毋滥原则**：
    - 如果文中只包含上述被禁止的抽象词，没有具体技术或实体，**允许返回空列表 [] 或仅返回文中出现的具体名词**。
    - 绝不要为了凑数而提取抽象词。

    【示例演示】
    输入："药物研发需综合评估其有效性、安全性和可及性。虽然理性设计能提高成功率，但仍面临挑战。具体技术如分子对接可用于优化结合能。"
    ❌ 错误输出：["有效性", "安全性", "可及性", "理性设计", "挑战", "分子对接"]
    ✅ 正确输出：["分子对接", "结合能"] 
    *(解释：剔除了通用属性、宽泛方法和抽象名词，只保留了具体技术)*

    以json列表形式返回: \n[keyword1, ...]
    """
    response = await gpt_completion(prompt=prompt)

    def _normalize_keywords(raw: Any) -> List[str]:
        if isinstance(raw, dict):
            # 兼容 {"keywords":[...]} 这类返回
            if isinstance(raw.get("keywords"), list):
                raw = raw.get("keywords")
            else:
                raw = []
        if not isinstance(raw, list):
            raw = []
        normalized: List[str] = []
        for item in raw:
            text = str(item).strip()
            if text and text not in normalized:
                normalized.append(text)
        return normalized[:max_keywords]

    json_candidates: List[str] = []
    # 1) ```json ... ```
    match_json_fence = re.search(r"```json\s*([\s\S]*?)\s*```", response, re.IGNORECASE)
    if match_json_fence:
        json_candidates.append(match_json_fence.group(1).strip())
    # 2) ``` ... ```
    match_any_fence = re.search(r"```\s*([\s\S]*?)\s*```", response)
    if match_any_fence:
        json_candidates.append(match_any_fence.group(1).strip())
    # 3) 裸数组片段
    match_array = re.search(r"\[[\s\S]*\]", response)
    if match_array:
        json_candidates.append(match_array.group(0).strip())
    # 4) 整体文本直接尝试
    json_candidates.append(response.strip())

    for candidate in json_candidates:
        if not candidate:
            continue
        try:
            parsed = json.loads(candidate)
            keywords = _normalize_keywords(parsed)
            if keywords:
                return keywords
        except Exception:
            continue

    # 兜底：解析失败时退回到本地规则提取，避免中断 QA 检索流程
    return extract_keywords_from_outline(subchapter_title, topics, max_keywords=max_keywords)
    
    
async def search_qa_pairs_for_subchapter(
    subchapter_title: str,
    topics: List[str],
    max_keywords: int = 10,
    max_results_per_keyword: int = 1
) -> Dict[str, Any]:
    """Search QA pairs for a subchapter using extracted keywords.

    Args:
        subchapter_title: Subchapter title
        topics: List of topics related to the subchapter
        max_keywords: Maximum number of keywords to search
        max_results_per_keyword: Maximum QA pairs to retrieve per keyword

    Returns:
        Dictionary containing:
            - qa_pairs: List of QA pairs found
            - keywords: List of keywords used for search
            - summary: Summary of search results
    """
    # Extract keywords from online
    keywords = await extract_keywords_from_online(subchapter_title, topics, max_keywords)

    if not keywords:
        print(f"  [QA] No keywords extracted for '{subchapter_title}'")
        return {
            "qa_pairs": [],
            "keywords": [],
            "summary": {
                "total_keywords_searched": 0,
                "total_qa_pairs_found": 0
            }
        }

    print(f"  [QA] Keywords ({len(keywords)}): {keywords}")

    # Search QA pairs for each keyword
    all_qa_pairs = []
    search_results = []
    failed_keywords = []

    for keyword in keywords:
        try:
            result = await retrieve_and_check_qa(
                keyword=keyword,
                num_variations=3,
                max_results_per_keyword=max_results_per_keyword
            )

            qa_pairs = result.get("results", [])
            if qa_pairs:
                # Add keyword information to each QA pair
                for qa in qa_pairs:
                    qa["search_keyword"] = keyword
                    qa["keyword_variations"] = result.get("variations", [])

                all_qa_pairs.extend(qa_pairs)
                search_results.append({
                    "keyword": keyword,
                    "variations": result.get("variations", []),
                    "found": len(qa_pairs)
                })
                # print(f"  [QA] '{keyword}': Found {len(qa_pairs)} QA pair(s)")
            else:
                failed_keywords.append(keyword)
                search_results.append({
                    "keyword": keyword,
                    "variations": result.get("variations", []),
                    "found": 0
                })
        except Exception as e:
            failed_keywords.append(keyword)
            print(f"  [QA] '{keyword}': Error - {e}")
            search_results.append({
                "keyword": keyword,
                "error": str(e),
                "found": 0
            })

    # Print summary
    if failed_keywords:
        print(f"  [QA] Summary: {len(all_qa_pairs)} QA pairs found, {len(failed_keywords)} keywords failed")
    else:
        print(f"  [QA] Summary: {len(all_qa_pairs)} QA pairs found")

    return {
        "qa_pairs": all_qa_pairs,
        "keywords": keywords,
        "search_results": search_results,
        "summary": {
            "total_keywords_searched": len(keywords),
            "total_qa_pairs_found": len(all_qa_pairs)
        }
    }


async def get_qa_pair_for_subchapter(
    subchapter_title: str,
    topics: List[str],
    num_variations: int = 5,
    max_results: int = 1
) -> Union[List[Dict], tuple]:
    """Get QA pairs for a subchapter (matching get_wiki_article signature).

    Args:
        subchapter_title: Subchapter title
        topics: List of topics related to the subchapter
        num_variations: Number of keyword variations to generate
        max_results: Maximum number of QA pairs to retrieve

    Returns:
        If return_titles is True (default): returns (qa_pairs, qa_titles)
        If return_titles is False: returns qa_pairs

        qa_pairs: List of QA pair dictionaries
        qa_titles: List of QA pair problem titles
    """
    # Extract keywords from outline
    keywords = extract_keywords_from_outline(subchapter_title, topics)

    if not keywords:
        return [], []

    # Search QA pairs using the first keyword (one per keyword as requested)
    try:
        result = await retrieve_and_check_qa(
            keyword=keywords[0],
            num_variations=num_variations,
            max_results_per_keyword=max_results
        )

        qa_pairs = result.get("results", [])
        qa_titles = []

        for qa in qa_pairs:
            title = qa.get("problem", "") or qa.get("problem_thumbnail", "")
            qa_titles.append(title)

        return qa_pairs, qa_titles

    except Exception as e:
        print(f"  [Error] Failed to get QA pairs for '{subchapter_title}': {e}")
        return [], []


async def search_qa_pairs_by_outline(
    chapter_structure: Dict[str, Any],
    language: str = "zh"
) -> Dict[str, Dict[str, Any]]:
    """Search QA pairs for all subchapters in a chapter structure.

    Args:
        chapter_structure: Chapter structure dictionary containing subchapters
        language: Language for the content ("zh" or "en")

    Returns:
        Dictionary mapping subchapter codes to QA pair results
    """
    results = {}

    for chapter_key, chapter_info in chapter_structure.items():
        subchapters = chapter_info.get("sub_chapters", {})
        chapter_results = {}

        for sub_code, sub_info in subchapters.items():
            sub_title = sub_info.get("subchapter_title", "")
            topics = sub_info.get("topics", [])

            if sub_title:
                result = await search_qa_pairs_for_subchapter(
                    subchapter_title=sub_title,
                    topics=topics,
                    max_keywords=10,
                    max_results_per_keyword=1
                )
                chapter_results[sub_code] = result

        results[chapter_key] = chapter_results

    return results


if __name__ == "__main__":
    import asyncio

    async def test():
        # Test case
        subchapter_title = "傅里叶变换"
        topics = ["频域分析", "信号处理", "傅里叶级数", "时域频域转换"]

        result = await search_qa_pairs_for_subchapter(
            subchapter_title=subchapter_title,
            topics=topics,
            max_keywords=5,
            max_results_per_keyword=1
        )

        print(f"Keywords: {result['keywords']}")
        print(f"Total QA pairs found: {result['summary']['total_qa_pairs_found']}")
        print(f"\nSearch results:")
        for sr in result['search_results']:
            print(f"  Keyword: {sr['keyword']}, Found: {sr.get('found', 0)}")

        print(f"\nQA pairs:")
        for i, qa in enumerate(result['qa_pairs'], 1):
            print(f"\n--- QA Pair {i} ---")
            print(f"Search Keyword: {qa.get('search_keyword')}")
            print(f"Problem: {qa.get('problem', '')[:200]}...")
            print(f"Answer: {qa.get('ground_truth_answer', '')[:100]}...")

    asyncio.run(test())
