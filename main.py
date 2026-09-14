import os
import json
import re
from contextlib import contextmanager
from decimal import Decimal
from typing import Any, Literal
from urllib.error import URLError
from urllib.request import Request, urlopen

import psycopg
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, field_validator


load_dotenv()

app = FastAPI(title="Product Search Agent API")


class AgentRequest(BaseModel):
    request: str = Field(..., min_length=1, examples=["find iPhone by name"])
    limit: int = Field(default=10, ge=1, le=50)


class QueryPlan(BaseModel):
    name: str | None = None
    category: str | None = None
    brand: str | None = None
    min_rating: float | None = None
    max_rating: float | None = None
    min_price: float | None = None
    max_price: float | None = None
    available_only: bool = True
    sort_by: Literal["relevance", "price", "rating", "name"] = "relevance"
    sort_order: Literal["asc", "desc"] = "desc"

    @field_validator("sort_by", mode="before")
    @classmethod
    def default_sort_by(cls, value):
        return "relevance" if value is None else value

    @field_validator("sort_order", mode="before")
    @classmethod
    def default_sort_order(cls, value):
        return "desc" if value is None else value


class CategoryOption(BaseModel):
    name: str
    code: str | None = None


def get_database_url() -> str:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise HTTPException(
            status_code=500,
            detail="DATABASE_URL is not set. Add your Supabase Postgres connection string to .env.",
        )
    return database_url


def get_ollama_url() -> str:
    return os.getenv("OLLAMA_URL", "http://localhost:11434").rstrip("/")


def get_ollama_model() -> str:
    return os.getenv("OLLAMA_MODEL", "llama3.1")


def get_ollama_timeout() -> int:
    return int(os.getenv("OLLAMA_TIMEOUT", "120"))


@contextmanager
def get_connection():
    with psycopg.connect(get_database_url(), connect_timeout=10) as connection:
        yield connection


def json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    return value


def parse_json_object(text: str) -> dict[str, Any]:
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not match:
        raise ValueError("Ollama did not return a JSON object.")
    return json.loads(match.group(0))


def get_category_options() -> list[CategoryOption]:
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                select name, code
                from public.categories
                order by name
                """
            )
            return [
                CategoryOption(name=row[0], code=row[1])
                for row in cursor.fetchall()
            ]


def format_category_options(categories: list[CategoryOption]) -> str:
    return "\n".join(
        f"- {category.name}" + (f" ({category.code})" if category.code else "")
        for category in categories
    )


def call_ollama(prompt: str) -> dict[str, Any]:
    body = json.dumps(
        {
            "model": get_ollama_model(),
            "prompt": prompt,
            "stream": False,
            "format": "json",
        }
    ).encode("utf-8")
    request = Request(
        f"{get_ollama_url()}/api/generate",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urlopen(request, timeout=get_ollama_timeout()) as response:
            ollama_result = json.loads(response.read().decode("utf-8"))
    except (TimeoutError, URLError) as error:
        raise HTTPException(
            status_code=503,
            detail=f"Could not reach Ollama at {get_ollama_url()}: {error}",
        ) from error

    return parse_json_object(ollama_result.get("response", ""))


def normalize_phrase(text: str) -> str:
    return re.sub(r"[^a-z0-9.]+", " ", text.lower()).strip()


def singularize(value: str) -> str:
    return value[:-1] if value.endswith("s") else value


def normalize_category(
    requested_category: str | None,
    user_request: str,
    categories: list[CategoryOption],
) -> str | None:
    category_lookup: dict[str, str] = {}
    for category in categories:
        category_lookup[normalize_phrase(category.name)] = category.name
        category_lookup[singularize(normalize_phrase(category.name))] = category.name
        if category.code:
            category_lookup[normalize_phrase(category.code)] = category.name

    if requested_category:
        normalized = normalize_phrase(requested_category)
        if normalized in category_lookup:
            return category_lookup[normalized]

    normalized_request = normalize_phrase(user_request)
    request_words = set(normalized_request.split())
    for key, category_name in category_lookup.items():
        if key and (key in normalized_request or singularize(key) in request_words):
            return category_name

    return requested_category


def apply_generic_language_hints(plan: QueryPlan, user_request: str) -> QueryPlan:
    normalized = normalize_phrase(user_request)

    rating_match = re.search(
        r"rating\s+(above|over|greater than|at least|min(?:imum)?|>=)\s+(\d+(?:\.\d+)?)",
        normalized,
    )
    if rating_match:
        plan.min_rating = float(rating_match.group(2))
        if plan.max_rating == plan.min_rating:
            plan.max_rating = None

    rating_match = re.search(
        r"rating\s+(under|below|less than|at most|max(?:imum)?|<=)\s+(\d+(?:\.\d+)?)",
        normalized,
    )
    if rating_match:
        plan.max_rating = float(rating_match.group(2))
        if plan.min_rating == plan.max_rating:
            plan.min_rating = None

    price_match = re.search(
        r"(under|below|less than|cheaper than|at most|max(?:imum)?|up to|<=)\s+\$?(\d+(?:\.\d+)?)",
        normalized,
    )
    if price_match:
        plan.max_price = float(price_match.group(2))
        if plan.min_price == plan.max_price:
            plan.min_price = None

    price_match = re.search(
        r"(above|over|greater than|at least|min(?:imum)?|>=)\s+\$?(\d+(?:\.\d+)?)",
        normalized,
    )
    if price_match and "rating" not in normalized[max(0, price_match.start() - 12):price_match.start()]:
        plan.min_price = float(price_match.group(2))
        if plan.max_price == plan.min_price:
            plan.max_price = None

    if "rating" in normalized and plan.sort_by == "rating":
        plan.sort_order = "desc"

    if not re.search(r"unavailable|out of stock|out-of-stock|not available", normalized):
        plan.available_only = True

    return plan


def build_query_plan(user_request: str) -> QueryPlan:
    categories = get_category_options()
    prompt = f"""
You are a product database search planner. Convert the user's request into JSON only.

Database fields:
- product name
- brand
- category name or category code
- price
- rating
- availability

Valid categories, loaded from the database:
{format_category_options(categories)}

Allowed JSON keys:
name, category, brand, min_rating, max_rating, min_price, max_price,
available_only, sort_by, sort_order

Rules:
- Use null when a field is not requested.
- category must be null or exactly one of the valid category names above.
- If the user says under, below, less than, cheaper than, at most, or up to a price, set max_price.
- If the user says above, over, greater than, or at least a rating, set min_rating.
- Do not use min_price for "under a price".
- Do not use max_rating for "rating above".
- available_only should be true unless the user asks for unavailable/out-of-stock items.
- sort_by must be one of: relevance, price, rating, name.
- sort_order must be asc or desc.
- Return only JSON. No markdown.

User request: {user_request}
""".strip()

    raw_plan = call_ollama(prompt)
    plan = QueryPlan.model_validate(raw_plan)
    plan.category = normalize_category(plan.category, user_request, categories)
    return apply_generic_language_hints(plan, user_request)


def search_products(plan: QueryPlan, limit: int) -> list[dict[str, Any]]:
    where = []
    params: list[Any] = []

    if plan.name:
        where.append("(p.name ilike %s or p.description ilike %s or p.sku ilike %s)")
        pattern = f"%{plan.name}%"
        params.extend([pattern, pattern, pattern])
    if plan.category:
        where.append("(c.name ilike %s or c.code ilike %s)")
        pattern = f"%{plan.category}%"
        params.extend([pattern, pattern])
    if plan.brand:
        where.append("p.brand ilike %s")
        params.append(f"%{plan.brand}%")
    if plan.min_rating is not None:
        where.append("p.rating >= %s")
        params.append(plan.min_rating)
    if plan.max_rating is not None:
        where.append("p.rating <= %s")
        params.append(plan.max_rating)
    if plan.min_price is not None:
        where.append("p.price >= %s")
        params.append(plan.min_price)
    if plan.max_price is not None:
        where.append("p.price <= %s")
        params.append(plan.max_price)
    if plan.available_only:
        where.append("p.is_available = true")

    sort_column = {
        "relevance": "p.rating",
        "price": "p.price",
        "rating": "p.rating",
        "name": "p.name",
    }[plan.sort_by]
    sort_order = "asc" if plan.sort_order == "asc" else "desc"
    where_sql = f"where {' and '.join(where)}" if where else ""

    query = f"""
        select
            p.id,
            p.name,
            p.brand,
            p.sku,
            p.price,
            p.discount,
            p.rating,
            p.stock_quantity,
            p.is_available,
            p.description,
            p.image_url,
            p.attributes,
            c.name as category,
            c.code as category_code
        from public.products p
        left join public.categories c on c.id = p.category_id
        {where_sql}
        order by {sort_column} {sort_order}, p.id asc
        limit %s
    """
    params.append(limit)

    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(query, params)
            rows = cursor.fetchall()
            columns = [column.name for column in cursor.description]

    return [
        {column: json_safe(value) for column, value in zip(columns, row)}
        for row in rows
    ]


@app.get("/")
def root():
    return {
        "message": "FastAPI backend is running",
        "db_test": "Open /db-test to test the Supabase database connection.",
        "agent": "POST /agent with JSON like {'request': 'show laptops under 2000 with rating above 4.5'}",
    }


@app.get("/db-test")
def db_test():
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("select 1 as ok")
                row = cursor.fetchone()
    except psycopg.Error as error:
        raise HTTPException(
            status_code=500,
            detail=f"Database connection failed: {error}",
        ) from error

    return {"connected": True, "result": row[0]}


@app.get("/ollama-test")
def ollama_test():
    plan = build_query_plan("show me Apple phones under 1500")
    return {"connected": True, "model": get_ollama_model(), "plan": plan.model_dump()}


@app.post("/agent")
def agent_search(agent_request: AgentRequest):
    try:
        plan = build_query_plan(agent_request.request)
        results = search_products(plan, agent_request.limit)
    except psycopg.Error as error:
        raise HTTPException(status_code=500, detail=f"Database query failed: {error}") from error
    except (json.JSONDecodeError, ValueError) as error:
        raise HTTPException(status_code=502, detail=f"Ollama returned an invalid plan: {error}") from error

    return {
        "request": agent_request.request,
        "plan": plan.model_dump(),
        "count": len(results),
        "results": results,
    }
