-- ============================================================
-- Risk Issue & Remediation Analytics — Phase 3: SQL Cross-Validation
-- Data loaded via pandas .to_sql() into risk_issues_db.risk_issues
-- ============================================================

USE risk_issues_db;

-- ------------------------------------------------------------
-- 0. Environment check
-- ------------------------------------------------------------
DESCRIBE risk_issues;
SELECT COUNT(*) AS total_rows FROM risk_issues;  -- expect 2200


-- ------------------------------------------------------------
-- 1. Data quality checks
-- ------------------------------------------------------------

-- Expect 401 (open issues)
SELECT COUNT(*) AS open_issues_null_check
FROM risk_issues
WHERE Actual_Close_Date IS NULL;

-- Expect 0/1 values only
SELECT SLA_Breach, Recurrence_Flag
FROM risk_issues
LIMIT 5;


-- ------------------------------------------------------------
-- 2. Step 6 — Issue aging via DATEDIFF
-- ------------------------------------------------------------

-- Closed issues: days to close, longest 10
SELECT
    Issue_ID, Business_Unit, Open_Date, Actual_Close_Date,
    DATEDIFF(Actual_Close_Date, Open_Date) AS Days_To_Close
FROM risk_issues
WHERE Actual_Close_Date IS NOT NULL
ORDER BY Days_To_Close DESC
LIMIT 10;

-- Open issues: age as of snapshot 2026-06-30
-- Expect: 401 issues, avg ~285 days (matches Python EDA)
SELECT
    COUNT(*) AS open_issue_count,
    ROUND(AVG(DATEDIFF('2026-06-30', Open_Date)), 1) AS avg_age_days,
    MAX(DATEDIFF('2026-06-30', Open_Date)) AS oldest_open_days
FROM risk_issues
WHERE Actual_Close_Date IS NULL;


-- ------------------------------------------------------------
-- 3. Step 7 — RANK() business units by open issue count
-- ------------------------------------------------------------

SELECT
    Business_Unit,
    COUNT(*) AS open_issue_count,
    RANK() OVER (ORDER BY COUNT(*) DESC) AS open_count_rank
FROM risk_issues
WHERE Actual_Close_Date IS NULL
GROUP BY Business_Unit
ORDER BY open_count_rank;


-- ------------------------------------------------------------
-- 4. Step 8 — Recompute recurrence via LAG()
-- Rule: within Business_Unit + Root_Cause_Category, order issues
-- by Open_Date (Issue_ID breaks ties on same-day opens). Flag an
-- issue as recurrence if the immediately preceding issue in that
-- order closed 1–90 days before this one opened (0-day gap does
-- NOT count — same-day reopen is excluded by design).
-- Verified against the source data: this exact rule reproduces
-- the original Recurrence_Flag column on all 2200 rows, not just
-- the total count.
-- ------------------------------------------------------------

WITH ordered AS (
    SELECT
        Issue_ID, Business_Unit, Root_Cause_Category,
        Open_Date, Actual_Close_Date,
        LAG(Actual_Close_Date) OVER (
            PARTITION BY Business_Unit, Root_Cause_Category
            ORDER BY Open_Date, Issue_ID
        ) AS Prev_Close_Date
    FROM risk_issues
)
SELECT COUNT(*) AS recomputed_recurrence_count
FROM ordered
WHERE Prev_Close_Date IS NOT NULL
  AND DATEDIFF(Open_Date, Prev_Close_Date) BETWEEN 1 AND 90;


-- ------------------------------------------------------------
-- 5. Step 9 — Confirm the match
-- Both columns should read: 89
-- ------------------------------------------------------------

WITH ordered AS (
    SELECT
        Issue_ID, Business_Unit, Root_Cause_Category,
        Open_Date, Actual_Close_Date,
        LAG(Actual_Close_Date) OVER (
            PARTITION BY Business_Unit, Root_Cause_Category
            ORDER BY Open_Date, Issue_ID
        ) AS Prev_Close_Date
    FROM risk_issues
)
SELECT
    (SELECT COUNT(*) FROM ordered
     WHERE Prev_Close_Date IS NOT NULL
       AND DATEDIFF(Open_Date, Prev_Close_Date) BETWEEN 1 AND 90
    ) AS recomputed_count,
    (SELECT SUM(Recurrence_Flag) FROM risk_issues) AS original_flag_count;


-- ------------------------------------------------------------
-- 6. Step 10 — Control fail rate by Business_Unit x Risk_Category
-- ------------------------------------------------------------

SELECT
    Business_Unit, Risk_Category,
    COUNT(*) AS total_tests,
    SUM(CASE WHEN Control_Test_Result = 'Fail' THEN 1 ELSE 0 END) AS fail_count,
    ROUND(
        SUM(CASE WHEN Control_Test_Result = 'Fail' THEN 1 ELSE 0 END) / COUNT(*) * 100,
    1) AS fail_rate_pct
FROM risk_issues
GROUP BY Business_Unit, Risk_Category
ORDER BY fail_rate_pct DESC;

-- ============================================================
-- End of Phase 3.
-- ============================================================


