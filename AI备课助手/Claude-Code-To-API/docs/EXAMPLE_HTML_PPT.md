# 实例：html-ppt-skill 封装为 PPT 生成 API

> 本文档记录将 `html-ppt-skill`（HTML 演示文稿生成 skill）封装为 REST API 的完整过程，作为 [SKILL.md](./SKILL.md) 的具体实例。

## 背景

### 目标

将 html-ppt-skill 封装为 HTTP API，使外部系统可以通过一次 POST 请求生成完整的 HTML 课件。

### Skill 概况

| 项目 | 内容 |
|------|------|
| 位置 | `/personal/AI备课助手/html-ppt-skill/` |
| 功能 | 根据文本内容生成多页 HTML 演示文稿 |
| 配套服务 | `tools/ppt_service.py`（端口 18765） |
| 资源文件 | `assets/` 下有 base.css、fonts.css、36 个主题 CSS、动画 CSS |
| LLM 调用 | 配套服务支持 `modelDriven` 模式，调用 OpenAI 兼容接口生成内容 |
| 输出 | 自包含的 HTML 文件 |

---

## Step 1: 分析 Skill 结构

### 1.1 读取 SKILL.md

确认 skill 的输入输出契约：

- **输入**：用户描述的演示主题、内容大纲、风格偏好
- **输出**：`<section class="slide">` 结构的 HTML 文件
- **约束**：支持 36 种主题，8-12 页，中英文

### 1.2 检查配套服务

读取 `tools/ppt_service.py` 发现：

```
POST /api/ppt/generate  →  主生成接口
GET  /health             →  健康检查
GET  /output/<deck>/...  →  静态文件服务
GET  /assets/...         →  CSS/JS 资源服务
```

关键发现：服务支持 `modelDriven: true` 模式，需要 `modelBaseUrl` 和 `modelApiKey` 参数来回调 LLM。

### 1.3 确认资源文件

```
assets/
├── fonts.css                    # Google Fonts 导入
├── base.css                     # 重置 + 令牌定义 + 布局系统
├── runtime.js                   # 键盘导航（多页模式需要）
├── themes/                      # 36 个主题 CSS
│   ├── aurora.css
│   ├── tokyo-night.css
│   └── ... (34 more)
└── animations/
    └── animations.css           # 27 种动画
```

### 1.4 识别问题

配套服务生成的 HTML 使用**相对路径**引用 CSS：

```html
<link rel="stylesheet" href="../../../assets/base.css">
```

这意味着通过 API 返回的 HTML 在其他服务器上打开时，CSS 无法加载。**必须将 CSS 内联到 HTML 中**。

---

## Step 2: 启动配套服务

```bash
python /personal/AI备课助手/html-ppt-skill/tools/ppt_service.py &
# 输出: html-ppt-skill service running on http://127.0.0.1:18765

# 验证
curl http://127.0.0.1:18765/health
# {"ok": true, "service": "html-ppt-skill"}
```

---

## Step 3: 设计接口

### 3.1 请求模型

设计用户友好的接口，不暴露 skill 内部细节：

```python
class PPTGenerateV2Request(BaseModel):
    config: dict = Field(..., description="配置信息")
    content: str = Field(..., description="任意文本内容")
```

`config` 字段包含：
- `outputLanguage`：输出语言（默认"中文"）
- `pptStyle`：风格名称（中文，如"极光渐变"）
- `pageMin` / `pageMax`：页数范围

### 3.2 响应模型

```python
class PPTGenerateV2Response(BaseModel):
    ok: bool
    html: Optional[str] = None       # 完整 HTML 内容
    slideCount: Optional[int] = None
    theme: Optional[str] = None
    error: Optional[str] = None
```

### 3.3 风格映射

用户传中文风格名，需要映射到 skill 的内部主题 ID：

```python
STYLE_THEME_MAP = {
    "学术简约": "academic-paper",
    "技术分享": "tokyo-night",
    "极光渐变": "aurora",
    "小红书风": "xiaohongshu-white",
    "赛博朋克": "cyberpunk-neon",
    # ... 共 37 条映射
}

def get_theme_from_style(style: str) -> str:
    return STYLE_THEME_MAP.get(style, "minimal-white")
```

---

## Step 4: 实现路由 — ppt_v2.py

### 4.1 核心流程

创建 `src/api/routes/ppt_v2.py`：

```
用户请求
  ↓
解析 config（语言、风格、页数）
  ↓
风格映射：中文名 → 主题 ID
  ↓
构建配套服务 payload
  ↓ httpx.AsyncClient(timeout=180)
调用 ppt_service POST /api/ppt/generate
  ↓
配套服务内部：LLM 生成 slides → 渲染 HTML → 保存文件
  ↓
读取生成的 HTML 文件内容
  ↓
返回完整 HTML
```

### 4.2 关键代码 — 参数转换

将用户友好的请求转换为配套服务格式：

```python
payload = {
    "deckName": f"v2-{int(time.time())}",
    "theme": theme,                        # 映射后的主题 ID
    "renderThumbnails": False,
    "modelDriven": True,                   # 启用 LLM 驱动
    "modelProvider": "openai",             # 使用 OpenAI 兼容格式
    "injectSkillPrompt": True,             # 注入 SKILL.md 到 prompt
    "pageMin": page_min,
    "pageMax": page_max,
    "pptInput": {
        "content": request.content,
        "outputLanguage": output_language,
        "instructions": f"将以下内容转换为 {page_min}-{page_max} 页的 {ppt_style} 风格课件"
    },
    # ⚠️ 关键：LLM 回调本服务
    "modelBaseUrl": "http://127.0.0.1:9000",
    "modelApiKey": "sk-demo-key-replace-this"
}
```

`modelBaseUrl` 指向本服务，形成闭环：

```
API (9000) → ppt_service (18765) → API (9000) → Claude CLI
```

### 4.3 关键代码 — 读取生成结果

配套服务返回的是文件路径，需要再次请求读取内容：

```python
# 第一次请求：生成
resp = await client.post(f"{PPT_SERVICE_BASE}/api/ppt/generate", json=payload)
data = resp.json()
html_url = data["result"]["htmlUrl"]  # 如 "/output/v2-1717300000/index.html"

# 第二次请求：读取 HTML 文件
html_resp = await client.get(f"{PPT_SERVICE_BASE}{html_url}")
html_content = html_resp.text

return PPTGenerateV2Response(ok=True, html=html_content, ...)
```

---

## Step 5: 实现路由 — ppt_split.py（拆分版本）

### 5.1 为什么需要拆分

前端需要按页展示课件，要求每一页是独立的、可单独打开的 HTML 文件。

### 5.2 核心流程

```
生成完整 HTML（同 v2）
  ↓
正则提取每个 <section class="slide"> 块
  ↓
为每页构建独立 HTML（CSS 内联 + 可见性修复）
  ↓
返回 pages 数组
```

### 5.3 CSS 内联

从 skill 的 assets 目录直接读取 CSS 文件并合并：

```python
HTML_PPT_ASSETS = Path("/personal/AI备课助手/html-ppt-skill/assets")

def load_css_resources(theme: str) -> str:
    css_parts = []
    for css_file in [
        "fonts.css",
        "base.css",
        f"themes/{theme}.css",
        "animations/animations.css"
    ]:
        path = HTML_PPT_ASSETS / css_file
        if path.exists():
            css_parts.append(path.read_text(encoding="utf-8"))
    return "\n\n".join(css_parts)
```

### 5.4 可见性修复 — 踩坑记录

**问题**：拆分后的单页 HTML 打开只显示背景色，内容不可见。

**根因分析**：base.css 中 `.slide` 默认 `opacity: 0`，依赖 JavaScript（runtime.js）添加 `.is-active` 类来显示。单页模式没有 runtime.js，所以内容永远不可见。

**解决方案**：三层修复机制：

```python
def build_single_page_html(title, theme, page_num, total_pages, slide_content, deck_title):
    inline_css = load_css_resources(theme)
    
    return f"""<!DOCTYPE html>
<html lang="zh-CN" data-theme="{theme}">
<head>
<meta charset="utf-8">
<title>{title}</title>
<style>
{inline_css}

/* 修复层1：CSS 强制覆盖 */
.slide {{
  opacity: 1 !important;
  pointer-events: auto !important;
  transform: none !important;
  position: absolute;
  inset: 0;
}}
</style>
</head>
<!-- 修复层2：触发 base.css 的 body.single 规则 -->
<body class="single">
<div class="deck">
  <!-- 修复层3：手动添加 is-active 类 -->
  <section class="slide is-active" data-title="{title}">
    {slide_content}
  </section>
</div>
</body>
</html>"""
```

三层修复的作用：

| 层级 | 机制 | 触发的 CSS 规则 |
|------|------|----------------|
| `<body class="single">` | 触发 base.css 单页模式 | `body.single .slide { position: relative; opacity: 1; }` |
| `class="slide is-active"` | 模拟 runtime.js 的行为 | `.slide.is-active { opacity: 1; pointer-events: auto; }` |
| `opacity: 1 !important` | 兜底强制覆盖 | 确保任何情况下内容可见 |

### 5.5 Slide 提取

用正则从完整 HTML 中提取每个 slide：

```python
def extract_slides_from_html(html_content: str) -> list:
    pattern = r'<section class="slide"[^>]*?data-title="([^"]*)"[^>]*?>(.*?)</section>'
    matches = re.findall(pattern, html_content, re.DOTALL)
    return [(idx, title, content) for idx, (title, content) in enumerate(matches, start=1)]
```

---

## Step 6: 注册路由

编辑 `src/api/main.py`：

```python
def create_app() -> FastAPI:
    app = FastAPI(...)
    
    # ... 现有路由 ...
    
    # 添加 PPT v2 路由
    from .routes.ppt_v2 import router as ppt_v2_router
    app.include_router(ppt_v2_router, prefix="/v1")
    
    # 添加 PPT 拆分路由
    from .routes.ppt_split import router as ppt_split_router
    app.include_router(ppt_split_router, prefix="/v1")
    
    return app
```

---

## Step 7: 编写 API 文档

创建 `docs/PPT_API.md`，包含：
- 接口地址和鉴权方式
- 完整的请求/响应 JSON 示例
- 37 种风格列表
- cURL / Python / JavaScript 调用示例
- 超时和代理配置说明

---

## Step 8: 测试

### 8.1 发送测试请求

```bash
curl --noproxy "*" \
  -X POST http://10.5.54.232:9000/v1/ppt/generate \
  -H "Authorization: Bearer sk-demo-key-replace-this" \
  -H "Content-Type: application/json" \
  -d '{
    "config": {
      "outputLanguage": "中文",
      "pptStyle": "极光渐变",
      "pageMin": 4,
      "pageMax": 6
    },
    "content": "Python异步编程入门：协程基础、async/await语法、asyncio事件循环、并发模式对比"
  }'
```

### 8.2 验证响应

```json
{
  "ok": true,
  "html": "<!DOCTYPE html>\n<html lang=\"zh-CN\" data-theme=\"aurora\">...",
  "slideCount": 5,
  "theme": "aurora"
}
```

### 8.3 验证 HTML 可打开

将返回的 `html` 字段保存为 `.html` 文件，在浏览器中打开，确认：
- [x] 背景渐变正常显示（aurora 主题的极光效果）
- [x] 文字内容可见
- [x] 键盘 ← → 可翻页（完整版）
- [x] 独立打开无需额外资源（CSS 已内联）

### 8.4 测试拆分接口

```bash
curl --noproxy "*" \
  -X POST http://10.5.54.232:9000/v1/ppt/generate-split \
  -H "Authorization: Bearer sk-demo-key-replace-this" \
  -H "Content-Type: application/json" \
  -d '{
    "config": {
      "outputLanguage": "中文",
      "pptStyle": "极光渐变",
      "pageMin": 4,
      "pageMax": 6
    },
    "content": "牛顿第一定律：惯性概念、实验基础、应用场景"
  }'
```

验证拆分响应：

```json
{
  "ok": true,
  "slideCount": 4,
  "theme": "aurora",
  "pages": [
    {
      "page": 1,
      "title": "牛顿第一定律",
      "html": "<!DOCTYPE html>..."
    },
    {
      "page": 2,
      "title": "惯性概念",
      "html": "<!DOCTYPE html>..."
    }
  ]
}
```

每个 page 的 html 独立打开均可正常显示内容。

---

## 踩坑总结

### 坑 1: CSS 资源路径

**现象**：API 返回的 HTML 在其他服务器打开时无样式。

**原因**：配套服务生成的 HTML 用相对路径引用 CSS（`../../../assets/base.css`），脱离服务器目录结构后路径失效。

**解决**：在路由层读取 CSS 文件并内联到 `<style>` 标签中。

### 坑 2: Slide 不可见

**现象**：单页 HTML 只显示背景，不显示文字内容。

**原因**：base.css 的 slide 系统设计为多页模式，默认 `opacity: 0`，需要 runtime.js 激活。

**解决**：三层修复（body.single + is-active + opacity !important）。

### 坑 3: aiosqlite 依赖缺失

**现象**：启动服务报 `ModuleNotFoundError: No module named 'aiosqlite'`。

**原因**：会话管理使用 SQLite 异步驱动，但 requirements.txt 中未包含。

**解决**：`pip install aiosqlite` 并更新 requirements.txt。

### 坑 4: 超时不足

**现象**：复杂内容生成时请求超时。

**原因**：LLM 生成 + HTML 渲染耗时可达 2-3 分钟。

**解决**：`httpx.AsyncClient(timeout=180.0)` 设置 3 分钟超时。

### 坑 5: 代理干扰

**现象**：服务间调用失败。

**原因**：服务器配置了 Privoxy 代理，`127.0.0.1` 的请求也被代理拦截。

**解决**：文档中标注必须禁用代理（`--noproxy "*"` / `proxies={"http": None}`）。

---

## 最终文件清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `src/api/routes/ppt_v2.py` | 新建 | v2 接口：自由文本输入，返回完整 HTML |
| `src/api/routes/ppt_split.py` | 新建 | 拆分接口：返回每页独立 HTML |
| `src/api/main.py` | 修改 | 注册两个新路由 |
| `docs/PPT_API.md` | 新建 | API 接口文档 |

---

## 调用链路全景

```
外部系统
  │
  │ POST /v1/ppt/generate
  │ { config: { pptStyle: "极光渐变", pageMin: 4 }, content: "..." }
  ▼
┌─────────────────────────────────────────────────┐
│  FastAPI (端口 9000)                              │
│  ppt_v2.py                                       │
│    1. 风格映射: "极光渐变" → "aurora"              │
│    2. 构建 payload (modelBaseUrl 指回自己)          │
│    3. httpx.post → ppt_service                   │
└──────────────────────┬──────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────┐
│  ppt_service (端口 18765)                         │
│    1. 收到 modelDriven=true                       │
│    2. 读取 SKILL.md 注入 prompt                    │
│    3. 调用 modelBaseUrl/v1/chat/completions       │
│       → 回到 FastAPI → Claude CLI                 │
│    4. 解析 LLM 返回的 JSON slides                  │
│    5. build_html() 生成 index.html                │
│    6. 返回 { ok: true, result: { htmlUrl: "..." }} │
└──────────────────────┬──────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────┐
│  FastAPI (端口 9000)                              │
│  ppt_v2.py                                       │
│    4. 读取生成的 HTML 文件内容                      │
│    5. 返回 { ok: true, html: "<!DOCTYPE..." }     │
└─────────────────────────────────────────────────┘
```

拆分版本在此基础上增加后处理：

```
完整 HTML
  ↓ 正则提取 <section class="slide">
  ↓ 读取 assets/ 下的 CSS 文件
  ↓ 为每页组装独立 HTML（CSS 内联 + 可见性修复）
  ↓ 返回 pages 数组
```
