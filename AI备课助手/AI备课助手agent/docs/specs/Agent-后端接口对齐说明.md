# Agent-后端接口对齐说明

本文档基于以下材料综合整理：
- `docs/product/【prd】2026-3-30｜奇点课堂V1.1.4版本产品需求文档.pdf`
- `docs/product/奇点课堂AI课程技术方案.pdf`
- `docs/specs/需求确认清单.md`

目标：明确 AI Agent 服务与后端系统之间的接口协议、任务边界、结果存储方式和待确认项，便于双方尽快对齐并进入编码阶段。

## 1. 当前已确认的后端约束
- `course_task` 任务类型：`0-大纲解析 / 1-小节解析 / 2-小节微调 / 3-生成课程包`
- AI 课程目录树只有 `2层`
- OSS 路径组织：
  - `/{courseId}/outline/source.{pdf|txt|text}`（原始上传，可选）
  - 输入目录同路径 `{inputDir}/{basename}.md`（与上传的 PDF 同级；Agent 首次解析后写入，章节生成复用，避免重复解析 PDF）
  - `/{courseId}/outline/parsed.json`（产物目录，仅结构化目录）
  - `/{courseId}/sections/{sectionId}/seq_{n}.json`
  - `/{courseId}/package/{sectionId}/...`

## 2. 推荐职责边界
- 后端负责业务状态、任务主数据、课程树入库
- Agent 负责内容生成、结果文件产出、回调后端

## 3. 推荐统一接口模式
- 建议统一入口：`POST /agent-api/v1/tasks`
- Agent 根据 `taskType` 路由到四类内部任务

## 4. 推荐请求协议

```json
{
  "externalTaskId": "string",
  "taskType": 0,
  "courseId": 123,
  "targetId": 456,
  "callbackUrl": "string",
  "config": {
    "applianceObject": 1,
    "sectionDuration": 45,
    "outputLanguage": 1,
    "pptStyle": 0,
    "pageMin": 15,
    "pageMax": 25,
    "sourceFileUrl": "string"
  },
  "payload": {}
}
```

## 5. 回调协议建议

```json
{
  "externalTaskId": "string",
  "status": "success",
  "resultUrl": "string",
  "errorMessage": ""
}
```
