"""Reviewed import of the legacy horizontal schedules; never executes Excel formulas."""
from io import BytesIO
from datetime import date,datetime,timedelta
from decimal import ROUND_HALF_UP
import base64,hashlib,json,re,zipfile
import openpyxl
import related_loan_store as db
import related_loan_calc as calc

def install(c):
 c.executescript('''CREATE TABLE IF NOT EXISTS rlc_imports(id INTEGER PRIMARY KEY,digest TEXT NOT NULL,basis_company INTEGER NOT NULL,filename TEXT NOT NULL,source TEXT NOT NULL,manifest TEXT NOT NULL,actor TEXT NOT NULL,reverted INTEGER NOT NULL DEFAULT 0,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
 CREATE INDEX IF NOT EXISTS rlc_import_active ON rlc_imports(digest,basis_company);
 CREATE TABLE IF NOT EXISTS rlc_import_keys(source_key TEXT PRIMARY KEY,import_id INTEGER NOT NULL REFERENCES rlc_imports(id),deal_id INTEGER NOT NULL REFERENCES rlc_deals(id));''')
def date_value(v):
 if isinstance(v,datetime):return v.date().isoformat()
 if isinstance(v,date):return v.isoformat()
 s=str(v or '').strip();m=re.fullmatch(r'(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})',s)
 if not m:raise ValueError('날짜 형식 확인')
 return date(*map(int,m.groups())).isoformat()
def month_value(v):
 s=str(v or '').strip();m=re.fullmatch(r'(\d{4})[.\-/](\d{1,2})',s)
 if not m:raise ValueError('귀속년월 확인')
 return calc.period(f'{int(m[1]):04}-{int(m[2]):02}')
def numeric(v):
 if v is None or isinstance(v,bool):raise ValueError('계산 결과 공란')
 return calc.D(v)
def displayed(v):return int(numeric(v).quantize(calc.D(1),rounding=ROUND_HALF_UP))
def read(blob,corrections=None):
 if len(blob)>32*1024*1024:raise ValueError('엑셀은 32MB 이하로 올리세요.')
 with zipfile.ZipFile(BytesIO(blob)) as z:
  if sum(i.file_size for i in z.infolist())>100*1024*1024:raise ValueError('압축 해제 크기가 너무 큽니다.')
 a=openpyxl.load_workbook(BytesIO(blob),data_only=False,keep_links=False);b=openpyxl.load_workbook(BytesIO(blob),data_only=True,keep_links=False)
 corrections=corrections or {};out=dict(digest=hashlib.sha256(blob).hexdigest(),sheets=[],excluded=[],errors=[],warnings=[])
 for s in a:
  if s.max_row>5000 or s.max_column>500:raise ValueError('지원 범위를 벗어난 큰 시트입니다.')
  headers=[r for r in range(1,s.max_row+1) if s.cell(r,2).value=='차입금액' and s.cell(r,3).value=='차입일자']
  if not headers:out['excluded'].append(s.title+' (거래 계산표 아님)');continue
  rawparty=str(s.cell(headers[0]+1,1).value or '')
  if not any(x in rawparty for x in ['㈜','(주)','주식회사']):out['excluded'].append(s.title+' (개인 또는 법인 구분 확인)');continue
  sheet=dict(name=s.title,party=rawparty.replace('\n',' ').strip(),direction='대여' if '대여' in str(s.cell(3,1).value).replace(' ','') else '차입',trades=[],payments=[],ledger=[],warnings=[])
  def cell(r,c):return b[s.title].cell(r,c).value
  def dt(r,c,owner):
   key=s.title+'!'+s.cell(r,c).coordinate;v=corrections.get(key,cell(r,c) if s.cell(r,c).data_type=='f' else s.cell(r,c).value)
   try:return date_value(v)
   except Exception:
    out['errors'].append(dict(key=key,owner=owner,raw=str(s.cell(r,c).value),reason='날짜 확인',replacement=''));return None
  for index,header in enumerate(headers):
   stop=headers[index+1] if index+1<len(headers) else next((r for r in range(header+1,s.max_row+1) if s.cell(r,4).value=='귀속년월'),s.max_row+1)
   for col in range(1,s.max_column,8):
    if s.cell(header,col+1).value!='차입금액':continue
    amount=cell(header+1,col+1)
    if amount is None:continue
    key=s.title+'!'+s.cell(header+1,col+1).coordinate
    try:
     value=numeric(amount)
     if value<=0 or value!=value.to_integral_value():raise ValueError()
     principal=int(value)
    except Exception:out['errors'].append(dict(key=key,owner=key,raw=str(amount),reason='양수 원금 확인',replacement=''));continue
    start=dt(header+1,col+2,key)
    t=dict(key=key,sheet=s.title,party=sheet['party'],principal=principal,start=start,date_cell=s.title+'!'+s.cell(header+1,col+2).coordinate,months=[],years=[],rates=[],warnings=[])
    for r in range(header+1,stop):
     raw=cell(r,col+3) if s.cell(r,col+3).data_type=='f' else s.cell(r,col+3).value
     if raw is None:continue
     year=re.search(r'(\d{4})년\s*소',str(raw))
     if year:
      try:t['years'].append(dict(year=int(year[1]),amount=displayed(cell(r,col+7)),cell=s.cell(r,col+7).coordinate))
      except ValueError:t['warnings'].append('연 소계 캐시 공란: '+s.cell(r,col+7).coordinate)
      continue
     if isinstance(raw,str) and any(x in raw for x in ['계','합']):continue
     if not isinstance(raw,(str,date,datetime)):continue
     when=dt(r,col+3,key)
     if not when:continue
     try:
      rate=numeric(cell(r,col+6));interest=numeric(cell(r,col+7));days=int(numeric(cell(r,col+5)))
      if not 0<=rate<=100 or not 0<=days<=400:raise ValueError('이율/일수 범위')
     except ValueError as e:
      out['errors'].append(dict(key=s.title+'!'+s.cell(r,col+6).coordinate,owner=key,raw=str(s.cell(r,col+6).value),reason='이율·일수·이자 캐시 확인: '+str(e),replacement=''));continue
     kb=cell(r,col+4);month=when[:7]
     t['months'].append(dict(month=month,end=when,days=days,rate=str(rate),kb=None if kb is None else str(kb),raw=str(interest),amount=displayed(interest),cell=s.cell(r,col+7).coordinate,formula=str(s.cell(r,col+7).value)))
    if not t['months']:t['warnings'].append('월별 계산 내역 없음')
    sheet['trades'].append(t)
  for r in range(1,s.max_row+1):
   if s.cell(r,4).value!='귀속년월':continue
   for rr in range(r+1,s.max_row+1):
    amount=cell(rr,2);rawdate=s.cell(rr,1).value
    if isinstance(amount,(float,int)) and amount<0:
     key=s.title+'!'+s.cell(rr,2).coordinate;when=dt(rr,1,key)
     sheet['payments'].append(dict(key=key,date=when,amount=int(-numeric(amount)),note=str(s.cell(rr,7).value or '')))
    elif isinstance(amount,(float,int)) and amount>0 and rawdate and not any(x in str(rawdate) for x in ['계','합']):
     try:
      when=date_value(rawdate);matches=[t for t in sheet['trades'] if t['start']==when and t['principal']==int(amount)]
      if len(matches)!=1:sheet['warnings'].append('원금 집계와 상세 거래일/금액 대조 필요: '+s.cell(rr,1).coordinate+' '+str(rawdate)+' / '+str(amount))
     except ValueError:sheet['warnings'].append('원금 집계 날짜 확인: '+s.cell(rr,1).coordinate)
    rawmonth=s.cell(rr,4).value
    if rawmonth is not None:
     try:
      m=month_value(rawmonth);value=cell(rr,5)
      if value is not None:sheet['ledger'].append(dict(month=m,amount=displayed(value),cell=s.cell(rr,5).coordinate))
     except ValueError:pass
   break
  out['sheets'].append(sheet)
 a.close();b.close();return out

def propose(parsed,selected):
 trades=[t for s in parsed['sheets'] if s['name'] in selected for t in s['trades']];remaining={t['key']:t['principal'] for t in trades};alloc=[]
 for s in parsed['sheets']:
  if s['name'] not in selected:continue
  for p in sorted(s['payments'],key=lambda p:p['date'] or ''):
   amount=p['amount']
   for t in sorted(s['trades'],key=lambda t:(t['start'] or '',t['key'])):
    if not p['date'] or not t['start'] or t['start']>p['date']:continue
    take=min(amount,remaining[t['key']])
    if take:alloc.append(dict(payment=p['key'],trade=t['key'],amount=take,date=p['date']));amount-=take;remaining[t['key']]-=take
   if amount:raise ValueError('상환액이 등록 가능한 이전 원금을 초과합니다: '+p['key'])
 return alloc

def prepare(c,parsed,basis,mapping,selected,allocations,accept_details=False):
 if basis not in {r['id'] for r in db.companies(c)}:raise ValueError('기준회사를 먼저 등록하세요.')
 sheets=[s for s in parsed['sheets'] if s['name'] in selected]
 if not sheets:raise ValueError('시트를 선택하세요.')
 owners={t['key'] for s in sheets for t in s['trades']}|{p['key'] for s in sheets for p in s['payments']}
 errors=[r for r in parsed['errors'] if r['owner'] in owners]
 if errors:raise ValueError('선택 시트의 날짜·이율·수식 결과를 먼저 확인하세요. 오류 '+str(len(errors))+'건')
 if not accept_details:raise ValueError('상세 계산표를 기준으로 가져오며 집계 대조 차이를 확인했다는 동의가 필요합니다.')
 cos={r['id']:r for r in db.companies(c)};plans=[];payments={p['key']:p for s in sheets for p in s['payments']}
 sums={key:0 for key in payments}
 for a in allocations:
  if a['payment'] not in payments or a['trade'] not in owners:raise ValueError('상환 배분 연결을 확인하세요.')
  if a['amount']<=0 or int(a['amount'])!=a['amount']:raise ValueError('상환 배분액은 양수 정수여야 합니다.')
  sums[a['payment']]+=int(a['amount'])
 if any(sums[k]!=p['amount'] for k,p in payments.items()):raise ValueError('상환 배분 합계가 엑셀 상환액과 다릅니다.')
 for s in sheets:
  partner=mapping.get(s['name'])
  if partner not in cos or partner==basis:raise ValueError(s['name']+'의 상대회사를 연결하세요.')
  sheetkeys={t['key'] for t in s['trades']}
  if any(a['trade'] not in sheetkeys for a in allocations if a['payment'] in {p['key'] for p in s['payments']}):raise ValueError('다른 회사 거래에 상환을 배분할 수 없습니다.')
  for t in s['trades']:
   source_key=hashlib.sha256(db.dump(dict(basis=basis,partner=partner,direction=s['direction'],source=t['key'],date=t['start'],amount=t['principal'])).encode()).hexdigest()
   if c.execute('SELECT 1 FROM rlc_import_keys WHERE source_key=?',(source_key,)).fetchone():raise ValueError('이미 가져온 거래가 있습니다: '+t['key'])
   lender,borrower=(basis,partner) if s['direction']=='대여' else (partner,basis)
   if any(r['lender_id']==lender and r['borrower_id']==borrower and r['start']==t['start'] and calc.D(r['principal'])==t['principal'] for r in db.deals(c)):raise ValueError('같은 회사·거래일·원금의 기존 거래가 있습니다: '+t['key']+' (기존 자료를 확인하세요)')
   months=sorted(t['months'],key=lambda m:(m['month'],m['end']));monthly={}
   for m in months:
    if m['month'] in monthly:
     grouped=monthly[m['month']];grouped['amount']+=m['amount'];grouped['raw']=str(calc.D(grouped['raw'])+calc.D(m['raw']));grouped['days']+=m['days'];grouped['cell']+=','+m['cell']
    else:monthly[m['month']]=dict(m)
   if not months:raise ValueError('월별 계산이 없는 거래는 별도 수기 등록하세요: '+t['key'])
   end=calc.month_end(months[-1]['month']).isoformat();deal=dict(id=-1,number='XL-'+source_key[:16],lender_id=lender,borrower_id=borrower,start=t['start'],interest_start=t['start'],principal=str(t['principal']),maturity=None,maturity_unverified=True,rate=months[0]['rate'],rate_mode='거래별',first_inclusive=True,repay_inclusive=True,basis='365',rounding='절사',rounding_unit='월 합계',purpose='',collateral='',repayment='원리금 일시상환',import_rate_until=end,import_source=t['key'],note='엑셀 가져오기 · 만기 미확인. 원본 약정 확인 후 만기를 등록하세요.')
   es=[dict(event_date=payments[a['payment']]['date'],kind='원금상환·회수',principal=str(a['amount']),interest='0',note='엑셀 '+a['payment']+' · '+payments[a['payment']]['note']) for a in allocations if a['trade']==t['key']]
   db.timeline(deal,es);rs=[];last=None
   for m in months:
    value=(m['rate'],m['kb'])
    if value!=last:
     dt=max(t['start'],(calc.day(m['end'])-timedelta(days=max(1,m['days'])-1)).isoformat());rs.append(dict(id=len(rs)+1,deal_id=-1,lender_id=lender,borrower_id=borrower,effective_date=dt,rate=m['rate'],kb=m['kb'],note='엑셀 '+t['key']+' '+m['cell']));last=value
   # Preserve each displayed year subtotal as an explicitly labelled last-month adjustment.
   for annual in t['years']:
    ms=[m for m in monthly.values() if int(m['month'][:4])==annual['year']]
    if ms:
     delta=annual['amount']-sum(m['amount'] for m in ms)
     if delta:
      lastmonth=max(ms,key=lambda m:m['month']);lastmonth['year_adjustment']=delta;lastmonth['year_reason']='연 소계 '+annual['cell']+' 대조';lastmonth['amount']+=delta
   first=months[0]
   for missing in calc.months(t['start'],end):
    if missing in monthly:continue
    result=calc.calculation(deal,es,rs,missing)
    if missing<first['month'] and first['days']>__import__('calendar').monthrange(int(first['month'][:4]),int(first['month'][5:]))[1]:
     monthly[missing]=dict(month=missing,amount=0,raw='0',days=0,cell=first['cell']+' (최초월 합산 이전기간)',year_adjustment=0)
    elif result['calculated']==0:monthly[missing]=dict(month=missing,amount=0,raw='0',days=0,cell='원금 잔액 0',year_adjustment=0)
    else:raise ValueError(t['key']+' '+missing+' 월 계산 누락. 원본을 확인하세요.')
   comparisons=[]
   for m in sorted(monthly.values(),key=lambda m:m['month']):
    result=calc.calculation(deal,es,rs,m['month']);target=m['amount']
    comparisons.append(dict(month=m['month'],excel=target,recalculated=result['calculated'],adjustment=target-result['calculated'],raw=m['raw'],days=m['days'],cell=m['cell'],year_adjustment=m.get('year_adjustment',0)))
   plans.append(dict(source_key=source_key,source=t['key'],sheet=s['name'],deal=deal,events=es,rates=rs,months=comparisons))
 comparison=[]
 for s in sheets:
  expected={}
  for p in plans:
   if p['sheet']==s['name']:
    for m in p['months']:expected[m['month']]=expected.get(m['month'],0)+m['excel']
  for row in s['ledger']:
   if row['month'] in expected and row['amount']!=expected[row['month']]:comparison.append(dict(sheet=s['name'],month=row['month'],ledger=row['amount'],details=expected[row['month']],cell=row['cell']))
 return dict(digest=parsed['digest'],basis_company=basis,plans=plans,allocations=allocations,ledger_differences=comparison,source_revision=db.shared.revision(c))

def fingerprint(c,ids):
 data={}
 for id in ids:
  data[id]={}
  for table in ['deals','events','rates','months','files']:
   query='SELECT * FROM rlc_'+table+' WHERE '+('id=?' if table=='deals' else 'deal_id=?')+' ORDER BY id'
   data[id][table]=db.rows(c,query,(id,))
 return hashlib.sha256(db.dump(data).encode()).hexdigest()
def history(c):return db.rows(c,'SELECT id,filename,digest,basis_company,actor,reverted,created_at FROM rlc_imports ORDER BY id DESC')
def commit(c,blob,filename,basis,mapping,selected,allocations,corrections,expected,ack):
 if not ack:raise ValueError('원본 차이·상환 배분·월별 조정 확인이 필요합니다.')
 parsed=read(blob,corrections);plan=prepare(c,parsed,basis,mapping,selected,allocations,True)
 if db.dump(plan)!=db.dump(expected):raise ValueError('파일·연결·자료가 변경되었습니다. 다시 미리보기하세요.')
 with c:
  c.execute('DELETE FROM rlc_import_keys WHERE source_key=?',('unused-lock',))
  if db.shared.revision(c)!=plan['source_revision']:raise ValueError('다른 사용자가 자료를 변경했습니다.')
  actor=db.shared.RUN.get()['user']['username'];id=c.execute('INSERT INTO rlc_imports(digest,basis_company,filename,source,manifest,actor) VALUES(?,?,?,?,?,?)',(plan['digest'],basis,filename,base64.b64encode(blob).decode(),'{}',actor)).lastrowid
  ids=[]
  for p in plan['plans']:
   v=dict(p['deal']);v.pop('id');v['number']+='-'+str(id);lender=v.pop('lender_id');borrower=v.pop('borrower_id');number=v.pop('number')
   deal_id=c.execute('INSERT INTO rlc_deals(number,lender_id,borrower_id,payload) VALUES(?,?,?,?)',(number,lender,borrower,db.dump(v))).lastrowid;ids.append(deal_id)
   for e in p['events']:c.execute('INSERT INTO rlc_events(deal_id,event_date,kind,principal,interest,note) VALUES(?,?,?,?,?,?)',(deal_id,e['event_date'],e['kind'],e['principal'],e['interest'],e['note']))
   for r in p['rates']:c.execute('INSERT INTO rlc_rates(deal_id,lender_id,borrower_id,effective_date,rate,kb,note) VALUES(?,?,?,?,?,?,?)',(deal_id,lender,borrower,r['effective_date'],r['rate'],r['kb'],r['note']))
   t=db.one(c,'deals',deal_id);es=db.events(c,deal_id);rs=db.rates(c,t)
   for m in p['months']:
    result=calc.calculation(t,es,rs,m['month'])
    result.update(deal=t,adjustment=m['excel']-result['calculated'],final_interest=m['excel'],adjustment_reason='엑셀 '+p['source']+'!'+m['cell']+' 대조 / 일수·원단위·연소계 차이',import_source=m)
    c.execute('INSERT INTO rlc_months(deal_id,month,payload,final) VALUES(?,?,?,0)',(deal_id,m['month'],db.dump(result)))
   c.execute('INSERT INTO rlc_import_keys VALUES(?,?,?)',(p['source_key'],id,deal_id))
  manifest=dict(ids=ids,fingerprint=fingerprint(c,ids),plan=plan,corrections=corrections)
  c.execute('UPDATE rlc_imports SET manifest=? WHERE id=?',(db.dump(manifest),id))
 return id

def undo(c,id,reason):
 if not reason.strip():raise ValueError('되돌리기 사유를 입력하세요.')
 with c:
  c.execute('DELETE FROM rlc_import_keys WHERE source_key=?',('unused-lock',))
  rows=db.rows(c,'SELECT * FROM rlc_imports WHERE id=? AND reverted=0',(id,))
  if not rows:raise ValueError('이미 되돌렸거나 없는 가져오기입니다.')
  manifest=json.loads(rows[0]['manifest']);ids=manifest['ids']
  if fingerprint(c,ids)!=manifest['fingerprint']:raise ValueError('가져온 자료가 이후 수정·확정·첨부되었습니다. 일괄 되돌리기를 제한합니다. 개별 자료를 확인하세요.')
  for r in db.entities(c,'batches')+db.entities(c,'batches',True):
   if any(i['deal']['id'] in ids for i in r['items']):raise ValueError('문서 발행본에 사용된 가져오기는 되돌릴 수 없습니다.')
  for deal in ids:
   c.execute('UPDATE rlc_deals SET deleted=1,version=version+1 WHERE id=?',(deal,));c.execute('UPDATE rlc_events SET deleted=1,version=version+1 WHERE deal_id=?',(deal,));c.execute('UPDATE rlc_rates SET deleted=1,version=version+1 WHERE deal_id=?',(deal,))
  c.execute('DELETE FROM rlc_import_keys WHERE import_id=?',(id,));c.execute('UPDATE rlc_imports SET reverted=1 WHERE id=?',(id,));c.execute('INSERT INTO rlc_change_reasons(kind,entity_id,reason) VALUES(?,?,?)',('import',id,reason))
