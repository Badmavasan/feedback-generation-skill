"""
Seed the AlgoPython KCs, error catalog, and exercise 116 into the database.

Usage (from repo root):
    python backend/scripts/seed_db_algopython.py [--base-url http://localhost:8000]

Requires ADMIN_PASSWORD env var (default username: admin).
Safe to re-run — duplicate entries are skipped (409 → already exists).
"""
import argparse
import json
import os
import sys
import urllib.request
import urllib.error

# ── Data ──────────────────────────────────────────────────────────────────────

KCS = [
    {
        "platform_id": "algopython",
        "name": "AL.1.1.1.2.3",
        "description": "Décomposer la tâche t en sous-tâches t1...tn — reconnaître que le programme principal se découpe en plusieurs sous-appels ordonnés.",
        "series": "AL",
    },
    {
        "platform_id": "algopython",
        "name": "FO.2.1",
        "description": "Identifier le nom d'une fonction déclarée — savoir que la fonction s'appelle exactement tel nom (ex: vroum et non vroum2 ou vrooum).",
        "series": "FO",
    },
    {
        "platform_id": "algopython",
        "name": "FO.2.2",
        "description": "Identifier les paramètres d'une fonction déclarée — reconnaître le nombre et le rôle des paramètres (ex: vroum prend un seul paramètre entier n).",
        "series": "FO",
    },
    {
        "platform_id": "algopython",
        "name": "FO.2.3",
        "description": "Déterminer la tâche réalisée par une fonction déclarée — comprendre que vroum(n) équivaut exactement à gauche(n) suivi de haut(1).",
        "series": "FO",
    },
    {
        "platform_id": "algopython",
        "name": "FO.4.1",
        "description": "Appeler une fonction native — utiliser une fonction prédéfinie par la plateforme (haut, bas, gauche, droite, print…) sans la redéclarer avec def.",
        "series": "FO",
    },
    {
        "platform_id": "algopython",
        "name": "FO.4.1.1",
        "description": "Choisir l'argument avec lequel appeler la fonction native — déterminer la bonne valeur numérique pour chaque appel natif (ex: gauche(2), bas(1)).",
        "series": "FO",
    },
    {
        "platform_id": "algopython",
        "name": "FO.4.2",
        "description": "Appeler une fonction déclarée — savoir qu'il faut appeler vroum (fonction déclarée ou fournie dans l'énoncé) et non la redéfinir.",
        "series": "FO",
    },
    {
        "platform_id": "algopython",
        "name": "FO.4.2.1",
        "description": "Choisir l'argument avec lequel appeler la fonction déclarée — déterminer la bonne valeur de n pour chaque appel à vroum (ex: vroum(3), vroum(4), vroum(2)).",
        "series": "FO",
    },
]

ERRORS = [
    {
        "platform_id": "algopython",
        "tag": "decomposition_error",
        "description": (
            "Appels de fonctions manquants, superflus ou mal ordonnés au niveau principal du code "
            "(hors corps de fonction déclarée). Indique que l'élève n'a pas décomposé la tâche globale "
            "en sous-appels corrects dans le bon ordre. KC : AL.1.1.1.2.3."
        ),
        "related_kc_names": ["AL.1.1.1.2.3"],
    },
    {
        "platform_id": "algopython",
        "tag": "function_body_error",
        "description": (
            "Instructions manquantes, superflues ou incorrectes à l'intérieur du corps d'une fonction "
            "déclarée (ex: corps de vroum). Indique que l'élève ne maîtrise pas ce que la fonction doit "
            "accomplir. KC : FO.2.3."
        ),
        "related_kc_names": ["FO.2.3"],
    },
    {
        "platform_id": "algopython",
        "tag": "function_declaration_error",
        "description": (
            "Erreurs portant sur la déclaration de la fonction : nom incorrect (ex: vroum2), "
            "nombre de paramètres erroné, ou présence d'un return inattendu. "
            "Indique une confusion sur l'identité ou la signature de la fonction. KC : FO.2.1, FO.2.2."
        ),
        "related_kc_names": ["FO.2.1", "FO.2.2"],
    },
    {
        "platform_id": "algopython",
        "tag": "declared_function_call_error",
        "description": (
            "Appel à une fonction déclarée (ex: vroum) avec un argument incorrect — l'élève appelle "
            "la bonne fonction mais choisit la mauvaise valeur de n par rapport à la carte ou à la "
            "description de l'exercice. KC : FO.4.2, FO.4.2.1."
        ),
        "related_kc_names": ["FO.4.2", "FO.4.2.1"],
    },
    {
        "platform_id": "algopython",
        "tag": "native_function_call_error",
        "description": (
            "Appel à une fonction native de la plateforme (haut, bas, gauche, droite…) avec un "
            "argument incorrect, une native absente, ou une native superflue au niveau principal. "
            "KC : FO.4.1, FO.4.1.1."
        ),
        "related_kc_names": ["FO.4.1", "FO.4.1.1"],
    },
]

EXERCISE_116 = {
    "platform_id": "algopython",
    "exercise_id": "116",
    "title": "Utiliser une fonction pour raccourcir le code",
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
    "exercise_type": "robot",
    "robot_map": {
        "rows": 5,
        "cols": 12,
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
    "kc_names": [
        "AL.1.1.1.2.3",
        "FO.2.1",
        "FO.2.2",
        "FO.2.3",
        "FO.4.1",
        "FO.4.1.1",
        "FO.4.2",
        "FO.4.2.1",
    ],
}


# ── HTTP helpers ──────────────────────────────────────────────────────────────

def _request(method: str, url: str, payload: dict | None, token: str) -> tuple[int, dict]:
    data = json.dumps(payload).encode() if payload else None
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
        method=method,
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        return e.code, {"detail": body}


def _get_token(base: str, username: str, password: str) -> str:
    data = json.dumps({"username": username, "password": password}).encode()
    req = urllib.request.Request(
        f"{base}/auth/login",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())["access_token"]


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Seed AlgoPython DB data")
    parser.add_argument("--base-url", default="http://localhost:8000")
    args = parser.parse_args()

    username = os.environ.get("ADMIN_USERNAME", "admin")
    password = os.environ.get("ADMIN_PASSWORD", "")
    if not password:
        print("ERROR: set ADMIN_PASSWORD environment variable", file=sys.stderr)
        sys.exit(1)

    base = args.base_url.rstrip("/")

    print("Logging in …")
    token = _get_token(base, username, password)
    print("  OK\n")

    # ── KCs ────────────────────────────────────────────────────────────────────
    print(f"Seeding {len(KCS)} knowledge components …")
    for kc in KCS:
        status, body = _request("POST", f"{base}/kcs", kc, token)
        if status == 201:
            print(f"  ✓ {kc['name']}")
        elif status == 409:
            print(f"  ~ {kc['name']} (already exists)")
        else:
            print(f"  ✗ {kc['name']} — {status}: {body}")

    print()

    # ── Errors ─────────────────────────────────────────────────────────────────
    print(f"Seeding {len(ERRORS)} error catalog entries …")
    for err in ERRORS:
        status, body = _request("POST", f"{base}/error-catalog", err, token)
        if status == 201:
            print(f"  ✓ {err['tag']}")
        elif status == 409:
            print(f"  ~ {err['tag']} (already exists)")
        else:
            print(f"  ✗ {err['tag']} — {status}: {body}")

    print()

    # ── Exercise 116 ──────────────────────────────────────────────────────────
    print("Seeding exercise 116 …")
    status, body = _request("POST", f"{base}/exercises", EXERCISE_116, token)
    if status == 201:
        print(f"  ✓ exercise {EXERCISE_116['exercise_id']} — {EXERCISE_116['title']}")
    elif status == 409:
        print(f"  ~ exercise {EXERCISE_116['exercise_id']} (already exists)")
    else:
        print(f"  ✗ {status}: {body}")

    print("\nDone.")


if __name__ == "__main__":
    main()
