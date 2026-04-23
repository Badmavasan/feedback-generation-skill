# Feedback Generation Skill — Architecture

## System Overview

A multi-agent pipeline that generates formative pedagogical feedback for AlgoPython, a K12 French Python learning platform. Each feedback request produces one or more *characteristics* (e.g. conceptual explanation, worked example, error pointer) that together form a structured XML response.

**Key design principle:** Claude (Sonnet 4.6) orchestrates and judges. Mistral Large generates. Gemini/Imagen annotates images. None of these roles overlap.

---

## Architecture Diagram

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│                              CLIENT / PLATFORM                                   │
│                     POST /feedback/{kc|exercise|error|image}                     │
│           Auth: Bearer JWT (admin) · X-API-Key (platform integration)            │
└──────────────────────────────────┬───────────────────────────────────────────────┘
                                   │
                                   ▼
┌──────────────────────────────────────────────────────────────────────────────────┐
│                          FASTAPI APPLICATION LAYER                               │
│                                                                                  │
│   api/routes/feedback.py  ──  api/routes/auth.py  ──  api/routes/platforms.py   │
│                                                                                  │
│   • Validate auth (JWT / API key)          • Characteristic ↔ level validation  │
│   • Resolve language (explicit or RAG)     • Decode base64 image (if present)   │
└──────────────────────────────────┬───────────────────────────────────────────────┘
                                   │
                         ┌─────────▼──────────┐
                         │  feedback/generator │
                         │  validate + decode  │
                         └─────────┬──────────┘
                                   │
                    ┌──────────────▼─────────────────────┐
                    │       RAG RETRIEVAL                 │
                    │  rag/retriever.py                   │
                    │                                     │
                    │  retrieve_full_platform_context()   │
                    │  ├─ Pedagogical guidelines chunk    │
                    │  ├─ Tone & style chunk              │
                    │  ├─ Curriculum / primitives chunk   │
                    │  ├─ Feedback system chunk           │
                    │  └─ Exercise-specific chunk (if ID) │
                    │                                     │
                    │  retrieve_exercise_struct()         │
                    │  └─ description + solutions         │
                    │                                     │
                    │       ChromaDB (cosine, MiniLM)     │
                    └──────────────┬─────────────────────┘
                                   │  platform_context, exercise struct
                                   ▼
┌──────────────────────────────────────────────────────────────────────────────────┐
│                       CLAUDE ORCHESTRATOR (claude-sonnet-4-6)                    │
│                          agents/orchestrator.py                                  │
│                                                                                  │
│   System prompt: 6-dimension quality gate + GAG rules + language + platform ctx  │
│   Planning prompt: KC + exercise + error + characteristics to produce            │
│                                                                                  │
│   ╔══════════ AGENTIC LOOP (tool_use ↔ tool_result) ══════════╗                  │
│   ║                                                           ║                  │
│   ║  Claude decides tool call order and regeneration         ║                  │
│   ║  Backend enforces hard attempt cap (text_max_iterations) ║                  │
│   ║                                                           ║                  │
│   ╚═════════════════════════════════════════════════════════╝                  │
│                                                                                  │
│   TOOLS AVAILABLE TO CLAUDE:                                                     │
│   ┌─────────────────────────┐  ┌───────────────────────────┐                   │
│   │ generate_text_feedback  │  │  generate_image_feedback  │                   │
│   │  ↓ Mistral Large        │  │  ↓ Gemini Flash + Imagen 3│                   │
│   │  ↓ +GAG inject          │  │  Annotation plan → paint  │                   │
│   │  ↓ Claude 6-dim eval    │  │  → verify → iterate       │                   │
│   └────────────┬────────────┘  └───────────────────────────┘                   │
│                │                                                                 │
│   ┌────────────▼────────────┐  ┌───────────────────────────┐                   │
│   │  check_example_relevance│  │     simulate_student      │                   │
│   │  (only for ex-related)  │  │  (all text components)    │                   │
│   │  ↓ Mistral semantic     │  │  ↓ Mistral K12 roleplay   │                   │
│   │    verification         │  │    can_act? feels_related?│                   │
│   └─────────────────────────┘  └───────────────────────────┘                   │
│                                                                                  │
│   ┌─────────────────────────┐                                                   │
│   │    assemble_feedback    │                                                   │
│   │  ↓ xml_builder.py       │                                                   │
│   │    Final XML output     │                                                   │
│   └─────────────────────────┘                                                   │
└──────────────────────────────────┬───────────────────────────────────────────────┘
                                   │
                                   ▼
                         application/xml response


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
QUALITY VALIDATION CHAIN (text feedback — with_example_related_to_exercise)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Mistral generates
        │
        ▼
  Claude 6-dim eval ──── FAIL ──→ regenerate_with_critique ──┐
  (incl. intro sentence check)                               │
        │ PASS                                                │
        ▼                                                     │
  check_example_relevance ─ FAIL ──→ regenerate ────────────┘
  (RelevanceChecker)        │ PASS
                            ▼
                    simulate_student ─── FAIL ──→ regenerate ─┘
                    (StudentSimulator)   │ PASS
                                        ▼
                                   ACCEPTED
                                        │
                          (all components accepted)
                                        ▼
                    Cross-characteristic coherence pass
                    ├─ Redundancy check (same point in 2 components?)
                    │    └─ FAIL → regenerate less specific one
                    └─ Complementarity check (angles covered?)
                         └─ Note missing angles in evaluation_notes
                                        │
                                        ▼
                                 assemble_feedback


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MODEL ASSIGNMENT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Role                    Model                        Task
  ──────────────────────  ───────────────────────────  ─────────────────────────────
  Orchestrator / Judge    claude-sonnet-4-6             Plan, evaluate, regenerate
  Feedback Generator      mistral-large-latest          Write feedback text
  Relevance Checker       claude-sonnet-4-6             Semantic exercise anchoring
  Student Simulator       mistral-large-latest          K12 actionability check
  Image Planner           gemini-2.0-flash              Annotation plan (JSON)
  Image Verifier          gemini-2.0-flash (vision)     Quality scoring + issues
  Image Annotator         imagen-3.0-generate-002       PNG annotation
  Embedder                MiniLM-L12-v2 (multilingual)  ChromaDB vector search
```

---

## Component Reference

### 1. FastAPI Application Layer
**Files:** `api/routes/feedback.py`, `api/routes/auth.py`, `api/routes/platforms.py`, `api/deps.py`, `main.py`

The entry point. Seven HTTP endpoints handle different feedback contexts:

| Endpoint | Level | Context Required |
|---|---|---|
| `POST /feedback/kc` | task_type | KC only |
| `POST /feedback/exercise` | exercise | KC + exercise |
| `POST /feedback/error` | error / error_exercise | KC + error (+ optional exercise) |
| `POST /feedback/image` | exercise / error_exercise | KC + exercise + base64 image |
| `POST /feedback/offline` | configurable | API key auth, flexible |
| `POST /feedback/offline/admin` | configurable | JWT auth, flexible |
| `POST /feedback/live` | live | student_attempt + interaction_data |

Each endpoint validates that the requested characteristics are compatible with its level (e.g. `with_example_related_to_exercise` cannot be requested on a `/kc` endpoint). Auth is JWT for admin endpoints and `X-API-Key` for platform integrations.

---

### 2. RAG Pipeline
**Files:** `rag/retriever.py`, `rag/store.py`, `rag/embedder.py`

Retrieves platform-specific context that grounds every generation. Without RAG, the generator would have no knowledge of AlgoPython's specific primitives, tone rules, or exercise content.

**`VectorStore` (ChromaDB, cosine similarity)**
- One collection per platform: `platform_algopython`
- Chunks stored with metadata: `{section, platform_id}`
- Multi-field `where` filters use ChromaDB's `$and` operator

**`retrieve_full_platform_context()`**
Fires multiple targeted queries and assembles a single context string:
- *Pedagogical guidelines* — non-typed platform, formative philosophy
- *Tone & style* — young teacher register, forbidden phrases
- *Curriculum / primitives* — native functions list, KC taxonomy
- *Feedback system* — characteristic definitions, output format rules
- *Exercise chunk* (pinned first if `exercise_id` provided)

**`retrieve_exercise_struct()`**
When only an `exercise_id` is provided (no explicit exercise body), this function fetches the exercise's RAG chunk and parses it into `{description, possible_solutions}`. This ensures the feedback generator always has access to the correct solution(s) as reference material.

**Embedder:** `paraphrase-multilingual-MiniLM-L12-v2` — multilingual MiniLM, handles French/English. Lazy-loaded on first use.

---

### 3. Claude Orchestrator
**Files:** `agents/orchestrator.py`, `prompts/orchestrator.py`

The central intelligence of the system. Claude does not generate feedback — it **plans, evaluates, critiques, and assembles**. It operates in a tool-use agentic loop, calling sub-agents as tools and evaluating their output before accepting it.

**System prompt contains:**
- 6-dimension quality gate with hard violations per characteristic
- GAG (Ground-truth Annotated Grading) instructions — how to use gold examples as calibration
- Workflow: required tool call sequence per characteristic type
- Language and register rules

**Planning prompt contains:**
- The KC to illustrate
- Exercise context and solutions (if applicable)
- Error context (if applicable)
- The list of characteristics to produce
- Iteration budget

**Agentic loop:** Claude calls tools, receives tool results, evaluates, and either accepts the result or calls the tool again with precise regeneration instructions. The backend enforces a hard cap (`text_max_iterations`, default 3) independent of Claude's judgment.

---

### 4. Mistral Feedback Agent
**File:** `agents/mistral_agent.py`

The primary text generation worker. Uses `mistral-large-latest` with temperature 0.7 (creative enough for varied feedback, controlled enough for pedagogical coherence). Called by:
- The orchestrator (via `generate_text_feedback` tool → `_run_text_generation`)
- The `RelevanceChecker` (semantic verification)
- The `StudentSimulator` (K12 roleplay)

Each call to Mistral receives a fully constructed system + user prompt from `prompts/feedback.py`, ensuring the model always has the platform context, tone rules, and characteristic-specific instructions baked in.

---

### 5. Feedback Prompt System
**File:** `prompts/feedback.py`

Defines the prompts sent to Mistral for each characteristic. Hard rules embedded in the system prompt:
- **Max 2 lines of prose** — non-negotiable
- **Stepping-stone philosophy** — give ONE nudge, leave room for discovery
- **No markdown in prose** — plain text only
- **Code tags** — `<code-block>` for blocks, `<code-inline>` for inline references
- **Never show a full solution** — always partial, always illustrative
- **Bigger picture** — every feedback must carry a transferable concept-level idea

**Per-characteristic templates:**

| Characteristic | What it does | Hard boundaries |
|---|---|---|
| `logos` | Pure conceptual — what the concept IS, why it exists | No code, no syntax, no procedural direction of any kind |
| `technical` | Procedural direction — what mechanism to use, what to check | `<code-inline>` for name reference only; no working expressions; no `<code-block>` |
| `error_pointed` | Names the error precisely + redirects to underlying concept | No code; must name the specific error; no generic advice |
| `with_example_unrelated_to_exercise` | 1 intro sentence that **presents** the example ("Voici ce que ça donne quand...", "Regarde comment...") + `<code-block>` in a neutral context | Prose is an abstract conceptual statement not referencing the code; no `<code-block>`; `#` in code |
| `with_example_related_to_exercise` | 1 intro sentence anchored in the exercise ("Voici ce que ça donne si tu appelles vroum()...") + `<code-block>` | Same + must pass relevance check; KC-type rules apply; prose must introduce the code |

**KC-type rules** (embedded in the related-to-exercise template):
- KC about a *declared function* (`FO.2.x`, `FO.4.2.x`) → example must focus on the student-defined function (e.g. `vroum()`), not platform primitives
- KC about a *native function* (`FO.4.1.x`) → example must call a native primitive directly (`gauche(3)`, `haut(2)`), never with `def`

---

### 6. Relevance Checker
**File:** `agents/relevance_checker.py`

A Mistral-powered semantic guard that runs on every `with_example_related_to_exercise` component after it passes the Claude quality gate. Its job: verify that the example is genuinely anchored in *this specific exercise*, not a generic Python snippet that could have been written without knowing the exercise at all.

**Two-layer approach:**

1. **Fast regex pre-check** — immediately rejects any example that defines a native platform primitive with `def` (e.g. `def haut():`, `def avancer():`). These functions are always called directly, never declared.

2. **Mistral semantic check** — verifies:
   - Exercise-specific identifiers are present in the example
   - The example is consistent with the correct solution(s)
   - The example actually illustrates the KC
   - The KC-type rule is respected (declared function vs. native function)
   - No native primitive is defined with `def`

Returns: `{is_relevant, exercise_identifiers, found_in_example, kc_illustrated, kc_type_violation, native_def_violation, verdict}`

---

### 7. Student Simulator
**File:** `agents/student_simulator.py`

A Mistral agent that roleplay as a K12 student receiving the feedback. Called after the quality gate and relevance check pass. Verifies actionability from the student's perspective.

The simulator is given:
- The KC name and description
- The exercise description (if applicable)
- The error (if applicable)
- The feedback text to evaluate

It returns:
- `can_act` — can the student identify what to do next?
- `next_step` — what would the student actually try?
- `missing` — what is still unclear or blocking?
- `example_feels_related` — (for exercise-related examples only) does the example feel connected to this exercise?
- `example_relevance_note` — explanation if example felt unrelated

If `can_act = false` or `example_feels_related = false`, Claude uses the `missing` / `example_relevance_note` to write precise regeneration instructions.

---

### 8. GAG — Ground-Truth Annotated Grading
**Files:** `feedback/gold.py`, `feedback/gold_corpus.json`

Every `generate_text_feedback` tool result includes 2 randomly sampled gold examples for the same characteristic, injected into the tool result JSON as `gold_examples`. Claude is instructed to treat these as **primary calibration anchors**, not optional suggestions.

Gold examples calibrate Claude's judgment on four axes:
- **Length/density** — is the generated feedback as concise as gold?
- **Characteristic purity** — does it stay within the characteristic's defined boundaries?
- **Register** — does it match the pedagogical tone without chattiness?
- **Scope** — is the nudge granularity comparable to gold?

The corpus is loaded from `gold_corpus.json` (seeded from `existing_feedback_components.json`). Stubs shorter than 15 characters are filtered out at sampling time.

---

### 9. Gemini Image Agent
**Files:** `agents/gemini_agent.py`, `prompts/image.py`

Handles the `generate_image_feedback` tool. Image feedback is *always* `with_example_related_to_exercise` — a concrete, exercise-anchored visual. Requires a `base_image` (base64-encoded screenshot of the student's code or output).

**Three-step pipeline:**

1. **Annotation planning** (Gemini 2.0 Flash) — given the KC, exercise, and image description, produces a JSON plan: where to place annotations, what text to add, what to highlight.

2. **Image annotation** (Imagen 3) — applies the annotation plan to the base image, producing an annotated PNG.

3. **Verification loop** (Gemini 2.0 Flash, vision) — evaluates the annotated image for quality (`quality_score`, `approved`, `issues`). If not approved, refines the annotation prompt with the identified issues and retries. Tracks the best version across all iterations (`image_max_iterations`, default 3).

---

### 10. XML Builder
**File:** `feedback/xml_builder.py`

Assembles all accepted components into the final structured XML response. Called via the `assemble_feedback` tool once Claude has accepted all requested characteristics.

Output structure:
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
    <description>Choisir l'argument de la fonction déclarée</description>
  </knowledge_component>
  <components>
    <component characteristic="logos" type="text">
      <iterations>1</iterations>
      <content>Un argument permet à une fonction de recevoir...</content>
    </component>
    <component characteristic="with_example_related_to_exercise" type="image">
      <iterations>2</iterations>
      <image_data>iVBORw0KGgo...</image_data>
      <caption>La fonction vroum() reçoit un nombre de pas...</caption>
      <quality_score>0.91</quality_score>
    </component>
  </components>
</feedback>
```

Each component includes `iterations` — the number of generation attempts needed — which provides a quality signal for monitoring and corpus curation.

---

## Data Flow Summary

```
POST /feedback/exercise
  │
  ├─ Auth + characteristic validation
  │
  ├─ RAG: retrieve platform context + exercise struct
  │    (description, possible_solutions from ChromaDB)
  │
  ├─ Claude receives: KC + exercise + solutions + platform_context
  │    + characteristics to produce + quality gate in system prompt
  │
  └─ For each characteristic (Claude decides order):
       │
       ├─ generate_text_feedback
       │    ├─ Mistral generates (system + characteristic-specific prompt)
       │    ├─ GAG: 2 gold examples appended to tool result
       │    └─ Claude evaluates on 6 dimensions
       │         ├─ FAIL → regenerate with precise critique (up to N times)
       │         └─ PASS → continue
       │
       ├─ [if with_example_related_to_exercise]
       │    check_example_relevance
       │    ├─ Fast path: native def regex check
       │    ├─ Mistral: exercise identifier + KC-type semantic check
       │    └─ FAIL → regenerate   PASS → continue
       │
       ├─ simulate_student
       │    ├─ Mistral plays K12 student
       │    └─ can_act=false → regenerate   PASS → accepted
       │
       └─ assemble_feedback → XML → HTTP response
```

---

## File Map

```
backend/
├── main.py                          FastAPI app setup, CORS, routes
├── core/
│   ├── config.py                    Pydantic settings (API keys, model names, limits)
│   └── security.py                  JWT creation and verification
├── api/
│   ├── deps.py                      Auth dependency injection
│   └── routes/
│       ├── feedback.py              7 feedback endpoints
│       ├── auth.py                  Admin login
│       └── platforms.py             Platform registry + context seeding
├── agents/
│   ├── base.py                      Abstract agent interface
│   ├── orchestrator.py              Claude orchestrator + tool dispatch
│   ├── mistral_agent.py             Mistral Large text generation
│   ├── gemini_agent.py              Gemini Flash + Imagen 3 image pipeline
│   ├── student_simulator.py         K12 student actionability simulation
│   └── relevance_checker.py         Exercise-anchoring semantic verification
├── prompts/
│   ├── orchestrator.py              Orchestrator system + planning prompts
│   ├── feedback.py                  Mistral per-characteristic prompts + hard rules
│   └── image.py                     Gemini annotation + verification prompts
├── feedback/
│   ├── generator.py                 Entry point: validate + decode + call orchestrator
│   ├── characteristics.py           Characteristic enum + level compatibility rules
│   ├── gold.py                      GAG gold example loader + sampler
│   ├── gold_corpus.json             Curated gold feedback examples per characteristic
│   └── xml_builder.py              Final XML assembly
├── rag/
│   ├── retriever.py                 Platform context + exercise struct retrieval
│   ├── store.py                     ChromaDB VectorStore wrapper
│   └── embedder.py                  Lazy SentenceTransformer loader
├── platforms/
│   ├── models.py                    Platform + PlatformContextChunk data models
│   └── manager.py                   Platform registry + language resolution
├── data/
│   ├── seeds/
│   │   └── algopython_seed.json     AlgoPython platform context chunks
│   └── chroma/                      ChromaDB persistent storage
└── scripts/
    └── seed_algopython.py           CLI to seed/re-seed AlgoPython context
```
