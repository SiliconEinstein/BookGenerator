# AI备课助手

面向教育场景的 AI 备课工具集，覆盖**课程大纲解析 → 章节内容生成 → PPT 课件产出**的完整链路。项目由三个子模块协同组成，可独立部署，也可串联使用。

## 子模块概览

| 模块 | 说明 | 技术栈 |
|------|------|--------|
| [AI备课助手agent](./AI备课助手agent/) | 备课 Agent 服务：大纲解析、章节生成、PPTX 渲染 | Python / FastAPI / python-pptx |
| [Claude-Code-To-API](./Claude-Code-To-API/) | 将 Claude Code 智能体封装为 OpenAI 兼容 API | Python / FastAPI / Claude CLI |
| [html-ppt-skill](./html-ppt-skill/) | HTML 演示文稿生成 Skill：36 主题、31 布局、演讲者模式 | HTML / CSS / JS |

## 架构关系

```mermaid
flowchart LR
    A[课程 PDF / 文本] --> B[AI备课助手agent]
    B --> C[大纲 JSON]
    B --> D[章节内容]
    B --> E[PPTX 课件]

    F[任意文本内容] --> G[Claude-Code-To-API]
    G --> H[Claude CLI + html-ppt-skill]
    H --> I[HTML 演示文稿]
```

- **AI备课助手agent**：面向结构化备课流程，通过 LLM 完成语义生成，最终输出 `.pptx` 文件。
- **Claude-Code-To-API + html-ppt-skill**：面向灵活的 HTML 课件生成，支持 37 种可视化风格，由 Claude 自主选布局、组织内容。

## 目录结构

```text
AI备课助手/
├── AI备课助手agent/          # 备课 Agent 服务
│   ├── src/agent/            # Python 服务主代码
│   ├── docs/                 # 产品文档、需求规格
│   ├── data/                 # 示例与产出数据
│   └── tools/                # PDF 解析等工具脚本
├── Claude-Code-To-API/       # Claude → OpenAI API 网关
│   ├── src/                  # API 服务与路由
│   └── docs/                 # 接口文档（含 PPT API）
└── html-ppt-skill/           # HTML PPT 生成 Skill
    ├── templates/            # deck 模板与单页布局
    ├── assets/               # 主题、动画、脚本
    └── output/               # 生成产物（本地，不提交）
```

## 快速开始

### 1. AI备课助手agent

```bash
cd AI备课助手agent/src/agent
pip install -r requirements.txt

# 配置 LLM（必填）
export GPUGEEK_API_KEY=your_key
export GPUGEEK_API_BASE=your_base_url

uvicorn app.main:app --host 0.0.0.0 --port 3200
```

主要接口：

- `GET /healthz` — 健康检查
- `POST /agent-api/v1/tasks` — 提交备课任务

工作流阶段（`taskType`）：

| taskType | 阶段 | 产出 |
|----------|------|------|
| 0 | 大纲解析 | 课程目录 JSON |
| 1 | 章节生成 | 教学目标、知识点等字段 |
| 2 | 章节微调 | 改写后的章节 JSON |
| 3 | PPT 生成 | `.pptx` + `*.slides.json` |

冒烟测试：

```bash
cd AI备课助手agent/src/agent
PYTHONPATH=. python tests/smoke_test.py
```

### 2. Claude-Code-To-API

```bash
cd Claude-Code-To-API
python3.12 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # 编辑配置
cp api_keys.json.example api_keys.json

python -m src.cli.server --claude-dir .
```

服务默认监听 `9000` 端口，提供 OpenAI 兼容的 Chat Completions 接口，以及 PPT 生成专用路由。

### 3. html-ppt-skill

作为 Claude Code Skill 使用，需注册到 `~/.claude/skills/html-ppt`：

```bash
ln -s "$(pwd)/html-ppt-skill" ~/.claude/skills/html-ppt
```

也可通过 Claude-Code-To-API 的 PPT 接口间接调用，无需手动操作 Skill。

## PPT 生成 API

Claude-Code-To-API 提供三代 PPT 接口，推荐使用 **v3**（Claude CLI + html-ppt-skill 自主决策布局）：

| 版本 | 路径 | 特点 |
|------|------|------|
| v1 | `POST /v1/ppt/generate` | 基础 HTML 生成 |
| v2 | `POST /v1/ppt/generate-v2` | 增强风格映射 |
| v3 | `POST /v1/ppt/generate-v3` | Claude 自主选布局，推荐 |

### v3 调用示例

```bash
curl -X POST http://127.0.0.1:9000/v1/ppt/generate-v3 \
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

支持的 `pptStyle` 包括：学术简约、简约白底、技术分享、代码风格、企业商务、小红书风、柔和粉彩、极光渐变、玻璃质感、新粗野主义、日式极简 等 37 种风格。

状态检查：`GET /v1/ppt/v3/status`

详细接口文档见 [Claude-Code-To-API/docs/PPT_API.md](./Claude-Code-To-API/docs/PPT_API.md)。

## 环境要求

| 组件 | 要求 |
|------|------|
| Python | 3.12+（Claude-Code-To-API）/ 3.10+（agent） |
| Claude Code | 已安装并配置（PPT v3 需要） |
| Node.js | 可选（agent 中 pptxgenjs 依赖） |

## 安全说明

以下文件包含敏感信息，**请勿提交到版本库**（已在 `.gitignore` 中排除）：

- `Claude-Code-To-API/.env`
- `Claude-Code-To-API/api_keys.json`
- `AI备课助手agent` 中的 `GPUGEEK_API_KEY` 等环境变量

首次部署请从 `*.example` 文件复制并填入自己的配置。

## 相关文档

- [AI备课助手agent 服务说明](./AI备课助手agent/src/agent/README.md)
- [Claude-Code-To-API 使用指南](./Claude-Code-To-API/README.md)
- [html-ppt-skill 中文文档](./html-ppt-skill/README.zh-CN.md)
- [PPT API 接口文档](./Claude-Code-To-API/docs/PPT_API.md)

## 仓库

本项目托管于 [SiliconEinstein/BookGenerator](https://github.com/SiliconEinstein/BookGenerator)，与 `book_generate_pipeline` 模块并列存放。
