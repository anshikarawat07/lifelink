import sqlite3
from db import get_db

def query_db(query, args=(), one=False):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(query, args)

    query_type = query.strip().split()[0].upper()

    # For SELECT queries → return data
    if query_type == "SELECT":
        result = cur.fetchall()
        conn.close()
        return result[0] if (one and result) else result

    # For INSERT, UPDATE, DELETE → commit changes
    conn.commit()
    conn.close()
    return None
