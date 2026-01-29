import asyncio
import json
import logging
import sys
import time
from typing import Dict, List, Optional, Tuple
from pathlib import Path

import dotenv

from .prompt import (
    KEYWORD_VARIATIONS_PROMPT,
    PROBLEM_FILTER_PROMPT,
    KeywordVariations,
    ProblemFilterResult,
)
from .utils import call_llm, LLMUsageStats
from .retriever import QARetriever

dotenv.load_dotenv(override=True)

logger = logging.getLogger(__name__)


async def expand_keywords(keyword: str, num_variations: int = 8) -> Tuple[List[str], Optional[LLMUsageStats]]:
    """
    Generate keyword variations based on the given keyword
    """
    try:
        user_prompt = f"Please generate {num_variations} different variations of the following keyword:\n\nKeyword: {keyword}"
        
        response, stats = await call_llm(
            system_prompt=KEYWORD_VARIATIONS_PROMPT,
            user_prompt=user_prompt,
            response_format=KeywordVariations,
            temperature=1.0,
            max_tokens=2048
        )
        
        if stats:
            logger.info(f"Keyword expansion statistics: {stats}")
        
        result = json.loads(response)
        variations = result.get("variations", [])
        
        if keyword not in variations:
            variations.insert(0, keyword)
        
        logger.info(f"Generated {len(variations)} keyword variations: {variations}")
        return variations, stats
        
    except Exception as e:
        logger.error(f"Keyword expansion failed: {e}", exc_info=True)
        return [keyword], None



async def filter_problems_by_query(problems: List[Dict], query: str) -> Tuple[List[str], Optional[LLMUsageStats]]:
    """
    Use LLM to filter problems that match the query
    """
    if not problems:
        return [], None
    
    try:
        logger.info(f"Filtering {len(problems)} problems for query: {query}")
        
        problem_list = []
        for p in problems:
            problem_id = p.get('_id', '')
            problem_text = p.get('problem', '') or p.get('problem_thumbnail', '')
            problem_list.append(f"ID: {problem_id}\nProblem: {problem_text}")
        
        problems_text = "\n\n".join(problem_list)
        
        user_prompt = f"""Query: {query}

Problems:
{problems_text}

Please select the problem IDs that are most relevant to the query."""
        
        response, stats = await call_llm(
            system_prompt=PROBLEM_FILTER_PROMPT,
            user_prompt=user_prompt,
            response_format=ProblemFilterResult,
            temperature=0.3,
            max_tokens=2048
        )
        if stats:
            logger.info(f"Problem filtering statistics: {stats}")
        result = json.loads(response)
        selected_ids = result.get("selected_ids", [])
        
        logger.info(f"Selected {len(selected_ids)} problems from {len(problems)} candidates")
        
        return selected_ids, stats
        
    except Exception as e:
        logger.error(f"Problem filtering failed: {e}", exc_info=True)
        logger.warning("Returning empty list due to filtering failure")
        return [], None


async def retrieve_and_check_qa(
    keyword: str,
    num_variations: int = 5,
    max_results_per_keyword: int = 2
) -> Dict:
    """
    Expand keywords, search QA pairs, filter with LLM, and retrieve details
    """
    logger.info(f"Starting QA retrieval and quality check for keyword: {keyword}")
    start_time = time.time()
    
    total_stats = {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "llm_calls": 0
    }
    
    try:
        variations, expand_stats = await expand_keywords(keyword, num_variations)
        if expand_stats:
            total_stats["prompt_tokens"] += expand_stats.prompt_tokens
            total_stats["completion_tokens"] += expand_stats.completion_tokens
            total_stats["total_tokens"] += expand_stats.total_tokens
            total_stats["llm_calls"] += 1

        logger.info(f"variations: {variations}")

        retriever = QARetriever()

        logger.info(f"Searching with keyword: {keyword}, variations: {variations}")
        all_problems = await retriever.search_problems_only(
            query=keyword,
            variations=variations,
            max_results=max_results_per_keyword
        )

        logger.info(f"Filtering {len(all_problems)} problems using LLM for query: {keyword}")

        # selected_ids, filter_stats = await filter_problems_by_query(all_problems, keyword)
        # if filter_stats:
        #     total_stats["prompt_tokens"] += filter_stats.prompt_tokens
        #     total_stats["completion_tokens"] += filter_stats.completion_tokens
        #     total_stats["total_tokens"] += filter_stats.total_tokens
        #     total_stats["llm_calls"] += 1
        
        # Skip LLM filtering for efficiency
        selected_ids = [
            p.get("_id", "")
            for p in all_problems
            if p.get("_id")
        ]

        if not selected_ids:
            print(f"  [QA] Keyword '{keyword}': No QA pairs found")
            # logger.warning("No problems selected after filtering")
            elapsed_time = time.time() - start_time
            usage_stats = {
                "total_elapsed_time_seconds": round(elapsed_time, 2),
                "llm_calls": total_stats["llm_calls"],
                "total_tokens": total_stats["total_tokens"],
                "prompt_tokens": total_stats["prompt_tokens"],
                "completion_tokens": total_stats["completion_tokens"],
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
            }
            return {
                "keyword": keyword,
                "variations": variations,
                "results": [],
                "summary": {
                    "total_found": 0,
                    "selected_count": 0
                },
                "usage_stats": usage_stats
            }
        
        logger.info(f"Getting details for {len(selected_ids)} selected problems")
        qa_pairs = await retriever.get_problem_details(selected_ids)
        
        all_results = []
        for qa_pair in qa_pairs:
            result_item = {
                "problem_id": qa_pair.get("_id", ""),
                "problem_thumbnail": qa_pair.get("problem_thumbnail", ""),
                "problem": qa_pair.get("problem", ""),
                "ground_truth_answer": qa_pair.get("ground_truth_answer", ""),
                "solutions": qa_pair.get("solutions", ""),
            }
            all_results.append(result_item)
        
        elapsed_time = time.time() - start_time
        
        total_found = len(all_results)
        selected_count = len(selected_ids)
        
        usage_stats = {
            "total_elapsed_time_seconds": round(elapsed_time, 2),
            "llm_calls": total_stats["llm_calls"],
            "total_tokens": total_stats["total_tokens"],
            "prompt_tokens": total_stats["prompt_tokens"],
            "completion_tokens": total_stats["completion_tokens"],
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
        }
        
        result = {
            "keyword": keyword,
            "variations": variations,
            "results": all_results,
            "total_found": total_found,
            "selected_count": selected_count,
            "usage_stats": usage_stats,
        }
        
        logger.info(f"QA retrieval completed! Keyword: {keyword}, Variations generated: {len(variations)},Total problems found: {len(all_problems)}")
        logger.info(f"Final results: {total_found}, Usage Statistics: {usage_stats}")

        
        return result
        
    except Exception as e:
        logger.error(f"QA retrieval and quality check failed: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    try:
        result = asyncio.run(
            retrieve_and_check_qa(
                keyword="Transformer",
                num_variations=4,
                max_results_per_keyword=5,
            )
        )

        print(f"\nKeyword: {result.get('keyword')}, Variations: {result.get('variations', [])}, Total found: {result.get('total_found', 0)}, Selected count: {result.get('selected_count', 0)}")
        print(f"\nUsage statistics: {result.get('usage_stats', {})}")

        results = result.get("results", [])
        if results:
            for i, r in enumerate(results[:2], 1):
                print("problem_thumbnail: ", r.get("problem_thumbnail"))
                print("problem: ", r.get("problem"))
                print("ground_truth_answer: ", r.get("ground_truth_answer"))
                print("solutions length: ", len(r.get("solutions", "")))
                print("\n")
    except Exception as e:
        logger.error(f"Execution failed: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)

