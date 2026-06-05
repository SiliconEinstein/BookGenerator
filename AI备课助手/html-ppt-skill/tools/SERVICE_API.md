# html-ppt-skill 服务接口

用于把 `html-ppt-skill` 包装成一个后端可直接调用的 HTTP 服务，输入结构化内容后生成 HTML 幻灯片。

## 1. 启动服务

```bash
python tools/ppt_service.py
```

默认监听：

- `host`: `127.0.0.1`
- `port`: `18765`

可用环境变量覆盖：

- `PPT_SERVICE_HOST`
- `PPT_SERVICE_PORT`

---

## 2. 健康检查

`GET /healthz`

响应示例：

```json
{"ok": true, "service": "html-ppt-skill"}
```

---

## 3. 生成接口

`POST /api/ppt/generate`

### 3.1 请求体（推荐）

```json
{
  "deckName": "nlp-report-service-demo",
  "theme": "aurora",
  "renderThumbnails": false,
  "pptInput": {
    "chapterName": "第5章 自然语言处理、知识图谱和可解释人工智能",
    "sectionName": "自然语言处理与文本挖掘",
    "teachingGoal": "## 知识理解\n- 解释 NER 与 RE 的区别\n- 说明关系抽取与不良反应抽取的产出",
    "knowledgePoints": "## 概念\n- NER：实体识别\n- RE：关系抽取",
    "suggestedStructure": "## 45分钟流程\n- 导入\n- 讲授\n- 实操\n- 总结",
    "extraInfo": "## 案例\n- 药物-不良反应\n- 药物-靶点"
  }
}
```

### 3.2 请求体（直接传 slides）

```json
{
  "deckName": "custom-deck",
  "theme": "minimal-white",
  "slides": [
    {"title": "封面", "body": "这是第一张"},
    {"title": "目标", "body": ["目标1", "目标2", "目标3"]}
  ]
}
```

### 3.3 请求体（模型驱动：GPUGeek + Skill Prompt）

```json
{
  "deckName": "nlp-model-demo",
  "theme": "aurora",
  "modelDriven": true,
  "modelProvider": "gpugeek",
  "injectSkillPrompt": true,
  "modelName": "Vendor2/GPT-5.2",
  "pageMin": 8,
  "pageMax": 12,
  "pptInput": {
    "chapterName": "第5章 自然语言处理、知识图谱和可解释人工智能",
    "sectionName": "自然语言处理与文本挖掘",
    "teachingGoal": "..."
  }
}
```

`modelProvider` 支持：

- `gpugeek`：调用 `GPUGEEK_API_BASE/chat/completions`（与 `llm_service.py` 同协议）
- `anthropic`：调用 Claude Messages API
- `openai` 或 `codex`：调用 OpenAI 兼容 `chat/completions`

鉴权方式（任选其一）：

- 请求体传 `modelApiKey`
- 环境变量（推荐，和现有 `llm_service.py` 保持一致）：
  - `GPUGEEK_API_BASE`
  - `GPUGEEK_API_KEY`
  - `LLM_MODEL`
  - `LLM_RETRY_TIMES`
  - `LLM_CONNECT_TIMEOUT_SECONDS`
  - `LLM_READ_TIMEOUT_SECONDS`

可选项：

- `modelBaseUrl`（默认 `https://api.anthropic.com` 或 `https://api.openai.com`）
- `modelTimeoutSec`（默认 90 秒）
- `injectSkillPrompt`（默认 `true`，会把 `html-ppt-skill/SKILL.md` 作为提示词注入模型）

### 3.4 返回体

```json
{
  "ok": true,
  "result": {
    "deckName": "custom-deck",
    "html": "F:\\SciencePedia\\AI备课助手\\html-ppt-skill\\examples\\_service_output\\custom-deck\\index.html",
    "htmlUrl": "/output/custom-deck/index.html",
    "slideCount": 2,
    "theme": "minimal-white",
    "modelDriven": false,
    "modelMeta": {},
    "renderThumbnails": false,
    "thumbnails": []
  }
}
```

---

## 4. 静态访问

服务内置静态文件路由，后端可直接拼接 URL 给前端预览：

- 生成结果：`GET /output/<deckName>/index.html`
- 资源文件：`GET /assets/...`

例如：

- `http://127.0.0.1:18765/output/custom-deck/index.html`

---

## 5. cURL 示例

```bash
curl -X POST "http://127.0.0.1:18765/api/ppt/generate" \
  -H "Content-Type: application/json" \
  -d "{\"deckName\":\"demo\",\"theme\":\"aurora\",\"slides\":[{\"title\":\"封面\",\"body\":\"hello\"}]}"
```

---

## 6. 对接建议（后端）

- 生产环境建议由后端托管 `OUTPUT_ROOT` 目录并做定时清理。
- 若只要 HTML，不要缩略图，显式传 `renderThumbnails=false`。
- `theme` 传不存在的值会自动回落到 `minimal-white`。
