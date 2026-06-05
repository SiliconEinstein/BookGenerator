# AI备课助手 Python Agent

## 安装

```bash
cd /personal/AI备课助手/src/agent
pip install -r requirements.txt
```

## 启动

```bash
uvicorn app.main:app --host 0.0.0.0 --port 3200
```

## 接口

- `GET /healthz`
- `POST /agent-api/v1/tasks`

## LLM 工作流

四个阶段均通过 GPUGeek `GPT-5.2` 完成语义生成，提示词模板位于 `prompts/`（见 `prompts/README.md`）：

| taskType | 阶段 | Prompt 文件 | 说明 |
|----------|------|-------------|------|
| 0 | 大纲解析 | `outline_parse.md` | PDF/文本 → 课程目录 JSON；失败时回退规则解析 |
| 1 | 章节大纲 | `section_generate.md` | 生成教学目标等字段 |
| 2 | 章节微调 | `section_refine.md` | 按指令改写章节 JSON |
| 3 | PPT | `ppt_plan.md` | 先规划幻灯片 JSON，再由 `python-pptx` 渲染；中间产物 `*.slides.json` |

需配置环境变量：`GPUGEEK_API_KEY`、`GPUGEEK_API_BASE`。

## OSS 配置

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `BACKEND_BASE_URL` | `https://bohrium-core.test.dp.tech` | 后端根地址，用于换取 OSS token |
| `OSS_TOKEN_PATH` | `/api/v1/courses/ai/common/token` | Token 接口路径 |
| `OSS_UPLOAD_URL` | `https://tiefblue.test.dp.tech/api/upload/binary` | 二进制上传地址 |
| `BACKEND_AUTH_TOKEN` | 空 | 若后端鉴权需要，填 Bearer token |

完整 Token URL：`{BACKEND_BASE_URL}{OSS_TOKEN_PATH}` → `https://bohrium-core.test.dp.tech/api/v1/courses/ai/common/token`

## 冒烟测试

```bash
PYTHONPATH=/personal/AI备课助手/src/agent python tests/smoke_test.py
```


## 可控测试流程

默认跑整条链路：

```bash
PYTHONPATH=/personal/AI备课助手/src/agent python tests/test_workflow_runner.py
```

使用本地 PDF 作为大纲输入（仅 outline 或整条链路均可）：

```bash
PYTHONPATH=/personal/AI备课助手/src/agent python tests/test_workflow_runner.py --steps outline \
  --source-file "/personal/AI备课助手/docs/project/人工智能与药物设计的发展.pdf"
```

只跑指定接口：

```bash
PYTHONPATH=/personal/AI备课助手/src/agent python tests/test_workflow_runner.py --steps outline
PYTHONPATH=/personal/AI备课助手/src/agent python tests/test_workflow_runner.py --steps outline section
PYTHONPATH=/personal/AI备课助手/src/agent python tests/test_workflow_runner.py --steps section
```

自定义任务入参：

```bash
PYTHONPATH=/personal/AI备课助手/src/agent python tests/test_workflow_runner.py --task-file tests/tasks.example.json
```

说明：
- 产物目录：`data/outputs/{课程名称}/`（课程名来自大纲解析的 `courseName`，非法文件名字符会替换为 `_`）。
- **大纲解析（taskType 0）** 仅在输入目录解析 PDF/文本一次，并在**与源文件同目录**生成 `.md`（如 `docs/project/人工智能与药物设计的发展.pdf` → `docs/project/人工智能与药物设计的发展.md`）。若该 `.md` 已存在则直接复用，不重复解析 PDF。未来输入为 OSS 路径时，逻辑路径为同前缀的 `.md`（本地暂镜像至 `data/outputs/_input_mirror/`）。
- **章节生成（taskType 1）** 通过 `outlineSourceUrl` 读取输入目录中的 `.md`；`parsed.json` 中会记录 `outlineSourceUrl`。默认 PDF 测试小节为「新药研发流程、成本与挑战」。
- `refine` 会自动复用 `section` 的输出结果。
- `ppt` 会优先复用 `refine` 的输出，若未执行 `refine`，则回退复用 `section`。
- 若单独测试 `section` / `refine` / `ppt`，请在 `payload` 或 `config` 中传入 `courseName`，或保证依赖 URL 指向 `outputs/{课程名称}/` 下的文件。

{
  "config": {
    "outputLanguage": "中文",
    "pptStyle": "学术简约",
    "pageMin": 8,
    "pageMax": 12
  },
  "content": string
}

其中content中的可以是任何文本内容，
