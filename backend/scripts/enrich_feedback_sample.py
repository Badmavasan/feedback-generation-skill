"""Enrich feedback_sample.csv with an exercise context per feedback.

For each of the 18 sampled feedback records, adds:
  - context_exercise_id / title / type — the exercise the feedback applies to
    (kept when the record already references one, otherwise chosen so that the
    KC + error tag of the feedback genuinely apply to the exercise)
  - correct_submission  — canonical solution from exercises.json
  - errored_submission  — handcrafted buggy student code that triggers exactly
    the error / KC gap the feedback addresses
  - feedback_html       — the feedback components extracted from result_xml,
    rendered as HTML (one <p> per text component, <figure><img> for images)

Usage: python3 enrich_feedback_sample.py <in.csv> <out.csv>
"""
import csv
import html
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

EXERCISES_JSON = Path(
    "/home/bkirouch/PycharmProjects/algopython/secondary/"
    "error-annotations-algopython/exercises.json"
)
IMAGE_URL_PREFIX = "https://badmavasan.tech"

# id-prefix → (exercise_id, errored student submission)
# Exercise choice rationale (for rows without one in the DB):
#   d0752dd0 UNNECESSARY_RETURN on a void function   → 112 D-6 (carre(n), void)
#   aee5e992 BODY_ERROR (body misses the repetition) → 113 D-7 (ping loop)
#   ea807364 MISSING_PARAMETER                       → 111 D-4 (pairs(n))
#   09a4995b CALL_INCORRECT_POSITION (call < def)    → 56  D-17 (carre())
#   task_type rows: exercise picked so the KC is the central skill tested.
CONTEXTS = {
    # ─── error level ────────────────────────────────────────────────────────
    "d0752dd0": (112, "def carre(n):\n\tfor k in range(4):\n\t\tavancer(n)\n\t\ttourner(90)\n\treturn n\n\ncarre(3)\navancer(5)\ncarre(2)\navancer(3)\ncarre(1)\navancer(1)\ncarre(2)"),
    "aee5e992": (113, "def ping(n):\n\tprint(\"ping\")\n\nping(3)\nprint(\"pong\")\nping(5)\nprint(\"pong\")\nping(2)"),
    "ea807364": (111, "def pairs():\n\tfor k in range(n//2+1):\n\t\tprint(k*2)\n\npairs(4)\npairs(2)\npairs(10)"),
    "09a4995b": (56,  "carre()\n\ndef carre():\n\tfor k in range(4):\n\t\tavancer(1)\n\t\ttourner(90)\n\nlever()\navancer(2)\nposer()\ncouleur(255,0,0)\ncarre()\nlever()\navancer(3)\nposer()\ncouleur(0,255,0)\ncarre()"),
    # ─── error_exercise level (exercise fixed by the record) ───────────────
    "4955f647": (110, "def triangle():\n\tfor k in range(3):\n\t\tavancer(1)\n\t\ttourner(-120)\n\ntriangle()\navancer(2)\navancer(3)\ntriangle()\navancer(1)\ntourner(90)\navancer(2)\ntriangle()"),
    "cccf718d": (110, "def triangle():\n\tfor k in range(3):\n\t\tavancer(1)\n\t\ttourner(-120)\n\navancer(2)\ntriangle(1)\navancer(3)\ntriangle(2)\navancer(1)\ntourner(90)\navancer(2)\ntriangle(3)"),
    "54a21c3f": (116, "def vroum(n):\n\tgauche(n)\n\thaut(1)\n\nvroum(3)\nvroum(4)\ngauche(2)\nbas(1)"),
    # ─── exercise level (exercise fixed by the record) ──────────────────────
    "a769dedb": (109, "def vroum(n):\n\tdroite(2)\n\tbas(1)\n\nvroum()\nvroum()\nbas(3)\nvroum()"),
    "c8fdd59e": (109, "def vroum():\n\tdroite(n)\n\tbas(1)\n\nvroum(2)\nvroum(2)\nbas(3)\nvroum(2)"),
    "5ff6d270": (116, "gauche(3)\nhaut(1)\ngauche(4)\nhaut(1)\ngauche(2)\nbas(1)\ngauche(2)\nhaut(1)"),
    # ─── task_type level (exercise chosen from the KC) ──────────────────────
    "730ecf27": (112, "def carre(n):\n\tfor k in range(4):\n\t\tavancer(n)\n\t\ttourner(90)\n\ncarre(3)\navancer(5)\ncarre(3)\navancer(3)\ncarre(3)\navancer(1)\ncarre(3)"),
    "5a59928b": (118, "def carre(n):\n\tprint(n*n)\n\nprint(carre(7))\nprint(carre(10))\nprint(carre(-5))"),
    "0f066710": (117, "def triple(n)\n\treturn 3*n"),
    "976c3caa": (114, "f(n):\n\treturn 4*n+5"),
    "08563d3b": (106, "def triangle(x,y):\n\tfor k in range(y):\n\t\tfor k in range(3):\n\t\t\tavancer(x)\n\t\t\ttourner(-120)\n\t\tx = x + 1\n\ntriangle(4,2)\ntourner(180)\ncouleur(255,255,0)\ntriangle(3,4)"),
    "fef8559d": (108, "def angle(n):\navancer(n)\ntourner(90)\navancer(1)\n\nangle(2)\ncouleur(255,0,0)\nangle(3)\ncouleur(0,255,0)\nangle(5)"),
    "d91bb875": (115, "def f(n):\n\tdroite(n)\n\thaut(1)\n\ndef g(n):\n\thaut(n)\n\tgauche(1)\n\nf(4)\nf(2)\ng(2)\ng(1)\nhaut(2)\nf"),
    "9f516f4d": (96,  "def multiplier(a):\n\treturn a*b"),
}


def load_exercises() -> dict:
    data = json.loads(EXERCISES_JSON.read_text(encoding="utf-8"))
    return {e["exerciseId"]: e for e in data}


def _content_to_html(content: str) -> str:
    """Escape text but convert platform markup to real HTML.

    Feedback texts use <code-inline> / <code-block> tags; map them to
    <code> and <pre><code>, and newlines outside code blocks to <br/>.
    """
    out = html.escape(content)
    out = out.replace("&lt;code-inline&gt;", "<code>").replace("&lt;/code-inline&gt;", "</code>")
    out = out.replace("&lt;code-block&gt;", "<pre><code>").replace("&lt;/code-block&gt;", "</code></pre>")
    # newlines → <br/>, except inside <pre> blocks where they are significant
    parts = re.split(r"(<pre><code>.*?</code></pre>)", out, flags=re.S)
    return "".join(p if p.startswith("<pre>") else p.replace("\n", "<br/>")
                   for p in parts)


def feedback_to_html(result_xml: str) -> str:
    root = ET.fromstring(result_xml)
    parts = []
    components = root.find("components")
    for comp in components if components is not None else []:
        char = comp.get("characteristic", "")
        if comp.get("type") == "image":
            url = (comp.findtext("image_url") or "").strip()
            if url.startswith("/"):
                url = IMAGE_URL_PREFIX + url
            parts.append(
                f'<figure class="feedback-component" data-characteristic="{html.escape(char)}">'
                f'<img src="{html.escape(url)}" alt="Illustration annotée de l\'exercice"/>'
                f"</figure>"
            )
        else:
            content = (comp.findtext("content") or "").strip()
            parts.append(
                f'<p class="feedback-component" data-characteristic="{html.escape(char)}">'
                f"{_content_to_html(content)}</p>"
            )
    return '<div class="feedback">' + "".join(parts) + "</div>"


def main(src: str, dst: str) -> None:
    exercises = load_exercises()
    rows = list(csv.DictReader(open(src, encoding="utf-8")))

    out_rows = []
    for r in rows:
        prefix = r["id"][:8]
        ex_id, errored = CONTEXTS[prefix]
        if r["exercise_id"] and int(r["exercise_id"]) != ex_id:
            raise ValueError(f"{prefix}: DB exercise {r['exercise_id']} != mapped {ex_id}")
        ex = exercises[ex_id]
        ex_type = {"consoleDisplay": "console"}.get(ex["exerciseType"], ex["exerciseType"])
        r.update({
            "context_exercise_id": ex_id,
            "context_exercise_title": ex["exerciseTitle"],
            "context_exercise_type": ex_type,
            "correct_submission": ex["correctCodes"][0] if ex["correctCodes"] else "",
            "errored_submission": errored,
            "feedback_html": feedback_to_html(r["result_xml"]),
        })
        out_rows.append(r)

    with open(dst, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(out_rows[0].keys()))
        writer.writeheader()
        writer.writerows(out_rows)
    print(f"Wrote {len(out_rows)} rows to {dst}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "feedback_sample.csv",
         sys.argv[2] if len(sys.argv) > 2 else "feedback_sample_enriched.csv")
