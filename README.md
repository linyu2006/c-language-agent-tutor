# C 语言智能辅导系统

基于多 Agent 协作的 C 语言课程作业辅导工具，解决学生在学习 C 语言时遇到的调试困难、逻辑理解慢、作业质量参差不齐的核心痛点。

## 架构

```
用户提交代码 + 题目描述
        │
        ▼
  ┌─────────────────┐
  │   理解 Agent     │  GCC 静态检查 + LLM 深度推理
  │   代码分析       │  定位语法/逻辑/内存问题
  └────────┬────────┘
           │ 错误报告
           ▼
  ┌─────────────────┐
  │   辅导 Agent     │  错误类型 → 针对性讲解
  │   生成建议       │  符合教学规范的修正方案
  └────────┬────────┘
           │ 修正代码
           ▼
  ┌─────────────────┐
  │   验证 Agent     │  编译 + 多组测试用例
  │   编译运行       │  逐条对比期望/实际输出
  └────────┬────────┘
           │
     ┌─────┴────── 测试失败则回传辅导 Agent 重试（最多 3 轮）
     │
     ▼
  最终结果（分析报告 + 辅导建议 + 验证结果 + 修正代码）
```

## 快速开始

### 环境要求

- Python 3.10+
- GCC (MinGW-w64 / Linux GCC)

### 安装

```bash
pip install -r requirements.txt
```

### 配置 LLM（可选）

```bash
cp .env.example .env
# 编辑 .env，填入 Anthropic API Key
```

不配置 LLM 也能使用 GCC 静态检查 + 验证功能。

### 启动

```bash
python app.py
```

浏览器打开 http://127.0.0.1:8080

## 使用流程

1. 粘贴 C 代码到代码编辑区
2. 填写题目描述（可选）
3. 展开「测试用例」，填入输入和期望输出（可选，每行一组）
4. 点击「提交分析」
5. 右侧实时显示三个 Agent 的协作分析结果

## 项目结构

```
├── app.py                  # FastAPI 入口，SSE 流式响应
├── orchestrator.py         # 三 Agent 协调器 + 闭环反馈
├── agents/
│   ├── llm_client.py       # Anthropic API 客户端
│   ├── understanding.py    # 理解 Agent (GCC + LLM)
│   ├── tutoring.py         # 辅导 Agent
│   └── verification.py     # 验证 Agent
├── sandbox/
│   └── executor.py         # 安全编译执行沙箱
├── static/                 # 前端资源
├── templates/              # HTML 模板
└── workspace/              # 临时编译目录 (已 gitignore)
```

## 技术栈

| 层 | 技术 |
|---|---|
| 后端 | FastAPI + uvicorn |
| LLM | Anthropic Claude API |
| 编译 | GCC (MinGW-w64) |
| 前端 | 原生 HTML/CSS/JS + SSE 流式渲染 |
