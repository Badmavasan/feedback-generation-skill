"""Load feedback requests (stimuli) for the ablation study from the enriched
sample. Each row already carries task type, exercise + solution, error, KC,
characteristics and level. Image feedbacks are excluded (text-only study)."""
from __future__ import annotations
import csv, json, os, random

csv.field_size_limit(10 ** 7)
_HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # repo root
CSV_PATH = os.path.join(_HERE, "feedback_sample_enriched.csv")


def _row_to_stimulus(r: dict) -> dict:
    try:
        chars = json.loads(r["characteristics"])
    except Exception:
        chars = [c.strip() for c in (r.get("characteristics_combo") or "").split(",") if c.strip()]
    solution = r.get("correct_submission") or ""
    exercise = {
        "description": r.get("context_exercise_title") or r.get("exercise_title") or "",
        "possible_solutions": [solution] if solution else [],
        "exercise_type": r.get("exercise_type") or "",
        "robot_map": None,
        "task_types": ([{"task_code": r["task_type"], "task_name": r["task_type"]}]
                       if r.get("task_type") else []),
    }
    error = None
    if (r.get("error_tag") or "").strip():
        error = {"tag": r["error_tag"], "description": r.get("error_description") or ""}
    live_context = None
    if (r.get("errored_submission") or "").strip():
        live_context = {"student_attempt": r["errored_submission"], "interaction_data": {}}
    return {
        "id": r["id"],
        "platform_id": "algopython",
        "mode": r.get("mode") or "offline",
        "level": r.get("level") or "error",
        "language": r.get("language") or "fr",
        "characteristics": chars,
        "kc_name": r.get("kc_name") or "",
        "kc_description": r.get("kc_description") or "",
        "exercise": exercise,
        "exercise_id": r.get("exercise_id") or None,
        "error": error,
        "live_context": live_context,
        "solution": solution,
        "characteristics_combo": r.get("characteristics_combo") or "",
    }


def load_stimuli(n: int | None = None, seed: int = 0, stratify: bool = True) -> list[dict]:
    rows = [r for r in csv.DictReader(open(CSV_PATH)) if (r.get("has_image") or "f") != "t"]
    stims = [_row_to_stimulus(r) for r in rows]
    stims = [s for s in stims if s["characteristics"]]
    if n is None or n >= len(stims):
        return stims
    rng = random.Random(seed)
    if stratify:
        # one per distinct characteristics_combo first, then fill
        by_combo: dict[str, list] = {}
        for s in stims:
            by_combo.setdefault(s["characteristics_combo"], []).append(s)
        picked, pool = [], []
        for combo, items in by_combo.items():
            rng.shuffle(items)
            picked.append(items[0]); pool.extend(items[1:])
        rng.shuffle(pool)
        picked.extend(pool)
        return picked[:n]
    rng.shuffle(stims)
    return stims[:n]


if __name__ == "__main__":
    s = load_stimuli()
    from collections import Counter
    print("total text stimuli:", len(s))
    print("by combo:", dict(Counter(x["characteristics_combo"] for x in s)))
    print("levels:", dict(Counter(x["level"] for x in s)))
