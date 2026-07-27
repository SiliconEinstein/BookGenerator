# Topic Book Generator（当前版本 README）

本项目用于自动化生成课程教材，核心是两段式流程：

1. 先生成素材包 `pack/`（可预览、可人工修改）
2. 再基于素材包生成正文、插图与书籍导出（HTML/PDF）

主入口：
- 推荐脚本：`scripts/generate_book.py`
- 编程调用：`src/core/topic_book_generator.py`（`TopicBookGenerator`）
- 试验入口：`main.py`（默认只跑素材包阶段，便于调试）

---

## 1. 当前代码对应的真实流程

`TopicBookGenerator` 的核心方法有 3 个：

- `generate_chapter(...)`
  - 生成/刷新大纲文本（内部会调用 `ChapterGenerator`）
- `generate_material_pack(...)`
  - 只生成素材包（摘要、wiki、qa、案例 notebook、summary_images、prompt 快照等）
- `generate_book(...)`
  - 加载已存在 `pack/`，再继续正文生成与导出

`generate_book(...)` 内部分阶段：

- Phase 0：加载素材包（若不存在会报错，要求先跑 material pack）
- Phase 1：生成子章节正文（`book/chapters/*/step1`）
- Phase 2：项目/练习插入与章节级整理（`book/chapters/*/step2` + `book/md`）
- Phase 3：对章节 Markdown 插图（输出到 `book/images`，并生成 `book/md_with_images`）
- Phase 4：`md -> html -> pdf`

> 当传入 `subchapter_ids` 时，会在 Phase 1 后提前结束（跳过插图与导出），用于低成本局部重跑。

---

## 2. 安装与准备

在 `book_generate_pipeline/` 目录执行：

```bash
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium
```

装好后建议先跑一遍体检，确认外部依赖都通：

```bash
cp .env.example .env           # 填入网关密钥与 OpenSearch 凭据
python scripts/healthcheck.py
```

---

## 3. 配置说明

配置来源：

- YAML：`config/config.dev.yaml`
- 环境变量：支持 `${ENV_VAR}` 插值
- `.env`：`src/__init__.py` 在导入任何子模块前加载项目根目录的 `.env`

所有 LLM 调用统一走同一个 LiteLLM 网关，只需两个凭据：

- `LITELLM_PROXY_API_BASE`（默认 `https://litellm.dp.tech`）
- `LITELLM_PROXY_API_KEY`

其余环境变量：`OPENSEARCH_HOST`、`OPENSEARCH_USERNAME`、`OPENSEARCH_PASSWORD`、`WIKI_SEARCH_API_BASE`。

### 模型按用途配置

模型名写在 `config/config.dev.yaml` 的 `llm.models` 下，可用 `LLM_<ROLE>_MODEL` 环境变量临时覆盖：

| 角色 | 用途 | 默认模型 |
| --- | --- | --- |
| `writer` | 正文、摘要、前言、章节纠错、notebook | `cds/GPT-5.4` |
| `reviewer` | 大纲 battle 的对手模型 | `claude-sonnet-4-6` |
| `utility` | 结构化输出、QA 关键词扩展、插图选点 | `gemini-3.1-pro-preview` |
| `image` | 插图生成 | `sn/gemini-3-pro-image-preview` |

另有两项列表配置：`llm.evaluators` 是大纲 battle 的评委（取多数票，应选相互独立的模型），
`llm.writer_fallbacks` 是 writer 调用失败后的降级顺序。

注意 `utility` 角色必须选支持 `response_format` JSON schema 的模型；Claude 系会忽略该参数并返回散文。

语言与 prompt 目录映射：

- `language="ch"` -> `prompts/`
- `language="en"` -> `prompts_en/`

---

## 4. 目录结构（当前版本）

```text
book_generate_pipeline/
├─ config/config.dev.yaml     # 模型角色、并发、prompt 名映射
├─ prompts/                   # 中文 prompt
├─ prompts_en/                # 英文 prompt
├─ scripts/
│  ├─ generate_book.py        # 主命令行入口
│  ├─ healthcheck.py          # 外部依赖逐项体检
│  ├─ run_e2e.py              # 最小课程端到端自检
│  └─ list_litellm_models.py  # 列出网关可用模型
├─ src/
│  ├─ core/
│  │  ├─ topic_book_generator.py   # 总调度
│  │  ├─ chapter_generator.py      # 大纲生成与 battle
│  │  ├─ material_pack_generator.py# 素材包
│  │  ├─ book_generator.py         # 正文与导出
│  │  ├─ article_writer_local.py   # 单篇写作
│  │  └─ chapter_types.py
│  ├─ models/llm_providers.py      # 唯一的 LLM 调用出口
│  ├─ tools/
│  │  ├─ draw_images.py            # 插图高层封装
│  │  ├─ draw_image/               # 选点 + 出图
│  │  ├─ get_wiki_article.py       # 百科检索
│  │  ├─ get_qa_pair.py            # 问答对检索
│  │  ├─ qa_retrieve/              # OpenSearch 检索实现
│  │  ├─ md2html/ + md2html_wrapper.py  # HTML 渲染
│  │  ├─ convert_format.py         # md -> html -> pdf
│  │  └─ database.py               # wiki MySQL
│  └─ utils/
└─ output/                    # 生成产物，已在 .gitignore 中
```

单课程输出布局（`output/<课程名>/`）：

```text
output/<课程名>/
├─ book_info/
│  ├─ syllabus.md
│  └─ book_info.json
├─ pack/
│  ├─ book_info/
│  ├─ prompts/
│  ├─ abstracts/
│  ├─ wiki_articles/
│  ├─ qa_pairs/
│  ├─ summary_images/
│  └─ notebooks/
└─ book/
   ├─ chapters/          # step1 / step2
   ├─ md/
   ├─ md_with_images/
   ├─ images/
   ├─ html/
   ├─ pdf/
   ├─ log/
   └─ qa_pairs/
```

---

## 5. 运行方式

## 5.1 推荐：命令行脚本

```bash
python scripts/generate_book.py --course-name "离散数学" --language ch --education-level 本科 --number-of-topics 50
```

局部重跑：

```bash
python scripts/generate_book.py --course-name "离散数学" --language ch --chapter-ids 1 2
python scripts/generate_book.py --course-name "离散数学" --language ch --subchapter-ids 1.1 1.2 2.1
```

脚本默认读取：
- 大纲路径：`./output/<course_name>/book_info/syllabus.md`
- 课程目录：`./output/<course_name>/`

## 5.2 调试入口（`main.py`）

```bash
python main.py
```

当前 `main.py` 默认行为：
- 自动检查/校验 `book_info.json`
- 仅跑素材包阶段（`generate_material_pack`，示例里有 `chapter_ids=[1]`）
- 正文阶段代码默认注释，适合先验证 pack 逻辑

## 5.3 编程调用（推荐双阶段显式调用）

```python
import asyncio
from src.core.topic_book_generator import TopicBookGenerator

async def run():
    agent = TopicBookGenerator(language="ch")
    chapter_path = "output/离散数学/book_info/syllabus.md"
    output_dir = "output/离散数学"

    # 1) 先构建素材包
    await agent.generate_material_pack(chapter_path, output_dir)

    # 2) 再消费素材包生成正文与导出
    await agent.generate_book(chapter_path, output_dir)

asyncio.run(run())
```

---

## 6. 素材包（pack）重点说明

`pack/` 是可复用中间层，推荐先人工审核后再跑全文生成。

典型内容：

- `pack/book_info/`：`syllabus.md`、`book_info.json`、`preface.md`、`practical_case.json`
- `pack/prompts/`：本课程 prompt 快照（支持人工微调）
- `pack/abstracts/`：分章摘要
- `pack/wiki_articles/`：子章节资料缓存
- `pack/qa_pairs/`：问答对缓存
- `pack/summary_images/`：章节总结图与元数据
- `pack/notebooks/`：实战案例 notebook 与数据

### 实战案例 notebook 数据目录（已改为分层）

- notebook：`pack/notebooks/<章节目录>/<案例名>.ipynb`
- 数据：`pack/notebooks/data/<章节目录>/<案例目录>/`
- notebook 中 `DATA_DIR` 由模板变量 `{{DATA_DIR}}` 注入（相对路径）
  - 典型值：`../data/<章节目录>/<案例目录>`

策略：
- 已存在 notebook 默认跳过（增量补齐，不覆盖）
- `chapter_ids` 会同步过滤案例生成（无法识别章节归属的 case 会跳过并打印日志）

---

## 7. 插图流水线

高层封装：
- `src/tools/draw_images.py` -> `draw_images_for_markdown(...)`

功能：
- 选取插图位点（`insert_meta.json`）
- 生成图片（`image_*.png`）
- 生成 `with_images.md` 与 `images.json`
- 输出 `book/md_with_images/*.md`，并修正为相对图片路径

出图接口偶发过载，`generate_images` 会退避重试三次；仍失败时该位点的图片标签会被摘掉，
不会在成书里留下指向空文件的链接。

单独调试某个 Markdown：

```python
import asyncio
from src.tools import draw_images_for_markdown

asyncio.run(draw_images_for_markdown(
    md_path="你的md路径",
    image_output_dir="输出目录",
    new_md_path="输出目录/with_images.md",
))
```

---

## 8. 常见问题（FAQ）

- **Q1：为什么提示找不到素材包？**
  - `generate_book()` 依赖已存在的 `pack/`；请先执行 `generate_material_pack()`。

- **Q2：为什么 `book_info.json` 校验失败？**
  - `main.py` 会校验以下字段非空且无占位符：
    - `教材名称`、`语言`、`面向人群`、`教学方式`、`教学目的`、`教学要求`、`教材行文风格`
  - 其中 `语言` 仅支持 `中文` 或 `英文`。

- **Q3：为什么只生成了 step1 没有 HTML/PDF？**
  - 你很可能传了 `subchapter_ids`，系统会提前结束后续阶段（这是预期行为）。

- **Q4：`.env` 不生效怎么办？**
  - `.env` 必须放在 `book_generate_pipeline/` 根目录，由 `src/__init__.py` 统一加载。
    子包内不要再放 `.env`，否则会互相覆盖。

- **Q5：QA 检索命中 0 条怎么办？**
  - OpenSearch 里的题库是英文的，中文关键词要靠 `utility` 模型扩展出英文变体才能命中。
    先跑 `python scripts/healthcheck.py structured` 确认结构化输出正常。注意 `utility`
    角色不能配 Claude 系模型，它们会忽略 `response_format` 导致关键词解析失败。

---

## 9. 辅助工具

查询网关可用模型：

```bash
python scripts/list_litellm_models.py
```

逐项体检（网关各角色模型、结构化输出、出图、百科检索、问答检索、PDF 渲染）：

```bash
python scripts/healthcheck.py             # 全部
python scripts/healthcheck.py chat image  # 只跑指定项
```

改动核心链路后跑一遍最小课程端到端自检：

```bash
python scripts/run_e2e.py         # pack + book 全流程
python scripts/run_e2e.py pack    # 只跑素材包
```

---

## License

MIT
