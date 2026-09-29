"""
Rebuilds static/data.js, the saved copy the page uses when server.py is not running.

From the database (recommended, copies everything the live page shows):
    python make_data_js.py --db

From a CSV file (papers only, no funnel or quality numbers):
    python make_data_js.py path/to/final.csv
"""
import json
import sys

COLUMNS = ["research_id", "university", "publication_year", "title", "authors",
           "journal", "doi", "url", "source", "abstract"]


def from_database():
    # Same connection and queries as the live site
    from server import COLUMNS as SQL_COLUMNS, TABLE, query, read_meta

    rows = query(f"SELECT {SQL_COLUMNS} FROM {TABLE} ORDER BY publication_year DESC, title")
    try:
        stats = query("SELECT university, cleaned, validated FROM research.source_stats ORDER BY university")
    except Exception as err:
        print("source_stats not read:", err)
        stats = []
    meta = read_meta()
    return [dict(r) for r in rows], [dict(r) for r in stats], meta


def from_csv(path):
    import pandas as pd

    df = pd.read_csv(path)[COLUMNS]
    df["publication_year"] = df["publication_year"].astype(int)
    return json.loads(df.to_json(orient="records", force_ascii=False)), [], None


def dump(value):
    return json.dumps(value, ensure_ascii=False, default=str).replace("</", "<\\/")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--db":
        rows, stats, meta = from_database()
        origin = "PostgreSQL"
    else:
        path = sys.argv[1] if len(sys.argv) > 1 else "final.csv"
        rows, stats, meta = from_csv(path)
        origin = path

    with open("static/data.js", "w", encoding="utf-8") as f:
        f.write(f"// Saved copy from {origin}. Used only when server.py is not running.\n")
        f.write("window.SAVED_ROWS = " + dump(rows) + ";\n")
        f.write("window.SAVED_STATS = " + dump(stats) + ";\n")
        f.write("window.SAVED_META = " + dump(meta) + ";\n")

    print(f"static/data.js written: {len(rows)} papers, {len(stats)} universities in stats")
