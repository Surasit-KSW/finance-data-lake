-- ══════════════════════════════════════════════════════════════
-- Finance Data Lake — Neon PostgreSQL Schema
-- Run once on your Neon database to create tables.
--
-- Steps:
--   1. Create free Neon DB at https://neon.tech
--   2. Copy the connection string (postgresql://user:pass@ep-xxx.neon.tech/neondb)
--   3. Run: psql "your_connection_string" -f scripts/setup_neon_schema.sql
--   4. Then run: python scripts/migrate_to_neon.py to load data
-- ══════════════════════════════════════════════════════════════

-- ── GL Transactions (Silver: Master_GL_24_25.parquet) ─────────────────────
CREATE TABLE IF NOT EXISTS v_gl (
    id                      SERIAL PRIMARY KEY,
    "Posting Date"          DATE,
    "Document Date"         DATE,
    "G/L Account"           VARCHAR(20),
    "G/L Account: Long Text" VARCHAR(255),
    "Net_Amount"            DECIMAL(18,2),
    "Text"                  TEXT,
    "Document Number"       VARCHAR(20),
    "Document Type"         VARCHAR(10),
    "Cost Center"           VARCHAR(20),
    "Cost Center: Short Text" VARCHAR(100),
    "Profit Center"         VARCHAR(20),
    "Year"                  INTEGER,
    "Month"                 INTEGER
);

CREATE INDEX IF NOT EXISTS idx_gl_account   ON v_gl ("G/L Account");
CREATE INDEX IF NOT EXISTS idx_gl_year_month ON v_gl ("Year", "Month");

-- ── Sales Data (Silver: master_sales_*.parquet) ────────────────────────────
CREATE TABLE IF NOT EXISTS v_sales (
    id              SERIAL PRIMARY KEY,
    "Year"          INTEGER,
    "Month"         INTEGER,
    "Product Group" VARCHAR(100),
    "Product"       VARCHAR(255),
    "Customer"      VARCHAR(255),
    "Net Sales"     DECIMAL(18,2),
    "Quantity"      DECIMAL(18,3),
    "Unit"          VARCHAR(20)
);

CREATE INDEX IF NOT EXISTS idx_sales_year ON v_sales ("Year");

-- ── Production Data (Silver: master_production_*.parquet) ─────────────────
CREATE TABLE IF NOT EXISTS v_production (
    id               SERIAL PRIMARY KEY,
    "Year"           INTEGER,
    "Month"          INTEGER,
    "Plant"          VARCHAR(10),
    "Order No"       VARCHAR(30),
    "Material"       VARCHAR(50),
    "Production Qty" DECIMAL(18,3),
    "Total Cost"     DECIMAL(18,2)
);

CREATE INDEX IF NOT EXISTS idx_prod_year ON v_production ("Year", "Month", "Plant");

-- ── Trial Balance Data (extracted from SAP exports + YE25 leadsheet) ───────
CREATE TABLE IF NOT EXISTS tb_data (
    id           SERIAL PRIMARY KEY,
    period       VARCHAR(10)  NOT NULL,   -- 'YYYY-MM-DD'
    account_code VARCHAR(20),
    account_name TEXT,
    balance      DECIMAL(18,2),
    fs_item      VARCHAR(100)
);

CREATE INDEX IF NOT EXISTS idx_tb_period ON tb_data (period);

-- ── AR Invoices (v_ar — load from master_ar.parquet if available) ──────────
CREATE TABLE IF NOT EXISTS v_ar (
    id               SERIAL PRIMARY KEY,
    "Customer Code"  VARCHAR(20),
    "Customer Name"  VARCHAR(255),
    "Invoice No"     VARCHAR(30),
    "Invoice Date"   DATE,
    "Due Date"       DATE,
    "Outstanding"    DECIMAL(18,2),
    "Aging Bucket"   VARCHAR(30)
);

CREATE INDEX IF NOT EXISTS idx_ar_customer ON v_ar ("Customer Name");
CREATE INDEX IF NOT EXISTS idx_ar_date     ON v_ar ("Invoice Date");

-- ── GL Summary (Gold: Summary_GL_24_25.parquet) ───────────────────────────
CREATE TABLE IF NOT EXISTS v_gl_summary (
    id           SERIAL PRIMARY KEY,
    "G/L Account" VARCHAR(20),
    "Account Name" VARCHAR(255),
    "Year"         INTEGER,
    "Month"        INTEGER,
    "Net_Amount"   DECIMAL(18,2)
);

-- ── Metadata: track when each table was last loaded ───────────────────────
CREATE TABLE IF NOT EXISTS _lake_meta (
    table_name   VARCHAR(50) PRIMARY KEY,
    row_count    INTEGER,
    loaded_at    TIMESTAMP DEFAULT NOW(),
    source_file  TEXT
);

-- ── Verify ────────────────────────────────────────────────────────────────
SELECT table_name, pg_size_pretty(pg_total_relation_size(quote_ident(table_name))) AS size
FROM information_schema.tables
WHERE table_schema = 'public'
ORDER BY table_name;
