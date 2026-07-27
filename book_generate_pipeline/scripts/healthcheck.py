#!/usr/bin/env python3
"""逐项体检：LiteLLM 网关各角色模型、出图、百科检索、问答检索、PDF 渲染。

用法：
    python scripts/healthcheck.py            # 全部检查
    python scripts/healthcheck.py chat image # 只跑指定项
"""

import asyncio
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

RESULTS = []


def record(name, ok, detail=""):
    RESULTS.append((name, ok, detail))
    print(f"[{'OK ' if ok else 'FAIL'}] {name} {('- ' + detail) if detail else ''}")


async def check_env():
    from src.utils import get_config

    config = get_config()
    record("网关地址", bool(config.gateway_base_url), config.gateway_base_url or "未配置")
    record("网关密钥", bool(config.gateway_api_key), "已设置" if config.gateway_api_key else "未配置")
    for role in ("writer", "reviewer", "utility", "image"):
        record(f"模型配置 [{role}]", True, config.get_model(role))
    for key in ("OPENSEARCH_HOST", "OPENSEARCH_USERNAME", "OPENSEARCH_PASSWORD"):
        record(f"环境变量 {key}", bool(os.environ.get(key)), "已设置" if os.environ.get(key) else "未设置")


async def check_chat():
    """writer / reviewer / utility 三个文本角色。"""
    from src.models import complete, model_for

    for role in ("writer", "reviewer", "utility"):
        model = model_for(role)
        start = time.time()
        try:
            text = await asyncio.wait_for(
                complete("回复两个字：可用", model=model, max_tokens=512), timeout=180
            )
            record(f"{role} ({model})", bool(text.strip()), f"{time.time() - start:.1f}s {text.strip()[:30]}")
        except Exception as e:
            record(f"{role} ({model})", False, f"{type(e).__name__}: {str(e)[:150]}")


async def check_structured():
    """结构化输出，QA 关键词扩展依赖它。"""
    from pydantic import BaseModel
    from src.models import model_for, structured_completion

    class Answer(BaseModel):
        keywords: list[str]

    try:
        content, usage = await asyncio.wait_for(
            structured_completion(
                "你是关键词抽取助手，只输出 JSON。",
                "从「蛋白质组学 质谱」中抽出英文关键词。",
                response_format=Answer,
                max_tokens=512,
            ),
            timeout=180,
        )
        record(f"结构化输出 ({model_for('utility')})", "keywords" in content, content[:120])
    except Exception as e:
        record("结构化输出", False, f"{type(e).__name__}: {str(e)[:150]}")


async def check_image():
    from src.models import generate_images, model_for

    try:
        images = await asyncio.wait_for(
            generate_images("a simple blue circle on white background", max_attempts=1),
            timeout=300,
        )
        total = sum(len(b) for b in images)
        record(f"出图 ({model_for('image')})", bool(images), f"{len(images)} 张，共 {total} 字节")
    except Exception as e:
        record("出图", False, f"{type(e).__name__}: {str(e)[:150]}")


async def check_wiki():
    from src.tools.get_wiki_article import search_wiki_articles_for_subchapter

    try:
        res = await asyncio.wait_for(
            search_wiki_articles_for_subchapter("蛋白质组学", ["质谱"], k=2), timeout=90
        )
        contents = res[0] if isinstance(res, tuple) else res
        record("百科检索", bool(contents), f"{len(contents)} 篇")
    except Exception as e:
        record("百科检索", False, f"{type(e).__name__}: {str(e)[:150]}")


async def check_opensearch():
    from src.tools.qa_retrieve.retriever import QARetriever

    try:
        retriever = QARetriever()
        problems = await asyncio.wait_for(
            retriever.search_problems_only("proteomics", max_results=3), timeout=90
        )
        record("问答检索 (OpenSearch)", bool(problems), f"命中 {len(problems)} 条")
    except Exception as e:
        record("问答检索 (OpenSearch)", False, f"{type(e).__name__}: {str(e)[:150]}")


async def check_render():
    """Playwright + Chromium，成书转 PDF 依赖它。"""
    try:
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page()
            await page.set_content("<h1>ok</h1>")
            pdf = await page.pdf()
            await browser.close()
        record("Playwright 渲染", len(pdf) > 0, f"{len(pdf)} 字节 PDF")
    except Exception as e:
        record("Playwright 渲染", False, f"{type(e).__name__}: {str(e)[:150]}")


CHECKS = {
    "env": check_env,
    "chat": check_chat,
    "structured": check_structured,
    "image": check_image,
    "wiki": check_wiki,
    "opensearch": check_opensearch,
    "render": check_render,
}


async def main():
    selected = sys.argv[1:] or list(CHECKS)
    for name in selected:
        check = CHECKS.get(name)
        if check is None:
            print(f"未知检查项: {name}（可选: {', '.join(CHECKS)}）")
            continue
        print(f"\n=== {name} ===")
        await check()

    failed = [name for name, ok, _ in RESULTS if not ok]
    print(f"\n总计 {len(RESULTS)} 项，失败 {len(failed)} 项")
    if failed:
        print("失败项：" + ", ".join(failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
