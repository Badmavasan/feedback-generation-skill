# Robot Annotation Pipeline — Development Log

**Project:** AlgoPython feedback-generation-skill  
**Feature:** Automated robot exercise screenshot annotation  
**Period:** 2026-04-23 → 2026-04-26  
**Total generation runs logged:** 66 (across `logs/agents.log`, 30 669 lines)

---

## Context

AlgoPython robot exercises present a 2-D grid to the student. A robot starts at cell `I` and must reach cell `G` using movement primitives (`droite`, `gauche`, `haut`, `bas`) and user-defined functions. The goal was to annotate a screenshot of the student's exercise view — drawing the correct path on top of the grid image — and embed that annotated image as a feedback component.

The constraint: every LLM call costs money and adds latency. The path is *deterministic* given the correct solution and the map. The question was how much of the pipeline could be made code-only.

---

## Strategy 1 — Full LLM annotation planning (Gemini)

**Dates:** 2026-04-23 14:46 → 2026-04-24 ~01:00  
**Approach:** Gemini 2.5 Pro received the exercise map, the solution code, and the screenshot. It was asked to produce a complete JSON annotation plan (`drawings` array) in one shot — arrows, badges, colours, positions — everything decided by the model.

**What it did well:** Gemini understood the visual layout intuitively and placed arrows roughly in the right region of the image.

**Problems encountered:**

- **Coordinate hallucination.** Gemini produced fractional coordinates (image fractions 0–1) that were plausible but inconsistent — arrows would skip cells, overlap, or point in the wrong direction. The model had no reliable way to map a 7×13 grid to exact pixel fractions without ground truth.
- **Incomplete paths.** The model would annotate 4–5 steps out of 8, then stop, apparently losing track of the execution state mid-solution.
- **High cost per call.** Gemini 2.5 Pro with a 4 096-token thinking budget per annotation attempt cost roughly 2–4× a normal call. With up to 3 retry iterations, a single image feedback could trigger 3 Gemini calls.
- **Truncated JSON.** At the `max_output_tokens` limit, the `drawings` array was sometimes cut mid-element. A `_rescue_truncated_json` helper was added to close open brackets and salvage partial arrays — but the rescued drawings were still geometrically wrong.
- **`budget_tokens > max_tokens` crash.** The extended-thinking call used `budget_tokens=16 000` with `max_tokens=8 192`, causing the API to reject the call silently. Fixed to `budget_tokens=10 000`, `max_tokens=14 000`.

**Verdict:** Abandoned. Geometry is a solved problem — handing it to an LLM was the wrong tool.

---

## Strategy 2 — Claude extended-thinking path planner (RobotPathAgent)

**Dates:** 2026-04-24 ~01:00 → ~13:00  
**Approach:** A dedicated `RobotPathAgent` used Claude Sonnet with extended thinking (`budget_tokens=10 000`) to read the map + solution and produce the step-by-step path as a JSON array, which was then fed to a deterministic PIL renderer.

**What it did well:** Separated the path-finding concern from the rendering concern. PIL rendering was reliable once it received correct step dicts.

**Problems encountered:**

- **Still incomplete paths.** Claude with 10 k thinking tokens would reason correctly for 4–6 steps, then halt early. Adding more budget helped but did not eliminate the problem, and raised cost significantly.
- **Sensitive to prompt wording.** Minor prompt changes would flip between correct and incomplete outputs with no predictable pattern.
- **Granularity bug.** The agent was producing one badge per *unit move* (e.g., `haut(3)` → 3 badges) instead of one badge per *instruction call*. Fixing this required rethinking step numbering throughout.
- **Latency.** Each extended-thinking call took 15–40 seconds. The full image pipeline (grid calibration + path planning + render) was routinely 45–70 seconds.
- **Fundamental mismatch.** The LLM was being asked to simulate a deterministic state machine. That's what Python AST evaluation is for.

**Verdict:** Abandoned. Any task that is deterministic should not be delegated to a probabilistic model.

---

## Strategy 3 — Deterministic AST path tracer + PIL renderer (current)

**Dates:** 2026-04-24 ~13:00 → 2026-04-26  
**Approach:** Parse the solution code with Python's `ast` module. Walk the AST deterministically — executing `droite(n)` moves the position `n` cells right, calling a user function recurses into its body with bound parameters, a `for` loop iterates the body `range(n)` times. Every unit move appends one step dict. PIL draws the result.

**One LLM call remains:** Claude (`claude-sonnet-4-6`) analyzes the screenshot to calibrate grid bounds — returning `grid_x1`, `grid_y1`, `grid_x2`, `grid_y2` as image fractions. This is genuinely vision work (the grid may be inset, padded, or scaled differently per screenshot) and cannot be replaced by code.

**Key implementation decisions:**

| Decision | Rationale |
|---|---|
| Step counter increments once per *call site*, not per unit move | One `haut(3)` is one instruction to the student — it gets one badge number, not three |
| Badges suppressed unless `has_for_loop()` is True | Without a loop, numbers add visual clutter with no pedagogical value (there is no "iteration N" to communicate) |
| `_USER_FUNCTION_PALETTE` — ordered list of colors | Multiple user-defined functions (e.g. `f(n)` and `g(n)`) must be visually distinct; a single purple for all was ambiguous |
| Pixel-diff guard + one retry | PIL may produce an image identical to the input when grid bounds are wrong; detecting this and re-asking Claude for fresh bounds costs one extra call but avoids returning an unannotated image |
| `goal_reached()` check over all stored solutions | `correct_codes` in the AlgoPython DB can be incomplete; the pipeline tries every stored solution, picks the first that lands on `G`, and falls back to the longest partial path with a log warning |

---

## Critical bugs found and fixed

### Bug 1 — Parameterized user functions ignored argument values

**Symptom:** Exercise 115 (D-16) uses `f(n)` and `g(n)`. A call like `f(4)` was traced as `droite(1), haut(1)` instead of `droite(4), haut(1)`. The annotation showed a path covering ≈8 cells instead of 23.

**Root cause:** `_int_arg` only handled `ast.Constant` and `ast.Num` nodes. When the argument was `ast.Name` (a variable like `n`), it returned the default value `1`.

**Fix:** Added a `bindings: dict[str, int]` parameter to `_trace_block`. Each user-function call site builds a fresh frame mapping parameter names to their resolved integer values. `_int_arg` and `_range_n` resolve `ast.Name` nodes through the current bindings before falling back to the default.

```
Before: f(4) → droite(1) + haut(1)  = 2 unit moves
After:  f(4) → droite(4) + haut(1)  = 5 unit moves   ✓
```

**Detected by:** Unit test `test_exercise_115.py` — assertion `len(path) == 23` failed with 8.

---

### Bug 2 — Incomplete correct solution in AlgoPython DB (exercise 109)

**Symptom:** D-5 annotation always stopped at user position `(0,6)` — exactly halfway across the grid. The description says "tu auras besoin de l'appeler 5 fois" (call `vroum()` 5 times) but the stored solution only called it 3 times.

**Root cause:** The `correct_codes` column for exercise 109 stored an incomplete solution — `vroum()×3 + bas(3)`, missing `droite(2)`, `haut(4)`, and two more `vroum()` calls.

**Fix (two-part):**
1. Updated the AlgoPython DB directly: `correct_codes` for exercise 109 now contains the complete 8-call solution.
2. Added `goal_reached()` check in the pipeline: before using a solution to generate the annotation, the pipeline traces it and checks whether it lands on `G`. If not, it tries the next stored solution. If none reach `G`, it uses the longest partial path and logs a warning rather than crashing.

**Detected by:** Unit test `test_exercise_109.py` — `goal_reached()` returned `False` for the stored solution.

---

### Bug 3 — `else` branch accessing `None` object

**Symptom:** When an exercise was not found in the AlgoPython DB, `generator.py` attempted to build a fallback context string by accessing `algo_ex.platform_exercise_id` — but `algo_ex` was `None` in the `else` branch.

**Root cause:** Dead code written with incorrect variable reference. The else branch was for "exercise not found" but still tried to read fields from the (null) exercise object.

**Fix:** Removed the entire `else` block and the local PostgreSQL exercise table fallback. Exercise data now comes exclusively from the external AlgoPython MySQL DB.

---

## Final architecture

```
POST /feedback/image
        │
        ▼
generator.py
  ├─ AlgoPython MySQL DB  ──►  parse_robot_map_from_description()
  │   correct_codes              parse_correct_codes()
  │   description                get_exercise_task_types()
  │
  ▼
orchestrator.py  _run_robot_pipeline()
  │
  ├─ 1. ClaudeImageAnalyzer  (1 API call — vision only)
  │       └─ Returns grid_x1/y1/x2/y2 as image fractions
  │
  ├─ 2. solution_to_hint()  (pure Python, 0 API calls)
  │       └─ trace_path() via AST evaluation
  │           ├─ _collect_functions() → funcs + func_params
  │           ├─ _trace_block() with bindings frame per call
  │           │   ├─ Direct primitives: droite/gauche/haut/bas/avancer
  │           │   ├─ User functions: recurse with bound parameters
  │           │   └─ For loops: iterate range(n), n resolved via bindings
  │           └─ goal_reached() → prefer complete path over partial
  │
  ├─ 3. parse_hint()  (pure Python, 0 API calls)
  │       └─ Converts hint text → step dicts
  │
  ├─ 4. steps_to_drawings()  (pure Python, 0 API calls)
  │       ├─ One arrow per unit move
  │       ├─ One badge per step_num group (only if has_for_loop())
  │       │   └─ Badge = large circle, radius ≈ W/28, shows iteration N
  │       └─ Color map:
  │           ├─ droite/right/avancer → blue
  │           ├─ gauche/left         → pink
  │           ├─ bas/down            → orange
  │           ├─ haut/up             → green
  │           └─ user functions      → palette: purple, teal, rose, yellow, red
  │                                    (1st fn → purple, 2nd → teal, …)
  │
  └─ 5. draw_annotations()  (pure PIL, 0 API calls)
          └─ Pixel-diff guard: if output == input, re-call ClaudeImageAnalyzer and retry once
```

**API calls per image annotation: 1** (grid calibration only).  
**Latency observed in production logs:** ~4–8 seconds end-to-end for the robot pipeline step.  
**Comparison to Strategy 1:** ~3–5 Gemini calls at 15–40 s each = 45–200 s, with unreliable geometry.

---

## Data source

All exercise data (map, solution code, task types) comes from the **AlgoPython production MySQL database** (`141.95.144.3:3306/feed-prod`) via an async read-only connection (`algopython_db`). The feedback skill's local PostgreSQL database is used exclusively for:
- Feedback records and agent logs
- Knowledge component catalog
- Error catalog
- Platform config

The local `exercises` table (SQLAlchemy `Exercise` model) still exists for manual catalog management via the `/exercises` admin routes but is **never consulted during feedback generation**.

---

## Unit tests

| File | Exercise | Checks |
|---|---|---|
| `test_exercise_109.py` | D-5 (id=109) — no-param functions, incomplete DB data | Map parse, incomplete solution detection, complete solution hint, goal_reached |
| `test_exercise_115.py` | D-16 (id=115) — parameterized `f(n)`, `g(n)` | Map parse, parameter substitution (23 unit moves), goal reached, hint output, distinct colors, has_for_loop |

Both pass as of 2026-04-26.
