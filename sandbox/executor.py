import os
import subprocess
import tempfile
import shutil
import hashlib
import time

WORKSPACE_ROOT = os.path.join(os.path.dirname(os.path.dirname(__file__)), "workspace")
COMPILE_TIMEOUT = 15
RUN_TIMEOUT = 5


def create_workspace() -> str:
    """Create a unique workspace directory for this session."""
    session_id = hashlib.md5(str(time.time()).encode()).hexdigest()[:12]
    path = os.path.join(WORKSPACE_ROOT, session_id)
    os.makedirs(path, exist_ok=True)
    return path


def cleanup_workspace(workspace: str) -> None:
    """Remove workspace directory and its contents."""
    try:
        shutil.rmtree(workspace, ignore_errors=True)
    except Exception:
        pass


def gcc_static_check(code: str) -> dict:
    """Run GCC syntax-only check and return warnings/errors."""
    workspace = create_workspace()
    src_path = os.path.join(workspace, "check.c")

    try:
        with open(src_path, "w", encoding="utf-8") as f:
            f.write(code)

        result = subprocess.run(
            ["gcc", "-Wall", "-Wextra", "-Wpedantic", "-fsyntax-only", src_path],
            capture_output=True, text=True, timeout=COMPILE_TIMEOUT,
        )

        lines = result.stderr.strip().split("\n") if result.stderr.strip() else []
        errors = []
        warnings = []

        for line in lines:
            entry = {"raw": line.strip()}
            if "error:" in line:
                errors.append(entry)
            elif "warning:" in line:
                warnings.append(entry)

        return {
            "has_errors": result.returncode != 0 or len(errors) > 0,
            "errors": errors,
            "warnings": warnings,
            "raw_output": result.stderr.strip(),
        }
    except subprocess.TimeoutExpired:
        return {"has_errors": True, "errors": [{"raw": "编译检查超时"}], "warnings": [], "raw_output": ""}
    except FileNotFoundError:
        return {"has_errors": False, "errors": [], "warnings": [],
                "raw_output": "", "gcc_missing": True}
    finally:
        cleanup_workspace(workspace)


def compile_code(code: str, workspace: str) -> dict:
    """Compile C code and return result with binary path."""
    src_path = os.path.join(workspace, "program.c")
    bin_path = os.path.join(workspace, "program.exe")

    with open(src_path, "w", encoding="utf-8") as f:
        f.write(code)

    try:
        result = subprocess.run(
            ["gcc", "-Wall", "-Wextra", "-o", bin_path, src_path],
            capture_output=True, text=True, timeout=COMPILE_TIMEOUT,
        )

        return {
            "success": result.returncode == 0 and os.path.exists(bin_path),
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
            "binary": bin_path if os.path.exists(bin_path) else None,
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "stdout": "", "stderr": "编译超时", "binary": None}
    except FileNotFoundError:
        return {"success": False, "stdout": "", "stderr": "GCC 未找到，请安装 MinGW-w64", "binary": None}


def run_code(binary: str, stdin_input: str = "") -> dict:
    """Run compiled binary with optional stdin input and capture output."""
    if not binary or not os.path.exists(binary):
        return {"success": False, "stdout": "", "stderr": "可执行文件不存在", "timed_out": False}

    try:
        result = subprocess.run(
            [binary],
            input=stdin_input,
            capture_output=True, text=True,
            timeout=RUN_TIMEOUT,
        )

        return {
            "success": result.returncode == 0,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
            "return_code": result.returncode,
            "timed_out": False,
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "stdout": "", "stderr": "程序运行超时 (>5s)", "timed_out": True}


def run_test_cases(code: str, test_cases: list, workspace: str) -> list:
    """Compile code and run multiple test cases. Returns detailed results."""
    compile_result = compile_code(code, workspace)
    if not compile_result["success"]:
        return [{"compilation_failed": True, "stderr": compile_result["stderr"]}]

    results = []
    for i, tc in enumerate(test_cases):
        run_result = run_code(compile_result["binary"], tc.get("input", ""))

        passed = False
        if run_result["success"]:
            actual = run_result["stdout"].strip()
            expected = tc.get("expected_output", "").strip()
            passed = actual == expected

        results.append({
            "index": i + 1,
            "input": tc.get("input", ""),
            "expected_output": tc.get("expected_output", ""),
            "actual_output": run_result.get("stdout", ""),
            "stderr": run_result.get("stderr", ""),
            "passed": passed,
            "timed_out": run_result.get("timed_out", False),
            "runtime_error": not run_result["success"] and not run_result.get("timed_out"),
        })

    return results
