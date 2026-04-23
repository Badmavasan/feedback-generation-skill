"""
Full smart-upsert seed for AlgoPython KCs and error catalog.

Rules:
  KCs    → full upsert by (platform_id, name): UPDATE description+series if exists, INSERT if new
  Errors → INSERT-only by (platform_id, tag): skip existing entries entirely (user may have enriched descriptions)

Source files (relative to /app inside container):
  data/seeds/algopython_kcs_source.json
  data/seeds/algopython_errors_source.json

Usage (inside container):
    docker exec feedback-generation-skill-backend-1 python scripts/seed_db_full.py

Or copy + run ad-hoc:
    docker cp backend/scripts/seed_db_full.py feedback-generation-skill-backend-1:/app/scripts/
    docker exec feedback-generation-skill-backend-1 python scripts/seed_db_full.py
"""
import asyncio
import json
import os
from datetime import datetime
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

DATABASE_URL = "postgresql+asyncpg://feedback:feedback@db:5432/feedback"

engine = create_async_engine(DATABASE_URL, echo=False)
Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

SEEDS_DIR = Path(__file__).parent.parent / "data" / "seeds"


async def seed_kcs(db: AsyncSession, kcs: list[dict]) -> tuple[int, int]:
    """Upsert KCs: update description+series for existing, insert new. Returns (inserted, updated)."""
    inserted = updated = 0
    now = datetime.utcnow()

    for kc in kcs:
        exists = (await db.execute(
            text("SELECT id FROM knowledge_components WHERE platform_id=:pid AND name=:name"),
            {"pid": kc["platform_id"], "name": kc["name"]},
        )).fetchone()

        if exists:
            await db.execute(
                text("""
                    UPDATE knowledge_components
                    SET description=:desc, series=:series
                    WHERE platform_id=:pid AND name=:name
                """),
                {"desc": kc["description"], "series": kc.get("series"), "pid": kc["platform_id"], "name": kc["name"]},
            )
            updated += 1
        else:
            await db.execute(
                text("""
                    INSERT INTO knowledge_components (platform_id, name, description, series, created_at)
                    VALUES (:pid, :name, :desc, :series, :now)
                """),
                {
                    "pid": kc["platform_id"], "name": kc["name"],
                    "desc": kc["description"], "series": kc.get("series"), "now": now,
                },
            )
            inserted += 1

    return inserted, updated


async def seed_errors(db: AsyncSession, errors: list[dict]) -> tuple[int, int]:
    """Insert new error tags only — never overwrite existing descriptions. Returns (inserted, skipped)."""
    inserted = skipped = 0
    now = datetime.utcnow()

    for err in errors:
        exists = (await db.execute(
            text("SELECT 1 FROM error_entries WHERE platform_id=:pid AND tag=:tag"),
            {"pid": err["platform_id"], "tag": err["tag"]},
        )).scalar()

        if exists:
            skipped += 1
        else:
            await db.execute(
                text("""
                    INSERT INTO error_entries (platform_id, tag, description, related_kc_names, created_at)
                    VALUES (:pid, :tag, :desc, CAST(:kcs AS jsonb), :now)
                """),
                {
                    "pid": err["platform_id"], "tag": err["tag"],
                    "desc": err["description"],
                    "kcs": json.dumps(err["related_kc_names"]),
                    "now": now,
                },
            )
            inserted += 1

    return inserted, skipped


async def main():
    kcs_path = SEEDS_DIR / "algopython_kcs_source.json"
    errors_path = SEEDS_DIR / "algopython_errors_source.json"

    if not kcs_path.exists():
        raise FileNotFoundError(f"KC source file not found: {kcs_path}")
    if not errors_path.exists():
        raise FileNotFoundError(f"Error source file not found: {errors_path}")

    with open(kcs_path) as f:
        kcs = json.load(f)
    with open(errors_path) as f:
        errors = json.load(f)

    print(f"Source: {len(kcs)} KCs, {len(errors)} error tags")
    print()

    async with Session() as db:
        # ── KCs ───────────────────────────────────────────────────────────────
        print(f"Seeding knowledge components …")
        kc_inserted, kc_updated = await seed_kcs(db, kcs)
        print(f"  ✓ {kc_inserted} inserted, ~ {kc_updated} updated")

        # ── Errors ────────────────────────────────────────────────────────────
        print(f"\nSeeding error catalog …")
        err_inserted, err_skipped = await seed_errors(db, errors)
        print(f"  ✓ {err_inserted} inserted, ~ {err_skipped} skipped (existing — descriptions preserved)")

        await db.commit()

    print("\nDone.")


if __name__ == "__main__":
    asyncio.run(main())
