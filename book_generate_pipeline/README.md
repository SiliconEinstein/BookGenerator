# Topic Book Generator（教材生成流水线）

这是一个基于 Python 的教材/课程讲义生成 pipeline：输入课程名与基本参数，自动生成**章节大纲 → 摘要 → 子章节正文 → 章节整合与纠错 → 插图 → HTML/PDF**等产物。

项目主要入口是：
- **推荐 CLI**：`scripts/generate_book.py`
- **编程调用**：`src/core/topic_book_generator.py`（`TopicBookGenerator`）
- **示例主程序**：`main.py`（更像一个可改参数的 demo）

---

## 功能概览（按代码实际流程）

在 `TopicBookGenerator.generate_book()` 中，整体流程大致是：
- **阶段 1：生成摘要**（按子章节并发）
- **阶段 2：生成子章节正文**（step1 文件落盘）
- **阶段 3：章节整合 + “实战项目/练习题”插入 + 逐节纠错**（step2 文件落盘，生成整章 `md/` 与 `log/`，目前log为弃用状态）
- **阶段 4：为整章 Markdown 自动插图**（输出 `md_with_images/` 与 `output/images/`）
- **阶段 5：格式转换**：`md → html → pdf`

---

## 目录结构（节选）

```
book_generate_pipeline/
├── config/
│   └── config.dev.yaml              # 开发配置（支持 ${ENV_VAR} 注入）
├── prompts/                         # 中文 prompt
├── prompts_en/                      # 英文 prompt
├── scripts/
│   ├── generate_book.py             # 推荐：CLI 入口
│   └── list_litellm_models.py       # 查询 LiteLLM Proxy 的 /v1/models
├── src/
│   ├── core/
│   │   ├── topic_book_generator.py  # 主编排：TopicBookGenerator
│   │   ├── chapter_generator.py     # 章节大纲生成
│   │   └── book_generator.py        # 摘要/正文/整章整合/纠错/项目插入等
│   ├── models/                      # 各模型 provider（gemini/gpt/deepseek/qwen/doubao）
│   ├── tools/
│   │   ├── md2html_wrapper.py       # md→html / html→pdf 封装
│   │   ├── draw_images.py           # 给 Markdown 批量生成插图（高层封装）
│   │   └── draw_image/              # 插图子流水线（插图位点选择/生成/校验/插入标签）
│   └── utils/
│       └── config.py                # 配置读取（支持 .env 与 yaml）
├── output/                          # 产物输出目录（books/ images/ abstract/ temp/ 等）
├── main.py                          # demo 入口（可按需改参数）
├── requirements.txt / pyproject.toml
└── .env.example
```

---

## 安装（Windows / PowerShell 友好）

### 1）创建虚拟环境

```bash
python -m venv .venv
.venv\Scripts\activate
```

### 2）安装依赖

```bash
pip install -r requirements.txt
```

### 3）安装 Playwright 浏览器（用于 HTML→PDF 等）

```bash
playwright install chromium
```

### 4）（可选但强烈建议）支持读取 `.env`

代码会尝试从项目根目录读取 `.env`（`src/utils/config.py` 里通过 `dotenv`）。如果你希望 `.env` 生效，请额外安装：

```bash
pip install python-dotenv
```

---

## 配置

### 环境变量

参考 `.env.example` 新建 `.env`（放在 `book_generate_pipeline/` 目录下）：
- **LiteLLM Proxy**：`LITELLM_PROXY_API_BASE`、`LITELLM_API_KEY`
- **GPUgeek**：`GPUGEEK_API_BASE`、`GPUGEEK_API_KEY`（首云平台的模型）
- **MCP**：`MCP_URL`（用于内容生成/工具调用）
- **Wiki 检索**：`WIKI_SEARCH_API_BASE`

也可以直接修改 `config/config.dev.yaml`（里面支持 `${ENV_VAR}` 占位符插值）。

### prompt 目录选择

`language="ch"` 使用 `prompts/`，`language="en"` 使用 `prompts_en/`。

---

## 运行方式

### 方式 A（推荐）：命令行生成一本书

在 `book_generate_pipeline/` 目录下执行：

```bash
python scripts/generate_book.py --course-name "离散数学" --language ch --education-level 本科 --number-of-topics 50
```

只跑部分章节/小节：

```bash
python scripts/generate_book.py --course-name "离散数学" --language ch --chapter-ids 1 2
python scripts/generate_book.py --course-name "离散数学" --language ch --subchapter-ids 1.1 1.2 2.1
```

> 注意：该脚本默认输出到 `./output/books/{language}/{course_name}`，章节大纲输出到 `./output/chapter/{language}/{course_name}.md`。

### 方式 B：运行 `main.py`（适合你手动改参数做实验）

```bash
python main.py
```

`main.py` 中包含 `prompt_config`（课程类型、推导密度、案例策略、读者水平、风格倾向等），你可以按需要调整。

### 方式 C：作为模块编程调用

```python
import asyncio
from src.core.topic_book_generator import TopicBookGenerator

async def run():
    agent = TopicBookGenerator(language="ch")
    book_info = ["本科生", "离散数学", "50"]
    chapter_save_path = "output/chapter/ch/离散数学.md"
    book_save_dir = "output/books/ch/离散数学"
    await agent.generate_chapter(book_info, chapter_save_path, "./docs")
    await agent.generate_book(chapter_save_path, book_save_dir)

asyncio.run(run())
```

---

## 输出产物说明（按默认约定）

以 `output/books/ch/离散数学/` 为例，常见会看到：
- `md/`：整章合并后的 Markdown
- `md_with_images/`：插图后 Markdown（图像链接已替换为相对路径）
- `pdf/`：最终 PDF
- `html/`：中间 HTML
- `<chapter_dir>/step1/`：子章节初稿（逐节文件）
- `<chapter_dir>/step2/`：纠错/优化后的逐节文件（以及 `Section_summary_summary.md` 等）
- `log/`：纠错/优化日志（如果生成）

插图会输出到 `output/images/...`（由 `TopicBookGenerator` 在阶段 4 里计算路径：`books → images`）。

---

## 插图流水线（draw_image）

插图逻辑在 `src/tools/draw_image/`，高层封装为 `src/tools/draw_images.py:draw_images_for_markdown()`：
- 从整章 Markdown 里选择插图位置（生成 `insert_meta.json`）
- 为每个位置调用图像生成（输出 `image_{index}.png`）
- 生成带标签的 `with_images.md` 与 `images.json` 清单
- 最终生成的 `md_with_images/*.md` 会把图片路径替换为相对路径，便于移动/打包

你也可以单独运行插图 pipeline（开发/调试用）：

```bash
python -m src.tools.draw_image.main markdown --markdown-path "你的md路径" --output-dir "你的输出目录"
```

---

## LiteLLM Proxy 模型列表（可选）

```bash
python scripts/list_litellm_models.py
```

---

## 常见问题（FAQ）

- **Q：`.env` 不生效？**
  - **A**：请确认你安装了 `python-dotenv`，并且 `.env` 放在 `book_generate_pipeline/` 目录下。

- **Q：运行时报 `ModuleNotFoundError: dp...`？**
  - **A**：`src/core/book_generator.py` 使用了 `from dp.agent.client import MCPClient`（用于 MCP 调用）。如果你环境里没有该包，需要安装对应的内部/外部依赖，或者将 MCP 客户端实现替换为你可用的实现。

- **Q：图片生成阶段报 JSON 解析错误（LLM 输出不规范）？**
  - **A**：插图模块对 LLM 的结构化输出有要求；如果遇到解析失败，优先查看 `output/images/**/images.json`、`insert_meta.json` 以及 `draw_image_agent.py` 的日志定位是哪一段输出不符合 JSON。

---

## License

MIT License
