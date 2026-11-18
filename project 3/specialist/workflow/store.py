"""Local durable case storage. Each command is serialized across server processes."""
from contextlib import contextmanager
import json
import sqlite3
from pathlib import Path


class CaseStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS specialist_cases
                        (id TEXT PRIMARY KEY, owner TEXT NOT NULL, state TEXT NOT NULL)""")

    @contextmanager
    def _connect(self):
        db = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        try:
            yield db
        finally:
            db.close()

    def insert(self, state):
        with self._connect() as db:
            db.execute("INSERT INTO specialist_cases VALUES (?, ?, ?)",
                       (state["case_id"], state["customer_id"], json.dumps(state)))

    def get(self, case_id, customer_id):
        with self._connect() as db:
            row = db.execute("SELECT state FROM specialist_cases WHERE id=? AND owner=?",
                             (case_id, customer_id)).fetchone()
        if row is None:
            raise LookupError("Case not found")
        return json.loads(row[0])

    def recent(self, customer_id=None):
        with self._connect() as db:
            if customer_id is None:
                rows = db.execute("SELECT state FROM specialist_cases ORDER BY rowid DESC LIMIT 25").fetchall()
            else:
                rows = db.execute("SELECT state FROM specialist_cases WHERE owner=? ORDER BY rowid DESC LIMIT 25",
                                  (customer_id,)).fetchall()
        return [json.loads(row[0]) for row in rows]

    def owner_for_review(self, case_id):
        with self._connect() as db:
            row = db.execute("SELECT owner FROM specialist_cases WHERE id=?", (case_id,)).fetchone()
        if row is None:
            raise LookupError("Case not found")
        return row[0]

    def clear(self):
        with self._connect() as db:
            db.execute("DELETE FROM specialist_cases")

    @contextmanager
    def update(self, case_id, customer_id):
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT state FROM specialist_cases WHERE id=? AND owner=?",
                             (case_id, customer_id)).fetchone()
            if row is None:
                raise LookupError("Case not found")
            state = json.loads(row[0])
            yield state
            db.execute("UPDATE specialist_cases SET state=? WHERE id=? AND owner=?",
                       (json.dumps(state), case_id, customer_id))
            db.commit()
