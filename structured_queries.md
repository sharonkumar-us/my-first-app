# Structured Queries — Day 4

Queries written and tested against `coverage.db`, built from synthetic `plans.csv` and `claims.csv`.

---

## Q1: What's the deductible on the Gold PPO plan?

\`\`\`sql
SELECT plan_name, annual_deductible
FROM plans
WHERE plan_name = 'Gold PPO';
\`\`\`

**Result:**
| plan_name | annual_deductible |
|---|---|
| Gold PPO | 2000 |

---

## Q2: How many claims are pending for member M1001?

\`\`\`sql
SELECT COUNT(*) AS pending_claims
FROM claims
WHERE member_id = 'M1001' AND status = 'Pending';
\`\`\`

**Result:**
| pending_claims |
|---|
| 1 |

---

## Q3: Which plans have a monthly premium under $400?

\`\`\`sql
SELECT plan_id, plan_name, monthly_premium
FROM plans
WHERE monthly_premium < 400;
\`\`\`

**Result:**
| plan_id | plan_name | monthly_premium |
|---|---|---|
| P102 | Silver HMO | 300 |
| P103 | Bronze HMO | 150 |

---

## Q4: JOIN — claims with their plan details

\`\`\`sql
SELECT c.claim_id, c.member_id, p.plan_name, p.network_tier, c.procedure, c.claim_amount, c.status
FROM claims c
JOIN plans p ON c.plan_id = p.plan_id;
\`\`\`

**Result:**
| claim_id | member_id | plan_name | network_tier | procedure | claim_amount | status |
|---|---|---|---|---|---|---|
| C1001 | M1001 | Gold PPO | Gold | X-ray | 250 | Pending |
| C1002 | M1001 | Gold PPO | Gold | Surgery | 1200 | Approved |
| C1003 | M1002 | Silver HMO | Silver | X-ray | 150 | Denied |
| C1004 | M1002 | Silver HMO | Silver | Surgery | 900 | Approved |
| C1005 | M1003 | Bronze HMO | Bronze | X-ray | 50 | Pending |

---

## Q5: Top-N — most frequently claimed procedures

\`\`\`sql
SELECT procedure, COUNT(*) AS times_claimed
FROM claims
GROUP BY procedure
ORDER BY times_claimed DESC;
\`\`\`

**Result:**
| procedure | times_claimed |
|---|---|
| X-ray | 3 |
| Surgery | 2 |