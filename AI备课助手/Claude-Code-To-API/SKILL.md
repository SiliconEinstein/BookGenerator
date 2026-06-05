# Skill 封装为 API 服务 — 操作指南

> 本文档面向 agent：按照以下步骤，可以将任意 Claude Code skill 封装为标准 HTTP API。

## 前置条件

| 条件 | 验证方式 |
|------|---------|
| Claude Code CLI 已安装 | `claude --version` |
| Claude-Code-To-API 项目可运行 | `cd /personal/AI备课助手/Claude-Code-To-API && python -m src.cli.server --help` |
| Python 3.12+ | `python3 --version` |
| 目标 skill 已存在且可用 | 目标目录下有 `SKILL.md` 文件 |

## 总体架构

```
外部系统 (Dify / CherryStudio / 自定义前端)
  ↓ HTTP POST (OpenAI 格式)
Claude-Code-To-API (FastAPI, 端口 9000)
  ├─ /v1/chat/completions  →  Claude CLI 子进程（通用对话）
  └─ /v1/<skill-endpoint>  →  Skill 配套服务（专用功能）
                                  ↓ LLM 调用回环
                              本服务 /v1/chat/completions → Claude CLI
```

核心设计：**配套服务调用 LLM 时，回调本服务的 `/v1/chat/completions`，由本服务统一调度 Claude CLI**。这确保所有 LLM 调用都走同一条认证和会话管理链路。

## 两种封装模式

### 模式 A：透明代理（skill 有独立配套服务）

适用于：skill 自带 HTTP 服务，API 层只做参数转换和代理。

```
用户请求 → FastAPI 路由 → httpx 代理 → Skill 配套服务
                                           ↓ 生成结果
                                        读取结果 → 返回
```

**典型场景**：html-ppt-skill（配套服务 ppt_service.py 端口 18765）

### 模式 B：直接调用（skill 无独立服务）

适用于：skill 只是 prompt 模板，不需要额外服务。

```
用户请求 → FastAPI 路由 → ClaudeService → Claude CLI（加载 skill）→ 返回
```

**典型场景**：文档生成 skill、翻译 skill 等纯 prompt 类 skill

## 实施步骤

### Step 1: 分析目标 skill

读取 skill 目录，确认以下信息：

```
# 必须确认的信息
1. SKILL.md 位置和内容  → 确定 skill 的输入/输出契约
2. 是否有配套服务       → 检查 tools/ 目录下是否有 *service*.py
3. 配套服务端口         → 读取服务代码中的端口定义
4. 资源文件位置         → assets/ 目录结构（CSS/JS/模板等）
5. LLM 调用方式        → 服务是否需要回调 OpenAI 兼容接口
```

### Step 2: 启动配套服务（模式 A）

如果 skill 有配套服务：

```bash
# 启动配套服务
python /path/to/skill/tools/service.py &

# 验证服务可用
curl http://127.0.0.1:<port>/health
```

### Step 3: 创建路由文件

在 `src/api/routes/` 下创建 `<skill_name>.py`：

```python
"""
<Skill Name> API
"""

import logging
from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
import httpx

logger = logging.getLogger(__name__)
router = APIRouter(tags=["<skill-name>"])

SERVICE_BASE = "http://127.0.0.1:<port>"


# ── 请求/响应模型 ──

class SkillRequest(BaseModel):
    """请求模型：字段来自 skill 的输入契约"""
    config: dict = Field(..., description="配置参数")
    content: str = Field(..., description="输入内容")


class SkillResponse(BaseModel):
    """响应模型：统一格式"""
    ok: bool
    result: Optional[dict] = None
    error: Optional[str] = None


# ── 参数映射 ──

def build_service_payload(request: SkillRequest) -> dict:
    """将 API 请求转换为配套服务格式"""
    return {
        # 配套服务期望的字段
        "key": request.content,
        # LLM 回调配置（关键！）
        "modelDriven": True,
        "modelProvider": "openai",
        "modelBaseUrl": "http://127.0.0.1:9000",  # 回调本服务
        "modelApiKey": "sk-demo-key-replace-this"
    }


# ── 路由 ──

@router.post("/<skill>/generate", response_model=SkillResponse)
async def generate(request: SkillRequest):
    """调用 skill 生成内容"""
    try:
        payload = build_service_payload(request)

        logger.info(f"Skill invocation: {request.config}")

        async with httpx.AsyncClient(timeout=180.0) as client:
            resp = await client.post(
                f"{SERVICE_BASE}/api/<skill>/generate",
                json=payload
            )

        if resp.status_code != 200:
            logger.error(f"Service error: {resp.status_code}: {resp.text}")
            return SkillResponse(ok=False, error=resp.text)

        data = resp.json()
        if not data.get("ok"):
            return SkillResponse(ok=False, error=data.get("error"))

        # 如果需要读取生成的文件内容
        result = data["result"]
        file_url = result.get("htmlUrl", "")
        if file_url:
            async with httpx.AsyncClient(timeout=10.0) as client:
                file_resp = await client.get(f"{SERVICE_BASE}{file_url}")
            if file_resp.status_code == 200:
                result["fileContent"] = file_resp.text

        return SkillResponse(ok=True, result=result)

    except httpx.ConnectError:
        raise HTTPException(503, detail="配套服务未启动")
    except Exception as e:
        logger.error(f"Skill failed: {e}", exc_info=True)
        raise HTTPException(500, detail=str(e))
```

### Step 4: 注册路由

编辑 `src/api/main.py`，在 `create_app()` 函数中添加：

```python
# 在现有路由注册之后添加
from .routes.<skill_name> import router as <skill_name>_router
app.include_router(<skill_name>_router, prefix="/v1")
```

### Step 5: 处理资源内联（如需要）

如果 skill 生成的文件引用了外部资源（CSS/JS），需要将其内联：

```python
from pathlib import Path

SKILL_ASSETS = Path("/path/to/skill/assets")

def load_inline_css(theme: str) -> str:
    """读取并合并 CSS 文件"""
    parts = []
    for css_file in ["fonts.css", "base.css", f"themes/{theme}.css"]:
        path = SKILL_ASSETS / css_file
        if path.exists():
            parts.append(path.read_text(encoding="utf-8"))
    return "\n\n".join(parts)
```

**为什么需要内联**：配套服务通常通过相对路径引用资源文件，但 API 返回的 HTML 在其他服务器打开时无法访问这些相对路径。内联所有 CSS/JS 可确保生成的文件完全自包含。

### Step 6: 处理单页拆分（如需要）

如果 skill 生成多页内容且需要拆分为独立页面：

```python
import re

def extract_pages(html: str) -> list:
    """从完整 HTML 中提取每个页面"""
    pattern = r'<section class="slide"[^>]*?data-title="([^"]*)"[^>]*?>(.*?)</section>'
    return re.findall(pattern, html, re.DOTALL)

def build_single_page(title, content, theme, page_num, total):
    """构建单页独立 HTML（CSS 内联 + 可见性修复）"""
    css = load_inline_css(theme)
    return f'''<!DOCTYPE html>
<html lang="zh-CN" data-theme="{theme}">
<head>
<meta charset="utf-8">
<title>{title}</title>
<style>
{css}
/* 单页适配：覆盖多页演示的默认隐藏行为 */
.slide {{ opacity: 1 !important; pointer-events: auto !important; transform: none !important; position: absolute; inset: 0; }}
</style>
</head>
<body class="single">
<div class="deck">
  <section class="slide is-active" data-title="{title}">
    {content}
  </section>
</div>
</body>
</html>'''
```

**关键点**：
- `<body class="single">` 触发 base.css 中的单页模式规则
- `class="slide is-active"` 确保 slide 可见
- `opacity: 1 !important` 作为兜底保障

### Step 7: 风格映射表（如适用）

如果 skill 支持多种风格，建立用户友好名称到内部 ID 的映射：

```python
STYLE_MAP = {
    "学术简约": "academic-paper",
    "技术分享": "tokyo-night",
    "极光渐变": "aurora",
    # ... 更多映射
}

def map_style(name: str) -> str:
    return STYLE_MAP.get(name, "minimal-white")

# 提供查询接口
@router.get("/<skill>/styles")
async def list_styles():
    return {"styles": list(STYLE_MAP.keys()), "mapping": STYLE_MAP}
```

### Step 8: 编写 API 文档

在 `docs/` 目录创建 `<SKILL>_API.md`，必须包含：

```markdown
# <Skill> API 文档

## 接口地址
POST http://服务器IP:9000/v1/<skill>/generate

## 鉴权
Authorization: Bearer <api-key>

## 请求参数（JSON）
| 字段 | 类型 | 必填 | 说明 |

## 响应格式（JSON）
成功/失败示例

## 调用示例
cURL / Python / JavaScript 各一份

## 超时设置
建议 180 秒（LLM 生成需要时间）

## 代理配置
如果网络环境有代理，必须禁用
```

### Step 9: 测试验证

```bash
# 1. 启动配套服务
python /path/to/skill/tools/service.py &

# 2. 启动 API 服务
cd /personal/AI备课助手/Claude-Code-To-API
python -m src.cli.server

# 3. 测试接口
curl --noproxy "*" \
  -X POST http://127.0.0.1:9000/v1/<skill>/generate \
  -H "Authorization: Bearer sk-demo-key-replace-this" \
  -H "Content-Type: application/json" \
  -d '{"config": {...}, "content": "..."}'

# 4. 验证返回的 HTML 可在浏览器正常打开
```

## 错误处理规范

| 场景 | HTTP 码 | 处理方式 |
|------|---------|---------|
| 配套服务未启动 | 503 | `httpx.ConnectError` → 明确提示启动服务 |
| 配套服务超时 | 504 | `httpx.TimeoutException` → 建议增加超时 |
| 配套服务返回错误 | 200 | `ok=False` + 透传原始错误信息 |
| API Key 无效 | 401 | 中间件层拦截 |
| 未知错误 | 500 | 记录堆栈 + 返回通用错误 |

## 关键设计约束

1. **参数转换在路由层**：FastAPI 路由负责用户格式 ↔ 服务格式的转换，配套服务不感知 API 层
2. **配套服务保持独立**：可以脱离 FastAPI 单独运行和测试
3. **LLM 调用走回环**：配套服务的 `modelBaseUrl` 指向本服务，确保统一调度
4. **错误信息透传**：保留配套服务的原始错误描述
5. **资源完全内联**：API 返回的文件必须自包含，不依赖外部路径
6. **CSS 可见性修复**：单页 HTML 必须处理多页框架的默认隐藏行为

## 文件清单（每次封装需要创建/修改的文件）

| 操作 | 文件 |
|------|------|
| 新建 | `src/api/routes/<skill_name>.py` — 路由和业务逻辑 |
| 修改 | `src/api/main.py` — 注册路由 |
| 新建 | `docs/<SKILL>_API.md` — API 文档 |
| 可选 | `requirements.txt` — 如需新依赖 |
