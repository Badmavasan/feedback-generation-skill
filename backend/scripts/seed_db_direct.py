"""
Seed KCs, error catalog, and exercise 116 directly into PostgreSQL.
Run inside the backend container:
    docker exec feedback-generation-skill-backend-1 python scripts/seed_db_direct.py
"""
import asyncio
from datetime import datetime

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

DATABASE_URL = "postgresql+asyncpg://feedback:feedback@db:5432/feedback"

engine = create_async_engine(DATABASE_URL, echo=False)
Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


KCS = [
    {"platform_id": "algopython", "name": "AL.1.1.1.2.3", "series": "AL",
     "description": "Décomposer la tâche t en sous-tâches t1...tn — reconnaître que le programme principal se découpe en plusieurs sous-appels ordonnés."},
    {"platform_id": "algopython", "name": "FO.2.1", "series": "FO",
     "description": "Identifier le nom d'une fonction déclarée — savoir que la fonction s'appelle exactement tel nom (ex: vroum et non vroum2 ou vrooum)."},
    {"platform_id": "algopython", "name": "FO.2.2", "series": "FO",
     "description": "Identifier les paramètres d'une fonction déclarée — reconnaître le nombre et le rôle des paramètres (ex: vroum prend un seul paramètre entier n)."},
    {"platform_id": "algopython", "name": "FO.2.3", "series": "FO",
     "description": "Déterminer la tâche réalisée par une fonction déclarée — comprendre que vroum(n) équivaut exactement à gauche(n) suivi de haut(1)."},
    {"platform_id": "algopython", "name": "FO.4.1", "series": "FO",
     "description": "Appeler une fonction native — utiliser une fonction prédéfinie par la plateforme (haut, bas, gauche, droite, print…) sans la redéclarer avec def."},
    {"platform_id": "algopython", "name": "FO.4.1.1", "series": "FO",
     "description": "Choisir l'argument avec lequel appeler la fonction native — déterminer la bonne valeur numérique pour chaque appel natif (ex: gauche(2), bas(1))."},
    {"platform_id": "algopython", "name": "FO.4.2", "series": "FO",
     "description": "Appeler une fonction déclarée — savoir qu'il faut appeler vroum (fonction déclarée ou fournie dans l'énoncé) et non la redéfinir."},
    {"platform_id": "algopython", "name": "FO.4.2.1", "series": "FO",
     "description": "Choisir l'argument avec lequel appeler la fonction déclarée — déterminer la bonne valeur de n pour chaque appel à vroum (ex: vroum(3), vroum(4), vroum(2))."},
]

ERRORS = [
    {"platform_id": "algopython", "tag": "decomposition_error",
     "related_kc_names": ["AL.1.1.1.2.3"],
     "description": "Appels de fonctions manquants, superflus ou mal ordonnés au niveau principal du code (hors corps de fonction déclarée). Indique que l'élève n'a pas décomposé la tâche globale en sous-appels corrects dans le bon ordre. KC : AL.1.1.1.2.3."},
    {"platform_id": "algopython", "tag": "function_body_error",
     "related_kc_names": ["FO.2.3"],
     "description": "Instructions manquantes, superflues ou incorrectes à l'intérieur du corps d'une fonction déclarée (ex: corps de vroum). Indique que l'élève ne maîtrise pas ce que la fonction doit accomplir. KC : FO.2.3."},
    {"platform_id": "algopython", "tag": "function_declaration_error",
     "related_kc_names": ["FO.2.1", "FO.2.2"],
     "description": "Erreurs portant sur la déclaration de la fonction : nom incorrect (ex: vroum2), nombre de paramètres erroné, ou présence d'un return inattendu. Indique une confusion sur l'identité ou la signature de la fonction. KC : FO.2.1, FO.2.2."},
    {"platform_id": "algopython", "tag": "declared_function_call_error",
     "related_kc_names": ["FO.4.2", "FO.4.2.1"],
     "description": "Appel à une fonction déclarée (ex: vroum) avec un argument incorrect — l'élève appelle la bonne fonction mais choisit la mauvaise valeur de n. KC : FO.4.2, FO.4.2.1."},
    {"platform_id": "algopython", "tag": "native_function_call_error",
     "related_kc_names": ["FO.4.1", "FO.4.1.1"],
     "description": "Appel à une fonction native de la plateforme (haut, bas, gauche, droite…) avec un argument incorrect, une native absente, ou une native superflue au niveau principal. KC : FO.4.1, FO.4.1.1."},
]

EXERCISE_116 = {
    "platform_id": "algopython",
    "exercise_id": "116",
    "title": "Utiliser une fonction pour raccourcir le code",
    "exercise_type": "robot",
    "description": (
        "Dans cet exercice, une fonction vroum est déjà définie :\n\n"
        "  def vroum(n):\n"
        "      gauche(n)\n"
        "      haut(1)\n\n"
        "Seul, ce code ne fait rien : il faut appeler la fonction avec un argument entier à la place de n. "
        "Par exemple, vroum(3) équivaut à gauche(3) puis haut(1) — le robot avance de 3 cases à gauche, "
        "puis de 1 case en haut. L'élève doit appeler vroum avec les bons arguments, et peut aussi utiliser "
        "les fonctions individuelles gauche, droite, haut, bas si nécessaire, pour guider le robot jusqu'à l'arrivée."
    ),
    "robot_map": {
        "rows": 5, "cols": 12,
        "grid": [
            ["O","X","X","O","O","X","O","O","O","O","O","O"],
            ["O","X","O","O","O","X","O","O","O","O","O","O"],
            ["G","X","O","O","O","X","X","X","X","X","O","O"],
            ["O","O","O","X","O","O","O","O","O","X","X","X"],
            ["X","X","X","X","X","X","X","X","O","O","O","I"],
        ],
    },
    "possible_solutions": [
        "def vroum(n):\n    gauche(n)\n    haut(1)\n\nvroum(3)\nvroum(4)\ngauche(2)\nbas(1)\nvroum(2)"
    ],
    "kc_names": ["AL.1.1.1.2.3","FO.2.1","FO.2.2","FO.2.3","FO.4.1","FO.4.1.1","FO.4.2","FO.4.2.1"],
}


async def seed():
    import json as _json

    async with Session() as db:
        now = datetime.utcnow()

        # ── KCs ────────────────────────────────────────────────────────────────
        print(f"Seeding {len(KCS)} KCs …")
        for kc in KCS:
            exists = (await db.execute(
                text("SELECT 1 FROM knowledge_components WHERE platform_id=:pid AND name=:name"),
                {"pid": kc["platform_id"], "name": kc["name"]},
            )).scalar()
            if exists:
                print(f"  ~ {kc['name']} (already exists)")
            else:
                await db.execute(
                    text("""
                        INSERT INTO knowledge_components (platform_id, name, description, series, created_at)
                        VALUES (:pid, :name, :desc, :series, :now)
                    """),
                    {"pid": kc["platform_id"], "name": kc["name"],
                     "desc": kc["description"], "series": kc["series"], "now": now},
                )
                print(f"  ✓ {kc['name']}")

        # ── Errors ─────────────────────────────────────────────────────────────
        print(f"\nSeeding {len(ERRORS)} error entries …")
        for err in ERRORS:
            exists = (await db.execute(
                text("SELECT 1 FROM error_entries WHERE platform_id=:pid AND tag=:tag"),
                {"pid": err["platform_id"], "tag": err["tag"]},
            )).scalar()
            if exists:
                print(f"  ~ {err['tag']} (already exists)")
            else:
                await db.execute(
                    text("""
                        INSERT INTO error_entries (platform_id, tag, description, related_kc_names, created_at)
                        VALUES (:pid, :tag, :desc, :kcs::jsonb, :now)
                    """),
                    {"pid": err["platform_id"], "tag": err["tag"],
                     "desc": err["description"],
                     "kcs": _json.dumps(err["related_kc_names"]), "now": now},
                )
                print(f"  ✓ {err['tag']}")

        # ── Exercise 116 ───────────────────────────────────────────────────────
        print("\nSeeding exercise 116 …")
        ex = EXERCISE_116
        exists = (await db.execute(
            text("SELECT 1 FROM exercises WHERE exercise_id=:eid"),
            {"eid": ex["exercise_id"]},
        )).scalar()
        if exists:
            print(f"  ~ exercise {ex['exercise_id']} (already exists)")
        else:
            await db.execute(
                text("""
                    INSERT INTO exercises
                      (platform_id, exercise_id, title, description, exercise_type,
                       robot_map, possible_solutions, kc_names, created_at, updated_at)
                    VALUES
                      (:pid, :eid, :title, :desc, :etype,
                       :rmap::jsonb, :sols::jsonb, :kcs::jsonb, :now, :now)
                """),
                {
                    "pid": ex["platform_id"], "eid": ex["exercise_id"],
                    "title": ex["title"], "desc": ex["description"],
                    "etype": ex["exercise_type"],
                    "rmap": _json.dumps(ex["robot_map"]),
                    "sols": _json.dumps(ex["possible_solutions"]),
                    "kcs": _json.dumps(ex["kc_names"]),
                    "now": now,
                },
            )
            print(f"  ✓ exercise {ex['exercise_id']} — {ex['title']}")

        await db.commit()
        print("\nDone.")


if __name__ == "__main__":
    asyncio.run(seed())
