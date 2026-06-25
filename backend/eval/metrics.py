"""Reference-free + reference-based NLP metrics for the ablation study.

No heavy deps (no torch/sklearn). Reference-based similarity uses ROUGE-L and a
bag-of-words cosine against the platform gold corpus; the rest are rule-based
construct checks plus process metrics parsed from the result XML.
"""
from __future__ import annotations
import re, json, math, os
import xml.etree.ElementTree as ET
from collections import Counter

_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # backend/
GOLD = json.load(open(os.path.join(_HERE, "feedback", "gold_corpus.json")))

CODE_TAG_RE = re.compile(r"<code[\w-]*>(.*?)</code[\w-]*>", re.S)
ANY_TAG_RE = re.compile(r"<[^>]+>")
WORD_RE = re.compile(r"[\wàâäéèêëïîôöùûüç']+", re.I)


# ── text utilities ──────────────────────────────────────────────────────────
def strip_tags(t: str) -> str:
    return ANY_TAG_RE.sub(" ", t or "")


def words(t: str) -> list[str]:
    return [w.lower() for w in WORD_RE.findall(strip_tags(t))]


def sentences(t: str) -> list[str]:
    s = re.split(r"[.!?]+", strip_tags(t))
    return [x.strip() for x in s if x.strip()]


def code_in(t: str) -> str:
    """Concatenated code referenced in the component (code tags + backticks)."""
    parts = CODE_TAG_RE.findall(t or "")
    parts += re.findall(r"`([^`]+)`", t or "")
    parts += re.findall(r"```(.*?)```", t or "", re.S)
    return "\n".join(parts)


def has_markdown(t: str) -> bool:
    return bool(re.search(r"```|(?<!`)`(?!`)|\*\*|^#", t or "", re.M))


# ── similarity ──────────────────────────────────────────────────────────────
def bow_cosine(a: str, b: str) -> float:
    ca, cb = Counter(words(a)), Counter(words(b))
    if not ca or not cb:
        return 0.0
    common = set(ca) & set(cb)
    num = sum(ca[w] * cb[w] for w in common)
    da = math.sqrt(sum(v * v for v in ca.values()))
    db = math.sqrt(sum(v * v for v in cb.values()))
    return num / (da * db) if da and db else 0.0


def rouge_l(a: str, b: str) -> float:
    """ROUGE-L F1 on word sequences."""
    x, y = words(a), words(b)
    if not x or not y:
        return 0.0
    # LCS length (DP)
    dp = [[0] * (len(y) + 1) for _ in range(len(x) + 1)]
    for i in range(1, len(x) + 1):
        for j in range(1, len(y) + 1):
            dp[i][j] = dp[i - 1][j - 1] + 1 if x[i - 1] == y[j - 1] else max(dp[i - 1][j], dp[i][j - 1])
    lcs = dp[-1][-1]
    if lcs == 0:
        return 0.0
    prec, rec = lcs / len(x), lcs / len(y)
    return 2 * prec * rec / (prec + rec)


def best_vs_gold(content: str, characteristic: str) -> dict:
    gold = GOLD.get(characteristic, [])
    if not gold:
        return {"rougeL": None, "bow_cos": None}
    return {
        "rougeL": max(rouge_l(content, g) for g in gold),
        "bow_cos": max(bow_cosine(content, g) for g in gold),
    }


# ── component-level construct checks ────────────────────────────────────────
def identifier_overlap(content: str, solution: str) -> float:
    sol_ids = set(re.findall(r"[A-Za-zà-ÿ_][\w]*\s*\(", solution or ""))
    sol_ids = {s.rstrip("( ").lower() for s in sol_ids}
    comp_ids = {w for w in words(code_in(content))}
    if not sol_ids:
        return 0.0
    return len(sol_ids & comp_ids) / len(sol_ids)


def solution_leak(content: str, solution: str) -> float:
    """Fraction of (non-trivial) solution lines that appear in the component."""
    sol_lines = [l.strip() for l in (solution or "").splitlines()
                 if l.strip() and not l.strip().startswith("#")]
    if not sol_lines:
        return 0.0
    comp = re.sub(r"\s+", " ", strip_tags(content) + " " + code_in(content)).lower()
    hit = sum(1 for l in sol_lines if len(l) > 3 and re.sub(r"\s+", " ", l).lower() in comp)
    return hit / len(sol_lines)


# ── top-level: metrics for one generated feedback ───────────────────────────
def parse_components(xml: str) -> list[dict]:
    out = []
    try:
        root = ET.fromstring(xml)
    except Exception:
        return out
    for c in root.iter("component"):
        it = c.find("iterations")
        content_el = c.find("content")
        out.append({
            "characteristic": c.get("characteristic"),
            "type": c.get("type"),
            "iterations": int(it.text) if it is not None and it.text and it.text.isdigit() else 1,
            "content": (content_el.text if content_el is not None and content_el.text else "") or "",
        })
    return out


def compute(xml: str, solution: str = "") -> dict:
    comps = parse_components(xml)
    text_comps = [c for c in comps if c["type"] != "image" and c["content"]]
    n = len(text_comps)
    if n == 0:
        return {"n_components": 0, "parse_ok": bool(comps)}

    rouge, bowg, purity, leak, ground, concise, fmt, read = [], [], [], [], [], [], [], []
    for c in text_comps:
        ch, content = c["characteristic"], c["content"]
        g = best_vs_gold(content, ch)
        if g["rougeL"] is not None:
            rouge.append(g["rougeL"]); bowg.append(g["bow_cos"])
        # purity: logos must contain no code; example_* must reference identifiers
        if ch == "logos":
            purity.append(0.0 if code_in(content).strip() else 1.0)
        elif ch == "with_example_related_to_exercise":
            purity.append(1.0 if identifier_overlap(content, solution) > 0 else 0.0)
        elif ch == "with_example_unrelated_to_exercise":
            purity.append(0.0 if identifier_overlap(content, solution) > 0 else 1.0)
        leak.append(solution_leak(content, solution))
        ground.append(identifier_overlap(content, solution))
        sents = sentences(content)
        concise.append(len(sents))
        fmt.append(1.0 if has_markdown(content) else 0.0)
        ws = words(content)
        read.append(len(ws) / len(sents) if sents else len(ws))

    # redundancy: mean pairwise BoW cosine between components
    red = []
    for i in range(n):
        for j in range(i + 1, n):
            red.append(bow_cosine(text_comps[i]["content"], text_comps[j]["content"]))

    def mean(x):
        return sum(x) / len(x) if x else None

    total_iters = sum(c["iterations"] for c in comps)
    return {
        "n_components": n,
        "parse_ok": True,
        # reference-based
        "rougeL_vs_gold": mean(rouge),
        "bowcos_vs_gold": mean(bowg),
        # construct / safety
        "characteristic_purity": mean(purity),
        "solution_leak_rate": mean(leak),
        "grounding_overlap": mean(ground),
        "redundancy": mean(red),
        # form
        "sentences_per_component": mean(concise),
        "format_violation_rate": mean(fmt),
        "words_per_sentence": mean(read),
        # process
        "total_iterations": total_iters,
        "regenerations": total_iters - len(comps),
    }
