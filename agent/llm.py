"""OpenAI-compatible chat client (vLLM / llama.cpp) with optional JSON-schema constrained output."""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from .config import Config


class LLMError(RuntimeError):
    pass


@dataclass
class LLMReply:
    content: str = ""
    tool_calls: list[dict] = field(default_factory=list)  # [{"name":..., "arguments": {...}}]
    latency: float = 0.0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    raw: dict = field(default_factory=dict)


_THINK = re.compile(r"<think>.*?</think>", re.S)
_TOOL_TAG = re.compile(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", re.S)


def strip_think(text: str) -> str:
    text = _THINK.sub("", text or "")
    if "</think>" in text:  # R1 sometimes omits the opening tag
        text = text.split("</think>", 1)[1]
    return text.strip()


def extract_json(text: str) -> Any:
    """Parse the first JSON object/array in a model reply (fenced or bare)."""
    text = strip_think(text)
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fence:
        text = fence.group(1)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start = min([i for i in (text.find("{"), text.find("[")) if i >= 0], default=-1)
    if start < 0:
        raise LLMError(f"no JSON in reply: {text[:200]!r}")
    dec = json.JSONDecoder()
    try:
        obj, _ = dec.raw_decode(text[start:])
        return obj
    except json.JSONDecodeError as e:
        raise LLMError(f"bad JSON in reply: {e}: {text[:200]!r}") from e


class LLM:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.client = httpx.Client(timeout=cfg.llm_timeout)
        self.calls = 0
        self.total_latency = 0.0

    # ------------------------------------------------------------------ R1 / llama.cpp style
    @staticmethod
    def render_r1(messages: list[dict]) -> str:
        """Chat messages -> DeepSeek-R1 prompt. The empty <think></think> block is pre-filled so the model answers
        directly (and the JSON grammar constrains the very first token)."""
        system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
        out = ["<｜begin▁of▁sentence｜>" + system]
        for m in messages:
            r = m["role"]
            if r == "system":
                continue
            if r == "user":
                out.append("<｜User｜>" + m["content"])
            elif r == "assistant":
                txt = m.get("content") or ""
                for tc in m.get("tool_calls") or []:
                    fn = tc["function"]
                    txt += json.dumps({"tool": fn["name"], "arguments": json.loads(fn["arguments"])})
                out.append("<｜Assistant｜>" + txt + "<｜end▁of▁sentence｜>")
            elif r == "tool":
                out.append("<｜User｜>TOOL RESULT: " + m["content"])
        return "".join(out) + "<｜Assistant｜><think>\n\n</think>\n\n"

    @staticmethod
    def tools_schema(tools: list[dict]) -> tuple[dict, str]:
        """One-of schema: either a tool call {tool, arguments} or {tool: 'done'}; plus a text description."""
        alts, lines = [], []
        for t in tools:
            fn = t["function"]
            alts.append({"type": "object", "properties": {"tool": {"const": fn["name"]}, "arguments": fn["parameters"]},
                         "required": ["tool", "arguments"]})
            lines.append(f"- {fn['name']}: {fn['description']} Arguments: {json.dumps(fn['parameters']['properties'], separators=(',', ':'))}")
        alts.append({"type": "object", "properties": {"tool": {"const": "done"}}, "required": ["tool"]})
        return {"anyOf": alts}, "\n".join(lines)

    def _completion(self, messages: list[dict], tools: list[dict] | None, schema: dict | None, max_tokens: int) -> LLMReply:
        msgs = messages
        sch = schema
        if tools:
            sch, desc = self.tools_schema(tools)
            msgs = [dict(m) for m in messages]
            sys_i = next(i for i, m in enumerate(msgs) if m["role"] == "system")
            msgs[sys_i]["content"] += ("\n\nTOOLS (reply with exactly one JSON object {\"tool\": name, \"arguments\": {...}}; "
                                       "when the work is complete reply {\"tool\": \"done\"}):\n" + desc)
        body: dict[str, Any] = {"model": self.cfg.llm_model, "prompt": self.render_r1(msgs), "max_tokens": max_tokens,
                                "temperature": self.cfg.temperature, "stop": ["<｜end▁of▁sentence｜>", "<｜User｜>"]}
        if sch:
            body["json_schema"] = sch
        headers = {"Authorization": f"Bearer {self.cfg.llm_key}"}
        last: Exception | None = None
        for attempt in range(3):
            t0 = time.time()
            try:
                r = self.client.post(f"{self.cfg.llm_url}/completions", json=body, headers=headers)
                if r.status_code >= 400:
                    raise LLMError(f"HTTP {r.status_code}: {r.text[:400]}")
                data = r.json()
                break
            except (httpx.HTTPError, LLMError) as e:
                last = e
                if isinstance(e, LLMError) and "HTTP 4" in str(e):
                    raise
                time.sleep(1 + attempt)
        else:
            raise LLMError(f"LLM unreachable: {last}")
        dt = time.time() - t0
        self.calls += 1
        self.total_latency += dt
        text = data["choices"][0]["text"]
        usage = data.get("usage", {})
        calls: list[dict] = []
        content = strip_think(text)
        if tools:
            try:
                obj = json.loads(content)
            except json.JSONDecodeError:
                obj = {"tool": "done"}
            if obj.get("tool") not in (None, "done"):
                calls.append({"name": obj["tool"], "arguments": obj.get("arguments", {})})
            content = "" if calls else "DONE"
        return LLMReply(content=content, tool_calls=calls, latency=dt, prompt_tokens=usage.get("prompt_tokens", 0),
                        completion_tokens=usage.get("completion_tokens", 0), raw=data)

    def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        schema: dict | None = None,
        schema_name: str = "out",
        max_tokens: int | None = None,
    ) -> LLMReply:
        if self.cfg.llm_call_style == "json":
            return self._completion(messages, tools, schema, max_tokens or self.cfg.max_tokens)
        body: dict[str, Any] = {
            "model": self.cfg.llm_model,
            "messages": messages,
            "temperature": self.cfg.temperature,
            "max_tokens": max_tokens or self.cfg.max_tokens,
        }
        if tools:
            body["tools"] = tools
            body["tool_choice"] = "auto"
        if schema:
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": schema_name, "schema": schema, "strict": True},
            }
        headers = {"Authorization": f"Bearer {self.cfg.llm_key}"}
        last: Exception | None = None
        for attempt in range(3):
            t0 = time.time()
            try:
                r = self.client.post(f"{self.cfg.llm_url}/chat/completions", json=body, headers=headers)
                if r.status_code >= 500:
                    raise LLMError(f"HTTP {r.status_code}: {r.text[:300]}")
                if r.status_code >= 400:
                    raise LLMError(f"HTTP {r.status_code}: {r.text[:500]}")
                data = r.json()
                break
            except (httpx.HTTPError, LLMError) as e:
                last = e
                if isinstance(e, LLMError) and "HTTP 4" in str(e):
                    raise
                time.sleep(1 + attempt)
        else:
            raise LLMError(f"LLM unreachable: {last}")
        dt = time.time() - t0
        self.calls += 1
        self.total_latency += dt
        msg = data["choices"][0]["message"]
        calls = []
        for tc in msg.get("tool_calls") or []:
            fn = tc.get("function", {})
            args = fn.get("arguments", {})
            if isinstance(args, str):
                try:
                    args = json.loads(args) if args.strip() else {}
                except json.JSONDecodeError:
                    args = {"__unparsed__": args}
            calls.append({"name": fn.get("name"), "arguments": args})
        content = msg.get("content") or ""
        if not calls:  # some servers leave <tool_call> tags in the content
            for m in _TOOL_TAG.finditer(content):
                try:
                    obj = json.loads(m.group(1))
                    calls.append({"name": obj.get("name"), "arguments": obj.get("arguments", {})})
                except json.JSONDecodeError:
                    continue
            if calls:
                content = _TOOL_TAG.sub("", content).strip()
        usage = data.get("usage", {})
        return LLMReply(
            content=strip_think(content),
            tool_calls=calls,
            latency=dt,
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
            raw=data,
        )

    def json_out(self, messages: list[dict], schema: dict, name: str = "out", max_tokens: int | None = None) -> tuple[Any, LLMReply]:
        reply = self.chat(messages, schema=schema, schema_name=name, max_tokens=max_tokens)
        return extract_json(reply.content), reply
