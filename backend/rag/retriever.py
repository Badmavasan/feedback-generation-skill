"""High-level RAG retrieval — build a context string for the orchestrator."""
import re
from rag.store import get_vector_store


def format_db_exercise_context(exercise: dict) -> str:
    """
    Format a DB exercise record (as a plain dict) into a structured context string
    suitable for injection into the orchestrator's platform context.

    Works for exercises that live only in the DB (not yet / no longer in Chroma).
    """
    lines = [
        f"Exercice ID {exercise['exercise_id']} — Type : {exercise.get('exercise_type', '?')}",
        f"Titre : {exercise.get('title', '')}",
        "",
        "Description pédagogique :",
        exercise.get("description", "").strip(),
    ]

    solutions = exercise.get("possible_solutions") or []
    if solutions:
        lines += ["", "Solution correcte :"]
        for sol in solutions:
            for ln in sol.splitlines():
                lines.append(f"  {ln}")

    robot_map = exercise.get("robot_map")
    if robot_map:
        grid = robot_map.get("grid", [])
        rows = robot_map.get("rows", len(grid))
        cols = robot_map.get("cols", len(grid[0]) if grid else 0)
        lines += ["", f"Carte (grille {rows} lignes × {cols} colonnes) :"]
        for i, row in enumerate(grid):
            lines.append(f"  Ligne {i} : [{', '.join(row)}]")
        lines += [
            "Légende : O = case libre, X = obstacle, I = position initiale du robot, G = arrivée",
        ]

    kc_names = exercise.get("kc_names") or []
    if kc_names:
        lines += ["", "Composantes de connaissance mobilisées :"]
        for kc in kc_names:
            lines.append(f"  {kc}")

    return "\n".join(lines)


def retrieve_platform_context(
    platform_id: str,
    query: str,
    n_results: int = 6,
) -> str:
    """
    Query the platform's vector store and return a formatted context string
    ready to be injected into the orchestrator's system prompt.
    """
    store = get_vector_store()
    chunks = store.query(platform_id, query, n_results=n_results)
    if not chunks:
        return ""
    return "\n\n---\n\n".join(chunks)


def retrieve_full_platform_context(
    platform_id: str,
    generation_context: dict,
    exercise_context_override: str | None = None,
) -> str:
    """
    Build a rich platform context by running targeted queries for each
    relevant dimension: pedagogy, tone/style, curriculum, characters.

    When `exercise_context_override` is provided (pre-built from DB), it is used
    as the exercise section — the Chroma section query is skipped for that section.
    When it is None and an exercise_id is in generation_context, the Chroma
    section query is used as before (backwards-compatible fallback).
    """
    store = get_vector_store()
    if store.count_chunks(platform_id) == 0:
        return exercise_context_override or ""

    sections = {
        "Pedagogical guidelines": "pedagogical approach learning feedback students",
        "Tone and style": "tone style language writing feedback characters voice",
        "Curriculum": f"curriculum knowledge component {generation_context.get('kc_name', '')}",
        "Feedback system": "feedback system characteristics level compatibility",
        "Interaction data": "interaction data student behavior metrics events",
    }

    parts = []
    seen: set[str] = set()

    # Exercise section — DB override takes priority over Chroma lookup
    exercise_id = generation_context.get("exercise_id")
    if exercise_context_override:
        parts.append(
            f"## Exercise context (ID {exercise_id or '?'}) [source: database]\n"
            + exercise_context_override
        )
        seen.add(exercise_context_override)
    elif exercise_id:
        exercise_chunks = store.query(
            platform_id,
            f"exercice {exercise_id}",
            n_results=2,
            section_filter=f"exercise_{exercise_id}",
        )
        if exercise_chunks:
            seen.update(exercise_chunks)
            parts.append(
                f"## Exercise context (ID {exercise_id}) [source: vector store]\n"
                + "\n\n".join(exercise_chunks)
            )

    for label, query in sections.items():
        chunks = store.query(platform_id, query, n_results=3)
        new_chunks = [c for c in chunks if c not in seen]
        seen.update(new_chunks)
        if new_chunks:
            parts.append(f"## {label}\n" + "\n\n".join(new_chunks))

    return "\n\n".join(parts)


def retrieve_exercise_struct(platform_id: str, exercise_id: str) -> dict | None:
    """
    Return {"description": str, "possible_solutions": list[str]} for a given exercise_id,
    extracted from the exercise-specific RAG chunk.

    Falls back to the full chunk text as description if structured parsing fails.
    Returns None if no exercise chunk is found.
    """
    store = get_vector_store()
    chunks = store.query(
        platform_id,
        f"exercice {exercise_id} description solution correcte",
        n_results=1,
        section_filter=f"exercise_{exercise_id}",
    )
    if not chunks:
        return None

    text = chunks[0]
    description = _parse_description(text)
    solutions = _parse_solutions(text)

    return {
        "description": description or text[:500],
        "possible_solutions": solutions,
    }


def _parse_description(text: str) -> str:
    """Extract the pedagogical description block from an exercise chunk."""
    # Match content after "Description pédagogique :" or "Description :" until next header
    match = re.search(
        r'Description\s+p[ée]dagogique\s*:\s*\n(.*?)(?=\n(?:Carte|Solution|Composantes|---|\Z))',
        text,
        re.DOTALL | re.IGNORECASE,
    )
    if match:
        return match.group(1).strip()
    # Fallback: first non-empty paragraph
    for para in text.split("\n\n"):
        para = para.strip()
        if para and not para.startswith("Exercice ID"):
            return para
    return ""


def _parse_solutions(text: str) -> list[str]:
    """Extract the correct solution code block(s) from an exercise chunk."""
    match = re.search(
        r'Solution\s+correcte\s*:\s*\n(.*?)(?=\n(?:Composantes|---|\Z))',
        text,
        re.DOTALL | re.IGNORECASE,
    )
    if not match:
        return []
    raw = match.group(1)
    # Strip consistent leading indentation (2 spaces used in seed)
    lines = raw.splitlines()
    dedented = "\n".join(
        line[2:] if line.startswith("  ") else line
        for line in lines
    ).strip()
    return [dedented] if dedented else []
