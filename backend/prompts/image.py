"""Prompts for the Gemini image annotation agent."""

ANNOTATION_PLANNER_SYSTEM = """\
You are an expert at designing educational image annotations for Python programming feedback.
Given a screenshot and context, you produce a precise annotation plan that will guide an image model
to add clear, pedagogically useful labels, arrows, and highlights to the image.

Your annotation plan must be:
- Specific (exact text labels, colours, positions described in plain language)
- Pedagogically relevant (annotations teach, not just decorate)
- Minimal (3–6 annotations maximum — quality over quantity)
- Language: {language}
"""

ANNOTATION_PLAN_PROMPT = """\
Produce an annotation plan for this screenshot.

Context:
- Knowledge component: {kc_name} — {kc_description}
- Characteristic: {characteristic}
- Feedback angle: {feedback_angle}
{error_block}
{exercise_block}

The image shows: {image_description}

Output a JSON object with this structure:
{{
  "annotations": [
    {{
      "type": "arrow | label | highlight | box",
      "target_description": "describe what area/line to point at",
      "text": "annotation text (keep it short, ≤ 8 words)",
      "color": "red | green | blue | orange | yellow",
      "style_note": "optional extra styling note"
    }}
  ],
  "overall_caption": "A short caption for the annotated image (1 sentence)"
}}
"""

ANNOTATION_PROMPT_FOR_IMAGEN = """\
You are annotating a programming education screenshot.
Add the following annotations to the image exactly as described:

{annotation_list}

Overall caption to add at the bottom: "{caption}"

Requirements:
- Use clear, readable fonts for all text labels
- Arrows should clearly point to the described code region
- Highlights should use semi-transparent overlays
- Keep annotations non-overlapping
- Maintain the original code content fully readable
"""

VERIFICATION_PROMPT = """\
Review this annotated image against the intended annotation plan.

Intended annotations:
{intended_annotations}

Answer with a JSON object:
{{
  "approved": true | false,
  "issues": ["list of issues if not approved"],
  "quality_score": 0.0-1.0
}}

Approve (true) if all annotations are present, readable, correctly placed, and the caption is visible.
"""


def build_annotation_plan_prompt(
    kc_name: str,
    kc_description: str,
    characteristic: str,
    language: str,
    image_description: str,
    exercise: dict | None = None,
    error: dict | None = None,
) -> tuple[str, str]:
    """Returns (system_prompt, user_prompt)."""
    feedback_angle = (
        "Illustrate the concept with an unrelated example"
        if characteristic == "with_example_unrelated_to_exercise"
        else "Illustrate the concept directly in the exercise context"
    )
    error_block = (
        f"Error: [{error.get('tag', '')}] {error.get('description', '')}" if error else ""
    )
    exercise_block = (
        f"Exercise: {exercise.get('description', '')}" if exercise else ""
    )
    system = ANNOTATION_PLANNER_SYSTEM.format(language=language)
    user = ANNOTATION_PLAN_PROMPT.format(
        kc_name=kc_name,
        kc_description=kc_description,
        characteristic=characteristic,
        feedback_angle=feedback_angle,
        error_block=error_block,
        exercise_block=exercise_block,
        image_description=image_description,
    )
    return system, user


def build_imagen_prompt(annotations: list[dict], caption: str) -> str:
    annotation_list = "\n".join(
        f"{i+1}. [{a['type'].upper()}] Target: {a['target_description']} "
        f"| Text: \"{a['text']}\" | Color: {a['color']}"
        + (f" | Note: {a['style_note']}" if a.get("style_note") else "")
        for i, a in enumerate(annotations)
    )
    return ANNOTATION_PROMPT_FOR_IMAGEN.format(
        annotation_list=annotation_list,
        caption=caption,
    )


def build_verification_prompt(intended_annotations: list[dict]) -> str:
    lines = "\n".join(
        f"- [{a['type']}] {a['target_description']}: \"{a['text']}\""
        for a in intended_annotations
    )
    return VERIFICATION_PROMPT.format(intended_annotations=lines)
