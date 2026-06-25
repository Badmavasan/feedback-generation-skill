"""Non-invasive token-usage capture for the ablation study.

Monkeypatches the Anthropic and Mistral SDK calls so every LLM request records
(model, input_tokens, output_tokens) into a per-run accumulator. Attribution is
by model string, so Claude vs Mistral usage is separable regardless of which
agent issued the call.
"""
from __future__ import annotations
import functools

# accumulator: list of {"model": str, "input": int, "output": int, "calls": 1}
_USAGE: list[dict] = []
_installed = False


def reset() -> None:
    _USAGE.clear()


def snapshot() -> dict:
    """Aggregate the recorded calls by model + grand total."""
    by_model: dict[str, dict] = {}
    for u in _USAGE:
        m = by_model.setdefault(u["model"], {"input": 0, "output": 0, "calls": 0})
        m["input"] += u["input"]; m["output"] += u["output"]; m["calls"] += 1
    total = {
        "input": sum(m["input"] for m in by_model.values()),
        "output": sum(m["output"] for m in by_model.values()),
        "calls": sum(m["calls"] for m in by_model.values()),
    }
    return {"by_model": by_model, "total": total}


def _record(model, input_tokens, output_tokens):
    _USAGE.append({
        "model": model or "unknown",
        "input": int(input_tokens or 0),
        "output": int(output_tokens or 0),
    })


def install(mistral_api_key: str | None = None) -> None:
    """Patch the SDK call sites. Idempotent."""
    global _installed
    if _installed:
        return

    # ── Anthropic (AsyncMessages.create) ────────────────────────────────────
    try:
        from anthropic.resources.messages import AsyncMessages
        _orig_anthropic = AsyncMessages.create

        @functools.wraps(_orig_anthropic)
        async def _patched_anthropic(self, *args, **kwargs):
            resp = await _orig_anthropic(self, *args, **kwargs)
            try:
                u = getattr(resp, "usage", None)
                _record(kwargs.get("model"), getattr(u, "input_tokens", 0),
                        getattr(u, "output_tokens", 0))
            except Exception:
                pass
            return resp

        AsyncMessages.create = _patched_anthropic
    except Exception as e:  # pragma: no cover
        print("[usage_tracker] anthropic patch failed:", e)

    # ── Mistral (chat.complete_async) ───────────────────────────────────────
    try:
        from mistralai.client import Mistral
        _probe = Mistral(api_key=mistral_api_key or "x")
        chat_cls = type(_probe.chat)
        _orig_mistral = chat_cls.complete_async

        @functools.wraps(_orig_mistral)
        async def _patched_mistral(self, *args, **kwargs):
            resp = await _orig_mistral(self, *args, **kwargs)
            try:
                u = getattr(resp, "usage", None)
                _record(kwargs.get("model"),
                        getattr(u, "prompt_tokens", 0),
                        getattr(u, "completion_tokens", 0))
            except Exception:
                pass
            return resp

        chat_cls.complete_async = _patched_mistral
    except Exception as e:  # pragma: no cover
        print("[usage_tracker] mistral patch failed:", e)

    _installed = True
