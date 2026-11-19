"""Source-backed monthly work guidance; review marks never finalize financial records."""
import hashlib,json
from decimal import Decimal
import joint_store as db
import joint_workflow as flow
import collaboration as shared

LEAD=[('project','프로젝트·회원사 확인','프로젝트·회원사'),('ledger','원장 등록·확인','원장 등록'),('allocation','원가배분·월 비율 검토','원가배분내역서'),('entries','기성·하도급·회수 입력','기성·하도급·회수'),('settlement','원가정산서 검토','원가정산서'),('close','월마감·보고서 출력','월 마감·보고서 출력'),('archive','발행본·메일 확인','발행본·백업')]
NONLEAD=[('project','프로젝트·회원사 확인','프로젝트·회원사'),('ledger','당사투입비 등록·확인','당사 투입비'),('letter','공문 통보·발행 확인','공문 작성'),('entries','원가배분 접수·지급 입력','원가배분·기성·하도급·지급'),('settlement','원가정산서 검토','원가정산서'),('archive','발행본·메일 확인','발행본·백업')]
NUMBERS=['①','②','③','④','⑤','⑥','⑦']
def steps(nonlead):return NONLEAD if nonlead else LEAD

def install(c):
 c.execute('''CREATE TABLE IF NOT EXISTS jv_work_reviews(project_id INTEGER NOT NULL REFERENCES jv_projects(id),month TEXT NOT NULL,member_id INTEGER NOT NULL REFERENCES jv_members(id),step TEXT NOT NULL,status TEXT NOT NULL,reason TEXT NOT NULL,fingerprint TEXT NOT NULL,actor TEXT NOT NULL,version INTEGER NOT NULL DEFAULT 1,PRIMARY KEY(project_id,month,member_id,step))''')

def digest(value):return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,default=str).encode()).hexdigest()

def state(c,p,m,month,nonlead=None):
 month=db.period(month);nonlead=db.is_nonlead(c,p) if nonlead is None else nonlead
 project=next((r for r in db.projects(c) if r['id']==p),None);ms=db.members(c,p)
 if not project or m not in {r['id'] for r in ms}:raise ValueError('공사와 대상 회원사를 먼저 선택하세요.')
 raw=[r for r in db.ledger(c,p) if r['allocation_month']==month and (not nonlead or r['company_id']==project['owner_id'])]
 al=db.allocations(c,p,month,month);entries=[r for r in db.entries(c,p,m) if (r['entry_date'][:7]==month if r['kind'] in ['receipt','subcontract'] else r['period_start']<=month<=r['period_end'])]
 eids={r['id'] for r in entries};fees=[r for r in flow.groups(c,p,m) if eids.intersection(json.loads(r['receipt_ids']))]
 ids={r['id'] for r in raw};feeids={r['id'] for r in fees};runs=[]
 for run in flow.runs(c,p,m):
  selected=json.loads(run['selection']);refs={i for key in ['receipts','subcontracts','recoveries'] for i in selected.get(key,[])};claims=set(selected.get('claims',[]))
  if refs.intersection(eids) or claims.intersection({-i for i in eids} if nonlead else ids) or feeids.intersection(selected.get('fees',[])):runs.append(run)

 docs=[]
 from joint_letter_manage import visible as visible_documents
 for d in visible_documents(c,p):
  if not nonlead and d['member_id']!=m:continue
  body=json.loads(d['snapshot'])
  if body.get('start','')<=month<=body.get('end',''):docs.append(d)
 letters=[d for d in docs if d['kind']=='공문'];closed=flow.is_closed(c,p,month)
 by={}
 for a in al:by.setdefault(a['ledger_id'],[]).append(a)
 invalid=0
 for r in raw:
  a=by.get(r['id'],[])
  if {x['member_id'] for x in a}!={x['id'] for x in ms} or sum((db.num(x['base']) for x in a),Decimal(0))!=sum((db.num(r[k]) for k in ['tax_supply','invoice','receipt']),Decimal(0)) or sum((db.num(x['vat']) for x in a),Decimal(0))!=db.num(r['vat']):invalid+=1
 import joint_allocation as allocation
 _,unknown=allocation.effective_details(raw,al,allocation.details(c,p,month)) if not nonlead else ({},set())
 import joint_month_shares
 monthly=joint_month_shares.record(c,p,month)
 config_ok=bool(ms) and sum((db.num(x['share']) for x in ms),Decimal(0))==100 and project['owner_id'] in {x['company_id'] for x in ms}
 source={'project':[project,ms],'ledger':raw,'allocation':[raw,al,monthly],'entries':[entries,fees],'settlement':[raw,al,entries,fees,runs],'close':[closed,raw,al,letters],'letter':[raw,letters],'archive':[docs,raw,al,entries,runs]}
 tips={'project':'공사·관리법인·회원사·계약 지분율을 확인하세요.','ledger':'선택 월 원장과 등록 건수·금액을 확인하세요.','allocation':'미배분·검산을 확인하고 필요하면 월별 배분비율을 조정하세요.','entries':'해당 월 기성·하도급·회수/지급을 확인하세요. 없는 업무는 사유와 함께 해당 없음으로 표시할 수 있습니다.','settlement':'청구·공제·지급/회수 범위를 선택하고 정산서를 검토하세요.','close':'마감 후 공문·보고서를 출력하세요. 안내의 확인 완료는 월마감을 대신하지 않습니다.','letter':'공문 내용을 확인하고 발행하세요. 실제 송부는 직접 확인해야 합니다.','archive':'발행본을 확인하고 필요한 경우 기존 메일 송부 화면에서 직접 발송·이력을 확인하세요.'}
 counts={'project':f'회원사 {len(ms)}개','ledger':f'원장 {len(raw)}건','allocation':f'원장 {len(raw)}건 · 미배분/불일치 {invalid}건','entries':f'입력 {len(entries)}건 · 관리비 정산 {len(fees)}건','settlement':f'선택 월 연결 정산 {len(runs)}건','close':'마감 완료' if closed else '미마감','letter':f'공문 {len(letters)}건','archive':f'발행본 {len(docs)}건 · 메일 이력은 송부 화면 확인'}
 ready={'project':config_ok,'ledger':bool(raw),'allocation':bool(raw) and not invalid and not unknown,'entries':bool(entries or fees),'settlement':bool(entries) if nonlead else bool(raw) and not invalid and not unknown,'close':closed,'letter':bool(letters),'archive':bool(docs)}
 marks={r['step']:r for r in db.rows(c,'SELECT * FROM jv_work_reviews WHERE project_id=? AND month=? AND member_id=?',(p,month,m))};out=[]
 for i,(key,label,target) in enumerate(steps(nonlead)):
  fp=digest(source[key]);base='완료' if key=='project' and config_ok or key=='close' and closed or closed and key in ['ledger','allocation'] else '검토 필요' if key=='allocation' and raw and (invalid or unknown) else '작성 중' if ready[key] else '미등록'
  mark=marks.get(key)
  if mark and mark['status']!='reset':base=('완료' if mark['status']=='reviewed' else '해당 없음') if mark['fingerprint']==fp else '검토 필요'
  out.append(dict(step=key,label=label,target=target,number=NUMBERS[i],status=base,detail=counts[key],tip=tips[key],ready=ready[key],optional=key in ['entries','archive'],empty=not(entries or fees) if key=='entries' else not docs,fingerprint=fp,mark=mark))
 return out

def review(c,p,m,month,step,status,reason,expected):
 reason=str(reason or '')
 if status not in ['reviewed','na','reset']:raise ValueError('확인 상태를 선택하세요.')
 with c:
  c.execute('DELETE FROM jv_work_reviews WHERE project_id=-1')
  row=next((r for r in state(c,p,m,month) if r['step']==step),None)
  if not row or row['fingerprint']!=expected:raise ValueError('자료가 변경되었습니다. 진행 현황을 다시 확인하세요.')
  if status=='reviewed' and not row['ready']:raise ValueError('자료 또는 검토 조건을 먼저 확인하세요. 이 확인은 실제 등록·발행·마감을 대신하지 않습니다.')
  if status=='na' and (not row['optional'] or not row['empty'] or not reason.strip()):raise ValueError('해당 없음은 선택 가능한 업무에 자료가 없을 때 사유를 입력해 표시하세요.')
  actor=shared.RUN.get()['user']['username'];reason=reason.strip() or '사용자 검토 완료' if status!='reset' else reason.strip() or '확인 해제'
  c.execute('INSERT INTO jv_work_reviews(project_id,month,member_id,step,status,reason,fingerprint,actor) VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(project_id,month,member_id,step) DO UPDATE SET status=excluded.status,reason=excluded.reason,fingerprint=excluded.fingerprint,actor=excluded.actor,version=version+1',(p,db.period(month),m,step,status,reason,expected,actor))
