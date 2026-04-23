"""Prompts for the Gemini image annotation agent — AlgoPython decomposition style."""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

# ── Reference image loader ─────────────────────────────────────────────────────

@lru_cache(maxsize=8)
def _load_reference_bytes(path: str) -> bytes:
    return Path(path).read_bytes()


def load_reference_images(exercise_type: str, max_count: int = 2) -> list[bytes]:
    """
    Load up to `max_count` F_* reference images for the given exercise_type.
    Files named F_*.png are the annotated gold examples (feedback style references).
    Returns list of PNG bytes, empty list if directory not found.
    """
    from core.config import get_settings
    base = Path(get_settings().reference_images_dir)

    # Map exercise_type to subfolder; console has no references
    folder_map = {"design": "design", "robot": "robot"}
    subfolder = folder_map.get(exercise_type, "design")
    folder = base / subfolder

    if not folder.exists():
        return []

    candidates = sorted(p for p in folder.iterdir() if p.name.startswith("F_") and p.suffix.lower() == ".png")
    selected = candidates[:max_count]
    return [_load_reference_bytes(str(p)) for p in selected]


# ── System prompt ──────────────────────────────────────────────────────────────

ANNOTATION_PLANNER_SYSTEM = """\
You are an expert at creating educational image annotations for AlgoPython programming exercises.
Your sole purpose: annotate a given exercise image to visually show how the big problem decomposes \
into 1–3 smaller repeating sub-patterns (loops / boucles).

## AlgoPython decomposition annotation style

You will be shown reference images that demonstrate the exact visual style to follow.
These are real AlgoPython feedback images — match their style precisely.

### Core principle
Identify every repeating pattern in the exercise path and annotate each one as "Boucle N".
The student should immediately see: "this complex movement is just this simple step repeated N times."

### Visual vocabulary

**Loop labels**
- Text: "Boucle 1", "Boucle 2", etc.
- Style: white rounded rectangle, bold dark text, drop shadow
- Placement: next to (not overlapping) the annotated region

**Directional arrows** — trace the movement direction inside each loop
- Boucle 1 → blue (#3B82F6)
- Boucle 2 → pink / magenta (#EC4899)
- Approach / transition path → orange (#F97316)
- Arrows must follow actual grid directions (horizontal or vertical; diagonal only when the path is diagonal)
- Use multiple short arrows, one per grid step, pointing in the movement direction

**Boundary markers** — frame the repeating unit
- White dashed corner brackets (⌐ ¬ L J) at the four corners of the loop bounding box
- OR a colored outline (matching the loop color) around the shape
- Must clearly delimit: "this enclosed area is the part that repeats"

**Step-count badges** (simpler alternative for uniform repetitions)
- White or yellow hexagon badge with a digit inside
- One badge per identical step in the sequence (1 → 2 → 3 …)
- Use when every single step is strictly identical (same direction, same distance)

### Rules
- 1–3 loops maximum (usually 1 or 2)
- Single loop → use blue; approach path → orange
- Two loops → Boucle 1 = blue, Boucle 2 = pink; transition arrow = orange
- Do NOT annotate non-repeating segments unless needed to show the approach path
- Keep the original image fully readable beneath all overlays
- All text labels in: {language}
"""

# ── Planning prompt ────────────────────────────────────────────────────────────

ANNOTATION_PLAN_PROMPT = """\
{reference_header}

Now annotate the following exercise image.

Context:
- Knowledge component: {kc_name} — {kc_description}
- Exercise: {exercise_block}
- Exercise type: {exercise_type_label}
{error_block}

Step 1 — Decompose: how many distinct repeating loop bodies exist in this exercise? \
Identify each one (1–3 max) and which part is the non-repeating approach.

Step 2 — Assign colors: Boucle 1 = blue, Boucle 2 = pink, approach = orange.

Step 3 — Output a JSON annotation plan (no extra text, just the JSON):

{{
  "decomposition_summary": "one sentence: e.g. 'Two loops: a 4-step square (Boucle 1) and a 2-step return (Boucle 2)'",
  "loops": [
    {{
      "name": "Boucle 1",
      "color": "blue",
      "description": "what this loop does in plain words"
    }}
  ],
  "annotations": [
    {{
      "type": "arrow | label | bracket | hexagon",
      "loop": "Boucle 1 | Boucle 2 | approach | none",
      "target_description": "precise description of where to place this element on the image",
      "text": "short text label (≤ 8 words) — empty string if no text",
      "color": "blue | pink | orange | white | yellow"
    }}
  ],
  "overall_caption": "one sentence summarizing what the annotation teaches"
}}
"""

# ── Imagen execution prompt ────────────────────────────────────────────────────

ANNOTATION_PROMPT_FOR_IMAGEN = """\
Annotate this AlgoPython exercise image in the decomposition style.

Decomposition: {decomposition_summary}

Add the following annotations exactly as described:
{annotation_list}

Caption at bottom: "{caption}"

Requirements:
- Arrows: short, directional, following the grid; one per grid step within each loop
- Corner brackets: white dashed ⌐¬LJ corners framing each loop boundary box
- Labels "Boucle N": white rounded rectangles, bold text, drop shadow, near their loop
- Hexagon badges: white or yellow filled hexagon with digit, no overlap with other elements
- Colors: Boucle 1 = blue (#3B82F6), Boucle 2 = pink (#EC4899), approach = orange (#F97316)
- Keep original image pixels fully visible beneath all overlays
- Non-overlapping layout — spread labels to avoid collision
"""

# ── Coherence verification prompt ─────────────────────────────────────────────

COHERENCE_REGION_PROMPT = """\
You are reviewing a region of an annotated AlgoPython exercise image.
Region: {region_name}

The annotation was supposed to show: {decomposition_summary}

For this region, answer with a JSON object:
{{
  "has_relevant_annotation": true | false,
  "annotation_type_seen": "arrow | label | bracket | hexagon | none",
  "is_readable": true | false,
  "follows_grid": true | false,
  "issues": ["list any visible problems in this region"]
}}
"""

COHERENCE_OVERALL_PROMPT = """\
Review this fully annotated AlgoPython exercise image.

Intended decomposition: {decomposition_summary}
Intended loops: {loops_summary}

Answer with a JSON object:
{{
  "approved": true | false,
  "decomposition_visible": true | false,
  "loop_labels_present": true | false,
  "directional_arrows_correct": true | false,
  "boundaries_clear": true | false,
  "starting_position_marked": true | false,
  "not_overcrowded": true | false,
  "issues": ["list any problems"],
  "overall_score": 0.0-1.0
}}

Approve (true) only when: loops are clearly delimited, labels are readable, \
arrows follow the correct grid directions, and the original image remains legible.
"""


# ── Builder functions ──────────────────────────────────────────────────────────

def build_annotation_plan_prompt(
    kc_name: str,
    kc_description: str,
    characteristic: str,
    language: str,
    image_description: str,
    exercise: dict | None = None,
    error: dict | None = None,
    reference_images: list[bytes] | None = None,
) -> tuple[str, str]:
    """Returns (system_prompt, user_prompt).

    When reference_images are provided they are passed separately to Gemini
    as multimodal content — the prompt just contains the reference_header marker.
    """
    exercise_type = (exercise or {}).get("exercise_type", "design")
    exercise_type_label = (
        "design — dark grid, AlgoPython design editor"
        if exercise_type == "design"
        else "robot — green grass grid, robot world"
        if exercise_type == "robot"
        else exercise_type
    )
    exercise_block = (exercise or {}).get("description", image_description)
    error_block = (
        f"- Error: [{error.get('tag', '')}] {error.get('description', '')}" if error else ""
    )
    reference_header = (
        "Style reference images are shown above. Match their annotation style exactly."
        if reference_images
        else "Follow the AlgoPython decomposition annotation style described in the system prompt."
    )

    system = ANNOTATION_PLANNER_SYSTEM.format(language=language)
    user = ANNOTATION_PLAN_PROMPT.format(
        reference_header=reference_header,
        kc_name=kc_name,
        kc_description=kc_description,
        exercise_block=exercise_block,
        exercise_type_label=exercise_type_label,
        error_block=error_block,
    )
    return system, user


def build_imagen_prompt(annotations: list[dict], caption: str, decomposition_summary: str = "") -> str:
    annotation_list = "\n".join(
        f"{i+1}. [{a['type'].upper()}] Loop: {a.get('loop','—')} | "
        f"Target: {a['target_description']} | "
        f"Text: \"{a.get('text', '')}\" | Color: {a['color']}"
        for i, a in enumerate(annotations)
    )
    return ANNOTATION_PROMPT_FOR_IMAGEN.format(
        decomposition_summary=decomposition_summary or "decompose the exercise into loops",
        annotation_list=annotation_list,
        caption=caption,
    )


def build_coherence_region_prompt(region_name: str, decomposition_summary: str) -> str:
    return COHERENCE_REGION_PROMPT.format(
        region_name=region_name,
        decomposition_summary=decomposition_summary,
    )


def build_coherence_overall_prompt(decomposition_summary: str, loops: list[dict]) -> str:
    loops_summary = ", ".join(
        f"{l['name']} ({l['color']}): {l['description']}"
        for l in loops
    ) or "one or more loops"
    return COHERENCE_OVERALL_PROMPT.format(
        decomposition_summary=decomposition_summary,
        loops_summary=loops_summary,
    )
