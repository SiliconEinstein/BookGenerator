#!/usr/bin/env python
import html
import json
import mimetypes
import os
import re
import shutil
import subprocess
import time
import urllib.error
import urllib.request
import requests
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, unquote


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = ROOT / "examples" / "_service_output"
THEMES_ROOT = ROOT / "assets" / "themes"
SKILL_FILE = ROOT / "SKILL.md"
_SKILL_CACHE = None


def _truthy(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return False


def _skill_prompt_text(max_chars: int = 12000):
    global _SKILL_CACHE
    if _SKILL_CACHE is None:
        try:
            _SKILL_CACHE = SKILL_FILE.read_text(encoding="utf-8")
        except Exception:
            _SKILL_CACHE = ""
    text = (_SKILL_CACHE or "").strip()
    if len(text) > max_chars:
        text = text[:max_chars]
    return text


def _strip_md(text: str) -> str:
    value = text or ""
    value = re.sub(r"`([^`]+)`", r"\1", value)
    value = re.sub(r"\*\*([^*]+)\*\*", r"\1", value)
    value = re.sub(r"\*([^*]+)\*", r"\1", value)
    value = re.sub(r"_([^_]+)_", r"\1", value)
    return value.strip()


def _md_bullets(md: str, limit: int = 6):
    rows = []
    for raw in (md or "").splitlines():
        line = raw.strip()
        if line.startswith("- "):
            rows.append(_strip_md(line[2:].strip()))
        elif re.match(r"^\d+\.\s+", line):
            rows.append(_strip_md(re.sub(r"^\d+\.\s+", "", line)))
    return [item for item in rows if item][:limit]


def _first_heading(md: str):
    for raw in (md or "").splitlines():
        line = raw.strip()
        if line.startswith("## "):
            return _strip_md(line[3:].strip())
        if line.startswith("# "):
            return _strip_md(line[2:].strip())
    return ""


def normalize_theme(theme: str) -> str:
    candidate = (theme or "minimal-white").strip()
    if not candidate:
        candidate = "minimal-white"
    css = THEMES_ROOT / f"{candidate}.css"
    return candidate if css.exists() else "minimal-white"


def safe_name(name: str) -> str:
    text = name.strip() or "deck"
    return re.sub(r"[^a-zA-Z0-9._-]+", "-", text).strip("-") or "deck"


def chrome_candidates():
    return [
        os.environ.get("CHROME_PATH", ""),
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ]


def find_chrome():
    for item in chrome_candidates():
        if item and Path(item).exists():
            return item
    return None


def _slides_from_ppt_input(payload: dict):
    chapter = _strip_md(payload.get("chapterName", "")).strip()
    section = _strip_md(payload.get("sectionName", "")).strip()
    title = section or chapter or "课堂汇报"

    teaching_goal = payload.get("teachingGoal", "")
    knowledge_points = payload.get("knowledgePoints", "")
    structure = payload.get("suggestedStructure", "")
    extra = payload.get("extraInfo", "")

    slides = []
    if chapter or section:
        subtitle = " · ".join([x for x in [chapter, section] if x])
        slides.append({"title": "封面", "body": subtitle or title})

    goal_heading = _first_heading(teaching_goal) or "教学目标"
    goal_items = _md_bullets(teaching_goal, limit=6)
    if goal_items:
        slides.append({"title": goal_heading, "body": goal_items})

    kp_heading = _first_heading(knowledge_points) or "核心知识点"
    kp_items = _md_bullets(knowledge_points, limit=8)
    if kp_items:
        slides.append({"title": kp_heading, "body": kp_items})

    flow_heading = _first_heading(structure) or "课堂流程"
    flow_items = _md_bullets(structure, limit=8)
    if flow_items:
        slides.append({"title": flow_heading, "body": flow_items})

    extra_heading = _first_heading(extra) or "案例与拓展"
    extra_items = _md_bullets(extra, limit=8)
    if extra_items:
        slides.append({"title": extra_heading, "body": extra_items})

    if not slides:
        slides = [{"title": "封面", "body": "这是通过 html-ppt-skill 服务接口生成的示例。"}]

    return title, slides


def _json_from_model_text(text: str):
    if not text:
        raise RuntimeError("model returned empty content")
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.I)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, flags=re.S)
        if not match:
            raise RuntimeError("model output does not contain JSON")
        return json.loads(match.group(0))


def _llm_prompt_from_payload(payload: dict, page_min: int, page_max: int, include_skill: bool = True):
    source = payload.get("pptInput", payload)
    source_text = json.dumps(source, ensure_ascii=False, indent=2)
    skill_prompt = _skill_prompt_text() if include_skill else ""
    skill_block = ""
    if skill_prompt:
        skill_block = f"""
以下是 html-ppt skill 说明（请把它当作设计规范）：
<<<SKILL_PROMPT_START>>>
{skill_prompt}
<<<SKILL_PROMPT_END>>>
""".strip()
    return f"""
你是资深演示设计师。请基于输入内容，输出可直接渲染的 slides JSON。

要求：
1) 只输出 JSON，不要解释文本。
2) JSON 结构必须是：
{{
  "title": "总标题",
  "slides": [
    {{
      "title": "页标题",
      "layout": "bullets",
      "body": {{"items": ["要点1", "要点2"]}} 或 "文本内容"
    }}
  ]
}}
3) slides 数量范围：{page_min} 到 {page_max}。
4) 每页必须包含 layout 字段，根据内容特点选择合适的布局类型。
5) 输出语言：中文。
6) 优先遵循上面的 html-ppt skill 风格与约束（如果提供了 skill 文本）。
7) 不要在 JSON 中包含 theme 字段（主题由调用方指定）。

可用的布局类型（layout）及其适用场景：
- **cover**: 封面页，用于开篇。body 格式: {{"subtitle": "副标题", "author": "作者"}}
- **bullets**: 要点列表（最常用）。body 格式: {{"items": ["要点1", "要点2", ...]}}
- **two-column**: 左右对比。body 格式: {{"left": ["左侧要点1", ...], "right": ["右侧要点1", ...]}}
- **three-column**: 三栏并列。body 格式: {{"col1": ["项1", ...], "col2": [...], "col3": [...]}}
- **stat-highlight**: 突出单个关键数字。body 格式: {{"number": "85%", "subtitle": "增长率"}}
- **kpi-grid**: 多个指标展示（2-4个）。body 格式: {{"metrics": [{{"label": "指标1", "value": "123"}}, ...]}}
- **big-quote**: 引用或金句强调。body 格式: {{"quote": "引用文本", "author": "作者"}}
- **comparison**: 对比表格。body 格式: {{"headers": ["维度", "方案A", "方案B"], "rows": [["性能", "高", "中"], ...]}}
- **timeline**: 时间线。body 格式: {{"events": [{{"year": "2020", "event": "事件描述"}}, ...]}}
- **code**: 代码展示。body 格式: {{"language": "python", "code": "代码内容"}}
- **image-hero**: 图片为主。body 格式: {{"image_url": "URL", "caption": "说明"}}
- **section-divider**: 章节分隔。body 格式: {{"subtitle": "子标题"}}
- **thanks**: 感谢页。body 格式: {{"contact": "联系方式"}}

布局选择原则：
- 首页用 cover
- 单一关键数据用 stat-highlight
- 多个指标用 kpi-grid
- 对比分析用 two-column 或 comparison
- 时间相关用 timeline
- 列举要点用 bullets
- 章节开始用 section-divider
- 最后一页用 thanks

{skill_block}

输入内容：
{source_text}
""".strip()


def _post_json(url: str, headers: dict, payload: dict, timeout: int):
    req = urllib.request.Request(
        url=url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return resp.status, body
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"model http error {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"model request failed: {exc}") from exc


def _call_openai_chat(api_key: str, model: str, prompt: str, base_url: str, timeout: int):
    url = base_url.rstrip("/") + "/v1/chat/completions"
    status, body = _post_json(
        url=url,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        payload={
            "model": model,
            "temperature": 0.4,
            "messages": [
                {"role": "system", "content": "You output strict JSON only."},
                {"role": "user", "content": prompt},
            ],
        },
        timeout=timeout,
    )
    if status != 200:
        raise RuntimeError(f"unexpected status from openai-compatible api: {status}")
    data = json.loads(body)
    return data["choices"][0]["message"]["content"]


def _call_anthropic(api_key: str, model: str, prompt: str, base_url: str, timeout: int):
    url = base_url.rstrip("/") + "/v1/messages"
    status, body = _post_json(
        url=url,
        headers={
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
        payload={
            "model": model,
            "max_tokens": 3000,
            "temperature": 0.4,
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=timeout,
    )
    if status != 200:
        raise RuntimeError(f"unexpected status from anthropic api: {status}")
    data = json.loads(body)
    parts = data.get("content", [])
    text = "".join([x.get("text", "") for x in parts if x.get("type") == "text"]).strip()
    if not text:
        raise RuntimeError("anthropic returned empty text")
    return text


def _call_gpugeek_chat(payload: dict, prompt: str):
    api_base = (payload.get("modelBaseUrl") or os.environ.get("GPUGEEK_API_BASE", "")).strip()
    api_key = (payload.get("modelApiKey") or os.environ.get("GPUGEEK_API_KEY", "")).strip()
    model = (payload.get("modelName") or os.environ.get("LLM_MODEL", "Vendor2/GPT-5.2")).strip()
    if not api_base or not api_key:
        raise RuntimeError("GPUGeek API not configured (need GPUGEEK_API_BASE and GPUGEEK_API_KEY)")

    retry_times = int(payload.get("modelRetryTimes", os.environ.get("LLM_RETRY_TIMES", 3)))
    retry_times = max(1, retry_times)
    connect_timeout = int(payload.get("modelConnectTimeoutSec", os.environ.get("LLM_CONNECT_TIMEOUT_SECONDS", 20)))
    read_timeout = int(payload.get("modelReadTimeoutSec", os.environ.get("LLM_READ_TIMEOUT_SECONDS", 360)))
    max_tokens = int(payload.get("modelMaxTokens", 65535))
    temperature = float(payload.get("modelTemperature", 0.4))

    request_payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
        "max_completion_tokens": max_tokens,
    }

    last_error = None
    for attempt in range(retry_times):
        try:
            response = requests.post(
                f"{api_base.rstrip('/')}/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=request_payload,
                timeout=(connect_timeout, read_timeout),
            )
            response.raise_for_status()
            data = response.json()
            content = data["choices"][0]["message"]["content"] or ""
            return model, content
        except Exception as exc:
            last_error = exc
            if attempt < retry_times - 1:
                time.sleep(min(8.0, 1.2 * (2 ** attempt)))
    prompt_chars = len(prompt or "")
    raise RuntimeError(
        f"LLM request failed (model={model}, prompt_chars={prompt_chars}, max_tokens={max_tokens}): {last_error}"
    )


def _generate_slides_with_model(payload: dict):
    provider = (
        payload.get("modelProvider")
        or os.environ.get("PPT_MODEL_PROVIDER")
        or "gpugeek"
    ).strip().lower()
    page_min = int(payload.get("pageMin", 8))
    page_max = int(payload.get("pageMax", 12))
    if page_min <= 0:
        page_min = 1
    if page_max < page_min:
        page_max = page_min

    include_skill = _truthy(payload.get("injectSkillPrompt", True))
    prompt = _llm_prompt_from_payload(payload, page_min=page_min, page_max=page_max, include_skill=include_skill)
    if provider in {"gpugeek", "gpt"}:
        model, content = _call_gpugeek_chat(payload=payload, prompt=prompt)
    elif provider == "anthropic":
        model = (
            payload.get("modelName")
            or os.environ.get("PPT_MODEL_NAME")
            or "claude-3-5-sonnet-20241022"
        ).strip()
        api_key = payload.get("modelApiKey") or os.environ.get("PPT_MODEL_API_KEY", "")
        if not api_key:
            raise RuntimeError("missing model api key (modelApiKey or PPT_MODEL_API_KEY)")
        base_url = (
            payload.get("modelBaseUrl")
            or os.environ.get("PPT_MODEL_BASE_URL")
            or "https://api.anthropic.com"
        ).strip()
        timeout = int(payload.get("modelTimeoutSec", os.environ.get("PPT_MODEL_TIMEOUT_SEC", 90)))
        content = _call_anthropic(api_key=api_key, model=model, prompt=prompt, base_url=base_url, timeout=timeout)
    elif provider in {"openai", "codex"}:
        model = (
            payload.get("modelName")
            or os.environ.get("PPT_MODEL_NAME")
            or "gpt-4.1"
        ).strip()
        api_key = payload.get("modelApiKey") or os.environ.get("PPT_MODEL_API_KEY", "")
        if not api_key:
            raise RuntimeError("missing model api key (modelApiKey or PPT_MODEL_API_KEY)")
        base_url = (
            payload.get("modelBaseUrl")
            or os.environ.get("PPT_MODEL_BASE_URL")
            or "https://api.openai.com"
        ).strip()
        timeout = int(payload.get("modelTimeoutSec", os.environ.get("PPT_MODEL_TIMEOUT_SEC", 90)))
        content = _call_openai_chat(api_key=api_key, model=model, prompt=prompt, base_url=base_url, timeout=timeout)
    else:
        raise RuntimeError(f"unsupported model provider: {provider}")

    parsed = _json_from_model_text(content)
    slides = parsed.get("slides", []) if isinstance(parsed, dict) else []
    title = parsed.get("title", "") if isinstance(parsed, dict) else ""
    theme = parsed.get("theme", "") if isinstance(parsed, dict) else ""

    normalized_slides = []
    for item in slides:
        if not isinstance(item, dict):
            continue
        st = _strip_md(str(item.get("title", "") or "未命名页面"))
        layout = item.get("layout", "bullets")
        body = item.get("body", [])

        # 结构化 body（dict）直接保留，供 _render_layout 使用
        if isinstance(body, dict):
            pass  # 保持原样，如 {"items": [...]}, {"left": [...], "right": [...]}
        elif isinstance(body, str):
            body = [_strip_md(body)]
        elif isinstance(body, list):
            body = [_strip_md(str(x)) for x in body if str(x).strip()]
        else:
            body = []

        # 仅对 list 类型的 body 做截断和兜底
        if isinstance(body, list):
            body = body[:8] if body else ["（模型未返回要点）"]

        normalized_slides.append({"title": st or "未命名页面", "layout": layout, "body": body})

    if not normalized_slides:
        raise RuntimeError("model returned no valid slides")

    return {
        "provider": provider,
        "model": model,
        "title": _strip_md(title) or "模型生成汇报",
        "theme": normalize_theme(theme) if theme else "",
        "slides": normalized_slides,
    }


def _render_layout(layout: str, title: str, slide_title: str, body, deck_title: str) -> str:
    """根据布局类型渲染 HTML 内容"""

    if layout == "cover":
        # 封面页
        subtitle = body.get("subtitle", "") if isinstance(body, dict) else ""
        author = body.get("author", "") if isinstance(body, dict) else ""
        return f"""
    <h1 class="h1 anim-fade-up">{html.escape(slide_title)}</h1>
    {f'<p class="lede">{html.escape(subtitle)}</p>' if subtitle else ''}
    {f'<p class="dim mt-m">{html.escape(author)}</p>' if author else ''}"""

    elif layout == "bullets":
        # 要点列表
        items = body.get("items", []) if isinstance(body, dict) else (body if isinstance(body, list) else [])
        items_html = "".join(f"<li>{html.escape(str(item))}</li>" for item in items)
        return f"""
    <p class="kicker">{html.escape(deck_title)}</p>
    <h2 class="h2">{html.escape(slide_title)}</h2>
    <ul class="list mt-m">{items_html}</ul>"""

    elif layout == "two-column":
        # 左右两栏
        if isinstance(body, dict):
            left = body.get("left", [])
            right = body.get("right", [])
        else:
            left, right = [], []
        left_html = "".join(f"<li>{html.escape(str(item))}</li>" for item in left)
        right_html = "".join(f"<li>{html.escape(str(item))}</li>" for item in right)
        return f"""
    <p class="kicker">{html.escape(deck_title)}</p>
    <h2 class="h2">{html.escape(slide_title)}</h2>
    <div class="grid g2 mt-m">
      <div class="card"><ul class="list">{left_html}</ul></div>
      <div class="card"><ul class="list">{right_html}</ul></div>
    </div>"""

    elif layout == "three-column":
        # 三栏
        if isinstance(body, dict):
            col1 = body.get("col1", [])
            col2 = body.get("col2", [])
            col3 = body.get("col3", [])
        else:
            col1, col2, col3 = [], [], []
        col1_html = "".join(f"<li>{html.escape(str(item))}</li>" for item in col1)
        col2_html = "".join(f"<li>{html.escape(str(item))}</li>" for item in col2)
        col3_html = "".join(f"<li>{html.escape(str(item))}</li>" for item in col3)
        return f"""
    <p class="kicker">{html.escape(deck_title)}</p>
    <h2 class="h2">{html.escape(slide_title)}</h2>
    <div class="grid g3 mt-m">
      <div class="card"><ul class="list">{col1_html}</ul></div>
      <div class="card"><ul class="list">{col2_html}</ul></div>
      <div class="card"><ul class="list">{col3_html}</ul></div>
    </div>"""

    elif layout == "stat-highlight":
        # 关键数字
        number = body.get("number", "") if isinstance(body, dict) else ""
        subtitle = body.get("subtitle", "") if isinstance(body, dict) else ""
        return f"""
    <div class="center">
      <p class="kicker">{html.escape(deck_title)}</p>
      <div style="font-size:180px;font-weight:900;line-height:1" class="gradient-text">{html.escape(number)}</div>
      <h3 class="mt-m">{html.escape(subtitle)}</h3>
    </div>"""

    elif layout == "kpi-grid":
        # KPI 网格
        metrics = body.get("metrics", []) if isinstance(body, dict) else []
        cards_html = ""
        for metric in metrics:
            label = metric.get("label", "") if isinstance(metric, dict) else ""
            value = metric.get("value", "") if isinstance(metric, dict) else ""
            cards_html += f'<div class="card tc"><div class="h2 gradient-text">{html.escape(str(value))}</div><p class="dim">{html.escape(str(label))}</p></div>'
        return f"""
    <p class="kicker">{html.escape(deck_title)}</p>
    <h2 class="h2">{html.escape(slide_title)}</h2>
    <div class="grid g2 mt-m">{cards_html}</div>"""

    elif layout == "big-quote":
        # 引用
        quote = body.get("quote", "") if isinstance(body, dict) else str(body)
        author = body.get("author", "") if isinstance(body, dict) else ""
        return f"""
    <div class="center">
      <h2 class="h2" style="font-size:48px;line-height:1.4">"{html.escape(quote)}"</h2>
      {f'<p class="dim mt-m">— {html.escape(author)}</p>' if author else ''}
    </div>"""

    elif layout == "comparison":
        # 对比表格
        headers = body.get("headers", []) if isinstance(body, dict) else []
        rows = body.get("rows", []) if isinstance(body, dict) else []
        table_html = "<table style='width:100%;border-collapse:collapse'><thead><tr>"
        for h in headers:
            table_html += f"<th style='padding:12px;border-bottom:2px solid var(--border-strong);text-align:left'>{html.escape(str(h))}</th>"
        table_html += "</tr></thead><tbody>"
        for row in rows:
            table_html += "<tr>"
            for cell in row:
                table_html += f"<td style='padding:12px;border-bottom:1px solid var(--border)'>{html.escape(str(cell))}</td>"
            table_html += "</tr>"
        table_html += "</tbody></table>"
        return f"""
    <p class="kicker">{html.escape(deck_title)}</p>
    <h2 class="h2">{html.escape(slide_title)}</h2>
    <div class="mt-m">{table_html}</div>"""

    elif layout == "timeline":
        # 时间线
        events = body.get("events", []) if isinstance(body, dict) else []
        timeline_html = ""
        for event in events:
            year = event.get("year", "") if isinstance(event, dict) else ""
            desc = event.get("event", "") if isinstance(event, dict) else ""
            timeline_html += f'<div class="card"><h4>{html.escape(str(year))}</h4><p class="dim">{html.escape(str(desc))}</p></div>'
        return f"""
    <p class="kicker">{html.escape(deck_title)}</p>
    <h2 class="h2">{html.escape(slide_title)}</h2>
    <div class="stack mt-m">{timeline_html}</div>"""

    elif layout == "code":
        # 代码展示
        language = body.get("language", "python") if isinstance(body, dict) else "python"
        code = body.get("code", "") if isinstance(body, dict) else ""
        return f"""
    <p class="kicker">{html.escape(deck_title)}</p>
    <h2 class="h2">{html.escape(slide_title)}</h2>
    <pre class="mt-m" style="background:var(--surface-2);padding:20px;border-radius:var(--radius);overflow:auto"><code class="language-{html.escape(language)}">{html.escape(code)}</code></pre>"""

    elif layout == "section-divider":
        # 章节分隔
        subtitle = body.get("subtitle", "") if isinstance(body, dict) else ""
        return f"""
    <div class="center">
      <div class="divider-accent mb-m"></div>
      <h1 class="h1">{html.escape(slide_title)}</h1>
      {f'<p class="lede">{html.escape(subtitle)}</p>' if subtitle else ''}
    </div>"""

    elif layout == "thanks":
        # 感谢页
        contact = body.get("contact", "") if isinstance(body, dict) else ""
        return f"""
    <div class="center tc">
      <h1 class="h1 gradient-text" style="font-size:160px">Thanks</h1>
      {f'<p class="lede">{html.escape(contact)}</p>' if contact else ''}
    </div>"""

    else:
        # 默认回退到 bullets 布局
        items = body if isinstance(body, list) else [str(body)]
        items_html = "".join(f"<li>{html.escape(str(item))}</li>" for item in items)
        return f"""
    <p class="kicker">{html.escape(deck_title)}</p>
    <h2 class="h2">{html.escape(slide_title)}</h2>
    <ul class="list mt-m">{items_html}</ul>"""


def build_html(title: str, theme: str, slides: list[dict]) -> str:
    sections = []
    total = max(1, len(slides))

    for index, slide in enumerate(slides, start=1):
        slide_title = str(slide.get("title", f"Slide {index}"))
        layout = slide.get("layout", "bullets")
        body = slide.get("body", "")

        # 渲染布局内容
        content_html = _render_layout(layout, title, slide_title, body, title)

        sections.append(
            f"""
  <section class="slide" data-title="{html.escape(slide_title)}">
    {content_html}
    <div class="deck-footer"><span class="dim2">html-ppt-skill service</span><span class="slide-number" data-current="{index}" data-total="{total}"></span></div>
  </section>
"""
        )

    return f"""<!DOCTYPE html>
<html lang="zh-CN" data-theme="{theme}">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title>
<link rel="stylesheet" href="../../../assets/fonts.css">
<link rel="stylesheet" href="../../../assets/base.css">
<link rel="stylesheet" id="theme-link" href="../../../assets/themes/{theme}.css">
<link rel="stylesheet" href="../../../assets/animations/animations.css">
</head>
<body data-themes="{theme}" data-theme-base="../../../assets/themes/">
<div class="deck">
{''.join(sections)}
</div>
<script src="../../../assets/runtime.js"></script>
</body>
</html>
"""


def render_pngs(html_path: Path, slide_count: int):
    chrome = find_chrome()
    if not chrome:
        return []

    png_files = []
    for index in range(1, slide_count + 1):
        target = html_path.parent / f"{index}.png"
        url = f"file:///{html_path.as_posix()}#/{index}"
        cmd = [
            chrome,
            "--headless=new",
            "--disable-gpu",
            "--hide-scrollbars",
            "--no-sandbox",
            "--virtual-time-budget=4000",
            "--window-size=1600,900",
            f"--screenshot={target}",
            url,
        ]
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        png_files.append(str(target))
    return png_files


def create_deck(payload: dict):
    deck_name = safe_name(payload.get("deckName", "service-deck"))
    theme = normalize_theme(payload.get("theme", "minimal-white"))
    title = payload.get("title", "服务生成示例")
    slides = payload.get("slides", [])
    model_meta = {}

    model_driven = _truthy(payload.get("modelDriven", False))
    if model_driven:
        generated = _generate_slides_with_model(payload)
        title = generated["title"]
        slides = generated["slides"]
        # 优先使用用户指定的主题，不使用模型返回的主题
        # if generated.get("theme"):
        #     theme = generated["theme"]
        model_meta = {
            "provider": generated["provider"],
            "model": generated["model"],
        }
    else:
        if not slides and payload.get("pptInput"):
            title, slides = _slides_from_ppt_input(payload["pptInput"])
        if not slides:
            title, slides = _slides_from_ppt_input(payload)
        if not slides:
            slides = [{"title": "封面", "body": "这是通过 html-ppt-skill 服务接口生成的示例。"}]

    out_dir = OUTPUT_ROOT / deck_name
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    html = build_html(title, theme, slides)
    html_path = out_dir / "index.html"
    html_path.write_text(html, encoding="utf-8")

    render_thumbnails = bool(payload.get("renderThumbnails", False))
    pngs = []
    if render_thumbnails:
        try:
            pngs = render_pngs(html_path, len(slides))
        except Exception:
            pngs = []

    return {
        "deckName": deck_name,
        "html": str(html_path),
        "htmlUrl": f"/output/{deck_name}/index.html",
        "slideCount": len(slides),
        "theme": theme,
        "modelDriven": model_driven,
        "modelMeta": model_meta,
        "renderThumbnails": render_thumbnails,
        "thumbnails": pngs,
    }


class Handler(BaseHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        super().end_headers()

    def _json(self, status: int, body: dict):
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _serve_file(self, file_path: Path):
        if not file_path.exists() or not file_path.is_file():
            self._json(404, {"ok": False, "error": "file not found"})
            return
        try:
            data = file_path.read_bytes()
            ctype, _ = mimetypes.guess_type(str(file_path))
            self.send_response(200)
            self.send_header("Content-Type", ctype or "application/octet-stream")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except Exception as exc:
            self._json(500, {"ok": False, "error": str(exc)})

    def do_OPTIONS(self):
        self.send_response(204)
        self.end_headers()

    def do_GET(self):
        path = unquote(urlparse(self.path).path or "/")
        if path in ["/health", "/healthz"]:
            self._json(200, {"ok": True, "service": "html-ppt-skill"})
            return
        if path.startswith("/output/"):
            tail = path[len("/output/") :]
            file_path = (OUTPUT_ROOT / tail).resolve()
            if OUTPUT_ROOT.resolve() not in file_path.parents and file_path != OUTPUT_ROOT.resolve():
                self._json(403, {"ok": False, "error": "forbidden"})
                return
            self._serve_file(file_path)
            return
        if path.startswith("/assets/"):
            tail = path[len("/assets/") :]
            assets_root = (ROOT / "assets").resolve()
            file_path = (assets_root / tail).resolve()
            if assets_root not in file_path.parents and file_path != assets_root:
                self._json(403, {"ok": False, "error": "forbidden"})
                return
            self._serve_file(file_path)
            return
        self._json(404, {"ok": False, "error": "not found"})

    def do_POST(self):
        if urlparse(self.path).path != "/api/ppt/generate":
            self._json(404, {"error": "not found"})
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(size) or b"{}")
            result = create_deck(payload)
            self._json(200, {"ok": True, "result": result})
        except Exception as exc:
            self._json(500, {"ok": False, "error": str(exc)})


def main():
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    host = os.environ.get("PPT_SERVICE_HOST", "127.0.0.1")
    port = int(os.environ.get("PPT_SERVICE_PORT", "18765"))
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"ppt service listening on http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
