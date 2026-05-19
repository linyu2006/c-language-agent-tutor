import json
from sandbox.executor import compile_code, run_test_cases, create_workspace, cleanup_workspace
from .llm_client import LLMClient

VERIFICATION_SYSTEM_PROMPT = """你是 C 语言代码验证专家。你的任务是：

1. 审查编译结果 — 分析编译是否成功，如有错误判断是哪类问题
2. 分析测试用例结果 — 对比预期输出和实际输出，判断测试是否通过
3. 如果测试失败，推断可能的原因并反馈给辅导 Agent

输出 JSON：
{
  "compilation_ok": <true/false>,
  "compile_errors": "<编译错误信息，无则为空>",
  "compile_warnings": ["<警告列表>"],
  "test_summary": {
    "total": <总测试数>,
    "passed": <通过数>,
    "failed": <失败数>
  },
  "test_details": [<逐条测试结果>],
  "failure_analysis": "<如果全部通过则为空，否则分析可能的原因>",
  "all_passed": <true/false>
}"""


class VerificationAgent:
    def __init__(self, llm: LLMClient = None):
        self.llm = llm or LLMClient()

    def verify(self, code: str, test_cases: list) -> dict:
        """Verify code by compiling and running test cases."""
        workspace = create_workspace()

        try:
            test_results = run_test_cases(code, test_cases, workspace)

            if test_results and test_results[0].get("compilation_failed"):
                result = {
                    "compilation_ok": False,
                    "compile_errors": test_results[0].get("stderr", ""),
                    "compile_warnings": [],
                    "test_summary": {"total": len(test_cases), "passed": 0, "failed": len(test_cases)},
                    "test_details": [],
                    "failure_analysis": "编译失败，需要修正语法错误后重试。",
                    "all_passed": False,
                }
            else:
                total = len(test_results)
                passed = sum(1 for r in test_results if r["passed"])
                result = {
                    "compilation_ok": True,
                    "compile_errors": "",
                    "compile_warnings": [],
                    "test_summary": {"total": total, "passed": passed, "failed": total - passed},
                    "test_details": test_results,
                    "failure_analysis": "",
                    "all_passed": passed == total,
                }

            if not result["all_passed"] and self.llm.available:
                result["failure_analysis"] = self._analyze_failures(code, test_results)

            return result
        finally:
            cleanup_workspace(workspace)

    def verify_stream(self, code: str, test_cases: list):
        """Stream the verification process."""
        yield {"stage": "verifying", "message": "正在编译代码..."}

        result = self.verify(code, test_cases)

        if result["compilation_ok"]:
            yield {"stage": "verifying", "message": f"编译成功，运行 {result['test_summary']['total']} 个测试用例..."}

        yield {"stage": "verification_done", "data": result}

    def _analyze_failures(self, code: str, test_results: list) -> str:
        if not self.llm.available:
            return self._basic_failure_analysis(test_results)

        failures = [r for r in test_results if not r.get("passed")]
        user_msg = f"代码:\n```c\n{code}\n```\n\n失败的测试:\n{json.dumps(failures, ensure_ascii=False, indent=2)}"

        try:
            return self.llm.chat(VERIFICATION_SYSTEM_PROMPT, user_msg, temperature=0.2, max_tokens=1024)
        except Exception:
            return self._basic_failure_analysis(test_results)

    def _basic_failure_analysis(self, test_results: list) -> str:
        failures = [r for r in test_results if not r.get("passed")]
        reasons = []
        for f in failures:
            if f.get("timed_out"):
                reasons.append(f"测试 {f['index']}: 超时（可能死循环或效率过低）")
            elif f.get("runtime_error"):
                reasons.append(f"测试 {f['index']}: 运行时错误 — {f.get('stderr', '未知')}")
            else:
                reasons.append(
                    f"测试 {f['index']}：输入 '{f['input']}'，"
                    f"期望输出 '{f['expected_output']}'，"
                    f"实际输出 '{f['actual_output']}'"
                )
        return "; ".join(reasons)
