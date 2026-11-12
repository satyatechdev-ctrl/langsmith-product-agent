"""Tests for schema setup, SQL restrictions, and product queries."""

from __future__ import annotations

import json
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import DBAPIError

from product_agent.database import Base, Product, ProductDatabase, ProductQueryError
from product_agent.init_db import initialize_database


@pytest.fixture
def database(tmp_path):
    database_path = tmp_path / "products.db"
    database_url = f"sqlite:///{database_path.as_posix()}"
    assert initialize_database(database_url, seed=True) == 7
    return ProductDatabase(database_url)


def test_average_price_for_inventory_over_100(database):
    result = json.loads(
        database.query("SELECT AVG(price) AS average_price FROM products WHERE inventory > 100")
    )

    assert result["row_count"] == 1
    assert Decimal(str(result["rows"][0]["average_price"])) == Decimal("21.546")


def test_durable_products_under_50(database):
    result = json.loads(
        database.query(
            "SELECT name, description FROM products "
            "WHERE price < 50 AND LOWER(description) LIKE '%durable%' ORDER BY name"
        )
    )

    assert [row["name"] for row in result["rows"]] == [
        "Ceramic Mug",
        "Heavy-Duty Storage Bin",
        "Stainless Water Bottle",
        "Waterproof Hiking Backpack",
    ]


@pytest.mark.parametrize(
    "query",
    [
        "DELETE FROM products",
        "UPDATE products SET price = 0",
        "SELECT * FROM sqlite_master",
        "SELECT name FROM products; SELECT price FROM products",
        "SELECT secret FROM products",
        "SELECT pg_sleep(60) FROM products",
        "SELECT * INTO copied_products FROM products",
        "SELECT name FROM products FOR UPDATE",
    ],
)
def test_rejects_unsafe_queries(database, query):
    with pytest.raises(ProductQueryError):
        database.query(query)


def test_sqlite_connection_is_query_only(database):
    with pytest.raises(DBAPIError):
        with database.engine.begin() as connection:
            connection.execute(
                Product.__table__.update().values(price=Decimal("0.00"))
            )


def test_result_count_is_capped(tmp_path):
    database_path = tmp_path / "many-products.db"
    database_url = f"sqlite:///{database_path.as_posix()}"
    engine = create_engine(database_url)
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(
            Product.__table__.insert(),
            [
                {
                    "name": f"Product {index}",
                    "price": Decimal("1.00"),
                    "description": "Sample",
                    "inventory": index,
                }
                for index in range(5)
            ],
        )
    engine.dispose()

    database = ProductDatabase(database_url, max_rows=2)
    result = json.loads(database.query("SELECT name FROM products ORDER BY id"))

    assert result["row_count"] == 2
    assert len(result["rows"]) == 2


def test_requested_limit_is_preserved_or_capped(database):
    one_row = json.loads(database.query("SELECT name FROM products LIMIT 1"))
    capped = json.loads(database.query("SELECT name FROM products LIMIT 500"))

    assert one_row["row_count"] == 1
    assert capped["row_count"] == 7
