"""Parse manual robot path hints into step dicts for draw_annotations().

Line format — one segment per line, each segment = one step number = one badge color:

  (x,y) -> (x2,y2) primitive1(n), primitive2(n) [label()]
  (x,y) primitive1(n) [label()]
  primitive1(n) [label()]          ← start position chained from previous segment

Coordinate convention (user-facing):
  • Bottom-left cell is (0, 0)
  • x = vertical axis  (x increases upward)
  • y = horizontal axis (y increases rightward)

Grid-coord conversion: row = (rows - 1) - x,  col = y

Primitives and their screen direction:
  droite(n) → right  (col + n)
  gauche(n) → left   (col - n)
  bas(n)    → down   (row + n)   [x decreases]
  haut(n)   → up     (row - n)   [x increases]

Color grouping:
  • If a non-primitive label name (custom function) appears on the line → all arrows
    in that segment share the label's color (from the custom palette).
  • If only one primitive type is used → that primitive's fixed color.
  • If multiple primitives with no label → one custom-palette color for the segment.
"""
from __future__ import annotations

import re
import logging

logger = logging.getLogger(__name__)

_PRIMITIVES: frozenset[str] = frozenset(
    {"droite", "gauche", "bas", "haut", "right", "left", "down", "up"}
)

_PRIMITIVE_COLORS: dict[str, str] = {
    "droite": "blue",   "right": "blue",
    "gauche": "pink",   "left":  "pink",
    "bas":    "orange", "down":  "orange",
    "haut":   "green",  "up":    "green",
}

# Each distinct user-defined function label gets the next color from this palette.
_USER_FUNCTION_PALETTE = ["purple", "teal", "rose", "yellow", "red"]

# (row_delta, col_delta, direction_name) — in grid coordinates
_DELTA: dict[str, tuple[int, int, str]] = {
    "droite": (0, +1, "right"), "right": (0, +1, "right"),
    "gauche": (0, -1, "left"),  "left":  (0, -1, "left"),
    "bas":    (+1, 0, "down"),  "down":  (+1, 0, "down"),
    "haut":   (-1, 0, "up"),    "up":    (-1, 0, "up"),
}

_COORD_RE = re.compile(r'\(\s*(\d+)\s*,\s*(\d+)\s*\)')
_CALL_RE  = re.compile(r'([a-zA-Z_]\w*)\s*\(\s*(\d*)\s*\)')


def _user_to_grid(x: int, y: int, rows: int) -> tuple[int, int]:
    """Convert user coords (bottom-left = 0,0) to grid coords (top-left = 0,0)."""
    return (rows - 1 - x, y)


def parse_hint(hint: str, robot_map: dict) -> list[dict]:
    """Parse the manual decomposition hint into path step dicts.

    Each non-empty, non-comment line is one segment (= one step_num, one color).
    Returns [] when the hint is empty or contains no recognisable movements.
    """
    if not hint or not hint.strip():
        return []

    grid = robot_map.get("grid", [])
    rows = robot_map.get("rows", len(grid))
    cols = robot_map.get("cols", len(grid[0]) if grid else 0)

    # Start from the robot's I cell as the default chain origin
    cur_row, cur_col = 0, 0
    for r, row in enumerate(grid):
        for c, cell in enumerate(row):
            if cell == "I":
                cur_row, cur_col = r, c

    color_map: dict[str, str] = dict(_PRIMITIVE_COLORS)
    step_num  = 0
    steps: list[dict] = []

    for raw_line in hint.strip().splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#'):
            continue

        # Extract (x,y) coordinates — first one overrides current position
        coords = [(int(m.group(1)), int(m.group(2))) for m in _COORD_RE.finditer(line)]

        # Extract all fn(n) / fn() calls
        calls: list[tuple[str, int]] = []
        for m in _CALL_RE.finditer(line):
            name  = m.group(1)
            count = int(m.group(2)) if m.group(2) else 1
            calls.append((name, count))

        # Separate primitives from label-only names
        primitive_calls = [(n, c) for n, c in calls if n in _PRIMITIVES]
        label_calls     = [(n, c) for n, c in calls if n not in _PRIMITIVES]

        if not primitive_calls:
            logger.debug("[hint_parser] no primitive calls on line: %r — skipping", line)
            continue

        # ── Determine segment label (drives color) ────────────────────────────
        if label_calls:
            # Custom function name present → all arrows in this segment share its color
            label = label_calls[0][0]
        elif len({n for n, _ in primitive_calls}) == 1:
            # Single primitive type → use its fixed color
            label = primitive_calls[0][0]
        else:
            # Mixed primitives, no label → assign a fresh custom-palette color
            label = f"_group_{step_num + 1}"

        if label not in color_map:
            user_fn_count = sum(1 for k in color_map if k not in _PRIMITIVE_COLORS)
            color_map[label] = _USER_FUNCTION_PALETTE[user_fn_count % len(_USER_FUNCTION_PALETTE)]

        # ── Override start position when coordinates are given ────────────────
        if coords:
            ux, uy = coords[0]
            cur_row, cur_col = _user_to_grid(ux, uy, rows)

        step_num += 1

        # ── Execute each primitive in order ───────────────────────────────────
        for prim, n in primitive_calls:
            if prim not in _DELTA:
                logger.warning("[hint_parser] unknown primitive %r — skipping", prim)
                continue
            dr, dc, direction = _DELTA[prim]
            for _ in range(n):
                nr, nc = cur_row + dr, cur_col + dc
                if not (0 <= nr < rows and 0 <= nc < cols):
                    logger.warning(
                        "[hint_parser] move (%d,%d)→(%d,%d) is out of bounds — stopping",
                        cur_row, cur_col, nr, nc,
                    )
                    break
                steps.append({
                    "from_row":    cur_row,
                    "from_col":    cur_col,
                    "to_row":      nr,
                    "to_col":      nc,
                    "direction":   direction,
                    "instruction": label,
                    "step_num":    step_num,
                })
                cur_row, cur_col = nr, nc

    logger.info(
        "[hint_parser] parsed %d arrow(s) across %d segment(s)",
        len(steps), step_num,
    )
    return steps
