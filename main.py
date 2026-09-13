import os
from contextlib import contextmanager

import psycopg
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException


load_dotenv()

app = FastAPI(title="Supabase Connection Test API")


def get_database_url() -> str:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise HTTPException(
            status_code=500,
            detail="DATABASE_URL is not set. Add your Supabase Postgres connection string to .env.",
        )
    return database_url


@contextmanager
def get_connection():
    with psycopg.connect(get_database_url(), connect_timeout=10) as connection:
        yield connection


@app.get("/")
def root():
    return {
        "message": "FastAPI backend is running",
        "db_test": "Open /db-test to test the Supabase database connection.",
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
