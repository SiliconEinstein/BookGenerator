# 隧道调用、API 外层封装与缩略图生成指南

> 面向 Agent：本文档说明如何通过隧道访问本地 PPT API、外层封装的分层逻辑，以及缩略图的生成原理与调用方式。

---

## 1. 系统端口与角色

| 服务 | 默认端口 | 监听地址 | 职责 |
|------|----------|----------|------|
| **Claude-Code-To-API** | 9000 | `0.0.0.0` | 对外 API 网关：鉴权、路由、参数转换、后处理 |
| **ppt_service** | 18765 | `127.0.0.1` | 内部配套服务：LLM 驱动生成 HTML、Headless Chrome 缩略图 |
| **Claude CLI** | — | 子进程 | v3 路径：直接读写 html-ppt-skill 模板与输出文件 |

```text
外部 Agent / 前端
      │
      │  HTTP（经隧道或直连）
      ▼
┌─────────────────────────┐
│  API 网关 :9000          │  ← 唯一对外暴露的入口（推荐）
│  Claude-Code-To-API      │
└───────────┬─────────────┘
            │ 127.0.0.1 内网调用（不经隧道）
            ▼
┌─────────────────────────┐
│  ppt_service :18765      │  ← 仅本机访问，不对外暴露
│  html-ppt-skill/tools/   │
└─────────────────────────┘
```

**原则**：对外只暴露 9000 端口；18765 始终绑定 `127.0.0.1`，由 API 网关代为转发。

---

## 2. 隧道方式调用接口

本地服务跑在 `127.0.0.1`，外部 Agent 无法直接访问。有三种常用隧道方案。

### 2.1 SSH 本地端口转发（推荐：有 SSH 权限时）

在**调用方机器**上执行，将远程服务器的 9000 映射到本地：

```bash
# 将远程 9000 映射到本地 19000
ssh -N -L 19000:127.0.0.1:9000 user@<服务器IP>
```

然后通过本地端口调用：

```bash
curl -s --max-time 300 \
  -X POST http://127.0.0.1:19000/v1/ppt/generate-v3 \
  -H "Authorization: Bearer sk-demo-key-replace-this" \
  -H "Content-Type: application/json" \
  -d '{"config": {"outputLanguage": "中文", "pptStyle": "极光渐变", "pageMin": 4, "pageMax": 6}, "content": "牛顿三大定律"}'
```

Agent 代码中把 `BASE_URL` 设为 `http://127.0.0.1:19000` 即可，无需改服务端。

### 2.2 Cloudflare 临时隧道（推荐：无 SSH 时）

在**服务器**上，API 服务已启动的前提下：

```bash
# 下载 cloudflared（一次性）
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 \
  -o /usr/local/bin/cloudflared && chmod +x /usr/local/bin/cloudflared

# 启动临时隧道，将本地 9000 暴露到公网
cloudflared tunnel --url http://127.0.0.1:9000
```

终端会输出类似：

```text
https://random-words-abc123.trycloudflare.com
```

Agent 使用该 URL 作为 `BASE_URL`：

```bash
BASE="https://random-words-abc123.trycloudflare.com"

curl -s --max-time 300 \
  -X POST "$BASE/v1/ppt/generate-v3" \
  -H "Authorization: Bearer sk-demo-key-replace-this" \
  -H "Content-Type: application/json" \
  -d '{"config": {"outputLanguage": "中文", "pptStyle": "学术简约", "pageMin": 4, "pageMax": 6}, "content": "光合作用原理"}'
```

注意：
- 临时隧道 URL 每次重启都会变
- 必须加 `--max-time 300`（生成耗时 30–180 秒）
- 隧道只暴露 9000，不要暴露 18765

### 2.3 同机直连（Agent 与服务在同一台机器）

无需隧道，直接调用：

```bash
curl -s --noproxy 127.0.0.1 --max-time 300 \
  -X POST http://127.0.0.1:9000/v1/ppt/generate-v3 \
  -H "Authorization: Bearer sk-demo-key-replace-this" \
  -H "Content-Type: application/json" \
  -d '{...}'
```

### 2.4 代理环境必知：禁用 HTTP 代理

服务器常配置 Privoxy/HTTP 代理（如 `http://ga.dp.tech:8118`），会导致 `127.0.0.1` 请求被错误转发。

| 调用方式 | 处理方式 |
|----------|----------|
| curl | 加 `--noproxy 127.0.0.1` 或 `--noproxy "*"` |
| Python requests | `proxies={"http": None, "https": None}` |
| Python httpx | `trust_env=False` 或显式 `proxies=None` |
| Node.js axios | `proxy: false` |

Agent 复现模板（Python）：

```python
import requests

resp = requests.post(
    "http://127.0.0.1:9000/v1/ppt/generate-v3",
    headers={
        "Authorization": "Bearer sk-demo-key-replace-this",
        "Content-Type": "application/json",
    },
    json={
        "config": {
            "outputLanguage": "中文",
            "pptStyle": "极光渐变",
            "pageMin": 4,
            "pageMax": 6,
        },
        "content": "牛顿三大定律",
    },
    proxies={"http": None, "https": None},  # 关键：禁用代理
    timeout=300,
)
data = resp.json()
```

### 2.5 隧道 + 鉴权检查清单

Agent 发起请求前，按顺序验证：

```bash
# 1. 健康检查（经隧道地址）
curl -s "$BASE/v1/health" -H "Authorization: Bearer sk-demo-key-replace-this"

# 2. v3 依赖检查
curl -s "$BASE/v1/ppt/v3/status" -H "Authorization: Bearer sk-demo-key-replace-this"
# 期望：skill_exists=true, skill_registered=true

# 3. 正式生成（长超时）
curl -s --max-time 300 -X POST "$BASE/v1/ppt/generate-v3" ...
```

---

## 3. API 外层封装：分层架构

外层封装的核心思想：**用户只面对友好的 REST 接口，内部复杂性由网关消化**。

### 3.1 封装分层图

```mermaid
flowchart TB
    subgraph L1["L1 对外 API 网关（:9000）"]
        V3["ppt_v3.py\nPOST /v1/ppt/generate-v3"]
        V2["ppt_v2.py\nPOST /v1/ppt/generate"]
        SPLIT["ppt_split.py\nPOST /v1/ppt/generate-split"]
    end

    subgraph L2["L2 内部引擎"]
        CLAUDE["Claude CLI\n读写 html-ppt-skill"]
        PPTSVC["ppt_service.py\n:18765"]
    end

    subgraph L3["L3 资源与产物"]
        SKILL["html-ppt-skill/\ntemplates + assets"]
        OUT["output/\nHTML + PNG"]
    end

    V3 --> CLAUDE --> SKILL --> OUT
    V2 --> PPTSVC
    SPLIT --> PPTSVC
    PPTSVC -->|"modelBaseUrl 回调"| L1
    PPTSVC --> SKILL --> OUT
```

### 3.2 各层职责

| 层级 | 文件 | 输入（用户侧） | 输出（用户侧） | 核心转换 |
|------|------|---------------|---------------|----------|
| **L1-v3** | `ppt_v3.py` | `{config, content}` | `{ok, slideCount, theme, pages[]}` | 中文风格→theme；构建 Claude prompt；拆分+CSS内联 |
| **L1-v2** | `ppt_v2.py` | `{config, content}` | `{ok, html, slideCount, theme}` | 中文风格→theme；转发 ppt_service；读回完整 HTML |
| **L1-split** | `ppt_split.py` | `{config, content}` | `{ok, slideCount, theme, pages[]}` | 同 v2 生成；正则拆 slide；CSS 内联 |
| **L2** | `ppt_service.py` | 结构化 payload | `{htmlUrl, thumbnails[]}` | LLM 生成 slides JSON；`build_html()`；可选 PNG |
| **L3** | `html-ppt-skill/` | 模板 + 主题 CSS | `.html` / `.png` 文件 | 静态资源与布局 |

### 3.3 v2 封装的参数转换（典型范例）

用户请求（友好格式）：

```json
{
  "config": {
    "outputLanguage": "中文",
    "pptStyle": "极光渐变",
    "pageMin": 4,
    "pageMax": 6
  },
  "content": "任意文本内容"
}
```

`ppt_v2.py` 转换为 `ppt_service` 内部格式：

```json
{
  "deckName": "v2-1717600000",
  "theme": "aurora",
  "renderThumbnails": false,
  "modelDriven": true,
  "modelProvider": "openai",
  "injectSkillPrompt": true,
  "pageMin": 4,
  "pageMax": 6,
  "pptInput": {
    "content": "任意文本内容",
    "outputLanguage": "中文",
    "instructions": "将以下内容转换为 4-6 页的 极光渐变 风格课件，使用 中文。"
  },
  "modelBaseUrl": "http://127.0.0.1:9000",
  "modelApiKey": "sk-demo-key-replace-this"
}
```

**关键设计：`modelBaseUrl` 指回 API 网关自身**，形成闭环：

```text
API :9000
  → ppt_service :18765（生成 slides 结构）
    → API :9000 /v1/chat/completions（LLM 调用）
      → Claude CLI
    ← slides JSON
  ← index.html 文件路径
→ API 读取 HTML 内容 → 返回给调用方
```

### 3.4 v3 封装的后处理（split + 内联）

v3 不走 `ppt_service`，但输出格式与 split 一致。后处理在 `ppt_v3.py` 内完成：

```python
# 1. 读取 Claude 写入的完整 deck
html_content = output_file.read_text()

# 2. 页数兜底 + 主题强制修正
if slide_count < page_min: ...  # 向 Claude 发补充 prompt
html_content = re.sub(r'data-theme="[^"]*"', f'data-theme="{theme}"', html_content)

# 3. 按页拆分，每页 CSS 完全内联
pages = split_to_pages(html_content, theme)
# 返回 pages[].html — 可直接在浏览器打开，无需外部资源
```

`split_to_pages()` 内联的 CSS 来源：

```text
assets/fonts.css
assets/base.css
assets/themes/{theme}.css
assets/animations/animations.css
```

并追加单页可见性修复（否则 `.slide { opacity: 0 }` 导致空白）：

```css
.slide { opacity: 1 !important; pointer-events: auto !important; ... }
```

```html
<body class="single">
  <section class="slide is-active">...</section>
</body>
```

### 3.5 封装设计约束（Agent 复现新 Skill 时遵循）

1. **参数转换在路由层**：用户格式 ↔ 服务格式，配套服务不感知 API 层
2. **配套服务保持独立**：`ppt_service.py` 可单独 `curl` 测试
3. **LLM 回调走 localhost 回环**：`modelBaseUrl` 必须是 `http://127.0.0.1:9000`，不能走隧道地址
4. **返回资源完全自包含**：`pages[].html` 必须 CSS 内联，不依赖 `../assets/`
5. **单页必须做可见性修复**：否则截图和预览都是空白背景

---

## 4. 缩略图生成逻辑

### 4.1 生成位置

缩略图由 **`ppt_service.py` 的 `render_pngs()`** 生成，不在 v3 路径中。

```text
renderThumbnails: true
      │
      ▼
create_deck() 写完 index.html
      │
      ▼
render_pngs(html_path, slide_count)
      │
      ▼
每页生成 1.png, 2.png, ... N.png
```

### 4.2 核心代码逻辑

文件：`html-ppt-skill/tools/ppt_service.py`

```python
def render_pngs(html_path: Path, slide_count: int):
    chrome = find_chrome()          # 查找 Chrome/Edge 可执行文件
    if not chrome:
        return []                     # 无 Chrome → 跳过，不报错

    png_files = []
    for index in range(1, slide_count + 1):
        target = html_path.parent / f"{index}.png"
        # 利用 runtime.js 的 hash 路由定位到第 N 页
        url = f"file:///{html_path.as_posix()}#/{index}"
        subprocess.run([
            chrome,
            "--headless=new",
            "--disable-gpu",
            "--hide-scrollbars",
            "--no-sandbox",
            "--virtual-time-budget=4000",   # 等待 CSS/动画渲染 4 秒
            "--window-size=1600,900",        # 截图分辨率
            f"--screenshot={target}",
            url,
        ], check=True)
        png_files.append(str(target))
    return png_files
```

**原理**：
1. 用 Headless Chrome 打开本地 `file://` URL
2. 通过 `#/N` hash 让 `runtime.js` 切换到第 N 页 slide
3. `--virtual-time-budget=4000` 等待主题 CSS 和动画渲染完成
4. `--screenshot=` 输出 PNG 到 deck 目录

输出路径示例：

```text
html-ppt-skill/examples/_service_output/v2-1717600000/
├── index.html
├── 1.png
├── 2.png
├── 3.png
└── ...
```

### 4.3 如何触发缩略图生成

#### 方式 A：直接调用 ppt_service（最直接）

```bash
curl -s --noproxy 127.0.0.1 -X POST http://127.0.0.1:18765/api/ppt/generate \
  -H "Content-Type: application/json" \
  -d '{
    "deckName": "thumb-demo",
    "theme": "aurora",
    "renderThumbnails": true,
    "slides": [
      {"title": "封面", "body": "牛顿力学"},
      {"title": "第一定律", "body": ["惯性定律", "物体保持静止或匀速直线运动"]},
      {"title": "总结", "body": "三大定律是经典力学基础"}
    ]
  }'
```

响应：

```json
{
  "ok": true,
  "result": {
    "deckName": "thumb-demo",
    "htmlUrl": "/output/thumb-demo/index.html",
    "slideCount": 3,
    "theme": "aurora",
    "renderThumbnails": true,
    "thumbnails": [
      ".../examples/_service_output/thumb-demo/1.png",
      ".../examples/_service_output/thumb-demo/2.png",
      ".../examples/_service_output/thumb-demo/3.png"
    ]
  }
}
```

通过静态路由访问缩略图：

```bash
# 在服务器本机
curl -s --noproxy 127.0.0.1 http://127.0.0.1:18765/output/thumb-demo/1.png -o page1.png
```

#### 方式 B：经 API 网关封装（需改代码）

当前 `ppt_v2.py` 和 `ppt_split.py` **硬编码** `renderThumbnails: false`：

```python
# ppt_v2.py 第 119 行
"renderThumbnails": False,
```

要经 9000 端口返回缩略图，需修改路由层：

```python
# 在 config 中增加开关
render_thumbnails = config.get("renderThumbnails", False)
payload["renderThumbnails"] = render_thumbnails

# 生成后从 result["thumbnails"] 读取 PNG 路径
# 通过 ppt_service 静态路由读取二进制，base64 编码后返回
```

v3 路径（`ppt_v3.py`）**目前不支持缩略图**。可选扩展方案：
1. 生成 `pages[].html` 后，写入临时文件，调用 `render_pngs()`
2. 或复用 `html-ppt-skill/scripts/render.sh`

### 4.4 Chrome 依赖

| 环境变量 | 说明 |
|----------|------|
| `CHROME_PATH` | 手动指定 Chrome/Edge 路径 |

自动搜索路径（`find_chrome()`）：

```text
$CHROME_PATH
C:\Program Files\Google\Chrome\Application\chrome.exe
C:\Program Files (x86)\Google\Chrome\Application\chrome.exe
C:\Program Files\Microsoft\Edge\Application\msedge.exe
```

Linux 服务器需安装 Chrome 并设置：

```bash
export CHROME_PATH=/usr/bin/google-chrome-stable
# 或 chromium
export CHROME_PATH=/usr/bin/chromium-browser
```

无 Chrome 时：`renderThumbnails: true` 不会报错，但 `thumbnails` 返回空数组 `[]`。

### 4.5 命令行批量截图（不经过 API）

`html-ppt-skill/scripts/render.sh` 提供独立截图能力：

```bash
cd html-ppt-skill

# 单页截图
./scripts/render.sh output/ppt-v3-latest.html

# 所有 slide 截图（自动检测页数）
./scripts/render.sh output/ppt-v3-latest.html all

# 指定页数
./scripts/render.sh output/ppt-v3-latest.html 5
```

输出：`ppt-v3-latest.png` 或 `ppt-v3-latest-png/ppt-v3-latest_01.png` 等。

---

## 5. Agent 完整复现流程

### 场景 A：外部 Agent 通过隧道生成 HTML 课件（v3，无缩略图）

```bash
# === 服务器侧 ===
# 1. 启动 API
cd Claude-Code-To-API && source venv/bin/activate
nohup python -m src.cli.server > /tmp/api-server.log 2>&1 &

# 2. 启动隧道（二选一）
ssh -N -L 19000:127.0.0.1:9000 user@server          # SSH 方案
# 或
cloudflared tunnel --url http://127.0.0.1:9000       # Cloudflare 方案

# === Agent 侧 ===
BASE="http://127.0.0.1:19000"   # SSH 方案
# BASE="https://xxx.trycloudflare.com"  # Cloudflare 方案

# 3. 检查依赖
curl -s "$BASE/v1/ppt/v3/status" -H "Authorization: Bearer sk-demo-key-replace-this"

# 4. 生成
curl -s --max-time 300 -X POST "$BASE/v1/ppt/generate-v3" \
  -H "Authorization: Bearer sk-demo-key-replace-this" \
  -H "Content-Type: application/json" \
  -d '{"config": {"outputLanguage": "中文", "pptStyle": "极光渐变", "pageMin": 4, "pageMax": 6}, "content": "牛顿三大定律"}' \
  -o response.json

# 5. 提取单页 HTML
python3 -c "
import json
d = json.load(open('response.json'))
for p in d['pages']:
    open(f'page_{p[\"page\"]}.html','w').write(p['html'])
    print(f'page {p[\"page\"]}: {p[\"title\"]}')
"
```

### 场景 B：本机生成 HTML + 缩略图

```bash
# 1. 启动 ppt_service
cd html-ppt-skill
nohup python tools/ppt_service.py > /tmp/ppt-service.log 2>&1 &

# 2. 确认 Chrome 可用
export CHROME_PATH=/usr/bin/google-chrome-stable  # 按实际路径设置

# 3. 生成（含缩略图）
curl -s --noproxy 127.0.0.1 -X POST http://127.0.0.1:18765/api/ppt/generate \
  -H "Content-Type: application/json" \
  -d '{
    "deckName": "demo-with-thumbs",
    "theme": "aurora",
    "renderThumbnails": true,
    "slides": [
      {"title": "封面", "body": "AI 备课助手"},
      {"title": "要点", "body": ["大纲解析", "章节生成", "PPT 输出"]}
    ]
  }' | python3 -m json.tool

# 4. 查看缩略图
ls html-ppt-skill/examples/_service_output/demo-with-thumbs/*.png
```

### 场景 C：v3 生成后用脚本补截图

```bash
# v3 生成完成后，本地已有 output/ppt-v3-latest.html
cd html-ppt-skill
./scripts/render.sh output/ppt-v3-latest.html all
ls output/ppt-v3-latest-png/
```

---

## 6. 接口能力矩阵

| 能力 | v3 `/generate-v3` | v2 `/generate` | split `/generate-split` | ppt_service 直连 |
|------|-------------------|----------------|-------------------------|-----------------|
| 经隧道调用（:9000） | ✅ | ✅ | ✅ | ❌ 仅本机 |
| 返回单页 HTML 数组 | ✅ `pages[]` | ❌ 完整 `html` | ✅ `pages[]` | ❌ 文件路径 |
| CSS 内联（可独立打开） | ✅ | ❌ 相对路径 | ✅ | ❌ 相对路径 |
| 缩略图 PNG | ❌ | ❌（封装关闭） | ❌（封装关闭） | ✅ `renderThumbnails` |
| Claude 自主选布局 | ✅ | ❌ 固定布局 | ❌ 固定布局 | ❌ 固定布局 |
| 需 ppt_service | ❌ | ✅ | ✅ | — |
| 需 Claude CLI | ✅ | ✅（回调） | ✅（回调） | ❌（非 modelDriven 时） |

---

## 7. 故障排查

| 现象 | 可能原因 | 处理 |
|------|----------|------|
| 隧道 URL 返回 502 | API 服务未启动 | `curl http://127.0.0.1:9000/v1/health` |
| 连接超时 | 未禁用代理 / 超时太短 | `--noproxy` + `--max-time 300` |
| v3 返回 `ok: false` | Skill 未注册 | `ln -sf .../html-ppt-skill ~/.claude/skills/html-ppt` |
| v2/split 返回 503 | ppt_service 未启动 | `python html-ppt-skill/tools/ppt_service.py` |
| `thumbnails: []` | Chrome 未安装 | 设置 `CHROME_PATH` 环境变量 |
| 缩略图空白 | HTML 未渲染完 | 增大 `--virtual-time-budget` |
| 单页 HTML 空白 | 缺少可见性修复 | 确认 `body.single` + `slide is-active` |
| LLM 回调失败 | modelBaseUrl 走了隧道地址 | 必须保持 `http://127.0.0.1:9000` |

---

## 8. 关键源码索引

| 文件 | 内容 |
|------|------|
| `Claude-Code-To-API/src/api/routes/ppt_v3.py` | v3 封装 + `split_to_pages()` + CSS 内联 |
| `Claude-Code-To-API/src/api/routes/ppt_v2.py` | v2 封装 + 风格映射 |
| `Claude-Code-To-API/src/api/routes/ppt_split.py` | split 封装 + 单页 HTML 构建 |
| `Claude-Code-To-API/src/api/routes/ppt.py` | 原始封装（含 renderThumbnails 透传，未注册到 main.py） |
| `html-ppt-skill/tools/ppt_service.py` | `create_deck()` + `render_pngs()` 缩略图 |
| `html-ppt-skill/scripts/render.sh` | 命令行批量截图 |
| `html-ppt-skill/tools/SERVICE_API.md` | ppt_service 接口说明 |
