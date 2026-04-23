"""
Populate the `platforms` and `general_config` DB tables from existing project files.

Sources:
  - platform_context  ← backend/data/seeds/algopython_seed.json  (context_chunks)
  - general_feedback_instructions ← prompts/feedback.py FEEDBACK_AGENT_SYSTEM (hard rules)

Usage (inside container):
    python scripts/seed_platform_db.py

Usage (via docker exec from repo root):
    docker exec feedback-generation-skill-backend-1 python scripts/seed_platform_db.py
"""

import asyncio
import json
import os
import sys

# ── add backend/ to path so imports work ──────────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.database import AsyncSessionLocal
from db.crud import get_platform_db, update_platform_db, upsert_general_config

SEED_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "seeds", "algopython_seed.json")


# ── Platform context built from algopython_seed.json ──────────────────────────

SECTION_LABELS = {
    "general":               "Présentation générale",
    "curriculum":            "Curriculum et types d'exercices",
    "feedback_system":       "Système de feedback",
    "pedagogical_guidelines":"Directives pédagogiques",
    "tone_style":            "Ton et registre",
}


def build_platform_context(chunks: list[dict]) -> str:
    """
    Build a single structured text from context chunks.
    Chunks with the same section are grouped under one heading.
    """
    # Group by section, preserve order of first appearance
    sections: dict[str, list[str]] = {}
    for chunk in chunks:
        sec = chunk["section"]
        sections.setdefault(sec, []).append(chunk["content"].strip())

    parts = []
    for sec, contents in sections.items():
        label = SECTION_LABELS.get(sec, sec.replace("_", " ").title())
        parts.append(f"## {label}")
        parts.extend(contents)
        parts.append("")  # blank line between sections

    return "\n\n".join(p for p in parts if p != "").strip()


# ── General feedback instructions (language/platform-independent hard rules) ──

GENERAL_FEEDBACK_INSTRUCTIONS = """\
Règles absolues pour tous les feedbacks

Longueur — non négociable :
MAXIMUM 500-800 caractères avec tous les Components de Feedback. Absolument pas plus de 800 caractères.
C'est un coup de pouce formatif, pas un cours. Si tu as besoin de plus d'espace, coupe.

Philosophie du stepping-stone :
Tu n'expliques PAS tout. Tu donnes à l'élève UNE piste précise pour qu'il trouve l'étape suivante seul.
Laisse quelque chose à découvrir. Oriente vers la réponse, ne la donne pas.
Question directrice : quelle est la SEULE chose la plus importante dont cet élève a besoin pour débloquer sa réflexion maintenant ?

Format de sortie — texte brut uniquement (sauf blocs de code) :
AUCUN markdown dans la prose : pas de gras, pas de italique, pas de ## titres, pas de listes.
Pas de préambule, pas de méta-commentaire, pas de balises XML.
Tout le contenu est en {language_name}.

Fragments de code (caractéristiques with_example uniquement) :
Encadrer le code bloc dans <code-block>...</code-block>. Les expressions inline dans <code-inline>...</code-inline>.
Le contenu dans <code-block> doit contenir ZÉRO commentaire. Aucun # à l'intérieur.
Toute explication va dans le texte avant le code, pas dans la balise.
Garder le fragment court (≤ 8 lignes). Il doit être syntaxiquement correct tel quel.
NE JAMAIS montrer la solution complète à l'exercice. Montrer un fragment partiel et illustratif.
Le fragment est un stepping-stone conceptuel, pas une réponse.

Vision d'ensemble — toujours :
Chaque feedback doit porter une idée de niveau conceptuel qui va au-delà du problème immédiat.
L'élève doit repartir avec quelque chose de transférable, pas juste corriger ce cas précis.
Niveau task_type ou exercise : pencher vers le concept.
Niveau error ou error_exercise : adresser l'erreur, mais l'ancrer dans le concept sous-jacent.

Ton et registre — jeune enseignant, ni trop formel ni trop familier :
Écrire comme un enseignant de 25 ans qui parle à ses élèves : clair, direct, humain, avec une intention pédagogique visible mais sans rigidité.
Tutoiement obligatoire. Phrases courtes. Français naturel parlé — pas le français d'un manuel.
Bonnes amorces : "Vérifie que...", "Pense à...", "Le problème vient de...", "Ce que tu cherches ici, c'est...", "Regarde ce qui se passe quand..."
INTERDIT — trop formel : "Il convient de noter que", "On observe que", "Il est nécessaire de", "En effet,", "Ainsi,", "Par conséquent,", "De ce fait,"
INTERDIT — trop familier : "Ouais", "Cool", "Genre", "En gros", "T'as vu"
INTERDIT — encouragements vides : "Bravo !", "C'est bien essayé !", "Super !", "Excellent !"
Ne jamais valider une conception erronée de l'élève pour adoucir le message.

Qualité formative :
Après lecture, l'élève doit savoir exactement quoi essayer ou réfléchir sur la stratégie de correction de code pour résoudre le problème ensuite.
Une idée claire. Une direction. C'est tout.

Règle sur les types Python — non typé :
Ne jamais mentionner le type d'une variable ou d'une valeur (pas "un entier", "une chaîne de caractères", "un booléen", "de type int", etc.).
Ne jamais utiliser les mots : type, int, str, float, bool, TypeError, isinstance, cast, typage.
Si une valeur est numérique, parler de "valeur" ou de "nombre".
Si une valeur est textuelle, parler de "texte" ou de "ce qui est entre guillemets".
"""


async def seed() -> None:
    # Load seed JSON
    with open(SEED_FILE, encoding="utf-8") as f:
        seed_data = json.load(f)

    chunks = seed_data["context_chunks"]
    platform_context = build_platform_context(chunks)

    async with AsyncSessionLocal() as db:
        try:
            # ── Update platform_context for algopython ─────────────────────────
            p = await get_platform_db(db, "algopython")
            if p is None:
                print("ERROR: platform 'algopython' not found in DB. Run the backend first to auto-seed it.", file=sys.stderr)
                return

            await update_platform_db(db, "algopython", {
                "platform_context": platform_context,
                "name": "AlgoPython",
                "language": "fr",
                "description": "Plateforme d'apprentissage de la programmation Python pour élèves de seconde (K12), en français.",
                "feedback_mode": "offline",
            })
            print(f"✓ platform_context updated for 'algopython' ({len(platform_context)} chars, {len(chunks)} source chunks)")

            # ── Upsert general_feedback_instructions ───────────────────────────
            cfg = await upsert_general_config(db, GENERAL_FEEDBACK_INSTRUCTIONS.strip())
            print(f"✓ general_feedback_instructions saved ({len(cfg.general_feedback_instructions)} chars)")

            await db.commit()
            print("\nDone. Both records committed.")

        except Exception as e:
            await db.rollback()
            print(f"ERROR: {e}", file=sys.stderr)
            raise


if __name__ == "__main__":
    asyncio.run(seed())
