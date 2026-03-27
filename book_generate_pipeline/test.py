"""Test script for get_qa_pair tool."""

import asyncio
import sys
import os
import litellm
from pathlib import Path

try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None

from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")
# Add src directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.tools.get_qa_pair import (
    extract_keywords_from_outline,
    search_qa_pairs_for_subchapter,
    get_qa_pair_for_subchapter,
    search_qa_pairs_by_outline
)
from src.models import gpugeek_image_generation

def test_draw_image():
    env_path = Path(__file__).resolve().parent / ".env"
    if load_dotenv and env_path.exists():
        # 测试脚本优先使用当前项目 .env，避免被外部环境变量污染
        load_dotenv(dotenv_path=env_path, override=True)

    LITELLM_PROXY_API_BASE = os.environ.get("LITELLM_PROXY_API_BASE", "").strip()
    LITELLM_PROXY_API_KEY = os.environ.get("LITELLM_PROXY_API_KEY", "").strip()
    if LITELLM_PROXY_API_KEY:
        os.environ["LITELLM_API_KEY"] = LITELLM_PROXY_API_KEY

    print(f"LITELLM_PROXY_API_BASE: {LITELLM_PROXY_API_BASE}")
    print(f"LITELLM_PROXY_API_KEY set: {bool(LITELLM_PROXY_API_KEY)}")

    if not LITELLM_PROXY_API_BASE or not LITELLM_PROXY_API_KEY:
        raise RuntimeError(
            "缺少绘图配置：请在 .env 中设置 LITELLM_PROXY_API_BASE 和 LITELLM_PROXY_API_KEY"
        )

    # model = "litellm_proxy/gemini-3-pro-image-preview"
    model = "litellm_proxy/gemini-3-pro-preview"
    prompt = "画一个苹果"
    response = litellm.completion(
        model=model,
        messages=[{"role": "user", "content": prompt}],
    )
    print(response)


async def test_gpugeek_image_generation():
    """Test gpugeek image provider registration and API availability."""
    env_path = Path(__file__).resolve().parent / ".env"
    if load_dotenv and env_path.exists():
        load_dotenv(dotenv_path=env_path, override=True)

    api_key = os.environ.get("GPUGEEK_API_KEY", "").strip()
    print(f"GPUGEEK_API_KEY set: {bool(api_key)}")
    if not api_key:
        raise RuntimeError("缺少 GPUGEEK_API_KEY，请先在 .env 中配置。")

    outputs = await gpugeek_image_generation(
        prompt="画一个气球",
        aspect_ratio="16:9",
        image_size="1K",
    )
    print(f"gpugeek_image_generation outputs count: {len(outputs)}")
    if outputs:
        first = outputs[0]
        if isinstance(first, str):
            print(f"First output preview: {first[:120]}")
        else:
            print(f"First output type: {type(first)}")

async def test_search_qa_pairs():
    """Test searching QA pairs for a subchapter."""
    print("\n" + "=" * 60)
    print("Test 2: search_qa_pairs_for_subchapter")
    print("=" * 60)

    test_cases = [
        {
            "name": "Fourier Transform",
            "subchapter_title": "傅里叶变换",
            "topics": ["频域分析", "信号处理"],
        },
        {
            "name": "Linear Algebra",
            "subchapter_title": "线性代数基础",
            "topics": ["矩阵运算", "行列式"],
        },
    ]

    for i, test_case in enumerate(test_cases, 1):
        print(f"\n--- Test Case {i}: {test_case['name']} ---")
        print(f"Title: {test_case['subchapter_title']}")
        print(f"Topics: {test_case['topics']}")

        result = await search_qa_pairs_for_subchapter(
            subchapter_title=test_case["subchapter_title"],
            topics=test_case["topics"],
            max_keywords=5,
            max_results_per_keyword=1
        )

        print(f"Keywords searched: {result['keywords']}")
        print(f"Total QA pairs found: {result['summary']['total_qa_pairs_found']}")

        print(f"\nSearch results per keyword:")
        for sr in result['search_results']:
            if 'error' in sr:
                print(f"  - {sr['keyword']}: ERROR - {sr['error']}")
            else:
                print(f"  - {sr['keyword']}: {sr['found']} found")

        if result['qa_pairs']:
            print(f"\nSample QA pairs:")
            for j, qa in enumerate(result['qa_pairs'][:2], 1):
                print(f"\n  --- QA Pair {j} ---")
                print(f"  Search Keyword: {qa.get('search_keyword')}")
                problem = qa.get('problem', '') or qa.get('problem_thumbnail', '')
                print(f"  Problem: {problem[:150]}...")
                answer = qa.get('ground_truth_answer', '')
                print(f"  Answer: {answer[:100]}...")


async def test_get_qa_pair_for_subchapter():
    """Test get_qa_pair_for_subchapter function (matching get_wiki_article signature)."""
    print("\n" + "=" * 60)
    print("Test 3: get_qa_pair_for_subchapter")
    print("=" * 60)

    test_cases = [
        {
            "name": "Transformer",
            "subchapter_title": "Transformer",
            "topics": ["注意力机制", "深度学习", "神经网络"],
        },
        {
            "name": "Bessel Function",
            "subchapter_title": "贝塞尔函数",
            "topics": ["特殊函数", "数学物理"],
        },
    ]

    for i, test_case in enumerate(test_cases, 1):
        print(f"\n--- Test Case {i}: {test_case['name']} ---")
        print(f"Title: {test_case['subchapter_title']}")
        print(f"Topics: {test_case['topics']}")

        qa_pairs, qa_titles = await get_qa_pair_for_subchapter(
            subchapter_title=test_case["subchapter_title"],
            topics=test_case["topics"],
            num_variations=3,
            max_results=2
        )

        print(f"QA pairs found: {len(qa_pairs)}")
        print(f"QA titles: {qa_titles}")

        if qa_pairs:
            print(f"\nSample QA pair:")
            qa = qa_pairs[0]
            problem = qa.get('problem', '') or qa.get('problem_thumbnail', '')
            print(f"  Problem: {problem[:200]}...")
            answer = qa.get('ground_truth_answer', '')
            print(f"  Answer: {answer[:150]}...")


async def test_search_qa_pairs_by_outline():
    """Test searching QA pairs for a complete chapter structure."""
    print("\n" + "=" * 60)
    print("Test 4: search_qa_pairs_by_outline")
    print("=" * 60)

    # Mock chapter structure
    chapter_structure = {
        "chapter1": {
            "title": "第一章 数学基础",
            "sub_chapters": {
                "1.1": {
                    "subchapter_title": "微积分基础",
                    "topics": ["导数", "积分", "极限"]
                },
                "1.2": {
                    "subchapter_title": "线性代数",
                    "topics": ["矩阵", "向量", "特征值"]
                }
            }
        },
        "chapter2": {
            "title": "第二章 物理基础",
            "sub_chapters": {
                "2.1": {
                    "subchapter_title": "经典力学",
                    "topics": ["牛顿定律", "动量", "能量"]
                },
                "2.2": {
                    "subchapter_title": "电磁学",
                    "topics": ["电场", "磁场", "麦克斯韦方程"]
                }
            }
        }
    }

    print(f"Chapter structure: {list(chapter_structure.keys())}")

    results = await search_qa_pairs_by_outline(
        chapter_structure=chapter_structure,
        language="zh"
    )

    for chapter_key, chapter_results in results.items():
        print(f"\n{chapter_key}:")
        for sub_code, result in chapter_results.items():
            print(f"  {sub_code}: {result['summary']['total_qa_pairs_found']} QA pairs found")


async def run_all_tests():
    """Run all test functions."""
    print("\n" + "=" * 60)
    print("QA Pair Tool Test Suite")
    print("=" * 60)

    # Test 1: Keyword extraction (synchronous)

    # Test 2: Search QA pairs
    await test_search_qa_pairs()

    # Test 3: Get QA pair for subchapter
    await test_get_qa_pair_for_subchapter()

    # Test 4: Search QA pairs by outline
    await test_search_qa_pairs_by_outline()

    print("\n" + "=" * 60)
    print("All tests completed!")
    print("=" * 60)



import asyncio
from dp.agent.client import MCPClient

async def test_mcp_tool():
    mcp_url = "http://rceb1397946.bohrium.tech:50001/mcp"
    async with MCPClient(mcp_url) as client:
        result = await client.call_tool(
            "generate_article",
            arguments={
                'topic': "path integral molecular dynamics",
                "language": "en",
            },
            async_mode=True,
        )
        print("result: ", result)

if __name__ == "__main__":
    # asyncio.run(test_mcp_tool())
    # test_draw_image()
    asyncio.run(test_gpugeek_image_generation())


