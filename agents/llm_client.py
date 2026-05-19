import os
import anthropic
from dotenv import load_dotenv

load_dotenv()


class LLMClient:
    def __init__(self):
        self.api_key = os.getenv("ANTHROPIC_API_KEY", "")
        self.model = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")
        self.client = anthropic.Anthropic(api_key=self.api_key) if self.api_key else None

    @property
    def available(self):
        return self.client is not None

    def chat(self, system_prompt: str, user_message: str, temperature: float = 0.3,
             max_tokens: int = 4096) -> str:
        """Send a message and get the full response."""
        if not self.client:
            return self._fallback_response(user_message)

        response = self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
        )
        return response.content[0].text

    def chat_stream(self, system_prompt: str, user_message: str, temperature: float = 0.3,
                    max_tokens: int = 4096):
        """Stream the response token by token."""
        if not self.client:
            yield from self._fallback_stream(user_message)
            return

        with self.client.messages.stream(
            model=self.model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
        ) as stream:
            for text in stream.text_stream:
                yield text

    def _fallback_response(self, user_message: str) -> str:
        return (
            "[本地分析模式] LLM 未配置 — 仅执行 GCC 静态检查。\n"
            "请在 .env 文件中设置 ANTHROPIC_API_KEY 以启用智能分析。"
        )

    def _fallback_stream(self, user_message: str):
        yield self._fallback_response(user_message)
