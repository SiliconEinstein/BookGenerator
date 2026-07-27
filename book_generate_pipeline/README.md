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

## 4. 输入文件格式

跑一门课程前，在 `output/<课程名>/book_info/` 下准备两个必需文件，另有两个可选文件。

### 4.1 syllabus.md（必需）

课程大纲。整份内容必须包在 `<syllabus>` 标签里，标签外的文字会被忽略：

```markdown
<syllabus>
# 分子对接入门

## 第1章：分子对接基础

### 1.1 分子对接的基本原理（1课时）
- 受体与配体的结合模式
- 打分函数与结合自由能估计
- 刚性对接与柔性对接的差异

### 1.2 分子对接的实践流程（1课时）
- 蛋白结构准备与质量检查
- 对接盒子设置与构象搜索
- 对接结果的可视化与评估

## 第2章：对接结果的解读

### 2.1 打分函数的局限（1课时）
- 打分函数为何不等于亲和力
</syllabus>
```

解析规则见 `TopicBookGenerator.parse_syllabus_to_dict`，不符合格式的行会被**静默跳过**而不是报错：

| 行首 | 含义 | 硬性要求 |
| --- | --- | --- |
| `# ` | 课程名 | 建议与目录名、`book_info.json` 的 `教材名称` 保持一致 |
| `## ` | 章 | 必须含 `第N章`，N 为阿拉伯数字 |
| `### ` | 子节 | 形如 `<编号> <标题>`，两者之间必须有空格 |
| `- ` | 知识点 | 挂到最近的 `### ` 下 |

几个容易踩的点：

- `## 第一章：...` 用中文数字**不会被识别**，该章连同其下所有子节会被整段丢弃，必须写成 `第1章`。
- `### ` 行按第一个空格切分，`1.1` 是编号、其余是标题。写成 `### 1.1分子对接原理`（无空格）会导致这个子节丢失。
- 子节编号建议用 `章号.序号`，`chapter_ids` / `subchapter_ids` 这类局部重跑参数依赖它。
- `（1课时）` 这类后缀会作为标题的一部分保留，不影响解析。
- 出现在任何 `### ` 之前的 `- ` 会被忽略。

### 4.2 book_info.json（必需）

课程元信息。七个字段全部必填，`main.py` 启动时会校验非空且不含 `{{...}}` 占位符：

```json
{
  "教材名称": "分子对接入门",
  "语言": "中文",
  "面向人群": "药学、生物信息学专业本科高年级学生",
  "教学方式": "课堂讲授与上机实践相结合，强调问题驱动的分析流程",
  "教学目的": "理解分子对接的基本原理，掌握一次完整对接实验的操作流程与结果评估方法",
  "教学要求": "具备基础的有机化学与蛋白质结构知识",
  "教材行文风格": "问题驱动型"
}
```

| 字段 | 用途 |
| --- | --- |
| `教材名称` | 课程名，用于目录与标题 |
| `语言` | 只接受 `中文` 或 `英文`，决定 prompt 目录与输出语言 |
| `面向人群` | 写进前言与正文 prompt，影响行文深度 |
| `教学方式` | 影响正文中实践环节与理论叙述的配比 |
| `教学目的` | 前言与章节目标的依据 |
| `教学要求` | 预备知识，决定哪些概念需要展开 |
| `教材行文风格` | 映射为 prompt 的 `style_tendency`，见下 |

`教材行文风格` 最终会被归一化为 `严谨推演型`、`叙事引导型`、`问题驱动型` 三选一。
建议直接填这三个值之一；填自由描述时会按关键词模糊匹配，匹配不上则默认 `问题驱动型`，并在日志里打印实际采用的值。

文件不存在时，`main.py` 会先生成一份字段留空的模板并提示你填写，填完再跑。

### 4.3 practical_case.json（可选）

实战案例 notebook 的定义，是一个对象数组。不提供此文件时，notebook 环节会直接跳过：

```json
[
  {
    "chapter": "第1章 人工智能算法基础",
    "section": "1.1 监督学习 分类算法实战",
    "topic": "Iris数据集分类实战",
    "description": "加载Iris数据集，使用scikit-learn实现逻辑回归、SVM、随机森林，绘制决策边界并对比准确率。",
    "key_libraries": ["scikit-learn", "matplotlib", "pandas"]
  }
]
```

| 字段 | 说明 |
| --- | --- |
| `chapter` | 所属章，用于定位 notebook 落盘目录与按 `chapter_ids` 过滤 |
| `section` | 所属子节 |
| `topic` | 案例名，会被清洗成 notebook 文件名 |
| `description` | 案例要做什么，是生成 notebook 的主要依据 |
| `key_libraries` | 期望用到的库，写进 prompt 约束技术选型 |

章节归属按 `chapter` 里的 `第N章` 或 `Chapter N` 识别，识别不到则回退到 `section` 的 `N.M` 前缀。
两者都识别不出时，如果你传了 `chapter_ids`，该案例会被跳过并打印日志。

### 4.4 docs/<课程名>_job.md（可选）

岗位需求描述，普通 Markdown 即可，无固定结构。只在 `generate_chapter()` 生成或精修大纲时读取
（路径为 `<docs_path>/<课程名>_job.md`，`scripts/generate_book.py` 默认 `docs_path="./docs"`），
用于让大纲贴合真实岗位的能力要求。文件不存在时按空字符串处理，不影响运行。

---

## 5. 目录结构（当前版本）

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
├─ book_info/                # 输入，格式见第 4 节
│  ├─ syllabus.md
│  ├─ book_info.json
│  └─ practical_case.json    # 可选
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

## 6. 运行方式

## 6.1 推荐：命令行脚本

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

## 6.2 调试入口（`main.py`）

```bash
python main.py
```

当前 `main.py` 默认行为：
- 自动检查/校验 `book_info.json`
- 仅跑素材包阶段（`generate_material_pack`，示例里有 `chapter_ids=[1]`）
- 正文阶段代码默认注释，适合先验证 pack 逻辑

## 6.3 编程调用（推荐双阶段显式调用）

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

## 7. 素材包（pack）重点说明

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

## 8. 插图流水线

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

## 9. 常见问题（FAQ）

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

## 10. 辅助工具

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
