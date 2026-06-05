# Prompt 模板目录

各阶段 LLM 提示词独立存放，由 `app/utils/prompt_utils.py` 加载，使用 Python `str.format` 占位符注入变量。

| 文件 | 阶段 | 调用方 |
|------|------|--------|
| `outline_parse.md` | 课程大纲 → 目录 JSON | `outline_service.parse_outline_from_text` |
| `section_generate.md` | 章节大纲生成 | `content_service.create_section_content`（需 `outline/source.md` + `parsed.json`） |
| `section_refine.md` | 章节大纲微调 | `content_service.refine_section_content`（同上） |
| `ppt_plan.md` | PPT 页面规划 JSON | `ppt_service.plan_ppt_slides` |

修改提示词后无需改 Python 代码（除非新增占位符变量）。
