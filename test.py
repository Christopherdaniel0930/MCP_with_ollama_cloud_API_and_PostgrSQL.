
import os
import psycopg
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

try:
    with psycopg.connect(DATABASE_URL) as conn:
        # Retrieve available tables
        tables = conn.execute("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_type = 'BASE TABLE'
        """).fetchall()

        print("Tables found:")
        for table in tables:
            print("-", table[0])

        # Test a simple database query
        result = conn.execute("SELECT 1 AS test").fetchone()
        print("\nConnection test:", result[0])

    with psycopg.connect(DATABASE_URL) as conn:
        result = conn.execute("""
            SELECT current_database(),
                current_user,
                current_schema()
        """).fetchone()

    with psycopg.connect(DATABASE_URL) as conn:
        row = conn.execute("""
            SELECT * FROM Customers
        """).fetchone()

        print("Database:", result[0])
        print("User:", result[1])
        print("Schema:", result[2])
        
        print("Row:", row)

except Exception as e:
    print("Error:", e)
