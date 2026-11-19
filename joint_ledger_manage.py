"""Scoped, reversible ledger removal with allocation-period and settlement guards."""
import json
import joint_store as db
import joint_workflow as flow
import collaboration as shared

def install(c):
 c.execute('''CREATE TABLE IF NOT EXISTS jv_ledger_deleted(ledger_id INTEGER PRIMARY KEY REFERENCES jv_ledger(id),project_id INTEGER NOT NULL REFERENCES jv_projects(id),reason TEXT NOT NULL,actor TEXT NOT NULL,deleted_at TEXT DEFAULT CURRENT_TIMESTAMP)''')

def records(c,p,cid,deleted=False):
 if cid not in [r['company_id'] for r in db.members(c,p)]:raise ValueError('해당 공사의 원가투입 회사를 선택하세요.')
 if not deleted:return [r for r in db.ledger(c,p) if r['company_id']==cid]
 return db.rows(c,'SELECT l.*,c.name AS company,d.reason AS delete_reason,d.deleted_at FROM jv_ledger l JOIN jv_ledger_deleted d ON d.ledger_id=l.id JOIN jv_companies c ON c.id=l.company_id WHERE l.project_id=? AND l.company_id=? ORDER BY l.posting_date,l.id',(p,cid))

def preview(c,p,cid,ids,restore=False):
 ids=list(map(int,ids))
 if not ids or len(ids)!=len(set(ids)):raise ValueError('중복 없이 원장을 선택하세요.')
 lookup={r['id']:r for r in records(c,p,cid,deleted=restore)}
 if not set(ids)<=set(lookup):raise ValueError('선택 원장의 공사·회사 또는 삭제 상태가 변경되었습니다. 다시 조회하세요.')
 selected=[lookup[id] for id in ids];months=sorted({r['allocation_month'] for r in selected})
 for month in months:
  if flow.is_closed(c,p,month):raise ValueError('배분연월 '+month+'은 마감되어 삭제·복구할 수 없습니다. 관리자에게 해당 배분월 마감 해제를 요청하세요. 기표일자 월과 구분하세요.')
 all_rows=db.rows(c,'SELECT id,allocation_month FROM jv_ledger WHERE project_id=?',(p,))
 cohort={r['id'] for r in all_rows if r['allocation_month'] in months}
 for row in db.rows(c,'SELECT name,selection FROM jv_runs WHERE project_id=?',(p,)):
  if cohort.intersection(json.loads(row['selection']).get('claims',[])):raise ValueError('해당 배분월 원장이 정산 건 「'+row['name']+'」에 연결되어 있습니다. 원가정산서에서 청구 범위 연결을 먼저 해제하세요.')
 reallocate=[month for month in months if c.execute('SELECT 1 FROM jv_allocations a JOIN jv_ledger l ON l.id=a.ledger_id WHERE l.project_id=? AND l.allocation_month=? LIMIT 1',(p,month)).fetchone()]
 supply=sum((sum((db.num(r[k]) for k in ['tax_supply','invoice','receipt']),db.num(0)) for r in selected),db.num(0));vat=sum((db.num(r['vat']) for r in selected),db.num(0))
 return dict(ids=ids,months=months,reallocate=reallocate,count=len(ids),supply=str(supply),vat=str(vat),total=str(supply+vat),revision=shared.revision(c),restore=restore)

def change(c,p,cid,ids,reason,token,expected,restore=False):
 actor=shared.validate_session(token)
 if not actor or not shared.RUN.get() or shared.RUN.get()['token']!=token:raise ValueError('현재 로그인 세션에서 실행하세요.')
 if not isinstance(reason,str) or not reason.strip():raise ValueError('삭제·복구 사유를 입력하세요.')
 plan=preview(c,p,cid,ids,restore)
 if plan['revision']!=expected:raise ValueError('자료가 변경되었습니다. 선택 금액과 연결 상태를 다시 확인하세요.')
 with c:
  c.execute('DELETE FROM jv_ledger_deleted WHERE ledger_id=-1')
  plan=preview(c,p,cid,ids,restore)
  if plan['revision']!=expected:raise ValueError('자료가 변경되었습니다. 다시 확인하세요.')
  manual={};details={}
  for month in plan['reallocate']:
   allocations=db.rows(c,'SELECT a.* FROM jv_allocations a JOIN jv_ledger l ON l.id=a.ledger_id WHERE l.project_id=? AND l.allocation_month=?',(p,month))
   adjusted={r['ledger_id'] for r in allocations if r['reason'].strip()}
   for r in allocations:
    if r['ledger_id'] in adjusted:manual[(r['ledger_id'],r['member_id'])]=r
   for id in adjusted:details[id]=db.rows(c,'SELECT * FROM jv_allocation_details WHERE ledger_id=?',(id,))
  for id in ids:
   if restore:c.execute('DELETE FROM jv_ledger_deleted WHERE ledger_id=?',(id,))
   else:c.execute('INSERT INTO jv_ledger_deleted(ledger_id,project_id,reason,actor) VALUES(?,?,?,?)',(id,p,str(reason).strip(),actor['username']))
  import joint_allocation as allocation
  for month in plan['reallocate']:allocation.allocate(c,p,month,rebuild=True,transaction=False)
  active={r['id'] for r in db.ledger(c,p)}
  for (id,m),r in manual.items():
   if id in active:c.execute('UPDATE jv_allocations SET base=?,vat=?,reason=? WHERE ledger_id=? AND member_id=?',(r['base'],r['vat'],r['reason'],id,m))
  for id,rows in details.items():
   if id not in active:continue
   c.execute('DELETE FROM jv_allocation_details WHERE ledger_id=?',(id,))
   for row in rows:c.execute('INSERT INTO jv_allocation_details(ledger_id,member_id,tax_supply,invoice,receipt,vat,rule) VALUES(?,?,?,?,?,?,?)',tuple(row[k] for k in ['ledger_id','member_id','tax_supply','invoice','receipt','vat','rule']))
 return plan
