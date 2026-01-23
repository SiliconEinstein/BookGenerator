"""QA pair retrieval tool for textbook chapter outline."""

import re
import json
from typing import Dict, Any, Optional, List, Union

from src.tools.qa_retrieve.pipeline import retrieve_and_check_qa
from src.utils import sanitize_filename
from src.models import gemini_completion


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
    prompt = f"请从[{words}]中提取关键词，不得超过{max_keywords}个关键词，以json列表形式返回: \n[keyword1, ...]"
    response = await gemini_completion(prompt=prompt)
    match = re.search(r'```json\s*(\[.*?\]|\{.*?\})\s*```', response, re.DOTALL).group(1)
    keywords = json.loads(match.strip())
    return keywords
    
    
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
