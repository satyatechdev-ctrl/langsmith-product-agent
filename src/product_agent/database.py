"""SQLAlchemy schema and guarded, read-only product queries."""

from __future__ import annotations

import json
import os
import sqlite3
from decimal import Decimal
from functools import lru_cache
from typing import Any

import sqlglot
from sqlalchemy import CheckConstraint, Integer, Numeric, String, Text, create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlglot import exp
from sqlglot.errors import ParseError

DEFAULT_DATABASE_URL = "sqlite:///./data/products.db"
MAX_QUERY_LENGTH = 4_000
DEFAULT_MAX_ROWS = 100
DEFAULT_STATEMENT_TIMEOUT_MS = 5_000
PRODUCT_COLUMNS = frozenset({"id", "name", "price", "description", "inventory", "*"})
ALLOWED_FUNCTIONS = frozenset(
    {
        "ABS",
        "AVG",
        "COALESCE",
        "COUNT",
        "LENGTH",
        "LOWER",
        "MAX",
        "MIN",
        "NULLIF",
        "REPLACE",
        "ROUND",
        "SUBSTR",
        "SUM",
        "TRIM",
        "UPPER",
    }
)


class Base(DeclarativeBase):
    """Declarative SQLAlchemy base."""


class Product(Base):
    """Product record schema."""

    __tablename__ = "products"
    __table_args__ = (
        CheckConstraint("price >= 0", name="ck_products_price_nonnegative"),
        CheckConstraint("inventory >= 0", name="ck_products_inventory_nonnegative"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    inventory: Mapped[int] = mapped_column(Integer, nullable=False)


class ProductQueryError(ValueError):
    """Raised when a product query is invalid or cannot be executed."""


def _enable_sqlite_query_only(dbapi_connection: sqlite3.Connection, _: object) -> None:
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA query_only = ON")
    finally:
        cursor.close()


class ProductDatabase:
    """Execute validated, read-only queries against the products table."""

    def __init__(
        self,
        database_url: str | None = None,
        *,
        max_rows: int = DEFAULT_MAX_ROWS,
        statement_timeout_ms: int = DEFAULT_STATEMENT_TIMEOUT_MS,
    ) -> None:
        if max_rows < 1:
            raise ValueError("max_rows must be greater than zero")
        if statement_timeout_ms < 1:
            raise ValueError("statement_timeout_ms must be greater than zero")

        self.engine: Engine = create_engine(
            database_url or os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL),
            pool_pre_ping=True,
        )
        dialect = self.engine.dialect.name
        if dialect not in {"sqlite", "postgresql"}:
            self.engine.dispose()
            raise ValueError("DATABASE_URL must use SQLite or PostgreSQL")

        self._sql_dialect = "postgres" if dialect == "postgresql" else "sqlite"
        self._is_postgresql = dialect == "postgresql"
        self._max_rows = max_rows
        self._statement_timeout_ms = statement_timeout_ms

        if dialect == "sqlite":
            event.listen(self.engine, "connect", _enable_sqlite_query_only)

    def _validated_sql(self, query: str) -> str:
        if not query.strip():
            raise ProductQueryError("A SQL SELECT query is required.")
        if len(query) > MAX_QUERY_LENGTH:
            raise ProductQueryError(f"SQL query exceeds the {MAX_QUERY_LENGTH}-character limit.")

        try:
            statements = sqlglot.parse(query, read=self._sql_dialect)
        except ParseError as error:
            raise ProductQueryError("The SQL query could not be parsed.") from error

        if len(statements) != 1 or statements[0] is None:
            raise ProductQueryError("Exactly one SQL statement is allowed.")

        statement = statements[0]
        if not isinstance(statement, exp.Select):
            raise ProductQueryError("Only SELECT queries are allowed.")
        if statement.args.get("into") is not None or statement.args.get("locks"):
            raise ProductQueryError("SELECT INTO and row-locking queries are not allowed.")

        tables = list(statement.find_all(exp.Table))
        if not tables or any(
            table.name.casefold() != "products" or table.db or table.catalog for table in tables
        ):
            raise ProductQueryError("Queries may read only from the products table.")

        if any(
            column.name.casefold() not in PRODUCT_COLUMNS
            for column in statement.find_all(exp.Column)
        ):
            raise ProductQueryError("The query references a column outside the products schema.")

        if any(
            not isinstance(function, (exp.Binary, exp.Unary))
            and function.sql_name().upper() not in ALLOWED_FUNCTIONS
            for function in statement.find_all(exp.Func)
        ):
            raise ProductQueryError("The query uses a function that is not allowed.")

        limit = statement.args.get("limit")
        if limit is None:
            statement = statement.limit(self._max_rows)
        else:
            limit_value = limit.expression
            if not isinstance(limit_value, exp.Literal) or not limit_value.is_number:
                raise ProductQueryError("LIMIT must be a non-negative integer literal.")
            if int(limit_value.this) > self._max_rows:
                statement = statement.limit(self._max_rows)

        return statement.sql(dialect=self._sql_dialect)

    def query(self, query: str) -> str:
        """Return a JSON object containing at most ``max_rows`` product query results."""
        safe_sql = self._validated_sql(query)
        try:
            with self.engine.connect() as connection, connection.begin():
                if self._is_postgresql:
                    connection.exec_driver_sql("SET TRANSACTION READ ONLY")
                    connection.exec_driver_sql(
                        f"SET LOCAL statement_timeout = '{self._statement_timeout_ms}ms'"
                    )

                result = connection.execute(text(safe_sql))
                rows = [
                    {
                        key: str(value) if isinstance(value, Decimal) else value
                        for key, value in row._mapping.items()
                    }
                    for row in result
                ]
        except SQLAlchemyError as error:
            raise ProductQueryError(f"Product query failed: {error}") from error

        return json.dumps(
            {"columns": list(result.keys()), "row_count": len(rows), "rows": rows},
            default=str,
        )


@lru_cache(maxsize=1)
def get_product_database() -> ProductDatabase:
    """Create a database wrapper using the configured connection URL."""
    return ProductDatabase()


def product_seed_rows() -> list[dict[str, Any]]:
    """Return deterministic sample products for local development."""
    return [
        {
            "name": "Waterproof Hiking Backpack",
            "price": Decimal("42.50"),
            "description": "Durable hiking backpack with waterproof lining and reinforced seams.",
            "inventory": 150,
        },
        {
            "name": "Ceramic Mug",
            "price": Decimal("12.99"),
            "description": "Durable ceramic mug suitable for everyday use.",
            "inventory": 250,
        },
        {
            "name": "Wireless Mouse",
            "price": Decimal("29.99"),
            "description": "Compact wireless mouse with adjustable sensitivity.",
            "inventory": 80,
        },
        {
            "name": "Heavy-Duty Storage Bin",
            "price": Decimal("18.75"),
            "description": "Durable storage bin with reinforced handles.",
            "inventory": 320,
        },
        {
            "name": "Premium Desk Chair",
            "price": Decimal("189.00"),
            "description": "Ergonomic desk chair with adjustable lumbar support.",
            "inventory": 35,
        },
        {
            "name": "Stainless Water Bottle",
            "price": Decimal("24.50"),
            "description": "Durable stainless-steel bottle that keeps drinks cold.",
            "inventory": 125,
        },
        {
            "name": "USB-C Cable",
            "price": Decimal("8.99"),
            "description": "Braided USB-C charging cable, 2 meters long.",
            "inventory": 500,
        },
    ]
