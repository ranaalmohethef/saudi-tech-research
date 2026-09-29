"""
Checks the connection to PostgreSQL before running the website.

Run:  python test_connection.py
"""
import os

import psycopg2
from dotenv import load_dotenv

load_dotenv()

missing = [k for k in ("PGHOST", "PGUSER", "PGPASSWORD") if not os.environ.get(k)]
if missing:
    raise SystemExit(f"Missing in .env: {', '.join(missing)}")

print("Connecting to", os.environ["PGHOST"], "...")
try:
    conn = psycopg2.connect(
        host=os.environ["PGHOST"],
        port=os.environ.get("PGPORT", "5432"),
        dbname=os.environ.get("PGDATABASE", "research_hub"),
        user=os.environ["PGUSER"],
        password=os.environ["PGPASSWORD"],
        sslmode="require",
        connect_timeout=10,
    )
except psycopg2.OperationalError as err:
    msg = str(err)
    print("\nFAILED:", msg.strip())
    if "timeout" in msg or "timed out" in msg:
        print("-> Add your IP in Azure: PostgreSQL server > Networking > Add current client IP address")
        print("-> Or the server is stopped: click Start in Azure Portal")
    elif "password authentication failed" in msg:
        print("-> Wrong user or password in .env")
    elif "could not translate host name" in msg:
        print("-> Wrong PGHOST in .env, or no internet")
    raise SystemExit(1)

with conn, conn.cursor() as cur:
    cur.execute("SELECT university, COUNT(*) FROM research.final_dataset GROUP BY 1 ORDER BY 1")
    rows = cur.fetchall()
conn.close()

print("\nCONNECTED. research.final_dataset:")
for uni, n in rows:
    print(f"  {uni:<8} {n:>6}")
print(f"  {'Total':<8} {sum(n for _, n in rows):>6}")
