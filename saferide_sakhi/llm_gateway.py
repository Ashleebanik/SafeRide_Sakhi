"""
LLM Gateway – unified wrapper for Granite 4 (watsonx), Gemini, and Groq.
Logs every call: model, tokens_in, tokens_out, cost_usd, latency_ms.
All agents use this module; never import SDKs directly in agent code.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any

from saferide_sakhi.config import (
    GEMINI_API_KEY, GEMINI_MODEL,
    GRANITE_MODEL_ID, GROQ_API_KEY, GROQ_MODEL,
    WATSONX_API_KEY, WATSONX_PROJECT_ID, WATSONX_URL,
)
from saferide_sakhi.logger import AgentLogger

_log = AgentLogger("LLMGateway")

# Approximate cost per 1k tokens (USD) – update as pricing changes
_COST_PER_1K = {
    "granite": {"in": 0.0005, "out": 0.0015},
    "gemini":  {"in": 0.00035, "out": 0.00105},
    "groq":    {"in": 0.0001,  "out": 0.0001},
}


@dataclass
class LLMResponse:
    text: str
    model: str
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    latency_ms: float = 0.0
    success: bool = True
    error: str = ""
    raw: dict[str, Any] = field(default_factory=dict)


def _calc_cost(model_key: str, tokens_in: int, tokens_out: int) -> float:
    rates = _COST_PER_1K.get(model_key, {"in": 0, "out": 0})
    return round((tokens_in * rates["in"] + tokens_out * rates["out"]) / 1000, 6)


# ── Granite 4 via watsonx.ai ──────────────────────────────────────────────────

def _call_granite(prompt: str, max_tokens: int = 512) -> LLMResponse:
    if not WATSONX_API_KEY or not WATSONX_PROJECT_ID:
        return LLMResponse(text="", model=GRANITE_MODEL_ID, success=False,
                           error="WATSONX_API_KEY or WATSONX_PROJECT_ID not set")
    t0 = time.perf_counter()
    try:
        import httpx
        url = f"{WATSONX_URL}/ml/v1/text/generation?version=2024-05-01"
        headers = {"Authorization": f"Bearer {WATSONX_API_KEY}",
                   "Content-Type": "application/json"}
        body = {
            "model_id": GRANITE_MODEL_ID,
            "project_id": WATSONX_PROJECT_ID,
            "input": prompt,
            "parameters": {"decoding_method": "greedy",
                           "max_new_tokens": max_tokens,
                           "stop_sequences": ["\n\n"]},
        }
        resp = httpx.post(url, headers=headers, json=body, timeout=20.0)
        resp.raise_for_status()
        data = resp.json()
        text = data["results"][0]["generated_text"].strip()
        tok_in  = data.get("input_token_count", len(prompt.split()))
        tok_out = data["results"][0].get("generated_token_count", len(text.split()))
        latency = (time.perf_counter() - t0) * 1000
        cost = _calc_cost("granite", tok_in, tok_out)
        return LLMResponse(text=text, model=GRANITE_MODEL_ID,
                           tokens_in=tok_in, tokens_out=tok_out,
                           cost_usd=cost, latency_ms=round(latency, 1),
                           success=True, raw=data)
    except Exception as exc:
        return LLMResponse(text="", model=GRANITE_MODEL_ID, success=False,
                           error=str(exc), latency_ms=(time.perf_counter()-t0)*1000)


# ── Gemini ────────────────────────────────────────────────────────────────────

def _call_gemini(prompt: str, max_tokens: int = 512) -> LLMResponse:
    if not GEMINI_API_KEY:
        return LLMResponse(text="", model=GEMINI_MODEL, success=False,
                           error="GEMINI_API_KEY not set")
    t0 = time.perf_counter()
    try:
        import google.generativeai as genai
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel(
            GEMINI_MODEL,
            generation_config={"max_output_tokens": max_tokens, "temperature": 0.2},
        )
        resp = model.generate_content(prompt)
        text = resp.text.strip()
        tok_in  = getattr(resp.usage_metadata, "prompt_token_count", len(prompt.split()))
        tok_out = getattr(resp.usage_metadata, "candidates_token_count", len(text.split()))
        latency = (time.perf_counter() - t0) * 1000
        cost = _calc_cost("gemini", tok_in, tok_out)
        return LLMResponse(text=text, model=GEMINI_MODEL,
                           tokens_in=tok_in, tokens_out=tok_out,
                           cost_usd=cost, latency_ms=round(latency, 1), success=True)
    except Exception as exc:
        return LLMResponse(text="", model=GEMINI_MODEL, success=False,
                           error=str(exc), latency_ms=(time.perf_counter()-t0)*1000)


# ── Groq ──────────────────────────────────────────────────────────────────────

def _call_groq(prompt: str, max_tokens: int = 512) -> LLMResponse:
    if not GROQ_API_KEY:
        return LLMResponse(text="", model=GROQ_MODEL, success=False,
                           error="GROQ_API_KEY not set")
    t0 = time.perf_counter()
    try:
        from groq import Groq
        client = Groq(api_key=GROQ_API_KEY)
        resp = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            temperature=0.2,
        )
        text = resp.choices[0].message.content.strip()
        tok_in  = resp.usage.prompt_tokens
        tok_out = resp.usage.completion_tokens
        latency = (time.perf_counter() - t0) * 1000
        cost = _calc_cost("groq", tok_in, tok_out)
        return LLMResponse(text=text, model=GROQ_MODEL,
                           tokens_in=tok_in, tokens_out=tok_out,
                           cost_usd=cost, latency_ms=round(latency, 1), success=True)
    except Exception as exc:
        return LLMResponse(text="", model=GROQ_MODEL, success=False,
                           error=str(exc), latency_ms=(time.perf_counter()-t0)*1000)


# ── Public API ────────────────────────────────────────────────────────────────

def call(provider: str, prompt: str, max_tokens: int = 512,
         agent: str = "unknown", trip_id: str = "") -> LLMResponse:
    """
    Call an LLM by provider name ("granite" | "gemini" | "groq").
    Logs cost, tokens and latency to the structured audit log.
    """
    providers = {"granite": _call_granite, "gemini": _call_gemini, "groq": _call_groq}
    fn = providers.get(provider.lower())
    if fn is None:
        return LLMResponse(text="", model=provider, success=False,
                           error=f"Unknown provider: {provider}")

    result = fn(prompt, max_tokens)

    _log.step(
        trip_id=trip_id or "n/a",
        stage=f"llm_call:{provider}",
        input_summary=f"agent={agent}, tokens_in={result.tokens_in}",
        tool_call=result.model,
        output_summary=f"success={result.success}, tokens_out={result.tokens_out}, "
                       f"cost=${result.cost_usd:.6f}",
        latency_ms=result.latency_ms,
        decision="ok" if result.success else f"error:{result.error[:60]}",
    )
    return result
