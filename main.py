import os
import json
import re
from contextlib import contextmanager
from decimal import Decimal
from typing import Any, Literal

import psycopg
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from groq import Groq
from pydantic import BaseModel, Field, field_validator


load_dotenv()

app = FastAPI(title="Product Search Agent API")


# ============================================================
# MODELS
# ============================================================

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

    sort_by: Literal[
        "relevance",
        "price",
        "rating",
        "name"
    ] = "relevance"

    sort_order: Literal[
        "asc",
        "desc"
    ] = "desc"

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


# ============================================================
# DATABASE CONFIG
# ============================================================

def get_database_url() -> str:
    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        raise HTTPException(
            status_code=500,
            detail=(
                "DATABASE_URL is not set. "
                "Add your Supabase Postgres connection string to .env."
            ),
        )

    return database_url


@contextmanager
def get_connection():
    with psycopg.connect(
        get_database_url(),
        connect_timeout=10
    ) as connection:
        yield connection


# ============================================================
# GROQ CONFIG
# ============================================================

def get_groq_api_key() -> str:
    api_key = os.getenv("GROQ_API_KEY")

    if not api_key:
        raise HTTPException(
            status_code=500,
            detail=(
                "GROQ_API_KEY is not set. "
                "Add your Groq API key to .env."
            ),
        )

    return api_key


def get_groq_model() -> str:
    return os.getenv(
        "GROQ_MODEL",
        "openai/gpt-oss-20b"
    )


# ============================================================
# JSON HELPERS
# ============================================================

def json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)

    return value


def parse_json_object(text: str) -> dict[str, Any]:
    match = re.search(
        r"\{.*\}",
        text,
        flags=re.DOTALL
    )

    if not match:
        raise ValueError(
            "Groq did not return a JSON object."
        )

    return json.loads(match.group(0))


# ============================================================
# CATEGORY FUNCTIONS
# ============================================================

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
                CategoryOption(
                    name=row[0],
                    code=row[1]
                )
                for row in cursor.fetchall()
            ]


def format_category_options(
    categories: list[CategoryOption]
) -> str:

    return "\n".join(
        f"- {category.name}"
        + (
            f" ({category.code})"
            if category.code
            else ""
        )
        for category in categories
    )


# ============================================================
# GROQ LLM CALL
# ============================================================

def call_groq(prompt: str) -> dict[str, Any]:

    api_key = get_groq_api_key()

    client = Groq(
        api_key=api_key
    )

    try:

        completion = client.chat.completions.create(
            model=get_groq_model(),

            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a product database search planner. "
                        "Convert the user's request into a search "
                        "query plan. "
                        "Return ONLY a valid JSON object."
                    ),
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ],

            temperature=0,

            response_format={
                "type": "json_object"
            },
        )

        response_text = (
            completion
            .choices[0]
            .message
            .content
        )

        if not response_text:
            raise ValueError(
                "Groq returned an empty response."
            )

        return parse_json_object(
            response_text
        )

    except Exception as error:

        raise HTTPException(
            status_code=503,
            detail=f"Could not reach Groq: {error}",
        ) from error


# ============================================================
# NORMALIZATION
# ============================================================

def normalize_phrase(text: str) -> str:
    return re.sub(
        r"[^a-z0-9.]+",
        " ",
        text.lower()
    ).strip()


def singularize(value: str) -> str:
    return (
        value[:-1]
        if value.endswith("s")
        else value
    )


def normalize_category(
    requested_category: str | None,
    user_request: str,
    categories: list[CategoryOption],
) -> str | None:

    category_lookup: dict[str, str] = {}

    for category in categories:

        category_lookup[
            normalize_phrase(category.name)
        ] = category.name

        category_lookup[
            singularize(
                normalize_phrase(category.name)
            )
        ] = category.name

        if category.code:

            category_lookup[
                normalize_phrase(category.code)
            ] = category.name

    # Try the category returned by Groq
    if requested_category:

        normalized = normalize_phrase(
            requested_category
        )

        if normalized in category_lookup:
            return category_lookup[normalized]

    # Try detecting a category directly from the user request
    normalized_request = normalize_phrase(
        user_request
    )

    request_words = set(
        normalized_request.split()
    )

    for key, category_name in category_lookup.items():

        if key and (
            key in normalized_request
            or singularize(key) in request_words
        ):
            return category_name

    return requested_category


# ============================================================
# LANGUAGE GUARDRAILS
# ============================================================

def apply_generic_language_hints(
    plan: QueryPlan,
    user_request: str
) -> QueryPlan:

    normalized = normalize_phrase(
        user_request
    )

    # --------------------------------------------------------
    # Rating ABOVE
    # --------------------------------------------------------

    rating_match = re.search(
        r"rating\s+"
        r"(above|over|greater than|at least|min(?:imum)?|>=)"
        r"\s+(\d+(?:\.\d+)?)",
        normalized,
    )

    if rating_match:

        plan.min_rating = float(
            rating_match.group(2)
        )

        if plan.max_rating == plan.min_rating:
            plan.max_rating = None

    # --------------------------------------------------------
    # Rating BELOW
    # --------------------------------------------------------

    rating_match = re.search(
        r"rating\s+"
        r"(under|below|less than|at most|max(?:imum)?|<=)"
        r"\s+(\d+(?:\.\d+)?)",
        normalized,
    )

    if rating_match:

        plan.max_rating = float(
            rating_match.group(2)
        )

        if plan.min_rating == plan.max_rating:
            plan.min_rating = None

    # --------------------------------------------------------
    # Price BELOW
    # --------------------------------------------------------

    price_match = re.search(
        r"(under|below|less than|cheaper than|at most|up to|<=)"
        r"\s+\$?(\d+(?:\.\d+)?)",
        normalized,
    )

    if price_match:

        plan.max_price = float(
            price_match.group(2)
        )

        if plan.min_price == plan.max_price:
            plan.min_price = None

    # --------------------------------------------------------
    # Price ABOVE
    # --------------------------------------------------------

    price_match = re.search(
        r"(above|over|greater than|at least|min(?:imum)?|>=)"
        r"\s+\$?(\d+(?:\.\d+)?)",
        normalized,
    )

    if price_match:

        # Make sure we're not interpreting
        # "rating above X" as a price.
        if "rating" not in normalized[
            max(0, price_match.start() - 12):
            price_match.start()
        ]:

            plan.min_price = float(
                price_match.group(2)
            )

            if plan.max_price == plan.min_price:
                plan.max_price = None

    # --------------------------------------------------------
    # Rating sorting
    # --------------------------------------------------------

    if (
        "rating" in normalized
        and plan.sort_by == "rating"
    ):
        plan.sort_order = "desc"

    # --------------------------------------------------------
    # Availability
    # --------------------------------------------------------

    if not re.search(
        r"unavailable|out of stock|out-of-stock|not available",
        normalized,
    ):
        plan.available_only = True

    return plan


# ============================================================
# PROMPT BUILDER
# ============================================================

def build_query_prompt(
    user_request: str,
    categories: list[CategoryOption],
    use_guardrails: bool,
) -> str:

    guardrail_rules = """
- If the user says under, below, less than, cheaper than, at most, or up to a price, set max_price.
- If the user says above, over, greater than, or at least a rating, set min_rating.
- Do not use min_price for "under a price".
- Do not use max_rating for "rating above".
""".strip()

    prompt = f"""
You are a product database search planner.

Convert the user's request into a JSON search plan.

Return ONLY JSON.
Do not include markdown.
Do not include explanations.

Database fields:

- product name
- brand
- category name or category code
- price
- rating
- availability

Valid categories loaded from the database:

{format_category_options(categories)}

Allowed JSON keys:

name,
category,
brand,
min_rating,
max_rating,
min_price,
max_price,
available_only,
sort_by,
sort_order

Rules:

- Use null when a field is not requested.
- category must be null or exactly one of the valid category names above.

{guardrail_rules if use_guardrails else ""}

- available_only should be true unless the user explicitly asks for unavailable or out-of-stock items.
- sort_by must be one of:
  relevance,
  price,
  rating,
  name

- sort_order must be one of:
  asc,
  desc

Examples:

User:
"show me Apple phones under 1500"

JSON:
{{
  "name": "iPhone",
  "category": null,
  "brand": "Apple",
  "min_rating": null,
  "max_rating": null,
  "min_price": null,
  "max_price": 1500,
  "available_only": true,
  "sort_by": "relevance",
  "sort_order": "desc"
}}

User:
"find products rated above 4"

JSON:
{{
  "name": null,
  "category": null,
  "brand": null,
  "min_rating": 4,
  "max_rating": null,
  "min_price": null,
  "max_price": null,
  "available_only": true,
  "sort_by": "rating",
  "sort_order": "desc"
}}

User request:

{user_request}
""".strip()

    return re.sub(
        r"\n{3,}",
        "\n\n",
        prompt
    )


# ============================================================
# QUERY PLAN
# ============================================================

def build_query_plan(
    user_request: str,
    use_guardrails: bool = True
) -> QueryPlan:

    categories = get_category_options()

    prompt = build_query_prompt(
        user_request,
        categories,
        use_guardrails
    )

    raw_plan = call_groq(prompt)

    plan = QueryPlan.model_validate(
        raw_plan
    )

    plan.category = normalize_category(
        plan.category,
        user_request,
        categories
    )

    if use_guardrails:

        plan = apply_generic_language_hints(
            plan,
            user_request
        )

    return plan


# ============================================================
# PRODUCT SEARCH
# ============================================================

def search_products(
    plan: QueryPlan,
    limit: int
) -> list[dict[str, Any]]:

    where = []
    params: list[Any] = []

    # --------------------------------------------------------
    # Name
    # --------------------------------------------------------

    if plan.name:

        where.append(
            """
            (
                p.name ilike %s
                or p.description ilike %s
                or p.sku ilike %s
            )
            """
        )

        pattern = f"%{plan.name}%"

        params.extend([
            pattern,
            pattern,
            pattern
        ])

    # --------------------------------------------------------
    # Category
    # --------------------------------------------------------

    if plan.category:

        where.append(
            """
            (
                c.name ilike %s
                or c.code ilike %s
            )
            """
        )

        pattern = f"%{plan.category}%"

        params.extend([
            pattern,
            pattern
        ])

    # --------------------------------------------------------
    # Brand
    # --------------------------------------------------------

    if plan.brand:

        where.append(
            "p.brand ilike %s"
        )

        params.append(
            f"%{plan.brand}%"
        )

    # --------------------------------------------------------
    # Minimum rating
    # --------------------------------------------------------

    if plan.min_rating is not None:

        where.append(
            "p.rating >= %s"
        )

        params.append(
            plan.min_rating
        )

    # --------------------------------------------------------
    # Maximum rating
    # --------------------------------------------------------

    if plan.max_rating is not None:

        where.append(
            "p.rating <= %s"
        )

        params.append(
            plan.max_rating
        )

    # --------------------------------------------------------
    # Minimum price
    # --------------------------------------------------------

    if plan.min_price is not None:

        where.append(
            "p.price >= %s"
        )

        params.append(
            plan.min_price
        )

    # --------------------------------------------------------
    # Maximum price
    # --------------------------------------------------------

    if plan.max_price is not None:

        where.append(
            "p.price <= %s"
        )

        params.append(
            plan.max_price
        )

    # --------------------------------------------------------
    # Availability
    # --------------------------------------------------------

    if plan.available_only:

        where.append(
            "p.is_available = true"
        )

    # --------------------------------------------------------
    # Sorting
    # --------------------------------------------------------

    sort_column = {
        "relevance": "p.rating",
        "price": "p.price",
        "rating": "p.rating",
        "name": "p.name",
    }[plan.sort_by]

    sort_order = (
        "asc"
        if plan.sort_order == "asc"
        else "desc"
    )

    # --------------------------------------------------------
    # WHERE
    # --------------------------------------------------------

    where_sql = (
        f"where {' and '.join(where)}"
        if where
        else ""
    )

    # --------------------------------------------------------
    # SQL QUERY
    # --------------------------------------------------------

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

        left join public.categories c
            on c.id = p.category_id

        {where_sql}

        order by
            {sort_column} {sort_order},
            p.id asc

        limit %s
    """

    params.append(limit)

    # --------------------------------------------------------
    # EXECUTE
    # --------------------------------------------------------

    with get_connection() as connection:

        with connection.cursor() as cursor:

            cursor.execute(
                query,
                params
            )

            rows = cursor.fetchall()

            columns = [
                column.name
                for column in cursor.description
            ]

    # --------------------------------------------------------
    # FORMAT RESULTS
    # --------------------------------------------------------

    return [
        {
            column: json_safe(value)
            for column, value in zip(
                columns,
                row
            )
        }
        for row in rows
    ]


# ============================================================
# ROOT
# ============================================================

@app.get("/")
def root():

    return {
        "message": "FastAPI backend is running",

        "db_test": (
            "Open /db-test to test "
            "the Supabase database connection."
        ),

        "groq_test": (
            "Open /groq-test to test "
            "the Groq connection."
        ),

        "agent": (
            "POST /agent or /agent-guarded "
            "for safer results."
        ),

        "agent_raw": (
            "POST /agent-raw to see the "
            "Groq-only plan without "
            "language guardrails."
        ),
    }


# ============================================================
# DATABASE TEST
# ============================================================

@app.get("/db-test")
def db_test():

    try:

        with get_connection() as connection:

            with connection.cursor() as cursor:

                cursor.execute(
                    "select 1 as ok"
                )

                row = cursor.fetchone()

    except psycopg.Error as error:

        raise HTTPException(
            status_code=500,
            detail=f"Database connection failed: {error}",
        ) from error

    return {
        "connected": True,
        "result": row[0]
    }


# ============================================================
# GROQ TEST
# ============================================================

@app.get("/groq-test")
def groq_test():

    plan = build_query_plan(
        "show me Apple phones under 1500"
    )

    return {
        "connected": True,
        "model": get_groq_model(),
        "plan": plan.model_dump()
    }


# ============================================================
# AGENT SEARCH
# ============================================================

def run_agent_search(
    agent_request: AgentRequest,
    use_guardrails: bool
):

    try:

        plan = build_query_plan(
            agent_request.request,
            use_guardrails=use_guardrails
        )

        results = search_products(
            plan,
            agent_request.limit
        )

    except psycopg.Error as error:

        raise HTTPException(
            status_code=500,
            detail=f"Database query failed: {error}"
        ) from error

    except (json.JSONDecodeError, ValueError) as error:

        raise HTTPException(
            status_code=502,
            detail=f"Groq returned an invalid plan: {error}"
        ) from error

    return {
        "request": agent_request.request,

        "mode": (
            "guarded"
            if use_guardrails
            else "raw"
        ),

        "plan": plan.model_dump(),

        "count": len(results),

        "results": results,
    }


# ============================================================
# API ENDPOINTS
# ============================================================

@app.post("/agent")
def agent_search(
    agent_request: AgentRequest
):

    return run_agent_search(
        agent_request,
        use_guardrails=True
    )


@app.post("/agent-guarded")
def agent_search_guarded(
    agent_request: AgentRequest
):

    return run_agent_search(
        agent_request,
        use_guardrails=True
    )


@app.post("/agent-raw")
def agent_search_raw(
    agent_request: AgentRequest
):

    return run_agent_search(
        agent_request,
        use_guardrails=False
    )