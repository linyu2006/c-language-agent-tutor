from agents.understanding import UnderstandingAgent
from agents.tutoring import TutoringAgent
from agents.verification import VerificationAgent
from agents.llm_client import LLMClient

MAX_RETRY_ROUNDS = 3


class Orchestrator:
    """Coordinates the three-agent pipeline with closed-loop feedback."""

    def __init__(self):
        llm = LLMClient()
        self.understanding = UnderstandingAgent(llm)
        self.tutoring = TutoringAgent(llm)
        self.verification = VerificationAgent(llm)

    def process(self, code: str, problem_description: str = "",
                test_cases: list = None):
        """Process code through the agent pipeline, yielding progress events.

        Pipeline: Understanding -> Tutoring -> Verification
        If verification fails -> back to Tutoring (max 3 rounds).
        """
        if test_cases is None:
            test_cases = []

        yield {"agent": "orchestrator", "stage": "start", "message": "开始分析..."}

        # Step 1: Understanding Agent
        yield {"agent": "understanding", "stage": "start", "message": "理解 Agent 正在分析代码..."}

        analysis_report = None
        for event in self.understanding.analyze_stream(code, problem_description):
            wrapped = {"agent": "understanding", **event}
            yield wrapped
            if event.get("stage") == "analysis_done":
                analysis_report = event["data"]

        if analysis_report is None:
            yield {"agent": "orchestrator", "stage": "error", "message": "分析阶段失败"}
            return

        yield {"agent": "understanding", "stage": "done",
               "data": analysis_report, "message": "代码分析完成"}

        # Step 2-4: Tutoring <-> Verification loop
        current_code = code
        round_num = 0
        verification_feedback = None

        while round_num < MAX_RETRY_ROUNDS:
            round_num += 1
            yield {"agent": "orchestrator", "stage": "round",
                   "round": round_num, "max_rounds": MAX_RETRY_ROUNDS}

            # Tutoring
            yield {"agent": "tutoring", "stage": "start",
                   "message": f"辅导 Agent 正在生成讲解 (第 {round_num} 轮)..."}

            tutoring_result = None
            for event in self.tutoring.tutor_stream(
                analysis_report, current_code, verification_feedback
            ):
                yield {"agent": "tutoring", **event}
                if event.get("stage") == "tutoring_done":
                    tutoring_result = event["data"]

            if tutoring_result is None:
                yield {"agent": "orchestrator", "stage": "error", "message": "辅导阶段失败"}
                return

            yield {"agent": "tutoring", "stage": "done",
                   "data": tutoring_result, "message": "辅导建议生成完成"}

            corrected_code = tutoring_result.get("corrected_full_code", current_code)

            # Verification
            if not test_cases:
                yield {"agent": "verification", "stage": "skip",
                       "message": "未提供测试用例，跳过验证"}
                yield {"agent": "orchestrator", "stage": "done",
                       "data": {
                           "analysis_report": analysis_report,
                           "tutoring_result": tutoring_result,
                           "verification_result": None,
                           "final_code": corrected_code,
                       }}
                return

            yield {"agent": "verification", "stage": "start",
                   "message": f"验证 Agent 正在编译运行 (第 {round_num} 轮)..."}

            verification_result = None
            for event in self.verification.verify_stream(corrected_code, test_cases):
                yield {"agent": "verification", **event}
                if event.get("stage") == "verification_done":
                    verification_result = event["data"]

            if verification_result is None:
                yield {"agent": "orchestrator", "stage": "error", "message": "验证阶段失败"}
                return

            yield {"agent": "verification", "stage": "done",
                   "data": verification_result, "message": "验证完成"}

            if verification_result.get("all_passed"):
                yield {"agent": "orchestrator", "stage": "done",
                       "data": {
                           "analysis_report": analysis_report,
                           "tutoring_result": tutoring_result,
                           "verification_result": verification_result,
                           "final_code": corrected_code,
                           "rounds": round_num,
                       },
                       "message": f"所有 {verification_result['test_summary']['total']} 个测试通过！"}
                return

            # Feedback loop: prepare for retry
            verification_feedback = {
                "failed_tests": [r for r in verification_result.get("test_details", []) if not r["passed"]],
                "failure_analysis": verification_result.get("failure_analysis", ""),
                "compile_errors": verification_result.get("compile_errors", ""),
            }
            current_code = corrected_code
            yield {"agent": "orchestrator", "stage": "retry",
                   "message": f"{verification_result['test_summary']['failed']} 个测试未通过，反馈给辅导 Agent 重试...",
                   "retry_reason": verification_feedback["failure_analysis"]}

        # Max rounds exhausted
        yield {"agent": "orchestrator", "stage": "done",
               "data": {
                   "analysis_report": analysis_report,
                   "tutoring_result": tutoring_result,
                   "verification_result": verification_result,
                   "final_code": current_code,
                   "rounds": round_num,
                   "max_rounds_reached": True,
               },
               "message": "达到最大重试次数，以下是当前最佳结果"}
