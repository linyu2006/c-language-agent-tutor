import json
import asyncio
import os
from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from orchestrator import Orchestrator

app = FastAPI(title="C 语言智能辅导系统")

app.mount("/static", StaticFiles(directory="static"), name="static")

_INDEX_HTML = None


def _load_index():
    global _INDEX_HTML
    if _INDEX_HTML is None:
        path = os.path.join(os.path.dirname(__file__), "templates", "index.html")
        with open(path, "r", encoding="utf-8") as f:
            _INDEX_HTML = f.read()
    return _INDEX_HTML


@app.get("/", response_class=HTMLResponse)
async def index():
    return HTMLResponse(content=_load_index())


@app.post("/analyze")
async def analyze(
    code: str = Form(...),
    problem: str = Form(default=""),
    test_inputs: str = Form(default=""),
    test_outputs: str = Form(default=""),
):
    test_cases = _parse_test_cases(test_inputs, test_outputs)

    async def event_stream():
        orchestrator = Orchestrator()

        try:
            for event in orchestrator.process(code, problem, test_cases):
                json_data = json.dumps(event, ensure_ascii=False)
                yield f"data: {json_data}\n\n"
                await asyncio.sleep(0.01)

            yield "data: [DONE]\n\n"
        except Exception as e:
            error_event = json.dumps({
                "agent": "system", "stage": "error",
                "message": f"系统错误: {str(e)}"
            }, ensure_ascii=False)
            yield f"data: {error_event}\n\n"
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _parse_test_cases(test_inputs: str, test_outputs: str) -> list:
    inputs = [line.strip() for line in test_inputs.strip().split("\n") if line.strip()]
    outputs = [line.strip() for line in test_outputs.strip().split("\n") if line.strip()]

    if not inputs and not outputs:
        return []

    max_len = max(len(inputs), len(outputs))
    while len(inputs) < max_len:
        inputs.append("")
    while len(outputs) < max_len:
        outputs.append("")

    return [
        {"input": inp, "expected_output": out}
        for inp, out in zip(inputs, outputs)
    ]


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8080, log_level="info")
