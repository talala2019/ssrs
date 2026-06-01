"""Generate FinancialStatements.rdl for SSRS 2016"""

OUTPUT = r'C:\Users\tully\Workspaces\SSRS\InvestmentReportProject\InvestmentReportProject\FinancialStatements.rdl'

# (header_text, field_name, width_in, fmt, align, is_yoy)
# fmt: 'int','1dp','2dp','big'(comma no dp),'str'
COLS = [
    ('Year',      'Year',       0.28, 'int',  'Center', False),
    ('Q',         'Quarter',    0.20, 'int',  'Center', False),
    ('RoA',       'RoA',        0.33, '1dp',  'Right',  False),
    ('RoE',       'RoE',        0.33, '1dp',  'Right',  False),
    ('IRR',       'IRR',        0.35, '1dp',  'Right',  False),
    ('ICF',       'ICF',        0.35, '1dp',  'Right',  False),
    ('Debt',      'Debt',       0.35, '1dp',  'Right',  False),
    ('RDebt',     'RDebt',      0.35, '1dp',  'Right',  False),
    ('CR',        'CR',         0.33, '2dp',  'Right',  False),
    ('Sales',     'Sales',      0.72, 'big',  'Right',  False),
    ('YoY',       'SalesYoY',   0.33, '2dp',  'Right',  True),
    ('NetIncome', 'NetIncome',  0.60, 'big',  'Right',  False),
    ('YoY',       'NIYoY',      0.33, '2dp',  'Right',  True),
    ('PM',        'PM',         0.33, '1dp',  'Right',  False),
    ('GPM',       'GPM',        0.33, '1dp',  'Right',  False),
    ('NOI',       'NOI',        0.33, '1dp',  'Right',  False),
    ('EBT',       'EBT_Margin', 0.33, '1dp',  'Right',  False),
    ('NPM',       'NPM',        0.33, '1dp',  'Right',  False),
    ('EPS',       'EPS',        0.38, '2dp',  'Right',  False),
    ('CashDiv',   'CashDiv',    0.40, '2dp',  'Right',  False),
    ('Div%',      'Div',        0.35, '1dp',  'Right',  False),
    ('Yld%',      'Yld',        0.33, '2dp',  'Right',  False),
    ('BVPS',      'BVPS',       0.38, '1dp',  'Right',  False),
    ('Inv',       'Inv',         0.35, '1dp',  'Right',  False),
    ('Inv_T',     'Inv_T',      0.33, '1dp',  'Right',  False),
    ('ArR',       'ArR',         0.35, '1dp',  'Right',  False),
    ('Equity',    'Equity',     0.62, 'big',  'Right',  False),
    ('PE_L',      'PE_L',       0.33, '1dp',  'Right',  False),
    ('PE_H',      'PE_H',       0.33, '1dp',  'Right',  False),
    ('P_L',       'P_L',        0.35, '1dp',  'Right',  False),
    ('P_H',       'P_H',        0.35, '1dp',  'Right',  False),
]

ALL_FIELDS = ['Year','Quarter','Type','ChtName','RoA','RoE','IRR','ICF','Debt','RDebt','CR',
              'Sales','SalesYoY','NetIncome','NIYoY','PM','GPM','NOI','EBT_Margin','NPM',
              'EPS','CashDiv','Div','Yld','BVPS','Inv','Inv_T','ArR','Equity',
              'PE_L','PE_H','P_L','P_H','IsLatestRow']

WIDTH_SCALE = 1.5
TOTAL_W = sum(c[2] * WIDTH_SCALE for c in COLS)
FONT = '10pt'
HDR_BG = '#404040'        # dark grey header
HDR_COLOR = 'White'
ANNUAL_BG = '#C6D9F1'     # mid-blue for annual rows
LATEST_BG = '#FF9900'     # amber — most recent row highlight
LATEST_COLOR = 'White'
BORDER = '#888888'
PAD = '<PaddingLeft>3pt</PaddingLeft><PaddingRight>3pt</PaddingRight><PaddingTop>2pt</PaddingTop><PaddingBottom>2pt</PaddingBottom>'
HDR_ROW_H = '0.28in'
DATA_ROW_H = '0.24in'


def val_expr(field, fmt):
    f = f'Fields!{field}.Value'
    null_check = f'IsNothing({f})'
    if fmt == 'int':
        return f'=IIF({null_check},"",CStr(CInt({f})))'
    elif fmt == '1dp':
        return f'=IIF({null_check},"",Format(CDbl({f}),"0.0"))'
    elif fmt == '2dp':
        return f'=IIF({null_check},"",Format(CDbl({f}),"0.00"))'
    elif fmt == 'big':
        return f'=IIF({null_check},"",Format(CDbl({f}),"#,##0"))'
    return f'=IIF({null_check},"",CStr({f}))'


def xml_val(expr):
    # Escape for XML text content
    return expr.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def hdr_cell(i, hdr, align):
    return f'''              <TablixCell><CellContents><Textbox Name="h{i}">
                <CanGrow>false</CanGrow><KeepTogether>true</KeepTogether>
                <Paragraphs><Paragraph><TextRuns><TextRun><Value>{hdr}</Value>
                  <Style><FontSize>{FONT}</FontSize><FontWeight>Bold</FontWeight><Color>{HDR_COLOR}</Color></Style>
                </TextRun></TextRuns><Style><TextAlign>{align}</TextAlign></Style></Paragraph></Paragraphs>
                <Style><Border><Color>{BORDER}</Color><Style>Solid</Style></Border>
                <BackgroundColor>{HDR_BG}</BackgroundColor><VerticalAlign>Middle</VerticalAlign>{PAD}</Style>
              </Textbox></CellContents></TablixCell>'''


def data_cell(i, field, fmt, align, is_yoy):
    val = xml_val(val_expr(field, fmt))
    is_latest = 'Fields!IsLatestRow.Value=1'
    # font color: latest row white, YoY green/red, else black
    if is_yoy:
        color = xml_val(
            f'=IIF({is_latest},"{LATEST_COLOR}",'
            f'IIF(IsNothing(Fields!{field}.Value),"Black",'
            f'IIF(CDbl(Fields!{field}.Value)>=1,"DarkGreen","Red")))'
        )
    else:
        color = xml_val(f'=IIF({is_latest},"{LATEST_COLOR}","Black")')
    bg = xml_val(
        f'=IIF({is_latest},"{LATEST_BG}",'
        f'IIF(Fields!Quarter.Value=0,"{ANNUAL_BG}","White"))'
    )
    fw = xml_val(f'=IIF({is_latest},"Bold",IIF(Fields!Quarter.Value=0,"Bold","Normal"))')
    return f'''              <TablixCell><CellContents><Textbox Name="d{i}">
                <CanGrow>false</CanGrow><KeepTogether>true</KeepTogether>
                <Paragraphs><Paragraph><TextRuns><TextRun><Value>{val}</Value>
                  <Style><FontSize>{FONT}</FontSize><FontWeight>{fw}</FontWeight><Color>{color}</Color></Style>
                </TextRun></TextRuns><Style><TextAlign>{align}</TextAlign></Style></Paragraph></Paragraphs>
                <Style><Border><Color>{BORDER}</Color><Style>Solid</Style></Border>
                <BackgroundColor>{bg}</BackgroundColor><VerticalAlign>Middle</VerticalAlign>{PAD}</Style>
              </Textbox></CellContents></TablixCell>'''


def fields_xml():
    lines = []
    for f in ALL_FIELDS:
        lines.append(f'          <Field Name="{f}"><DataField>{f}</DataField><rd:TypeName>System.Object</rd:TypeName></Field>')
    return '\n'.join(lines)


def tablix_cols():
    return '\n'.join(f'            <TablixColumn><Width>{c[2]*WIDTH_SCALE:.2f}in</Width></TablixColumn>' for c in COLS)


def hdr_row():
    cells = '\n'.join(hdr_cell(i, c[0], c[4]) for i, c in enumerate(COLS))
    return f'''          <TablixRow>
            <Height>{HDR_ROW_H}</Height>
            <TablixCells>
{cells}
            </TablixCells>
          </TablixRow>'''


def data_row():
    cells = '\n'.join(data_cell(i, c[1], c[3], c[4], c[5]) for i, c in enumerate(COLS))
    return f'''          <TablixRow>
            <Height>{DATA_ROW_H}</Height>
            <TablixCells>
{cells}
            </TablixCells>
          </TablixRow>'''


def col_hierarchy():
    members = '\n'.join('            <TablixMember/>' for _ in COLS)
    return f'''          <TablixMembers>
{members}
          </TablixMembers>'''


PAGE_W = max(TOTAL_W + 0.5, 12.0)

rdl = f'''<?xml version="1.0" encoding="utf-8"?>
<Report MustUnderstand="df" xmlns="http://schemas.microsoft.com/sqlserver/reporting/2016/01/reportdefinition" xmlns:rd="http://schemas.microsoft.com/SQLServer/reporting/reportdesigner" xmlns:df="http://schemas.microsoft.com/sqlserver/reporting/2016/01/reportdefinition/defaultfontfamily">
  <df:DefaultFontFamily>Segoe UI</df:DefaultFontFamily>
  <AutoRefresh>0</AutoRefresh>

  <DataSources>
    <DataSource Name="DataSource_localhost">
      <DataSourceReference>DataSource_localhost</DataSourceReference>
      <rd:SecurityType>None</rd:SecurityType>
      <rd:DataSourceID>56cd27f5-46d2-4105-a744-8706f1cbd54f</rd:DataSourceID>
    </DataSource>
  </DataSources>

  <DataSets>
    <DataSet Name="FinancialData">
      <Query>
        <DataSourceName>DataSource_localhost</DataSourceName>
        <QueryParameters>
          <QueryParameter Name="@symbol">
            <Value>=Parameters!symbol.Value</Value>
          </QueryParameter>
        </QueryParameters>
        <CommandText>EXEC sp_FinancialStatements @symbol</CommandText>
      </Query>
      <Fields>
{fields_xml()}
      </Fields>
    </DataSet>
  </DataSets>

  <ReportParameters>
    <ReportParameter Name="symbol">
      <DataType>String</DataType>
      <Prompt>Symbol (e.g. 2317 or 2317.TW)</Prompt>
    </ReportParameter>
  </ReportParameters>

  <ReportSections>
    <ReportSection>
      <Body>
        <ReportItems>

          <Textbox Name="ReportTitle">
            <CanGrow>true</CanGrow><KeepTogether>true</KeepTogether>
            <Paragraphs><Paragraph><TextRuns><TextRun>
              <Value>=First(Fields!ChtName.Value,"FinancialData") &amp; "  " &amp; Parameters!symbol.Value &amp; "  Financial Statements"</Value>
              <Style><FontSize>14pt</FontSize><FontWeight>Bold</FontWeight></Style>
            </TextRun></TextRuns></Paragraph></Paragraphs>
            <rd:DefaultName>ReportTitle</rd:DefaultName>
            <Top>0in</Top><Left>0in</Left>
            <Height>0.4in</Height><Width>{TOTAL_W:.2f}in</Width>
            <Style><PaddingLeft>4pt</PaddingLeft><PaddingBottom>4pt</PaddingBottom></Style>
          </Textbox>

          <Tablix Name="FinTable">
            <TablixBody>
              <TablixColumns>
{tablix_cols()}
              </TablixColumns>
              <TablixRows>
{hdr_row()}
{data_row()}
              </TablixRows>
            </TablixBody>

            <TablixColumnHierarchy>
{col_hierarchy()}
            </TablixColumnHierarchy>

            <TablixRowHierarchy>
              <TablixMembers>
                <TablixMember>
                  <KeepWithGroup>After</KeepWithGroup>
                  <RepeatOnNewPage>true</RepeatOnNewPage>
                  <KeepTogether>true</KeepTogether>
                </TablixMember>
                <TablixMember>
                  <Group Name="FinTable_Details"/>
                  <TablixMembers>
                    <TablixMember/>
                  </TablixMembers>
                </TablixMember>
              </TablixMembers>
            </TablixRowHierarchy>

            <DataSetName>FinancialData</DataSetName>
            <Top>0.45in</Top><Left>0in</Left>
            <Height>0.4in</Height><Width>{TOTAL_W:.2f}in</Width>
            <Style/>
          </Tablix>

        </ReportItems>
        <Height>6in</Height>
        <Style/>
      </Body>
      <Width>{TOTAL_W:.2f}in</Width>
      <Page>
        <PageWidth>{PAGE_W:.2f}in</PageWidth>
        <PageHeight>8.5in</PageHeight>
        <TopMargin>0.25in</TopMargin>
        <BottomMargin>0.25in</BottomMargin>
        <LeftMargin>0.25in</LeftMargin>
        <RightMargin>0.25in</RightMargin>
      </Page>
    </ReportSection>
  </ReportSections>

  <ReportParametersLayout>
    <GridLayoutDefinition>
      <NumberOfColumns>1</NumberOfColumns>
      <NumberOfRows>1</NumberOfRows>
      <CellDefinitions>
        <CellDefinition>
          <ColumnIndex>0</ColumnIndex>
          <RowIndex>0</RowIndex>
          <ParameterName>symbol</ParameterName>
        </CellDefinition>
      </CellDefinitions>
    </GridLayoutDefinition>
  </ReportParametersLayout>
  <Language>zh-TW</Language>
  <ConsumeContainerWhitespace>true</ConsumeContainerWhitespace>
  <rd:ReportUnitType>Inch</rd:ReportUnitType>
  <rd:ReportID>a1b2c3d4-e5f6-7890-abcd-ef1234567890</rd:ReportID>
</Report>'''

with open(OUTPUT, 'w', encoding='utf-8') as f:
    f.write(rdl)

print(f"Generated: {OUTPUT}")
print(f"Total table width: {TOTAL_W:.2f} in")
print(f"Columns: {len(COLS)}")
