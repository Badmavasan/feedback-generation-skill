"""Claude orchestrator — plans generation, evaluates quality, regenerates, assembles XML."""
import json
import base64
import time
from typing import Any

import anthropic

from core.config import get_settings
from core.agent_logger import log_prompt
from agents.mistral_agent import MistralFeedbackAgent
from agents.gemini_agent import GeminiImageAgent
from agents.student_simulator import StudentSimulator
from agents.relevance_checker import RelevanceChecker
from agents.coherence_checker import CoherenceChecker
from agents.image_coherence_checker import ImageCoherenceChecker
from feedback.gold import get_gold_examples
from prompts.feedback import build_feedback_system_prompt, build_feedback_user_prompt
from prompts.image import (
    build_annotation_plan_prompt,
    build_imagen_prompt,
    load_reference_images,
)
from prompts.orchestrator import build_orchestrator_system, build_planning_prompt
from feedback.xml_builder import build_xml_output
from rag.retriever import retrieve_full_platform_context, retrieve_exercise_struct
from db.trace import TraceCollector

# ── Tools exposed to the Claude orchestrator ───────────────────────────────────

ORCHESTRATOR_TOOLS = [
    {
        "name": "generate_text_feedback",
        "description": (
            "Generate a text feedback component for a given characteristic using the Mistral agent. "
            "After receiving the result, evaluate it against all five quality dimensions before accepting. "
            "If any dimension fails, call this tool again with `regeneration_instructions` containing "
            "your precise critique. Maximum attempts per component is set in the system prompt."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "characteristic": {
                    "type": "string",
                    "enum": [
                        "logos",
                        "technical",
                        "error_pointed",
                        "with_example_unrelated_to_exercise",
                        "with_example_related_to_exercise",
                    ],
                    "description": "The feedback characteristic to generate.",
                },
                "regeneration_instructions": {
                    "type": "string",
                    "description": (
                        "Leave empty on the first attempt. "
                        "On regeneration attempts, provide a detailed critique identifying: "
                        "(1) which quality dimension(s) failed, "
                        "(2) the specific problem with a quote from the text, "
                        "(3) a concrete directive for the fix. "
                        "The feedback agent will use this verbatim to improve its output."
                    ),
                },
            },
            "required": ["characteristic"],
        },
    },
    {
        "name": "generate_image_feedback",
        "description": (
            "Generate an image feedback component (annotated screenshot). "
            "Always uses with_example_related_to_exercise — image feedback is by definition "
            "a concrete, exercise-anchored illustration. "
            "Requires a base_image to have been provided in the request. "
            "Returns a base64-encoded PNG and a caption. "
            "Apply the same quality evaluation after receiving the result. "
            "Skip simulate_student for image components."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "image_description": {
                    "type": "string",
                    "description": "Brief description of what the screenshot shows.",
                },
            },
            "required": ["image_description"],
        },
    },
    {
        "name": "check_example_relevance",
        "description": (
            "Semantically verify that a with_example_related_to_exercise component "
            "is genuinely anchored in the exercise context, not a generic Python example. "
            "Call this BEFORE simulate_student whenever the characteristic is "
            "with_example_related_to_exercise. "
            "If is_relevant=false, reject immediately with regeneration_instructions "
            "quoting the verdict and listing the missing exercise identifiers."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "feedback_content": {
                    "type": "string",
                    "description": "The full feedback text (prose + code block) to check.",
                },
            },
            "required": ["feedback_content"],
        },
    },
    {
        "name": "simulate_student",
        "description": (
            "Simulate a K12 student receiving the feedback to verify it is actionable. "
            "Call this AFTER you have approved a text component on all quality dimensions. "
            "If the student cannot identify what to do next (can_act=false), "
            "use the 'missing' field to write regeneration_instructions and call generate_text_feedback again. "
            "Do NOT call this for image components."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "characteristic": {
                    "type": "string",
                    "description": "The characteristic of the feedback component being tested.",
                },
                "feedback_text": {
                    "type": "string",
                    "description": "The exact feedback text to test with the simulated student.",
                },
            },
            "required": ["characteristic", "feedback_text"],
        },
    },
    {
        "name": "check_coherence",
        "description": (
            "Check all accepted components for point-for-point redundancy. "
            "MANDATORY before calling assemble_feedback when more than one component was generated. "
            "If passed=false, regenerate the component named in 'regenerate' using 'suggested_angle' "
            "as the regeneration_instructions, then call check_coherence again before assembling. "
            "If passed=true, proceed immediately to assemble_feedback."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "components": {
                    "type": "object",
                    "description": (
                        "Dict of characteristic → accepted feedback text for all accepted components. "
                        "Pass the plain text content of each component, not the full result object."
                    ),
                }
            },
            "required": ["components"],
        },
    },
    {
        "name": "assemble_feedback",
        "description": (
            "Assemble all approved components into the final XML output. "
            "Call this ONLY after all requested characteristics have been generated and evaluated, "
            "AND after check_coherence has returned passed=true (or only one component was generated). "
            "Include evaluation metadata for each component."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "components": {
                    "type": "object",
                    "description": (
                        "Dict of characteristic → component result. "
                        "Each value: {"
                        "  content: str (text components only), "
                        "  type: 'text'|'image', "
                        "  iterations: int, "
                        "  caption?: str (image components), "
                        "  image_url?: str (image components — server URL to the saved PNG), "
                        "  evaluation_notes?: str  (brief note on quality assessment)"
                        "}"
                    ),
                }
            },
            "required": ["components"],
        },
    },
]


class ClaudeOrchestrator:
    """
    Orchestrator powered by Claude with tool use.
    Coordinates Mistral (text) and Gemini (image) sub-agents.
    Applies a six-dimension quality gate + coherence pass on every generation.
    """

    def __init__(self) -> None:
        self._settings = get_settings()
        self._client = anthropic.AsyncAnthropic(api_key=self._settings.anthropic_api_key)
        self._mistral = MistralFeedbackAgent()
        self._gemini = GeminiImageAgent()
        self._simulator = StudentSimulator()
        self._relevance = RelevanceChecker()
        self._coherence = CoherenceChecker()
        self._img_coherence = ImageCoherenceChecker()

    async def run(
        self,
        platform_id: str,
        mode: str,
        level: str,
        language: str,
        characteristics: list[str],
        kc_name: str,
        kc_description: str,
        exercise: dict | None = None,
        error: dict | None = None,
        live_context: dict | None = None,
        base_image: bytes | None = None,
        exercise_id: str | None = None,
        exercise_context_override: str | None = None,
        platform_context_override: str | None = None,
        general_feedback_instructions: str | None = None,
        platform_config: dict | None = None,
        run_id: str | None = None,
        trace: TraceCollector | None = None,
    ) -> str:
        """
        Orchestrate full generation with quality evaluation loop.
        Returns final XML string.

        exercise_context_override: pre-formatted exercise context string from DB.
        platform_context_override: fully built platform context (DB + Chroma) from
          generator.py. When provided, the internal Chroma lookup is skipped.
        general_feedback_instructions: global instructions from GeneralConfig to
          prepend to the system prompt.
        """
        tc = trace or TraceCollector()
        settings = self._settings

        # 1. Build platform context via RAG — or use pre-built override from generator
        generation_context = {"kc_name": kc_name, "exercise_id": exercise_id}
        if platform_context_override is not None:
            platform_context = platform_context_override
        else:
            platform_context = retrieve_full_platform_context(
                platform_id,
                generation_context,
                exercise_context_override=exercise_context_override,
            )

        # 2. Build system + planning prompts
        system_prompt = build_orchestrator_system(
            platform_context=platform_context,
            language=language,
            max_image_iterations=settings.image_max_iterations,
            text_max_iterations=settings.text_max_iterations,
            general_feedback_instructions=general_feedback_instructions or "",
            platform_config=platform_config,
        )
        planning_prompt = build_planning_prompt(
            platform_id=platform_id,
            mode=mode,
            level=level,
            language=language,
            characteristics=characteristics,
            kc_name=kc_name,
            kc_description=kc_description,
            exercise=exercise,
            error=error,
            live_context=live_context,
            text_max_iterations=settings.text_max_iterations,
        )

        # 3. Resolve exercise struct from RAG only when not already resolved from DB
        #    (generator.py pre-resolves from DB when db session is available)
        if exercise is None and exercise_id is not None:
            exercise = retrieve_exercise_struct(platform_id, exercise_id)

        # Log orchestrator prompts to file
        log_prompt(run_id, "orchestrator_system", user=planning_prompt, system=system_prompt)

        # 4. Shared context passed to sub-agents
        shared_ctx = dict(
            platform_id=platform_id,
            mode=mode,
            level=level,
            language=language,
            kc_name=kc_name,
            kc_description=kc_description,
            exercise=exercise,
            exercise_id=exercise_id,
            error=error,
            live_context=live_context,
            platform_context=platform_context,
            platform_config=platform_config,
            run_id=run_id,
        )

        # Log planning step
        tc.log(
            agent="orchestrator",
            role="planning",
            input_data={
                "platform_id": platform_id,
                "mode": mode,
                "level": level,
                "language": language,
                "characteristics": characteristics,
                "kc_name": kc_name,
                "exercise_id": exercise_id,
            },
            output_data={"platform_context_length": len(platform_context)},
        )

        attempt_counts: dict[str, int] = {}
        messages = [{"role": "user", "content": planning_prompt}]
        assembled_xml: str | None = None

        while True:
            tc.start_timer("claude_turn")
            response = await self._client.messages.create(
                model=settings.orchestrator_model,
                max_tokens=8192,
                system=system_prompt,
                tools=ORCHESTRATOR_TOOLS,
                messages=messages,
            )
            claude_ms = tc.elapsed_ms("claude_turn")

            messages.append({"role": "assistant", "content": response.content})

            # Extract any reasoning text Claude emitted alongside tool calls
            claude_text = " ".join(
                block.text for block in response.content
                if hasattr(block, "text") and block.text
            ).strip()

            if response.stop_reason == "end_turn":
                if assembled_xml is None:
                    assembled_xml = claude_text or None
                tc.log(
                    agent="orchestrator",
                    role="planning",
                    verdict="completed",
                    notes=claude_text or None,
                    duration_ms=claude_ms,
                )
                break

            if response.stop_reason != "tool_use":
                break

            tool_results = []
            for block in response.content:
                if block.type != "tool_use":
                    continue

                tool_name = block.name
                tool_input = block.input
                result_content: Any = ""

                # ── generate_text_feedback ───────────────────────────────────
                if tool_name == "generate_text_feedback":
                    char = tool_input["characteristic"]
                    regen = tool_input.get("regeneration_instructions", "")

                    attempt_counts[char] = attempt_counts.get(char, 0) + 1
                    is_final_attempt = attempt_counts[char] >= settings.text_max_iterations

                    tc.start_timer(f"mistral_{char}")
                    result_content = await self._run_text_generation(
                        characteristic=char,
                        ctx=shared_ctx,
                        regeneration_instructions=regen,
                        attempt=attempt_counts[char],
                        is_final_attempt=is_final_attempt,
                        run_id=shared_ctx.get("run_id"),
                    )
                    mistral_ms = tc.elapsed_ms(f"mistral_{char}")

                    parsed_result = json.loads(result_content)

                    tc.log(
                        agent="mistral",
                        role="generation",
                        tool_name=tool_name,
                        characteristic=char,
                        attempt=attempt_counts[char],
                        verdict="regenerating" if regen else "first_attempt",
                        notes=regen or None,
                        input_data={"regeneration_instructions": regen or None},
                        output_data={"content": parsed_result.get("content", "")[:500]},
                        duration_ms=mistral_ms,
                    )

                    # GAG: attach gold examples
                    gold = get_gold_examples(char, n=2)
                    if gold:
                        parsed_result["gold_examples"] = gold
                        result_content = json.dumps(parsed_result)

                    # Log Claude's evaluation intent
                    if claude_text:
                        tc.log(
                            agent="orchestrator",
                            role="evaluation",
                            characteristic=char,
                            attempt=attempt_counts[char],
                            notes=claude_text,
                            duration_ms=claude_ms,
                        )

                # ── generate_image_feedback ──────────────────────────────────
                elif tool_name == "generate_image_feedback":
                    if base_image is None:
                        result_content = json.dumps({
                            "error": "No base_image provided — cannot generate image feedback",
                            "fallback": False,
                        })
                        tc.log(
                            agent="gemini",
                            role="image",
                            tool_name=tool_name,
                            verdict="rejected",
                            notes="No base_image provided",
                        )
                    else:
                        tc.start_timer("gemini_image")
                        result_content = await self._run_image_generation(
                            characteristic="with_example_related_to_exercise",
                            image_description=tool_input.get("image_description", "a code screenshot"),
                            base_image=base_image,
                            ctx=shared_ctx,
                        )
                        gemini_ms = tc.elapsed_ms("gemini_image")
                        img_result = json.loads(result_content)
                        tc.log(
                            agent="gemini",
                            role="image",
                            tool_name=tool_name,
                            characteristic="with_example_related_to_exercise",
                            verdict="accepted",
                            output_data={
                                "iterations": img_result.get("iterations"),
                                "quality_score": img_result.get("quality_score"),
                                "caption": img_result.get("caption"),
                            },
                            duration_ms=gemini_ms,
                        )

                # ── check_example_relevance ──────────────────────────────────
                elif tool_name == "check_example_relevance":
                    tc.start_timer("relevance")
                    rel_result = await self._relevance.check(
                        feedback_content=tool_input["feedback_content"],
                        kc_name=shared_ctx["kc_name"],
                        kc_description=shared_ctx["kc_description"],
                        exercise=shared_ctx.get("exercise"),
                        exercise_id=shared_ctx.get("exercise_id"),
                        platform_context=shared_ctx.get("platform_context", ""),
                        platform_config=shared_ctx.get("platform_config"),
                        run_id=shared_ctx.get("run_id"),
                    )
                    rel_ms = tc.elapsed_ms("relevance")
                    result_content = json.dumps(rel_result)

                    tc.log(
                        agent="claude_relevance",
                        role="relevance",
                        tool_name=tool_name,
                        verdict="passed" if rel_result.get("is_relevant") else "rejected",
                        notes=rel_result.get("verdict", ""),
                        input_data={"feedback_preview": tool_input["feedback_content"][:300]},
                        output_data=rel_result,
                        duration_ms=rel_ms,
                    )

                # ── simulate_student ─────────────────────────────────────────
                elif tool_name == "simulate_student":
                    tc.start_timer("simulator")
                    sim_result = await self._simulator.simulate(
                        feedback=tool_input["feedback_text"],
                        kc_name=shared_ctx["kc_name"],
                        kc_description=shared_ctx["kc_description"],
                        characteristic=tool_input.get("characteristic", ""),
                        exercise=shared_ctx.get("exercise"),
                        error=shared_ctx.get("error"),
                        run_id=shared_ctx.get("run_id"),
                    )
                    sim_ms = tc.elapsed_ms("simulator")
                    result_content = json.dumps(sim_result)

                    tc.log(
                        agent="mistral_simulator",
                        role="simulation",
                        tool_name=tool_name,
                        characteristic=tool_input.get("characteristic"),
                        verdict="passed" if sim_result.get("can_act") else "failed",
                        notes=sim_result.get("missing") or sim_result.get("next_step"),
                        input_data={"feedback_preview": tool_input["feedback_text"][:300]},
                        output_data=sim_result,
                        duration_ms=sim_ms,
                    )

                # ── check_coherence ──────────────────────────────────────────
                elif tool_name == "check_coherence":
                    tc.start_timer("coherence")
                    coh_result = await self._coherence.check(
                        components=tool_input["components"],
                        kc_name=shared_ctx["kc_name"],
                        kc_description=shared_ctx["kc_description"],
                        run_id=shared_ctx.get("run_id"),
                    )
                    coh_ms = tc.elapsed_ms("coherence")
                    result_content = json.dumps(coh_result)

                    tc.log(
                        agent="claude_coherence",
                        role="coherence",
                        tool_name=tool_name,
                        verdict="passed" if coh_result.get("passed") else "rejected",
                        notes=coh_result.get("summary", ""),
                        input_data={"components": list(tool_input["components"].keys())},
                        output_data=coh_result,
                        duration_ms=coh_ms,
                    )

                # ── assemble_feedback ────────────────────────────────────────
                elif tool_name == "assemble_feedback":
                    assembled_xml = build_xml_output(
                        platform_id=platform_id,
                        mode=mode,
                        level=level,
                        language=language,
                        kc_name=kc_name,
                        kc_description=kc_description,
                        components=tool_input["components"],
                    )
                    result_content = "XML assembled successfully."

                    tc.log(
                        agent="orchestrator",
                        role="assembly",
                        tool_name=tool_name,
                        verdict="completed",
                        output_data={
                            "components": list(tool_input["components"].keys()),
                            "xml_length": len(assembled_xml),
                        },
                    )

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result_content if isinstance(result_content, str)
                    else json.dumps(result_content),
                })

            messages.append({"role": "user", "content": tool_results})

        return assembled_xml or "<feedback><error>Generation failed</error></feedback>"

    async def _run_text_generation(
        self,
        characteristic: str,
        ctx: dict,
        regeneration_instructions: str = "",
        attempt: int = 1,
        is_final_attempt: bool = False,
        run_id: str | None = None,
    ) -> str:
        system = build_feedback_system_prompt(ctx["language"], ctx["platform_context"])
        user = build_feedback_user_prompt(
            characteristic=characteristic,
            kc_name=ctx["kc_name"],
            kc_description=ctx["kc_description"],
            language=ctx["language"],
            mode=ctx["mode"],
            level=ctx["level"],
            exercise=ctx.get("exercise"),
            error=ctx.get("error"),
            live_context=ctx.get("live_context"),
            platform_context=ctx["platform_context"],
            regeneration_instructions=regeneration_instructions,
        )
        content = await self._mistral.generate(
            system, user,
            run_id=run_id,
            agent_label=f"mistral:{characteristic}:attempt{attempt}",
        )
        return json.dumps({
            "characteristic": characteristic,
            "type": "text",
            "content": content,
            "attempt": attempt,
            "is_final_attempt": is_final_attempt,
        })

    async def _run_image_generation(
        self,
        characteristic: str,
        image_description: str,
        base_image: bytes,
        ctx: dict,
    ) -> str:
        import re
        import uuid as _uuid
        from pathlib import Path

        settings = get_settings()
        exercise_type = (ctx.get("exercise") or {}).get("exercise_type", "design")

        # Load reference images for few-shot style injection
        reference_images = load_reference_images(exercise_type, max_count=2)

        system, user = build_annotation_plan_prompt(
            kc_name=ctx["kc_name"],
            kc_description=ctx["kc_description"],
            characteristic=characteristic,
            language=ctx["language"],
            image_description=image_description,
            exercise=ctx.get("exercise"),
            error=ctx.get("error"),
            reference_images=reference_images or None,
        )

        plan_json = await self._gemini.generate(
            system,
            user,
            reference_images=reference_images or None,
            user_image=base_image,
        )
        try:
            plan = json.loads(plan_json)
        except json.JSONDecodeError:
            match = re.search(r'\{.*\}', plan_json, re.DOTALL)
            plan = json.loads(match.group()) if match else {
                "annotations": [], "overall_caption": "", "loops": [], "decomposition_summary": ""
            }

        annotations = plan.get("annotations", [])
        caption = plan.get("overall_caption", "")
        loops = plan.get("loops", [])
        decomposition_summary = plan.get("decomposition_summary", "")

        imagen_prompt = build_imagen_prompt(annotations, caption, decomposition_summary)
        annotated_bytes = await self._gemini.annotate_image(base_image, imagen_prompt)

        best_bytes = annotated_bytes
        best_score = 0.0
        iterations = 1

        for _ in range(settings.image_max_iterations - 1):
            verdict = await self._img_coherence.check(
                annotated_bytes=annotated_bytes,
                decomposition_summary=decomposition_summary,
                loops=loops,
            )
            score = verdict.get("quality_score", 0.0)

            if score > best_score:
                best_score = score
                best_bytes = annotated_bytes

            if verdict.get("approved", False):
                break

            issues = verdict.get("issues", [])
            refined_prompt = imagen_prompt + (
                "\n\nFix these issues from the previous attempt:\n"
                + "\n".join(f"- {iss}" for iss in issues)
            )
            annotated_bytes = await self._gemini.annotate_image(base_image, refined_prompt)
            iterations += 1

        # Save generated image to disk; return URL instead of embedding base64
        images_dir = Path(settings.generated_images_dir)
        images_dir.mkdir(parents=True, exist_ok=True)
        image_id = str(_uuid.uuid4())
        (images_dir / f"{image_id}.png").write_bytes(best_bytes)
        image_url = f"/feedback-generation/api/feedback/images/{image_id}"

        return json.dumps({
            "characteristic": characteristic,
            "type": "image",
            "image_url": image_url,
            "caption": caption,
            "iterations": iterations,
            "quality_score": best_score,
        })
