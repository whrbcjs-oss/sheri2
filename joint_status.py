"""Nonlead monthly status snapshots and auditable manual investment exclusions."""
import json
from decimal import ROUND_HALF_UP
import joint_store as db
import joint_workflow as flow

CATEGORIES=['영업비','보증수수료','급여 및 4대보험','기타비용']
RATIOS=['미설정','수입 ÷ 지출총계 × 100','지출총계 ÷ 수입 × 100']

def install(c):
 c.executescript('''
 CREATE TABLE IF NOT EXISTS jv_status_manual(id INTEGER PRIMARY KEY,project_id INTEGER NOT NULL REFERENCES jv_projects(id),member_id INTEGER NOT NULL REFERENCES jv_members(id),month TEXT NOT NULL,kind TEXT NOT NULL,category TEXT NOT NULL,amount TEXT NOT NULL,note TEXT NOT NULL,included INTEGER NOT NULL,version INTEGER NOT NULL DEFAULT 1,deleted INTEGER NOT NULL DEFAULT 0);
 CREATE TABLE IF NOT EXISTS jv_status_contract_values(project_id INTEGER NOT NULL REFERENCES jv_projects(id),member_id INTEGER NOT NULL REFERENCES jv_members(id),company_id INTEGER NOT NULL REFERENCES jv_companies(id),contract TEXT NOT NULL,manual INTEGER NOT NULL DEFAULT 0,PRIMARY KEY(project_id,member_id,company_id));
 CREATE TABLE IF NOT EXISTS jv_status_records(id INTEGER PRIMARY KEY,project_id INTEGER NOT NULL REFERENCES jv_projects(id),member_id INTEGER NOT NULL REFERENCES jv_members(id),run_id INTEGER NOT NULL REFERENCES jv_runs(id),month TEXT NOT NULL,payload TEXT NOT NULL,version INTEGER NOT NULL DEFAULT 1,deleted INTEGER NOT NULL DEFAULT 0);
 ''')
 missing_date='entry_date' not in {r[1] for r in c.execute('PRAGMA table_info(jv_status_manual)')}
 if missing_date or c.execute("SELECT 1 FROM jv_status_manual WHERE entry_date='' LIMIT 1").fetchone():
  if hasattr(c,'path') and c.execute('SELECT 1 FROM jv_status_manual LIMIT 1').fetchone():db.shared.backup_database(c.path)
  ctx=db.shared.RUN.get()
  c.create_function('current_actor',0,lambda:ctx['user']['username'] if ctx else 'system')
  if missing_date:c.execute("ALTER TABLE jv_status_manual ADD COLUMN entry_date TEXT NOT NULL DEFAULT ''")
  c.execute("UPDATE jv_status_manual SET entry_date=month||'-01' WHERE entry_date=''")
  for op in ['INSERT','UPDATE','DELETE']:c.execute('DROP TRIGGER IF EXISTS audit_jv_status_manual_'+op)
  c.commit()
def scope(c,p,m):
 if not db.is_nonlead(c,p):raise ValueError('당사비주관공사에서 사용하는 현황입니다.')
 project=next((x for x in db.projects(c) if x['id']==p),None);member=next((x for x in db.members(c,p) if x['id']==m),None)
 if not project or not member or member['company_id']!=project['owner_id']:raise ValueError('해당 공사의 관리법인 회원사를 선택하세요.')
 return project,member

def manual(c,p,m,month,deleted=False):
 return db.rows(c,'SELECT * FROM jv_status_manual WHERE project_id=? AND member_id=? AND month=? AND deleted=? ORDER BY entry_date,id',(p,m,db.period(month),int(deleted)))
def save_manual(c,p,m,month,kind,category,amount,note,included=False,id=None,expected=None,entry_date=None):
 scope(c,p,m);month=db.period(month);flow.ensure_open(c,p,month)
 entry_date=db.day(entry_date or month+'-01')
 if entry_date[:7]!=month:raise ValueError('입력 기준일은 기준월 내로 지정하세요.')
 if kind not in ['영업비','안분제외'] or category not in CATEGORIES or kind=='영업비' and category!='영업비':raise ValueError('비용 구분을 확인하세요.')
 amount=db.num(amount)
 if amount<0:raise ValueError('금액은 0원 이상 입력하세요.')
 if not str(note).strip():raise ValueError('입력 사유·적요를 입력하세요.')
 with c:
  if id:
   old=next((r for r in manual(c,p,m,month) if r['id']==id),None)
   if not old or expected!=old['version']:raise ValueError('수동입력 내역이 변경되었습니다. 다시 불러오세요.')
   c.execute('UPDATE jv_status_manual SET kind=?,category=?,amount=?,note=?,included=?,entry_date=?,version=version+1 WHERE id=?',(kind,category,str(amount),note,int(bool(included) if kind=='안분제외' else False),entry_date,id))
  else:id=c.execute('INSERT INTO jv_status_manual(project_id,member_id,month,kind,category,amount,note,included,entry_date) VALUES(?,?,?,?,?,?,?,?,?)',(p,m,month,kind,category,str(amount),note,int(bool(included) if kind=='안분제외' else False),entry_date)).lastrowid
 return id

def set_manual_deleted(c,p,m,month,id,version,deleted):
 scope(c,p,m);flow.ensure_open(c,p,month)
 old=next((r for r in manual(c,p,m,month,not deleted) if r['id']==id),None)
 if not old or old['version']!=version:raise ValueError('수동입력 내역이 변경되었습니다. 다시 불러오세요.')
 with c:c.execute('UPDATE jv_status_manual SET deleted=?,version=version+1 WHERE id=?',(int(deleted),id))

def records(c,p,m,run_id=None,deleted=False):
 out=[dict(r,data=json.loads(r['payload'])) for r in db.rows(c,'SELECT * FROM jv_status_records WHERE project_id=? AND member_id=? AND deleted=? ORDER BY month DESC,id DESC',(p,m,int(deleted)))]
 return [r for r in out if run_id is None or r['run_id']==run_id]
def get(c,p,m,id,deleted=False):
 r=next((r for r in records(c,p,m,deleted=deleted) if r['id']==id),None)
 if not r:raise ValueError('해당 프로젝트·회원사의 현황을 선택하세요.')
 return r

def notices(c,p,month):
 result=[]
 from joint_letter_manage import visible
 for r in visible(c,p):
  if r['kind']!='공문':continue
  value=json.loads(r['snapshot'])
  if value.get('investment_letter') and value.get('start')==month and value.get('end')==month:result.append(dict(id=r['id'],number=r['number'],issued=r['issued'],data=value))
 return result

def investment(c,p,m,month,source_doc=None,as_of=None,months=None):
 project,member=scope(c,p,m)
 months=sorted(set(months or [month]));source=[];labels=[]
 by_month={}
 for row in db.ledger(c,p):
  if row['company_id']==project['owner_id']:by_month.setdefault(row['allocation_month'],[]).append(row)
 doc=next((d for period in months for d in notices(c,p,period) if d['id']==source_doc),None) if source_doc else None
 if source_doc and not doc:raise ValueError('정산 대상월의 당사투입비 통보 발행본을 확인하세요.')
 for period in months:
  if doc and doc['data']['start']==period:source+=doc['data']['investment_rows'];labels.append(doc['number'])
  else:source += by_month.get(period,[])
 label=' + '.join(labels+(['현재 당사투입비 (미발행 자료 포함)'] if not doc or len(months)>1 else []))
 if as_of:source=[row for row in source if row['posting_date']<=db.day(as_of)]
 totals={k:db.num(0) for k in CATEGORIES};unknown=[]
 aliases={'급여':'급여 및 4대보험','급여및4대보험':'급여 및 4대보험','급여4대보험':'급여 및 4대보험','보증수수료':'보증수수료','기타비용':'기타비용'}
 for row in source:
  category='급여 및 4대보험' if str(row.get('note','')).strip()=='급여' else aliases.get(''.join(str(row['account']).split()).replace('·','').replace('/',''))
  amount=sum((db.num(row[k]) for k in ['tax_supply','invoice','receipt']),db.num(0))
  if category:totals[category]+=amount
  else:
   totals['기타비용']+=amount
   unknown.append(dict(id=row['id'],account=row['account'],amount=str(amount)))
 return dict(totals={k:str(v) for k,v in totals.items()},source_label=label,source_rows=source,unmapped=unknown)

def settlement_months(c,p,m,run_id,month):
 run=next((r for r in flow.runs(c,p,m) if r['id']==run_id),None)
 if not run:return [db.period(month)]
 selection=json.loads(run['selection']);lookup={r['id']:r for r in flow.claim_rows(c,p,m)}
 return sorted({lookup[id]['month'] for id in selection.get('claims',[]) if id in lookup}) or [db.period(month)]

def cumulative_months(c,p,m,month):
 scope(c,p,m);month=db.period(month)
 periods={month}
 periods.update(r['allocation_month'] for r in db.ledger(c,p) if r['allocation_month']<=month)
 periods.update(r['month'] for r in db.rows(c,'SELECT DISTINCT month FROM jv_status_manual WHERE project_id=? AND member_id=? AND month<=?',(p,m,month)))
 periods.update(r['month'] for r in flow.claim_rows(c,p,m) if r['month']<=month)
 return sorted(periods)

def cumulative_selection(c,p,m,month,as_of):
 selection={k:[] for k in flow.SELECTIONS}
 # Claim period and entry date both must be within the reporting cutoff.
 claims={-e['id'] for e in flow.source_entries(c,p,m,'allocation_receipt') if e['period_start']<=month and e['entry_date']<=as_of}
 selection['claims']=[r['id'] for r in flow.claim_rows(c,p,m) if r['month']<=month and r['id'] in claims]
 for kind,key in [('receipt','receipts'),('recovery','recoveries'),('subcontract','subcontracts')]:
  selection[key]=[e['id'] for e in flow.source_entries(c,p,m,kind) if e['period_start']<=month and (e['data'].get('paid_date',e['entry_date']) if kind=='subcontract' else e['entry_date'])<=as_of]
 # Insurance is counted only when its stored stage receipt scope is fully
 # within the cutoff; later receipts are never pulled into this month.
 return selection

def cumulative_insurance(c,p,m,month,as_of):
 eligible={e['id'] for e in flow.source_entries(c,p,m,'receipt') if e['period_start']<=month and e['entry_date']<=as_of}
 total=db.num(0)
 member=next(r for r in db.members(c,p) if r['id']==m)
 if not member['fee_enabled']:return total
 for group in flow.groups(c,p,m):
  for line in json.loads(group['calculations']):
   if line.get('receipt_ids') and set(line['receipt_ids'])<=eligible:
    total+=db.num(line.get('산재보험',0))+db.num(line.get('고용보험',0))
 return total

def manual_periods(c,p,m,months,deleted=False):
 wanted={db.period(period) for period in months}
 return [r for r in db.rows(c,'SELECT * FROM jv_status_manual WHERE project_id=? AND member_id=? AND deleted=? ORDER BY entry_date,id',(p,m,int(deleted))) if r['month'] in wanted]

def contract_defaults(c,p,m,month,cumulative=False):
 project,member=scope(c,p,m);members=db.members(c,p)
 prior=next((r['data'] for r in records(c,p,m) if r['month']<month),None)
 previous={int(r['company_id']):r for r in prior.get('contracts',[])} if prior else {}
 profiles={r['company_id']:r for r in db.rows(c,'SELECT * FROM jv_status_contract_values WHERE project_id=? AND member_id=?',(p,m))}
 latest=records(c,p,m)
 if cumulative:latest=[r for r in latest if r['month']<=month]
 current_month=next((r['data'] for r in latest if r['month']==month),{}) if cumulative else {}
 current_values={int(r['company_id']):r for r in current_month.get('contracts',[])}
 legacy={int(row['company_id']):row for row in latest[0]['data'].get('contracts',[])} if latest else {}
 out=[]
 for row in members:
  cid=row['company_id'];basis=(db.num(project['supply'])*db.num(row['share'])/100).quantize(db.num(1),rounding=ROUND_HALF_UP)
  profile=profiles.get(cid)
  if cumulative:
   historical=legacy.get(cid)
   profile=dict(contract=historical['contract'],manual=historical.get('contract_manual',False)) if historical else None
  manual=bool(profile['manual']) if profile else cid in legacy and db.num(legacy[cid]['contract'])!=basis
  contract=profile['contract'] if profile and manual else legacy[cid]['contract'] if not profile and manual else str(basis)
  out.append(dict(company_id=cid,name=row['name'],share=row['share'],basis_contract=str(basis),contract=contract,contract_manual=manual,previous=current_values.get(cid,{}).get('previous',previous.get(cid,{}).get('cumulative','0')),current=current_values.get(cid,{}).get('current','0')))
 return out

def build(c,p,m,run_id,month,v):
 project,member=scope(c,p,m);month=db.period(month);as_of=db.day(v.get('as_of',month+'-01'))
 if v.get('aggregation')=='cumulative':
  from calendar import monthrange
  as_of=month+'-'+str(monthrange(int(month[:4]),int(month[5:]))[1])
 run=next((r for r in flow.runs(c,p,m) if r['id']==run_id),None)
 if not run:raise ValueError('먼저 원가정산서에서 정산 건을 저장하고 선택하세요.')
 selection=json.loads(run['selection']);is_cumulative=v.get('aggregation')=='cumulative'
 active_selection=cumulative_selection(c,p,m,month,as_of) if is_cumulative else selection
 d=flow.selected_settlement(c,p,m,active_selection)
 claim_lookup={r['id']:r for r in flow.claim_rows(c,p,m)}
 claim_months=cumulative_months(c,p,m,month) if is_cumulative else settlement_months(c,p,m,run_id,month)
 if not is_cumulative and any(period>as_of[:7] for period in claim_months):raise ValueError('기준일 이후의 청구월이 선택되어 있습니다. 기준일 또는 정산 범위를 확인하세요.')
 selected_payments=[e for e in d['entries'] if e['kind'] in ['recovery','subcontract']]
 if not is_cumulative and any(e['entry_date']>as_of for e in selected_payments):raise ValueError('선택 정산의 지급일은 기준일 이전이어야 합니다.')
 source=investment(c,p,m,month,None if is_cumulative else v.get('source_doc'),as_of,claim_months);rows=[r for r in manual_periods(c,p,m,claim_months+[month]) if r['entry_date']<=as_of]
 investment_rows=[]
 for category in CATEGORIES:
  target=sum((db.num(r['amount']) for r in rows if r['kind']=='영업비'),db.num(0)) if category=='영업비' else db.num(source['totals'][category])
  excluded=sum((db.num(r['amount']) for r in rows if r['kind']=='안분제외' and r['category']==category),db.num(0))
  investment_rows.append(dict(category=category,target=str(target),excluded=str(excluded),total=str(target+excluded)))
 contracts=[];actual={r['company_id']:r for r in db.members(c,p)};seen=set()
 for row in v.get('contracts',[]):
  cid=int(row['company_id'])
  if cid not in actual or cid in seen:raise ValueError('계약현황의 법인 목록·중복을 확인하세요.')
  seen.add(cid);amounts={k:db.num(row.get(k,0)) for k in ['contract','previous','current']}
  if any(x<0 for x in amounts.values()):raise ValueError('계약·기성 금액은 0원 이상 입력하세요.')
  cumulative=amounts['previous']+amounts['current']
  basis=(db.num(project['supply'])*db.num(actual[cid]['share'])/100).quantize(db.num(1),rounding=ROUND_HALF_UP)
  manual=bool(row.get('contract_manual',False)) or amounts['contract']!=basis
  contracts.append(dict(contract_manual=manual,basis_contract=str(basis),company_id=cid,name=actual[cid]['name'],share=actual[cid]['share'],**{k:str(a) for k,a in amounts.items()},cumulative=str(cumulative),rate=str(cumulative/amounts['contract']*100) if amounts['contract'] else None))
 if seen!=set(actual):raise ValueError('등록된 모든 법인의 계약현황을 입력하세요.')
 receipts=[e for e in flow.source_entries(c,p,m,'receipt') if e['entry_date']<=as_of and (not is_cumulative or e['period_start']<=month)]
 payments=[e for e in flow.source_entries(c,p,m,'recovery') if e['entry_date']<=as_of and (not is_cumulative or e['period_start']<=month)]
 subcontracts=[e for e in flow.source_entries(c,p,m,'subcontract') if e['data'].get('paid_date',e['entry_date'])<=as_of and (not is_cumulative or e['period_start']<=month)]
 paid_supply=sum((db.num(e['data']['supply']) for e in payments),db.num(0))
 paid_vat=sum((db.num(e['data']['vat']) for e in payments),db.num(0))
 sub_paid_supply=sum((db.num(e['data'].get('paid_supply',0)) for e in subcontracts),db.num(0))
 sub_paid_vat=sum((db.num(e['data'].get('paid_vat',0)) for e in subcontracts),db.num(0))
 target=sum((db.num(r['target']) for r in investment_rows),db.num(0))
 exclusion=sum((db.num(r['excluded']) for r in investment_rows),db.num(0))
 investment_total=target
 a=d['amounts'];insurance=cumulative_insurance(c,p,m,month,as_of) if is_cumulative else db.num(a['industrial'])+db.num(a['employment'])
 previous_status=next((r for r in records(c,p,m) if r['month']<month),None)
 previous_balance=db.num(0)
 if previous_status:
  prior_run=next((r for r in flow.runs(c,p,m) if r['id']==previous_status['run_id']),None)
  if prior_run:previous_balance=db.num(flow.selected_settlement(c,p,m,json.loads(prior_run['selection']))['amounts']['remaining'])
 hold=db.num(v.get('hold',v.get('prior_balance',0)))
 advance=db.num(v.get('advance',0))
 if hold<0 or advance<0:raise ValueError('유보액·선금반제는 0원 이상 입력하세요.')
 carry=previous_balance+hold
 selected_vat=sum((db.num(claim_lookup[id]['vat']) for id in active_selection.get('claims',[])),db.num(0))
 prior_paid=paid_supply+sub_paid_supply+target
 extra=insurance+exclusion
 income=sum((db.num(e['data']['supply']) for e in receipts),db.num(0))
 income_scope='관리법인'
 earned=sum((db.num(row['cumulative']) for row in contracts if row['company_id']==project['owner_id']),db.num(0))
 included=True
 ratio='미설정'
 def ratio_value(income):return None
 gross=sum((db.num(claim_lookup[id]['base'])+db.num(claim_lookup[id]['vat']) for id in active_selection.get('claims',[])),db.num(0))
 paid=paid_supply+paid_vat+sub_paid_supply+sub_paid_vat
 offset=investment_total+advance
 planned=gross-paid-carry-offset
 current=planned-selected_vat
 spending=prior_paid+current+extra
 return dict(schema_version=12 if is_cumulative else 11,aggregation='cumulative' if is_cumulative else 'settlement',claim_months=claim_months,project_supply=project['supply'],project_id=p,member_id=m,run_id=run_id,run_name=run['name'],month=month,as_of=as_of,selection=selection,aggregate_selection=d['selection'],source_doc=None if is_cumulative else v.get('source_doc'),source_label=source['source_label'],investment_rows=investment_rows,investment_source=source,manual_rows=rows,contracts=contracts,insurance_in_payment=included,income_scope=income_scope,ratio=ratio,cash=dict(income=str(income),earned=str(earned),previous=str(prior_paid),current=str(current),insurance=str(insurance),excluded=str(exclusion),extra=str(extra),spending=str(spending),cash_balance=str(income-spending),earned_balance=str(earned-spending),cash_ratio=ratio_value(income),earned_ratio=ratio_value(earned),target=str(target),selected_vat=str(selected_vat),statement_remaining=a['remaining']),payment=dict(claim=str(gross),paid=str(paid),previous_balance=str(previous_balance),hold=str(hold),prior_balance=str(carry),investment_offset=str(investment_total),advance=str(advance),offset=str(offset),planned=str(planned),approved=None),inputs=v,sources=dict(receipts=receipts,payments=payments,subcontracts=subcontracts,previous_status_id=previous_status['id'] if previous_status else None))

def save(c,p,m,run_id,month,v,id=None,expected=None):
 flow.ensure_open(c,p,month);data=build(c,p,m,run_id,month,v)
 with c:
  if id:
   old=get(c,p,m,id)
   if old['version']!=expected:raise ValueError('현황이 변경되었습니다. 다시 불러오세요.')
   if old['run_id']!=run_id or old['month']!=month:raise ValueError('기준월·정산 건을 변경하려면 새 현황으로 저장하세요.')
   c.execute('UPDATE jv_status_records SET payload=?,version=version+1 WHERE id=?',(json.dumps(data,ensure_ascii=False),id))
  else:
   if c.execute('SELECT 1 FROM jv_status_records WHERE project_id=? AND member_id=? AND run_id=? AND month=? AND deleted=0',(p,m,run_id,month)).fetchone():raise ValueError('같은 기준월·정산 건의 현황이 있습니다. 불러와 수정하세요.')
   id=c.execute('INSERT INTO jv_status_records(project_id,member_id,run_id,month,payload) VALUES(?,?,?,?,?)',(p,m,run_id,month,json.dumps(data,ensure_ascii=False))).lastrowid
  for row in data['contracts']:
   c.execute('INSERT INTO jv_status_contract_values(project_id,member_id,company_id,contract,manual) VALUES(?,?,?,?,?) ON CONFLICT(project_id,member_id,company_id) DO UPDATE SET contract=excluded.contract,manual=excluded.manual',(p,m,row['company_id'],row['contract'],int(row['contract_manual'])))

 return id

def set_deleted(c,p,m,id,version,deleted):
 scope(c,p,m);r=get(c,p,m,id,deleted=not deleted);flow.ensure_open(c,p,r['month'])
 if r['version']!=version:raise ValueError('현황이 변경되었습니다. 다시 불러오세요.')
 if not deleted and c.execute('SELECT 1 FROM jv_status_records WHERE project_id=? AND member_id=? AND run_id=? AND month=? AND deleted=0',(p,m,r['run_id'],r['month'])).fetchone():raise ValueError('같은 기준월·정산 건의 현황이 이미 있습니다.')
 with c:c.execute('UPDATE jv_status_records SET deleted=?,version=version+1 WHERE id=?',(int(deleted),id))

def attach(c,d,p,m,run_id,id,refresh=False):
 r=get(c,p,m,id)
 if r['run_id']!=run_id or r['data']['selection']!=d['selection']:raise ValueError('현황의 연결 정산 범위가 변경되었습니다. 현황을 다시 불러와 저장하세요.')
 data=build(c,p,m,run_id,r['month'],r['data']['inputs']) if refresh else r['data']
 return dict(d,nonlead_status=dict(data,status_id=r['id'],status_version=r['version'],source_mode='현재 원본 재계산' if refresh else '현황 저장값'))
