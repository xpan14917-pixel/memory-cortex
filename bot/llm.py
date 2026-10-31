"""DeepSeek / OpenAI 兼容的聊天客户端（纯标准库）。"""
import json
import time
import urllib.error
import urllib.request

from .log import get

log = get("llm")


class LLMError(Exception):
    pass


class LLM:
    def __init__(self, base_url, api_key, model, timeout=60, temperature=0.9,
                 max_tokens=400):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.temperature = temperature
        self.max_tokens = max_tokens

    def configure(self, **kw):
        for k, v in kw.items():
            if v is not None:
                setattr(self, k, v)

    def _raw_chat(self, messages, json_mode=False, temperature=None, max_tokens=None,
                  timeout=None):
        """返回完整响应体，便于排查空内容 / finish_reason。"""
        if not self.api_key:
            raise LLMError("未配置 DeepSeek API Key")
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature if temperature is None else temperature,
            "max_tokens": self.max_tokens if max_tokens is None else max_tokens,
            "stream": False,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions", data=body, method="POST"
        )
        req.add_header("Content-Type", "application/json")
        req.add_header("Authorization", f"Bearer {self.api_key}")
        with urllib.request.urlopen(req, timeout=timeout or self.timeout) as resp:
            return json.loads(resp.read().decode("utf-8", "replace"))

    def chat(self, messages, json_mode=False, temperature=None, max_tokens=None,
             timeout=None):
        if not self.api_key:
            raise LLMError("未配置 DeepSeek API Key")

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature if temperature is None else temperature,
            "max_tokens": self.max_tokens if max_tokens is None else max_tokens,
            "stream": False,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        last_err = None
        for attempt in range(3):
            req = urllib.request.Request(
                f"{self.base_url}/chat/completions", data=body, method="POST"
            )
            req.add_header("Content-Type", "application/json")
            req.add_header("Authorization", f"Bearer {self.api_key}")
            try:
                with urllib.request.urlopen(req, timeout=timeout or self.timeout) as resp:
                    raw = resp.read().decode("utf-8", "replace")
                data = json.loads(raw)
                choice = (data.get("choices") or [{}])[0]
                content = (choice.get("message") or {}).get("content")
                finish = choice.get("finish_reason")
                if not content or not content.strip():
                    last_err = f"空内容 finish_reason={finish} body={raw[:300]}"
                    log.warning("LLM 返回空内容：%s", last_err)
                    continue
                return content
            except urllib.error.HTTPError as e:
                detail = e.read().decode("utf-8", "replace")[:400]
                last_err = f"HTTP {e.code}: {detail}"
                if e.code in (400, 401, 402, 403, 404):
                    raise LLMError(last_err) from e
            except Exception as e:  # noqa: BLE001
                last_err = repr(e)
            time.sleep(1.5 * (attempt + 1))
        raise LLMError(f"LLM 调用失败：{last_err}")

    def chat_json(self, messages, **kw):
        raw = self.chat(messages, json_mode=True, **kw)
        return parse_json(raw)


def parse_json(raw):
    """容错解析模型返回的 JSON（去代码块、截取首尾大括号）。"""
    if isinstance(raw, dict):
        return raw
    text = (raw or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError(f"模型没有返回 JSON：{text[:200]}")
    return json.loads(text[start : end + 1])
