import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import List, Dict, Any


@dataclass
class ChatMessage:
    role: str
    text: str


class OllamaTutorClient:
    def __init__(self, model: str = "llama3.3", base_url: str = "http://127.0.0.1:11434") -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.history: List[ChatMessage] = []

    def send(self, user_text: str, system_instruction: str) -> str:
        self.history.append(ChatMessage(role="user", text=user_text))

        payload = {
            "model": self.model,
            "stream": False,
            "messages": [
                {"role": "system", "content": system_instruction},
                *[
                    {"role": msg.role, "content": msg.text}
                    for msg in self.history
                ],
            ],
        }

        endpoint = f"{self.base_url}/api/chat"
        request = urllib.request.Request(
            endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=300) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            self.history.pop()
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Ollama API error ({exc.code}): {body}") from exc
        except urllib.error.URLError as exc:
            self.history.pop()
            raise RuntimeError(
                "Could not connect to Ollama at http://127.0.0.1:11434. "
                "Confirm `brew services start ollama` worked and the model is installed."
            ) from exc

        parsed = self._safe_json_load(raw)
        text = self._extract_response_text(parsed)
        self.history.append(ChatMessage(role="assistant", text=text))
        return text

    @staticmethod
    def _safe_json_load(raw: str) -> Dict[str, Any]:
        try:
            value = json.loads(raw)
            return value if isinstance(value, dict) else {}
        except Exception:
            return {}

    @staticmethod
    def _extract_response_text(response_json: Dict[str, Any]) -> str:
        message = response_json.get("message", {})
        if isinstance(message, dict):
            content = message.get("content", "")
            if isinstance(content, str) and content.strip():
                return content.strip()
        return "Ollama returned an empty response."
