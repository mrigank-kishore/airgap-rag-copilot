import sqlite3
from pathlib import Path

DB = Path('storage/ingestion/ingestion.db')
if not DB.exists():
    print('Ingestion DB not found at', DB)
    raise SystemExit(1)

con = sqlite3.connect(DB)
con.row_factory = sqlite3.Row
cur = con.execute("SELECT parent_id, source_path, heading, substr(text,1,800) as preview, length(text) as length FROM parent_documents ORDER BY source_path, parent_id LIMIT 200")
rows = cur.fetchall()
if not rows:
    print('No parent_documents rows found')
else:
    for r in rows:
        print('---')
        print('parent_id:', r['parent_id'])
        print('source_path:', r['source_path'])
        print('heading:', r['heading'])
        print('length:', r['length'])
        print('preview:\n', r['preview'])
con.close()
