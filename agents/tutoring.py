import json
from .llm_client import LLMClient

TUTORING_SYSTEM_PROMPT = """你是一个耐心的 C 语言辅导老师，面向大一学生。你的学生刚刚提交了代码，另一位专家已经找出了问题清单。你的任务是针对每个问题生成学生能听懂的讲解。

## 核心原则
1. **用学生听得懂的语言**：避免术语堆砌，用打比方的方式解释概念。例如，"指针就像一个门牌号，它告诉你去哪个地址找数据"
2. **讲为什么错而不只是错在哪**：对于每个错误，解释错误背后的原理。例如分号不是"规则"，而是"语句的结束标记，编译器靠它分辨语句边界"
3. **先启发再给答案**：先指出问题方向，让学生自己想一想，再给出具体修改方案
4. **遵循教学规范**：不要写出超出当前教学进度的解法（如学生还在学循环就不要用递归、还在学数组就不要用指针）
5. **标注知识点薄弱环节**：如果某个概念反复出错，明确告诉学生"这是你目前需要加强的知识点"

## 输出格式
严格按以下 JSON 结构输出：

{
  "explanations": [
    {
      "error_index": <对应输入中 errors 数组的索引>,
      "concept": "<涉及的知识点名称>",
      "why_wrong": "<用通俗语言解释为什么这样写是错的>",
      "analogy": "<用生活中的例子打比方，帮助学生建立直觉>",
      "fix_guide": "<分步骤引导如何修改，先指出方向，再给具体改法>",
      "before_code": "<修改前的代码片段>",
      "after_code": "<修改后的代码片段>",
      "study_tip": "<建议复习的教材章节或练习方向>"
    }
  ],
  "corrected_full_code": "<完整修正后的代码>",
  "weak_points": ["<学生需要加强的知识点1>", "<知识点2>"],
  "encouragement": "<一句鼓励的话，肯定学生的努力>"
}

## 注意事项
- 如果代码完全正确且无优化空间，corrected_full_code 就是原代码，explanations 为空数组
- 修正代码必须保持原有的代码风格和命名习惯
- 不要在 JSON 外输出任何文字"""


class TutoringAgent:
    def __init__(self, llm: LLMClient = None):
        self.llm = llm or LLMClient()

    def tutor(self, analysis_report: dict, original_code: str,
              verification_feedback: dict = None) -> dict:
        """Generate tutoring response based on analysis report."""
        if not self.llm.available:
            return self._offline_tutor(analysis_report, original_code)

        user_message = self._build_message(analysis_report, original_code, verification_feedback)

        try:
            response = self.llm.chat(TUTORING_SYSTEM_PROMPT, user_message, temperature=0.4)
            return self._parse_response(response, original_code)
        except Exception as e:
            return self._offline_tutor(analysis_report, original_code, str(e))

    def tutor_stream(self, analysis_report: dict, original_code: str,
                     verification_feedback: dict = None):
        """Stream the tutoring process."""
        if not self.llm.available:
            result = self._offline_tutor(analysis_report, original_code)
            yield {"stage": "tutoring_done", "data": result}
            return

        user_message = self._build_message(analysis_report, original_code, verification_feedback)

        accumulated = ""
        try:
            for chunk in self.llm.chat_stream(TUTORING_SYSTEM_PROMPT, user_message, temperature=0.4):
                accumulated += chunk
                yield {"stage": "tutoring", "chunk": chunk}
        except Exception as e:
            result = self._offline_tutor(analysis_report, original_code, str(e))
            yield {"stage": "tutoring_done", "data": result}
            return

        result = self._parse_response(accumulated, original_code)
        yield {"stage": "tutoring_done", "data": result}

    def _build_message(self, analysis: dict, original_code: str,
                       verification_feedback: dict = None) -> str:
        errors = analysis.get("errors", [])
        summary = analysis.get("summary", "")

        parts = [
            "## 原始代码\n```c\n{}\n```".format(original_code),
            "## 分析报告\n整体评价: {}".format(summary),
        ]

        if errors:
            error_list = []
            for i, e in enumerate(errors):
                error_list.append(
                    f"### 问题 {i}\n"
                    f"- 类型: {e.get('type', '未知')}\n"
                    f"- 严重程度: {e.get('severity', '未知')}\n"
                    f"- 行号: {e.get('line', '未知')}\n"
                    f"- 标题: {e.get('title', '')}\n"
                    f"- 描述: {e.get('description', '')}\n"
                    f"- 根因: {e.get('root_cause', '')}\n"
                    f"- 相关代码: `{e.get('code_snippet', '')}`"
                )
            parts.append("## 检测到的问题\n" + "\n".join(error_list))
        else:
            parts.append("## 检测到的问题\n代码未发现明显问题。")

        if verification_feedback:
            parts.append("\n## 上一轮验证反馈\n{}".format(
                json.dumps(verification_feedback, ensure_ascii=False, indent=2)
            ))

        return "\n\n".join(parts)

    def _parse_response(self, response: str, original_code: str) -> dict:
        try:
            json_start = response.index("{")
            json_end = response.rindex("}") + 1
            return json.loads(response[json_start:json_end])
        except (ValueError, json.JSONDecodeError):
            return {
                "explanations": [],
                "corrected_full_code": original_code,
                "weak_points": [],
                "encouragement": "继续加油！",
                "raw_llm": response,
            }

    def _offline_tutor(self, analysis: dict, original_code: str, extra: str = "") -> dict:
        errors = analysis.get("errors", [])
        gcc = analysis.get("gcc_result", {})

        explanations = []
        for i, e in enumerate(errors):
            explanations.append({
                "error_index": i,
                "concept": "C 语言基础",
                "why_wrong": f"GCC 报告: {e.get('description', '未知错误')}",
                "analogy": "",
                "fix_guide": "请根据编译器的错误信息修正代码。常见修复方向：检查分号是否遗漏、括号是否匹配、变量是否已声明、头文件是否已包含。",
                "before_code": e.get("code_snippet", ""),
                "after_code": "",
                "study_tip": "建议回顾教材中关于 C 语言基本语法的章节",
            })

        return {
            "explanations": explanations,
            "corrected_full_code": original_code,
            "weak_points": ["C 语言基础语法"],
            "encouragement": "编译器给出了明确的错误提示，仔细阅读就能定位问题。加油！",
        }
