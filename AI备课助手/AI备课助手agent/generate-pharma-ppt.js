const PptxGenJS = require('pptxgenjs');
const pptx = new PptxGenJS();

pptx.author = 'AI备课助手';
pptx.company = 'OpenMAIC';
pptx.title = '新药研发流程、成本与挑战';

const THEME = {
    primary: '1565C0',
    secondary: '2E7D32',
    accent: 'E65100',
    text: '212121',
    light: 'F5F5F5',
    bg: 'FFFFFF'
};

// ========== 第1页：封面 ==========
const s1 = pptx.addSlide();
s1.background = { color: THEME.primary };
s1.addShape(pptx.shapes.OVAL, { x: 8, y: 0.3, w: 2.5, h: 2.5, fill: { color: 'FFFFFF', transparency: 15 } });
s1.addShape(pptx.shapes.OVAL, { x: -0.8, y: 4.2, w: 3.5, h: 3.5, fill: { color: 'FFFFFF', transparency: 8 } });
s1.addText('绪论：人工智能与药物设计的发展', { x: 0.5, y: 1.8, w: 9, h: 0.8, fontSize: 24, fontFace: 'Microsoft YaHei', color: 'BBDEFB', align: 'center' });
s1.addText('新药研发流程、成本与挑战', { x: 0.5, y: 2.6, w: 9, h: 1.2, fontSize: 44, fontFace: 'Microsoft YaHei', color: 'FFFFFF', bold: true, align: 'center' });
s1.addText('Pharmaceutical R&D: Process, Cost & Challenges', { x: 0.5, y: 4.0, w: 9, h: 0.6, fontSize: 20, fontFace: 'Arial', color: '90CAF9', align: 'center' });

// ========== 第2页：教学目标 ==========
const s2 = pptx.addSlide();
s2.addText('教学目标', { x: 0.5, y: 0.4, w: 9, h: 0.8, fontSize: 36, fontFace: 'Microsoft YaHei', color: THEME.primary, bold: true });

// 知识理解卡片
s2.addShape(pptx.shapes.RECTANGLE, { x: 0.5, y: 1.4, w: 4.3, h: 2.3, fill: { color: 'E3F2FD' }, line: { color: '2196F3', width: 2 } });
s2.addText('知识理解', { x: 0.7, y: 1.6, w: 3.9, h: 0.5, fontSize: 20, fontFace: 'Microsoft YaHei', color: THEME.primary, bold: true });
s2.addText('• 说清新药研发流程的主要阶段\n• 概括每阶段核心任务与关键产出\n• 解释成本与挑战的3类关键瓶颈', { x: 0.7, y: 2.1, w: 3.9, h: 1.4, fontSize: 14, fontFace: 'Microsoft YaHei', color: THEME.text });

// 能力训练卡片
s2.addShape(pptx.shapes.RECTANGLE, { x: 5.2, y: 1.4, w: 4.3, h: 2.3, fill: { color: 'E8F5E9' }, line: { color: '4CAF50', width: 2 } });
s2.addText('能力训练', { x: 5.4, y: 1.6, w: 3.9, h: 0.5, fontSize: 20, fontFace: 'Microsoft YaHei', color: THEME.secondary, bold: true });
s2.addText('• 映射研发问题到流程环节\n• 识别决策点与输入/输出\n• 结构化判断：优先级/风险/策略', { x: 5.4, y: 2.1, w: 3.9, h: 1.4, fontSize: 14, fontFace: 'Microsoft YaHei', color: THEME.text });

// 课堂达成要求
s2.addShape(pptx.shapes.RECTANGLE, { x: 0.5, y: 4.0, w: 9, h: 1.8, fill: { color: 'FFF3E0' }, line: { color: 'FF9800', width: 2 } });
s2.addText('课堂达成要求（可评估）', { x: 0.7, y: 4.2, w: 8.6, h: 0.5, fontSize: 18, fontFace: 'Microsoft YaHei', color: THEME.accent, bold: true });
s2.addText('✓ 快速测验：按正确顺序写出主要研发阶段，每阶段写出1个常见风险点\n✓ 参与讨论：用"流程阶段—挑战—成本后果—缓解策略"四段式表达观点', { x: 0.7, y: 4.7, w: 8.6, h: 1.0, fontSize: 14, fontFace: 'Microsoft YaHei', color: THEME.text });

// ========== 第3页：新药研发流程 ==========
const s3 = pptx.addSlide();
s3.background = { color: THEME.light };
s3.addText('新药研发流程：阶段—任务—产出', { x: 0.5, y: 0.4, w: 9, h: 0.8, fontSize: 32, fontFace: 'Microsoft YaHei', color: THEME.primary, bold: true });

const stages = [
    { num: '1', name: '靶点提出与验证', task: '机制、通路、疾病相关性验证', output: '因果证据', color: 'E3F2FD', x: 0.5, y: 1.5 },
    { num: '2', name: '先导发现与优化', task: 'SAR研究与性质平衡', output: '可优化化合物系列', color: 'E8F5E9', x: 2.2, y: 1.5 },
    { num: '3', name: '临床前研究', task: '有效性、药代/毒理、CMC', output: 'IND/CTA证据包', color: 'FFF3E0', x: 3.9, y: 1.5 },
    { num: '4', name: '临床研究', task: 'Ⅰ/Ⅱ/Ⅲ期试验', output: '疗效与安全性证据链', color: 'FCE4EC', x: 5.6, y: 1.5 },
    { num: '5', name: '注册与上市后', task: '申报、监测、风险管理', output: '真实世界数据', color: 'E1BEE7', x: 7.3, y: 1.5 }
];

stages.forEach(s => {
    s3.addShape(pptx.shapes.RECTANGLE, { x: s.x, y: s.y, w: 1.5, h: 3.8, fill: { color: s.color }, line: { color: 'BBBBBB', width: 1 } });
    s3.addText(s.num, { x: s.x, y: s.y + 0.2, w: 1.5, h: 0.6, fontSize: 32, fontFace: 'Arial', color: THEME.primary, bold: true, align: 'center' });
    s3.addText(s.name, { x: s.x + 0.1, y: s.y + 0.9, w: 1.3, h: 1.0, fontSize: 13, fontFace: 'Microsoft YaHei', color: THEME.text, bold: true, align: 'center' });
    s3.addText('任务:', { x: s.x + 0.1, y: s.y + 2.0, w: 1.3, h: 0.3, fontSize: 10, fontFace: 'Microsoft YaHei', color: '666666' });
    s3.addText(s.task, { x: s.x + 0.1, y: s.y + 2.3, w: 1.3, h: 0.6, fontSize: 9, fontFace: 'Microsoft YaHei', color: THEME.text });
    s3.addText('产出:', { x: s.x + 0.1, y: s.y + 3.0, w: 1.3, h: 0.3, fontSize: 10, fontFace: 'Microsoft YaHei', color: '666666' });
    s3.addText(s.output, { x: s.x + 0.1, y: s.y + 3.3, w: 1.3, h: 0.5, fontSize: 9, fontFace: 'Microsoft YaHei', color: THEME.secondary, bold: true });
});

// 箭头
for (let i = 0; i < 4; i++) {
    s3.addShape(pptx.shapes.RIGHT_ARROW, { x: 2.05 + i * 1.7, y: 3.0, w: 0.3, h: 0.5, fill: { color: '999999' } });
}

// ========== 第4页：成本与挑战 ==========
const s4 = pptx.addSlide();
s4.addText('成本与挑战：为何新药研发如此昂贵？', { x: 0.5, y: 0.4, w: 9, h: 0.8, fontSize: 32, fontFace: 'Microsoft YaHei', color: THEME.primary, bold: true });

// 成本构成
s4.addShape(pptx.shapes.RECTANGLE, { x: 0.5, y: 1.4, w: 4.3, h: 2.0, fill: { color: 'FFEBEE' }, line: { color: 'E53935', width: 2 } });
s4.addText('成本构成', { x: 0.7, y: 1.6, w: 3.9, h: 0.5, fontSize: 20, fontFace: 'Microsoft YaHei', color: 'C62828', bold: true });
s4.addText('💰 资金投入\n⏱️ 时间成本\n🎯 机会成本\n🔬 资源占用（平台/动物/临床中心）\n⚠️ 沉没成本', { x: 0.7, y: 2.1, w: 3.9, h: 1.2, fontSize: 14, fontFace: 'Microsoft YaHei', color: THEME.text });

// 三类关键瓶颈
s4.addShape(pptx.shapes.RECTANGLE, { x: 5.2, y: 1.4, w: 4.3, h: 2.0, fill: { color: 'FFF3E0' }, line: { color: 'F57C00', width: 2 } });
s4.addText('三类关键瓶颈', { x: 5.4, y: 1.6, w: 3.9, h: 0.5, fontSize: 20, fontFace: 'Microsoft YaHei', color: 'E65100', bold: true });
s4.addText('1. 时间与失败率：越往后阶段，失败代价越高\n2. 证据链与合规：临床前→临床的可转化性\n3. 数据质量与偏倚：实验可重复性', { x: 5.4, y: 2.1, w: 3.9, h: 1.2, fontSize: 13, fontFace: 'Microsoft YaHei', color: THEME.text });

// Go/No-Go决策点
s4.addShape(pptx.shapes.RECTANGLE, { x: 0.5, y: 3.7, w: 9, h: 2.3, fill: { color: 'E8F5E9' }, line: { color: '43A047', width: 2 } });
s4.addText('关键决策点：Go/No-Go 机制', { x: 0.7, y: 3.9, w: 8.6, h: 0.5, fontSize: 20, fontFace: 'Microsoft YaHei', color: THEME.secondary, bold: true });
s4.addText('靶点可信度？ → 先导可优化性？ → 临床前证据充分？ → 临床疗效显著？', { x: 0.7, y: 4.4, w: 8.6, h: 0.5, fontSize: 16, fontFace: 'Microsoft YaHei', color: THEME.text, align: 'center' });
s4.addText('核心逻辑：越往后阶段，证据等级越高、样本量越大、周期越长 → 成本呈跃迁式上升', { x: 0.7, y: 5.0, w: 8.6, h: 0.5, fontSize: 14, fontFace: 'Microsoft YaHei', color: '2E7D32', italic: true, align: 'center' });

// ========== 第5页：应用场景与决策 ==========
const s5 = pptx.addSlide();
s5.background = { color: THEME.light };
s5.addText('应用场景：研发挑战的四大典型场景', { x: 0.5, y: 0.4, w: 9, h: 0.8, fontSize: 32, fontFace: 'Microsoft YaHei', color: THEME.primary, bold: true });

const scenarios = [
    { title: '场景A：靶点可信度不足', desc: '不同队列/模型结论不一致；遗传学与药理学证据链断裂', impact: '反复验证、项目回退、早期投入沉没', color: 'E3F2FD', x: 0.5, y: 1.5 },
    { title: '场景B：实验到临床转化困难', desc: '体外有效但动物/人体无效；人群异质性导致信号稀释', impact: 'Ⅱ期失败常见；需精细分层或重新设计试验', color: 'E8F5E9', x: 5.2, y: 1.5 },
    { title: '场景C：多目标约束冲突', desc: '活性提升伴随溶解度下降；暴露不足；安全性风险', impact: '优化迭代次数多、周期长；可能陷入局部最优', color: 'FFF3E0', x: 0.5, y: 3.8 },
    { title: '场景D：数据与证据链挑战', desc: '数据分散、标准不一、偏倚与不可重复', impact: '模型与结论不稳、决策摇摆、试验设计不合理', color: 'FCE4EC', x: 5.2, y: 3.8 }
];

scenarios.forEach(s => {
    s5.addShape(pptx.shapes.RECTANGLE, { x: s.x, y: s.y, w: 4.3, h: 2.1, fill: { color: s.color }, line: { color: 'BBBBBB', width: 1 } });
    s5.addText(s.title, { x: s.x + 0.2, y: s.y + 0.2, w: 3.9, h: 0.5, fontSize: 16, fontFace: 'Microsoft YaHei', color: THEME.primary, bold: true });
    s5.addText(s.desc, { x: s.x + 0.2, y: s.y + 0.7, w: 3.9, h: 0.6, fontSize: 12, fontFace: 'Microsoft YaHei', color: '555555' });
    s5.addText('影响：' + s.impact, { x: s.x + 0.2, y: s.y + 1.4, w: 3.9, h: 0.6, fontSize: 11, fontFace: 'Microsoft YaHei', color: THEME.accent });
});

// ========== 第6页：课堂活动 ==========
const s6 = pptx.addSlide();
s6.addText('课堂活动与讨论', { x: 0.5, y: 0.4, w: 9, h: 0.8, fontSize: 32, fontFace: 'Microsoft YaHei', color: THEME.primary, bold: true });

// 1分钟投票
s6.addShape(pptx.shapes.RECTANGLE, { x: 0.5, y: 1.4, w: 4.3, h: 1.8, fill: { color: 'E1BEE7' }, line: { color: '8E24AA', width: 2 } });
s6.addText('1分钟投票', { x: 0.7, y: 1.6, w: 3.9, h: 0.4, fontSize: 18, fontFace: 'Microsoft YaHei', color: '6A1B9A', bold: true });
s6.addText('最"烧钱/烧时间"的阶段是哪一个？\n追问：理由属于哪类约束？\n（科学不确定性/工程资源/合规证据）', { x: 0.7, y: 2.1, w: 3.9, h: 0.9, fontSize: 13, fontFace: 'Microsoft YaHei', color: THEME.text });

// 情景卡练习
s6.addShape(pptx.shapes.RECTANGLE, { x: 5.2, y: 1.4, w: 4.3, h: 1.8, fill: { color: 'FFE0B2' }, line: { color: 'EF6C00', width: 2 } });
s6.addText('情景卡练习', { x: 5.4, y: 1.6, w: 3.9, h: 0.4, fontSize: 18, fontFace: 'Microsoft YaHei', color: 'E65100', bold: true });
s6.addText('两人一组抽取情景卡，分析：\n阶段 → 挑战类型 → 成本后果 → 下一步策略', { x: 5.4, y: 2.1, w: 3.9, h: 0.9, fontSize: 13, fontFace: 'Microsoft YaHei', color: THEME.text });

// 讨论问题
s6.addShape(pptx.shapes.RECTANGLE, { x: 0.5, y: 3.5, w: 9, h: 2.5, fill: { color: 'E0F2F1' }, line: { color: '00897B', width: 2 } });
s6.addText('核心讨论问题', { x: 0.7, y: 3.7, w: 8.6, h: 0.5, fontSize: 18, fontFace: 'Microsoft YaHei', color: '00695C', bold: true });
s6.addText('Q1: Ⅱ期出现"疗效趋势但不显著"，问题更可能来自哪里？（靶点/分子/患者分层/试验设计）\nQ2: 为什么很多公司宁愿在先导优化多花3个月，也不愿"带病上临床"？\nQ3: 出现轻度肝毒信号时，应该优先做什么？（换骨架/降低暴露/补充实验/终止）', { x: 0.7, y: 4.2, w: 8.6, h: 1.6, fontSize: 13, fontFace: 'Microsoft YaHei', color: THEME.text });

// ========== 第7页：谢谢 ==========
const s7 = pptx.addSlide();
s7.background = { color: THEME.primary };
s7.addShape(pptx.shapes.OVAL, { x: 8, y: 0.3, w: 2.5, h: 2.5, fill: { color: 'FFFFFF', transparency: 15 } });
s7.addShape(pptx.shapes.OVAL, { x: -0.8, y: 4.2, w: 3.5, h: 3.5, fill: { color: 'FFFFFF', transparency: 8 } });
s7.addText('谢谢', { x: 0.5, y: 2.5, w: 9, h: 1.5, fontSize: 72, fontFace: 'Microsoft YaHei', color: 'FFFFFF', bold: true, align: 'center' });
s7.addText('Thank You', { x: 0.5, y: 4.0, w: 9, h: 0.8, fontSize: 28, fontFace: 'Arial', color: '90CAF9', align: 'center' });
s7.addText('下一节：AI如何介入新药研发流程？', { x: 0.5, y: 5.0, w: 9, h: 0.5, fontSize: 18, fontFace: 'Microsoft YaHei', color: 'BBDEFB', align: 'center' });

// 保存
pptx.writeFile({ fileName: '/personal/AI备课助手/新药研发流程成本与挑战_图文并茂.pptx' })
    .then(() => console.log('✅ PPT生成成功！共7页'))
    .catch((err) => console.error('❌ 失败:', err));
