"""Aggregate ablation pilot runs -> per-condition metric means + token analysis.

  ../.venv-eval/bin/python scripts/aggregate_ablation.py \
     --in ../doc/ablation_results/pilot_runs.jsonl \
     --out ../doc/ablation_results
"""
from __future__ import annotations
import os, sys, json, argparse, statistics
from collections import defaultdict

METRIC_KEYS = [
    "rougeL_vs_gold", "bowcos_vs_gold", "characteristic_purity",
    "solution_leak_rate", "grounding_overlap", "redundancy",
    "sentences_per_component", "format_violation_rate", "words_per_sentence",
    "regenerations", "n_components",
]
COND_ORDER = ["A0_full", "A1_no_loop", "A2_no_quality_gate", "A3_no_relevance",
              "A4_no_student_sim", "A5_no_coherence", "A6_no_rag", "A7_generator_only"]


def msd(xs):
    xs = [x for x in xs if x is not None]
    if not xs:
        return None, None
    return statistics.mean(xs), (statistics.stdev(xs) if len(xs) > 1 else 0.0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True)
    ap.add_argument("--out", dest="out", required=True)
    args = ap.parse_args()

    rows = [json.loads(l) for l in open(args.inp) if l.strip()]
    by_cond = defaultdict(list)
    for r in rows:
        by_cond[r["condition"]].append(r)
    conds = [c for c in COND_ORDER if c in by_cond] + [c for c in by_cond if c not in COND_ORDER]

    os.makedirs(args.out, exist_ok=True)
    lines = ["# Ablation pilot — results\n",
             f"Runs: {len(rows)} | conditions: {len(conds)} | "
             f"errors: {sum(1 for r in rows if r['error'])}\n"]

    # ── metric table ────────────────────────────────────────────────────────
    lines.append("\n## Metrics by condition (mean ± sd)\n")
    header = "| Condition | n_runs | " + " | ".join(METRIC_KEYS) + " |"
    lines.append(header)
    lines.append("|" + "---|" * (len(METRIC_KEYS) + 2))
    for c in conds:
        rs = by_cond[c]
        ok = [r for r in rs if not r["error"]]
        cells = []
        for k in METRIC_KEYS:
            m, s = msd([r["metrics"].get(k) for r in ok])
            cells.append("—" if m is None else f"{m:.2f}±{s:.2f}")
        lines.append(f"| {c} | {len(ok)}/{len(rs)} | " + " | ".join(cells) + " |")

    # ── token analysis (per model) ──────────────────────────────────────────
    lines.append("\n## Token usage by condition and model (mean per run)\n")
    lines.append("| Condition | model | calls | input tok | output tok | in+out |")
    lines.append("|---|---|---|---|---|---|")
    for c in conds:
        ok = [r for r in by_cond[c] if not r["error"]]
        per_model = defaultdict(lambda: {"calls": [], "in": [], "out": []})
        for r in ok:
            for model, u in r["usage"]["by_model"].items():
                per_model[model]["calls"].append(u["calls"])
                per_model[model]["in"].append(u["input"])
                per_model[model]["out"].append(u["output"])
        for model, d in sorted(per_model.items()):
            cm, _ = msd(d["calls"]); im, _ = msd(d["in"]); om, _ = msd(d["out"])
            lines.append(f"| {c} | {model} | {cm:.1f} | {im:.0f} | {om:.0f} | {im+om:.0f} |")

    # ── total token cost per condition ──────────────────────────────────────
    lines.append("\n## Total tokens per run by condition (all models)\n")
    lines.append("| Condition | input (mean) | output (mean) | total (mean) | latency s (mean) |")
    lines.append("|---|---|---|---|---|")
    for c in conds:
        ok = [r for r in by_cond[c] if not r["error"]]
        im, _ = msd([r["usage"]["total"]["input"] for r in ok])
        om, _ = msd([r["usage"]["total"]["output"] for r in ok])
        lat, _ = msd([r["latency_s"] for r in ok])
        if im is None:
            continue
        lines.append(f"| {c} | {im:.0f} | {om:.0f} | {im+om:.0f} | {lat:.1f} |")

    # ── contribution vs control (A0) on key constructs ──────────────────────
    if "A0_full" in by_cond:
        lines.append("\n## Δ vs full pipeline (A0) — degradation when a component is removed\n")
        ctrl = {k: msd([r["metrics"].get(k) for r in by_cond["A0_full"] if not r["error"]])[0]
                for k in METRIC_KEYS}
        key = ["format_violation_rate", "solution_leak_rate", "characteristic_purity",
               "redundancy", "grounding_overlap", "bowcos_vs_gold"]
        lines.append("| Condition | " + " | ".join(f"Δ {k}" for k in key) + " |")
        lines.append("|" + "---|" * (len(key) + 1))
        for c in conds:
            if c == "A0_full":
                continue
            ok = [r for r in by_cond[c] if not r["error"]]
            cells = []
            for k in key:
                m, _ = msd([r["metrics"].get(k) for r in ok])
                base = ctrl.get(k)
                cells.append("—" if (m is None or base is None) else f"{m-base:+.2f}")
            lines.append(f"| {c} | " + " | ".join(cells) + " |")

    report = "\n".join(lines) + "\n"
    out_md = os.path.join(args.out, "ablation_report.md")
    open(out_md, "w").write(report)
    print(report)
    print("written:", out_md)


if __name__ == "__main__":
    main()
