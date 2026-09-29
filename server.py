"""
Saudi Tech Research Hub - small server between the web page and PostgreSQL.

Run:   python server.py
Open:  http://localhost:5000
"""
import os

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv
from flask import Flask, jsonify, request, send_from_directory

load_dotenv()  # reads the .env file (database password)

# static_url_path="" lets index.html load style.css, app.js ... directly
app = Flask(__name__, static_folder="static", static_url_path="")

TABLE = "research.final_dataset"

COLUMNS = """research_id, university, title, authors, publication_year,
             journal, doi, url, source, abstract"""


def query(sql, params=None):
    """Run a SELECT on PostgreSQL and return a list of dicts."""
    conn = psycopg2.connect(
        host=os.environ["PGHOST"],
        port=os.environ.get("PGPORT", "5432"),
        dbname=os.environ.get("PGDATABASE", "research_hub"),
        user=os.environ["PGUSER"],
        password=os.environ["PGPASSWORD"],
        sslmode="require",
        connect_timeout=10,
    )
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params or [])
            return cur.fetchall()
    finally:
        conn.close()


# ---------- the web page ----------
@app.route("/")
def home():
    return send_from_directory("static", "index.html")


# ---------- connection check ----------
@app.route("/api/health")
def health():
    """Open http://localhost:5000/api/health to check the database connection."""
    try:
        rows = query(f"SELECT university, COUNT(*) AS papers FROM {TABLE} GROUP BY 1 ORDER BY 1")
        return jsonify({"database": "connected", "table": TABLE, "papers": rows})
    except Exception as err:
        return jsonify({"database": "not connected", "error": str(err)}), 503


# ---------- data used by the page ----------
@app.route("/api/papers/all")
def all_papers():
    """Every paper in the final dataset. The page draws all charts from this."""
    try:
        return jsonify(query(f"SELECT {COLUMNS} FROM {TABLE} ORDER BY publication_year DESC, title"))
    except Exception as err:
        print("DATABASE ERROR:", err)          # shows in the VS Code terminal
        return jsonify({"error": str(err)}), 503


# ---------- pipeline numbers per university ----------
@app.route("/api/stats")
def stats():
    """Cleaned and validated counts per university, from research.source_stats."""
    try:
        return jsonify(query(
            "SELECT university, cleaned, validated, updated_at FROM research.source_stats ORDER BY university"
        ))
    except Exception as err:
        print("STATS ERROR:", err)
        return jsonify({"error": str(err)}), 503


# ---------- last update + last quality check ----------
def read_meta():
    """When the data was last loaded and the result of the last quality check.
    Used by the page and by make_data_js.py --db."""
    meta = {"last_loaded": None, "stats_updated": None, "quality": None}

    row = query(f"SELECT MAX(loaded_at) AS t FROM {TABLE}")[0]
    meta["last_loaded"] = row["t"].isoformat() if row["t"] else None

    try:
        row = query("SELECT MAX(updated_at) AS t FROM research.source_stats")[0]
        meta["stats_updated"] = row["t"].isoformat() if row["t"] else None
    except Exception:
        pass

    try:
        rows = query(
            "SELECT checked_at, total_rows, passed, details "
            "FROM research.quality_checks ORDER BY checked_at DESC LIMIT 1"
        )
        if rows:
            r = rows[0]
            checks = (r["details"] or {}).get("checks", [])
            meta["quality"] = {
                "checked_at": r["checked_at"].isoformat(),
                "total_rows": r["total_rows"],
                "passed": r["passed"],
                "checks_total": len(checks),
                "checks_passed": sum(1 for c in checks if c.get("passed")),
            }
    except Exception:
        pass   # table not created yet: the page shows "not run yet"

    return meta


@app.route("/api/meta")
def meta():
    try:
        return jsonify(read_meta())
    except Exception as err:
        print("META ERROR:", err)
        return jsonify({"error": str(err)}), 503


# ---------- extra endpoints (not used by the page yet) ----------
@app.route("/api/papers")
def papers():
    """Filtered papers:  /api/papers?university=KSU&year=2025&q=blockchain&limit=20&offset=0"""
    where, params = [], []

    if request.args.get("university"):
        where.append("university = %s")
        params.append(request.args["university"])

    year = request.args.get("year", type=int)
    if year:
        where.append("publication_year = %s")
        params.append(year)

    q = request.args.get("q")
    if q:
        where.append("(title ILIKE %s OR authors ILIKE %s OR journal ILIKE %s)")
        params += [f"%{q}%"] * 3

    where_sql = ("WHERE " + " AND ".join(where)) if where else ""
    limit = min(request.args.get("limit", 20, type=int), 200)
    offset = request.args.get("offset", 0, type=int)

    total = query(f"SELECT COUNT(*) AS n FROM {TABLE} {where_sql}", params)[0]["n"]
    rows = query(
        f"SELECT {COLUMNS} FROM {TABLE} {where_sql} "
        f"ORDER BY publication_year DESC, title LIMIT %s OFFSET %s",
        params + [limit, offset],
    )
    return jsonify({"total": total, "rows": rows})


@app.route("/api/summary/universities")
def by_university():
    """Number of papers per university."""
    return jsonify(query(
        f"SELECT university, COUNT(*) AS papers FROM {TABLE} GROUP BY university ORDER BY papers DESC"
    ))


@app.route("/api/summary/years")
def by_year():
    """Number of papers per university per year."""
    return jsonify(query(
        f"SELECT publication_year AS year, university, COUNT(*) AS papers "
        f"FROM {TABLE} GROUP BY 1, 2 ORDER BY 1, 2"
    ))


if __name__ == "__main__":
    missing = [k for k in ("PGHOST", "PGUSER", "PGPASSWORD") if not os.environ.get(k)]
    if missing:
        print("Missing in .env:", ", ".join(missing))
        print("Copy .env.example to .env and fill in the password.")
    app.run(debug=True, port=5000)
