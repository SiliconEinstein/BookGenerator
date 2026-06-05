# PPT 生成 API 接口文档

## 接口概述

将任意文本内容自动转换为结构化的 HTML 演示文稿，支持 37 种可视化风格，由 LLM 智能解析内容并生成多页幻灯片。

---

## 接口地址

```
POST http://10.5.54.232:9000/v1/ppt/generate
```

---

## 鉴权方式

请求头中必须携带 API Key：

```
Authorization: Bearer sk-demo-key-replace-this
```

---

## 请求参数

### Content-Type
```
application/json
```

### 请求体结构

```json
{
  "config": {
    "outputLanguage": "中文",
    "pptStyle": "学术简约",
    "pageMin": 8,
    "pageMax": 12
  },
  "content": "string"
}
```

### 字段说明

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| config | object | 是 | 配置信息 |
| config.outputLanguage | string | 否 | 输出语言，默认"中文" |
| config.pptStyle | string | 否 | PPT 风格，默认"学术简约"，见下方风格列表 |
| config.pageMin | integer | 否 | 最少页数，默认 8 |
| config.pageMax | integer | 否 | 最多页数，默认 12 |
| content | string | 是 | 任意文本内容，可以是教学大纲、课程笔记、技术文档等 |

---

## 响应格式

### 成功响应

```json
{
  "ok": true,
  "html": "<!DOCTYPE html>\n<html lang=\"zh-CN\">...</html>",
  "slideCount": 10,
  "theme": "academic-paper"
}
```

### 字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| ok | boolean | 是否成功 |
| html | string | 完整的 HTML 文件内容，可直接保存为 .html 文件 |
| slideCount | integer | 生成的幻灯片页数 |
| theme | string | 实际使用的主题名称 |

### 错误响应

```json
{
  "ok": false,
  "error": "错误描述信息"
}
```

---

## 支持的 pptStyle 值（37 种）

### 学术/正式
- `学术简约` / `学术论文` - 学术论文风格
- `简约白底` - 极简白色背景
- `编辑风格` - 编辑排版风格
- `瑞士网格` - 瑞士网格设计

### 技术/开发
- `技术分享` - 深色技术风格（推荐）
- `代码风格` - Dracula 代码主题
- `终端绿` - 终端绿色主题
- `工程图纸` - 蓝图风格
- `工程白图` - 工程图纸白底

### 商务/正式
- `企业商务` - 企业级简洁风格
- `投资路演` - VC 路演专用
- `新闻播报` - 新闻播报风格

### 时尚/设计
- `小红书风` - 小红书图文风格
- `柔和粉彩` - 柔和粉彩色调
- `彩虹渐变` - 彩虹渐变色
- `极光渐变` - 极光渐变效果
- `玻璃质感` - 玻璃拟态设计
- `新粗野主义` - Neo-Brutalism
- `包豪斯` - 包豪斯设计
- `日式极简` - 日式极简风格
- `杂志封面` - 杂志封面风格

### 主题色系
- `北欧冷色` - Nord 冷色调
- `北极冷调` - 北极冰雪色
- `日落暖调` - 日落暖色调
- `拿铁浅色` - Catppuccin Latte
- `摩卡深色` - Catppuccin Mocha
- `玫瑰松` - Rose Pine
- `索拉浅色` - Solarized Light
- `gruvbox深色` - Gruvbox Dark

### 特殊风格
- `赛博朋克` - 赛博朋克霓虹
- `蒸汽波` - Vaporwave 蒸汽波
- `Y2K复古` - Y2K 千禧复古
- `复古电视` - 复古电视风格
- `孟菲斯` - 孟菲斯设计
- `世纪中` - Mid-century Modern
- `锐利黑白` - 锐利黑白对比

> **注意**：如果传入的 pptStyle 不在上述列表中，将自动回落到 `学术简约` 风格。

---

## 调用示例

### cURL

```bash
curl --noproxy "*" \
  -X POST http://10.5.54.232:9000/v1/ppt/generate \
  -H "Authorization: Bearer sk-demo-key-replace-this" \
  -H "Content-Type: application/json" \
  -d '{
    "config": {
      "outputLanguage": "中文",
      "pptStyle": "技术分享",
      "pageMin": 8,
      "pageMax": 10
    },
    "content": "第5章 自然语言处理与文本挖掘。核心内容：命名实体识别(NER)、关系抽取(RE)、文本分类。教学目标：理解NLP基础概念，掌握NER的实现流程，了解在药物研发中的应用案例。"
  }'
```

### Python

```python
import requests

# API 配置
API_URL = "http://10.5.54.232:9000/v1/ppt/generate"
API_KEY = "sk-demo-key-replace-this"

# 请求数据
payload = {
    "config": {
        "outputLanguage": "中文",
        "pptStyle": "学术简约",
        "pageMin": 8,
        "pageMax": 12
    },
    "content": """
        第3章 动量守恒定律
        
        1. 动量和动量定理
        - 动量定义：p = mv
        - 冲量：I = Ft
        - 动量定理：Ft = Δp
        
        2. 动量守恒定律
        - 系统不受外力或合外力为零
        - m1v1 + m2v2 = m1v1' + m2v2'
        
        3. 碰撞问题
        - 弹性碰撞
        - 非弹性碰撞
        - 完全非弹性碰撞
    """
}

# 发送请求
response = requests.post(
    API_URL,
    headers={"Authorization": f"Bearer {API_KEY}"},
    json=payload,
    proxies={"http": None, "https": None},  # 绕过代理
    timeout=180  # 生成需要时间，建议 180 秒
)

# 处理响应
result = response.json()

if result["ok"]:
    # 保存 HTML 文件
    with open("output.html", "w", encoding="utf-8") as f:
        f.write(result["html"])
    
    print(f"✓ PPT 生成成功")
    print(f"  页数: {result['slideCount']}")
    print(f"  主题: {result['theme']}")
    print(f"  文件已保存: output.html")
else:
    print(f"✗ 生成失败: {result['error']}")
```

### JavaScript/Node.js

```javascript
const axios = require('axios');

const apiUrl = 'http://10.5.54.232:9000/v1/ppt/generate';
const apiKey = 'sk-demo-key-replace-this';

const payload = {
  config: {
    outputLanguage: '中文',
    pptStyle: '小红书风',
    pageMin: 8,
    pageMax: 10
  },
  content: '分享主题：前端性能优化实战。核心内容：懒加载、代码分割、CDN加速、图片优化、缓存策略...'
};

axios.post(apiUrl, payload, {
  headers: {
    'Authorization': `Bearer ${apiKey}`,
    'Content-Type': 'application/json'
  },
  proxy: false,  // 禁用代理
  timeout: 180000
})
.then(response => {
  const result = response.data;
  if (result.ok) {
    // 保存 HTML 文件
    const fs = require('fs');
    fs.writeFileSync('output.html', result.html, 'utf-8');
    console.log(`✓ PPT 生成成功，共 ${result.slideCount} 页`);
  } else {
    console.error(`✗ 生成失败: ${result.error}`);
  }
})
.catch(error => {
  console.error('请求失败:', error.message);
});
```

---

## 辅助接口

### 获取支持的风格列表

```bash
GET http://10.5.54.232:9000/v1/ppt/styles
```

**响应示例：**
```json
{
  "styles": ["学术简约", "技术分享", "小红书风", ...],
  "count": 37,
  "mapping": {
    "学术简约": "academic-paper",
    "技术分享": "tokyo-night",
    ...
  }
}
```

### 健康检查

```bash
GET http://10.5.54.232:9000/v1/health
```

---

## 重要提示

### 1. 代理配置

服务器网络环境配置了 Privoxy 代理，从其他机器调用时**必须禁用代理**：

- **curl**: 添加 `--noproxy "*"`
- **Python requests**: 设置 `proxies={"http": None, "https": None}`
- **Node.js axios**: 设置 `proxy: false`

### 2. 超时设置

PPT 生成需要调用 LLM，建议设置至少 **180 秒**的超时时间。

### 3. 输出格式

响应中的 `html` 字段是完整的 HTML 文件内容，包含：
- 内联 CSS 样式
- 键盘导航支持（← → 翻页，T 切换主题，F 全屏）
- 响应式布局
- 可直接在浏览器打开，无需额外依赖

### 4. content 字段建议

content 可以是任意文本，但建议包含：
- 明确的主题/标题
- 清晰的知识点或章节结构
- 适当的分段和要点

LLM 会根据内容自动生成标题、分页和排版。

---

## 错误码说明

| HTTP 状态码 | 说明 |
|------------|------|
| 200 | 请求成功，检查响应中的 `ok` 字段 |
| 401 | API Key 缺失或无效 |
| 503 | PPT 服务未启动 |
| 500 | 服务器内部错误 |

---

## 技术架构

```
调用方
  ↓ HTTP POST
API 网关 (端口 9000)
  ↓ 转发请求 + 调用 LLM
PPT 服务 (端口 18765)
  ↓ 渲染 HTML
返回完整 HTML 内容
```

- **API 网关**: FastAPI，处理鉴权、路由、LLM 调用
- **PPT 服务**: html-ppt-skill，负责 HTML 模板渲染和主题应用
- **LLM**: Claude Opus 4.6，负责内容解析和结构化

---

## 更新日志

**2026-06-02**
- 初始版本发布
- 支持 37 种可视化风格
- 直接返回 HTML 内容，无需中间文件存储
- 主题映射功能，用户友好的中文风格名称
