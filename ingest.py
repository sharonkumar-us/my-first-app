import pandas as pd

# --- Load ---
plans = pd.read_csv("data/plans.csv")
claims = pd.read_csv("data/claims.csv")

# --- Inspect ---
print("=== plans.info() ===")
plans.info()
print("\n=== plans.head() ===")
print(plans.head())

print("\n=== claims.info() ===")
claims.info()
print("\n=== claims.head() ===")
print(claims.head())

# --- Clean ---
plans = plans.drop_duplicates()
claims = claims.drop_duplicates()

plans = plans.dropna(subset=["plan_id"])
claims = claims.dropna(subset=["claim_id", "plan_id"])

claims["date_filed"] = pd.to_datetime(claims["date_filed"], errors="coerce")

print("\n=== Cleaned claims dtypes ===")
print(claims.dtypes)

print("\nStep 3 complete — data loaded and cleaned.")
import sqlite3

# --- Load into SQLite (Step 4) ---
conn = sqlite3.connect("coverage.db")
plans.to_sql("plans", conn, if_exists="replace", index=False)
claims.to_sql("claims", conn, if_exists="replace", index=False)
conn.close()

print("Step 4 complete — coverage.db created with 'plans' and 'claims' tables.")