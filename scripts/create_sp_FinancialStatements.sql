-- ============================================================
-- sp_FinancialStatements
-- Parameter: @symbol  e.g. '2317' or '2317.TW' (case-insensitive)
-- Returns one row per (Year, Quarter) for Type=2 合併 reports
-- ============================================================
CREATE OR ALTER PROCEDURE [dbo].[sp_FinancialStatements]
    @symbol NVARCHAR(20)
AS
BEGIN
    SET NOCOUNT ON;

    -- Normalize symbol to 'XXXX.TW'
    DECLARE @sym NVARCHAR(20) = UPPER(LTRIM(RTRIM(@symbol)));
    IF @sym NOT LIKE '%.%'
        SET @sym = @sym + '.TW';

    DECLARE @cid INT;
    DECLARE @ChtName NVARCHAR(100);
    SELECT @cid = CompanyID, @ChtName = ChtName FROM Company WHERE UPPER(Symbol) = @sym;
    IF @cid IS NULL RETURN;

    -- --------------------------------------------------------
    -- Annual balance-sheet for IRR (Q=0, Type=2)
    -- IRR_year = (LTI+TFA_year  - LTI+TFA_year-4)
    --          / SUM(NI, year-3..year)
    -- --------------------------------------------------------
    WITH BS_Annual AS (
        SELECT
            b.Year,
            b.A_LongTermInvestments + b.A_TotalFixedAssets AS TotalInv,
            i.NetIncome
        FROM BalanceSheet b
        JOIN IncomeStatement i
            ON  i.CompanyID = b.CompanyID
            AND i.Year      = b.Year
            AND i.Quarter   = 0
            AND i.Type      = 2
        WHERE b.CompanyID = @cid
          AND b.Quarter   = 0
          AND b.Type      = 2
    ),
    IRR_Calc AS (
        SELECT
            Year,
            ( TotalInv
              - LAG(TotalInv, 4) OVER (ORDER BY Year)
            )
            / NULLIF(
                SUM(NetIncome) OVER (ORDER BY Year ROWS BETWEEN 3 PRECEDING AND CURRENT ROW)
              , 0)
            AS IRR
        FROM BS_Annual
    ),

    -- --------------------------------------------------------
    -- Core financial data: IS + BS(period) + BS(annual Q=0) + CF
    -- BS annual (ba) used for E_CommonStock in ICF denominator
    -- --------------------------------------------------------
    FinBase AS (
        SELECT
            i.Year,
            i.Quarter,
            -- Income Statement
            i.NetSales,
            i.OperatingCosts,
            i.OperatingProfit,   -- = NetSales - OperatingCosts
            i.OperatingIncome,   -- = OperatingProfit - OpEx
            ISNULL(i.TotalNonOperatingIncome,  0) AS NOI_In,
            ISNULL(i.TotalNonOperatingExpenses,0) AS NOI_Ex,
            i.EBT,
            i.NetIncome,
            i.EarningsPerShare,
            -- Balance Sheet (period-end)
            b.A_TotalAssets,
            b.A_TotalCurrentAssets,
            b.A_LongTermInvestments,
            b.A_TotalFixedAssets,
            b.A_Inventories,
            b.A_AccountsReceivable,
            b.L_TotalLiabilities,
            b.L_TotalCurrentLiabilities,
            b.E_TotalEquity,
            b.E_CommonStock,
            -- Annual BS E_CommonStock for ICF denominator (matches Java getBalanceSheet(year,0))
            ba.E_CommonStock AS E_CommonStock_Annual,
            -- Cash Flow
            ISNULL(cf.Cash_Flows_From_Investing, 0) AS CFI
        FROM IncomeStatement i
        JOIN BalanceSheet b
            ON  b.CompanyID = i.CompanyID
            AND b.Year      = i.Year
            AND b.Quarter   = i.Quarter
            AND b.Type      = 2
        LEFT JOIN BalanceSheet ba
            ON  ba.CompanyID = i.CompanyID
            AND ba.Year      = i.Year
            AND ba.Quarter   = 0
            AND ba.Type      = 2
        LEFT JOIN CashFlow cf
            ON  cf.CompanyID = i.CompanyID
            AND cf.Year      = i.Year
            AND cf.Quarter   = i.Quarter
            AND cf.Type      = 2
        WHERE i.CompanyID = @cid
          AND i.Type      = 2
          AND i.Year >= (SELECT MAX(Year) - 6
                         FROM IncomeStatement
                         WHERE CompanyID = @cid AND Type = 2 AND Quarter = 0)
          -- 前3年只顯示年度 (Q=0)；最近4年顯示全季
          AND (
              i.Quarter = 0
              OR i.Year > (SELECT MAX(Year) - 4
                           FROM IncomeStatement
                           WHERE CompanyID = @cid AND Type = 2 AND Quarter = 0)
          )
    ),

    -- YoY: compare same quarter, previous year
    FinYoY AS (
        SELECT *,
            LAG(NetSales,   1) OVER (PARTITION BY Quarter ORDER BY Year) AS PrevSales,
            LAG(NetIncome,  1) OVER (PARTITION BY Quarter ORDER BY Year) AS PrevNI
        FROM FinBase
    ),

    -- Stock price: annual high/low
    PriceAnnual AS (
        SELECT
            YEAR(PriceDate) AS PYear,
            MIN(DayLow)    AS P_L,
            MAX(DayHigh)   AS P_H
        FROM StockDailyData
        WHERE CompanyID = @cid
        GROUP BY YEAR(PriceDate)
    ),
    -- Stock price: quarterly high/low
    PriceQtr AS (
        SELECT
            YEAR(PriceDate)              AS PYear,
            DATEPART(QUARTER, PriceDate) AS PQtr,
            MIN(DayLow)   AS P_L,
            MAX(DayHigh)  AS P_H
        FROM StockDailyData
        WHERE CompanyID = @cid
        GROUP BY YEAR(PriceDate), DATEPART(QUARTER, PriceDate)
    ),

    -- Dividends: annual fiscal year, Q=0
    DivData AS (
        SELECT DividendYear, TotalCashPerShare
        FROM DividendDistribution
        WHERE CompanyID = @cid
          AND DividendQuarter = 0
    )

    SELECT
        f.Year,
        f.Quarter,
        N'合併'                                                      AS [Type],
        @ChtName                                                     AS ChtName,

        -- ROA (%)
        ROUND(f.NetIncome * 100.0 / NULLIF(f.A_TotalAssets,  0), 1) AS RoA,
        -- ROE (%)
        ROUND(f.NetIncome * 100.0 / NULLIF(f.E_TotalEquity,  0), 1) AS RoE,
        -- IRR (annual only, %)  = investment growth 4Y / 4Y cumulative NI × 100
        CASE WHEN f.Quarter = 0
             THEN ROUND(irr.IRR * 100.0, 1)
             ELSE NULL END                                           AS IRR,
        -- ICF = ABS(CFI) / E_CommonStock_annual × 100  (%)
        ROUND(ABS(f.CFI) * 100.0 / NULLIF(f.E_CommonStock_Annual, 0), 1) AS ICF,

        -- Debt ratio (%)
        ROUND(f.L_TotalLiabilities * 100.0
              / NULLIF(f.A_TotalAssets, 0), 1)                       AS Debt,
        -- Long-term debt ratio (%)
        ROUND((f.L_TotalLiabilities - f.L_TotalCurrentLiabilities) * 100.0
              / NULLIF(f.A_TotalAssets - f.L_TotalCurrentLiabilities, 0), 1) AS RDebt,
        -- Current ratio
        ROUND(f.A_TotalCurrentAssets * 1.0
              / NULLIF(f.L_TotalCurrentLiabilities, 0), 2)           AS CR,

        -- Sales & YoY
        f.NetSales                                                   AS Sales,
        CASE WHEN f.PrevSales > 0
             THEN ROUND(f.NetSales / f.PrevSales, 2)
             ELSE NULL END                                           AS SalesYoY,

        -- NetIncome & YoY
        f.NetIncome,
        CASE WHEN f.PrevNI > 0
             THEN ROUND(f.NetIncome / f.PrevNI, 2)
             ELSE NULL END                                           AS NIYoY,

        -- PM  = 毛利率 (%)
        ROUND(f.OperatingProfit * 100.0
              / NULLIF(f.NetSales, 0), 1)                            AS PM,
        -- GPM = 營業利益率 (%)
        ROUND(f.OperatingIncome * 100.0
              / NULLIF(f.NetSales, 0), 1)                            AS GPM,
        -- NOI = 業外收支 / Sales (%)
        ROUND((f.NOI_In - f.NOI_Ex) * 100.0
              / NULLIF(f.NetSales, 0), 1)                            AS NOI,
        -- EBT margin (%)
        ROUND(f.EBT * 100.0 / NULLIF(f.NetSales, 0), 1)             AS EBT_Margin,
        -- NPM = 稅後淨利率 (%)
        ROUND(f.NetIncome * 100.0 / NULLIF(f.NetSales, 0), 1)       AS NPM,

        -- EPS
        f.EarningsPerShare                                           AS EPS,

        -- CashDiv (annual only)
        CASE WHEN f.Quarter = 0 THEN d.TotalCashPerShare ELSE NULL END AS CashDiv,
        -- Div = payout ratio (%)
        CASE WHEN f.Quarter = 0 AND f.EarningsPerShare > 0
             THEN ROUND(d.TotalCashPerShare * 100.0 / f.EarningsPerShare, 1)
             ELSE NULL END                                           AS [Div],
        -- Yld = dividend yield (%)  using (P_L+P_H)/2 as price
        CASE WHEN f.Quarter = 0
                  AND d.TotalCashPerShare IS NOT NULL
                  AND (pa.P_L + pa.P_H) > 0
             THEN ROUND(d.TotalCashPerShare * 200.0 / (pa.P_L + pa.P_H), 2)
             ELSE NULL END                                           AS Yld,

        -- BVPS
        ROUND(f.E_TotalEquity / NULLIF(f.E_CommonStock / 10.0, 0), 1) AS BVPS,

        -- Inv = Inventories / TotalAssets × 100  (%)
        ROUND(f.A_Inventories * 100.0 / NULLIF(f.A_TotalAssets, 0), 1) AS Inv,
        -- Inventory turnover = NetSales / Inventories  (times)
        ROUND(f.NetSales / NULLIF(f.A_Inventories, 0), 1)           AS Inv_T,
        -- ArR = AccountsReceivable / TotalAssets × 100  (%)
        ROUND(f.A_AccountsReceivable * 100.0 / NULLIF(f.A_TotalAssets, 0), 1) AS ArR,

        -- Equity (millions NTD)
        f.E_TotalEquity                                              AS Equity,

        -- PE (annual only, based on full-year EPS)
        CASE WHEN f.Quarter = 0 AND f.EarningsPerShare > 0
             THEN ROUND(pa.P_L / f.EarningsPerShare, 1) ELSE NULL END AS PE_L,
        CASE WHEN f.Quarter = 0 AND f.EarningsPerShare > 0
             THEN ROUND(pa.P_H / f.EarningsPerShare, 1) ELSE NULL END AS PE_H,

        -- Prices: annual row uses full-year H/L; quarterly uses quarterly H/L
        CASE WHEN f.Quarter = 0 THEN pa.P_L ELSE pq.P_L END         AS P_L,
        CASE WHEN f.Quarter = 0 THEN pa.P_H ELSE pq.P_H END         AS P_H,

        -- IsLatestRow flag for SSRS highlight (1 = most recent row)
        CASE WHEN ROW_NUMBER() OVER (ORDER BY f.Year ASC, f.Quarter ASC)
                  = COUNT(*) OVER ()
             THEN 1 ELSE 0 END                                       AS IsLatestRow

    FROM FinYoY f
    LEFT JOIN IRR_Calc   irr ON irr.Year  = f.Year
    LEFT JOIN PriceAnnual pa  ON pa.PYear  = f.Year
    LEFT JOIN PriceQtr    pq  ON pq.PYear  = f.Year AND pq.PQtr = f.Quarter
    LEFT JOIN DivData     d   ON d.DividendYear = f.Year
    ORDER BY f.Year ASC, f.Quarter ASC;
END
GO
