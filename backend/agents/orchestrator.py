"""Claude orchestrator — plans generation, evaluates quality, regenerates, assembles XML."""
import json
import base64
import logging
import time
from typing import Any

logger = logging.getLogger(__name__)

import anthropic

from core.config import get_settings
from core.agent_logger import log_prompt
from agents.mistral_agent import MistralFeedbackAgent
from agents.student_simulator import StudentSimulator
from agents.relevance_checker import RelevanceChecker
from agents.coherence_checker import CoherenceChecker
from agents.image_coherence_checker import ImageCoherenceChecker
from agents.claude_image_analyzer import ClaudeImageAnalyzer
from agents.claude_design_analyzer import ClaudeDesignAnalyzer
from feedback.gold import get_gold_examples
from prompts.feedback import build_feedback_system_prompt, build_feedback_user_prompt
from prompts.image import (
    build_annotation_plan_prompt,
    build_claude_annotation_prompt,
    build_imagen_prompt,
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


def _extract_last_json_object(text: str) -> dict:
    """Find the last top-level {...} JSON object in text, even if preceded by reasoning prose."""
    end = text.rfind("}")
    if end == -1:
        return {}
    depth = 0
    for i in range(end, -1, -1):
        if text[i] == "}":
            depth += 1
        elif text[i] == "{":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[i:end + 1])
                except json.JSONDecodeError:
                    return {}
    return {}


def _rescue_truncated_json(text: str) -> dict:
    """Close unclosed brackets in a truncated JSON string and try to parse."""
    s = text.rstrip().rstrip(',')
    open_braces = open_brackets = 0
    in_string = escape_next = False
    i = 0
    while i < len(s):
        ch = s[i]
        if escape_next:
            escape_next = False
        elif ch == '\\' and in_string:
            escape_next = True
        elif ch == '"':
            in_string = not in_string
        elif not in_string:
            if   ch == '{': open_braces   += 1
            elif ch == '}': open_braces   -= 1
            elif ch == '[': open_brackets += 1
            elif ch == ']': open_brackets -= 1
        i += 1
    if open_braces <= 0 and open_brackets <= 0:
        return {}
    s += ']' * max(0, open_brackets) + '}' * max(0, open_braces)
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        return {}


def _extract_plan_json(text: str) -> dict:
    """Extract the annotation plan (must contain 'drawings') from Claude's response.

    Handles:
    - JSON preceded by prose (looks for the { that opens the plan)
    - Truncated responses (closes unclosed brackets and rescues partial drawings)
    - Falls back to individual drawing objects if outer extraction fails
    """
    import re

    # Strategy 1: find the { that immediately precedes '"drawings"' and parse outward
    for m in re.finditer(r'"drawings"\s*:', text):
        pos = m.start()
        # Walk backwards up to 200 chars to find the opening {
        for i in range(pos - 1, max(0, pos - 200), -1):
            if text[i] == '{':
                segment = text[i:]
                # Try full parse
                try:
                    result = json.loads(segment)
                    if "drawings" in result:
                        return result
                except json.JSONDecodeError:
                    pass
                # Try rescue (truncated mid-array)
                rescued = _rescue_truncated_json(segment)
                if rescued and "drawings" in rescued:
                    logger.info("[extract_plan] rescued truncated response: %d drawings",
                                len(rescued.get("drawings", [])))
                    return rescued
                break  # Only try the nearest {

    # Strategy 2: standard last-object (may get an outer plan if not truncated)
    plan = _extract_last_json_object(text)
    if plan and "drawings" in plan:
        return plan

    return {}


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
        self._simulator = StudentSimulator()
        self._relevance = RelevanceChecker()
        self._coherence = CoherenceChecker()
        self._img_coherence = ImageCoherenceChecker()
        self._claude_analyzer  = ClaudeImageAnalyzer()
        self._design_analyzer  = ClaudeDesignAnalyzer()

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
        decomposition_hint: str | None = None,
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
            has_base_image=base_image is not None,
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
            decomposition_hint=decomposition_hint,
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
                        try:
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
                        except Exception:
                            # All image pipeline failures propagate as HTTP 500.
                            # The caller receives the real error (OpenAI, Gemini, config, etc.)
                            # rather than a misleading hint.
                            raise

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
                        platform_exercise_id=exercise_id,
                        error=error,
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
        import uuid as _uuid
        from pathlib import Path

        settings = get_settings()
        exercise = ctx.get("exercise") or {}
        exercise_type = (exercise.get("exercise_type") or (
            "robot" if exercise.get("robot_map") else ""
        )).lower()
        decomposition_hint = ctx.get("decomposition_hint") or ""

        logger.info(
            "[image_gen] exercise_id=%r exercise_type=%r robot_map=%s solutions=%d",
            ctx.get("exercise_id"),
            exercise_type,
            (f"{exercise.get('robot_map',{}).get('rows')}×{exercise.get('robot_map',{}).get('cols')}"
             if exercise.get("robot_map") else "MISSING"),
            len(exercise.get("possible_solutions") or []),
        )

        if exercise_type == "robot":
            annotated_bytes, xml_description, decomposition_summary, iterations = \
                await self._run_robot_pipeline(base_image, ctx, decomposition_hint=decomposition_hint)
        elif exercise_type == "design":
            annotated_bytes, xml_description, decomposition_summary, iterations = \
                await self._run_design_pipeline(base_image, ctx)
        else:
            logger.warning(
                "[image_gen] exercise_type=%r is not 'robot' or 'design' — "
                "annotation pipeline skipped, returning base image unchanged. "
                "Check that: (1) exercise_id is provided, (2) exercise was found in DB, "
                "(3) exercise_type column is 'Robot'/'robot' or 'Design'/'design'.",
                exercise_type or "(empty)",
            )
            annotated_bytes       = base_image
            xml_description       = ""
            decomposition_summary = ""
            iterations            = 1

        images_dir = Path(settings.generated_images_dir)
        images_dir.mkdir(parents=True, exist_ok=True)
        image_id = str(_uuid.uuid4())
        (images_dir / f"{image_id}.png").write_bytes(annotated_bytes)
        image_url = f"/feedback-generation/api/feedback/images/{image_id}"

        return json.dumps({
            "characteristic": characteristic,
            "type":           "image",
            "image_url":      image_url,
            "caption":        xml_description,
            "iterations":     iterations,
            "quality_score":  1.0,
        })

    async def _run_robot_pipeline(
        self,
        base_image: bytes,
        ctx: dict,
        decomposition_hint: str = "",
    ) -> tuple[bytes, str, str, int]:
        """Robot annotation pipeline.

        When decomposition_hint is provided (the normal case):
          1. Claude analyzes the screenshot → calibrated grid bounds
          2. Hint parser converts the text path → step dicts (no LLM, no solution code)
          3. PIL renders the drawings
          4. If rendering is pixel-identical to input, re-analyze grid bounds and retry once

        When no hint is provided (fallback):
          Same steps 1/3/4 but path is found by RobotPathAgent (tries all stored solutions,
          then Claude extended thinking if none reach the goal).

        Returns (annotated_bytes, xml_description, decomposition_summary, iterations_used).
        """
        from agents.gemini_agent import draw_annotations, images_visually_identical
        from robot.path_computer import (
            steps_to_drawings, compute_drawings, solution_to_hint,
            trace_path, goal_reached, has_for_loop,
        )
        from robot.hint_parser import parse_hint

        exercise  = ctx.get("exercise") or {}
        robot_map = exercise.get("robot_map")
        language  = ctx.get("language", "fr")

        if not robot_map:
            raise ValueError(
                f"robot_map is required for Robot exercises but is missing for "
                f"exercise_id={ctx.get('exercise_id')!r}. "
                "Check the <map>...</map> block in the exercise description."
            )

        logger.info(
            "[robot_pipeline] exercise_id=%r  grid=%d×%d  hint=%r",
            ctx.get("exercise_id"),
            robot_map.get("rows", 0),
            robot_map.get("cols", 0),
            (decomposition_hint[:80] + "…" if decomposition_hint and len(decomposition_hint) > 80
             else decomposition_hint or "(none)"),
        )

        # ── Step 1: Claude pixel calibration → grid bounds ────────────────────
        grid_bounds = await self._claude_analyzer.analyze_image(base_image, exercise)
        logger.info("[robot_pipeline] grid bounds: %s", grid_bounds)

        # ── Step 2: Path resolution ───────────────────────────────────────────
        if decomposition_hint and decomposition_hint.strip():
            # Explicit hint provided — use it directly
            hint_text = decomposition_hint.strip()
            logger.info("[robot_pipeline] using provided hint")
        else:
            # Auto-generate hint from stored solutions — prefer a solution that reaches G
            hint_text = ""
            best_partial = ""
            for idx, sol in enumerate(exercise.get("possible_solutions") or []):
                candidate = solution_to_hint(sol, robot_map)
                if not candidate:
                    logger.debug("[robot_pipeline] solution[%d] produced no hint — skipping", idx)
                    continue
                path_check = trace_path(sol, robot_map)
                if goal_reached(path_check, robot_map):
                    hint_text = candidate
                    logger.info(
                        "[robot_pipeline] solution[%d] reaches G — using as hint (%d steps)",
                        idx, len(path_check),
                    )
                    break
                if not best_partial:
                    best_partial = candidate
                    logger.warning(
                        "[robot_pipeline] solution[%d] does NOT reach G (ends at row=%d col=%d) — "
                        "keeping as fallback",
                        idx,
                        path_check[-1]["to_row"] if path_check else -1,
                        path_check[-1]["to_col"] if path_check else -1,
                    )

            if not hint_text:
                hint_text = best_partial
                if hint_text:
                    logger.warning(
                        "[robot_pipeline] no stored solution reaches G — "
                        "falling back to partial path (annotation will be incomplete)"
                    )
                else:
                    logger.warning("[robot_pipeline] no hint generated — solutions may be empty or unrecognised")

        path_steps = parse_hint(hint_text, robot_map) if hint_text else []

        if not path_steps:
            logger.error(
                "[robot_pipeline] path is empty — hint_preview=%.300s",
                hint_text or "(none)",
            )

        # Show iteration badges only when the solution uses a for loop
        solutions = exercise.get("possible_solutions") or []
        show_badges = any(has_for_loop(sol) for sol in solutions)

        # ── Step 3: Convert steps → drawing commands ──────────────────────────
        drawings, _ = steps_to_drawings(
            path_steps, grid_bounds, robot_map, show_badge_numbers=show_badges,
        )
        _, xml_desc, summary = compute_drawings(
            exercise, grid_bounds, path=path_steps, language=language,
        )

        _log_drawing_types(drawings, "[robot_pipeline] drawings")

        # ── Step 4: PIL render + pixel-diff guard (one retry with fresh bounds) ─
        rendered = draw_annotations(base_image, drawings)

        if images_visually_identical(base_image, rendered):
            logger.error(
                "[robot_pipeline] rendered image identical to input — "
                "re-analyzing grid bounds and retrying. drawings=%d  steps=%d",
                len(drawings), len(path_steps),
            )
            new_bounds = await self._claude_analyzer.analyze_image(base_image, exercise)
            if new_bounds:
                grid_bounds = new_bounds
                drawings, _ = steps_to_drawings(path_steps, grid_bounds, robot_map)
            rendered = draw_annotations(base_image, drawings)
            iteration = 2
            if images_visually_identical(base_image, rendered):
                logger.error("[robot_pipeline] still no annotations after retry — returning base image")
                return base_image, xml_desc, summary, iteration
        else:
            iteration = 1
        logger.info("[robot_pipeline] annotations drawn successfully (iteration %d)", iteration)
        return rendered, xml_desc, summary, iteration


    async def _generate_design_image_prompt(
        self,
        data_pack: str,
        n_steps: int,
    ) -> str:
        """Use Claude Opus 4.6 to craft a pixel-precise, non-overlapping image prompt.

        data_pack: output of build_design_annotation_prompt() — all pixel coords + colors.
        Returns a detailed prompt string ready for the OpenAI image generation model.
        """
        system = """\
You are an expert visual designer for AlgoPython, an educational coding platform for K12 students.

TASK
Given turtle path data with pixel coordinates, write a COMPLETE, DETAILED prompt
for OpenAI's image generation model to produce a clean decomposition annotation image.

═══ VISUAL STYLE (match AlgoPython reference images exactly) ═══
• Canvas: 1024×1024 px. Background: solid dark charcoal (#1a1a2e).
  Grid: faint purple lines (#3a2a4a, 1px) forming equal square cells.
• Start marker: solid yellow pentagon chevron (~22px), pointing in direction of first arrow.
• ARROWS — 4px thick, solid, with filled arrowhead at endpoint:
    Orange  (#F97316) — direct avancer / arc calls (approach / transition paths).
    Blue    (#3B82F6) — 1st user function call.
    Pink    (#EC4899) — 2nd user function call.
    Teal    (#14B8A6) — 3rd user function call.
  Drop shadow: 2px offset, 50% opacity black, behind every arrow.
• HEXAGONAL BADGES — per segment midpoint:
    ~14px radius hexagon. Colored fill matching the arrow. White bold number inside.
    Drop shadow: 2px offset.
• CORNER BRACKETS — for every user-function bounding box:
    White dashed ⌐¬LJ brackets, ~18px arm length, 2px thick, at the 4 corners of the bbox.
• LABEL PILLS — for every user-function step:
    White rounded-rectangle, bold dark text, e.g. "Étape 2 : triangle()".
    Placed OUTSIDE the bounding box in a clear canvas area.
• TURN INDICATORS — at every turn point:
    Small white curved arc, ~11px radius, with arrowhead at arc end.
    Clockwise or counter-clockwise as specified.
• END MARKER: small white chevron (~14px).

═══ ANTI-OVERLAP RULES (ABSOLUTE — no exceptions) ═══
1. No arrow may cross or touch another arrow except at their shared endpoint.
2. Every badge must have ≥10px of clearance from every arrow line and from every other badge.
3. Every bracket arm must have ≥8px clearance from every arrow and every badge.
4. Every label pill must be in empty canvas space — ≥12px from any arrow, badge, or bracket.
5. For each element, explicitly state its center pixel and list which nearby elements it must not touch.
6. If two elements would conflict, shift the label/badge further out until clear.

═══ OUTPUT FORMAT ═══
Write a single comprehensive prompt for OpenAI's image model.
Structure it as:

  CANVAS SETUP
  [Describe background and grid]

  ELEMENT Z-ORDER (bottom to top)
  1. Background + grid
  2. Turtle path outline (optional faint dark-red shape)
  3. Arrow lines + arrowheads (per phase, with exact pixel coordinates)
  4. Badges (hexagonal, per segment midpoint, with clearance notes)
  5. Corner brackets (per function bbox)
  6. Label pills (per function step)
  7. Turn indicators
  8. Start / end markers

  For each element: "Draw X at pixel (px,py). Do not place any other element within N px of this."

The prompt must be self-contained — the image model must reproduce the image exactly from the prompt alone.
This image is shown to 12-year-old students. Clarity and readability are paramount."""

        user = f"""\
Here is the turtle path data to visualize (canvas 1024×1024 px):

{data_pack}

Write the complete image generation prompt as described.
ALL {n_steps} steps must be visible simultaneously in ONE image.
Every arrow, badge, bracket, label, and marker must have explicit pixel coordinates.
No elements may overlap. State clearance distances explicitly for each element."""

        response = await self._client.messages.create(
            model="claude-opus-4-6",
            max_tokens=4096,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return response.content[0].text.strip()

    async def _run_design_pipeline(
        self,
        base_image: bytes,
        ctx: dict,
    ) -> tuple[bytes, str, str, int]:
        """Design exercise annotation pipeline (design-only — robot is untouched).

        1. trace_design_path()             — deterministic AST tracing (0 API calls)
        2. design_to_drawings()            — PIL drawings for xml_desc only (0 API calls)
        3. build_design_annotation_prompt  — pixel-precise data pack (0 API calls)
        4. Claude Opus 4.6                 — crafts detailed non-overlapping image prompt
        5. OpenAI gpt-image-2              — generates standalone dark canvas image
        6. check_annotation_relevance      — Gemini vision quality guard
        Raises RuntimeError (→ HTTP 500) if OpenAI returns None or relevance score < 0.30.
        No PIL fallback — failures surface as 500 with a detailed error message.

        Returns (annotated_bytes, xml_description, summary, iterations_used).
        """
        from agents.gemini_agent import (
            draw_annotations, generate_image_openai, check_annotation_relevance,
        )
        from robot.design_computer import trace_design_path, design_to_drawings, has_for_loop
        from prompts.image import build_design_annotation_prompt

        exercise  = ctx.get("exercise") or {}
        language  = ctx.get("language", "fr")
        solutions = exercise.get("possible_solutions") or []

        logger.info(
            "[design_pipeline] exercise_id=%r  solutions=%d",
            ctx.get("exercise_id"), len(solutions),
        )

        if not solutions:
            logger.warning("[design_pipeline] no solutions — returning base image")
            return base_image, "", "No solution available", 1

        solution  = solutions[0]
        segments, turn_events = trace_design_path(solution)

        if not segments:
            logger.error("[design_pipeline] trace_design_path returned no segments")
            return base_image, "", "No segments traced", 1

        show_badges = has_for_loop(solution)
        n_steps     = len({seg["step_num"] for seg in segments})

        # ── Step 1: PIL drawings (computed for xml_desc only — NOT used as fallback) ─
        canvas_bounds = await self._design_analyzer.analyze_image(base_image)
        drawings, xml_desc = design_to_drawings(
            segments, turn_events, canvas_bounds, show_badge_numbers=show_badges,
        )
        _log_drawing_types(drawings, "[design_pipeline] drawings")

        # ── Step 2: Build pixel-precise data pack ─────────────────────────────
        step_labels = _build_design_step_labels(segments, language)
        data_pack   = build_design_annotation_prompt(
            segments, turn_events, step_labels, canvas_bounds,
        )
        logger.info("[design_pipeline] data pack: %d chars, %d steps", len(data_pack), n_steps)

        # ── Step 3: Claude Opus 4.6 → detailed non-overlapping image prompt ──
        image_prompt = await self._generate_design_image_prompt(data_pack, n_steps)
        logger.info("[design_pipeline] Opus prompt: %d chars", len(image_prompt))

        # ── Step 4: OpenAI image generation ──────────────────────────────────
        ref_images = _load_design_reference_images()
        try:
            rendered = await generate_image_openai(image_prompt)
        except Exception as exc:
            raise RuntimeError(
                f"OpenAI image generation API error: {exc}  "
                f"model={self._settings.openai_image_model}"
            ) from exc
        iteration  = 1

        if rendered is None:
            raise RuntimeError(
                "Design image generation failed: OpenAI image model returned no image. "
                f"Model={self._settings.openai_image_model}  Steps={n_steps}  "
                f"Prompt length={len(image_prompt)} chars. "
                "Check OPEN_AI_API_KEY, model availability, and backend logs for the exact API error."
            )

        # ── Step 5: Relevance check ───────────────────────────────────────────
        rel = await check_annotation_relevance(rendered, None, n_steps=n_steps)
        logger.info(
            "[design_pipeline] relevance score=%.2f arrows=%s labels=%s issues=%s",
            rel["score"], rel.get("has_arrows"), rel.get("has_labels"), rel.get("issues", []),
        )
        if rel["score"] < 0.30:
            raise RuntimeError(
                f"Design image generation failed: relevance check rejected the image "
                f"(score={rel['score']:.2f}, issues={rel.get('issues', [])}). "
                f"The OpenAI model generated an image but it does not show the expected "
                f"decomposition steps. Check the image prompt sent to Opus 4.6 and the "
                f"data pack contents in the backend logs."
            )

        summary = (
            f"Design path: {len(segments)} segment(s), {len(turn_events)} turn(s), "
            f"{n_steps} step(s). Traced deterministically from solution[0]."
        )

        # ── Step 6: Gemini coherence check ───────────────────────────────────
        if ref_images:
            try:
                coh = await self._img_coherence.check(
                    rendered, summary, loops=[],
                    reference_images=ref_images,
                )
                logger.info(
                    "[design_pipeline] coherence: approved=%s score=%.2f issues=%s",
                    coh.get("approved"), coh.get("overall_score"),
                    coh.get("issues", [])[:2],
                )
            except Exception as exc:
                logger.warning("[design_pipeline] coherence check failed: %s", exc)

        logger.info("[design_pipeline] done (iteration=%d)", iteration)
        return rendered, xml_desc, summary, iteration


def _log_drawing_types(drawings: list[dict], prefix: str) -> None:
    counts: dict[str, int] = {}
    for d in drawings:
        t = d.get("type", "?")
        counts[t] = counts.get(t, 0) + 1
    if counts:
        logger.info("%s: %d total — %s", prefix, len(drawings),
                    ", ".join(f"{k}×{v}" for k, v in counts.items()))
    else:
        logger.error("%s: EMPTY", prefix)


_DIR_FR = {"right": "droite", "left": "gauche", "down": "bas", "up": "haut"}
_PRIM_FR = frozenset({"droite","gauche","haut","bas","avancer","arc",
                       "right","left","up","down"})


def _build_robot_step_labels(path_steps: list[dict], language: str = "fr") -> dict[int, str]:
    """Build step_num → label mapping from robot path steps.

    Example: step 1 has 3 right moves → "Étape 1 : droite(3)"
             step 2 has user fn 'f'   → "Étape 2 : f()"
    """
    from collections import defaultdict
    groups: dict[int, list[dict]] = defaultdict(list)
    for step in path_steps:
        groups[step["step_num"]].append(step)

    labels: dict[int, str] = {}
    for sn, group in groups.items():
        instr = group[0].get("instruction", "")
        if instr in _PRIM_FR:
            dir_name = group[0].get("direction", instr)
            fr_prim  = _DIR_FR.get(dir_name, instr)
            labels[sn] = f"Étape {sn} : {fr_prim}({len(group)})"
        else:
            labels[sn] = f"Étape {sn} : {instr}()"
    return labels


def _build_design_step_labels(segments: list[dict], language: str = "fr") -> dict[int, str]:
    """Build step_num → label mapping from design segments.

    Direct avancer calls get a plain "Étape N" label.
    User function calls get "Étape N : fname()".
    """
    labels: dict[int, str] = {}
    for seg in segments:
        sn    = seg.get("step_num")
        instr = seg.get("instruction", "")
        if sn is not None and sn not in labels:
            labels[sn] = (
                f"Étape {sn} : {instr}()"
                if instr and instr not in _PRIM_FR
                else f"Étape {sn}"
            )
    return labels


def _load_design_reference_images(max_images: int = 3) -> list[bytes]:
    """Load design exercise reference images to pass to Gemini as annotation style context.

    Prefers F_B*_DECOMPOSE.png files (full decomposition examples) over body/iteration images.
    Falls back gracefully if the directory doesn't exist or images can't be read.
    """
    from pathlib import Path
    from core.config import get_settings
    try:
        settings  = get_settings()
        ref_dir   = Path(settings.generated_images_dir).parent / "reference_images" / "design"
        # Prefer decompose examples first, then any remaining images
        preferred = sorted(ref_dir.glob("F_B*_DECOMPOSE.png"))
        others    = sorted(p for p in ref_dir.glob("*.png") if p not in set(preferred))
        candidates = preferred + others
        result: list[bytes] = []
        for path in candidates:
            if len(result) >= max_images:
                break
            try:
                result.append(path.read_bytes())
            except OSError:
                pass
        logger.info("[design_ref_images] loaded %d/%d reference image(s)", len(result), max_images)
        return result
    except Exception as exc:
        logger.warning("[design_ref_images] could not load reference images: %s", exc)
        return []
