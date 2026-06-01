"""
Migrate DividendData (2020-2023) into DividendDistribution.
Source: Investment_DB.dbo.DividendData JOIN Company
Target: Investment_DB.dbo.DividendDistribution
Only migrates TWSE (SECode=TPE) records; DividendData has no TPEX data.
On conflict (Symbol, Exchange, PeriodRange): skip to preserve richer TWSE openapi data.
"""
import pyodbc, sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

QUARTER_RANGES = {
    0: ('0101', '1231'),
    1: ('0101', '0331'),
    2: ('0401', '0630'),
    3: ('0701', '0930'),
    4: ('1001', '1231'),
}

def period_range(year_ad, quarter):
    roc = year_ad - 1911
    s, e = QUARTER_RANGES.get(quarter, ('0101', '1231'))
    return f'{roc}{s}~{roc}{e}'


conn = pyodbc.connect(
    'DRIVER={ODBC Driver 17 for SQL Server};SERVER=localhost;'
    'DATABASE=Investment_DB;Trusted_Connection=yes;'
)
cur = conn.cursor()

cur.execute("""
    SELECT d.CompanyID, d.Year, d.Quarter,
           d.CashDividend,
           d.StockDividendFromRetainedEarnings,
           d.StockDividendfromCapitalReserve,
           d.StockDividend,
           d.TotalDividend,
           c.Symbol, c.ChtName
    FROM DividendData d
    JOIN Company c ON d.CompanyID = c.CompanyID
    WHERE d.Year BETWEEN 2020 AND 2023
      AND c.SECode = 'TPE'
    ORDER BY d.Year, c.Symbol
""")
rows = cur.fetchall()
print(f'Records to migrate: {len(rows)}')

inserted = updated = 0

INSERT_SQL = """
    INSERT INTO DividendDistribution
        (CompanyID, Symbol, CompanyName, Exchange,
         DividendYear, DividendQuarter, PeriodType, PeriodRange,
         TotalCashPerShare, StockFromEarnings, StockFromCapitalReserve,
         TotalStockPerShare, TotalDividendPerShare)
    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
"""

for row in rows:
    (comp_id, year, quarter,
     cash, stock_earn, stock_cap, stock_total, total_div,
     sym_full, name) = row

    sym = sym_full[:4]
    pr = period_range(year, quarter)
    ptype = 'Y' if quarter == 0 else 'Q'

    def nz(v):
        return float(v) if v is not None else None

    try:
        cur.execute(INSERT_SQL,
            comp_id, sym, name, 'TWSE',
            year, quarter, ptype, pr,
            nz(cash), nz(stock_earn), nz(stock_cap),
            nz(stock_total), nz(total_div))
        inserted += 1
    except pyodbc.IntegrityError:
        # Already exists (from TWSE openapi or prior run) — keep existing richer data
        updated += 1

conn.commit()
print(f'Done: inserted={inserted}, skipped(conflict)={updated}')

# Verify
cur.execute("""
    SELECT DividendYear, COUNT(*) as cnt
    FROM DividendDistribution
    WHERE DividendYear BETWEEN 2020 AND 2023
    GROUP BY DividendYear ORDER BY DividendYear
""")
print('\nDividendDistribution 2020-2023:')
for r in cur.fetchall():
    print(f'  {r}')

conn.close()
