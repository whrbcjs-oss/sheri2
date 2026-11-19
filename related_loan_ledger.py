"""Borrower ledger import using registered terms, with reviewed principal allocations."""
from io import BytesIO
from datetime import datetime
import base64,hashlib,json
import openpyxl
import related_loan_calc as calc
import related_loan_store as db
import related_loan_import as legacy

def install(c):
 c.executescript('''CREATE TABLE IF NOT EXISTS rlc_ledger_imports(id INTEGER PRIMARY KEY,filename TEXT NOT NULL,source TEXT NOT NULL,payload TEXT NOT NULL,reverted INTEGER NOT NULL DEFAULT 0,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
 CREATE TABLE IF NOT EXISTS rlc_ledger_keys(source_key TEXT PRIMARY KEY,import_id INTEGER NOT NULL);''')
def _read(blob):
 if len(blob)>32*1024*1024:raise ValueError('32MB 이하 XLSX를 올리세요.')
 import zipfile
 with zipfile.ZipFile(BytesIO(blob)) as z:
  if sum(i.file_size for i in z.infolist())>100*1024*1024:raise ValueError('엑셀 크기가 너무 큽니다.')
 w=openpyxl.load_workbook(BytesIO(blob),data_only=False,keep_links=False);out=[]
 try:
  for s in w:
   if s.max_row>10000 or s.max_column>100:raise ValueError('시트 크기를 확인하세요.')
   header=None
   for row in s.iter_rows(min_row=1,max_row=min(20,s.max_row)):
    columns={str(x.value or '').strip():x.column for x in row}
    if {'날짜','차변','대변'}<=columns.keys() and ('적요란' in columns or '적요' in columns):header=(row[0].row,columns);break
   if not header:continue
   h,cols=header
   for r in range(h+1,s.max_row+1):
    vals=[s.cell(r,cols[k]).value for k in ['날짜','차변','대변']]
    if all(v in (None,'') for v in vals):continue
    for cell in s[r]:
     if cell.data_type=='f':raise ValueError(f'{s.title} {r}행: 수식 대신 값을 붙여넣어 업로드하세요.')
    try:
     when=legacy.date_value(vals[0]);debit=calc.D(vals[1] or 0);credit=calc.D(vals[2] or 0)
     if not 1990<=calc.day(when).year<=2100 or min(debit,credit)<0 or any(v!=v.to_integral_value() for v in [debit,credit]) or debit and credit:raise ValueError()
    except Exception:raise ValueError(f'{s.title} {r}행: 날짜·차변·대변을 확인하세요. 한 행에는 한쪽 금액만 입력하세요.')
    if not debit and not credit:continue
    note=str(s.cell(r,cols.get('적요란',cols.get('적요'))).value or '')
    out.append(dict(key=s.title+'!'+str(r),date=when,note=note,debit=int(debit),credit=int(credit)))
 finally:w.close()
 if not out:raise ValueError('날짜·적요란(또는 적요)·차변·대변 머리글과 거래 내역이 필요합니다.')
 return sorted(out,key=lambda r:(r['date'],r['key']))
def read(blob):
 try:return _read(blob)
 except ValueError:raise
 except Exception as ex:raise ValueError('정상 XLSX 파일인지 확인하세요. 파일이 손상되었거나 지원하지 않는 구조입니다.') from ex

def key(row,borrower,lender):
 # Identical rows are deliberately blocked even when they arrive in renamed files.
 return hashlib.sha256(db.dump(dict(borrower=borrower,lender=lender,date=row['date'],note=row['note'],debit=row['debit'],credit=row['credit'])).encode()).hexdigest()
def choices(c,borrower,lender,rows):
 out={str(t['id']):t for t in db.deals(c) if (t['borrower_id'],t['lender_id'])==(borrower,lender)}
 for r in rows:
  if r['credit']:out[r['key']]=dict(id=r['key'],start=r['date'],principal=str(r['credit']),number='신규 '+r['key'],borrower_id=borrower,lender_id=lender)
 return out

def propose(c,borrower,lender,rows):
 pool=choices(c,borrower,lender,rows);payments=[r for r in rows if r['debit']];used={k:0 for k in pool};alloc=[]
 for p in payments:
  left=p['debit']
  for k,t in sorted(pool.items(),key=lambda x:(x[1]['start'],x[0])):
   if t['start']>p['date']:continue
   available=calc.balance(t,db.events(c,t['id']) if isinstance(t['id'],int) else [],p['date'])-used[k]
   take=min(left,max(0,int(available)))
   if take:alloc.append(dict(payment=p['key'],trade=k,amount=take));used[k]+=take;left-=take
   if not left:break
  if left:raise ValueError(p['key']+' 상환액을 배분할 원금이 부족합니다. 기존 거래와 업로드 범위를 확인하세요.')
 return alloc

def prepare(c,blob,borrower,lender,template_id,allocations):
 if borrower==lender or not {borrower,lender}<={r['id'] for r in db.companies(c)}:raise ValueError('서로 다른 차입회사·대여회사를 선택하세요.')
 rows=read(blob);pool=choices(c,borrower,lender,rows);template=db.one(c,'deals',template_id)
 if (template['borrower_id'],template['lender_id'])!=(borrower,lender):raise ValueError('선택한 양사의 등록 약정만 사용할 수 있습니다.')
 if template.get('import_rate_until'):raise ValueError('기존 상세 엑셀 이관 약정은 원장 업로드 기준으로 사용할 수 없습니다. 실제 약정 조건을 신규 등록하세요.')
 keys=[key(r,borrower,lender) for r in rows]
 if len(set(keys))!=len(keys):raise ValueError('파일 안에 동일한 거래가 중복되어 있습니다. 원본을 확인하세요.')
 if any(c.execute('SELECT 1 FROM rlc_ledger_keys WHERE source_key=?',(k,)).fetchone() for k in keys):raise ValueError('이미 가져온 원장 거래가 있습니다.')
 new={};warnings=[]
 for r in rows:
  if not r['credit']:continue
  if any(t['start']==r['date'] and calc.D(t['principal'])==r['credit'] for t in pool.values() if isinstance(t['id'],int)):raise ValueError(r['key']+' 동일 회사·차입일·원금의 기존 거래가 있습니다.')
  t={k:v for k,v in template.items() if k not in ['id','version','deleted','payload','number','agreement_date','lender_meeting','borrower_meeting','import_source','import_rate_until','maturity_verified']}
  t.update(id=r['key'],number='원장 '+r['key'],start=r['date'],interest_start=r['date'],principal=str(r['credit']),maturity=None,maturity_unverified=True,note=r['note'],ledger_source=r['key'],ledger_template_id=template_id)
  own=[dict(x,deal_id=r['key'],ledger_template=True) for x in db.rates(c,template) if x['deal_id']==template_id]
  rs=own+[x for x in db.rates(c,template) if x['deal_id'] is None]
  calc.rate_at(t,rs,t['start'])
  new[r['key']]=dict(deal=t,rates=own)
 payments={r['key']:r for r in rows if r['debit']};sums={k:0 for k in payments};es={k:[] for k in pool}
 for a in allocations:
  if a['payment'] not in payments or a['trade'] not in pool:raise ValueError('상환 연결을 확인하세요.')
  value=calc.D(a['amount'])
  if value<=0 or value!=value.to_integral_value():raise ValueError('배분액은 양수 정수로 입력하세요.')
  p=payments[a['payment']];sums[a['payment']]+=int(value)
  es[a['trade']].append(dict(event_date=p['date'],kind='원금상환·회수',principal=str(value),interest='0',note='원장 '+p['key']+' '+p['note']))
 if any(sums[k]!=p['debit'] for k,p in payments.items()):raise ValueError('상환 배분 합계와 원장 차변 금액이 다릅니다.')
 for k,events in es.items():
  t=new[k]['deal'] if k in new else pool[k]
  db.timeline(t,(db.events(c,t['id']) if isinstance(t['id'],int) else [])+events)
  if isinstance(t['id'],int):
   for e in events:db.lock(c,t['id'],e['event_date'])
 return dict(rows=rows,new=new,events={k:v for k,v in es.items() if v},keys=keys,revision=db.shared.revision(c),borrower=borrower,lender=lender,template=template_id)

def commit(c,blob,filename,borrower,lender,template_id,allocations,expected,ack):
 if not ack:raise ValueError('차변은 이자 지급이 아닌 원금 상환임을 확인하세요.')
 plan=prepare(c,blob,borrower,lender,template_id,allocations)
 if db.dump(plan)!=db.dump(expected):raise ValueError('자료가 변경되었습니다. 미리보기를 다시 만드세요.')
 with c:
  c.execute('DELETE FROM rlc_ledger_keys WHERE source_key=?',('unused-lock',))
  if db.shared.revision(c)!=plan['revision']:raise ValueError('다른 사용자가 변경했습니다. 다시 조회하세요.')
  id=c.execute('INSERT INTO rlc_ledger_imports(filename,source,payload) VALUES(?,?,?)',(filename,base64.b64encode(blob).decode(),'{}')).lastrowid
  mapping={};newids=[];eventids=[]
  for k,p in plan['new'].items():
   t=dict(p['deal']);t.pop('id');t['number']='LG-'+str(id)+'-'+str(len(newids)+1);number=t.pop('number');a=t.pop('lender_id');b=t.pop('borrower_id')
   actual=c.execute('INSERT INTO rlc_deals(number,lender_id,borrower_id,payload) VALUES(?,?,?,?)',(number,a,b,db.dump(t))).lastrowid;mapping[k]=actual;newids.append(actual)
   for r in p['rates']:c.execute('INSERT INTO rlc_rates(deal_id,lender_id,borrower_id,effective_date,rate,kb,note) VALUES(?,?,?,?,?,?,?)',(actual,a,b,r['effective_date'],r['rate'],r['kb'],'원장 기준 약정 '+str(template_id)+' / '+r.get('note','')))
  involved=set(newids)
  for k,events in plan['events'].items():
   actual=mapping.get(k,int(k) if k.isdigit() else None);involved.add(actual)
   for e in events:eventids.append(c.execute('INSERT INTO rlc_events(deal_id,event_date,kind,principal,interest,note) VALUES(?,?,?,?,?,?)',(actual,e['event_date'],e['kind'],e['principal'],e['interest'],e['note'])).lastrowid)
  for k in plan['keys']:c.execute('INSERT INTO rlc_ledger_keys VALUES(?,?)',(k,id))
  payload=dict(plan=plan,newids=newids,eventids=eventids,ids=sorted(involved),fingerprint=legacy.fingerprint(c,sorted(involved)))
  c.execute('UPDATE rlc_ledger_imports SET payload=? WHERE id=?',(db.dump(payload),id))
 return id

def undo(c,id,reason):
 if not reason.strip():raise ValueError('되돌리기 사유를 입력하세요.')
 with c:
  c.execute('DELETE FROM rlc_ledger_keys WHERE source_key=?',('unused-lock',));r=db.rows(c,'SELECT * FROM rlc_ledger_imports WHERE id=? AND reverted=0',(id,))
  if not r:raise ValueError('이미 되돌렸거나 없는 이력입니다.')
  p=json.loads(r[0]['payload'])
  if legacy.fingerprint(c,p['ids'])!=p['fingerprint']:raise ValueError('이후 수정·확정된 자료가 있습니다. 개별 메뉴에서 확인하세요.')
  for batch in db.entities(c,'batches')+db.entities(c,'batches',True):
   if any(x['deal']['id'] in p['ids'] for x in batch['items']):raise ValueError('발행본에 사용되어 일괄 되돌릴 수 없습니다.')
  for eid in p['eventids']:c.execute('UPDATE rlc_events SET deleted=1,version=version+1 WHERE id=?',(eid,))
  for did in p['newids']:
   c.execute('UPDATE rlc_deals SET deleted=1,version=version+1 WHERE id=?',(did,));c.execute('UPDATE rlc_rates SET deleted=1,version=version+1 WHERE deal_id=?',(did,))
  c.execute('DELETE FROM rlc_ledger_keys WHERE import_id=?',(id,));c.execute('UPDATE rlc_ledger_imports SET reverted=1 WHERE id=?',(id,));c.execute('INSERT INTO rlc_change_reasons(kind,entity_id,reason) VALUES(?,?,?)',('ledger_import',id,reason))
