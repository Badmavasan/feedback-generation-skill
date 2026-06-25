# Ablation & Model-Variation Study — Protocol

*Reference-free (no human annotation) evaluation of the AlgoPython multi-agent
feedback-generation pipeline. Two goals: (i) quantify the contribution of each
pipeline component, (ii) measure how sensitive the output is to the choice of
model per role (in particular, not using Claude for everything).*

---

## 1. Pipeline under test

From `ARCHITECTURE.md`, a text feedback for one requested characteristic passes
through:

| # | Component | Default model | Role |
|---|-----------|---------------|------|
| G | Text generation | Mistral Large | writes the candidate |
| Q | 6-dimension quality gate (orchestrator eval) | Claude Sonnet 4.6 | length, purity, register, scope, language, formatting |
| R | Relevance check (`check_example_relevance`) | Mistral | only for exercise-anchored examples |
| S | Student simulation (`simulate_student`) | Mistral | actionability for a K12 student |
| C | Coherence / redundancy check | Claude/Gemini | cross-characteristic |
| L | Regeneration loop | orchestrator-driven, cap `text_max_iterations` | re-invokes G with a critique on any failure |
| K | RAG grounding | MiniLM + ChromaDB | platform context + exercise solutions |

**Design principle being tested (RQ-M):** generator and judge are deliberately
disjoint model families, since LLM judges favour their own
generations [Panickssery et al. 2024].

---

## 2. Research questions

- **RQ-A (component contribution).** Removing component *X* from the full
  pipeline, how does feedback quality change on reference-free NLP metrics? Which
  components contribute most, and to which quality construct?
- **RQ-M (model sensitivity).** Replacing the model in a given role (especially
  the Claude orchestrator/judge and the Mistral generator) with alternatives,
  how much do the metrics vary? Does collapsing judge and generator into the
  **same** model (self-judge) degrade quality, as the disjoint-role principle
  predicts?

---

## 3. Literature grounding (evaluation design)

- **Reference-based semantic metrics**: BERTScore [Zhang et al., ICLR 2020] and
  ROUGE [Lin 2004] against the platform's `gold_corpus.json` (gold feedback per
  characteristic). Response-adapted references (REVISEVAL, ICLR 2025) improve
  BERTScore reliability and are an optional enhancement.
- **Reference-free NLG evaluation**: GPTScore [Fu et al. 2023] and survey
  guidance show construct-specific, prompt/rule-based scoring is viable without
  references; we operationalise the pipeline's own quality constructs as
  computable checks rather than trusting an LLM judge.
- **LLM-as-judge caveat**: judges exhibit self-preference [Panickssery et al.
  2024] and variable reliability [Gu et al. 2025]; therefore an LLM judge, if
  used at all, is **secondary triangulation only**, run with a model from a
  family disjoint from every system under test.
- **Multi-agent ablation practice**: component-omission ablations with
  complementary automatic metrics capturing distinct failure modes are standard
  (e.g. Auto-Slides 2025; multi-agent code generation 2025). We mirror this:
  one metric family per failure mode.

---

## 4. Conditions (factors)

### 4.A Ablation arm (one component removed at a time)

| ID | Condition | Implementation cost |
|----|-----------|---------------------|
| A0 | **Full pipeline** (control) | none |
| A1 | − Regeneration loop (accept first generation) | trivial: `text_max_iterations = 1` |
| A2 | − Quality gate Q | code flag `skip_quality_gate` |
| A3 | − Relevance check R | code flag `skip_relevance` |
| A4 | − Student simulation S | code flag `skip_student_sim` |
| A5 | − Coherence check C | code flag `skip_coherence` |
| A6 | − RAG grounding K (empty/minimal context) | feed empty platform context |
| A7 | **Generator only** (raw Mistral, no checks, no loop) | all flags off — lower bound |

Each ablation isolates one component; A7 is the floor and A0 the ceiling.

### 4.B Model-variation arm — 2×2 (Mistral + Claude only, text components)

Available APIs: **Mistral and Claude**. The image pipeline (Gemini/Imagen/
GPT-Image) is therefore out of scope, and the study covers **text characteristics
only** (*logos*, *technical*, *error_pointed*, *with_example_related/unrelated*).
The model arm is a clean 2×2 of generator family × judge family:

| | Judge = Claude | Judge = Mistral |
|---|---|---|
| **Gen = Mistral** | M00 control (disjoint) | M01 self-judge (Mistral-only) |
| **Gen = Claude**  | M10 disjoint (swapped) | M11 self-judge (Claude-only) |

Diagonal cells (M01, M11) use the same family to generate and judge → direct
test of the self-judge bias [Panickssery et al. 2024]; off-diagonal are disjoint.
"Judge" = quality gate Q + coherence C (the relevance and student-sim checks stay
on their default model unless also varied as a sensitivity check).

> **Feasibility note.** A1 and A6 are config-only; A2–A5 need small `skip_*` flags
> in `orchestrator.py`/`config.py`. The model arm needs two code paths: a **Claude
> generator** (for Gen=Claude) and a **Mistral judge/orchestrator** (for
> Judge=Mistral) via Mistral function-calling, since the loop is currently built on
> Claude tool-use. Recommended order: **pilot = ablation arm A0–A7 + metric harness
> first** (no adapters, validates metrics + cost), then build the two model paths
> for the 2×2 arm.

---

## 5. Stimuli (request set)

- A fixed, **stratified** set of feedback requests, identical across all
  conditions (paired design). Stratify across: the 5 characteristics × 4 levels
  (task-type / exercise / error / error-exercise) × a sample of exercises and
  error tags drawn from `config/` and the AlgoPython exercise base.
- Target **N = 60–100 requests** (≥10 per characteristic), only valid
  characteristic×level combinations.
- **R = 5 repetitions** per (condition, request) at the production temperature, to
  capture stochasticity; fix and record model versions and seeds where the API
  allows.

Total runs ≈ N × R × (|A| + |M|). Budget accordingly (see §8).

---

## 6. Metrics (all automatic; no human annotation)

Grouped by the construct they measure; each construct has ≥1 metric so failures
are triangulated.

**Reference-based (vs `gold_corpus.json`, per characteristic)**
- BERTScore-F1 (multilingual model).
- Embedding cosine similarity (max over gold items of the characteristic).
- ROUGE-L (lexical overlap, secondary).

**Characteristic fidelity / purity (rule-based)**
- *logos*: contains no code tags / no Python syntax → purity score.
- *technical*: references a mechanism, no full working expression.
- *with_example_related*: example uses exercise identifiers (Jaccard overlap with
  the reference-solution identifiers > threshold).
- *with_example_unrelated*: example does **not** use exercise identifiers.
- Cross-characteristic **redundancy**: mean pairwise embedding similarity between
  the feedback's components (lower = better).

**Safety / pedagogy**
- **Solution-leak rate**: normalised AST / high token overlap between the feedback
  code and the reference solution → fraction leaking the full correction.
- Grounding: semantic similarity of the feedback to the exercise description.

**Form / register**
- Conciseness: line/sentence count vs the ≤2-line rule (violation rate).
- Format compliance: forbidden markdown/backticks, correct code-tag usage.
- French readability index (e.g. Kandel–Moles / LIX) as a register proxy.
- Lexical diversity: distinct-n.

**Process / cost** (efficiency axis)
- Regenerations per component, tool calls, tokens, latency, $ per feedback.

**(Optional, secondary) LLM-judge triangulation**
- A rubric score from a model in a family **disjoint** from all systems under
  test, reported separately and flagged as bias-prone; never the primary outcome.

---

## 7. Statistical analysis

- **Paired design** (same request set across conditions). Aggregate the R
  repetitions to a per-request mean (or fit a mixed-effects model with request as
  a random effect).
- Per metric: **Friedman** omnibus across conditions, then post-hoc **Wilcoxon
  signed-rank** of each condition vs control (A0), **Benjamini–Hochberg**
  corrected; report **effect sizes** (Cliff's δ / rank-biserial) and 95% CIs.
- **Component contribution** = degradation of metric *m* when component *X* is
  removed: Δ = metric(A0) − metric(A_X), with CI and effect size. Rank components
  by Δ per construct.
- **Model sensitivity** = spread of each metric across model variants
  (per role); explicitly test M-single (self-judge) vs A0 (disjoint).
- Report a heatmap (condition × metric, standardized) plus per-construct bar
  plots with CIs (Plotly, consistent with the paper figures).

---

## 8. Feasibility, cost, validity

- **Implementation**: add `skip_*` flags (A2–A5); empty-context path (A6);
  `text_max_iterations` toggle (A1); a tool-use adapter for M-judge/M-single.
- **Budget**: dominated by R × N × conditions API calls; pilot with N=10, R=2 to
  estimate cost before the full grid. Cache RAG retrieval.
- **Determinism**: fix temperature, pin model versions, log everything per run.
- **Validity threats**: reference-free metrics are proxies (mitigated by
  triangulation and the gold corpus); small gold corpus; LLM-judge self-bias
  (kept secondary); stochasticity (repetitions + mixed model). State all in the
  write-up. No human eval by design — construct validity rests on metric
  triangulation, not on a single score.

---

## 9. Deliverables

- Per-condition metric tables (mean ± CI) and the ablation-contribution ranking.
- Condition × metric heatmap; per-construct bar plots; model-variation plots.
- Statistical test results (Friedman/Wilcoxon + BH, effect sizes).
- Reproducible runner script + raw per-run logs.

---

## References

- Zhang, Kishore, Wu, Weinberger, Artzi. *BERTScore: Evaluating Text Generation with BERT.* ICLR 2020.
- Lin. *ROUGE: A Package for Automatic Evaluation of Summaries.* 2004.
- Fu et al. *GPTScore: Evaluate as You Desire.* 2023 (arXiv:2302.04166).
- *REVISEVAL: Improving LLM-as-a-Judge via Response-Adapted References.* ICLR 2025.
- Panickssery, Bowman, Feng. *LLM Evaluators Recognize and Favor Their Own Generations.* NeurIPS 2024.
- Gu et al. *A Survey on LLM-as-a-Judge.* 2025.
