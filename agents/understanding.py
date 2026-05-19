import json
from .llm_client import LLMClient
from sandbox.executor import gcc_static_check

UNDERSTANDING_SYSTEM_PROMPT = """你是一个 C 语言代码分析专家，擅长发现代码中的语法错误、逻辑漏洞和内存问题。

你的任务是分析学生提交的 C 代码，结合 GCC 编译器的警告信息，通过长链推理逐一排查以下问题：

1. **语法错误**：缺少分号、括号不匹配、类型错误、未声明的标识符、头文件遗漏等
2. **逻辑漏洞**：条件判断错误、循环边界问题 (off-by-one)、死循环、分支遗漏、返回值缺失等
3. **内存问题**：缓冲区溢出、未初始化变量、野指针、内存泄漏 (malloc 后无 free)、数组越界、栈溢出递归
4. **未定义行为**：溢出 (signed overflow)、序列点问题、空指针解引用、use-after-free / double-free

分析步骤（你必须在回答中完整展示推理链）：
- 第 1 步：逐行解读代码，标注有问题的行
- 第 2 步：对每个问题，分析其根因（是语法生疏、概念混淆、还是逻辑设计问题）
- 第 3 步：评估严重程度（critical=编译失败, major=运行结果错误, minor=代码风格或可维护性问题）

输出格式：严格按以下 JSON 结构输出，不要包含任何 JSON 之外的文字：

{
  "errors": [
    {
      "type": "syntax_error|logic_error|memory_issue|undefined_behavior",
      "severity": "critical|major|minor",
      "line": <行号，未知填null>,
      "title": "<问题标题>",
      "description": "<详细描述>",
      "code_snippet": "<相关代码片段>",
      "root_cause": "<根因分析>"
    }
  ],
  "summary": "<整体评价，1-2句话>"
}"""


class UnderstandingAgent:
    def __init__(self, llm: LLMClient = None):
        self.llm = llm or LLMClient()

    def analyze(self, code: str, problem_description: str = "") -> dict:
        """Analyze C code and return structured error report."""
        gcc_result = gcc_static_check(code)

        if not self.llm.available:
            return self._gcc_only_report(gcc_result, code)

        user_message = self._build_message(code, problem_description, gcc_result)

        try:
            response = self.llm.chat(UNDERSTANDING_SYSTEM_PROMPT, user_message, temperature=0.2)
            return self._parse_response(response, gcc_result)
        except Exception as e:
            return self._gcc_only_report(gcc_result, code, f"LLM 调用失败: {str(e)}")

    def analyze_stream(self, code: str, problem_description: str = ""):
        """Stream the analysis process."""
        gcc_result = gcc_static_check(code)

        yield {"stage": "gcc_check", "data": gcc_result}

        if not self.llm.available:
            report = self._gcc_only_report(gcc_result, code)
            yield {"stage": "analysis_done", "data": report}
            return

        user_message = self._build_message(code, problem_description, gcc_result)

        accumulated = ""
        try:
            for chunk in self.llm.chat_stream(UNDERSTANDING_SYSTEM_PROMPT, user_message, temperature=0.2):
                accumulated += chunk
                yield {"stage": "analyzing", "chunk": chunk}
        except Exception as e:
            report = self._gcc_only_report(gcc_result, code, f"LLM 调用失败: {str(e)}")
            yield {"stage": "analysis_done", "data": report}
            return

        report = self._parse_response(accumulated, gcc_result)
        yield {"stage": "analysis_done", "data": report}

    def _build_message(self, code: str, problem_description: str, gcc_result: dict) -> str:
        parts = ["## 学生提交的代码\n```c\n{}\n```".format(code)]

        if problem_description:
            parts.append("## 题目要求\n{}".format(problem_description))

        if gcc_result.get("gcc_missing"):
            parts.append("## GCC 状态\nGCC 未安装，无法提供静态检查信息。")
        elif gcc_result.get("raw_output"):
            parts.append("## GCC 编译器输出\n```\n{}\n```".format(gcc_result["raw_output"]))
        else:
            parts.append("## GCC 编译器输出\n编译通过，无警告或错误。")

        return "\n\n".join(parts)

    def _parse_response(self, response: str, gcc_result: dict) -> dict:
        try:
            json_start = response.index("{")
            json_end = response.rindex("}") + 1
            data = json.loads(response[json_start:json_end])
            data["gcc_result"] = gcc_result
            return data
        except (ValueError, json.JSONDecodeError):
            return {
                "errors": [],
                "summary": "无法解析 LLM 输出，请查看原始 GCC 检查结果。",
                "gcc_result": gcc_result,
                "raw_llm": response,
            }

    def _gcc_only_report(self, gcc_result: dict, code: str, extra: str = "") -> dict:
        errors = []
        for e in gcc_result.get("errors", []):
            errors.append({
                "type": "syntax_error",
                "severity": "critical",
                "line": None,
                "title": "编译错误",
                "description": e["raw"],
                "code_snippet": "",
                "root_cause": "语法错误导致编译失败",
            })
        for w in gcc_result.get("warnings", []):
            errors.append({
                "type": "syntax_error",
                "severity": "minor",
                "line": None,
                "title": "编译警告",
                "description": w["raw"],
                "code_snippet": "",
                "root_cause": "代码存在潜在问题",
            })

        summary = "(仅 GCC 静态检查"
        if extra:
            summary += f"；{extra}"
        summary += ")"

        return {
            "errors": errors,
            "summary": summary,
            "gcc_result": gcc_result,
        }
