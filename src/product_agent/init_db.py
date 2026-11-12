"""Explicit database schema initializer and optional local sample-data loader."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from product_agent.database import DEFAULT_DATABASE_URL, Base, Product, product_seed_rows


def initialize_database(database_url: str, *, seed: bool = False) -> int:
    """Create missing tables and optionally insert samples into an empty table."""
    engine = create_engine(database_url, pool_pre_ping=True)
    try:
        if engine.dialect.name == "sqlite" and engine.url.database not in {None, ":memory:"}:
            Path(engine.url.database).resolve().parent.mkdir(parents=True, exist_ok=True)

        Base.metadata.create_all(engine)
        if not seed:
            return 0

        with Session(engine) as session:
            if session.scalar(select(func.count()).select_from(Product)):
                return 0
            session.add_all(Product(**row) for row in product_seed_rows())
            session.commit()
        return len(product_seed_rows())
    finally:
        engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--seed",
        action="store_true",
        help="Insert the sample products only if the products table is empty.",
    )
    args = parser.parse_args()
    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
    database_url = os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)
    inserted = initialize_database(database_url, seed=args.seed)
    print(f"Database schema is ready. Sample rows inserted: {inserted}.")


if __name__ == "__main__":
    main()
