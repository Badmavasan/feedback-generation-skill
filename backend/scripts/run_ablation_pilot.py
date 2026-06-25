"""Ablation pilot runner.

Runs the feedback pipeline under each ablation condition over a stimulus set,
capturing reference-free NLP metrics + per-model token usage. Text-only
(image pipeline disabled — no Gemini/OpenAI keys).

Usage (from the backend/ directory, with the eval venv):
  AGENT_LOG_DIR=/tmp/abl_logs PYTHONPATH=. \
    ../.venv-eval/bin/python scripts/run_ablation_pilot.py --n 6 --reps 2
  add --smoke for a 1-stimulus, 2-condition dry run.
"""
from __future__ import annotations
import os, sys, json, time, asyncio, argparse, types, traceback

# ── make backend importable + redirect /app log dir ─────────────────────────
_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BACKEND)
os.environ.setdefault("AGENT_LOG_DIR", "/tmp/abl_logs")

# ── stub heavy deps we never call (platform context is provided statically) ──
def _stub(name, attrs=None, submods=None):
    m = types.ModuleType(name)
    for k, v in (attrs or {}).items():
        setattr(m, k, v)
    sys.modules[name] = m
    for sn, sa in (submods or {}).items():
        s = types.ModuleType(name + "." + sn)
        for k, v in sa.items():
            setattr(s, k, v)
        sys.modules[name + "." + sn] = s
        setattr(m, sn, s)


class _Dummy:
    def __init__(self, *a, **k): ...


if "chromadb" not in sys.modules:
    _stub("chromadb", {"PersistentClient": _Dummy, "Client": _Dummy}, {"config": {"Settings": _Dummy}})
    _stub("sentence_transformers", {"SentenceTransformer": _Dummy})

from core.config import get_settings            # noqa: E402
from agents.orchestrator import ClaudeOrchestrator  # noqa: E402
from eval import usage_tracker, metrics          # noqa: E402
from eval.stimuli import load_stimuli            # noqa: E402

# ── static platform context (replaces RAG) ──────────────────────────────────
def build_platform_context() -> str:
    seed = json.load(open(os.path.join(_BACKEND, "data", "seeds", "algopython_seed.json")))
    chunks = seed.get("context_chunks", [])
    return "\n\n".join(f"## {c.get('section','')}\n{c.get('content','')}" for c in chunks)


# ── ablation conditions ─────────────────────────────────────────────────────
BASE_DROP = ["generate_image_feedback"]  # text-only study
CONDITIONS: dict[str, dict] = {
    "A0_full":            {},
    "A1_no_loop":         {"text_max_iterations": 1},
    "A2_no_quality_gate": {"minimal_quality_gate": True},
    "A3_no_relevance":    {"drop_tools": ["check_example_relevance"]},
    "A4_no_student_sim":  {"drop_tools": ["simulate_student"]},
    "A5_no_coherence":    {"drop_tools": ["check_coherence"]},
    "A6_no_rag":          {"_no_rag": True},
    "A7_generator_only":  {"text_max_iterations": 1, "minimal_quality_gate": True,
                           "drop_tools": ["check_example_relevance", "simulate_student", "check_coherence"]},
}


async def run_one(orch, ctx, stim, cond_name, cfg, rep):
    cfg = dict(cfg)
    no_rag = cfg.pop("_no_rag", False)
    drop = list(set(BASE_DROP + cfg.get("drop_tools", [])))
    abl = {**cfg, "drop_tools": drop}
    usage_tracker.reset()
    t0 = time.time()
    err = None
    xml = ""
    try:
        xml = await orch.run(
            platform_id=stim["platform_id"], mode=stim["mode"], level=stim["level"],
            language=stim["language"], characteristics=stim["characteristics"],
            kc_name=stim["kc_name"], kc_description=stim["kc_description"],
            exercise=stim["exercise"], error=stim["error"], live_context=stim["live_context"],
            exercise_id=stim["exercise_id"],
            platform_context_override=("" if no_rag else ctx),
            run_id=f"{cond_name}__{stim['id']}__r{rep}",
            ablation=abl,
        )
    except Exception as e:
        err = f"{type(e).__name__}: {e}"
        traceback.print_exc()
    latency = time.time() - t0
    usage = usage_tracker.snapshot()
    m = metrics.compute(xml or "", solution=stim["solution"]) if xml else {"n_components": 0, "parse_ok": False}
    return {
        "condition": cond_name, "stimulus_id": stim["id"], "rep": rep,
        "characteristics": stim["characteristics"], "level": stim["level"],
        "error": err, "latency_s": round(latency, 2),
        "usage": usage, "metrics": m,
    }


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=6)
    ap.add_argument("--reps", type=int, default=2)
    ap.add_argument("--conditions", type=str, default="")  # comma list, empty = all
    ap.add_argument("--out", type=str, default=os.path.join(_BACKEND, "..", "doc", "ablation_results", "pilot_runs.jsonl"))
    ap.add_argument("--smoke", action="store_true")
    args = ap.parse_args()

    settings = get_settings()
    usage_tracker.install(mistral_api_key=settings.mistral_api_key)
    ctx = build_platform_context()
    orch = ClaudeOrchestrator()

    if args.smoke:
        conds = ["A0_full", "A7_generator_only"]
        stims = load_stimuli(n=1)
        reps = 1
    else:
        conds = [c.strip() for c in args.conditions.split(",") if c.strip()] or list(CONDITIONS)
        stims = load_stimuli(n=args.n)
        reps = args.reps

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    total = len(conds) * len(stims) * reps
    print(f"[pilot] platform_context={len(ctx)} chars | {len(stims)} stimuli x {len(conds)} conditions x {reps} reps = {total} runs")
    done = 0
    with open(args.out, "w") as f:
        for cond in conds:
            for stim in stims:
                for rep in range(reps):
                    rec = await run_one(orch, ctx, stim, cond, CONDITIONS[cond], rep)
                    f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    f.flush()
                    done += 1
                    u = rec["usage"]["total"]
                    status = rec["error"] or f"n={rec['metrics'].get('n_components')} regen={rec['metrics'].get('regenerations')}"
                    print(f"[{done}/{total}] {cond} {stim['id'][:18]} r{rep} "
                          f"{rec['latency_s']}s tok(in/out)={u['input']}/{u['output']} :: {status}")
    print(f"[pilot] wrote {args.out}")


if __name__ == "__main__":
    asyncio.run(main())
