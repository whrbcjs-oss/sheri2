"""Monthly bank-ledger persistence, separate from the existing settlement databases."""
import hashlib
from pathlib import Path
import secrets
import collaboration as shared
from monthly_ledger import build_report,money


def connect(year):
    year=int(year)
    if not 2000<=year<=2100:raise ValueError('회계연도를 확인하세요.')
    shared.DATA.mkdir(parents=True,exist_ok=True)
    c=shared.connect(shared.DATA/f'lb_monthly_{year}.db')
    c.executescript('''
    CREATE TABLE IF NOT EXISTS monthly_imports(
      fiscal_year INTEGER NOT NULL,month INTEGER NOT NULL,source_name TEXT NOT NULL,
      source_sha256 TEXT NOT NULL,imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      imported_by TEXT NOT NULL,PRIMARY KEY(fiscal_year,month));
    CREATE TABLE IF NOT EXISTS monthly_ledger(
      id INTEGER PRIMARY KEY AUTOINCREMENT,fiscal_year INTEGER NOT NULL,month INTEGER NOT NULL,
      source_row INTEGER NOT NULL,posting_date TEXT NOT NULL,corporation TEXT,project TEXT,
      vendor TEXT,description TEXT,note TEXT,department TEXT,category TEXT,
      inflow TEXT NOT NULL,outflow TEXT NOT NULL,vat TEXT NOT NULL,
      UNIQUE(fiscal_year,month,source_row));
    CREATE TABLE IF NOT EXISTS monthly_settings(
      fiscal_year INTEGER PRIMARY KEY,opening_amount TEXT NOT NULL DEFAULT '0',
      opening_confirmed INTEGER NOT NULL DEFAULT 0,management_rate TEXT NOT NULL DEFAULT '4');
    CREATE TABLE IF NOT EXISTS monthly_adjustments(
      fiscal_year INTEGER NOT NULL,month INTEGER NOT NULL,report_row INTEGER NOT NULL,
      amount TEXT NOT NULL,reason TEXT NOT NULL,PRIMARY KEY(fiscal_year,month,report_row));
    ''')
    return shared.protect(c)


def available_years():
    result=[]
    for path in shared.DATA.glob('lb_monthly_*.db'):
        try:result.append(int(path.stem.rsplit('_',1)[1]))
        except ValueError:pass
    return sorted(result)


def imports(c):
    rows=c.execute('SELECT month,source_name,source_sha256,imported_at,imported_by FROM monthly_imports ORDER BY month').fetchall()
    return [dict(zip(['month','source','sha256','imported_at','imported_by'],r)) for r in rows]


def settings(c):
    row=c.execute('SELECT opening_amount,opening_confirmed,management_rate FROM monthly_settings').fetchone()
    return dict(zip(['opening_amount','opening_confirmed','management_rate'],row)) if row else {'opening_amount':'0','opening_confirmed':0,'management_rate':'4'}


def records(c):
    columns=['month','row','date','corporation','project','vendor','description','note','department','category','inflow','outflow','vat']
    return [dict(zip(columns,r)) for r in c.execute('SELECT month,source_row,posting_date,corporation,project,vendor,description,note,department,category,inflow,outflow,vat FROM monthly_ledger ORDER BY posting_date,source_row')]


def report(c,year):
    adjustments=[dict(zip(['month','report_row','amount','reason'],r)) for r in c.execute('SELECT month,report_row,amount,reason FROM monthly_adjustments ORDER BY month,report_row')]
    return build_report(int(year),records(c),imports(c),settings(c),adjustments)


def save_month(c,year,month,payload,original,token):
    user=shared.require_admin(token);year=int(year);month=int(month)
    if int(c.path.stem.rsplit('_',1)[1])!=year or not 1<=month<=12:raise ValueError('저장할 연도·월을 확인하세요.')
    entries=[r for r in payload['records'] if r['year']==year and r['month']==month]
    if not entries:raise ValueError('선택한 월의 원장 자료가 없습니다.')
    digest=hashlib.sha256(original).hexdigest()
    if digest!=payload['sha256']:raise ValueError('분석한 파일과 저장할 파일이 다릅니다.')
    current=c.execute('SELECT source_sha256 FROM monthly_imports WHERE fiscal_year=? AND month=?',(year,month)).fetchone()
    if current and current[0]==digest:return False
    columns=['corporation','project','vendor','description','note','department','category','inflow','outflow','vat']
    rows=[(year,month,r['row'],r['date'],*[r[k] for k in columns]) for r in entries]
    if current:shared.backup_database(c.path)
    directory=shared.STATE/'monthly-originals';directory.mkdir(parents=True,exist_ok=True)
    archive=directory/(digest+'.xlsx')
    if archive.exists() and hashlib.sha256(archive.read_bytes()).hexdigest()!=digest:raise ValueError('보관 원본의 무결성 오류입니다.')
    with c:
        c.execute('DELETE FROM monthly_ledger WHERE fiscal_year=? AND month=?',(year,month))
        c.execute('DELETE FROM monthly_imports WHERE fiscal_year=? AND month=?',(year,month))
        c.execute('INSERT INTO monthly_imports(fiscal_year,month,source_name,source_sha256,imported_by) VALUES(?,?,?,?,?)',
                  (year,month,payload['source'],digest,user['username']))
        c.executemany('''INSERT INTO monthly_ledger(fiscal_year,month,source_row,posting_date,
          corporation,project,vendor,description,note,department,category,inflow,outflow,vat)
          VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',rows)
        if not archive.exists():
            temp=archive.with_suffix('.'+secrets.token_hex(6)+'.tmp')
            try:temp.write_bytes(original);temp.replace(archive)
            finally:temp.unlink(missing_ok=True)
    return True


def save_settings(c,year,opening,rate):
    confirmed=bool(str(opening).strip())
    amount=money(opening) if confirmed else money(0);rate=money(rate)
    if not 0<=rate<=100:raise ValueError('관리비율은 0~100%로 입력하세요.')
    with c:
        c.execute('INSERT INTO monthly_settings VALUES(?,?,?,?) ON CONFLICT(fiscal_year) DO UPDATE SET opening_amount=excluded.opening_amount,opening_confirmed=excluded.opening_confirmed,management_rate=excluded.management_rate',
                  (int(year),str(amount),int(confirmed),str(rate)))


def save_insurance(c,year,month,amount,reason):
    amount=money(amount)
    if amount and not reason.strip():raise ValueError('원장외 보험료 조정 사유를 입력하세요.')
    if not c.execute('SELECT 1 FROM monthly_imports WHERE fiscal_year=? AND month=?',(year,month)).fetchone():raise ValueError('먼저 해당 월 원장을 저장하세요.')
    with c:
        for row in [8,16]:
            c.execute('INSERT INTO monthly_adjustments VALUES(?,?,?,?,?) ON CONFLICT(fiscal_year,month,report_row) DO UPDATE SET amount=excluded.amount,reason=excluded.reason',
                      (int(year),int(month),row,str(amount),reason.strip()))


def ledger(c):
    import pandas as pd
    return pd.read_sql_query('SELECT source_row AS 원장행,posting_date AS 날짜,month AS 월,corporation AS 법인,project AS 프로젝트,vendor AS 거래처,department AS 대분류,category AS 중분류,inflow AS 입금,outflow AS 출금,vat AS 부가세,description AS 적요,note AS 비고 FROM monthly_ledger ORDER BY posting_date,source_row',c)
