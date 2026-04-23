"""Student simulator — uses Mistral to model a K12 student receiving feedback."""
import json
import re
from agents.mistral_agent import MistralFeedbackAgent

_SYSTEM = """\
You are simulating a K12 student learning Python programming.
You have just received a short piece of feedback about a concept you are working on.
Your job is to report honestly whether this feedback gives you enough information to know \
what to do next, and — when an exercise example is involved — whether the example \
actually connects to the exercise you are working on.

Answer in JSON only. No prose outside the JSON object.

JSON schema:
{
  "can_act": true | false,
  "next_step": "<one sentence: what you would try or think about next, based solely on the feedback>",
  "missing": "<one sentence: what is still unclear or missing — empty string if can_act is true>",
  "example_feels_related": true | false | null,
  "example_relevance_note": "<one sentence: does the example connect to your exercise, \
or does it feel like a random Python snippet? — null if no example in the feedback>"
}
"""

_USER_TEMPLATE = """\
Knowledge component: {kc_name}
Description: {kc_description}
{exercise_block}\
{error_block}\
Feedback I received:
\"\"\"{feedback}\"\"\"

Based only on this feedback (not your own knowledge), answer:
- Can I identify what to try or think about next?
- If yes, what would I do?
- If no, what is still missing?
{relevance_question}
"""

_RELEVANCE_QUESTION = """\
- Does the code example in this feedback feel connected to the exercise I am working on, \
or does it look like a generic Python snippet that has nothing to do with my exercise?
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


class StudentSimulator:
    def __init__(self) -> None:
        self._agent = MistralFeedbackAgent()

    async def simulate(
        self,
        feedback: str,
        kc_name: str,
        kc_description: str,
        characteristic: str = "",
        exercise: dict | None = None,
        error: dict | None = None,
        run_id: str | None = None,
    ) -> dict:
        """
        Simulate a student receiving the feedback.

        Returns:
            {
                "can_act": bool,
                "next_step": str,
                "missing": str,
                "example_feels_related": bool | None,
                "example_relevance_note": str | None,
            }
        """
        is_example_related = characteristic == "with_example_related_to_exercise"

        exercise_block = ""
        if exercise:
            desc = exercise.get("description", "")
            exercise_block = f"Exercise I am working on: {desc}\n"

        error_block = ""
        if error:
            error_block = (
                f"Error I made: [{error.get('tag', '')}] "
                f"{error.get('description', '')}\n"
            )

        relevance_question = _RELEVANCE_QUESTION if is_example_related else ""

        user = _USER_TEMPLATE.format(
            kc_name=kc_name,
            kc_description=kc_description,
            exercise_block=exercise_block,
            error_block=error_block,
            feedback=feedback,
            relevance_question=relevance_question,
        )

        raw = await self._agent.generate(
            system_prompt=_SYSTEM,
            user_prompt=user,
            temperature=0.2,
            max_tokens=300,
            run_id=run_id,
            agent_label="student_simulator",
        )

        result = _parse_json(raw)
        return {
            "can_act": bool(result.get("can_act", False)),
            "next_step": result.get("next_step", ""),
            "missing": result.get("missing", ""),
            "example_feels_related": result.get("example_feels_related") if is_example_related else None,
            "example_relevance_note": result.get("example_relevance_note") if is_example_related else None,
        }
