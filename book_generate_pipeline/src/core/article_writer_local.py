"""
本地实现 content_writer-master/MCPs/ArticleWriter/pipeline.py 中的 write_article 逻辑，
不依赖 MCP 服务；LLM 调用走本项目的 writer 角色模型。

原文参考：content_writer-master/MCPs/ArticleWriter/pipeline.py 与 prompt.py
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, Literal, Optional

from src.models import model_for, writer_completion

logger = logging.getLogger(__name__)

# 与 MCPs/ArticleWriter/prompt.py 保持一致
ARTICLE_WRITER_SYSTEM_PROMPT = """
You are an experienced academic writer, skilled at writing articles that are well‑structured, logically rigorous, and highly readable.

## Writing task
- Understand and integrate the given topic, reference material, Q&A data and encyclopedic data.
- Write the article according to the specified article type, writing style, target audience, extra requirements, and output language.
 
## Available materials (to be fully read and integrated)
- Topic: treat this as the central question.
- Reference material (as the primary reference content): the original paper or book chapter, including the file uploaded by the user or content provided by the user. Use it to understand the background, motivation, methods, experiments, conclusions, and outlook of the topic.
- Q&A data: usually contains key questions and detailed answers around the topic. 
- Encyclopedic data: tends to provide objective, conceptual definitions. Use it to extract precise concepts, background information, and technical terms.

## Writing principles
1. **Material integration strategy**
   - **If reference material is provided**: Use the reference material as the primary source for writing. Use Q&A data and encyclopedic data as supplementary materials to provide auxiliary explanations, clarify concepts, or establish connections with the reference material. The reference material should form the backbone of the article, while Q&A and encyclopedic data enhance understanding and provide additional context.
   - **If no reference material is provided**: Use the topic, Q&A data, and encyclopedic data as the primary sources for writing. Transform the questions and focal points in the Q&A data into natural narrative structure or subsections. Extract definitions, terminology and key facts from encyclopedic data and rewrite them in your own words.
   - When analyzing figures or experimental results in the provided materials, you must strictly rely on the actual data and descriptions presented in the text and figures, and must not make any unverified inferences, additions, or subjective assumptions; if the information is insufficient, avoid analyzing the figure without supporting evidence.
   - When different sources conflict, prioritise conceptual accuracy and academic reliability.
   - Construct the article according to the outline (if provided).
   - **Never explicitly mention sources in the text** (e.g., "according to Q&A data", "based on encyclopedic data", "from the Q&A materials", "as mentioned in the wiki data"). Integrate all knowledge naturally into the narrative flow as if it were your own writing, without revealing the underlying data sources.

2. **Content boundaries and safety**
   - Do not fabricate information that does not exist; all content must be based on the provided materials.
   - Do not fabricate specific citation details such as reference numbers, journal names or DOIs. If you must refer to the literature, use more generic phrasing (e.g. "classic textbooks often state that …").
   - Do not output any personal information that the user has not explicitly provided or requested.

3. **Coherence and transitions**
   - **Between paragraphs**: Use transition sentences or phrases to connect adjacent paragraphs. Each paragraph should logically flow from the previous one, building upon or extending the ideas presented. Avoid abrupt topic shifts without proper bridging.
   - **Between sections/chapters**: Use transition paragraphs or sentences at the beginning of each new section to connect it with the previous section. Clearly establish the relationship between sections. Ensure smooth logical progression throughout the article.
   - **Logical flow**: The article should read as a cohesive narrative, not as disconnected pieces. Each section should contribute to the overall argument or narrative arc, with clear connections between ideas.
   - **No jumping or breaking**: Avoid sudden topic changes, redundant content, or repetitive information. Maintain a coherent thread that guides the reader through the entire article.
   
## Output format
- Directly output the final article text in Markdown format.
- Do NOT output JSON, and do NOT wrap the whole content in Markdown code fences (```).
"""

DEFAULT_WRITING_STYLE_PROMPT = """
## Style and readability requirements
- The language should be natural and fluent, avoiding “translationese”.
- For highly abstract or mathematical content, first give intuitive explanations, then provide more formal or rigorous descriptions.
- The output should be a polished article ready for publication or submission, not an outline or bullet‑point notes.
- **Coherence and flow**: Ensure smooth transitions between paragraphs and sections. Use transition sentences to connect ideas and maintain logical flow throughout the article.
- For chapters: ensure the content fits naturally within a book context, with appropriate transitions and connections to broader themes.
- For articles: ensure the content is self-contained and can stand alone as a complete piece, with clear connections between all sections.
"""


async def _call_llm_combined(
    system_prompt: str,
    user_prompt: str,
    temperature: float = 1.0,
) -> tuple[str, Optional[Dict[str, Any]]]:
    """MCP 侧 utils.call_llm 在本仓库中的等价：单条 user 消息内嵌 system（OpenAI 兼容端仅 user 时）。"""
    combined = (
        "请同时遵循 [SYSTEM] 中的角色与原则，并完成 [USER] 中的写作任务与材料说明。\n\n"
        f"[SYSTEM]\n{system_prompt}\n\n[USER]\n{user_prompt}"
    )
    start = time.time()
    text = await writer_completion(combined, temperature=temperature)
    stats = {
        "model": model_for("writer"),
        "llm_elapsed_time_seconds": round(time.time() - start, 2),
    }
    return (text or "").strip(), stats


async def write_article(
    topic: Optional[str] = None,
    reference_material_path: Optional[str] = None,
    reference_material_content: Optional[str] = None,
    qa_data: Optional[str] = None,
    wiki_data: Optional[str] = None,
    outline: Optional[str] = None,
    article_type: Literal["article", "chapter"] = "article",
    writing_style: Optional[str] = None,
    target_audience: Optional[str] = None,
    output_language: str = "English",
    extra_requirements: Optional[str] = None,
) -> Dict[str, Any]:
    """
    与 content_writer-master/MCPs/ArticleWriter/pipeline.write_article 对齐的入口。
    说明：reference_material_path 在本仓库中不支持随请求传 PDF（无 litellm 多模态拼装），
    请将参考内容放在 reference_material_content 文本字段中。
    """
    if reference_material_path and (not reference_material_content or not str(reference_material_content).strip()):
        logger.warning(
            "article_writer_local: 已忽略 reference_material_path=%s（本地实现仅使用文本字段 reference_material_content）",
            reference_material_path,
        )

    start_time = time.time()

    system_prompt = ARTICLE_WRITER_SYSTEM_PROMPT
    if writing_style is None:
        system_prompt += DEFAULT_WRITING_STYLE_PROMPT
    else:
        ws = str(writing_style).strip()
        if ws:
            system_prompt += "\n## Additional style guidance from caller\n" + ws + "\n"

    user_prompt_parts = [
        f"## Article type: {article_type}",
        f"## Writing style: {writing_style.strip() if isinstance(writing_style, str) and writing_style.strip() else '(no writing style provided)'}",
        f"## Target audience: {target_audience.strip() if isinstance(target_audience, str) and target_audience.strip() else '(no target audience provided)'}",
        f"## Output language: {output_language}",
        f"## Topic\n{(topic or '').strip()}",
        f"## Reference material: {reference_material_content.strip() if isinstance(reference_material_content, str) and reference_material_content.strip() else '(no reference material provided)'}",
        f"## Q&A Data: {qa_data.strip() if isinstance(qa_data, str) and qa_data.strip() else '(no Q&A data provided)'}",
        f"## Wiki Data: {wiki_data.strip() if isinstance(wiki_data, str) and wiki_data.strip() else '(no encyclopedic data provided)'}",
        f"## Outline: {outline.strip() if isinstance(outline, str) and outline.strip() else '(no outline provided)'}",
        f"## Additional requirements: {extra_requirements.strip() if isinstance(extra_requirements, str) and extra_requirements.strip() else '(no additional requirements provided)'}",
    ]
    user_prompt = "\n".join(user_prompt_parts)

    article_text, stats = await _call_llm_combined(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        temperature=1.0,
    )

    elapsed_time = time.time() - start_time
    usage_stats = None
    if stats:
        usage_stats = {
            "model": stats.get("model"),
            "llm_elapsed_time_seconds": stats.get("llm_elapsed_time_seconds"),
            "total_elapsed_time_seconds": round(elapsed_time, 2),
        }

    result: Dict[str, Any] = {"article": article_text or ""}
    if usage_stats:
        result["usage_stats"] = usage_stats
    logger.info("article_writer_local: 完成生成，长度 %d 字符", len(result["article"]))
    return result
