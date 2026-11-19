"""Separate intercompany ledger with soft deletion, monthly locks and frozen batches."""
import json,base64,hashlib,re
from datetime import date
import collaboration as shared
import related_loan_calc as calc
D=calc.D

def dump(v):return json.dumps(v,ensure_ascii=False,sort_keys=True,default=str)
def rows(c,q,args=()):
 r=c.execute(q,args);return [dict(zip([x[0] for x in r.description],v)) for v in r]
def connect():
 shared.DATA.mkdir(parents=True,exist_ok=True)
 c=shared.connect(shared.DATA/'related_loans.db')
 c.executescript('''
 CREATE TABLE IF NOT EXISTS rlc_companies(id INTEGER PRIMARY KEY,name TEXT NOT NULL UNIQUE,payload TEXT NOT NULL,version INTEGER NOT NULL DEFAULT 1,deleted INTEGER NOT NULL DEFAULT 0);
 CREATE TABLE IF NOT EXISTS rlc_deals(id INTEGER PRIMARY KEY,number TEXT NOT NULL UNIQUE,lender_id INTEGER NOT NULL REFERENCES rlc_companies(id),borrower_id INTEGER NOT NULL REFERENCES rlc_companies(id),payload TEXT NOT NULL,version INTEGER NOT NULL DEFAULT 1,deleted INTEGER NOT NULL DEFAULT 0);
 CREATE TABLE IF NOT EXISTS rlc_events(id INTEGER PRIMARY KEY,deal_id INTEGER NOT NULL REFERENCES rlc_deals(id),event_date TEXT NOT NULL,kind TEXT NOT NULL,principal TEXT NOT NULL,interest TEXT NOT NULL,note TEXT NOT NULL,version INTEGER NOT NULL DEFAULT 1,deleted INTEGER NOT NULL DEFAULT 0);
 CREATE TABLE IF NOT EXISTS rlc_rates(id INTEGER PRIMARY KEY,deal_id INTEGER REFERENCES rlc_deals(id),lender_id INTEGER NOT NULL REFERENCES rlc_companies(id),borrower_id INTEGER NOT NULL REFERENCES rlc_companies(id),effective_date TEXT NOT NULL,rate TEXT NOT NULL,kb TEXT,note TEXT NOT NULL,version INTEGER NOT NULL DEFAULT 1,deleted INTEGER NOT NULL DEFAULT 0);
 CREATE TABLE IF NOT EXISTS rlc_months(id INTEGER PRIMARY KEY,deal_id INTEGER NOT NULL REFERENCES rlc_deals(id),month TEXT NOT NULL,payload TEXT NOT NULL,final INTEGER NOT NULL DEFAULT 0,version INTEGER NOT NULL DEFAULT 1,UNIQUE(deal_id,month));
 CREATE TABLE IF NOT EXISTS rlc_files(id INTEGER PRIMARY KEY,deal_id INTEGER NOT NULL REFERENCES rlc_deals(id),name TEXT NOT NULL,mime TEXT NOT NULL,content TEXT NOT NULL,digest TEXT NOT NULL,size INTEGER NOT NULL,version INTEGER NOT NULL DEFAULT 1,deleted INTEGER NOT NULL DEFAULT 0);
 CREATE TABLE IF NOT EXISTS rlc_batches(id INTEGER PRIMARY KEY,number TEXT NOT NULL UNIQUE,payload TEXT NOT NULL,actor TEXT NOT NULL,deleted INTEGER NOT NULL DEFAULT 0,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
 ''')
 c.execute('CREATE TABLE IF NOT EXISTS rlc_common_rates(id INTEGER PRIMARY KEY,effective_date TEXT NOT NULL,rate TEXT NOT NULL,kb TEXT,note TEXT NOT NULL DEFAULT \'\',version INTEGER NOT NULL DEFAULT 1,deleted INTEGER NOT NULL DEFAULT 0)')
 c.execute('CREATE UNIQUE INDEX IF NOT EXISTS rlc_common_active_date ON rlc_common_rates(effective_date) WHERE deleted=0')
 c.execute('CREATE TABLE IF NOT EXISTS rlc_change_reasons(id INTEGER PRIMARY KEY,kind TEXT NOT NULL,entity_id INTEGER NOT NULL,reason TEXT NOT NULL,at TEXT DEFAULT CURRENT_TIMESTAMP)')
 import related_loan_import
 related_loan_import.install(c)
 import related_loan_ledger
 related_loan_ledger.install(c)
 import related_loan_exceptions
 related_loan_exceptions.install(c)
 return shared.protect(c)

def entities(c,table,deleted=False):
 if table not in ['companies','deals','events','rates','common_rates','exception_rules','exception_rates','files','batches']:raise ValueError('자료 구분을 확인하세요.')
 out=rows(c,'SELECT * FROM rlc_'+table+' WHERE deleted=? ORDER BY id',(int(deleted),))
 return [dict(r,**(json.loads(r.pop('payload')) if 'payload' in r else {})) for r in out]
def companies(c,deleted=False):return entities(c,'companies',deleted)
def deals(c,company=None,deleted=False):return [r for r in entities(c,'deals',deleted) if company is None or company in (r['lender_id'],r['borrower_id'])]
def one(c,kind,id,deleted=False):
 r=next((r for r in entities(c,kind,deleted) if r['id']==id),None)
 if not r:raise ValueError('선택 자료를 다시 조회하세요.')
 return r
def events(c,id):return [r for r in entities(c,'events') if r['deal_id']==id]
def ledger_template(c,t):
 if not t.get('ledger_source'):return None
 if t.get('ledger_template_id'):return int(t['ledger_template_id'])
 # Earlier uploads stored the source agreement in the import manifest, not the deal.
 for row in rows(c,'SELECT payload FROM rlc_ledger_imports ORDER BY id DESC'):
  p=json.loads(row['payload'])
  if t['id'] in p.get('newids',[]):return p['plan']['template']
 return None

def rates(c,t,_seen=None):
 import related_loan_exceptions
 exception=related_loan_exceptions.rates(c,t)
 if exception is not None:return exception
 if c.execute('SELECT 1 FROM rlc_common_rates LIMIT 1').fetchone():
  active=entities(c,'common_rates')
  return [dict(r,common_rate=True,deal_id=None,lender_id=None,borrower_id=None) for r in active] or [dict(id=-1,effective_date='2101-01-01',rate=None,kb=None,common_rate=True,deal_id=None,lender_id=None,borrower_id=None)]
 seen=set(_seen or [])
 if t['id'] in seen:raise ValueError('원장 기준 약정 연결이 순환합니다. 원본 약정을 확인하세요.')
 seen.add(t['id']);all_rates=entities(c,'rates')
 result=[r for r in all_rates if r['deal_id']==t['id'] or r['deal_id'] is None and (r['lender_id'],r['borrower_id'])==(t['lender_id'],t['borrower_id'])]
 source=ledger_template(c,t)
 if t.get('ledger_source') and any(r['deal_id'] is None for r in result):
  return [r for r in result if r['deal_id'] is None or not str(r.get('note','')).startswith('원장 기준 약정 ')]
 if source:
  original=one(c,'deals',source)
  if (original['lender_id'],original['borrower_id'])!=(t['lender_id'],t['borrower_id']):raise ValueError('원장 기준 약정의 회사 연결을 확인하세요.')
  result=[r for r in result if not (r['deal_id']==t['id'] and str(r.get('note','')).startswith('원장 기준 약정 '))]
  result += [dict(r,deal_id=t['id'],ledger_template=True) for r in rates(c,original,seen) if r['deal_id']==source]
 return result

def ledger_depends(c,t,id):
 seen=set()
 while t.get('ledger_source'):
  source=ledger_template(c,t)
  if source==id:return True
  if not source or source in seen:return False
  seen.add(source);t=one(c,'deals',source)
 return False

def check_version(r,expected):
 if expected!=r['version']:raise ValueError('자료가 변경되었습니다. 다시 불러오세요.')
def lock(c,id,when=None):
 final=rows(c,'SELECT month FROM rlc_months WHERE deal_id=? AND final=1',(id,))
 if any(when is None or calc.day(when)<=calc.month_end(r['month']) for r in final):raise ValueError('확정된 월 이자계산서에 영향을 줍니다. 관리자 월 확정 해제 후 수정·삭제·복구하세요.')
def integer(v,positive=False):
 n=D(v)
 if n!=n.to_integral_value() or n<0 or positive and n==0:raise ValueError('금액은 올바른 원 단위 정수로 입력하세요.')
 return str(n)
def percent(v):
 n=D(v)
 if not 0<=n<=100:raise ValueError('연이율은 0~100%로 입력하세요.')
 return str(n)
def timeline(t,es):
 by_date={}
 for e in es:
  if calc.day(e['event_date'])<calc.day(t['start']):raise ValueError('입출금일은 거래일 이후여야 합니다.')
  by_date.setdefault(e['event_date'],D(0));by_date[e['event_date']]+=calc.change(e)
 total=D(t['principal'])
 for d in sorted(by_date):
  total+=by_date[d]
  if total<0:raise ValueError('원금 상환·회수액이 잔액보다 큽니다.')

def save_company(c,v,id=None,expected=None):
 v={k:x for k,x in v.items() if k not in ['id','version','deleted','payload']};name=str(v.pop('name','')).strip()
 if not name:raise ValueError('회사명을 입력하세요.')
 if len(name)>100:raise ValueError('회사명은 100자 이하로 입력하세요.')
 directors=[]
 for r in v.get('directors',[]):
  name_=str(r.get('name','') or '').strip();role=str(r.get('role','') or '').strip()
  if name_:
   if not role:raise ValueError('이사 직위를 입력하세요.')
   directors.append(dict(name=name_,role=role,present=bool(r.get('present',True))))
 if len({(r['role'],r['name']) for r in directors})!=len(directors):raise ValueError('중복 이사가 있습니다.')
 total=int(v.get('total_directors',len(directors)))
 if total<len(directors) or not 0<=total<=100:raise ValueError('이사 총수와 명단을 확인하세요.')
 v.update(directors=directors,total_directors=total)
 seal=v.get('seal','')
 if seal:
  from PIL import Image
  from io import BytesIO
  try:
   header,content=seal.split(',',1);blob=base64.b64decode(content,validate=True)
   if header not in ['data:image/png;base64','data:image/jpeg;base64'] or len(blob)>1024*1024:raise ValueError()
   with Image.open(BytesIO(blob)) as im:
    if max(im.size)>3000 or im.format not in ['PNG','JPEG']:raise ValueError()
    im.verify()
  except Exception:raise ValueError('직인은 1MB 이하 정상 PNG/JPG로 등록하세요.')
 if c.execute('SELECT 1 FROM rlc_companies WHERE name=? AND id<>?',(name,id or -1)).fetchone():raise ValueError('이미 등록된 회사명입니다. 삭제 목록도 확인하세요.')
 with c:
  if id:check_version(one(c,'companies',id),expected);c.execute('UPDATE rlc_companies SET name=?,payload=?,version=version+1 WHERE id=?',(name,dump(v),id))
  else:id=c.execute('INSERT INTO rlc_companies(name,payload) VALUES(?,?)',(name,dump(v))).lastrowid
 return id

def save_deal(c,v,id=None,expected=None):
 v={k:x for k,x in v.items() if k not in ['id','version','deleted','payload']};lender=int(v.pop('lender_id'));borrower=int(v.pop('borrower_id'));known={r['id'] for r in companies(c)}
 if lender==borrower or not {lender,borrower}<=known:raise ValueError('서로 다른 활성 대여·차입 회사를 선택하세요.')
 number=str(v.pop('number','')).strip()
 if not number:raise ValueError('관리번호를 입력하세요.')
 for k in ['agreement_date','lender_meeting','borrower_meeting']:
  if v.get(k):v[k]=calc.day(v[k]).isoformat()
  else:v.pop(k,None)
 for k in ['start','interest_start','maturity']:v[k]=calc.day(v[k]).isoformat()
 if not v['start']<=v['interest_start']<=v['maturity']:raise ValueError('거래일 ≤ 이자계산 시작일 ≤ 만기일이어야 합니다.')
 if not 1990<=calc.day(v['start']).year<=2100 or calc.day(v['maturity']).year>2100:raise ValueError('거래기간은 1990~2100년으로 입력하세요.')
 v['principal']=integer(v['principal'],True)
 if v.get('rate_mode','거래별') not in ['거래별','회사 기본이율']:raise ValueError('이율 적용방식을 확인하세요.')
 if v.get('rate_mode','거래별')=='거래별':
  if v.get('rate') in (None,''):raise ValueError('약정 연이율을 입력하세요. 무이자는 0입니다.')
  v['rate']=percent(v['rate'])
 if v.get('kb') not in (None,''):v['kb']=percent(v['kb'])
 if v.get('basis','365') not in ['365','실제연도'] or v.get('rounding','절사') not in ['절사','반올림'] or v.get('rounding_unit','월 합계') not in ['월 합계','구간별']:raise ValueError('일수·원 단위 처리 기준을 확인하세요.')
 for k in ['first_inclusive','repay_inclusive']:v[k]=bool(v.get(k,True))
 if c.execute('SELECT 1 FROM rlc_deals WHERE number=? AND id<>?',(number,id or -1)).fetchone():raise ValueError('이미 사용한 관리번호입니다.')
 with c:
  if id:
   old=one(c,'deals',id);check_version(old,expected);lock(c,id)
   for dependent in deals(c):
    if ledger_depends(c,dependent,id):
     lock(c,dependent['id'])
     if (old['lender_id'],old['borrower_id'])!=(lender,borrower):raise ValueError('연결된 원장 거래가 있어 회사 연결을 바꿀 수 없습니다.')
   for k in ['import_rate_until','import_source','ledger_source','ledger_template_id']:
    if old.get(k):v[k]=old[k]
   if old.get('maturity_unverified') and not v.get('maturity_verified'):raise ValueError('원본 약정으로 만기를 확인하고 확인 체크하세요.')
   if v.get('maturity_verified'):v['maturity_unverified']=False
   if (old['lender_id'],old['borrower_id'])!=(lender,borrower) and (events(c,id) or rows(c,'SELECT id FROM rlc_rates WHERE deal_id=? AND deleted=0',(id,))):raise ValueError('입출금·이율 연결 자료가 있는 거래는 회사 연결을 변경할 수 없습니다.')
   timeline(v,events(c,id));c.execute('UPDATE rlc_deals SET number=?,lender_id=?,borrower_id=?,payload=?,version=version+1 WHERE id=?',(number,lender,borrower,dump(v),id))
  else:id=c.execute('INSERT INTO rlc_deals(number,lender_id,borrower_id,payload) VALUES(?,?,?,?)',(number,lender,borrower,dump(v))).lastrowid
 return id

def save_event(c,id,v,entry=None,expected=None):
 t=one(c,'deals',id);v=dict(v);v['event_date']=calc.day(v['event_date']).isoformat();v['principal']=integer(v.get('principal',0));v['interest']=integer(v.get('interest',0))
 if not 1990<=calc.day(v['event_date']).year<=2100:raise ValueError('입출금일은 1990~2100년으로 입력하세요.')
 if v['kind'] not in ['추가원금','원금상환·회수','이자지급·수취','원리금정산']:raise ValueError('입출금 구분을 확인하세요.')
 if v['kind']=='추가원금' and D(v['interest']) or v['kind']=='이자지급·수취' and D(v['principal']) or v['kind']=='원금상환·회수' and D(v['interest']):raise ValueError('선택 구분에 해당하는 원금 또는 이자만 입력하세요.')
 if D(v['principal'])+D(v['interest'])<=0:raise ValueError('입출금액을 입력하세요.')
 with c:
  lock(c,id,v['event_date'])
  if entry:
   old=one(c,'events',entry);check_version(old,expected)
   if old['deal_id']!=id:raise ValueError('거래 연결을 확인하세요.')
   lock(c,id,old['event_date'])
  timeline(t,[r for r in events(c,id) if r['id']!=entry]+[dict(v,id=entry or -1)])
  args=(id,v['event_date'],v['kind'],v['principal'],v['interest'],str(v.get('note','')))
  if entry:c.execute('UPDATE rlc_events SET deal_id=?,event_date=?,kind=?,principal=?,interest=?,note=?,version=version+1 WHERE id=?',args+(entry,))
  else:entry=c.execute('INSERT INTO rlc_events(deal_id,event_date,kind,principal,interest,note) VALUES(?,?,?,?,?,?)',args).lastrowid
 return entry

def save_common_rate(c,v,id=None,expected=None):
 if v.get('rate') is None or not str(v['rate']).strip():raise ValueError('공통 연이율을 입력하세요. 무이자는 0을 명시하세요.')
 dt=calc.day(v['effective_date']).isoformat()
 if not 1990<=calc.day(dt).year<=2100:raise ValueError('적용일은 1990~2100년으로 입력하세요.')
 rate=percent(v['rate']);kb=percent(v['kb']) if v.get('kb') not in (None,'') else None
 with c:
  c.execute('DELETE FROM rlc_common_rates WHERE id=-1')
  if id:check_version(one(c,'common_rates',id),expected)
  if c.execute('SELECT 1 FROM rlc_common_rates WHERE effective_date=? AND deleted=0 AND id<>?',(dt,id or -1)).fetchone():raise ValueError('같은 적용 시작일의 공통이율이 이미 있습니다. 불러와 수정하세요.')
  args=(dt,rate,kb,str(v.get('note','')))
  if id:c.execute('UPDATE rlc_common_rates SET effective_date=?,rate=?,kb=?,note=?,version=version+1 WHERE id=?',args+(id,))
  else:id=c.execute('INSERT INTO rlc_common_rates(effective_date,rate,kb,note) VALUES(?,?,?,?)',args).lastrowid
 return id

def common_rate_candidates(c):
 grouped={}
 for r in entities(c,'rates'):
  if r['deal_id'] is None:grouped.setdefault(r['effective_date'],[]).append(r)
 out=[]
 for dt,items in sorted(grouped.items()):
  values={D(r['rate']) for r in items}
  if len(values)!=1:raise ValueError(dt+' 회사 간 기본이율이 서로 다릅니다. 확인 후 공통이율을 직접 등록하세요.')
  references={r['kb'] for r in items}
  out.append(dict(effective_date=dt,rate=str(next(iter(values))),kb=next(iter(references)) if len(references)==1 else None,note='기존 회사 간 기본이율을 공통으로 가져옴'))
 return out

def copy_common_rates(c,expected):
 with c:
  c.execute('DELETE FROM rlc_common_rates WHERE id=-1')
  candidates=common_rate_candidates(c)
  if not candidates or dump(candidates)!=dump(expected):raise ValueError('기존 이율이 변경되었거나 없습니다. 다시 확인하세요.')
  existing={r['effective_date']:r for r in entities(c,'common_rates')}
  for r in candidates:
   if r['effective_date'] in existing and D(existing[r['effective_date']]['rate'])!=D(r['rate']):raise ValueError('기존 공통이율과 충돌합니다: '+r['effective_date'])
  for r in candidates:
   if r['effective_date'] not in existing:c.execute('INSERT INTO rlc_common_rates(effective_date,rate,kb,note) VALUES(?,?,?,?)',(r['effective_date'],r['rate'],r['kb'],r['note']))
 return len(candidates)

def save_rate(c,v,id=None,expected=None):
 v=dict(v)
 if v.get('rate') in (None,''):raise ValueError('약정 연이율을 입력하세요. 무이자는 0입니다.')
 lender=int(v['lender_id']);borrower=int(v['borrower_id']);deal=v.get('deal_id');dt=calc.day(v['effective_date']).isoformat();rate=percent(v['rate']);kb=percent(v['kb']) if v.get('kb') not in (None,'') else None
 if lender==borrower or not {lender,borrower}<={r['id'] for r in companies(c)}:raise ValueError('활성 거래 회사를 선택하세요.')
 if deal:
  t=one(c,'deals',deal)
  if (lender,borrower)!=(t['lender_id'],t['borrower_id']):raise ValueError('거래별 이율의 회사 연결을 확인하세요.')
 matching=[r for r in deals(c) if (r['lender_id'],r['borrower_id'])==(lender,borrower) and (not deal or r['id']==deal or ledger_depends(c,r,deal))]
 with c:
  for t in matching:lock(c,t['id'],dt)
  if id:
   old=one(c,'rates',id);check_version(old,expected)
   if (old['deal_id'],old['lender_id'],old['borrower_id'])!=(deal,lender,borrower):raise ValueError('수정 시 이율 연결을 바꾸지 말고 새로 등록하세요.')
   for t in matching:lock(c,t['id'],old['effective_date'])
  if c.execute('SELECT 1 FROM rlc_rates WHERE lender_id=? AND borrower_id=? AND COALESCE(deal_id,0)=? AND effective_date=? AND deleted=0 AND id<>?',(lender,borrower,deal or 0,dt,id or -1)).fetchone():raise ValueError('같은 적용일의 이율이 이미 있습니다.')
  args=(deal,lender,borrower,dt,rate,kb,str(v.get('note','')))
  if id:c.execute('UPDATE rlc_rates SET deal_id=?,lender_id=?,borrower_id=?,effective_date=?,rate=?,kb=?,note=?,version=version+1 WHERE id=?',args+(id,))
  else:id=c.execute('INSERT INTO rlc_rates(deal_id,lender_id,borrower_id,effective_date,rate,kb,note) VALUES(?,?,?,?,?,?,?)',args).lastrowid
 return id

def set_deleted(c,kind,id,version,deleted,reason):
 if not str(reason).strip():raise ValueError('삭제·복구 사유를 입력하세요.')
 with c:
  r=one(c,kind,id,not deleted);check_version(r,version)
  if kind=='companies' and deleted and deals(c,id):raise ValueError('활성 거래가 있는 회사는 먼저 거래를 정리하세요. 과거 자료는 보존됩니다.')
  if kind=='deals':
   if deleted and any(ledger_depends(c,t,id) for t in deals(c) if t['id']!=id):raise ValueError('이 약정의 이율을 참조하는 원장 거래가 있어 삭제할 수 없습니다. 연결된 원장 거래를 먼저 확인하세요.')
   lock(c,id)
   if not deleted and not {r['lender_id'],r['borrower_id']}<={x['id'] for x in companies(c)}:raise ValueError('먼저 거래 회사를 복구하세요.')
  if kind=='events':
   t=one(c,'deals',r['deal_id']);lock(c,t['id'],r['event_date']);timeline(t,[e for e in events(c,t['id']) if e['id']!=id]+([] if deleted else [r]))
  if kind=='exception_rules' and not deleted:
   if not {r['lender_id'],r['borrower_id']}<={x['id'] for x in companies(c)}:raise ValueError('대여회사·차입회사를 먼저 복구하세요.')
  if kind=='exception_rates' and not deleted:
   one(c,'exception_rules',r['rule_id'])
   if c.execute('SELECT 1 FROM rlc_exception_rates WHERE rule_id=? AND effective_date=? AND deleted=0',(r['rule_id'],r['effective_date'])).fetchone():raise ValueError('같은 날짜의 활성 예외이율이 있습니다.')
  if kind=='common_rates' and not deleted:
   if c.execute('SELECT 1 FROM rlc_common_rates WHERE effective_date=? AND deleted=0',(r['effective_date'],)).fetchone():raise ValueError('같은 날짜의 활성 공통이율이 있습니다. 먼저 확인하세요.')
  if kind=='rates':
   for t in deals(c):
    if (t['lender_id'],t['borrower_id'])==(r['lender_id'],r['borrower_id']) and (r['deal_id'] is None or t['id']==r['deal_id'] or ledger_depends(c,t,r['deal_id'])):lock(c,t['id'],r['effective_date'])
   if not deleted and c.execute('SELECT 1 FROM rlc_rates WHERE lender_id=? AND borrower_id=? AND COALESCE(deal_id,0)=? AND effective_date=? AND deleted=0',(r['lender_id'],r['borrower_id'],r['deal_id'] or 0,r['effective_date'])).fetchone():raise ValueError('같은 적용일의 활성 이율이 있습니다.')
  if kind=='files' and not deleted:
   one(c,'deals',r['deal_id'])
   if sum(f['size'] for f in entities(c,'files') if f['deal_id']==r['deal_id'])+r['size']>20*1024*1024:raise ValueError('복구 후 첨부 합계가 20MB를 초과합니다.')
  if kind not in ['companies','deals','events','rates','common_rates','exception_rules','exception_rates','files']:raise ValueError('삭제할 구분을 확인하세요.')
  c.execute('UPDATE rlc_'+kind+' SET deleted=?,version=version+1 WHERE id=?',(int(deleted),id))
  # Shared audit preserves before/after plus explicit business reason.
  c.execute('INSERT INTO rlc_change_reasons(kind,entity_id,reason) VALUES(?,?,?)',(kind,id,reason))

def month_record(c,id,month):
 r=rows(c,'SELECT * FROM rlc_months WHERE deal_id=? AND month=?',(id,calc.period(month)))
 return dict(r[0],data=json.loads(r[0]['payload'])) if r else None

def calculate(c,id,month,stored=True):
 t=one(c,'deals',id);old=month_record(c,id,month)
 if stored and old and old['final']:return old['data']
 result=calc.calculation(t,events(c,id),rates(c,t),month)
 if old:
  result['adjustment']=old['data'].get('adjustment',0);result['adjustment_reason']=old['data'].get('adjustment_reason','')
 result['final_interest']=result['calculated']+result['adjustment'];result['deal']=t
 return result

def save_month(c,id,month,adjustment,reason,final=False,expected=None):
 with c:
  t=one(c,'deals',id);old=month_record(c,id,month)
  if calc.month_end(month)<calc.day(t['interest_start']):raise ValueError('이자 계산 시작월 이후를 선택하세요.')
  if old and old['version']!=expected or not old and expected is not None:raise ValueError('월 계산이 변경되었습니다. 다시 조회하세요.')
  if old and old['final']:raise ValueError('확정 월은 관리자 확정 해제 후 변경하세요.')
  adjustment=D(adjustment)
  if adjustment!=adjustment.to_integral_value() or adjustment and not str(reason).strip():raise ValueError('조정금액은 정수로, 조정 사유도 입력하세요.')
  data=calculate(c,id,month,False);data.update(adjustment=int(adjustment),adjustment_reason=reason,final_interest=data['calculated']+int(adjustment))
  c.execute('INSERT INTO rlc_months(deal_id,month,payload,final) VALUES(?,?,?,?) ON CONFLICT(deal_id,month) DO UPDATE SET payload=excluded.payload,final=excluded.final,version=version+1',(id,month,dump(data),int(final)))
 return data

def reopen(c,id,month,token,reason):
 shared.require_admin(token)
 if not str(reason).strip():raise ValueError('확정 해제 사유를 입력하세요.')
 with c:
  c.execute('UPDATE rlc_months SET final=0,version=version+1 WHERE deal_id=? AND month=? AND final=1',(id,month))
  c.execute('INSERT INTO rlc_change_reasons(kind,entity_id,reason) VALUES(?,?,?)',('month',id,month+' '+reason))

def totals(c,t,as_of):
 as_of=calc.day(as_of);es=events(c,t['id']);interest=0
 for month in calc.months(t['interest_start'],as_of):interest+=calculate(c,t['id'],month)['final_interest']
 paid=sum((D(e['interest']) for e in es if calc.day(e['event_date'])<=as_of),D(0))
 return dict(principal=str(calc.balance(t,es,as_of)),interest=interest,paid=str(paid),unpaid=str(D(interest)-paid))

def save_file(c,id,name,blob,entry=None,expected=None):
 from joint_letter_files import packed
 one(c,'deals',id);v=packed(name,blob)
 existing=[r for r in entities(c,'files') if r['deal_id']==id]
 if sum(r['size'] for r in existing if r['id']!=entry)+v['size']>20*1024*1024:raise ValueError('거래별 첨부 합계는 20MB 이하입니다.')
 with c:
  if entry:
   old=one(c,'files',entry);check_version(old,expected)
   if old['deal_id']!=id:raise ValueError('첨부 거래를 확인하세요.')
   c.execute('UPDATE rlc_files SET name=?,mime=?,content=?,digest=?,size=?,version=version+1 WHERE id=?',tuple(v[k] for k in ['name','mime','content','digest','size'])+(entry,))
  else:entry=c.execute('INSERT INTO rlc_files(deal_id,name,mime,content,digest,size) VALUES(?,?,?,?,?,?)',(id,*[v[k] for k in ['name','mime','content','digest','size']])).lastrowid
 return entry

def candidates(c,company,start,end,mode):
 start=calc.day(start);end=calc.day(end);out=[]
 for t in deals(c,company):
  if mode=='기간 내 등록 거래':include=start<=calc.day(t['start'])<=end
  else:
   es=events(c,t['id']);include=calc.day(t['start'])<=end and (start<=calc.day(t['start']) or calc.balance(t,es,start)>0 or calc.balance(t,es,end)>0 or any(start<=calc.day(e['event_date'])<=end and D(e['principal']) for e in es))
  if include:out.append(t)
 return out

def prepare_batch(c,company,ids,issued,meeting,until,include_files=False,final=False,rate_until=None,registered_dates=False):
 import related_loan_report as report
 ids=list(dict.fromkeys(map(int,ids)))
 if not ids or len(ids)>30:raise ValueError('한 번에 1~30건을 선택하세요.')
 issued=calc.day(issued).isoformat();meeting=calc.day(meeting).isoformat();until=calc.day(until).isoformat();rate_until=calc.day(rate_until or until[:4]+'-12-31').isoformat()
 cos={r['id']:r for r in companies(c)};items=[]
 for id in ids:
  t=one(c,'deals',id)
  if company not in (t['lender_id'],t['borrower_id']):raise ValueError('기준회사와 연결된 거래만 출력하세요.')
  if t.get('maturity_unverified') and final:raise ValueError(t['number']+'의 만기를 원본 약정으로 확인하세요.')
  if t['start']>until:raise ValueError('거래일 이후의 기준기간을 선택하세요.')
  lender=cos.get(t['lender_id']);borrower=cos.get(t['borrower_id'])
  if not lender or not borrower:raise ValueError('활성 거래 회사 정보를 확인하세요.')
  if final:
   for co in [lender,borrower]:
    if not all(str(co.get(k,'')).strip() for k in ['name','registration','representative','address','place']):raise ValueError(co['name']+'의 법인번호·대표이사·주소·회의 장소를 등록하세요.')
    if not [r for r in co.get('directors',[]) if r.get('present')]:raise ValueError(co['name']+'의 출석이사를 등록하세요.')
   if not str(t.get('purpose','')).strip() or not str(t.get('collateral','')).strip():raise ValueError(t['number']+'의 용도·담보조건(없으면 없음)을 입력하세요.')
  if rate_until<t['interest_start']:raise ValueError('이율 적용 종료일은 이자 계산 시작일 이후여야 합니다.')
  rs=rates(c,t);doc_date=t.get('agreement_date',t['start']) if registered_dates else issued
  lender_meeting=t.get('lender_meeting',t['start']) if registered_dates else meeting;borrower_meeting=t.get('borrower_meeting',t['start']) if registered_dates else meeting
  agreement=report.agreement(t,lender,borrower,doc_date,rate_until,rs)
  docs=[dict(agreement,copy_for=lender['name']),dict(agreement,copy_for=borrower['name']),dict(report.board(t,lender,borrower,True,lender_meeting,rate_until,rs),copy_for=lender['name']),dict(report.board(t,borrower,lender,False,borrower_meeting,rate_until,rs),copy_for=borrower['name'])]
  fs=[r for r in entities(c,'files') if r['deal_id']==id] if include_files else []
  items.append(dict(deal=t,lender=lender,borrower=borrower,rates=rs,documents=docs,files=fs))
 if sum(len(report.paginate(doc)) for item in items for doc in item['documents'])>200:raise ValueError('한 번에 200페이지 이하로 대상을 나누어 출력하세요.')
 return dict(schema_version=1,basis_company=company,issued=issued,meeting=meeting,until=until,rate_until=rate_until,registered_dates=registered_dates,items=items,source_revision=shared.revision(c))

def save_batch(c,data,token):
 user=shared.validate_session(token)
 if not user:raise PermissionError('다시 로그인하세요.')
 with c:
  if shared.revision(c)!=data['source_revision']:raise ValueError('원본이 변경되었습니다. 미리보기를 다시 확인하세요.')
  fresh=prepare_batch(c,data['basis_company'],[r['deal']['id'] for r in data['items']],data['issued'],data['meeting'],data['until'],any(r['files'] for r in data['items']),True,data.get('rate_until'),data.get('registered_dates',False))
  if dump(fresh)!=dump(data):raise ValueError('원본이 변경되었습니다. 미리보기를 다시 확인하세요.')
  prefix='RL-'+data['issued'].replace('-','')+'-';n=1
  while c.execute('SELECT 1 FROM rlc_batches WHERE number=?',(prefix+f'{n:03}',)).fetchone():n+=1
  id=c.execute('INSERT INTO rlc_batches(number,payload,actor) VALUES(?,?,?)',(prefix+f'{n:03}',dump(fresh),user['username'])).lastrowid
 return id

def set_batch_deleted(c,id,deleted,reason):
 if not str(reason).strip():raise ValueError('삭제·복구 사유를 입력하세요.')
 with c:
  if c.execute('UPDATE rlc_batches SET deleted=? WHERE id=? AND deleted=?',(int(deleted),id,int(not deleted))).rowcount!=1:raise ValueError('발행본 상태가 변경되었습니다.')
  c.execute('INSERT INTO rlc_change_reasons(kind,entity_id,reason) VALUES(?,?,?)',('batch',id,reason))
