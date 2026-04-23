"""
Coherence checker — verifies that a multi-component feedback set is non-redundant.

Called via the check_coherence orchestrator tool whenever more than one characteristic
is requested. Uses a focused Claude call to detect point-for-point redundancy between
accepted components before assembly.
"""
import json
import re
import anthropic
from core.config import get_settings
from core.agent_logger import log_prompt

_SYSTEM = """\
You are a strict pedagogical coherence reviewer for K12 programming feedback.

Your job: given a set of accepted feedback components (one per characteristic),
detect whether any pair makes the SAME pedagogical point in different words.

Redundancy definition — a pair is redundant when:
- Both components convey the same conceptual idea (e.g. both explain WHY loops work),
  even if the wording or framing differs.
- The example in one component illustrates exactly the same sub-concept already covered
  by another component's example.

Non-redundancy — a pair is NOT redundant when:
- `logos` explains the concept / mental model → `technical` explains how to apply it.
  These cover different angles (why vs. how) and are complementary, not redundant.
- `error_pointed` names a specific error → `logos` explains the underlying concept.
  Different grain (error vs. concept).
- Two `with_example_*` components use different contexts or illustrate different aspects.

Be strict: if the same conceptual point is made twice (even at different abstraction levels),
it is redundant. If the two components address different angles, mark as complementary.

Answer in JSON only. No prose outside the JSON object.

JSON schema:
{
  "passed": true | false,
  "redundancies": [
    {
      "components": ["<char1>", "<char2>"],
      "point_repeated": "<the exact shared point in one sentence>",
      "keep": "<which of the two to keep as-is>",
      "regenerate": "<which to regenerate>",
      "suggested_angle": "<what different angle the regenerated component should cover>"
    }
  ],
  "summary": "<one sentence overall verdict>"
}

If passed=true, redundancies must be an empty array.
"""

_USER_TEMPLATE = """\
## KC context
Name: {kc_name}
Description: {kc_description}

## Accepted feedback components

{components_block}

## Task
Check every pair of components for redundancy.
- If any pair is redundant: passed=false, list each redundant pair in `redundancies`.
- If all pairs are complementary: passed=true, redundancies=[].
"""


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


class CoherenceChecker:
    def __init__(self) -> None:
        settings = get_settings()
        self._client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        self._model = settings.orchestrator_model

    async def check(
        self,
        components: dict[str, str],
        kc_name: str,
        kc_description: str,
        run_id: str | None = None,
    ) -> dict:
        """
        Check a set of accepted components for redundancy.

        components: {characteristic: feedback_text}
        Returns:
            {
                "passed": bool,
                "redundancies": [{"components", "point_repeated", "keep", "regenerate", "suggested_angle"}],
                "summary": str,
            }
        """
        if len(components) <= 1:
            return {"passed": True, "redundancies": [], "summary": "Single component — no coherence check needed."}

        lines = []
        for char, text in components.items():
            lines.append(f"### {char}\n{text}")
        components_block = "\n\n".join(lines)

        user = _USER_TEMPLATE.format(
            kc_name=kc_name,
            kc_description=kc_description,
            components_block=components_block,
        )

        log_prompt(run_id, "coherence_checker", user=user, system=_SYSTEM)
        response = await self._client.messages.create(
            model=self._model,
            max_tokens=800,
            temperature=0.0,
            system=_SYSTEM,
            messages=[{"role": "user", "content": user}],
        )
        raw = response.content[0].text
        result = _parse_json(raw)

        return {
            "passed": bool(result.get("passed", True)),
            "redundancies": result.get("redundancies", []),
            "summary": result.get("summary", ""),
        }
