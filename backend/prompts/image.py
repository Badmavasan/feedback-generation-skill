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
{error_block}{grid_context}

Step 1 — Decompose: how many distinct repeating loop bodies exist in this exercise? \
Identify each one (1–3 max) and which part is the non-repeating approach.

Step 2 — Assign colors: Boucle 1 = blue, Boucle 2 = pink, approach = orange.

Step 3 — Output a JSON annotation plan. IMPORTANT rules for coordinates:
- All coordinates are fractions from 0.0 (left/top) to 1.0 (right/bottom) of the image size.
- "arrow"   → set x1,y1 (tail position) and x2,y2 (arrowhead position). Set x=0, y=0.
- "label"   → set x,y (center of the label). Set x1=y1=x2=y2=0.
- "bracket" → set x1,y1 (top-left corner) and x2,y2 (bottom-right corner). Set x=0, y=0.
- "hexagon" → set x,y (center). Set x1=y1=x2=y2=0.
Output ONLY the JSON, no other text:

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
      "type": "bracket",
      "loop": "Boucle 1",
      "text": "Boucle 1",
      "color": "blue",
      "x": 0, "y": 0,
      "x1": 0.1, "y1": 0.1, "x2": 0.6, "y2": 0.8
    }},
    {{
      "type": "arrow",
      "loop": "Boucle 1",
      "text": "",
      "color": "blue",
      "x": 0, "y": 0,
      "x1": 0.15, "y1": 0.2, "x2": 0.15, "y2": 0.5
    }},
    {{
      "type": "label",
      "loop": "Boucle 1",
      "text": "Boucle 1",
      "color": "blue",
      "x": 0.3, "y": 0.15,
      "x1": 0, "y1": 0, "x2": 0, "y2": 0
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
  "annotation_type_seen": "arrow | label | hexagon | none",
  "is_readable": true | false,
  "follows_grid": true | false,
  "no_text_on_image": true | false,
  "issues": ["list any visible problems in this region"]
}}

"is_readable" must be true only when:
- Arrows are clearly visible against the background
- Number badges are legible and not overlapping each other
- No annotation is hidden behind another element
- There is NO written text, label words, or variable names painted on the image
"""

COHERENCE_OVERALL_PROMPT = """\
Review this fully annotated AlgoPython exercise image.

Intended decomposition: {decomposition_summary}

Answer with a JSON object:
{{
  "approved": true | false,
  "decomposition_visible": true | false,
  "directional_arrows_correct": true | false,
  "starting_position_marked": true | false,
  "not_overcrowded": true | false,
  "no_text_on_image": true | false,
  "readability_score": 0.0-1.0,
  "issues": ["list any problems"],
  "overall_score": 0.0-1.0
}}

Readability criteria (readability_score):
- 1.0  All annotations are crisp, well-spaced, and immediately interpretable
- 0.7  Most annotations readable, minor overlaps or low contrast in one region
- 0.4  Several annotations hard to follow, cluttered, or obscured
- 0.0  Unreadable or annotations missing entirely

Approve (true) only when ALL of:
- Decomposition steps are clearly visible via arrows / numbered badges
- Arrows follow the correct grid directions
- Original image grid remains legible beneath annotations
- No written text, labels, or variable names appear on the image
- readability_score >= 0.6
"""


# ── Robot image pipeline prompts ──────────────────────────────────────────────

IMAGE_ANALYSIS_PROMPT = """\
Analyze this AlgoPython robot exercise screenshot precisely.

The exercise grid has {rows} rows × {cols} cols.
Logical layout (O=free, X=obstacle, I=robot start, G=goal):
{grid_text}

Locate the VISUAL grid in the image (it is a bordered rectangular area).
Ignore all UI chrome: buttons, headers, sidebars, padding outside the grid border.

Return ONLY valid JSON:
{{
  "grid_x1": 0.05,
  "grid_y1": 0.10,
  "grid_x2": 0.93,
  "grid_y2": 0.90,
  "observations": "brief description — e.g. robot top-left, goal top-right, 4×6 grid with green background"
}}

grid_x1/y1/x2/y2 are fractions of the full image dimensions (0.0=top-left, 1.0=bottom-right).
"""

# Keep old name as alias so existing callers don't break
GRID_DETECTION_PROMPT = IMAGE_ANALYSIS_PROMPT


# ── Legacy Gemini-driven system (kept for backwards compat) ───────────────────
CLAUDE_DRAW_SYSTEM = """\
You are an annotation planner for AlgoPython robot exercises.
Output ONLY valid JSON starting with {{. No prose before the JSON.
{{
  "drawings": [],
  "xml_description": "...",
  "decomposition_summary": "..."
}}
"""


# ── New: Claude-native combined image analysis + annotation planning ───────────

CLAUDE_ROBOT_COMBINED_SYSTEM = """\
You are an expert annotator for AlgoPython robot exercises.

You receive a screenshot of the exercise AND the logical grid map.
Your job is to do everything in one pass:
  1. Calibrate the grid boundaries from the image
  2. Trace the robot path from the solution code
  3. Compute exact, uniform drawing commands
  4. Output a single JSON object

## Arrow uniformity rule — ABSOLUTE
Since every cell is the same size, every move arrow must be EXACTLY one cell span.
Use a fixed 15 % inset at both ends so consecutive arrows have a clean visual gap.

Direction formulas (r = row, c = col of departure cell):
  RIGHT → (r, c) to (r, c+1):  x1 = cx(r,c)+0.15·cw,  x2 = cx(r,c+1)−0.15·cw,  y1=y2=cy(r,c)
  LEFT  → (r, c) to (r, c-1):  x1 = cx(r,c)−0.15·cw,  x2 = cx(r,c-1)+0.15·cw,  y1=y2=cy(r,c)
  DOWN  → (r, c) to (r+1, c):  y1 = cy(r,c)+0.15·ch,  y2 = cy(r+1,c)−0.15·ch,  x1=x2=cx(r,c)
  UP    → (r, c) to (r-1, c):  y1 = cy(r,c)−0.15·ch,  y2 = cy(r-1,c)+0.15·ch,  x1=x2=cx(r,c)

where  cx(r,c) = grid_x1 + (c+0.5)·cell_w
       cy(r,c) = grid_y1 + (r+0.5)·cell_h
       cell_w  = (grid_x2−grid_x1) / cols
       cell_h  = (grid_y2−grid_y1) / rows

All arrows produced by the SAME type of move (e.g. all rightward moves) will have
IDENTICAL x/y extents — this guarantees uniform size.

## Drawing types available

arrow  : {{"type":"arrow",  "x1":f,"y1":f,"x2":f,"y2":f,"color":str,"dashed":false,"width":"normal"}}
         "dashed":true for transition / approach segments.
         "width": "thin"|"normal"|"thick" — use thick for the primary annotated path.

marker : {{"type":"marker","x":f,"y":f,"direction":str,"color":str}}
         Filled chevron at the robot start cell, pointing in the initial direction.
         direction: "right"|"down"|"left"|"up"

badge  : {{"type":"badge","x":f,"y":f,"text":str,"color":str,"large":false,"shape":"hex"}}
         Step-count or loop-count badge. "shape":"hex"|"circle".
         ONLY add when counts or step labels are explicitly requested.
         Place at cell corners — NEVER on top of an arrow line.

dot    : {{"type":"dot","x":f,"y":f,"color":str}}
         Small filled circle for marking key positions (goal, pivot, waypoint).

## Color rules — MANDATORY
Every drawing must have an explicit "color" field.
Same logical group → same color throughout.
  "blue"   → main path / first loop body
  "pink"   → second loop body
  "orange" → approach / transition (use "dashed":true)
  "yellow" → robot start marker

## Output format — CRITICAL
Your response MUST begin with {{ and contain only the JSON.
No prose, no markdown, no explanation before or after.

{{
  "grid_x1": float,
  "grid_y1": float,
  "grid_x2": float,
  "grid_y2": float,
  "cell_w":  float,
  "cell_h":  float,
  "drawings": [ ... ],
  "xml_description": "2–4 sentences in {{language}} for the student",
  "decomposition_summary": "one English sentence"
}}
"""


CLAUDE_ROBOT_COMBINED_PROMPT = """\
## Exercise screenshot
(image attached above)

## Logical grid — {rows} rows × {cols} cols
[O = free cell,  X = obstacle,  I = robot start,  G = goal flag]

{grid_text}

  Robot START (I): row {start_row}, col {start_col}
  Goal FLAG  (G):  row {goal_row},  col {goal_col}

## Solution(s)
{solutions_block}

## Knowledge component
{kc_name} — {kc_description}

## Annotation request
{user_request}
{eval_feedback_block}
---
## Work through these steps in your thinking, then output the JSON

### Step 1 — Calibrate the grid from the image
Look at the screenshot. The grid is the bordered rectangular area — ignore all chrome
(buttons, headers, score panel, padding outside the grid border).

Determine as fractions of the full image size:
  grid_x1 = left edge of grid
  grid_y1 = top edge of grid
  grid_x2 = right edge of grid
  grid_y2 = bottom edge of grid

Compute:
  cell_w = (grid_x2 − grid_x1) / {cols}
  cell_h = (grid_y2 − grid_y1) / {rows}

Cross-check: visually identify the START cell (I) at row {start_row}, col {start_col}
and the GOAL cell (G) at row {goal_row}, col {goal_col}. Confirm their centres lie
within the grid area you calibrated.

### Step 2 — Trace the robot path
For each instruction in the solution, list every cell visited:
  (row, col, facing_direction)

Robot movement rules:
  • avancer(n)       → move n cells in the current facing direction
  • tourner_droite() → rotate 90° clockwise  (if present)
  • tourner_gauche() → rotate 90° counter-clockwise  (if present)
  • Initial facing: RIGHT (unless the grid or code indicates otherwise)

After tracing, verify:
  ✓ Path starts at I  (row {start_row}, col {start_col})
  ✓ Path ends at G    (row {goal_row}, col {goal_col})
  ✓ No step lands on X (obstacle)
If verification fails, re-read the solution and re-trace.

### Step 3 — Compute uniform arrow coordinates
Apply the direction formulas from the system prompt using your calibrated
grid_x1, grid_y1, cell_w, cell_h.

UNIFORMITY CHECKS before writing the JSON:
  • All rightward arrows: x-span must equal cell_w × 0.70 exactly
  • All downward arrows:  y-span must equal cell_h × 0.70 exactly
  • (same for left/up — mirror the formula)
  • y1 == y2 for all horizontal arrows
  • x1 == x2 for all vertical arrows

### Step 4 — Plan the annotation
Annotate only what the request asks for.
One arrow per cell-to-cell step.
Add a yellow marker at the robot start, pointing in the initial direction.
Add orange dashed arrows for any approach / transition segments.
{badge_note}

### Step 5 — Final check
Before writing the JSON:
  • Count total arrows — does it match the total number of avancer steps?
  • Is every coordinate in [0.0, 1.0]?
  • Are badges (if any) placed at cell corners, not on arrow lines?
"""

# ── Eval prompt ────────────────────────────────────────────────────────────────

IMAGE_EVAL_PROMPT = """\
You are evaluating an annotated AlgoPython robot exercise image.
{ref_instruction}
The user asked for:
"{hint}"

Grid context:
- Robot START (I) is at image position ({start_x:.3f}, {start_y:.3f})
- Goal FLAG (G) is at image position ({goal_x:.3f}, {goal_y:.3f})
(coordinates are fractions 0.0–1.0 of image width/height)

Evaluate the annotation on ALL FIVE criteria:

1. REQUEST MATCH — Does the annotation show exactly what the user asked for?

2. PATH COHERENCE — Do the drawn arrows form a valid robot path?
   - The first arrow must start near the robot START position ({start_x:.3f}, {start_y:.3f}).
   - The last arrow must end near the GOAL position ({goal_x:.3f}, {goal_y:.3f}).
   - Arrows must be connected end-to-start (no teleportation, no missing segments).
   - If arrows point in a direction that would take the robot away from the goal or into
     an obstacle, that is a path coherence failure.
   This is the MOST IMPORTANT criterion — an incoherent path means the annotation is wrong.

3. SPACING — Are individual step arrows visually separated from each other?
   Each arrow should represent one distinct step — they must not merge into one long line.

4. CLARITY — Is each annotated element (arrow, badge, dot) immediately recognisable
   as a distinct, separate action? Badges must NOT overlap arrow lines.

5. READABILITY — Is the overall annotation clean, uncluttered, and easy to understand?
   Colors must be vivid and coherent (same logical group = same color throughout).

Return ONLY valid JSON:
{{
  "satisfied": false,
  "score": 0.0,
  "request_match": true,
  "path_coherent": false,
  "spacing_ok": false,
  "clarity_ok": false,
  "readability_ok": false,
  "issues": [
    "arrows start at the wrong position — first arrow should be near ({start_x:.3f}, {start_y:.3f})",
    "..."
  ]
}}

satisfied = true ONLY when ALL five criteria pass. path_coherent=false is an automatic fail.
score: 1.0=all pass, 0.7=one minor issue, 0.4=one criterion clearly fails, 0.0=path_coherent=false or multiple failures.
issues: specific, actionable instructions for the next attempt (empty when satisfied=true).
"""

CLAUDE_DRAW_PROMPT = """\
## Image analysis (from Gemini vision)

grid_x1 = {grid_x1:.4f}   ← left edge as fraction of image width
grid_y1 = {grid_y1:.4f}   ← top edge as fraction of image height
grid_x2 = {grid_x2:.4f}   ← right edge as fraction of image width
grid_y2 = {grid_y2:.4f}   ← bottom edge as fraction of image height

Cell size:  cell_w = {cell_w:.4f}   cell_h = {cell_h:.4f}
Grid:       {rows} rows × {cols} cols

Gemini observations: {observations}

Cell center formula:
  cx(r,c) = {grid_x1:.4f} + (c + 0.5) × {cell_w:.4f}
  cy(r,c) = {grid_y1:.4f} + (r + 0.5) × {cell_h:.4f}

## Logical grid  [O=free  X=obstacle  I=robot start  G=goal]
{grid_text}

  Robot START: row={start_row}, col={start_col}  → ({start_cx:.4f}, {start_cy:.4f})
  GOAL:        row={goal_row},  col={goal_col}   → ({goal_cx:.4f},  {goal_cy:.4f})

## Solution(s)
{solutions_block}

## Knowledge component
{kc_name} — {kc_description}

## User annotation request
{user_request}
{eval_feedback_block}
## Steps

### Step 1 — Trace the path (mandatory — do this before anything else)
Robot primitive: avancer(n) = move n cells in the current facing direction.
Initial facing: RIGHT unless the grid clearly indicates otherwise.

For each avancer(n) call, list every intermediate cell:
  Before move: (row, col, facing)
  After each step cell: verify the destination cell is O or G (not X — obstacle).
  After move: (row, col, facing)

**PATH VALIDITY CHECK**: After tracing all avancer calls, verify:
  - The path starts at the I cell: ({start_row}, {start_col}) → ({start_cx:.4f}, {start_cy:.4f})
  - The path ends at the G cell:  ({goal_row}, {goal_col})  → ({goal_cx:.4f},  {goal_cy:.4f})
  - No step lands on an X cell
If the path does NOT reach the goal, you have a tracing error — re-read the solution.

### Step 2 — Identify what the user asked for
Map the request to specific path segments/structure.
Only plan drawings for what was explicitly requested.
Assign colors coherently (same group = same color throughout).
The first arrow's tail MUST be at ({start_cx:.4f}, {start_cy:.4f}).
The last arrow's head MUST be at or near ({goal_cx:.4f}, {goal_cy:.4f}).

### Step 3 — Compute coordinates with inset for visual spacing
Use the cell center formula for arrow tail and head, then apply 12% inset from each end
so consecutive arrows have a visible gap between them:
  raw_tail = center of departure cell
  raw_head = center of arrival cell
  dx = raw_head_x - raw_tail_x,  dy = raw_head_y - raw_tail_y
  x1 = raw_tail_x + 0.12 * dx,   y1 = raw_tail_y + 0.12 * dy   ← tail with inset
  x2 = raw_head_x - 0.12 * dx,   y2 = raw_head_y - 0.12 * dy   ← head with inset

This 12% inset on each end creates ~24% gap — each step arrow is visually distinct.
Verify all final values are in [0.0, 1.0].

### Step 4 — Output the JSON drawings list.
"""

# ── Keep old names as aliases for backwards compat ────────────────────────────
CLAUDE_ROBOT_ANNOTATION_SYSTEM = CLAUDE_DRAW_SYSTEM
CLAUDE_ROBOT_ANNOTATION_PROMPT = CLAUDE_DRAW_PROMPT


def build_image_analysis_prompt(exercise: dict) -> str:
    """Build the Gemini image analysis prompt from the exercise robot_map."""
    robot_map = (exercise or {}).get("robot_map") or {}
    grid      = robot_map.get("grid", [])
    rows      = robot_map.get("rows", len(grid))
    cols      = robot_map.get("cols", len(grid[0]) if grid else 0)
    grid_text = "\n".join(
        f"  row {r}: " + " ".join(str(cell) for cell in row)
        for r, row in enumerate(grid)
    )
    return IMAGE_ANALYSIS_PROMPT.format(rows=rows, cols=cols, grid_text=grid_text)


# Keep old name as alias
build_grid_detection_prompt = build_image_analysis_prompt


def build_eval_prompt(
    hint: str,
    has_references: bool = False,
    start_pos: tuple[float, float] | None = None,
    goal_pos: tuple[float, float] | None = None,
) -> str:
    """Build the evaluation prompt Gemini uses to check if the annotation satisfies the user.

    has_references: set True when reference images are prepended to the Gemini call.
    start_pos: (x, y) image fractions for the robot START cell (I).
    goal_pos:  (x, y) image fractions for the GOAL cell (G).
    """
    ref_instruction = (
        "Reference annotation examples are shown above. "
        "Cross-reference the visual style, color vibrancy, arrow clarity, and badge placement "
        "against those examples when scoring.\n"
        if has_references else ""
    )
    sx, sy = start_pos if start_pos else (0.5, 0.5)
    gx, gy = goal_pos  if goal_pos  else (0.5, 0.5)
    return IMAGE_EVAL_PROMPT.format(
        hint=hint.strip(),
        ref_instruction=ref_instruction,
        start_x=sx, start_y=sy,
        goal_x=gx,  goal_y=gy,
    )


def build_robot_combined_prompt(
    exercise: dict,
    base_image: bytes,
    kc_name: str,
    kc_description: str,
    language: str,
    decomposition_hint: str | None = None,
    eval_feedback: list[str] | None = None,
) -> tuple[str, list]:
    """Build the single-pass Claude prompt: image analysis + path tracing + drawing.

    Claude receives the screenshot and the logical map in one call.
    It calibrates the grid, traces the path, computes uniform arrows, and outputs JSON.

    Returns (system_prompt, user_content_list) for the Anthropic messages API.
    The content list starts with the image block followed by the text prompt.
    """
    import base64

    robot_map = (exercise or {}).get("robot_map") or {}
    grid      = robot_map.get("grid", [])
    rows      = robot_map.get("rows", len(grid))
    cols      = robot_map.get("cols", len(grid[0]) if grid else 0)

    grid_text = "\n".join(
        f"  row {r}: " + "  ".join(str(cell) for cell in row)
        for r, row in enumerate(grid)
    )

    start_row = start_col = goal_row = goal_col = 0
    for r, row in enumerate(grid):
        for c, cell in enumerate(row):
            if cell == "I":
                start_row, start_col = r, c
            elif cell == "G":
                goal_row, goal_col = r, c

    solutions = exercise.get("possible_solutions", [])
    solutions_block = (
        "\n\n".join(f"```python\n{s}\n```" for s in solutions[:3])
        if solutions else "(no solution provided)"
    )

    user_request = (
        decomposition_hint.strip()
        if decomposition_hint and decomposition_hint.strip()
        else (
            "Decompose the solution into its main repeating structure. "
            "Show the complete path with blue arrows for each avancer() step. "
            "Mark the robot start with a yellow marker. "
            "Use orange dashed arrows for any approach/transition moves before the loop."
        )
    )

    badge_note = (
        "The request mentions counts — add a badge (shape:hex) for loop repetitions."
        if decomposition_hint and any(w in decomposition_hint.lower()
                                      for w in ["fois", "times", "count", "×", "x", "badge"])
        else "Do NOT add badges unless the request explicitly asks for counts."
    )

    eval_feedback_block = ""
    if eval_feedback:
        lines = "\n".join(f"  - {iss}" for iss in eval_feedback)
        eval_feedback_block = f"\n## Previous attempt — fix these issues:\n{lines}\n"

    user_text = CLAUDE_ROBOT_COMBINED_PROMPT.format(
        rows=rows, cols=cols,
        grid_text=grid_text,
        start_row=start_row, start_col=start_col,
        goal_row=goal_row,   goal_col=goal_col,
        solutions_block=solutions_block,
        kc_name=kc_name, kc_description=kc_description,
        user_request=user_request,
        eval_feedback_block=eval_feedback_block,
        badge_note=badge_note,
    )

    b64 = base64.standard_b64encode(base_image).decode()
    user_content: list = [
        {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": b64}},
        {"type": "text",  "text": user_text},
    ]
    system = CLAUDE_ROBOT_COMBINED_SYSTEM.replace("{language}", language)
    return system, user_content


def build_robot_draw_prompt(
    exercise: dict,
    image_analysis: dict,
    kc_name: str,
    kc_description: str,
    language: str,
    base_image: bytes | None = None,
    decomposition_hint: str | None = None,
    eval_feedback: list[str] | None = None,
) -> tuple[str, list]:
    """Returns (system_prompt, user_content_list) for Claude annotation planning.

    image_analysis: dict returned by GeminiImageAgent.analyze_image — must have at minimum
      grid_x1, grid_y1, grid_x2, grid_y2.
    decomposition_hint: free-text user request driving what to annotate.
    eval_feedback: issues from a previous evaluation round (triggers regeneration).
    """
    import base64

    robot_map = (exercise or {}).get("robot_map") or {}
    grid = robot_map.get("grid", [])
    rows = robot_map.get("rows", len(grid))
    cols = robot_map.get("cols", len(grid[0]) if grid else 0)

    # Sanity-clamp bounds from Gemini analysis
    def _clamp(v, lo, hi, default):
        return max(lo, min(hi, v)) if isinstance(v, (int, float)) else default

    grid_x1 = _clamp(image_analysis.get("grid_x1"), 0.0, 0.49, 0.05)
    grid_y1 = _clamp(image_analysis.get("grid_y1"), 0.0, 0.49, 0.05)
    grid_x2 = _clamp(image_analysis.get("grid_x2"), 0.51, 1.0, 0.95)
    grid_y2 = _clamp(image_analysis.get("grid_y2"), 0.51, 1.0, 0.95)
    cell_w  = (grid_x2 - grid_x1) / cols if cols else 0.1
    cell_h  = (grid_y2 - grid_y1) / rows if rows else 0.1

    start_row = start_col = goal_row = goal_col = 0
    for r, row in enumerate(grid):
        for c, cell in enumerate(row):
            if cell == "I":
                start_row, start_col = r, c
            elif cell == "G":
                goal_row, goal_col = r, c

    start_cx = grid_x1 + (start_col + 0.5) * cell_w
    start_cy = grid_y1 + (start_row + 0.5) * cell_h
    goal_cx  = grid_x1 + (goal_col  + 0.5) * cell_w
    goal_cy  = grid_y1 + (goal_row  + 0.5) * cell_h

    grid_text = "\n".join(
        f"  row {r}: " + " ".join(str(cell) for cell in row)
        for r, row in enumerate(grid)
    )

    solutions = exercise.get("possible_solutions", [])
    solutions_block = (
        "\n\n".join(f"```python\n{s}\n```" for s in solutions[:3])
        if solutions else "(no solution provided)"
    )

    user_request = (
        decomposition_hint.strip()
        if decomposition_hint and decomposition_hint.strip()
        else (
            "Decompose the solution into its main repeating structure. "
            "Show the main path with blue arrows. "
            "If a for-loop is present, highlight all loop-body arrows in blue with the same color "
            "and add a ×N badge at the loop start. "
            "Mark the robot start with a yellow marker. "
            "Use orange dashed arrows for any approach/transition moves."
        )
    )

    eval_feedback_block = ""
    if eval_feedback:
        lines = "\n".join(f"  - {iss}" for iss in eval_feedback)
        eval_feedback_block = f"\n## Previous attempt issues — fix these:\n{lines}\n"

    observations = image_analysis.get("observations", "")

    user_text = CLAUDE_DRAW_PROMPT.format(
        grid_x1=grid_x1, grid_y1=grid_y1, grid_x2=grid_x2, grid_y2=grid_y2,
        rows=rows, cols=cols, cell_w=cell_w, cell_h=cell_h,
        observations=observations or "no additional observations",
        grid_text=grid_text,
        start_row=start_row, start_col=start_col, start_cx=start_cx, start_cy=start_cy,
        goal_row=goal_row,   goal_col=goal_col,   goal_cx=goal_cx,   goal_cy=goal_cy,
        solutions_block=solutions_block,
        kc_name=kc_name, kc_description=kc_description,
        user_request=user_request,
        eval_feedback_block=eval_feedback_block,
    )

    user_content: list = []
    if base_image:
        b64 = base64.standard_b64encode(base_image).decode()
        user_content.append({
            "type": "image",
            "source": {"type": "base64", "media_type": "image/png", "data": b64},
        })
    user_content.append({"type": "text", "text": user_text})

    system = CLAUDE_DRAW_SYSTEM.format(language=language)
    return system, user_content


def build_robot_annotation_prompt(
    exercise: dict,
    grid_bounds: dict,
    kc_name: str,
    kc_description: str,
    language: str,
    base_image: bytes | None = None,
    decomposition_hint: str | None = None,
    eval_feedback: list[str] | None = None,
) -> tuple[str, list]:
    """Backwards-compatible wrapper — grid_bounds is used as image_analysis."""
    return build_robot_draw_prompt(
        exercise=exercise,
        image_analysis=grid_bounds,
        kc_name=kc_name,
        kc_description=kc_description,
        language=language,
        base_image=base_image,
        decomposition_hint=decomposition_hint,
        eval_feedback=eval_feedback,
    )


# ── Grid coordinate helper ─────────────────────────────────────────────────────

def _build_grid_context(exercise: dict | None) -> str:
    """
    For robot exercises: parse the robot_map and return a precise coordinate
    reference table so Gemini can place annotations on exact cell positions.

    Cell (row r, col c) occupies the fractional rectangle:
        x ∈ [c/cols, (c+1)/cols],  y ∈ [r/rows, (r+1)/rows]
    """
    if not exercise:
        return ""
    robot_map = exercise.get("robot_map")
    if not robot_map:
        return ""

    grid = robot_map.get("grid", [])
    rows = robot_map.get("rows", len(grid))
    cols = robot_map.get("cols", len(grid[0]) if grid else 0)
    if not grid or rows == 0 or cols == 0:
        return ""

    start_cell = goal_cell = None
    annotated_rows = []
    for r, row in enumerate(grid):
        cells = []
        for c, cell in enumerate(row):
            cx = round((c + 0.5) / cols, 3)
            cy = round((r + 0.5) / rows, 3)
            cells.append(f"{cell}@({cx},{cy})")
            if cell == "I":
                start_cell = (r, c, cx, cy)
            elif cell == "G":
                goal_cell = (r, c, cx, cy)
        annotated_rows.append(f"  row {r}: " + "  ".join(cells))

    lines = [
        "",
        f"## Robot grid — {rows} rows × {cols} cols",
        "Each cell is shown as TYPE@(cx,cy) where cx,cy are the fractional CENTER",
        "coordinates you must use for annotations (0.0=left/top, 1.0=right/bottom).",
        "Cell bounding box: x1=c/cols, y1=r/rows, x2=(c+1)/cols, y2=(r+1)/rows",
        f"Cell width fraction = {round(1/cols, 4)},  cell height fraction = {round(1/rows, 4)}",
        "",
        "Grid (O=free, X=obstacle, I=robot start, G=goal):",
    ] + annotated_rows

    if start_cell:
        lines.append(f"\nRobot START (I): row={start_cell[0]}, col={start_cell[1]}, center=({start_cell[2]},{start_cell[3]})")
    if goal_cell:
        lines.append(f"GOAL (G):        row={goal_cell[0]}, col={goal_cell[1]}, center=({goal_cell[2]},{goal_cell[3]})")

    lines += [
        "",
        "NOTE: these cx,cy values are THEORETICAL (assume grid fills full image).",
        "In Step 0 you will visually calibrate the actual grid boundaries from the image",
        "and recompute all coordinates accordingly.",
    ]
    return "\n".join(lines)


# ── Claude annotation planning prompts ────────────────────────────────────────

CLAUDE_ANNOTATION_PLANNER_SYSTEM = """\
You are an expert educational annotation designer for AlgoPython robot/design exercises.

Given an uploaded exercise screenshot + grid map + correct solution code, your job is to produce a
JSON plan with two parts:

1. **image_editing_prompt** — precise natural-language instructions for an image-editing AI model
   (Nano Banana Pro) telling it exactly what visual elements to paint on the uploaded image.

2. **xml_description** — a short French text (2–4 sentences) explaining the decomposition to the
   student. This text will appear in the XML feedback, NOT on the image.

## Rules for the image_editing_prompt

STRICTLY FORBIDDEN on the image:
- Any written text, labels, words, code, variable names
- Corner brackets or rectangular borders around regions
- "Boucle", "for", "loop" or any textual annotation

ALLOWED on the image:
- Colored directional arrows (solid or dashed)
- Small numbered hexagonal/circular badges containing only a digit (1, 2, 3, 4…)
- Small filled chevron/arrow markers at start position
- Colored zone highlights (semi-transparent filled region)
- Small curved elbow arrows showing turn direction

COLOR SCHEME:
- First repeating unit: vivid blue (#4488ff), solid arrows
- Second repeating unit (if any): vivid pink (#EC4899), solid arrows
- Transition between units: orange (#F97316), dashed arrow with glow
- Start marker: yellow (#FBBF24) chevron

IMPORTANT LOGIC RULES:
- Only annotate a repeating loop if the solution code actually contains a `for` loop or explicit
  repetition. If the solution is a flat sequence of commands, just annotate each step sequentially.
- Number the steps 1, 2, 3… in the order they execute. Numbers must match the solution exactly.
- Calibrate ALL positions from the actual image (see Step 0 in the user prompt) — never use
  generic fractions that assume the grid fills the whole image.

## Output format

Output ONLY valid JSON, no markdown fences, no extra text:
{{
  "image_editing_prompt": "Full natural-language editing instructions for Nano Banana Pro...",
  "xml_description": "Texte en français pour le retour XML...",
  "decomposition_summary": "One English sentence summarising the decomposition"
}}
"""

CLAUDE_ANNOTATION_PLAN_PROMPT = """\
{grid_context}

## Correct solution(s):
{solutions_block}

## Exercise description:
{exercise_description}

## Knowledge component: {kc_name} — {kc_description}

## Your task — follow these steps in order:

### Step 0 — Calibrate the grid from the IMAGE (critical)

Look at the uploaded image carefully.
The theoretical grid above tells you the LOGICAL structure ({cols} cols × {rows} rows,
which cell is start/goal/obstacle). But the grid does NOT fill the entire image —
there are margins, toolbars, borders and padding around it.

Visually inspect the image and determine:
  grid_x1 = left edge of the grid as a fraction of image width   (e.g. 0.05)
  grid_y1 = top edge of the grid as a fraction of image height   (e.g. 0.10)
  grid_x2 = right edge of the grid as a fraction of image width  (e.g. 0.95)
  grid_y2 = bottom edge of the grid as a fraction of image height (e.g. 0.90)

From those, compute:
  cell_w = (grid_x2 - grid_x1) / {cols}
  cell_h = (grid_y2 - grid_y1) / {rows}

Cell center for logical (row r, col c):
  cx = grid_x1 + (c + 0.5) * cell_w
  cy = grid_y1 + (r + 0.5) * cell_h

Use ONLY these image-calibrated cx,cy values for every annotation coordinate.
Do NOT use the theoretical (c+0.5)/cols formula — it will be wrong for this image.

### Step 1 — Trace the path

Parse every primitive command in the solution in order:
  avancer(n) = move n cells in current facing direction
  tourner_droite() = turn right 90°   (clockwise)
  tourner_gauche() = turn left 90°    (counter-clockwise)

Write out the robot's (row, col, facing) after every single command.

### Step 2 — Identify loops

Find the repeating sub-sequence. Note which commands repeat and how many times.
Identify any transition movement between loop iterations or between two loops.

### Step 3 — Output the JSON annotation plan

For every movement step inside a loop body:
  - one "arrow" from tail cell center → head cell center
  - one "hexagon" badge at the midpoint of that arrow (text = step number "1","2"…)

For every 90° turn inside a loop body:
  - one "turn_indicator" at the corner cell center

For the loop bounding box:
  - one "bracket" x1=min_col*cell_w+grid_x1, y1=min_row*cell_h+grid_y1, etc.
  - one "label" placed just outside the bracket

For any transition:
  - one "dashed_arrow"

For the start:
  - one "chevron" at start cell center pointing in initial direction

Output ONLY the JSON — no text before or after.
"""


def build_claude_annotation_prompt(
    kc_name: str,
    kc_description: str,
    language: str,
    exercise: dict | None = None,
    image_description: str = "",
    base_image: bytes | None = None,
) -> tuple[str, list]:
    """Returns (system_prompt, user_content_list) for Claude annotation planning.
    user_content_list is a list of Anthropic content blocks (image + text).
    """
    import base64

    grid_context = _build_grid_context(exercise) or "(no grid — use visual estimates from the image)"
    solutions = (exercise or {}).get("possible_solutions", [])
    solutions_block = (
        "\n\n".join(f"```python\n{s}\n```" for s in solutions[:3])
        if solutions else "(no solution provided)"
    )
    exercise_description = (exercise or {}).get("description", image_description)

    # Extract grid dimensions for the calibration step
    robot_map = (exercise or {}).get("robot_map", {})
    grid = robot_map.get("grid", [])
    rows = robot_map.get("rows", len(grid))
    cols = robot_map.get("cols", len(grid[0]) if grid else 0)

    user_text = CLAUDE_ANNOTATION_PLAN_PROMPT.format(
        grid_context=grid_context,
        solutions_block=solutions_block,
        exercise_description=exercise_description,
        kc_name=kc_name,
        kc_description=kc_description,
        rows=rows or "?",
        cols=cols or "?",
    )

    user_content: list = []
    if base_image:
        b64 = base64.standard_b64encode(base_image).decode()
        user_content.append({
            "type": "image",
            "source": {"type": "base64", "media_type": "image/png", "data": b64},
        })
    user_content.append({"type": "text", "text": user_text})

    system = CLAUDE_ANNOTATION_PLANNER_SYSTEM.format(language=language) if "{language}" in CLAUDE_ANNOTATION_PLANNER_SYSTEM else CLAUDE_ANNOTATION_PLANNER_SYSTEM
    return system, user_content


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
        f"\n- Error: [{error.get('tag', '')}] {error.get('description', '')}" if error else ""
    )
    reference_header = (
        "Style reference images are shown above. Match their annotation style exactly."
        if reference_images
        else "Follow the AlgoPython decomposition annotation style described in the system prompt."
    )
    grid_context = _build_grid_context(exercise)

    system = ANNOTATION_PLANNER_SYSTEM.format(language=language)
    user = ANNOTATION_PLAN_PROMPT.format(
        reference_header=reference_header,
        kc_name=kc_name,
        kc_description=kc_description,
        exercise_block=exercise_block,
        exercise_type_label=exercise_type_label,
        error_block=error_block,
        grid_context=grid_context,
    )
    return system, user


def build_imagen_prompt(annotations: list[dict], caption: str, decomposition_summary: str = "") -> str:
    annotation_list = "\n".join(
        f"{i+1}. [{a.get('type','label').upper()}] Loop: {a.get('loop','—')} | "
        f"Target: {a.get('target_description', '')} | "
        f"Text: \"{a.get('text', '')}\" | Color: {a.get('color', 'blue')}"
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
    return COHERENCE_OVERALL_PROMPT.format(
        decomposition_summary=decomposition_summary or "decompose the exercise into steps",
    )
