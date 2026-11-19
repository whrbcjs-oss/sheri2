"""Tolerant XLSX/CSV ledger reader with explicit preview before persistence."""
from io import BytesIO,StringIO
from pathlib import Path
import csv,re,sys
from datetime import date,datetime
import openpyxl
import corporate_close_calc as calc

ALIASES={
 'date':['기표일자','일자','거래일자','날짜'],
 'account':['계정과목','계정명','과목명','과목'],
 'description':['적요란','적요사항','적요','내용'],
 'debit':['차변금액','차변'], 'credit':['대변금액','대변'],
 'amount':['당기잔액','잔액','합계금액','금액'],
 'business':['사업부','부문','관리항목','프로젝트명','프로젝트','공사명','공사현장','현장명','현장'],
 'counterparty':['거래처명','거래처','상호']}
def norm(v):return re.sub(r'[\s\n\r()·._-]','',str(v or '')).lower()
def match_header(row):
    found={}
    for i,v in enumerate(row):
        n=norm(v)
        for key,names in ALIASES.items():
            if key=='amount' and ('차변' in n or '대변' in n):continue
            if key not in found and any(norm(x)==n or norm(x) in n for x in names):found[key]=i
    score=sum(k in found for k in ['account','description','amount','debit','credit'])
    return found,score
def number(v):
    if v in (None,'','-'):return 0
    if isinstance(v,(int,float)):return calc.won(v)
    text=str(v).strip().replace(',','').replace('(','-').replace(')','')
    try:return calc.won(text)
    except Exception:return 0
def day(v):
    if isinstance(v,(date,datetime)):return v.strftime('%Y-%m-%d')
    text=str(v or '').strip().replace('/','-').replace('.','-')
    return text[:10]
def parse_matrix(matrix):
    best=({},-1,-1)
    for i,row in enumerate(matrix[:40]):
        found,score=match_header(row)
        if score>best[1]:best=(found,score,i)
    cols,score,header=best
    if score<2 or 'account' not in cols:raise ValueError('계정과목과 금액 또는 차변·대변 열을 찾지 못했습니다. 원장 표의 제목행을 확인하세요.')
    out=[]
    for row in matrix[header+1:]:
        def val(key):return row[cols[key]] if key in cols and cols[key]<len(row) else None
        account=str(val('account') or '').strip();description=str(val('description') or '').strip()
        if not account or account in ['합계','총계']:continue
        debit=number(val('debit')) if 'debit' in cols else None
        credit=number(val('credit')) if 'credit' in cols else None
        if 'amount' in cols:amount=number(val('amount'))
        else:amount=max((debit or 0),(credit or 0),key=abs)
        if not amount and not description:continue
        # Keep the original debit and credit separately.  ``amount`` may be a
        # running balance in accounting ledgers, so consumers must not use it
        # for non-operating income/expense when side columns are available.
        out.append({'date':day(val('date')),'account':account,'description':description,
                    'debit':debit,'credit':credit,'amount':amount,
                    'business':str(val('business') or '').strip(),'counterparty':str(val('counterparty') or '').strip(),'classification':''})
    if not out:raise ValueError('가져올 원장 행이 없습니다.')
    return out
def parse(name,content,sheet=None):
    lower=name.lower()
    if lower.endswith('.csv'):
        text=content.decode('utf-8-sig',errors='replace');return parse_matrix(list(csv.reader(StringIO(text))))
    if lower.endswith('.xls'):
        try:
            import xlrd
        except ImportError:
            wheel=Path(__file__).resolve().parent/'vendor'/'xlrd-2.0.2-py2.py3-none-any.whl'
            if wheel.is_file() and str(wheel) not in sys.path:sys.path.insert(0,str(wheel))
            try:import xlrd
            except ImportError as e:raise ValueError('XLS 원장 판독 모듈을 찾지 못했습니다. 최신 업데이트를 다시 적용하세요.') from e
        try:book=xlrd.open_workbook(file_contents=content,on_demand=True)
        except Exception as e:raise ValueError('XLS 파일을 열 수 없습니다. 파일이 손상되었거나 실제 Excel 97-2003 형식인지 확인하세요.') from e
        choices=[book.sheet_by_name(sheet)] if sheet and sheet in book.sheet_names() else [book.sheet_by_index(i) for i in range(book.nsheets)]
        errors=[]
        for ws in choices:
            matrix=[]
            for i in range(ws.nrows):
                converted=[]
                for cell in ws.row(i):
                    if cell.ctype==xlrd.XL_CELL_DATE:
                        try:value=xlrd.xldate.xldate_as_datetime(cell.value,book.datemode)
                        except Exception:value=cell.value
                    else:value=cell.value
                    converted.append(value)
                matrix.append(converted)
            try:return parse_matrix(matrix)
            except ValueError as e:errors.append(ws.name+': '+str(e))
        raise ValueError('XLS 원장 형식을 확인하세요. '+'; '.join(errors[:3]))
    if not lower.endswith('.xlsx'):raise ValueError('XLS, XLSX 또는 CSV 원장만 업로드할 수 있습니다.')
    book=openpyxl.load_workbook(BytesIO(content),data_only=True,read_only=True)
    choices=[book[sheet]] if sheet and sheet in book.sheetnames else list(book)
    errors=[]
    for ws in choices:
        try:return parse_matrix([list(r) for r in ws.iter_rows(values_only=True)])
        except ValueError as e:errors.append(ws.title+': '+str(e))
    raise ValueError('원장 형식을 확인하세요. '+'; '.join(errors[:3]))

STANDARD_RULES={
 'construction_revenue':['공사수입','도급공사수입'], 'service_revenue':['용역수입'],
 'cost':['도급공사매출원가','공사매출원가','매출원가'], 'sga':['판매비와일반관리비','판관비'],
 'nonop_income':['영업외수익'], 'nonop_expense':['영업외비용'],
 'prepaid_corp_interim':['법인세중간예납','법인세중간납부'],
 'prepaid_corp_withholding':['법인세원천납부','법인세원천징수'],
 'prepaid_local':['지방소득세기납부','지방세기납부']}
INCOME_KEYS={'construction_revenue','service_revenue','nonop_income'}
DEBIT_KEYS={'cost','sga','nonop_expense','prepaid_corp_interim','prepaid_corp_withholding','prepaid_local'}
def account_key(account):
    a=norm(account)
    for key,names in STANDARD_RULES.items():
        if any(norm(n) in a for n in names):return key
    if any(norm(n) in a for n in ['잡이익','처분이익']):return 'nonop_income'
    if any(norm(n) in a for n in ['잡손실','처분손실','이자비용','기부금']):return 'nonop_expense'
    return ''
def effective_amount(row,import_kind=''):
    """Return transaction turnover, never a running balance when sides exist."""
    has_debit=row.get('debit') is not None;has_credit=row.get('credit') is not None
    if not (has_debit or has_credit):return number(row.get('amount'))
    key=account_key(row.get('account'))
    if key in INCOME_KEYS or (not key and import_kind=='영업외수익'):return number(row.get('credit'))
    if key in DEBIT_KEYS or (not key and import_kind=='영업외비용'):return number(row.get('debit'))
    debit=number(row.get('debit'));credit=number(row.get('credit'))
    return debit if abs(debit)>=abs(credit) else credit
def aggregate(rows):
    out={k:0 for k in STANDARD_RULES}
    for r in rows:
        key=account_key(r.get('account'))
        if key:out[key]+=effective_amount(r,r.get('kind',''))
    return out
