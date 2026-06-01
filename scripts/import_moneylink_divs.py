"""
Fetch money-link.com.tw ex-dividend table and upsert into DividendDistribution.
Covers fiscal years 2024 (ex-dates in 2025) and 2025 (ex-dates in 2026).
TPEX companies identified by asterisk (*) in company name.
On conflict: UPDATE ExDividendDate + dividend amounts.
"""
import requests, re, pyodbc, sys
from bs4 import BeautifulSoup
from datetime import datetime

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

URL = 'https://ww2.money-link.com.tw/TWStock/TWStockMarket.aspx?mainOptionType=9&optionType=6'

HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120'}


def parse_ex_date(s):
    """'1152026/10/15' → date(2026, 10, 15). Strip 3-char ROC prefix."""
    try:
        return datetime.strptime(s[3:], '%Y/%m/%d').date()
    except Exception:
        return None


def to_float(s):
    try:
        return float(s)
    except Exception:
        return None


def fetch_records():
    r = requests.get(URL, headers=HEADERS, timeout=30)
    soup = BeautifulSoup(r.text, 'lxml')
    data_table = next(
        (t for t in soup.find_all('table') if len(t.find_all('tr')) > 100),
        None
    )
    if not data_table:
        raise RuntimeError('Data table not found')

    records = []
    for row in data_table.find_all('tr'):
        cells = row.find_all('td')
        if len(cells) < 6:
            continue
        texts = [c.get_text(strip=True) for c in cells]
        if not re.match(r'^\d{4}[A-Z0-9]*$', texts[0]):
            continue

        symbol = texts[0]
        name_raw = texts[1]
        date_str = texts[2]
        cash_str = texts[3]
        stock_str = texts[4]
        total_str = texts[5]

        ex_date = parse_ex_date(date_str)
        if not ex_date:
            continue

        is_tpex = '*' in name_raw
        exchange = 'TPEX' if is_tpex else 'TWSE'
        name = name_raw.replace('*', '').strip()

        # Fiscal year = ex-date year - 1 (annual dividend distributed the following year)
        div_year = ex_date.year - 1
        roc = div_year - 1911
        period_range = f'{roc}0101~{roc}1231'

        records.append({
            'Symbol': symbol,
            'CompanyName': name,
            'Exchange': exchange,
            'ExDividendDate': ex_date,
            'DividendYear': div_year,
            'DividendQuarter': 0,
            'PeriodType': 'Y',
            'PeriodRange': period_range,
            'TotalCashPerShare': to_float(cash_str),
            'TotalStockPerShare': to_float(stock_str),
            'TotalDividendPerShare': to_float(total_str),
        })
    return records


def run():
    print('Fetching money-link page...')
    records = fetch_records()
    print(f'Parsed {len(records)} records')

    conn = pyodbc.connect(
        'DRIVER={ODBC Driver 17 for SQL Server};SERVER=localhost;'
        'DATABASE=Investment_DB;Trusted_Connection=yes;'
    )
    cur = conn.cursor()

    # Build CompanyID lookup: first-4-chars of Symbol → CompanyID
    cur.execute("SELECT CompanyID, Symbol FROM Company WHERE SECode='TPE'")
    sym_to_id = {sym[:4]: cid for cid, sym in cur.fetchall()}

    INSERT_SQL = """
        INSERT INTO DividendDistribution
            (CompanyID, Symbol, CompanyName, Exchange,
             DividendYear, DividendQuarter, PeriodType, PeriodRange,
             ExDividendDate, TotalCashPerShare, TotalStockPerShare, TotalDividendPerShare)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
    """
    UPDATE_SQL = """
        UPDATE DividendDistribution SET
            ExDividendDate   = ?,
            TotalCashPerShare   = COALESCE(TotalCashPerShare, ?),
            TotalStockPerShare  = COALESCE(TotalStockPerShare, ?),
            TotalDividendPerShare = COALESCE(TotalDividendPerShare, ?)
        WHERE Symbol=? AND Exchange=? AND PeriodRange=?
    """

    inserted = updated = 0
    for rec in records:
        sym = rec['Symbol']
        exch = rec['Exchange']
        pr = rec['PeriodRange']
        comp_id = sym_to_id.get(sym[:4])  # NULL for TPEX not in Company

        try:
            cur.execute(INSERT_SQL,
                comp_id, sym, rec['CompanyName'], exch,
                rec['DividendYear'], rec['DividendQuarter'],
                rec['PeriodType'], pr,
                rec['ExDividendDate'],
                rec['TotalCashPerShare'], rec['TotalStockPerShare'],
                rec['TotalDividendPerShare'])
            inserted += 1
        except pyodbc.IntegrityError:
            cur.execute(UPDATE_SQL,
                rec['ExDividendDate'],
                rec['TotalCashPerShare'], rec['TotalStockPerShare'],
                rec['TotalDividendPerShare'],
                sym, exch, pr)
            updated += 1

    conn.commit()
    print(f'Done: inserted={inserted}, updated={updated}')

    # Summary
    cur.execute("""
        SELECT DividendYear, Exchange, COUNT(*) as cnt
        FROM DividendDistribution
        GROUP BY DividendYear, Exchange
        ORDER BY DividendYear, Exchange
    """)
    print('\nDividendDistribution summary:')
    for r in cur.fetchall():
        print(f'  {r}')

    conn.close()


if __name__ == '__main__':
    run()
