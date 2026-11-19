"""Directional company-pair exceptions, with date-based rates and reversible activation."""
import related_loan_calc as calc

def install(c):
 c.executescript('''CREATE TABLE IF NOT EXISTS rlc_exception_rules(id INTEGER PRIMARY KEY,lender_id INTEGER NOT NULL REFERENCES rlc_companies(id),borrower_id INTEGER NOT NULL REFERENCES rlc_companies(id),version INTEGER NOT NULL DEFAULT 1,deleted INTEGER NOT NULL DEFAULT 0,UNIQUE(lender_id,borrower_id));
 CREATE TABLE IF NOT EXISTS rlc_exception_rates(id INTEGER PRIMARY KEY,rule_id INTEGER NOT NULL REFERENCES rlc_exception_rules(id),effective_date TEXT NOT NULL,rate TEXT NOT NULL,kb TEXT,note TEXT NOT NULL,version INTEGER NOT NULL DEFAULT 1,deleted INTEGER NOT NULL DEFAULT 0);
 CREATE UNIQUE INDEX IF NOT EXISTS rlc_exception_active_date ON rlc_exception_rates(rule_id,effective_date) WHERE deleted=0;''')

def rule(c,lender,borrower):
 import related_loan_store as db
 return next(iter(db.rows(c,'SELECT * FROM rlc_exception_rules WHERE lender_id=? AND borrower_id=? AND deleted=0',(lender,borrower))),None)

def label(c,lender,borrower):
 import related_loan_store as db
 if rule(c,lender,borrower):
  names={r['id']:r['name'] for r in db.companies(c)}
  return names.get(borrower,str(borrower))+' 회사별 예외이율'
 return '공통이율' if c.execute('SELECT 1 FROM rlc_common_rates LIMIT 1').fetchone() else '기존 약정이율'

def rates(c,t):
 import related_loan_store as db
 selected=rule(c,t['lender_id'],t['borrower_id'])
 if not selected:return None
 active=db.rows(c,'SELECT * FROM rlc_exception_rates WHERE rule_id=? AND deleted=0 ORDER BY effective_date,id',(selected['id'],))
 active=active or [dict(id=-1,effective_date='2101-01-01',rate=None,kb=None)]
 return [dict(r,exception_rate=True,rate_policy=label(c,t['lender_id'],t['borrower_id']),deal_id=None,lender_id=t['lender_id'],borrower_id=t['borrower_id']) for r in active]

def save(c,lender,borrower,v,id=None,expected=None):
 import related_loan_store as db
 lender=int(lender);borrower=int(borrower)
 if lender==borrower or not {lender,borrower}<={r['id'] for r in db.companies(c)}:raise ValueError('서로 다른 활성 대여회사·차입회사를 선택하세요.')
 if v.get('rate') is None or not str(v['rate']).strip():raise ValueError('예외 연이율을 입력하세요. 무이자는 0입니다.')
 dt=calc.day(v['effective_date']).isoformat()
 if not 1990<=calc.day(dt).year<=2100:raise ValueError('적용일은 1990~2100년으로 입력하세요.')
 rate=db.percent(v['rate']);kb=db.percent(v['kb']) if v.get('kb') not in (None,'') else None
 with c:
  c.execute('DELETE FROM rlc_exception_rates WHERE id=-1')
  saved=db.rows(c,'SELECT * FROM rlc_exception_rules WHERE lender_id=? AND borrower_id=?',(lender,borrower))
  if saved and saved[0]['deleted']:raise ValueError('이 회사 조합은 예외 적용 해제 상태입니다. 예외 회사 복구에서 먼저 복구하세요.')
  if saved:rule_id=saved[0]['id']
  else:rule_id=c.execute('INSERT INTO rlc_exception_rules(lender_id,borrower_id) VALUES(?,?)',(lender,borrower)).lastrowid
  if id:
   old=db.one(c,'exception_rates',id);db.check_version(old,expected)
   if old['rule_id']!=rule_id:raise ValueError('이율의 회사 연결은 바꿀 수 없습니다. 기존 예외를 해제하고 정확한 회사 조합에 등록하세요.')
  if c.execute('SELECT 1 FROM rlc_exception_rates WHERE rule_id=? AND effective_date=? AND deleted=0 AND id<>?',(rule_id,dt,id or -1)).fetchone():raise ValueError('같은 적용일의 예외이율이 있습니다. 불러와 수정하세요.')
  args=(rule_id,dt,rate,kb,str(v.get('note','')))
  if id:c.execute('UPDATE rlc_exception_rates SET rule_id=?,effective_date=?,rate=?,kb=?,note=?,version=version+1 WHERE id=?',args+(id,))
  else:id=c.execute('INSERT INTO rlc_exception_rates(rule_id,effective_date,rate,kb,note) VALUES(?,?,?,?,?)',args).lastrowid
 return id
