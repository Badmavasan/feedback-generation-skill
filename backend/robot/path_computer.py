"""Deterministic robot path computation from solution code and calibrated grid bounds.

Supported movement APIs
-----------------------
Direct-direction (AlgoPython default):
  droite(n)  → right n cells   gauche(n)  → left n cells
  bas(n)     → down n cells    haut(n)    → up n cells

Legacy facing-direction:
  avancer(n)       → n cells in current facing direction
  tourner_droite() → rotate 90° clockwise
  tourner_gauche() → rotate 90° counter-clockwise

User-defined functions:
  def f(): ...  →  f() calls execute the body at the call site

Color scheme (instruction-based, NOT loop-based)
-------------------------------------------------
Each distinct instruction that produces movement gets a fixed color:
  droite / right  → blue
  gauche / left   → pink
  bas    / down   → orange
  haut   / up     → green
  avancer         → blue
  1st custom fn   → purple
  2nd custom fn   → yellow
  3rd custom fn   → teal
  4th+ custom fn  → red

Steps are numbered globally (1, 2, 3 …) in execution order; each arrow
carries a small circular badge with its step number.
"""
from __future__ import annotations

import ast
import logging
from typing import Any

logger = logging.getLogger(__name__)

# ── Direction tables ───────────────────────────────────────────────────────────

_DIRECT_PRIMITIVES: dict[str, tuple[int, int, str]] = {
    "droite":  (0,  +1, "right"),
    "gauche":  (0,  -1, "left"),
    "bas":     (+1,  0, "down"),
    "haut":    (-1,  0, "up"),
    "right":   (0,  +1, "right"),
    "left":    (0,  -1, "left"),
    "down":    (+1,  0, "down"),
    "up":      (-1,  0, "up"),
}

_DIR_DELTA: dict[str, tuple[int, int]] = {
    "right": (0,  1), "down":  (1,  0),
    "left":  (0, -1), "up":    (-1, 0),
}

_TURN_RIGHT: dict[str, str] = {
    "right": "down", "down": "left", "left": "up", "up": "right",
}
_TURN_LEFT: dict[str, str] = {
    "right": "up",   "up":   "left", "left": "down", "down": "right",
}

# Fixed color per primitive instruction name (each native function has its own color)
_PRIMITIVE_COLORS: dict[str, str] = {
    "droite":  "blue",
    "right":   "blue",
    "avancer": "blue",
    "gauche":  "pink",
    "left":    "pink",
    "bas":     "orange",
    "down":    "orange",
    "haut":    "green",
    "up":      "green",
}

# Each distinct user-defined function gets the next color from this palette (in appearance order).
# Primitive colors (blue/pink/orange/green) are excluded to avoid clashes.
_USER_FUNCTION_PALETTE = ["purple", "teal", "rose", "yellow", "red"]

# 15% inset → each arrow spans 70% of the cell dimension
_INSET = 0.15

# Direction → French primitive name (for solution_to_hint output)
_DIR_TO_PRIM: dict[str, str] = {
    "right": "droite", "left": "gauche",
    "down":  "bas",    "up":   "haut",
}


# ── AST helpers ────────────────────────────────────────────────────────────────

def _func_name(call: ast.Call) -> str:
    if isinstance(call.func, ast.Name):
        return call.func.id
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    return ""


def _resolve_int(node: ast.expr, bindings: dict[str, int], default: int = 1) -> int:
    """Resolve an AST expression to an integer, substituting bound variables."""
    if isinstance(node, ast.Constant):
        return int(node.value)
    if isinstance(node, ast.Num):          # Python <3.8 compat
        return int(node.n)
    if isinstance(node, ast.Name) and node.id in bindings:
        return bindings[node.id]
    return default


def _int_arg(call: ast.Call, idx: int = 0, default: int = 1,
             bindings: dict[str, int] | None = None) -> int:
    """Return the integer value of positional argument `idx`, resolving variables."""
    try:
        return _resolve_int(call.args[idx], bindings or {}, default)
    except IndexError:
        return default


def _range_n(for_node: ast.For, bindings: dict[str, int] | None = None) -> int:
    """Return the iteration count for a for-range loop, resolving variables."""
    iter_ = for_node.iter
    if not (isinstance(iter_, ast.Call) and iter_.args):
        return 1
    fn = (iter_.func.id if isinstance(iter_.func, ast.Name)
          else getattr(iter_.func, "attr", ""))
    if fn != "range":
        return 1
    return _resolve_int(iter_.args[0], bindings or {}, default=1)


def _collect_functions(
    stmts: list[ast.stmt],
) -> tuple[dict[str, list[ast.stmt]], dict[str, list[str]]]:
    """Collect all FunctionDef bodies and their parameter names.

    Returns:
        funcs      — name → body statements
        func_params — name → ordered list of parameter names
    """
    funcs:       dict[str, list[ast.stmt]] = {}
    func_params: dict[str, list[str]]      = {}
    for stmt in stmts:
        if isinstance(stmt, ast.FunctionDef):
            funcs[stmt.name]       = stmt.body
            func_params[stmt.name] = [arg.arg for arg in stmt.args.args]
    return funcs, func_params


# ── Path tracer ────────────────────────────────────────────────────────────────

def _trace_block(
    stmts: list[ast.stmt],
    state: dict[str, Any],
    path: list[dict],
    loop_ctr: list[int],
    step_ctr: list[int],
    funcs: dict[str, list[ast.stmt]],
    func_params: dict[str, list[str]],   # fn_name → ordered param names
    color_map: dict[str, str],            # fn_name → color (built lazily)
    current_instruction: str | None,      # outermost call site name (None at top level)
    bindings: dict[str, int] | None = None,  # variable name → resolved int value
    depth: int = 0,
) -> None:
    """Trace a block of AST statements, appending one step dict per unit cell move.

    Step numbering: step_ctr increments once per call site at the top level.
    All moves produced by that call (including inside user functions and their loops)
    share the same step_num.

    bindings: maps parameter names → their integer values for the current call frame.
    Each user-defined function call creates a fresh bindings dict from its arguments.
    """
    if depth > 20:
        logger.warning("[path_computer] max recursion depth — aborting")
        return

    b = bindings or {}

    for stmt in stmts:
        # ── Function call expression ──────────────────────────────────────────
        if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
            call = stmt.value
            fn   = _func_name(call)

            if current_instruction is not None:
                instr     = current_instruction
                this_step = step_ctr[0]
            else:
                if fn in funcs and fn not in color_map:
                    fn_idx = sum(1 for k in color_map if k not in _PRIMITIVE_COLORS)
                    color_map[fn] = _USER_FUNCTION_PALETTE[fn_idx % len(_USER_FUNCTION_PALETTE)]
                instr = fn if fn else "unknown"
                step_ctr[0] += 1
                this_step = step_ctr[0]

            if fn in _DIRECT_PRIMITIVES:
                dr, dc, direction = _DIRECT_PRIMITIVES[fn]
                n = _int_arg(call, 0, 1, bindings=b)
                for _ in range(n):
                    path.append({
                        "from_row":    state["row"],
                        "from_col":    state["col"],
                        "to_row":      state["row"] + dr,
                        "to_col":      state["col"] + dc,
                        "direction":   direction,
                        "instruction": instr,
                        "step_num":    this_step,
                    })
                    state["row"] += dr
                    state["col"] += dc

            elif fn == "avancer":
                n = _int_arg(call, 0, 1, bindings=b)
                dr, dc = _DIR_DELTA[state["facing"]]
                direction = state["facing"]
                for _ in range(n):
                    path.append({
                        "from_row":    state["row"],
                        "from_col":    state["col"],
                        "to_row":      state["row"] + dr,
                        "to_col":      state["col"] + dc,
                        "direction":   direction,
                        "instruction": instr,
                        "step_num":    this_step,
                    })
                    state["row"] += dr
                    state["col"] += dc

            elif fn == "tourner_droite":
                state["facing"] = _TURN_RIGHT[state["facing"]]
            elif fn == "tourner_gauche":
                state["facing"] = _TURN_LEFT[state["facing"]]

            elif fn in funcs:
                # Build a fresh bindings frame from the call arguments
                params    = func_params.get(fn, [])
                new_bindings = {
                    param: _int_arg(call, i, default=1, bindings=b)
                    for i, param in enumerate(params)
                }
                _trace_block(
                    funcs[fn], state, path, loop_ctr, step_ctr,
                    funcs, func_params, color_map,
                    current_instruction=instr,
                    bindings=new_bindings,
                    depth=depth + 1,
                )
            else:
                logger.debug("[path_computer] unrecognized call %r — skipping", fn)

        # ── for loop ─────────────────────────────────────────────────────────
        elif isinstance(stmt, ast.For):
            n = _range_n(stmt, bindings=b)
            loop_ctr[0] += 1
            for _ in range(n):
                _trace_block(
                    stmt.body, state, path, loop_ctr, step_ctr,
                    funcs, func_params, color_map,
                    current_instruction=current_instruction,
                    bindings=b, depth=depth,
                )

        # ── FunctionDef — skip (already collected) ────────────────────────────
        elif isinstance(stmt, ast.FunctionDef):
            pass

        # ── if-else — follow if-branch ────────────────────────────────────────
        elif isinstance(stmt, ast.If):
            _trace_block(
                stmt.body, state, path, loop_ctr, step_ctr,
                funcs, func_params, color_map,
                current_instruction=current_instruction,
                bindings=b, depth=depth,
            )


def trace_path(solution_code: str, robot_map: dict) -> list[dict]:
    """Parse and execute a robot solution, returning one step dict per unit cell move.

    Each step dict:
        from_row, from_col    — departure cell
        to_row,   to_col      — arrival cell
        direction             — "right" | "down" | "left" | "up"
        instruction           — the outermost function name that produced this step
        step_num              — global sequential step number (1-based)
    """
    grid = robot_map.get("grid", [])
    start_row = start_col = 0
    for r, row in enumerate(grid):
        for c, cell in enumerate(row):
            if cell == "I":
                start_row, start_col = r, c

    try:
        tree = ast.parse(solution_code.strip())
    except SyntaxError as exc:
        logger.warning("[path_computer] SyntaxError parsing solution: %s", exc)
        return []

    funcs, func_params = _collect_functions(tree.body)
    color_map: dict[str, str] = dict(_PRIMITIVE_COLORS)

    if funcs:
        logger.info(
            "[path_computer] user-defined functions: %s",
            {fn: func_params.get(fn, []) for fn in funcs},
        )

    state: dict[str, Any] = {"row": start_row, "col": start_col, "facing": "right"}
    path: list[dict]      = []

    _trace_block(
        tree.body, state, path,
        loop_ctr=[0], step_ctr=[0],
        funcs=funcs, func_params=func_params, color_map=color_map,
        current_instruction=None, bindings={},
    )

    if not path:
        call_names = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                name = _func_name(node)
                if name and name not in call_names:
                    call_names.append(name)
        logger.warning(
            "[path_computer] EMPTY path. Calls found: %s  Recognized: %s  User funcs: %s",
            call_names, list(_DIRECT_PRIMITIVES.keys()), list(funcs.keys()),
        )
        return []

    logger.info(
        "[path_computer] traced %d step(s), final pos=(%d,%d), instructions=%s",
        len(path), state["row"], state["col"],
        list({s["instruction"] for s in path}),
    )
    return path


def goal_reached(path: list[dict], robot_map: dict) -> bool:
    """Return True if the last step of path lands on the G cell."""
    if not path:
        return False
    grid = robot_map.get("grid", [])
    goal_row = goal_col = -1
    for r, row in enumerate(grid):
        for c, cell in enumerate(row):
            if cell == "G":
                goal_row, goal_col = r, c
    last = path[-1]
    return last["to_row"] == goal_row and last["to_col"] == goal_col


def has_for_loop(solution_code: str) -> bool:
    """Return True if the solution contains at least one for loop."""
    try:
        tree = ast.parse(solution_code.strip())
        for node in ast.walk(tree):
            if isinstance(node, ast.For):
                return True
    except SyntaxError:
        pass
    return False


# ── Coordinate conversion + drawing generation ─────────────────────────────────

def _cell_center(
    row: int, col: int, gx1: float, gy1: float, cw: float, ch: float,
) -> tuple[float, float]:
    return (gx1 + (col + 0.5) * cw, gy1 + (row + 0.5) * ch)


def _instruction_color(instr: str, color_map: dict[str, str]) -> str:
    return color_map.get(instr) or _PRIMITIVE_COLORS.get(instr) or "blue"


def _build_color_map(path: list[dict]) -> dict[str, str]:
    """Build instruction→color mapping.

    Primitives keep their fixed colors.
    Each distinct user-defined function is assigned the next color from the palette,
    in order of first appearance in the path.
    """
    color_map: dict[str, str] = dict(_PRIMITIVE_COLORS)
    palette_idx = 0
    for step in path:
        instr = step.get("instruction", "")
        if instr and instr not in color_map:
            color_map[instr] = _USER_FUNCTION_PALETTE[palette_idx % len(_USER_FUNCTION_PALETTE)]
            palette_idx += 1
    return color_map


def _badge_position(
    first_step: dict,
    gx1: float, gy1: float, cw: float, ch: float,
) -> tuple[float, float]:
    """Return (bx, by) for a segment badge — offset perpendicular to the first arrow."""
    cx, cy = _cell_center(first_step["from_row"], first_step["from_col"], gx1, gy1, cw, ch)
    direction = first_step["direction"]
    # Place badge one half-cell outside the arrow path, in the perpendicular direction
    if direction == "right":
        return cx, cy - ch * 0.55          # above
    if direction == "left":
        return cx, cy + ch * 0.55          # below
    if direction == "down":
        return cx - cw * 0.55, cy          # to the left
    if direction == "up":
        return cx + cw * 0.55, cy          # to the right
    return cx, cy - ch * 0.55


def steps_to_drawings(
    path: list[dict],
    grid_bounds: dict,
    robot_map: dict,
    add_marker: bool = True,
    add_badges: bool = True,
    show_badge_numbers: bool = False,
) -> tuple[list[dict], dict[str, str]]:
    """Convert path steps to drawing commands for draw_annotations().

    Returns (drawings, color_map) where color_map maps instruction → color.
    All coordinates are image fractions [0.0, 1.0].

    show_badge_numbers: when True (for-loop solutions only), one large numbered badge
    is placed per step_num group to indicate which iteration produced that movement.
    When False, no badges are rendered — arrows alone carry the visual meaning.
    """
    grid = robot_map.get("grid", [])
    rows = robot_map.get("rows", len(grid))
    cols = robot_map.get("cols", len(grid[0]) if grid else 0)
    if rows == 0 or cols == 0:
        return [], {}

    gx1 = float(grid_bounds.get("grid_x1", 0.05))
    gy1 = float(grid_bounds.get("grid_y1", 0.05))
    gx2 = float(grid_bounds.get("grid_x2", 0.95))
    gy2 = float(grid_bounds.get("grid_y2", 0.95))
    cw  = (gx2 - gx1) / cols
    ch  = (gy2 - gy1) / rows

    color_map = _build_color_map(path)
    drawings:  list[dict] = []

    # ── Start marker ──────────────────────────────────────────────────────────
    if add_marker and path:
        cx, cy = _cell_center(path[0]["from_row"], path[0]["from_col"], gx1, gy1, cw, ch)
        drawings.append({
            "type": "marker", "x": round(cx, 4), "y": round(cy, 4),
            "direction": path[0]["direction"], "color": "yellow",
        })

    # ── Arrows ────────────────────────────────────────────────────────────────
    for step in path:
        fcx, fcy = _cell_center(step["from_row"], step["from_col"], gx1, gy1, cw, ch)
        tcx, tcy = _cell_center(step["to_row"],   step["to_col"],   gx1, gy1, cw, ch)
        dx, dy   = tcx - fcx, tcy - fcy
        x1, y1   = fcx + _INSET * dx, fcy + _INSET * dy
        x2, y2   = tcx - _INSET * dx, tcy - _INSET * dy
        color    = _instruction_color(step.get("instruction", ""), color_map)
        drawings.append({
            "type": "arrow",
            "x1": round(x1, 4), "y1": round(y1, 4),
            "x2": round(x2, 4), "y2": round(y2, 4),
            "color": color, "dashed": False, "width": "normal",
            "step_num":    step["step_num"],
            "instruction": step.get("instruction", ""),
        })

    # ── One badge per step_num group (only when for-loop is present) ─────────
    if add_badges and show_badge_numbers and path:
        # Collect first step of each group (preserving order)
        seen: dict[int, dict] = {}
        for step in path:
            sn = step["step_num"]
            if sn not in seen:
                seen[sn] = step

        min_gap = min(cw, ch) * 0.65   # minimum distance between badge centres
        placed: list[tuple[float, float]] = []

        for sn, first_step in sorted(seen.items()):
            bx, by = _badge_position(first_step, gx1, gy1, cw, ch)
            direction = first_step["direction"]

            # Shift along the movement axis until clear of all existing badges
            for px, py in placed:
                while abs(bx - px) < min_gap and abs(by - py) < min_gap:
                    if direction in ("right", "left"):
                        bx += cw * 0.7
                    else:
                        by += ch * 0.7

            # Clamp inside image
            bx = max(0.01, min(0.99, bx))
            by = max(0.01, min(0.99, by))
            placed.append((bx, by))

            color = _instruction_color(first_step.get("instruction", ""), color_map)
            drawings.append({
                "type": "badge", "shape": "circle", "large": True,
                "x": round(bx, 4), "y": round(by, 4),
                "text": str(sn), "color": color,
            })

    return drawings, color_map


# ── solution_to_hint ───────────────────────────────────────────────────────────

def _compress_directions(group: list[dict]) -> str:
    """Compress consecutive same-direction unit steps to 'droite(2), bas(1)' text."""
    parts: list[str] = []
    i = 0
    while i < len(group):
        d = group[i]["direction"]
        prim = _DIR_TO_PRIM.get(d, d)
        count = 1
        while i + count < len(group) and group[i + count]["direction"] == d:
            count += 1
        parts.append(f"{prim}({count})")
        i += count
    return ", ".join(parts)


def solution_to_hint(solution_code: str, robot_map: dict) -> str:
    """Convert a robot solution to the manual path hint format.

    Coordinate convention: bottom-left = (0,0), x = vertical (upward), y = horizontal.

    Each line represents one logical instruction call (= one step number):
      (x1,y1) -> (x2,y2) (primitive1(n), ...) [function_name()]

    User-defined function calls include the function name as a label.
    Direct primitive calls have no extra label (color is determined by the primitive).

    Returns a multi-line string suitable for the hint parser, or "" if the solution
    cannot be traced.
    """
    path = trace_path(solution_code, robot_map)
    if not path:
        logger.warning("[solution_to_hint] trace_path returned empty — check solution code")
        return ""

    grid = robot_map.get("grid", [])
    rows = robot_map.get("rows", len(grid))

    # Group steps by step_num (preserving insertion order)
    groups: dict[int, list[dict]] = {}
    for step in path:
        sn = step["step_num"]
        if sn not in groups:
            groups[sn] = []
        groups[sn].append(step)

    lines: list[str] = []
    for sn in sorted(groups.keys()):
        group   = groups[sn]
        first   = group[0]
        last    = group[-1]
        instr   = first["instruction"]

        # User coords: x = (rows-1) - row,  y = col
        x1, y1  = (rows - 1) - first["from_row"], first["from_col"]
        x2, y2  = (rows - 1) - last["to_row"],    last["to_col"]
        prims   = _compress_directions(group)

        # User-defined functions carry their name as a label; primitives do not
        is_user_fn = instr not in _DIRECT_PRIMITIVES and instr not in _PRIMITIVE_COLORS
        if is_user_fn:
            lines.append(f"({x1},{y1}) -> ({x2},{y2}) ({prims}) {instr}()")
        else:
            lines.append(f"({x1},{y1}) -> ({x2},{y2}) ({prims})")

    hint = "\n".join(lines)
    logger.info("[solution_to_hint] %d segment(s):\n%s", len(lines), hint)
    return hint


# ── compute_drawings (orchestrator entry point) ────────────────────────────────

def compute_drawings(
    exercise: dict,
    grid_bounds: dict,
    path: list[dict] | None = None,
    language: str = "fr",
) -> tuple[list[dict], str, str]:
    """Produce drawing commands from a pre-traced path.

    If path is None, falls back to tracing the first available solution.
    Returns (drawings, xml_description, en_summary).
    """
    robot_map = exercise.get("robot_map") or {}

    if path is None:
        best_partial: list[dict] | None = None
        for sol in (exercise.get("possible_solutions") or []):
            candidate = trace_path(sol, robot_map)
            if not candidate:
                continue
            if goal_reached(candidate, robot_map):
                path = candidate
                break
            if best_partial is None:
                best_partial = candidate
        if path is None:
            path = best_partial

    if not path:
        logger.warning("[path_computer] no path to draw")
        return [], "", "No solution path found"

    solutions = exercise.get("possible_solutions") or []
    show_badges = any(has_for_loop(sol) for sol in solutions)

    drawings, color_map = steps_to_drawings(
        path, grid_bounds, robot_map, show_badge_numbers=show_badges,
    )

    instructions_used = list(dict.fromkeys(s["instruction"] for s in path))
    num_segments      = len({s["step_num"] for s in path})
    reached_g         = goal_reached(path, robot_map)

    en_summary = (
        f"{'Complete' if reached_g else 'Partial'} path: {len(path)} arrow(s), "
        f"{num_segments} step(s), instructions: {', '.join(instructions_used)}."
    )

    if language.lower().startswith("fr"):
        instr_fr = ", ".join(
            f"{fn}() [{color_map.get(fn, '?')}]" for fn in instructions_used
        )
        xml_desc = (
            f"Le robot effectue {num_segments} étape(s) "
            f"avec : {instr_fr}. "
            "Chaque type d'instruction est dessiné dans une couleur fixe et numéroté."
        )
        if not reached_g:
            xml_desc += " (Chemin incomplet dans la solution fournie.)"
    else:
        xml_desc = en_summary

    logger.info(
        "[path_computer] %d drawing(s), %d segment(s), instructions=%s, goal=%s",
        len(drawings), num_segments, instructions_used, reached_g,
    )
    return drawings, xml_desc, en_summary
