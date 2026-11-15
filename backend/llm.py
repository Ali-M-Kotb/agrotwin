"""One tool-calling loop for every language-model provider AgroTwin can use.

Provider is chosen from the key in agrotwin/.env (git-ignored):
  sk-ant-…          → Anthropic Messages API (Claude Opus 5.5)
  anything else     → OpenAI-compatible Chat Completions with tool calling
                      (default base URL: OpenCode inference, model "big-pickle"; override with LLM_BASE_URL / LLM_MODEL)
Keys are read from LLM_API_KEY, OPENCODE_API_KEY or ANTHROPIC_API_KEY. The model only talks and calls tools; every
number in its reply is still audited against the tool results by the caller, and any failure falls back to the
offline engine. The last provider error is kept so the UI can say why it is offline.
"""
from __future__ import annotations

import json
import os

ANTHROPIC_MODEL = "claude-opus-5-5"
OPENCODE_URL = "https://opencode.ai/inference/openai/v1"
NVIDIA_URL = "https://integrate.api.nvidia.com/v1"
NVIDIA_MODEL = "nvidia/nemotron-3-ultra-550b-a55b"   # best Egyptian Arabic on NVIDIA Build in our tests (≈6 s)
LAST = {"error": None}

def _key() -> str | None:
    for k in ("LLM_API_KEY", "OPENCODE_API_KEY", "ANTHROPIC_API_KEY"):
        v = (os.environ.get(k) or "").strip()
        if v:
            return v
    return None

def provider() -> dict | None:
    key = _key()
    if not key:
        return None
    if key.startswith("sk-ant-"):
        return dict(kind="anthropic", name="Claude", model=os.environ.get("LLM_MODEL") or ANTHROPIC_MODEL, key=key)
    nv = key.startswith("nvapi-")
    base = os.environ.get("LLM_BASE_URL") or (NVIDIA_URL if nv else OPENCODE_URL)
    model = os.environ.get("LLM_MODEL") or (NVIDIA_MODEL if nv else "big-pickle")
    short = model.split("/")[-1]
    name = ("NVIDIA " + short) if "nvidia.com" in base else ("OpenCode " + short) if "opencode.ai" in base else short
    return dict(kind="openai", name=name, model=model, key=key, base=base.rstrip("/"))

def status() -> dict:
    p = provider()
    if not p:
        return dict(active=False, provider=None, model=None, last_error=None)
    return dict(active=LAST["error"] is None, provider=p["name"], model=p["model"], last_error=LAST["error"])

def run_tools(system: str, messages: list[dict], tools: list[dict], execute, max_rounds: int = 6, max_tokens: int = 1200):
    """messages: [{role: user|assistant, content: str}]. tools: Anthropic-style dicts (name, description, input_schema).
    execute(name, args) -> dict. Returns reply text or None (caller falls back)."""
    p = provider()
    if not p:
        return None
    try:
        out = _anthropic(p, system, messages, tools, execute, max_rounds, max_tokens) if p["kind"] == "anthropic" \
            else _openai(p, system, messages, tools, execute, max_rounds, max_tokens)
        LAST["error"] = None if out else LAST["error"]
        return out
    except Exception as e:  # noqa: BLE001
        LAST["error"] = str(e)[:240]
        return None

def _anthropic(p, system, messages, tools, execute, rounds, max_tokens):
    import anthropic
    client = anthropic.Anthropic(api_key=p["key"])
    msgs = list(messages)
    for _ in range(rounds):
        resp = client.messages.create(model=p["model"], max_tokens=max_tokens, system=system, tools=tools, messages=msgs)
        if resp.stop_reason == "refusal":
            return None
        uses = [b for b in resp.content if b.type == "tool_use"]
        if resp.stop_reason != "tool_use" or not uses:
            return " ".join(b.text for b in resp.content if b.type == "text").strip() or None
        msgs.append(dict(role="assistant", content=resp.content))
        msgs.append(dict(role="user", content=[dict(type="tool_result", tool_use_id=u.id,
                                                    content=json.dumps(execute(u.name, u.input or {}), ensure_ascii=False, default=str)) for u in uses]))
    return None

def _openai(p, system, messages, tools, execute, rounds, max_tokens):
    import requests
    fn = [dict(type="function", function=dict(name=t["name"], description=t["description"], parameters=t["input_schema"])) for t in tools]
    msgs = [dict(role="system", content=system)] + [dict(role=m["role"], content=m["content"]) for m in messages]
    for _ in range(rounds):
        r = requests.post(p["base"] + "/chat/completions", timeout=60,
                          headers={"Authorization": f"Bearer {p['key']}", "Content-Type": "application/json"},
                          json=dict(model=p["model"], messages=msgs, tools=fn, tool_choice="auto", max_tokens=max_tokens, temperature=0.4))
        if r.status_code != 200:
            try:
                err = r.json().get("error", {})
                msg = err.get("message") if isinstance(err, dict) else str(err)
            except Exception:  # noqa: BLE001
                msg = r.text[:200]
            raise RuntimeError(f"{p['name']}: HTTP {r.status_code}: {msg}")
        m = r.json()["choices"][0]["message"]
        calls = m.get("tool_calls") or []
        if not calls:
            return (m.get("content") or "").strip() or None
        msgs.append(dict(role="assistant", content=m.get("content") or "", tool_calls=calls))
        for c in calls:
            try:
                args = json.loads(c["function"].get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {}
            res = execute(c["function"]["name"], args)
            msgs.append(dict(role="tool", tool_call_id=c["id"], content=json.dumps(res, ensure_ascii=False, default=str)))
    return None

def talk(system: str, messages: list[dict], max_tokens: int = 1200) -> str | None:
    """Plain conversation (no tools): the farmer's open questions, answered from the context the caller provides."""
    p = provider()
    if not p:
        return None
    try:
        if p["kind"] == "anthropic":
            import anthropic
            resp = anthropic.Anthropic(api_key=p["key"]).messages.create(model=p["model"], max_tokens=max_tokens, system=system, messages=messages)
            out = " ".join(b.text for b in resp.content if b.type == "text").strip()
        else:
            import requests
            r = requests.post(p["base"] + "/chat/completions", timeout=45,
                              headers={"Authorization": f"Bearer {p['key']}", "Content-Type": "application/json"},
                              json=dict(model=p["model"], messages=[dict(role="system", content=system)] + messages,
                                        max_tokens=max_tokens, temperature=0.4))
            if r.status_code != 200:
                raise RuntimeError(f"{p['name']}: HTTP {r.status_code}")
            out = (r.json()["choices"][0]["message"].get("content") or "").strip()
        LAST["error"] = None
        return out or None
    except Exception as e:  # noqa: BLE001
        LAST["error"] = str(e)[:240]
        return None
