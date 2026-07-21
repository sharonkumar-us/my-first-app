import sqlite3

conn = sqlite3.connect("coverage.db")
cur = conn.cursor()

def run_query(label, sql):
    print(f"\n=== {label} ===")
    print(sql.strip())
    print("--- Result ---")
    cur.execute(sql)
    rows = cur.fetchall()
    cols = [desc[0] for desc in cur.description]
    print(cols)
    for row in rows:
        print(row)

# 1. What's the deductible on the Gold PPO plan?
run_query(
    "Q1: Deductible on Gold PPO plan",
    """
    SELECT plan_name, annual_deductible
    FROM plans
    WHERE plan_name = 'Gold PPO';
    """
)

# 2. How many claims are pending for member M1001?
run_query(
    "Q2: Pending claims for member M1001",
    """
    SELECT COUNT(*) AS pending_claims
    FROM claims
    WHERE member_id = 'M1001' AND status = 'Pending';
    """
)

# 3. Which plans have a monthly premium under $400?
run_query(
    "Q3: Plans with monthly premium under $400",
    """
    SELECT plan_id, plan_name, monthly_premium
    FROM plans
    WHERE monthly_premium < 400;
    """
)

# 4. JOIN between claims and plans
run_query(
    "Q4: Claims joined with plan details",
    """
    SELECT c.claim_id, c.member_id, p.plan_name, p.network_tier, c.procedure, c.claim_amount, c.status
    FROM claims c
    JOIN plans p ON c.plan_id = p.plan_id;
    """
)

# 5. Top-N query — most claimed procedures
run_query(
    "Q5: Most frequently claimed procedures",
    """
    SELECT procedure, COUNT(*) AS times_claimed
    FROM claims
    GROUP BY procedure
    ORDER BY times_claimed DESC;
    """
)

conn.close()