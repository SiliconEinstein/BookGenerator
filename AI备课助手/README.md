# AI备课助手

面向教育场景的 AI 备课工具集。本文档重点说明 **HTML 课件生成** 的完整逻辑，使 Agent 读取后能按步骤完整复现。

## 子模块

| 模块 | 职责 |
|------|------|
| [AI备课助手agent](./AI备课助手agent/) | 结构化备课：大纲解析 → 章节生成 → **PPTX** 输出 |
| [Claude-Code-To-API](./Claude-Code-To-API/) | API 网关：将 Claude CLI 封装为 OpenAI 兼容接口，**HTML PPT 生成入口** |
| [html-ppt-skill](./html-ppt-skill/) | HTML 演示文稿 Skill：36 主题、31 布局、静态资源 |

> **HTML 课件走 Claude-Code-To-API + html-ppt-skill 链路，不走 AI备课助手agent。**

---

## HTML 生成：三代接口对比

| 版本 | 路由 | 生成引擎 | 响应格式 | 状态 |
|------|------|----------|----------|------|
| v2 | `POST /v1/ppt/generate` | `ppt_service.py`（端口 18765）+ LLM 回调 | 完整 `html` 字符串 | 可用，需额外启动配套服务 |
| split | `POST /v1/ppt/generate-split` | 同 v2，后处理拆分 | `pages[]` 单页 HTML 数组 | 可用，需额外启动配套服务 |
| **v3（推荐）** | `POST /v1/ppt/generate-v3` | **Claude CLI 直接操作 html-ppt-skill** | `pages[]` 单页 HTML 数组（CSS 内联） | **当前主力方案** |

**v3 的优势**：不依赖 `ppt_service`，由 Claude 自主读取模板、选布局、写文件，布局多样性更好。

---

## v3 生成逻辑（当前主力）

### 端到端流程

```mermaid
sequenceDiagram
    participant Client as 调用方
    participant API as Claude-Code-To-API :9000
    participant Claude as Claude CLI
    participant Skill as html-ppt-skill

    Client->>API: POST /v1/ppt/generate-v3
    API->>API: pptStyle → theme 映射
    API->>API: build_claude_prompt()
    API->>Claude: claude -p "请为以下内容生成..."
    Note over Claude,Skill: working_dir = html-ppt-skill/
    Claude->>Skill: Read templates/deck.html
    Claude->>Skill: Glob templates/single-page/*
    Claude->>Skill: Read 选定的布局文件
    Claude->>Skill: Write output/ppt-v3-latest.html
    Claude-->>API: stream-json 响应
    API->>Skill: 读取 output/ppt-v3-latest.html
    alt slideCount < pageMin
        API->>Claude: 补充页数 prompt
        Claude->>Skill: 覆写 output/ppt-v3-latest.html
    end
    API->>API: 强制修正 data-theme
    API->>API: split_to_pages() + CSS 内联
    API-->>Client: { ok, slideCount, theme, pages[] }
```

### 第 1 步：请求解析与风格映射

入口文件：`Claude-Code-To-API/src/api/routes/ppt_v3.py`

```python
# 从请求 config 提取参数
output_language = config.get("outputLanguage", "中文")
ppt_style       = config.get("pptStyle", "学术简约")   # 用户传中文名
page_min        = config.get("pageMin", 4)
page_max        = config.get("pageMax", 8)

# 中文风格名 → 内部 theme ID（定义在 ppt_v2.py 的 STYLE_THEME_MAP）
theme = get_theme_from_style(ppt_style)
# 例："极光渐变" → "aurora"，"技术分享" → "tokyo-night"
```

完整映射表见 `Claude-Code-To-API/src/api/routes/ppt_v2.py` 中的 `STYLE_THEME_MAP`（37 种）。

### 第 2 步：构建 Claude Prompt

`build_claude_prompt()` 生成一段结构化指令，核心要求：

1. 读取 `templates/deck.html` 作为 deck 骨架
2. 用 `Glob` 列出 `templates/single-page/` 下 31 种布局
3. 根据内容选 2–4 种布局（如 `cover.html`、`bullets.html`、`two-column.html`）
4. 读取选定布局，了解 `<section class="slide">` 结构
5. 组装完整 HTML，**硬性约束**：
   - `<html data-theme="{theme}">`
   - theme CSS 链接：`../assets/themes/{theme}.css`
   - 页数在 `pageMin`–`pageMax` 之间
6. 写入 `output/ppt-v3-latest.html`

### 第 3 步：调用 Claude CLI

```python
process_config = ClaudeProcessConfig(
    working_dir="/personal/AI备课助手/html-ppt-skill",  # ⚠️ 硬编码路径
    timeout=300
)
claude_process = ClaudeProcess(process_config)
await claude_process.start()
async for chunk in claude_process.send_message(prompt):
    full_response += chunk
```

Claude CLI 实际执行的命令（`claude_service.py`）：

```bash
claude \
  --output-format stream-json \
  --verbose \
  --disallowedTools Bash,Edit,BashOutput,KillShell \
  --allowedTools Read,Write,Glob,Grep,Task,Agent,Skill \
  --permission-mode dontAsk \
  --add-dir /personal/AI备课助手/html-ppt-skill \
  -p "<prompt 内容>"
```

Claude 在 `html-ppt-skill/` 目录下拥有 Read/Write/Glob 权限，通过 Skill 机制使用 `html-ppt` 能力。

### 第 4 步：读取生成产物

Claude 写入的文件路径：

```
html-ppt-skill/output/ppt-v3-latest.html
```

若文件不存在，API 会 fallback 到 `output/` 下最新修改的 `.html` 文件。

生成的 deck HTML 结构示例：

```html
<!DOCTYPE html>
<html lang="zh-CN" data-theme="aurora">
<head>
  <link rel="stylesheet" href="../assets/fonts.css">
  <link rel="stylesheet" href="../assets/base.css">
  <link rel="stylesheet" href="../assets/themes/aurora.css">
  <link rel="stylesheet" href="../assets/animations/animations.css">
</head>
<body>
  <div class="deck">
    <section class="slide" data-title="封面">...</section>
    <section class="slide" data-title="要点">...</section>
    <!-- 更多 slide -->
  </div>
  <script src="../assets/runtime.js"></script>
</body>
</html>
```

### 第 5 步：质量兜底

**页数不足时自动补充**：

```python
if slide_count < page_min:
    # 向 Claude 发送补充 prompt，要求增加 slide 并覆写文件
    supplement_prompt = f"当前只有 {slide_count} 页，要求最少 {page_min} 页..."
    async for chunk in claude_process.send_message(supplement_prompt):
        ...
```

**强制修正主题**（防止 Claude 沿用上一轮的错误 theme）：

```python
html_content = re.sub(r'data-theme="[^"]*"', f'data-theme="{theme}"', html_content, count=1)
```

### 第 6 步：按页拆分 + CSS 内联

`split_to_pages()` 将完整 deck 拆为独立单页 HTML，供前端逐页展示。

**提取 slide**：正则匹配 `<section class="slide..." data-title="...">...</section>`

**CSS 内联**（关键！）：从 `html-ppt-skill/assets/` 读取并合并：

```
assets/fonts.css
assets/base.css
assets/themes/{theme}.css
assets/animations/animations.css
```

**单页可见性修复**（三层机制，解决 base.css 中 `.slide { opacity: 0 }` 导致单页空白的问题）：

```css
/* 层1：强制覆盖 */
.slide { opacity: 1 !important; pointer-events: auto !important; ... }
```

```html
<!-- 层2：触发 base.css 的 body.single 规则 -->
<body class="single">
  <!-- 层3：模拟 runtime.js 添加 is-active -->
  <section class="slide is-active" data-title="标题">...</section>
</body>
```

### 第 7 步：返回响应

```json
{
  "ok": true,
  "slideCount": 5,
  "theme": "aurora",
  "pages": [
    {
      "page": 1,
      "title": "封面",
      "html": "<!DOCTYPE html>...(CSS 已内联的完整单页 HTML)"
    },
    {
      "page": 2,
      "title": "牛顿第一定律",
      "html": "..."
    }
  ]
}
```

每页 `html` 字段是**自包含**的：CSS 全部内联在 `<style>` 中，无需外部资源即可在浏览器中正确渲染。

---

## html-ppt-skill 内部结构（Claude 操作的文件）

```text
html-ppt-skill/
├── SKILL.md                    # Skill 说明（Claude 的行为指南）
├── templates/
│   ├── deck.html               # ★ deck 骨架模板（Claude 必读）
│   ├── single-page/            # ★ 31 种单页布局（Claude 选读）
│   │   ├── cover.html          # 封面
│   │   ├── bullets.html        # 要点列表
│   │   ├── two-column.html     # 双栏
│   │   ├── stat-highlight.html # 数据高亮
│   │   ├── thanks.html         # 致谢
│   │   └── ...（共 31 个）
│   └── full-decks/             # 15 套完整 deck 模板（可选参考）
├── assets/
│   ├── fonts.css               # Google Fonts
│   ├── base.css                # 设计令牌 + 布局系统 + .slide 可见性规则
│   ├── runtime.js              # 键盘导航（多页 deck 用）
│   ├── themes/                 # 36 个主题 CSS
│   │   ├── aurora.css
│   │   ├── tokyo-night.css
│   │   └── ...
│   └── animations/
│       └── animations.css      # 27 种 CSS 动画
└── output/
    └── ppt-v3-latest.html      # ★ Claude 写入的目标文件
```

### 单页布局的最小结构

每个 `templates/single-page/*.html` 的核心是一个 `<section class="slide">`：

```html
<section class="slide" data-title="页面标题">
  <p class="kicker">小标题</p>
  <h2 class="h2">主标题</h2>
  <div class="grid g2 mt-l">
    <div class="card"><h4>卡片标题</h4><p class="dim">内容</p></div>
  </div>
  <div class="deck-footer">...</div>
  <div class="notes">演讲者备注（可选）</div>
</section>
```

Claude 的任务是：从多个布局文件中复制 `<section>` 块，替换演示内容，嵌入 `deck.html` 的 `<div class="deck">` 中。

---

## 完整复现步骤（Agent 操作清单）

### 前置依赖

| 依赖 | 版本 | 验证命令 |
|------|------|----------|
| Python | 3.12+ | `python3 --version` |
| Claude Code CLI | 已安装 | `claude --version` |
| Claude 账号 | 已登录 | `claude -p "hello"` 能正常响应 |

### Step 1：注册 html-ppt Skill

```bash
# 将 skill 目录软链到 Claude 全局 skills 目录
ln -sf "$(pwd)/html-ppt-skill" ~/.claude/skills/html-ppt

# 验证
ls -la ~/.claude/skills/html-ppt
test -f ~/.claude/skills/html-ppt/SKILL.md && echo "OK"
```

### Step 2：确保输出目录可写

```bash
mkdir -p html-ppt-skill/output
touch html-ppt-skill/output/.gitkeep
```

### Step 3：配置并启动 API 服务

```bash
cd Claude-Code-To-API

# 创建虚拟环境
python3.12 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# 配置环境
cp .env.example .env
cp api_keys.json.example api_keys.json
# 编辑 .env：确认 SERVER_PORT=9000，CLAUDE_COMMAND=claude

# 启动（后台运行）
nohup python -m src.cli.server --claude-dir . > /tmp/api-server.log 2>&1 &
```

验证服务：

```bash
curl -s http://127.0.0.1:9000/v1/ppt/v3/status \
  -H "Authorization: Bearer sk-demo-key-replace-this"
```

期望返回：

```json
{
  "skill_exists": true,
  "skill_md_exists": true,
  "templates_exist": true,
  "output_dir_exists": true,
  "output_dir_writable": true,
  "skill_registered": true
}
```

### Step 4：调用 v3 生成接口

```bash
curl -s --noproxy 127.0.0.1 --max-time 300 \
  -X POST http://127.0.0.1:9000/v1/ppt/generate-v3 \
  -H "Authorization: Bearer sk-demo-key-replace-this" \
  -H "Content-Type: application/json" \
  -d '{
    "config": {
      "outputLanguage": "中文",
      "pptStyle": "极光渐变",
      "pageMin": 4,
      "pageMax": 6
    },
    "content": "牛顿三大定律：第一定律（惯性定律）、第二定律（F=ma）、第三定律（作用力与反作用力）"
  }'
```

耗时约 **30–180 秒**（Claude 需读模板、选布局、生成内容）。

### Step 5：验证生成结果

**检查 API 响应**：

| 检查项 | 期望 |
|--------|------|
| `ok` | `true` |
| `slideCount` | `pageMin` ≤ 值 ≤ `pageMax + 2` |
| `theme` | 与 `pptStyle` 映射一致（如极光渐变 → `aurora`） |
| `pages` | 非空数组，每项含 `page`、`title`、`html` |
| 每页 `html` | 以 `<!DOCTYPE html>` 开头，CSS 内联在 `<style>` 中 |
| 每页 `html` | 含 `data-theme="{theme}"` 和 `<section class="slide is-active">` |

**检查本地文件**：

```bash
# Claude 写入的原始 deck（多页合一，CSS 为相对路径引用）
cat html-ppt-skill/output/ppt-v3-latest.html | head -20

# 在浏览器中打开原始 deck（需要 assets/ 相对路径可访问）
# 单页 HTML 从 API 响应的 pages[].html 字段保存后可直接打开
```

**检查服务日志**（失败时）：

```bash
tail -50 /tmp/api-server.log
```

---

## v2 / split 生成逻辑（备选方案）

若使用 v2 或 split 接口，需额外启动 `ppt_service`：

```bash
cd html-ppt-skill
nohup python tools/ppt_service.py > /tmp/ppt-service.log 2>&1 &
# 监听 http://127.0.0.1:18765
```

v2 流程：

```
API :9000
  → httpx POST ppt_service :18765 /api/ppt/generate
    → ppt_service 注入 SKILL.md 到 LLM prompt
    → LLM 回调 API :9000（OpenAI 兼容接口）生成 slide 内容
    → ppt_service 渲染 HTML 写入 examples/_service_output/
  → API 读取 HTML 文件内容
  → 返回完整 html 字符串（v2）或拆分 pages[]（split）
```

v2 请求示例：

```bash
curl -X POST http://127.0.0.1:9000/v1/ppt/generate \
  -H "Authorization: Bearer sk-demo-key-replace-this" \
  -H "Content-Type: application/json" \
  -d '{"config": {"outputLanguage": "中文", "pptStyle": "学术简约", "pageMin": 4, "pageMax": 6}, "content": "光合作用原理"}'
```

---

## 关键源码索引

| 文件 | 作用 |
|------|------|
| `Claude-Code-To-API/src/api/routes/ppt_v3.py` | **v3 主逻辑**：prompt 构建、Claude 调用、拆分、CSS 内联 |
| `Claude-Code-To-API/src/api/routes/ppt_v2.py` | v2 逻辑 + `STYLE_THEME_MAP` 风格映射表 |
| `Claude-Code-To-API/src/api/routes/ppt_split.py` | split 逻辑（v2 生成 + 按页拆分） |
| `Claude-Code-To-API/src/services/claude_service.py` | Claude CLI 命令构建与流式解析 |
| `Claude-Code-To-API/src/api/main.py` | 路由注册（v2、split、v3 均挂载在 `/v1` 前缀下） |
| `html-ppt-skill/templates/deck.html` | deck 骨架模板 |
| `html-ppt-skill/templates/single-page/*.html` | 31 种单页布局 |
| `html-ppt-skill/assets/base.css` | 设计系统 + `.slide` 可见性规则 |
| `html-ppt-skill/tools/ppt_service.py` | v2 配套服务（端口 18765） |
| `html-ppt-skill/SKILL.md` | Claude Skill 行为指南 |

---

## 硬编码路径说明

以下路径在源码中硬编码，**换机器部署时需同步修改**：

| 变量 | 当前值 | 所在文件 |
|------|--------|----------|
| `HTML_PPT_SKILL` | `/personal/AI备课助手/html-ppt-skill` | `ppt_v3.py` |
| `working_dir` | `/personal/AI备课助手/html-ppt-skill` | `ppt_v3.py` |
| `HTML_PPT_ASSETS` | `/personal/AI备课助手/html-ppt-skill/assets` | `ppt_v3.py`, `ppt_split.py` |
| `PPT_SERVICE_BASE` | `http://127.0.0.1:18765` | `ppt_v2.py`, `ppt_split.py` |

---

## 支持的 pptStyle（37 种）

学术简约、学术论文、简约白底、编辑风格、瑞士网格、技术分享、代码风格、终端绿、工程图纸、工程白图、企业商务、投资路演、新闻播报、小红书风、柔和粉彩、彩虹渐变、极光渐变、玻璃质感、新粗野主义、包豪斯、日式极简、杂志封面、北欧冷色、北极冷调、日落暖调、拿铁浅色、摩卡深色、玫瑰松、索拉浅色、gruvbox深色、赛博朋克、蒸汽波、Y2K复古、复古电视、孟菲斯、世纪中、锐利黑白。

完整映射：`GET /v1/ppt/styles`

---

## 常见问题

| 现象 | 原因 | 处理 |
|------|------|------|
| `ok: false`，error 含"未生成 HTML 文件" | Claude 未执行 Write | 检查 skill 是否注册、`claude --version` 是否正常 |
| `data-theme` 与请求不符 | Claude 沿用了上一轮产物 | v3 已内置 `re.sub` 强制修正；检查 `ppt-v3-latest.html` |
| `slideCount` 少于 `pageMin` | Claude 自主裁量 | v3 已内置补充 prompt 重试 |
| 单页 HTML 只显示背景色 | 缺少可见性修复 | 确认响应中 `body class="single"` 和 `slide is-active` 存在 |
| v2 返回 503 | ppt_service 未启动 | `python html-ppt-skill/tools/ppt_service.py` |
| 请求超时 | Claude 生成慢 | curl 加 `--max-time 300` |

---

## AI备课助手agent（PPTX 链路，非 HTML）

如需生成 `.pptx` 而非 HTML，使用独立 Agent 服务：

```bash
cd AI备课助手agent/src/agent
pip install -r requirements.txt
export GPUGEEK_API_KEY=your_key
uvicorn app.main:app --host 0.0.0.0 --port 3200
```

工作流：`taskType 0` 大纲解析 → `1` 章节生成 → `2` 微调 → `3` PPT（`python-pptx` 渲染）。

详见 [AI备课助手agent/src/agent/README.md](./AI备课助手agent/src/agent/README.md)。

---

## 相关文档

- [PPT API 接口文档](./Claude-Code-To-API/docs/PPT_API.md)
- [html-ppt 封装实例（v2 踩坑记录）](./Claude-Code-To-API/docs/EXAMPLE_HTML_PPT.md)
- [html-ppt-skill 中文文档](./html-ppt-skill/README.zh-CN.md)
- [Claude-Code-To-API 使用指南](./Claude-Code-To-API/README.md)

## 仓库

[SiliconEinstein/BookGenerator](https://github.com/SiliconEinstein/BookGenerator)
