"""Admin-only correction of a misidentified project owner without deleting business rows."""
import hashlib,json
from pathlib import Path
import joint_store as db
import collaboration as shared

TABLES=['jv_projects','jv_members','jv_ledger','jv_batches','jv_entries','jv_runs','jv_allocations','jv_allocation_details','jv_fee_groups','jv_documents','jv_closes','jv_status_records','jv_status_manual','jv_status_contract_values','jv_letter_files','jv_ledger_deleted','jv_letter_hidden','jv_letter_recovery','jv_member_emails']
def install(c):
 c.execute('''CREATE TABLE IF NOT EXISTS jv_owner_corrections(id INTEGER PRIMARY KEY,project_id INTEGER NOT NULL REFERENCES jv_projects(id),old_company INTEGER NOT NULL,new_company INTEGER NOT NULL,reason TEXT NOT NULL,actor TEXT NOT NULL,backup_path TEXT NOT NULL,details TEXT NOT NULL,after_hash TEXT NOT NULL DEFAULT '',at TEXT DEFAULT CURRENT_TIMESTAMP)''')

def state_hash(c,p,legacy=False):
 data={}
 for table in TABLES:
  if legacy and table=='jv_letter_files':continue
  if table=='jv_projects':rows=db.rows(c,'SELECT * FROM jv_projects WHERE id=?',(p,))
  elif table in ['jv_allocations','jv_allocation_details']:rows=db.rows(c,'SELECT a.* FROM '+table+' a JOIN jv_members m ON m.id=a.member_id WHERE m.project_id=? ORDER BY a.ledger_id,a.member_id',(p,))
  elif table=='jv_letter_hidden':rows=db.rows(c,'SELECT h.* FROM jv_letter_hidden h JOIN jv_documents d ON d.id=h.document_id WHERE d.project_id=? ORDER BY h.document_id',(p,))
  else:rows=db.rows(c,'SELECT * FROM '+table+' WHERE project_id=? ORDER BY rowid',(p,))
  if table in ['jv_ledger_deleted','jv_letter_hidden','jv_letter_recovery','jv_member_emails'] and not rows:continue
  data[table]=rows
 return hashlib.sha256(json.dumps(data,sort_keys=True,ensure_ascii=False).encode()).hexdigest()

def preview(c,p,target):
 project=next((r for r in db.projects(c) if r['id']==p),None)
 company=next((r for r in db.companies(c) if r['id']==target),None)
 if not project or not company:raise ValueError('공사와 정정할 관리법인을 확인하세요.')
 old=project['owner_id'];members=db.members(c,p);member=next(r for r in members if r['company_id']==old)
 if old==target:raise ValueError('현재와 다른 관리법인을 선택하세요.')
 if any(r['company_id']==target for r in members):raise ValueError('변경할 법인이 이미 이 공사의 참여 회원사입니다. 회원사 자료를 자동 합치지 않습니다. 참여사 구성과 연결 자료를 먼저 확인하세요.')
 # An owner identity correction retains the same member ID, share and amounts.
 for table in ['jv_ledger','jv_batches','jv_status_contract_values']:
  if c.execute('SELECT 1 FROM '+table+' WHERE project_id=? AND company_id=? LIMIT 1',(p,target)).fetchone():raise ValueError('변경할 법인의 기존 연결 자료가 있어 자동 정정할 수 없습니다.')
 ledger=db.rows(c,'SELECT * FROM jv_ledger WHERE project_id=? AND company_id=?',(p,old))
 counts={table:c.execute('SELECT count(*) FROM '+table+' WHERE project_id=?',(p,)).fetchone()[0] for table in ['jv_entries','jv_runs','jv_documents','jv_closes','jv_status_records']}
 return dict(project_id=p,project_name=project['name'],old_company=old,old_name=member['name'],new_company=target,new_name=company['name'],member_id=member['id'],share=member['share'],ledger_count=len(ledger),ledger_supply=str(sum((sum((db.num(r[k]) for k in ['tax_supply','invoice','receipt']),db.num(0)) for r in ledger),db.num(0))),ledger_vat=str(sum((db.num(r['vat']) for r in ledger),db.num(0))),counts=counts,fingerprint=state_hash(c,p))

def _remap(value,old,new,name):
 if isinstance(value,list):return [_remap(r,old,new,name) for r in value]
 if not isinstance(value,dict):return value
 result={k:_remap(v,old,new,name) for k,v in value.items()}
 if value.get('company_id')==old:
  result['company_id']=new
  if 'name' in result:result['name']=name
  if 'company' in result:result['company']=name
 if value.get('owner_id')==old:result['owner_id']=new
 return result

def correct(c,p,target,reason,token,expected):
 actor=shared.require_admin(token)
 if not str(reason).strip():raise ValueError('관리법인 정정 사유를 입력하세요.')
 plan=preview(c,p,target)
 if plan['fingerprint']!=expected:raise ValueError('정정 대상 자료가 변경되었습니다. 미리보기를 다시 확인하세요.')
 backup=shared.backup_database(c.path)
 with c:
  # Acquire the guarded write transaction before verifying the reviewed plan again.
  c.execute('UPDATE jv_projects SET owner_id=owner_id WHERE id=?',(p,))
  plan=preview(c,p,target)
  if plan['fingerprint']!=expected:raise ValueError('정정 대상 자료가 변경되었습니다. 미리보기를 다시 확인하세요.')
  old=plan['old_company']
  c.execute('UPDATE jv_projects SET owner_id=? WHERE id=?',(target,p))
  c.execute('UPDATE jv_members SET company_id=? WHERE id=?',(target,plan['member_id']))
  for table in ['jv_ledger','jv_batches','jv_status_contract_values']:
   c.execute('UPDATE '+table+' SET company_id=? WHERE project_id=? AND company_id=?',(target,p,old))
  for row in db.rows(c,'SELECT id,payload FROM jv_status_records WHERE project_id=?',(p,)):
   payload=_remap(json.loads(row['payload']),old,target,plan['new_name'])
   c.execute('UPDATE jv_status_records SET payload=?,version=version+1 WHERE id=?',(json.dumps(payload,ensure_ascii=False),row['id']))
  after=state_hash(c,p)
  id=c.execute('INSERT INTO jv_owner_corrections(project_id,old_company,new_company,reason,actor,backup_path,details,after_hash) VALUES(?,?,?,?,?,?,?,?)',(p,old,target,str(reason).strip(),actor['username'],str(backup),json.dumps(plan,ensure_ascii=False),after)).lastrowid
 return id

def history(c,p):return db.rows(c,'SELECT * FROM jv_owner_corrections WHERE project_id=? ORDER BY id DESC',(p,))
def undo(c,p,id,reason,token):
 shared.require_admin(token)
 row=next((r for r in history(c,p) if r['id']==id),None)
 current=state_hash(c,p)
 compatible=row and not c.execute('SELECT 1 FROM jv_letter_files WHERE project_id=? LIMIT 1',(p,)).fetchone() and row['after_hash']==state_hash(c,p,legacy=True)
 if not row or (row['after_hash']!=current and not compatible):raise ValueError('정정 후 공사 자료가 변경되어 즉시 되돌릴 수 없습니다. 현재 자료를 확인한 뒤 새 정정으로 처리하세요.')
 return correct(c,p,row['old_company'],'정정 취소 #'+str(id)+': '+reason,token,current)
