"""
Semantic relevance checker — Mistral variant.

Same checks as RelevanceChecker (Claude) but calls mistral-large instead.
Drop-in replacement: identical public API, same JSON schema returned.

Checks:
1. The example uses identifiers/primitives specific to this exercise (not generic Python).
2. The example is consistent with the correct solution(s) — same domain, same primitives.
3. The example actually illustrates the KC, not some unrelated concept.
4. Native platform primitives (haut, bas, gauche, droite, avancer, tourner, arc,
   lever, poser, couleur, print) are used as direct calls, never defined with def.
"""
import json
import re
from core.config import get_settings
from core.agent_logger import log_prompt

_NATIVE_PRIMITIVES = (
    "haut", "bas", "gauche", "droite", "avancer",
    "tourner", "arc", "lever", "poser", "couleur", "print",
)


def _is_declared_function_kc(kc_name: str, kc_description: str) -> bool:
    name_upper = kc_name.upper()
    desc_lower = kc_description.lower()
    return (
        "FO.2" in name_upper
        or "FO.4.2" in name_upper
        or "déclarée" in desc_lower
        or "declared function" in desc_lower
    )


def _is_native_function_kc(kc_name: str, kc_description: str) -> bool:
    name_upper = kc_name.upper()
    desc_lower = kc_description.lower()
    return (
        "FO.4.1" in name_upper
        or "native" in desc_lower
        or "fonction native" in desc_lower
    )


_SYSTEM = """\
You are a strict pedagogical quality checker for a K12 Python programming platform.

Platform rule — native primitives: haut(), bas(), gauche(), droite(), avancer(), \
tourner(), arc(), lever(), poser(), couleur(), print() are predefined platform functions. \
They are ALWAYS called directly (e.g. haut(2), gauche(3)). \
They are NEVER defined with def. Any example that writes def haut(): or def avancer(): \
is wrong and must be rejected.

KC-type rule (you will be told which applies):
- KC about DECLARED function → the example must use the declared function from the exercise \
  (e.g. vroum()). Using only native primitives as the focus is a violation.
- KC about NATIVE function → the example must use a native primitive call directly. \
  Defining a new function with def is a violation.

Your job: verify that a generated feedback example is
  (a) genuinely anchored in the specific exercise — not a generic Python snippet,
  (b) consistent with the correct solution in terms of domain and primitives used,
  (c) actually illustrating the knowledge component requested,
  (d) respecting the KC-type rule above,
  (e) not defining a native primitive with def,
  (f) not containing any word or expression listed as forbidden in the active platform configuration.

Answer in JSON only. No prose outside the JSON object.

JSON schema:
{
  "is_relevant": true | false,
  "exercise_identifiers": ["<key identifiers specific to this exercise>"],
  "found_in_example": ["<which identifiers are present in the example>"],
  "kc_illustrated": true | false,
  "kc_type_violation": true | false,
  "native_def_violation": true | false,
  "config_violation": true | false,
  "config_violation_detail": "<which forbidden term was found, or empty string>",
  "verdict": "<one sentence: why relevant or not relevant>"
}
"""

_USER_TEMPLATE = """\
## Knowledge component
Name: {kc_name}
Description: {kc_description}
KC type: {kc_type}

## Exercise context
{exercise_block}

## Generated example (with_example_related_to_exercise)
{feedback_content}

{config_block}\
## Checks to perform
1. Extract identifiers specific to this exercise (declared function names, variables, \
movement primitives, specific values). Check which ones appear in the example.
2. Is the example consistent with the correct solution(s) — same domain, same primitives?
3. Does the example actually demonstrate the KC described above?
4. KC-type check:
{kc_type_check}
5. Does the example define any native primitive with def (e.g. def haut(), def avancer())? \
If yes → native_def_violation = true.
6. Could this example have been written without knowing this specific exercise? \
If yes → is_relevant = false.
7. Platform configuration check: if forbidden vocabulary is listed above, scan the example \
for any of those terms. If found → config_violation = true, set config_violation_detail \
to the exact term found.
"""

_KC_TYPE_CHECK_DECLARED = """\
   KC is about a DECLARED function. The example must use the declared function from the \
exercise (check the correct solution to find its name, e.g. vroum()). \
If the example focuses only on native primitives (haut, gauche, etc.) without using \
the declared function → kc_type_violation = true."""

_KC_TYPE_CHECK_NATIVE = """\
   KC is about a NATIVE function. The example must call a native primitive directly \
(haut(n), gauche(n), avancer(n), etc.). If the example declares a new function with def \
instead of calling a native primitive → kc_type_violation = true."""

_KC_TYPE_CHECK_OTHER = """\
   KC is conceptual or about another aspect. No specific KC-type constraint. \
kc_type_violation = false unless the example is clearly off-topic."""


def _parse_json(raw: str) -> dict:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
    return {}


def _native_def_in_content(content: str) -> bool:
    for prim in _NATIVE_PRIMITIVES:
        if re.search(rf'\bdef\s+{prim}\s*\(', content):
            return True
    return False


class MistralRelevanceChecker:
    def __init__(self) -> None:
        self._client = None  # lazy-init
        self._model: str | None = None

    def _get_client(self):
        if self._client is None:
            from mistralai.client import Mistral
            settings = get_settings()
            self._client = Mistral(api_key=settings.mistral_api_key)
            self._model = settings.mistral_model
        return self._client

    async def check(
        self,
        feedback_content: str,
        kc_name: str,
        kc_description: str,
        exercise: dict | None,
        exercise_id: str | None,
        platform_context: str,
        platform_config: dict | None = None,
        run_id: str | None = None,
    ) -> dict:
        """
        Verify that feedback_content is semantically anchored in the exercise and KC.
        Drop-in replacement for RelevanceChecker.check() — same return schema.
        """
        if _native_def_in_content(feedback_content):
            return {
                "is_relevant": False,
                "exercise_identifiers": [],
                "found_in_example": [],
                "kc_illustrated": False,
                "native_def_violation": True,
                "config_violation": False,
                "config_violation_detail": "",
                "verdict": (
                    "The example defines a native platform primitive with def. "
                    "Native functions (haut, bas, gauche, droite, avancer, tourner, "
                    "arc, lever, poser, couleur) must be called directly, never defined."
                ),
            }

        if platform_config:
            vta = (platform_config.get("vocabulary_to_avoid") or "").strip()
            if vta:
                content_lower = feedback_content.lower()
                for term in (t.strip() for t in vta.replace(",", "\n").splitlines() if t.strip()):
                    if term.lower() in content_lower:
                        return {
                            "is_relevant": False,
                            "exercise_identifiers": [],
                            "found_in_example": [],
                            "kc_illustrated": False,
                            "native_def_violation": False,
                            "config_violation": True,
                            "config_violation_detail": term,
                            "verdict": f"Forbidden vocabulary from platform configuration: '{term}'",
                        }

        exercise_block = _build_exercise_block(exercise, exercise_id, platform_context)
        if not exercise_block.strip():
            return {
                "is_relevant": False,
                "exercise_identifiers": [],
                "found_in_example": [],
                "kc_illustrated": False,
                "native_def_violation": False,
                "config_violation": False,
                "config_violation_detail": "",
                "verdict": "No exercise context available — cannot verify relevance.",
            }

        if _is_declared_function_kc(kc_name, kc_description):
            kc_type = "DECLARED function KC"
            kc_type_check = _KC_TYPE_CHECK_DECLARED
        elif _is_native_function_kc(kc_name, kc_description):
            kc_type = "NATIVE function KC"
            kc_type_check = _KC_TYPE_CHECK_NATIVE
        else:
            kc_type = "conceptual/other KC"
            kc_type_check = _KC_TYPE_CHECK_OTHER

        config_block = _build_config_block(platform_config)

        user = _USER_TEMPLATE.format(
            kc_name=kc_name,
            kc_description=kc_description,
            kc_type=kc_type,
            kc_type_check=kc_type_check,
            exercise_block=exercise_block,
            feedback_content=feedback_content,
            config_block=config_block,
        )

        log_prompt(run_id, "mistral_relevance_checker", user=user, system=_SYSTEM)

        client = self._get_client()
        response = await client.chat.complete_async(
            model=self._model,
            messages=[
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": user},
            ],
            temperature=0.1,
            max_tokens=600,
        )
        raw = response.choices[0].message.content.strip()

        result = _parse_json(raw)
        native_violation = bool(result.get("native_def_violation", False))
        config_violation = bool(result.get("config_violation", False))
        is_relevant = (
            bool(result.get("is_relevant", False))
            and not native_violation
            and not config_violation
        )

        return {
            "is_relevant": is_relevant,
            "exercise_identifiers": result.get("exercise_identifiers", []),
            "found_in_example": result.get("found_in_example", []),
            "kc_illustrated": bool(result.get("kc_illustrated", True)),
            "native_def_violation": native_violation,
            "config_violation": config_violation,
            "config_violation_detail": result.get("config_violation_detail", ""),
            "verdict": result.get("verdict", ""),
        }


def _build_config_block(platform_config: dict | None) -> str:
    if not platform_config:
        return ""
    lines = [f"## Active platform configuration — {platform_config.get('name', 'unnamed')}"]
    vta = (platform_config.get("vocabulary_to_avoid") or "").strip()
    tc = (platform_config.get("teacher_comments") or "").strip()
    if vta:
        lines.append(f"Forbidden vocabulary (must NOT appear in the example): {vta}")
    if tc:
        lines.append(f"Teacher directives: {tc}")
    return "\n".join(lines) + "\n\n"


def _build_exercise_block(
    exercise: dict | None,
    exercise_id: str | None,
    platform_context: str,
) -> str:
    parts = []
    if exercise_id:
        parts.append(f"Exercise ID: {exercise_id}")
    if exercise:
        desc = exercise.get("description", "")
        if desc:
            parts.append(f"Description: {desc}")
        solutions = exercise.get("possible_solutions", [])
        if solutions:
            parts.append("Correct solution(s):\n" + "\n---\n".join(
                f"  {s}" for s in solutions
            ))
    if platform_context and exercise_id:
        in_exercise_section = False
        section_lines = []
        for line in platform_context.splitlines():
            if f"Exercise context (ID {exercise_id})" in line or f"exercise_{exercise_id}" in line.lower():
                in_exercise_section = True
            if in_exercise_section:
                section_lines.append(line)
                if len(section_lines) > 30:
                    break
        if section_lines:
            parts.append("\n".join(section_lines))
    return "\n\n".join(parts)
