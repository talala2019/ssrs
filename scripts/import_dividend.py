#!/usr/bin/env python3
"""
import_dividend.py
------------------
Imports Taiwan listed (TWSE) and OTC (TPEx) dividend distribution data
into Investment_DB.DividendDistribution.

Sources:
  - Current year (2025): TWSE openapi JSON  (上市 only)
  - Historical 2020-2024: MOPS via Selenium  (上市 + 上櫃)

Run:  python import_dividend.py
      python import_dividend.py --no-headless   (show browser window)
      python import_dividend.py --twse-only      (skip MOPS, just current year)
"""

import re
import sys
import time
import argparse
import requests
import pyodbc

# Force UTF-8 output on Windows console
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ('utf-8', 'utf8'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from decimal import Decimal, InvalidOperation
from datetime import date

# ── Config ────────────────────────────────────────────────────────────────────
SQL_SERVER   = 'localhost'
SQL_DATABASE = 'Investment_DB'
SQL_DRIVER   = 'ODBC Driver 17 for SQL Server'

START_ROC    = 109   # 民國 109 = AD 2020
END_ROC      = 113   # 民國 113 = AD 2024  (2025 comes from openapi)

TWSE_OPENAPI = 'https://openapi.twse.com.tw/v1/opendata/t187ap45_L'

# ── Helpers ───────────────────────────────────────────────────────────────────
def roc_to_ad(y): return int(y) + 1911

def roc_date(s: str) -> date | None:
    s = str(s or '').strip()
    if len(s) < 7:
        return None
    try:
        ad = int(s[:-4]) + 1911
        m  = int(s[-4:-2])
        d  = int(s[-2:])
        return date(ad, m, d) if m and d else None
    except Exception:
        return None

def to_dec(s) -> Decimal | None:
    try:
        return Decimal(str(s).strip()) if str(s).strip() not in ('', '0.0', 'N/A') else Decimal(0)
    except InvalidOperation:
        return None

def to_int(s) -> int | None:
    try:
        v = str(s or '').strip().replace(',', '')
        return int(float(v)) if v else None
    except (ValueError, TypeError):
        return None

def nk(k: str) -> str:
    """Normalize field key: strip whitespace, convert full-width brackets."""
    return k.strip().replace('「', '(').replace('」', ')') \
             .replace('（', '(').replace('）', ')').replace('　', ' ')


# ── Normalize one raw record → DB dict ────────────────────────────────────────
FIELD_MAP = {
    '公司代號':                         'Symbol',
    '公司名稱':                         'CompanyName',
    '決議（擬議）進度':                  'ResolutionStatus',
    '決議(擬議)進度':                    'ResolutionStatus',
    '股利年度':                         '_YearROC',
    '股利所屬年(季)度':                  'PeriodType',
    '股利所屬期間':                      'PeriodRange',
    '期別':                            '_PeriodNo',
    '董事會（擬議）股利分派日':            '_BoardDate',
    '董事會(擬議)股利分派日':             '_BoardDate',
    '股東會日期':                        '_SMDate',
    '期初未分配盈餘/待彌補虧損(元)':      'BeginningRetainedEarnings',
    '本期淨利(淨損)(元)':                'NetIncome',
    '可分配盈餘(元)':                    'DistributableEarnings',
    '分配後期末未分配盈餘(元)':           'EndingRetainedEarnings',
    '股東配發-盈餘分配之現金股利(元/股)': 'CashFromEarnings',
    '股東配發-法定盈餘公積發放之現金(元/股)': 'CashFromLegalReserve',
    '股東配發-資本公積發放之現金(元/股)': 'CashFromCapitalReserve',
    '股東配發-股東配發之現金(股利)總金額(元)': 'TotalCashAmount',
    '股東配發-盈餘轉增資配股(元/股)':     'StockFromEarnings',
    '股東配發-法定盈餘公積轉增資配股(元/股)': 'StockFromLegalReserve',
    '股東配發-資本公積轉增資配股(元/股)': 'StockFromCapitalReserve',
    '股東配發-股東配股總股數(股)':        'TotalStockShares',
}

def normalize(raw: dict, exchange: str) -> dict | None:
    mapped = {}
    for k, v in raw.items():
        canonical = FIELD_MAP.get(nk(k)) or FIELD_MAP.get(k)
        if canonical:
            mapped[canonical] = str(v or '').strip()

    sym = mapped.get('Symbol', '').strip()
    if not sym:
        return None

    year_roc = mapped.get('_YearROC', '0')
    period_no_s = mapped.get('_PeriodNo', '1')
    period_no = int(period_no_s) if str(period_no_s).isdigit() else 1
    period_type = mapped.get('PeriodType', '')
    quarter = 0 if '年度' in period_type else period_no

    ce = to_dec(mapped.get('CashFromEarnings'))
    cl = to_dec(mapped.get('CashFromLegalReserve'))
    cc = to_dec(mapped.get('CashFromCapitalReserve'))
    se = to_dec(mapped.get('StockFromEarnings'))
    sl = to_dec(mapped.get('StockFromLegalReserve'))
    sc = to_dec(mapped.get('StockFromCapitalReserve'))

    def s(*vals):
        return sum((v for v in vals if v is not None), Decimal(0))

    total_cash  = s(ce, cl, cc)
    total_stock = s(se, sl, sc)

    return {
        'Symbol':                      sym,
        'CompanyName':                 mapped.get('CompanyName'),
        'Exchange':                    exchange,
        'DividendYear':                roc_to_ad(year_roc) if year_roc.isdigit() else None,
        'DividendQuarter':             quarter,
        'PeriodType':                  period_type,
        'PeriodRange':                 mapped.get('PeriodRange', ''),
        'PeriodNo':                    period_no,
        'ResolutionStatus':            re.sub(r'<[^>]+>', ' ', mapped.get('ResolutionStatus', '')).strip(),
        'BoardApprovalDate':           roc_date(mapped.get('_BoardDate')),
        'ShareholderMeetingDate':      roc_date(mapped.get('_SMDate')),
        'BeginningRetainedEarnings':   to_int(mapped.get('BeginningRetainedEarnings')),
        'NetIncome':                   to_int(mapped.get('NetIncome')),
        'DistributableEarnings':       to_int(mapped.get('DistributableEarnings')),
        'EndingRetainedEarnings':      to_int(mapped.get('EndingRetainedEarnings')),
        'CashFromEarnings':            ce,
        'CashFromLegalReserve':        cl,
        'CashFromCapitalReserve':      cc,
        'TotalCashPerShare':           total_cash,
        'TotalCashAmount':             to_int(mapped.get('TotalCashAmount')),
        'StockFromEarnings':           se,
        'StockFromLegalReserve':       sl,
        'StockFromCapitalReserve':     sc,
        'TotalStockPerShare':          total_stock,
        'TotalStockShares':            to_int(mapped.get('TotalStockShares')),
        'TotalDividendPerShare':       total_cash + total_stock,
    }


# ── Fetch: TWSE openapi (current year, 上市) ──────────────────────────────────
def fetch_twse_openapi() -> list[dict]:
    print('► TWSE openapi (current year, 上市)...')
    resp = requests.get(TWSE_OPENAPI, timeout=30)
    resp.raise_for_status()
    raw_list = resp.json()
    records = [r for r in (normalize(x, 'TWSE') for x in raw_list) if r]
    print(f'  {len(records)} records')
    return records


# ── Fetch: MOPS via Selenium (historical) ─────────────────────────────────────
def fetch_mops(year_roc: int, typek: str, headless: bool) -> list[dict]:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait, Select
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.chrome.options import Options
    from bs4 import BeautifulSoup

    exchange = 'TWSE' if typek == 'sii' else 'TPEx'
    print(f'► MOPS {exchange} ROC {year_roc} (AD {roc_to_ad(year_roc)})...')

    opts = Options()
    if headless:
        opts.add_argument('--headless=new')
    opts.add_argument('--no-sandbox')
    opts.add_argument('--disable-dev-shm-usage')
    opts.add_argument('--window-size=1920,1080')
    opts.add_argument('--disable-blink-features=AutomationControlled')
    opts.add_experimental_option('excludeSwitches', ['enable-automation'])
    opts.add_experimental_option('useAutomationExtension', False)

    driver = webdriver.Chrome(options=opts)
    records = []

    try:
        wait = WebDriverWait(driver, 25)

        # Establish portal session
        driver.get('https://mops.twse.com.tw/mops')
        time.sleep(3)

        # Navigate to the form page (may redirect on first load without session)
        driver.get('https://mops.twse.com.tw/mops/web/t187ap45_L')
        time.sleep(2)

        # If still on the portal main page, the JS re-routing should now allow the form
        if 't187ap45_L' not in driver.current_url:
            driver.get('https://mops.twse.com.tw/mops/web/t187ap45_L')
            time.sleep(2)

        print(f'  URL: {driver.current_url}')

        # Try to find the search form
        try:
            form = wait.until(EC.presence_of_element_located((By.TAG_NAME, 'form')))
        except Exception:
            # Save debug page
            fname = f'debug_mops_{year_roc}_{typek}.html'
            with open(fname, 'w', encoding='utf-8') as f:
                f.write(driver.page_source)
            print(f'  WARNING: form not found, saved {fname}')
            return []

        # Select TYPEK
        try:
            sel = driver.find_element(By.NAME, 'TYPEK')
            Select(sel).select_by_value(typek)
        except Exception:
            try:
                rb = driver.find_element(By.CSS_SELECTOR, f'input[name="TYPEK"][value="{typek}"]')
                rb.click()
            except Exception as e:
                print(f'  WARNING: could not set TYPEK: {e}')

        # Set year
        try:
            inp = driver.find_element(By.NAME, 'year')
            inp.clear()
            inp.send_keys(str(year_roc))
        except Exception as e:
            print(f'  WARNING: could not set year: {e}')

        # Set season = 0 (all year) if present
        try:
            Select(driver.find_element(By.NAME, 'season')).select_by_value('0')
        except Exception:
            pass

        # Submit
        try:
            btn = form.find_element(By.CSS_SELECTOR, 'input[type="submit"], button[type="submit"]')
            btn.click()
        except Exception:
            form.submit()

        # Wait for results table
        try:
            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'table')))
            time.sleep(2)
        except Exception:
            pass

        html = driver.page_source
        soup = BeautifulSoup(html, 'lxml')

        # Find the data table (look for one containing 公司代號 header)
        data_table = None
        for tbl in soup.find_all('table'):
            text = tbl.get_text()
            if '公司代號' in text and '股利年度' in text:
                data_table = tbl
                break

        if not data_table:
            fname = f'debug_mops_{year_roc}_{typek}.html'
            with open(fname, 'w', encoding='utf-8') as f:
                f.write(html)
            print(f'  WARNING: data table not found, saved {fname}')
            return []

        # Extract headers from first row
        rows = data_table.find_all('tr')
        if not rows:
            return []

        headers = [th.get_text(strip=True) for th in rows[0].find_all(['th', 'td'])]

        for row in rows[1:]:
            cells = row.find_all(['td', 'th'])
            if len(cells) < 5:
                continue
            raw = {headers[i]: cells[i].get_text(strip=True)
                   for i in range(min(len(headers), len(cells)))}
            rec = normalize(raw, exchange)
            if rec and rec.get('Symbol') and rec.get('PeriodRange'):
                records.append(rec)

        print(f'  {len(records)} records parsed')

    except Exception as e:
        print(f'  ERROR: {e}')
        fname = f'debug_mops_{year_roc}_{typek}_error.html'
        try:
            with open(fname, 'w', encoding='utf-8') as f:
                f.write(driver.page_source)
            print(f'  Saved {fname}')
        except Exception:
            pass

    finally:
        driver.quit()

    return records


# ── Database ───────────────────────────────────────────────────────────────────
DB_COLS = [
    'Symbol', 'CompanyName', 'Exchange', 'DividendYear', 'DividendQuarter',
    'PeriodType', 'PeriodRange', 'PeriodNo', 'ResolutionStatus',
    'BoardApprovalDate', 'ShareholderMeetingDate',
    'BeginningRetainedEarnings', 'NetIncome', 'DistributableEarnings',
    'EndingRetainedEarnings', 'CashFromEarnings', 'CashFromLegalReserve',
    'CashFromCapitalReserve', 'TotalCashPerShare', 'TotalCashAmount',
    'StockFromEarnings', 'StockFromLegalReserve', 'StockFromCapitalReserve',
    'TotalStockPerShare', 'TotalStockShares', 'TotalDividendPerShare',
]

INSERT_SQL = f"""
INSERT INTO DividendDistribution ({', '.join(DB_COLS)})
VALUES ({', '.join(['?'] * len(DB_COLS))})
"""

UPDATE_SQL = f"""
UPDATE DividendDistribution SET
    {', '.join(f'{c}=?' for c in DB_COLS if c not in ('Symbol','Exchange','PeriodRange'))},
    UpdatedTime = GETDATE()
WHERE Symbol=? AND Exchange=? AND PeriodRange=?
"""
UPDATE_COLS = [c for c in DB_COLS if c not in ('Symbol', 'Exchange', 'PeriodRange')]


def db_connect():
    return pyodbc.connect(
        f'DRIVER={{{SQL_DRIVER}}};SERVER={SQL_SERVER};'
        f'DATABASE={SQL_DATABASE};Trusted_Connection=yes;'
    )


def upsert_records(conn, records: list[dict]) -> int:
    cur = conn.cursor()
    inserted = updated = errors = 0

    for r in records:
        if not r.get('Symbol') or not r.get('PeriodRange'):
            continue
        vals = [r.get(c) for c in DB_COLS]
        try:
            cur.execute(INSERT_SQL, vals)
            inserted += 1
        except pyodbc.IntegrityError:
            # Unique constraint hit → update
            update_vals = [r.get(c) for c in UPDATE_COLS] + \
                          [r['Symbol'], r['Exchange'], r['PeriodRange']]
            try:
                cur.execute(UPDATE_SQL, update_vals)
                updated += 1
            except Exception as e:
                print(f'  Update error {r["Symbol"]}: {e}')
                errors += 1
        except Exception as e:
            print(f'  Insert error {r["Symbol"]}: {e}')
            errors += 1

    conn.commit()
    cur.close()
    print(f'  → inserted={inserted}, updated={updated}, errors={errors}')
    return inserted + updated


def link_company_ids(conn):
    """Populate CompanyID FK from Company table."""
    cur = conn.cursor()
    cur.execute("""
        UPDATE d SET d.CompanyID = c.CompanyID
        FROM DividendDistribution d
        JOIN Company c ON LEFT(c.Symbol, 4) = LEFT(d.Symbol, 4)
        WHERE d.CompanyID IS NULL
    """)
    print(f'  CompanyID linked: {cur.rowcount} rows')
    conn.commit()
    cur.close()


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--no-headless', action='store_true', help='Show browser window')
    parser.add_argument('--twse-only',   action='store_true', help='Only fetch current year from TWSE openapi')
    parser.add_argument('--year',        type=int,            help='Fetch only this ROC year from MOPS (e.g. 109)')
    args = parser.parse_args()

    headless = not args.no_headless
    conn = db_connect()
    print(f'Connected to {SQL_DATABASE}')

    # 1. Current year from TWSE openapi (上市 only)
    records = fetch_twse_openapi()
    upsert_records(conn, records)

    if not args.twse_only:
        # 2. Historical years from MOPS (上市 + 上櫃)
        years = [args.year] if args.year else range(START_ROC, END_ROC + 1)
        for year_roc in years:
            for typek in ['sii', 'otc']:
                recs = fetch_mops(year_roc, typek, headless)
                if recs:
                    upsert_records(conn, recs)
                time.sleep(3)  # polite delay

    # 3. Link CompanyID
    print('► Linking CompanyID...')
    link_company_ids(conn)

    conn.close()
    print('Done.')


if __name__ == '__main__':
    main()
