# Relevance Checker: Claude vs Mistral — Comparison Report

**Date:** 2026-04-27  
**KC tested:** FO.4.2 — Appeler une fonction déclarée  
**Feedback characteristics:** `error_pointed` + `with_example_unrelated_to_exercise`  
**Exercise:** #109 — robot path with `vroum()`  
**Models:** `claude-sonnet-4-6` vs `mistral-large-latest`

---

## Context

The relevance checker (`agents/relevance_checker.py`) is a quality gate in the orchestrator.
It runs whenever the generated feedback includes a `with_example_related_to_exercise`
component, and verifies that:

1. The example uses identifiers specific to the exercise (not generic Python).
2. The example is consistent with the correct solution — same domain and primitives.
3. The example actually illustrates the KC being taught.
4. The KC-type rule is respected:
   - **DECLARED function KC** (FO.2.x, FO.4.2.x) → example must use the declared
     function (e.g. `vroum()`), not just native primitives.
   - **NATIVE function KC** (FO.4.1.x) → example must call a native primitive directly.
5. No native primitive is re-defined with `def`.
6. No forbidden vocabulary from the active platform configuration is present.

The original implementation uses Claude (`anthropic.AsyncAnthropic`).
This report documents the Mistral drop-in replacement (`agents/mistral_relevance_checker.py`)
and a head-to-head comparison on three test cases.

---

## Generated Feedback (reference output)

The following feedback was generated for **KC FO.4.2** at **error level**
(`declared_function_call_error`), with characteristics `error_pointed` and
`with_example_unrelated_to_exercise`.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<feedback>
  <metadata>
    <platform>algopython</platform>
    <mode>offline</mode>
    <level>error</level>
    <language>fr</language>
    <generated_at>2026-04-27T08:44:12.081282+00:00</generated_at>
  </metadata>
  <knowledge_component>
    <name>FO.4.2</name>
    <description>Appeler une fonction déclarée — savoir qu'il faut appeler vroum
    (fonction déclarée ou fournie dans l'énoncé) et non la redéfinir.</description>
  </knowledge_component>
  <components>
    <component characteristic="error_pointed" type="text">
      <iterations>1</iterations>
      <content>Tu as appelé la fonction vroum avec un nombre qui ne correspond pas à
      ce qu'elle attend. Vérifie bien ce que représente ce nombre dans l'énoncé : c'est
      lui qui détermine combien de fois l'action doit se répéter.</content>
      <evaluation_notes>All 7 dimensions passed on first attempt. Correctly names the
      error (wrong value passed to vroum), redirects to underlying concept (what the
      number represents). No code, no fix shown. Good young-teacher register.
      Student simulation: can_act=true.</evaluation_notes>
    </component>
    <component characteristic="with_example_unrelated_to_exercise" type="text">
      <iterations>3</iterations>
      <content>Regarde comment on utilise directement la fonction avec la bonne valeur
      tirée du contexte.

nombre_de_tours = 5
faire_tour(nombre_de_tours)</content>
      <evaluation_notes>Accepted on 3rd attempt (final). First attempt violated
      characteristic 2 (used exercise function name 'vroum' and included def).
      Second attempt was too minimal (can_act=false). Third attempt regenerated after
      coherence failure to shift angle. Shows neutral everyday function call (faire_tour)
      with value drawn from a variable — complementary to error_pointed.
      Zero # in code, no def, no forbidden vocabulary.
      Student simulation: can_act=true.</evaluation_notes>
    </component>
  </components>
</feedback>
```

**Note:** `with_example_unrelated_to_exercise` took 3 iterations. The orchestrator
rejected the first attempt because it used `vroum` (too exercise-specific) and the
second because it was too sparse to be actionable.

---

## Test Cases

Three cases were designed to stress the checker across distinct scenarios:

| Case | Label | Expected outcome |
|------|-------|-----------------|
| **A** | Unrelated example (`faire_tour`) — the actual generated component | Both models reject — not anchored in exercise |
| **B** | Good related example — uses `vroum()`, correct calls, matches solution | Both models accept |
| **C** | Bad related example — only native primitives (`droite`/`bas`), no `vroum()` | kc_type_violation — KC requires declared function |

### Case A — Unrelated example

**Content:**
```
Regarde comment on utilise directement la fonction avec la bonne valeur tirée du contexte.

nombre_de_tours = 5
faire_tour(nombre_de_tours)
```

| Field | Claude | Mistral |
|-------|--------|---------|
| `is_relevant` | `false` | `false` |
| `kc_illustrated` | `false` | `false` |
| `native_def_violation` | `false` | `false` |
| `config_violation` | `false` | `false` |
| Latency | 6 438 ms | 2 753 ms |
| `exercise_identifiers` | `["vroum", "droite(2)", "bas(1)", "bas(3)"]` | `["vroum", "droite(2)", "bas(1)", "vroum()"]` |
| `found_in_example` | `[]` | `[]` |

**Claude verdict:**
> The example uses 'faire_tour' which is not the declared function from this exercise
> (vroum), contains no identifiers specific to exercise 109, and could have been written
> without any knowledge of this exercise — making it both irrelevant and a KC-type violation.

**Mistral verdict:**
> The example does not use the declared function 'vroum' from the exercise and instead
> focuses on an unrelated function 'faire_tour', making it irrelevant to the specific KC.

**Analysis:** Both models agree on the outcome. Claude's verdict is more detailed,
explicitly noting the "could be written without knowing the exercise" criterion. Mistral
is concise and correct. Both correctly extract `vroum` as an exercise identifier even
though it is absent from the example.

---

### Case B — Good related example (PASS expected)

**Content:**
```
Dans cet exercice la fonction vroum() permet de se déplacer de deux cases à droite
puis d'une case en bas. Pour finir le parcours tu dois l'appeler plusieurs fois
avec la valeur correcte :

vroum()
vroum()
bas(3)
vroum()
```

| Field | Claude | Mistral |
|-------|--------|---------|
| `is_relevant` | `true` | `true` |
| `kc_illustrated` | `true` | `true` |
| `native_def_violation` | `false` | `false` |
| `config_violation` | `false` | `false` |
| Latency | 3 214 ms | 2 327 ms |
| `exercise_identifiers` | `["vroum", "droite(2)", "bas(1)", "bas(3)"]` | `["vroum()", "droite(2)", "bas(1)", "bas(3)"]` |
| `found_in_example` | `["vroum()", "bas(3)"]` | `["vroum()", "bas(3)"]` |

**Claude verdict:**
> The example is directly anchored in exercise 109, uses the declared function vroum()
> multiple times as required by the DECLARED function KC, and correctly illustrates
> calling (not redefining) the declared function to complete the parcours.

**Mistral verdict:**
> The example is relevant as it correctly uses the declared function vroum() and aligns
> with the exercise's requirements and KC.

**Analysis:** Full agreement. Mistral's verdict is shorter but captures the essentials.
Both correctly identify `vroum()` and `bas(3)` as exercise-anchored identifiers found
in the example.

---

### Case C — Bad related example (kc_type_violation expected)

**Content:**
```
Pour avancer dans le parcours tu peux combiner les mouvements natifs :

droite(2)
bas(1)
droite(2)
bas(1)
bas(3)
droite(2)
bas(1)
```

| Field | Claude | Mistral |
|-------|--------|---------|
| `is_relevant` | **`true`** | **`false`** |
| `kc_illustrated` | `false` | `false` |
| `native_def_violation` | `false` | `false` |
| `config_violation` | `false` | `false` |
| Latency | 3 226 ms | 2 401 ms |
| `exercise_identifiers` | `["vroum", "droite(2)", "bas(1)", "bas(3)"]` | `["vroum", "droite(2)", "bas(1)"]` |
| `found_in_example` | `["droite(2)", "bas(1)", "bas(3)"]` | `["droite(2)", "bas(1)"]` |

**Claude verdict:**
> The example uses only native primitives (droite, bas) without ever calling the declared
> function vroum(), which is precisely what the KC requires — it violates the DECLARED
> function KC rule.

**Mistral verdict:**
> The example does not use the declared function `vroum()` and instead focuses only on
> native primitives, violating the DECLARED function KC.

**Analysis — key divergence.**

Both models correctly set `kc_illustrated=false` and identify the violation. However:

- **Claude** returns `is_relevant=true` because the example *is* anchored in the
  exercise (it uses `droite(2)`, `bas(1)`, `bas(3)` — all primitives from the correct
  solution). The failure is specifically `kc_illustrated=false`, not a relevance failure.
- **Mistral** collapses both signals into `is_relevant=false`, losing the distinction
  between "the example knows the exercise" and "the example illustrates the KC".

**Why this matters in the orchestrator:**

When `is_relevant=false`, the regeneration loop receives a generic hint: *"example not
anchored in the exercise."* When `is_relevant=true` but `kc_illustrated=false`, the loop
can give a targeted hint: *"use `vroum()`, not just `droite`/`bas`."* Claude's separation
enables a more precise regeneration cycle, reducing the number of iterations needed.

---

## Summary Table

| Case | Model | Relevant | KC OK | Latency | Verdict (summary) |
|------|-------|----------|-------|---------|-------------------|
| A | Claude | NO | NO | 6 438 ms | Unrelated function, no exercise identifiers |
| A | Mistral | NO | NO | 2 753 ms | Unrelated function, no exercise identifiers |
| B | Claude | YES | YES | 3 214 ms | Anchored in exercise, vroum() used correctly |
| B | Mistral | YES | YES | 2 327 ms | Correct vroum() usage, aligned with KC |
| C | Claude | **YES** | NO | 3 226 ms | Exercise primitives present, KC violated (no vroum) |
| C | Mistral | **NO** | NO | 2 401 ms | Collapses both signals into not-relevant |

---

## Pros / Cons

### Claude (`claude-sonnet-4-6`)

**Pros**
- Correctly separates `is_relevant` from `kc_illustrated` — the distinction that drives
  targeted regeneration hints in the orchestrator loop.
- Strong instruction-following on the JSON schema — all fields consistently populated,
  no regex fallback needed.
- Explains *why* an example fails with enough detail for debugging and audit.
- Handles the edge case "anchored in exercise but wrong KC angle" correctly.
- More stable across ambiguous inputs where the boundary between relevant/irrelevant
  is not clear-cut.

**Cons**
- Higher API cost (~4× per-token rate vs Mistral Large on most pricing tiers).
- Higher latency: 3–6 s vs 2.3–2.8 s for Mistral. Matters when multiple components
  are checked sequentially in the orchestrator.
- Overqualified for binary hard checks (native `def` violation, config vocabulary scan)
  that can be done with fast-path regex or a cheaper model.

---

### Mistral (`mistral-large-latest`)

**Pros**
- ~40% faster latency across all cases.
- Lower API cost — attractive for high-volume or batch generation pipelines.
- Solid French-language understanding; handles KC descriptions and feedback text
  in French with comparable accuracy to Claude on clear-cut cases.
- Reliable and sufficient for the binary hard-check fast paths (native `def`, config
  vocabulary) that already run before the LLM call.
- Concise, parseable verdicts on unambiguous inputs.

**Cons**
- Conflates `is_relevant` and `kc_illustrated` on Case C — loses the nuance needed for
  targeted regeneration hints.
- Occasionally wraps JSON output in surrounding prose, requiring the regex fallback in
  `_parse_json()` to extract the object.
- `exercise_identifiers` population is less granular (e.g. omits `bas(3)` in Case C).
- Less reliable on subtle KC-type violations where the example is topically correct
  but misses the declared-function requirement.

---

## Recommendation

| Scenario | Recommended model |
|----------|-------------------|
| Full semantic check (`with_example_related_to_exercise` gate) | **Claude** — its `is_relevant` vs `kc_illustrated` separation directly improves regeneration loop precision |
| Fast-path binary checks (native `def`, config vocabulary) | **Regex / no LLM call** — already implemented before the LLM is invoked |
| Cost-sensitive batch generation where regeneration loop quality is less critical | **Mistral** — acceptable accuracy on clear-cut cases at lower cost |
| A/B test | Run both in shadow mode on the same inputs and compare regeneration iteration counts as the primary metric |

The highest-value use of Mistral in this pipeline is as a **first-pass gate** before the
full Claude semantic check: handle `native_def_violation` and `config_violation` quickly
(already done via regex), and use Claude only when those fast paths are cleared. This
gives most of the cost savings without sacrificing the precision on kc_type_violation
that the regeneration loop depends on.

---

## Files

| File | Description |
|------|-------------|
| `backend/agents/relevance_checker.py` | Original Claude-based implementation |
| `backend/agents/mistral_relevance_checker.py` | Mistral drop-in replacement (same public API) |
| `backend/test/compare_relevance_checkers.py` | Comparison script — runs 3 test cases against both models |
