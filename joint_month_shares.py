"""Month-scoped allocation shares; owner is always the 100% remainder."""
import json
import joint_store as db
import collaboration as shared

def install(c):
 c.execute('''CREATE TABLE IF NOT EXISTS jv_month_shares(project_id INTEGER NOT NULL REFERENCES jv_projects(id),month TEXT NOT NULL,payload TEXT NOT NULL,reason TEXT NOT NULL,version INTEGER NOT NULL DEFAULT 1,deleted INTEGER NOT NULL DEFAULT 0,PRIMARY KEY(project_id,month))''')

def record(c,p,month):return next(iter(db.rows(c,'SELECT * FROM jv_month_shares WHERE project_id=? AND month=?',(p,db.period(month)))),None)

def normalize(c,p,values):
 ms=db.members(c,p);project=next((r for r in db.projects(c) if r['id']==p),None)
 if not project or not ms:raise ValueError('프로젝트·회원사를 먼저 확인하세요.')
 owner=next(m['id'] for m in ms if m['company_id']==project['owner_id']);partners={m['id'] for m in ms if m['id']!=owner}
 supplied={int(k):db.num(v) for k,v in values.items()}
 if set(supplied)!=partners:raise ValueError('대표사를 제외한 모든 회원사의 월 배분비율을 입력하세요.')
 if any(not 0<=v<=100 for v in supplied.values()) or sum(supplied.values(),db.num(0))>100:raise ValueError('회원사 비율은 0~100%, 합계는 100% 이하여야 합니다.')
 supplied[owner]=100-sum(supplied.values(),db.num(0))
 return {str(k):str(v) for k,v in supplied.items()}

def members(c,p,month):
 ms=db.members(c,p);r=record(c,p,month)
 if not r or r['deleted']:return [dict(m,contract_share=m['share']) for m in ms]
 values=json.loads(r['payload'])
 if set(values)!={str(m['id']) for m in ms}:raise ValueError('등록 회원사가 변경되었습니다. 해당 월 배분비율을 확인하세요.')
 owner=next(m['id'] for m in ms if m['company_id']==next(r['owner_id'] for r in db.projects(c) if r['id']==p))
 normalized=normalize(c,p,{k:v for k,v in values.items() if int(k)!=owner})
 if normalized!=values:raise ValueError('월 배분비율 합계를 확인하세요.')
 return [dict(m,contract_share=m['share'],share=values[str(m['id'])]) for m in ms]

def guard(c,p,month,reset_manual=False):
 import joint_workflow as flow
 flow.ensure_open(c,p,month)
 ids={r['id'] for r in db.rows(c,'SELECT id FROM jv_ledger WHERE project_id=? AND allocation_month=?',(p,month))}
 for run in db.rows(c,'SELECT name,selection FROM jv_runs WHERE project_id=?',(p,)):
  if ids.intersection(json.loads(run['selection']).get('claims',[])):raise ValueError('정산 건 「'+run['name']+'」에 연결된 월입니다. 청구 범위 연결을 먼저 해제하세요.')
 existing=db.allocations(c,p,month,month)
 if any(str(r['reason']).strip() for r in existing) and not reset_manual:raise ValueError('원장별 수동 배분액이 있습니다. 수동 배분 초기화 확인 후 적용하세요.')
 return existing

def change(c,p,month,values,reason,expected=None,deleted=False,restore=False,apply=False,reset_manual=False,revision=None):
 month=db.period(month)
 if deleted and restore or values is None and not (deleted or restore):raise ValueError('저장 또는 삭제·복구 작업을 선택하세요.')
 if not str(reason).strip():raise ValueError('월 배분비율 변경 사유를 입력하세요.')
 target=normalize(c,p,values) if values is not None else None
 existing=guard(c,p,month,reset_manual)
 if existing and not apply:raise ValueError('기존 배분이 있어 해당 월 재배분 확인이 필요합니다.')
 if existing:shared.backup_database(c.path)
 with c:
  c.execute('DELETE FROM jv_month_shares WHERE project_id=-1')
  if revision is not None and revision!=shared.revision(c):raise ValueError('자료가 변경되었습니다. 월 배분내역을 다시 확인하세요.')
  old=record(c,p,month)
  if (old['version'] if old else None)!=expected:raise ValueError('월 배분비율이 변경되었습니다. 다시 불러오세요.')
  guard(c,p,month,reset_manual)
  if deleted or restore:
   if not old or bool(old['deleted'])!=bool(restore):raise ValueError('삭제·복구 상태가 변경되었습니다.')
   if restore:
    ms=db.members(c,p);owner=next(m['id'] for m in ms if m['company_id']==next(r['owner_id'] for r in db.projects(c) if r['id']==p));saved=json.loads(old['payload']);target=normalize(c,p,{k:v for k,v in saved.items() if int(k)!=owner})
   else:target=json.loads(old['payload'])
  c.execute('INSERT INTO jv_month_shares(project_id,month,payload,reason,deleted) VALUES(?,?,?,?,?) ON CONFLICT(project_id,month) DO UPDATE SET payload=excluded.payload,reason=excluded.reason,deleted=excluded.deleted,version=version+1',(p,month,json.dumps(target,ensure_ascii=False),reason.strip(),int(deleted)))
  if existing or apply:
   import joint_allocation
   joint_allocation.allocate(c,p,month,rebuild=True,transaction=False)
 return record(c,p,month)
