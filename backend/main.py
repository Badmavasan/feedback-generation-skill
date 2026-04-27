from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import auth, platforms, feedback
from api.routes import algopython as algopython_router
from core.config import get_settings
from db.database import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    await _seed_all()
    yield


async def _seed_all() -> None:
    """
    Idempotent startup seed — runs on every container start, safe to re-run.

    Covers:
      1. algopython platform row + platform_context
      2. KCs (upsert: description+series always refreshed from source file)
      3. Error catalog (insert-only: existing descriptions are never overwritten)
      4. general_feedback_instructions (written only if currently empty)
    """
    import json
    from datetime import datetime
    from pathlib import Path

    from db.database import AsyncSessionLocal
    from db.crud import (
        get_platform_db, create_platform_db, update_platform_db,
        get_general_config, upsert_general_config,
    )

    SEEDS = Path("/app/data/seeds")

    # ── Load seed files ────────────────────────────────────────────────────────
    platform_seed_path = SEEDS / "algopython_seed.json"
    kcs_path           = SEEDS / "algopython_kcs_source.json"
    errors_path        = SEEDS / "algopython_errors_source.json"

    platform_seed = json.loads(platform_seed_path.read_text()) if platform_seed_path.exists() else None
    kcs_data      = json.loads(kcs_path.read_text())           if kcs_path.exists()           else []
    errors_data   = json.loads(errors_path.read_text())        if errors_path.exists()         else []

    # ── Build platform_context from seed chunks ────────────────────────────────
    _SECTION_LABELS = {
        "general":                "Présentation générale",
        "curriculum":             "Curriculum et types d'exercices",
        "feedback_system":        "Système de feedback",
        "pedagogical_guidelines": "Directives pédagogiques",
        "tone_style":             "Ton et registre",
        "robot_map":              "Format des cartes robot",
    }

    def _build_platform_context(chunks: list[dict]) -> str:
        sections: dict[str, list[str]] = {}
        for c in chunks:
            sections.setdefault(c["section"], []).append(c["content"].strip())
        parts = []
        for sec, contents in sections.items():
            label = _SECTION_LABELS.get(sec, sec.replace("_", " ").title())
            parts.append(f"## {label}")
            parts.extend(contents)
            parts.append("")
        return "\n\n".join(p for p in parts if p != "").strip()

    platform_context = (
        _build_platform_context(platform_seed["context_chunks"])
        if platform_seed else None
    )

    # ── General feedback instructions (cross-platform hard rules) ─────────────
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
Si une valeur est textuelle, parler de "texte" ou de "ce qui est entre guillemets"."""

    now = datetime.utcnow()

    async with AsyncSessionLocal() as session:
        try:
            # ── 1. Platform row ────────────────────────────────────────────────
            existing = await get_platform_db(session, "algopython")
            if existing is None:
                await create_platform_db(session, {
                    "id": "algopython",
                    "name": "AlgoPython",
                    "language": "fr",
                    "description": "Plateforme d'apprentissage de la programmation Python pour élèves de seconde (K12), en français.",
                    "feedback_mode": "offline",
                    "platform_context": platform_context,
                    "live_student_prompt": None,
                    "created_at": now,
                    "updated_at": now,
                })
            elif platform_context:
                # Always refresh from seed file — seed is the source of truth for platform context
                await update_platform_db(session, "algopython", {"platform_context": platform_context})

            # ── 2. KCs (upsert) ────────────────────────────────────────────────
            if kcs_data:
                from sqlalchemy import text
                kc_ins = kc_upd = 0
                for kc in kcs_data:
                    row = (await session.execute(
                        text("SELECT id FROM knowledge_components WHERE platform_id=:p AND name=:n"),
                        {"p": kc["platform_id"], "n": kc["name"]},
                    )).fetchone()
                    if row:
                        await session.execute(
                            text("UPDATE knowledge_components SET description=:d, series=:s WHERE platform_id=:p AND name=:n"),
                            {"d": kc["description"], "s": kc.get("series"), "p": kc["platform_id"], "n": kc["name"]},
                        )
                        kc_upd += 1
                    else:
                        await session.execute(
                            text("INSERT INTO knowledge_components (platform_id, name, description, series, created_at) VALUES (:p, :n, :d, :s, :t)"),
                            {"p": kc["platform_id"], "n": kc["name"], "d": kc["description"], "s": kc.get("series"), "t": now},
                        )
                        kc_ins += 1

            # ── 3. Errors (insert-only) ────────────────────────────────────────
            if errors_data:
                from sqlalchemy import text
                err_ins = err_skip = 0
                for err in errors_data:
                    exists = (await session.execute(
                        text("SELECT 1 FROM error_entries WHERE platform_id=:p AND tag=:t"),
                        {"p": err["platform_id"], "t": err["tag"]},
                    )).scalar()
                    if exists:
                        err_skip += 1
                    else:
                        await session.execute(
                            text("INSERT INTO error_entries (platform_id, tag, description, related_kc_names, created_at) VALUES (:p, :t, :d, CAST(:k AS jsonb), :now)"),
                            {"p": err["platform_id"], "t": err["tag"], "d": err["description"], "k": json.dumps(err["related_kc_names"]), "now": now},
                        )
                        err_ins += 1

            # ── 4. General config (always refresh from source) ────────────────
            await upsert_general_config(session, GENERAL_FEEDBACK_INSTRUCTIONS.strip())

            await session.commit()

        except Exception:
            await session.rollback()
            raise


_settings = get_settings()
_cors_origins = [o.strip() for o in _settings.cors_origins.split(",") if o.strip()]

app = FastAPI(
    title="Feedback Generation Skill",
    root_path="/feedback-generation/api",
    description=(
        "Multi-platform, multi-agent pedagogical feedback generation for K12 programming learners.\n\n"
        "## Feedback endpoints\n"
        "All four endpoints support **offline** (reusable) and **live** (student-personalised) modes "
        "via the `mode` field in the request body.\n\n"
        "Auth: admin JWT (`Authorization: Bearer …`) **or** platform API key (`X-API-Key`).\n\n"
        "- **POST /feedback/kc** — KC / task_type level (no exercise context)\n"
        "- **POST /feedback/exercise** — Exercise level (anchored in an exercise)\n"
        "- **POST /feedback/error** — Error level (targets a specific student error)\n"
        "- **POST /feedback/image** — Image-annotated feedback via Gemini\n\n"
        "## Catalog\n"
        "- **GET/POST /exercises** — Exercise catalog\n"
        "- **GET/POST /kcs** — Knowledge component catalog\n"
        "- **GET/POST /error-catalog** — Error catalog\n\n"
        "## History\n"
        "- **GET /history** — Feedback generation history + full agent traces\n"
    ),
    version="2.0.0",
    lifespan=lifespan,
    openapi_tags=[
        {"name": "feedback", "description": "Feedback generation — offline and live modes, dual auth."},
        {"name": "platforms", "description": "Platform registry and RAG context management."},
        {"name": "exercises", "description": "Exercise catalog CRUD."},
        {"name": "kcs", "description": "Knowledge component catalog CRUD."},
        {"name": "error-catalog", "description": "Error catalog CRUD."},
        {"name": "history", "description": "Feedback generation history and agent traces."},
        {"name": "auth", "description": "Admin authentication (JWT)."},
        {"name": "algopython", "description": "AlgoPython source DB — exercises, errors, task types (read-only)."},
    ],
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(platforms.router)
app.include_router(feedback.router)
app.include_router(algopython_router.router)

# Catalog + history routes (imported after DB is wired)
from api.routes import exercises as exercises_router      # noqa: E402
from api.routes import kcs as kcs_router                  # noqa: E402
from api.routes import error_catalog as error_catalog_router  # noqa: E402
from api.routes import history as history_router          # noqa: E402

app.include_router(exercises_router.router)
app.include_router(kcs_router.router)
app.include_router(error_catalog_router.router)
app.include_router(history_router.router)


@app.get("/health")
async def health():
    return {"status": "ok"}
