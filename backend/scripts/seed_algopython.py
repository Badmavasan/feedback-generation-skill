"""
Seed the AlgoPython platform into a running feedback-generation-skill backend.

Usage (from repo root):
    python backend/scripts/seed_algopython.py [--base-url http://localhost:8000] [--replace]

Options:
    --base-url  Base URL of the backend API  (default: http://localhost:8000)
    --replace   Delete existing AlgoPython context before seeding (safe re-seed)
"""

import argparse
import json
import os
import sys
import urllib.request
import urllib.error

SEED_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "seeds", "algopython_seed.json")


def _auth_header(username: str, password: str) -> str:
    import base64
    token = base64.b64encode(f"{username}:{password}".encode()).decode()
    return f"Basic {token}"


def _post(url: str, payload: dict, auth: str) -> dict:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", "Authorization": auth},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        raise RuntimeError(f"HTTP {e.code} {e.reason}: {body}") from e


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed AlgoPython platform context")
    parser.add_argument("--base-url", default="http://localhost:8000", help="Backend base URL")
    parser.add_argument("--replace", action="store_true", help="Replace existing context chunks")
    args = parser.parse_args()

    username = os.environ.get("ADMIN_USERNAME", "admin")
    password = os.environ.get("ADMIN_PASSWORD", "")
    if not password:
        print("ERROR: set ADMIN_PASSWORD environment variable", file=sys.stderr)
        sys.exit(1)

    auth = _auth_header(username, password)
    base = args.base_url.rstrip("/")

    with open(SEED_FILE, encoding="utf-8") as f:
        seed = json.load(f)

    platform = seed["platform"]
    chunks = seed["context_chunks"]

    # 1. Create platform (ignore 409 if it already exists)
    print(f"Creating platform '{platform['id']}' …")
    try:
        result = _post(f"{base}/platforms", platform, auth)
        print(f"  Created: {result}")
    except RuntimeError as e:
        if "409" in str(e):
            print("  Already exists — skipping creation.")
        else:
            raise

    # 2. Upload context chunks — group by section, replace each cleanly when --replace is used
    sections: dict[str, list[dict]] = {}
    for chunk in chunks:
        sections.setdefault(chunk["section"], []).append(chunk)

    for section, section_chunks in sections.items():
        print(f"Uploading section '{section}' ({len(section_chunks)} chunk(s)) …")
        payload: dict = {"chunks": section_chunks}
        if args.replace:
            payload["replace_section"] = section
        result = _post(f"{base}/platforms/{platform['id']}/context", payload, auth)
        print(f"  Total chunks after upload: {result.get('total_chunks')}")

    print("Done.")


if __name__ == "__main__":
    main()
