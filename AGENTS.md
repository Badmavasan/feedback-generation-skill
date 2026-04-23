# Agents — Roles, Responsibilities, and Feedback Generation Flow

## Quick reference

| Agent | Model | Role | Used by |
|---|---|---|---|
| `ClaudeOrchestrator` | claude-sonnet-4-6 | Plans, judges, directs | Entry point |
| `MistralFeedbackAgent` | mistral-large-latest | Generates feedback text | Orchestrator, RelevanceChecker, StudentSimulator |
| `GeminiImageAgent` | gemini-2.0-flash + imagen-3.0-generate-002 | Plans + paints + verifies image annotations | Orchestrator |
| `RelevanceChecker` | claude-sonnet-4-6 (direct Anthropic client) | Semantic guard: is the example actually about this exercise? | Orchestrator |
| `StudentSimulator` | mistral-large-latest (via MistralFeedbackAgent) | Actionability guard: can a K12 student act on this? | Orchestrator |

---

## Agent 1 — ClaudeOrchestrator
**File:** `agents/orchestrator.py`
**Model:** `claude-sonnet-4-6` (8 192 token output, tool use enabled)

### What it does
The orchestrator is the brain of the system. It does **not** write feedback. Its job is to plan what needs to be generated, call the right sub-agent for each component, critically evaluate every result, and assemble the final output.

It operates in a continuous tool-use loop:
1. Receives the full generation request (KC, exercise, error, characteristics list, platform context).
2. Decides the order and strategy for producing each characteristic.
3. Calls tools (`generate_text_feedback`, `check_example_relevance`, `simulate_student`, `generate_image_feedback`, `assemble_feedback`) and receives their results.
4. After each result, evaluates it against a **6-dimension quality gate**.
5. If the result passes, proceeds to the next validation step (relevance check, student simulation).
6. If it fails, writes a precise critique and calls the generation tool again.
7. Once all components pass all checks, performs a **cross-characteristic coherence pass** to eliminate redundancy across the set.
8. Calls `assemble_feedback` to produce the final XML.

### What it judges
Every `generate_text_feedback` result is evaluated on six dimensions:

1. **Pedagogical consistency** — factually correct Python, no misleading analogies
2. **Characteristic alignment** — strict boundary: logos = no code, technical = no demo, examples = no solution
3. **Content quality** — stepping stone (one nudge), concept-level idea, ≤2 lines prose, appropriate scope
4. **Format compliance** — no markdown in prose, `<code-block>` only (no triple-backtick), zero `#` in code, example prose must introduce the code not describe the concept abstractly
5. **Target audience** — K12 vocabulary, platform register
6. **Epistemics, tone, register** — explains WHY not just WHAT, "young teacher" register, no forbidden formal connectors, no slang, no empty praise

### GAG — Gold-calibrated judgment
Every tool result includes `gold_examples`: 1–2 real feedback items from the validated corpus (`gold_corpus.json`) for the same characteristic. Claude uses these as the **primary calibration anchor** — if the generated text is longer, more demonstrative, or off-register compared to gold, it rejects even if individual dimension checks pass.

### Coherence pass (multi-component requests)
After all components are individually accepted, the orchestrator reads them together and checks:
- **Redundancy**: do two components make the same point? If yes, regenerate the less specific one with instructions to cover a different angle.
- **Complementarity**: do the components together give a layered picture? Gaps are noted in `evaluation_notes`.

### Tools it can call

| Tool | What it triggers |
|---|---|
| `generate_text_feedback` | Calls `_run_text_generation` → Mistral |
| `generate_image_feedback` | Calls `_run_image_generation` → Gemini + Imagen |
| `check_example_relevance` | Calls `RelevanceChecker.check()` → Mistral semantic verification |
| `simulate_student` | Calls `StudentSimulator.simulate()` → Mistral K12 roleplay |
| `assemble_feedback` | Calls `xml_builder.build_xml_output()` → final XML |

### Hard cap
The backend independently tracks `attempt_counts[characteristic]`. If Claude somehow calls `generate_text_feedback` more than `text_max_iterations` times for the same characteristic (default: 3), the backend marks `is_final_attempt=True` and the last result is accepted regardless of quality.

---

## Agent 2 — MistralFeedbackAgent
**File:** `agents/mistral_agent.py`
**Model:** `mistral-large-latest` (temp 0.7, max 512 tokens)

### What it does
The sole text generation worker. It receives a fully constructed `(system_prompt, user_prompt)` pair and returns raw text. It has no awareness of quality gates, iteration counts, or the broader pipeline — it just generates.

It is used in three different contexts:

| Caller | Context | Temp | Max tokens |
|---|---|---|---|
| Orchestrator (`_run_text_generation`) | Generating a feedback characteristic | 0.7 | 512 |
| `RelevanceChecker.check()` | Semantic verification of an example | 0.1 | 500 |
| `StudentSimulator.simulate()` | K12 student roleplay | 0.2 | 300 |

The lower temperatures for verification and simulation are deliberate — those tasks need deterministic, analytical outputs, not creative variation.

### What it receives
The system prompt is built by `build_feedback_system_prompt()` and contains:
- Platform hard rules (2-line max, stepping-stone, no markdown, `<code-block>` tags)
- Tone register (25-year-old teacher, forbidden phrases, good openers)
- Non-typed platform rule (never introduce type names or TypeError)
- Full platform context from RAG

The user prompt is built by `build_feedback_user_prompt()` and contains:
- The specific characteristic template (logos / technical / error_pointed / with_example_*)
- KC name and description
- Exercise description + correct solutions (when available)
- Error tag and description (when applicable)
- Mode, level, live context
- Regeneration instructions (prepended as a `REGENERATION_PREFIX` block on retry attempts)

### What it returns
Raw text feedback. For `with_example_*` characteristics, this includes prose + a `<code-block>...</code-block>` tag. For others, plain prose only.

---

## Agent 3 — GeminiImageAgent
**File:** `agents/gemini_agent.py`
**Models:** `gemini-2.0-flash` (planning + verification), `imagen-3.0-generate-002` (annotation)

### What it does
Handles all image feedback. Image feedback is always `with_example_related_to_exercise` — a concrete, exercise-anchored visual annotation of a code screenshot.

It implements three distinct operations:

**`generate()` — annotation planning (Gemini 2.0 Flash)**
Receives a description of the exercise, KC, and what the screenshot shows. Returns a JSON plan:
```json
{
  "annotations": [
    {"type": "arrow", "from": [x1,y1], "to": [x2,y2], "label": "..."},
    {"type": "highlight", "region": [x,y,w,h], "color": "..."}
  ],
  "overall_caption": "La fonction vroum() reçoit ici deux arguments..."
}
```

**`annotate_image()` — image painting (Imagen 3)**
Takes the base screenshot bytes and the annotation prompt, returns an annotated PNG. Uses Imagen 3's `inpainting-insert` edit mode to overlay annotations without destroying the original content.

**`verify_image()` — quality check (Gemini 2.0 Flash, vision)**
Receives the annotated image and a verification prompt listing what the annotations should show. Returns:
```json
{
  "approved": true,
  "issues": ["arrow label too small", "highlight obscures code"],
  "quality_score": 0.87
}
```

### Iteration loop
The orchestrator runs these three operations in a loop (up to `image_max_iterations`, default 3):
1. Plan → annotate → verify
2. If not approved: take the `issues` list, append them to the annotation prompt as "Fix these issues", re-annotate
3. Track the best result (`quality_score`) across all iterations
4. Accept the best version when the loop ends

Image components skip `check_example_relevance` and `simulate_student` — the annotation plan already grounds them in the exercise context.

---

## Agent 4 — RelevanceChecker
**File:** `agents/relevance_checker.py`
**Model:** `claude-sonnet-4-6` (direct Anthropic client, temp 0.1, max 500 tokens)

### What it does
A semantic guard that runs on every `with_example_related_to_exercise` component after it passes the Claude quality gate. Its single question: **is this example actually about this exercise, or is it a generic Python snippet?**

A component can be syntactically correct, pedagogically sound, and within the characteristic boundary — and still be rejected here because it uses a random function name instead of the one from the exercise.

### Two-layer approach

**Layer 1 — Fast regex pre-check (no LLM needed)**
Before calling Mistral, the checker scans the feedback content for any pattern like `def haut(`, `def avancer(`, etc. Platform primitives (`haut`, `bas`, `gauche`, `droite`, `avancer`, `tourner`, `arc`, `lever`, `poser`, `couleur`, `print`) are never declared with `def` — they are always called directly. If found, the checker rejects immediately without an LLM call.

**Layer 2 — Mistral semantic check**
Mistral receives the exercise block (description + correct solutions), the feedback content, and the KC context. It checks:
1. What identifiers are specific to this exercise (function names, variable names, movement primitives, specific values)?
2. Which of those identifiers appear in the example?
3. Is the example consistent with the correct solution(s) — same domain, same primitives?
4. Does the example actually illustrate the KC?
5. KC-type rule — does the example respect the KC's type?
6. Could this example have been written without knowing this exercise? If yes → reject.

### KC-type detection
The checker classifies the KC before sending to Mistral, using `_is_declared_function_kc()` and `_is_native_function_kc()`:

| KC type | Detection | Rule enforced |
|---|---|---|
| Declared function | `FO.2.x`, `FO.4.2.x` in KC name, or "déclarée" in description | Example must use the declared function (e.g. `vroum()`); native primitives alone are a violation |
| Native function | `FO.4.1.x` in KC name, or "native" in description | Example must call a native primitive directly; declaring a new function with `def` is a violation |
| Conceptual/other | Everything else | No KC-type constraint; focus on concept illustration |

### What it returns
```json
{
  "is_relevant": true,
  "exercise_identifiers": ["vroum", "3", "gauche"],
  "found_in_example": ["vroum", "3"],
  "kc_illustrated": true,
  "kc_type_violation": false,
  "native_def_violation": false,
  "verdict": "The example uses vroum() and the correct step count from the exercise."
}
```

If `is_relevant=false`, the orchestrator regenerates immediately, passing the `verdict` and the `exercise_identifiers` that were missing as critique.

---

## Agent 5 — StudentSimulator
**File:** `agents/student_simulator.py`
**Model:** `mistral-large-latest` (via `MistralFeedbackAgent`, temp 0.2, max 300 tokens)

### What it does
The final gate before a text component is accepted. Mistral roleplays as a K12 student who has just read the feedback and answers honestly: can I tell what to do next?

This catches a specific failure mode that the other gates miss: feedback that is pedagogically correct, well-formatted, and exercise-relevant — but too vague or abstract for a real student to act on.

### What it receives
The simulator gets the student's full context:
- The KC name and description (what concept is being tested)
- The exercise description (what they were working on)
- The error, if any (what went wrong)
- The feedback text to evaluate

For `with_example_related_to_exercise`, an additional question is added: does the example feel connected to the exercise, or like a random Python snippet?

### What it returns
```json
{
  "can_act": true,
  "next_step": "Je vais appeler vroum() avec un argument différent pour voir ce qui change.",
  "missing": "",
  "example_feels_related": true,
  "example_relevance_note": "L'exemple utilise la même fonction que mon exercice."
}
```

The orchestrator checks two fields:
- `can_act=false` → regenerate; `missing` becomes the critique ("the student doesn't know what to change because the feedback says 'think about arguments' without pointing at where")
- `example_feels_related=false` (only for exercise-related examples) → regenerate; `example_relevance_note` becomes the critique

---

## How one feedback is generated — end to end

This walkthrough traces a single `POST /feedback/exercise` request asking for two characteristics: `logos` and `with_example_related_to_exercise`.

```
Request
───────
POST /feedback/exercise?platform_id=algopython
{
  "knowledge_component": {
    "name": "FO.4.2.1",
    "description": "Choisir la bonne valeur pour l'argument de la fonction déclarée"
  },
  "characteristics": ["logos", "with_example_related_to_exercise"],
  "exercise_id": "116"
}
```

**Step 1 — API layer** (`api/routes/feedback.py`)
- JWT is verified.
- `with_example_related_to_exercise` is confirmed compatible with level `exercise`.
- `_run_generation()` is called.

**Step 2 — Generator** (`feedback/generator.py`)
- Validates the two characteristics.
- Instantiates `ClaudeOrchestrator`.
- Calls `orchestrator.run(...)`.

**Step 3 — RAG retrieval** (`rag/retriever.py`)
- `retrieve_full_platform_context("algopython", {kc_name, exercise_id})` fires five targeted queries against ChromaDB and assembles a platform context string covering: pedagogical guidelines, tone rules, curriculum/primitives, feedback system rules, and the exercise-116 chunk.
- Since `exercise_id=116` is provided but no explicit `exercise` body, `retrieve_exercise_struct("algopython", "116")` parses the exercise chunk and returns:
  ```python
  {"description": "Fais avancer le robot de 3 cases vers la droite", "possible_solutions": ["vroum(3)"]}
  ```

**Step 4 — Orchestrator initialization**
- System prompt is built: 6-dimension quality gate + GAG instructions + language=fr + full platform context.
- Planning prompt is built: KC FO.4.2.1, exercise description + solution `vroum(3)`, two characteristics to produce.
- `shared_ctx` holds all context. `attempt_counts = {}`.

**Step 5 — Claude starts the agentic loop**
Claude reads the planning prompt and decides to generate `logos` first.

---

### Characteristic 1: `logos`

**5a — Claude calls `generate_text_feedback`**
```json
{"characteristic": "logos", "regeneration_instructions": ""}
```

**5b — Backend: `_run_text_generation`**
- Builds system prompt (platform hard rules, tone register, platform context).
- Builds user prompt from the `logos` template: "Write a purely conceptual feedback… no code, no direction, no syntax."
- Calls `MistralFeedbackAgent.generate()` (temp 0.7, max 512 tokens).
- Mistral returns, for example:
  > "Un argument, c'est ce que tu passes à une fonction pour qu'elle sache comment se comporter — c'est comme lui donner une instruction avant qu'elle démarre."
- Backend wraps in JSON, appends `gold_examples` (2 sampled logos examples from `gold_corpus.json`).

**5c — Claude evaluates on 6 dimensions**
- Dim 1: factually correct ✓
- Dim 2: no code, no direction, purely conceptual ✓
- Dim 3: one nudge, concept-level idea, ≤2 lines ✓
- Dim 4: plain prose, no markdown ✓
- Dim 5: K12 vocabulary ✓
- Dim 6: "tu" form, natural French, no forbidden phrases ✓
- GAG calibration: similar conciseness and register to gold examples ✓

→ **logos accepted.** Claude calls `simulate_student`.

**5d — Backend: `StudentSimulator.simulate()`**
Mistral receives:
- KC: FO.4.2.1, "Choisir la bonne valeur pour l'argument"
- Feedback text: the logos sentence above
- Temperature 0.2

Mistral responds:
```json
{"can_act": true, "next_step": "Je vais réfléchir à quelle valeur donner à ma fonction.", "missing": ""}
```

→ `can_act=true` → **logos definitively accepted.**

---

### Characteristic 2: `with_example_related_to_exercise`

**6a — Claude calls `generate_text_feedback`**
```json
{"characteristic": "with_example_related_to_exercise", "regeneration_instructions": ""}
```

**6b — Backend: `_run_text_generation`**
- User prompt uses the `with_example_related_to_exercise` template.
- Template includes: KC type rule (FO.4.2.1 → this is a declared function KC → example must use the declared function, here `vroum()`), exercise description, and the correct solution `vroum(3)` as reference.
- Mistral returns (example):
  > "Voici ce que ça donne si tu appelles vroum() avec des valeurs différentes :"
  > `<code-block>vroum(1)\nvroum(5)</code-block>`

**6c — Claude evaluates on 6 dimensions**
All pass, including the intro sentence check (prose introduces the code).

**6d — Claude calls `check_example_relevance`**
```json
{"feedback_content": "Voici ce que ça donne si tu appelles vroum() avec des valeurs différentes :\n<code-block>vroum(1)\nvroum(5)</code-block>"}
```

**6e — Backend: `RelevanceChecker.check()`**
- Fast path: no `def <native_prim>()` found.
- KC-type detection: `FO.4.2` in KC name → declared function KC → `_KC_TYPE_CHECK_DECLARED` template.
- Mistral (temp 0.1) checks: exercise identifiers = `["vroum", "3"]`; found in example = `["vroum"]`; KC illustrated ✓; no kc_type_violation (declared function `vroum()` is the focus) ✓.
- Returns `{"is_relevant": true, "verdict": "The example uses vroum() from the exercise."}`.

**6f — Claude calls `simulate_student`**
```json
{"characteristic": "with_example_related_to_exercise", "feedback_text": "Voici ce que ça donne..."}
```

**6g — Backend: `StudentSimulator.simulate()`**
- `is_example_related=True` → relevance question included.
- Mistral (temp 0.2) responds:
  ```json
  {
    "can_act": true,
    "next_step": "Je vais essayer d'appeler vroum() avec 3 pour avancer de 3 cases.",
    "missing": "",
    "example_feels_related": true,
    "example_relevance_note": "L'exemple utilise vroum() comme dans mon exercice."
  }
  ```
→ Both `can_act=true` and `example_feels_related=true` → **`with_example_related_to_exercise` accepted.**

---

### Coherence pass

Both components are now accepted. Claude reads them together:
- `logos`: explains what an argument is conceptually.
- `with_example_related_to_exercise`: shows `vroum()` called with two different values.

No redundancy — logos covers WHY, the example shows HOW concretely.
Complementarity: together they give the student the concept + a visual anchor in their exercise context.

→ **Coherence pass: no regeneration needed.**

---

### Assembly

**Claude calls `assemble_feedback`**
```json
{
  "components": {
    "logos": {"content": "Un argument, c'est...", "type": "text", "iterations": 1},
    "with_example_related_to_exercise": {"content": "Voici ce que...\n<code-block>...</code-block>", "type": "text", "iterations": 1}
  }
}
```

`xml_builder.build_xml_output()` produces:
```xml
<feedback>
  <metadata>
    <platform>algopython</platform>
    <mode>offline</mode>
    <level>exercise</level>
    <language>fr</language>
    <generated_at>2026-04-16T10:22:00.000Z</generated_at>
  </metadata>
  <knowledge_component>
    <name>FO.4.2.1</name>
    <description>Choisir la bonne valeur pour l'argument de la fonction déclarée</description>
  </knowledge_component>
  <components>
    <component characteristic="logos" type="text">
      <iterations>1</iterations>
      <content>Un argument, c'est ce que tu passes à une fonction pour qu'elle sache comment se comporter — c'est comme lui donner une instruction avant qu'elle démarre.</content>
    </component>
    <component characteristic="with_example_related_to_exercise" type="text">
      <iterations>1</iterations>
      <content>Voici ce que ça donne si tu appelles vroum() avec des valeurs différentes :
<code-block>vroum(1)
vroum(5)</code-block></content>
    </component>
  </components>
</feedback>
```

This XML is returned as the HTTP response (`Content-Type: application/xml`).

---

## What each Mistral call looks like in the chain

For the `with_example_related_to_exercise` characteristic above, Mistral is called **three times** — once as generator, once as relevance checker, once as student simulator. Each call uses the same model but with a completely different system prompt and temperature:

| Call | Model | Role | System prompt | Temp | Task |
|---|---|---|---|---|---|
| 1 | Mistral Large | Generator | Platform rules + tone + hard format rules | 0.7 | Write the feedback |
| 2 | Claude Sonnet 4.6 | Relevance checker | Strict pedagogical quality checker | 0.1 | Judge if example is exercise-anchored |
| 3 | Mistral Large | Student simulator | K12 student receiving feedback | 0.2 | Judge if feedback is actionable |

Claude handles the relevance check because it is the same model as the orchestrator — it applies the same strict quality standards and KC-type rules consistently, without context switching. Mistral handles generation and the student simulation, where its natural French generation quality is most valuable.
