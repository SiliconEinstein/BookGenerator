# AI备课助手

## 目录结构

```text
src/agent/                 Python Agent 服务
  app/                     服务主代码
  tests/                   冒烟测试

docs/product/              产品与技术原始文档
/docs/project/             项目方案与任务拆解
/docs/specs/               协议与需求确认文档

data/outputs/agent/        Python Agent 产出结果
/data/outputs/js_legacy/   历史 JS 产出结果
/data/examples/            示例 PPT 文件

tools/pdf_parser/          PDF 解析脚本
```

## 启动

```bash
cd /personal/AI备课助手/src/agent
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 3200
```

## 冒烟测试

```bash
cd /personal/AI备课助手/src/agent
PYTHONPATH=/personal/AI备课助手/src/agent python tests/smoke_test.py
```
