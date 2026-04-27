"""Deterministic turtle-graphics path computation for AlgoPython design exercises.

Supported primitives
--------------------
  avancer(n)         — move forward n units; produces one straight segment
  arc(radius, angle) — move along a circular arc (approximated as N short segments)
  tourner(deg)       — rotate by deg degrees (positive = clockwise; 0° = right)
  lever()            — pen up  (moves are silent while pen is up)
  poser()            — pen down
  couleur(name)      — change pen colour for subsequent segments

User-defined functions (def f(params): ...) are collected and executed deterministically.
Parameters are resolved through a per-call bindings frame (same mechanism as path_computer).
Any unrecognized call is logged at DEBUG level and skipped.

Coordinate system
-----------------
  Origin    : (0, 0)
  Angle 0°  : pointing right  (+x axis)
  Positive  : clockwise  (screen y-down convention)
  dx = cos(θ × π/180),  dy = sin(θ × π/180)

Arc convention (matches Python turtle adapted to clockwise-positive convention)
  arc(radius, extent):
    • |extent| degrees of arc are drawn
    • positive extent → clockwise arc
    • negative extent → counter-clockwise arc
  Approximated as ceil(|extent|/5) short straight segments (≤ 5° each).

Step numbering
--------------
  step_ctr increments once per top-level call site (avancer, arc, or user function call).
  All segments produced inside a user function call share that call's step_num.
  tourner / lever / poser / couleur do not increment step_ctr.

Return values
-------------
  trace_design_path() returns (segments, turn_events).
  segments    — list of segment dicts {x1,y1,x2,y2,instruction,step_num,pen_down,explicit_color}
  turn_events — list of turn dicts   {x,y,from_angle,to_angle,delta,step_num}
                recorded whenever tourner() is called between drawing operations.

Color scheme  (matches AlgoPython reference image style)
------------
  avancer / arc (direct)  → orange  approach / transition paths
  1st user function       → blue    Boucle 1
  2nd user function       → pink    Boucle 2
  3rd user function       → teal    Boucle 3
  4th user function       → yellow
  5th+ user function      → red (wraps)
  couleur() sets an explicit override stored per segment.
"""
from __future__ import annotations

import ast
import math
import logging

logger = logging.getLogger(__name__)

# ── Color palette ──────────────────────────────────────────────────────────────

_PRIMITIVE_COLORS: dict[str, str] = {
    "avancer": "orange",
    "arc":     "orange",
}

# Matches AlgoPython reference image style: blue=Boucle1, pink=Boucle2, teal=Boucle3 …
_USER_FUNCTION_PALETTE = ["blue", "pink", "teal", "yellow", "red"]

# Padding (fraction of canvas dimension) around the rendered drawing
_PAD = 0.10

# Segments per 5° of arc
_ARC_SEGS_PER_DEG = 1 / 5


# ── AST helpers ────────────────────────────────────────────────────────────────

def _func_name(call: ast.Call) -> str:
    if isinstance(call.func, ast.Name):
        return call.func.id
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    return ""


def _resolve_num(node: ast.expr, bindings: dict[str, float], default: float) -> float:
    if isinstance(node, ast.Constant):
        return float(node.value)
    if isinstance(node, ast.Num):
        return float(node.n)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        return -_resolve_num(node.operand, bindings, default)
    if isinstance(node, ast.Name) and node.id in bindings:
        return float(bindings[node.id])
    return default


def _float_arg(call: ast.Call, idx: int, default: float,
               bindings: dict[str, float]) -> float:
    try:
        return _resolve_num(call.args[idx], bindings, default)
    except IndexError:
        return default


def _str_arg(call: ast.Call, idx: int, default: str) -> str:
    try:
        node = call.args[idx]
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        if isinstance(node, ast.Str):
            return node.s
    except IndexError:
        pass
    return default


def _range_n(for_node: ast.For, bindings: dict[str, float]) -> int:
    iter_ = for_node.iter
    if not (isinstance(iter_, ast.Call) and iter_.args):
        return 1
    fn = (iter_.func.id if isinstance(iter_.func, ast.Name)
          else getattr(iter_.func, "attr", ""))
    if fn != "range":
        return 1
    return max(0, int(_resolve_num(iter_.args[0], bindings, 1)))


def _collect_functions(
    stmts: list[ast.stmt],
) -> tuple[dict[str, list[ast.stmt]], dict[str, list[str]]]:
    funcs:       dict[str, list[ast.stmt]] = {}
    func_params: dict[str, list[str]]      = {}
    for stmt in stmts:
        if isinstance(stmt, ast.FunctionDef):
            funcs[stmt.name]       = stmt.body
            func_params[stmt.name] = [arg.arg for arg in stmt.args.args]
    return funcs, func_params


# ── Turtle state ───────────────────────────────────────────────────────────────

class _TurtleState:
    __slots__ = ("x", "y", "angle", "pen_down", "color")

    def __init__(self) -> None:
        self.x        = 0.0
        self.y        = 0.0
        self.angle    = 0.0
        self.pen_down = True
        self.color: str | None = None


# ── Arc helper ─────────────────────────────────────────────────────────────────

def _trace_arc(
    radius: float,
    extent: float,
    state: _TurtleState,
    segments: list[dict],
    instr: str,
    step_num: int,
) -> None:
    if radius == 0 or extent == 0:
        return
    n = max(4, math.ceil(abs(extent) * _ARC_SEGS_PER_DEG))
    step_angle  = extent / n
    step_length = 2.0 * abs(radius) * math.sin(math.radians(abs(step_angle) / 2.0))

    for _ in range(n):
        state.angle += step_angle / 2.0
        rad = math.radians(state.angle)
        x2  = state.x + step_length * math.cos(rad)
        y2  = state.y + step_length * math.sin(rad)
        if state.pen_down:
            segments.append({
                "x1": state.x, "y1": state.y,
                "x2": x2,      "y2": y2,
                "instruction":    instr,
                "step_num":       step_num,
                "pen_down":       True,
                "explicit_color": state.color,
            })
        state.x, state.y = x2, y2
        state.angle += step_angle / 2.0


# ── Path tracer ────────────────────────────────────────────────────────────────

def _trace_block(
    stmts: list[ast.stmt],
    state: _TurtleState,
    segments: list[dict],
    turn_events: list[dict],
    step_ctr: list[int],
    funcs: dict[str, list[ast.stmt]],
    func_params: dict[str, list[str]],
    color_map: dict[str, str],
    current_instruction: str | None,
    bindings: dict[str, float],
    depth: int = 0,
) -> None:
    if depth > 20:
        logger.warning("[design_computer] max recursion depth — aborting")
        return

    for stmt in stmts:
        if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
            call = stmt.value
            fn   = _func_name(call)
            if not fn:
                continue

            at_top = current_instruction is None
            instr  = current_instruction or fn

            if fn == "avancer":
                dist = _float_arg(call, 0, 1.0, bindings)
                if at_top:
                    step_ctr[0] += 1
                this_step = step_ctr[0]
                rad = math.radians(state.angle)
                x2  = state.x + dist * math.cos(rad)
                y2  = state.y + dist * math.sin(rad)
                if state.pen_down and dist != 0.0:
                    segments.append({
                        "x1": state.x, "y1": state.y,
                        "x2": x2,      "y2": y2,
                        "instruction":    instr,
                        "step_num":       this_step,
                        "pen_down":       True,
                        "explicit_color": state.color,
                    })
                state.x, state.y = x2, y2

            elif fn == "arc":
                radius = _float_arg(call, 0, 1.0, bindings)
                extent = _float_arg(call, 1, 360.0, bindings)
                if at_top:
                    step_ctr[0] += 1
                _trace_arc(radius, extent, state, segments, instr, step_ctr[0])

            elif fn == "tourner":
                deg = _float_arg(call, 0, 0.0, bindings)
                if deg != 0.0:
                    turn_events.append({
                        "x":          state.x,
                        "y":          state.y,
                        "from_angle": state.angle,
                        "to_angle":   state.angle + deg,
                        "delta":      deg,
                        "step_num":   step_ctr[0],
                    })
                state.angle += deg

            elif fn == "lever":
                state.pen_down = False
            elif fn == "poser":
                state.pen_down = True

            elif fn == "couleur":
                col = _str_arg(call, 0, "")
                state.color = col.lower() if col else None

            elif fn in funcs:
                if at_top:
                    if fn not in color_map:
                        fn_idx = sum(1 for k in color_map if k not in _PRIMITIVE_COLORS)
                        color_map[fn] = _USER_FUNCTION_PALETTE[fn_idx % len(_USER_FUNCTION_PALETTE)]
                    step_ctr[0] += 1

                params = func_params.get(fn, [])
                new_bindings = {
                    param: _float_arg(call, i, 1.0, bindings)
                    for i, param in enumerate(params)
                }
                _trace_block(
                    funcs[fn], state, segments, turn_events, step_ctr,
                    funcs, func_params, color_map,
                    current_instruction=instr,
                    bindings=new_bindings,
                    depth=depth + 1,
                )
            else:
                logger.debug("[design_computer] unrecognized call %r — skipping", fn)

        elif isinstance(stmt, ast.For):
            n = _range_n(stmt, bindings)
            for _ in range(n):
                _trace_block(
                    stmt.body, state, segments, turn_events, step_ctr,
                    funcs, func_params, color_map,
                    current_instruction=current_instruction,
                    bindings=bindings,
                    depth=depth,
                )

        elif isinstance(stmt, ast.FunctionDef):
            pass

        elif isinstance(stmt, ast.If):
            _trace_block(
                stmt.body, state, segments, turn_events, step_ctr,
                funcs, func_params, color_map,
                current_instruction=current_instruction,
                bindings=bindings,
                depth=depth,
            )


def trace_design_path(
    solution_code: str,
) -> tuple[list[dict], list[dict]]:
    """Parse and execute a turtle design solution deterministically.

    Returns (segments, turn_events).

    segments:
        {x1, y1, x2, y2, instruction, step_num, pen_down, explicit_color}
        One dict per avancer / arc call while pen is down.

    turn_events:
        {x, y, from_angle, to_angle, delta, step_num}
        One dict per tourner() call that produces a non-zero rotation.
        Used by design_to_drawings() to render small arc turn-indicators.
    """
    try:
        tree = ast.parse(solution_code.strip())
    except SyntaxError as exc:
        logger.warning("[design_computer] SyntaxError: %s", exc)
        return [], []

    funcs, func_params = _collect_functions(tree.body)
    color_map: dict[str, str] = dict(_PRIMITIVE_COLORS)
    state       = _TurtleState()
    segments:    list[dict] = []
    turn_events: list[dict] = []

    _trace_block(
        tree.body, state, segments, turn_events,
        step_ctr=[0],
        funcs=funcs, func_params=func_params, color_map=color_map,
        current_instruction=None, bindings={},
    )

    logger.info(
        "[design_computer] traced %d segment(s), %d turn(s), final pos=(%.3f, %.3f), "
        "instructions=%s",
        len(segments), len(turn_events), state.x, state.y,
        sorted({s["instruction"] for s in segments}),
    )
    return segments, turn_events


def has_for_loop(solution_code: str) -> bool:
    """Return True if the solution (or any function it defines) contains a for loop."""
    try:
        tree = ast.parse(solution_code.strip())
        for node in ast.walk(tree):
            if isinstance(node, ast.For):
                return True
    except SyntaxError:
        pass
    return False


# ── Coordinate mapping + drawing generation ────────────────────────────────────

def _build_color_map(segments: list[dict]) -> dict[str, str]:
    color_map: dict[str, str] = dict(_PRIMITIVE_COLORS)
    palette_idx = 0
    for seg in segments:
        instr = seg.get("instruction", "")
        if instr and instr not in color_map:
            color_map[instr] = _USER_FUNCTION_PALETTE[palette_idx % len(_USER_FUNCTION_PALETTE)]
            palette_idx += 1
    return color_map


def design_to_drawings(
    segments: list[dict],
    turn_events: list[dict],
    canvas_bounds: dict,
    show_badge_numbers: bool = False,
) -> tuple[list[dict], str]:
    """Convert turtle segments + turn events to PIL drawing commands.

    canvas_bounds: {canvas_x1, canvas_y1, canvas_x2, canvas_y2} as image fractions.
    Segments are scaled and centered to fit within the canvas with PAD% padding.

    Drawing types produced:
      "line"      — one per segment (solid, no arrowhead)
      "turn_arc"  — one per turn event (small arc with arrowhead showing rotation direction)
      "badge"     — one per step_num group, only when show_badge_numbers=True

    Returns (drawings, xml_description).
    """
    if not segments:
        return [], ""

    # ── Bounding box of all turtle coordinates ────────────────────────────────
    all_x = [s["x1"] for s in segments] + [s["x2"] for s in segments]
    all_y = [s["y1"] for s in segments] + [s["y2"] for s in segments]
    min_x, max_x = min(all_x), max(all_x)
    min_y, max_y = min(all_y), max(all_y)

    tx_range = max_x - min_x or 1.0
    ty_range = max_y - min_y or 1.0

    # ── Canvas → image fraction mapping ──────────────────────────────────────
    cx1 = float(canvas_bounds.get("canvas_x1", 0.10))
    cy1 = float(canvas_bounds.get("canvas_y1", 0.10))
    cx2 = float(canvas_bounds.get("canvas_x2", 0.90))
    cy2 = float(canvas_bounds.get("canvas_y2", 0.90))

    cw = cx2 - cx1
    ch = cy2 - cy1

    draw_w = cw * (1.0 - 2 * _PAD)
    draw_h = ch * (1.0 - 2 * _PAD)

    scale_x = draw_w / tx_range
    scale_y = draw_h / ty_range
    scale   = min(scale_x, scale_y)

    rendered_w = tx_range * scale
    rendered_h = ty_range * scale
    x_off = cx1 + cw * _PAD + (draw_w - rendered_w) / 2
    y_off = cy1 + ch * _PAD + (draw_h - rendered_h) / 2

    def to_frac(tx: float, ty: float) -> tuple[float, float]:
        return (round(x_off + (tx - min_x) * scale, 4),
                round(y_off + (ty - min_y) * scale, 4))

    # Turn arc radius: 25% of one turtle unit in image fractions, clamped
    turn_radius = max(0.012, min(0.045, scale * 0.25))

    color_map = _build_color_map(segments)
    drawings: list[dict] = []

    # ── Line segments ─────────────────────────────────────────────────────────
    for seg in segments:
        if not seg.get("pen_down", True):
            continue
        x1, y1 = to_frac(seg["x1"], seg["y1"])
        x2, y2 = to_frac(seg["x2"], seg["y2"])
        color   = (seg.get("explicit_color")
                   or color_map.get(seg["instruction"], "blue"))
        drawings.append({
            "type":        "line",
            "x1": x1, "y1": y1,
            "x2": x2, "y2": y2,
            "color":       color,
            "instruction": seg["instruction"],
            "step_num":    seg["step_num"],
        })

    # ── Turn arc indicators ───────────────────────────────────────────────────
    for turn in turn_events:
        tx, ty = to_frac(turn["x"], turn["y"])
        # Colour: use the instruction active at the turn point
        instr = next(
            (seg["instruction"] for seg in reversed(segments)
             if seg["step_num"] == turn["step_num"]),
            "avancer",
        )
        color = color_map.get(instr, "blue")
        drawings.append({
            "type":       "turn_arc",
            "x":          tx,
            "y":          ty,
            "from_angle": turn["from_angle"],
            "to_angle":   turn["to_angle"],
            "delta":      turn["delta"],
            "radius":     turn_radius,
            "color":      color,
            "step_num":   turn["step_num"],
            "instruction": instr,
        })

    # ── Badges (optional) ─────────────────────────────────────────────────────
    if show_badge_numbers and drawings:
        step_groups: dict[int, list[dict]] = {}
        for d in drawings:
            sn = d.get("step_num")
            if sn is not None:
                step_groups.setdefault(sn, []).append(d)

        for sn, group in sorted(step_groups.items()):
            last  = group[-1]
            color = color_map.get(last.get("instruction", "avancer"), "blue")
            drawings.append({
                "type":  "badge",
                "shape": "circle",
                "large": True,
                "x":     last.get("x2", last.get("x", 0.5)),
                "y":     last.get("y2", last.get("y", 0.5)),
                "text":  str(sn),
                "color": color,
                "step_num": sn,
            })

    instructions_used = list(dict.fromkeys(seg["instruction"] for seg in segments))
    n_steps = len({seg["step_num"] for seg in segments})
    xml_desc = (
        f"Le dessin comporte {len(segments)} segment(s) en {n_steps} étape(s), "
        f"instructions : {', '.join(instructions_used)}."
    )

    logger.info(
        "[design_computer] %d drawing(s) (%d line, %d turn_arc) for %d segment(s), %d step(s)",
        len(drawings),
        sum(1 for d in drawings if d["type"] == "line"),
        sum(1 for d in drawings if d["type"] == "turn_arc"),
        len(segments), n_steps,
    )
    return drawings, xml_desc
