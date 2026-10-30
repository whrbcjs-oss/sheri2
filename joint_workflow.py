"""Selected settlement runs, receipt-based fee groups and project monthly closing."""
import json
from decimal import Decimal,ROUND_DOWN
import joint_store as db
import collaboration as shared

SELECTIONS=['receipts','fees','claims','subcontracts','recoveries']

def install(c):
    if not c.execute("SELECT 1 FROM sqlite_master WHERE name='jv_closes'").fetchone() and c.execute('SELECT 1 FROM jv_companies LIMIT 1').fetchone():shared.backup_database(c.path)
    c.executescript('''
    CREATE TABLE IF NOT EXISTS jv_sources(batch_id INTEGER PRIMARY KEY REFERENCES jv_batches(id),content TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS jv_fee_groups(id INTEGER PRIMARY KEY,project_id INTEGER NOT NULL REFERENCES jv_projects(id),member_id INTEGER NOT NULL REFERENCES jv_members(id),label TEXT NOT NULL,receipt_ids TEXT NOT NULL,calculations TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS jv_legacy_done(entry_id INTEGER PRIMARY KEY);
    CREATE TABLE IF NOT EXISTS jv_legacy_map(entry_id INTEGER PRIMARY KEY REFERENCES jv_entries(id),receipt_id INTEGER NOT NULL REFERENCES jv_entries(id),fee_id INTEGER NOT NULL REFERENCES jv_fee_groups(id));
    CREATE TABLE IF NOT EXISTS jv_runs(id INTEGER PRIMARY KEY,project_id INTEGER NOT NULL REFERENCES jv_projects(id),member_id INTEGER NOT NULL REFERENCES jv_members(id),name TEXT NOT NULL,selection TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS jv_closes(project_id INTEGER NOT NULL REFERENCES jv_projects(id),month TEXT NOT NULL,closed INTEGER NOT NULL DEFAULT 0,closed_by TEXT NOT NULL,closed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,snapshot TEXT NOT NULL,PRIMARY KEY(project_id,month));
    CREATE TABLE IF NOT EXISTS jv_close_history(id INTEGER PRIMARY KEY,project_id INTEGER NOT NULL,month TEXT NOT NULL,action TEXT NOT NULL,actor TEXT NOT NULL,reason TEXT NOT NULL,at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,snapshot TEXT NOT NULL);
    ''')

def is_closed(c,p,month):
    r=c.execute('SELECT closed FROM jv_closes WHERE project_id=? AND month=?',(p,db.period(month))).fetchone()
    return bool(r and r[0])

def ensure_open(c,p,start,end=None):
    if c.execute('SELECT 1 FROM jv_closes WHERE project_id=? AND closed=1 AND month BETWEEN ? AND ?',(p,db.period(start),db.period(end or start))).fetchone():raise ValueError('선택한 프로젝트의 해당 배분월은 마감되었습니다. 관리자가 마감을 해제한 뒤 수정하세요.')

def runs(c,p,m):return db.rows(c,'SELECT * FROM jv_runs WHERE project_id=? AND member_id=? ORDER BY id DESC',(p,m))
def groups(c,p,m):return db.rows(c,'SELECT * FROM jv_fee_groups WHERE project_id=? AND member_id=? ORDER BY id',(p,m))

def source_entries(c,p,m,kind):
    return [dict(e,data=json.loads(e['payload'])) for e in db.entries(c,p,m,kind)]

def used(c,p,m,key,exclude=None):
    ids={}
    for r in runs(c,p,m):
        if r['id']==exclude:continue
        for id in json.loads(r['selection']).get(key,[]):ids[int(id)]=r['name']
    return ids

def ensure_entry_editable(c,p,m,id):
    e=c.execute('SELECT kind,period_start,period_end FROM jv_entries WHERE id=? AND project_id=? AND member_id=?',(id,p,m)).fetchone()
    if not e:raise ValueError('수정할 내역이 없습니다.')
    ensure_open(c,p,e[1],e[2]);key={'receipt':'receipts','subcontract':'subcontracts','recovery':'recoveries'}.get(e[0])
    if key and id in used(c,p,m,key):raise ValueError('정산 건에 포함된 내역입니다. 해당 정산의 선택을 해제한 뒤 수정하세요.')
    if e[0]=='receipt' and any(id in json.loads(g['receipt_ids']) for g in groups(c,p,m)):raise ValueError('관리비·보험료 정산에 연결된 수령 내역입니다. 관리비 정산의 연결을 해제하거나 삭제한 뒤 수정하세요.')
    if e[0]=='progress':raise ValueError('이전 버전 자료입니다. 자동 이전된 공사대금과 관리비 정산에서 수정하세요.')

def ensure_claim_unassigned(c,p,id):
    for r in db.rows(c,'SELECT name,selection FROM jv_runs WHERE project_id=?',(p,)):
        if id in json.loads(r['selection']).get('claims',[]):raise ValueError('정산 건에 포함된 청구 내역입니다. 해당 정산의 선택을 해제한 뒤 배분을 수정하세요.')

def delete_entry(c,p,m,id):
    ensure_entry_editable(c,p,m,id)
    if c.execute('SELECT 1 FROM jv_legacy_map WHERE receipt_id=?',(id,)).fetchone():
        raise ValueError('이전 자료와 연결된 내역은 삭제 대신 금액을 수정하거나 반대금액을 입력하세요.')
    with c:c.execute('DELETE FROM jv_entries WHERE id=? AND project_id=? AND member_id=?',(id,p,m))

def fee_lines(c,p,m,receipt_ids,settings):
    receipts={e['id']:e for e in source_entries(c,p,m,'receipt')}
    if not receipt_ids or len(receipt_ids)!=len(set(receipt_ids)) or not set(receipt_ids)<=set(receipts):raise ValueError('해당 회원사의 공사대금 수령 내역을 선택하세요.')
    by_stage={}
    for id in receipt_ids:
        e=receipts[id];stage=e['data']['label'];by_stage.setdefault(stage,[]).append(e)
    enabled=next(x['fee_enabled'] for x in db.members(c,p) if x['id']==m)
    result=[]
    for stage,es in by_stage.items():
        v=dict(settings.get(stage,{}));rate=db.num(v.get('fee_rate',0))
        if not 0<=rate<=100:raise ValueError('관리비율은 0~100%입니다.')
        line={k:str(db.num(v.get(k,0))) for k in db.EXCLUSIONS}
        supply=sum((db.num(e['data']['supply']) for e in es),Decimal(0));vat=sum((db.num(e['data']['vat']) for e in es),Decimal(0))
        excluded=sum((db.num(line[k]) for k in db.EXCLUSIONS),Decimal(0))
        line.update(label=stage,supply=str(supply),vat=str(vat),fee_rate=str(rate),fee=str(((supply-excluded)*rate/100).quantize(Decimal('1'),rounding=ROUND_DOWN) if enabled else Decimal(0)),receipt_ids=[e['id'] for e in es])
        result.append(line)
    return result

def save_group(c,p,m,label,receipt_ids,settings,id=None):
    if not label.strip():raise ValueError('관리비·보험료 정산명을 입력하세요.')
    if m not in [x['id'] for x in db.members(c,p)]:raise ValueError('회원사를 확인하세요.')
    if id:
        old=next((g for g in groups(c,p,m) if g['id']==id),None)
        if not old:raise ValueError('수정할 관리비 정산이 없습니다.')
        if id in used(c,p,m,'fees'):raise ValueError('정산 건에 포함된 관리비입니다. 정산에서 선택을 해제한 뒤 수정하세요.')
    for g in groups(c,p,m):
        if g['id']!=id and set(receipt_ids)&set(json.loads(g['receipt_ids'])):raise ValueError('이미 다른 관리비 정산에 연결된 공사대금입니다. 중복 선택할 수 없습니다.')
    lines=fee_lines(c,p,m,receipt_ids,settings)
    relevant=set(receipt_ids)|set(json.loads(old['receipt_ids']) if id else [])
    for e in source_entries(c,p,m,'receipt'):
        if e['id'] in relevant:ensure_open(c,p,e['period_start'],e['period_end'])
    with c:
        values=(p,m,label.strip(),json.dumps(list(receipt_ids)),json.dumps(lines,ensure_ascii=False))
        if id:c.execute('UPDATE jv_fee_groups SET project_id=?,member_id=?,label=?,receipt_ids=?,calculations=? WHERE id=?',values+(id,))
        else:id=c.execute('INSERT INTO jv_fee_groups(project_id,member_id,label,receipt_ids,calculations) VALUES(?,?,?,?,?)',values).lastrowid
    return id

def delete_group(c,p,m,id):
    g=next((x for x in groups(c,p,m) if x['id']==id),None)
    if not g:raise ValueError('관리비 정산을 확인하세요.')
    if id in used(c,p,m,'fees'):raise ValueError('정산 건의 선택을 먼저 해제하세요.')
    ids=json.loads(g['receipt_ids'])
    for e in source_entries(c,p,m,'receipt'):
        if e['id'] in ids:ensure_open(c,p,e['period_start'],e['period_end'])
    with c:
        c.execute('DELETE FROM jv_legacy_map WHERE fee_id=?',(id,))
        c.execute('DELETE FROM jv_fee_groups WHERE id=?',(id,))

def migrate(c):
    # Preserve old records/documents; create linked receipts and fee groups once.
    with c:c.execute('INSERT OR IGNORE INTO jv_legacy_done SELECT entry_id FROM jv_legacy_map')
    old=db.rows(c,"SELECT e.* FROM jv_entries e WHERE kind='progress' AND NOT EXISTS(SELECT 1 FROM jv_legacy_done x WHERE x.entry_id=e.id)")
    if not old:return
    shared.backup_database(c.path)
    with c:
        for e in old:
            v=json.loads(e['payload']);label=v.get('label') or '이전 기성 '+str(e['id']);v['label']=label
            rid=c.execute('INSERT INTO jv_entries(project_id,member_id,kind,entry_date,period_start,period_end,payload) VALUES(?,?,?,?,?,?,?)',(e['project_id'],e['member_id'],'receipt',e['entry_date'],e['period_start'],e['period_end'],json.dumps(dict(label=label,supply=v.get('supply','0'),vat=v.get('vat','0'),note=v.get('note','')),ensure_ascii=False))).lastrowid
            v['receipt_ids']=[rid]
            gid=c.execute('INSERT INTO jv_fee_groups(project_id,member_id,label,receipt_ids,calculations) VALUES(?,?,?,?,?)',(e['project_id'],e['member_id'],'이전 기성 정산 '+str(e['id']),json.dumps([rid]),json.dumps([v],ensure_ascii=False))).lastrowid
            c.execute('INSERT INTO jv_legacy_map VALUES(?,?,?)',(e['id'],rid,gid))
            c.execute('INSERT INTO jv_legacy_done VALUES(?)',(e['id'],))

def claim_rows(c,p,m):
    all_al=db.allocations(c,p,'2000-01','2100-12');raw={e['id']:e for e in db.ledger(c,p)};member=next(x for x in db.members(c,p) if x['id']==m);owner=next(x for x in db.projects(c) if x['id']==p)['owner_id']
    return [dict(id=x['ledger_id'],month=x['allocation_month'],account=x['account'],description=x['description'],base=x['base'],vat=x['vat'],invested=str(db.num(raw[x['ledger_id']]['tax_supply'])+db.num(raw[x['ledger_id']]['invoice'])+db.num(raw[x['ledger_id']]['receipt'])) if member['company_id']!=owner and raw[x['ledger_id']]['company_id']==member['company_id'] else '0') for x in all_al if x['member_id']==m]

def selected_settlement(c,p,m,selection):
    if m not in [x['id'] for x in db.members(c,p)]:raise ValueError('해당 프로젝트에 등록된 회원사를 선택하세요.')
    sel={k:list(map(int,selection.get(k,[]))) for k in SELECTIONS}
    for k,v in sel.items():
        if len(v)!=len(set(v)):raise ValueError('선택 내역이 중복되었습니다.')
    receipts={e['id']:e for e in source_entries(c,p,m,'receipt')};gs={g['id']:g for g in groups(c,p,m)}
    if not set(sel['receipts'])<=set(receipts) or not set(sel['fees'])<=set(gs):raise ValueError('다른 프로젝트·회원사의 자료를 선택할 수 없습니다.')
    claims={x['id']:x for x in claim_rows(c,p,m)}
    if not set(sel['claims'])<=set(claims):raise ValueError('선택한 청구 내역에 미배분 또는 다른 프로젝트 자료가 있습니다.')
    chosen=[];management=[];covered=set();member=next(x for x in db.members(c,p) if x['id']==m)
    for gid in sel['fees']:
        g=gs[gid];ids=set(json.loads(g['receipt_ids']))
        if not ids<=set(sel['receipts']):raise ValueError('선택한 관리비 정산에 포함된 공사대금 수령 건을 모두 선택하세요.')
        if ids&covered:raise ValueError('관리비 정산의 공사대금이 중복되었습니다.')
        covered|=ids
        for v in json.loads(g['calculations']):management.append(dict(id=-gid,kind='progress',entry_date='',period_start='',period_end='',data=v))
    if member['fee_enabled'] and set(sel['receipts'])-covered:raise ValueError('선택한 공사대금에 대한 관리비·보험료 정산을 먼저 등록하고 함께 선택하세요.')
    receipt_list=[]
    for rid in sel['receipts']:
        e=receipts[rid];v=dict(e['data'],fee='0',산재보험='0',고용보험='0');receipt_list.append(dict(e,data=v))
        if rid not in covered:
            management.append(dict(e,kind='progress',data=dict(v,fee_rate='0',**{k:'0' for k in db.EXCLUSIONS})))
    # Fee/insurance amounts appear on the final receipt of each milestone.
    by_id={e['id']:e for e in receipt_list}
    for e in management:
        ids=e['data'].get('receipt_ids',[])
        if ids:
            last=max(ids,key=lambda id:(receipts[id]['entry_date'],id));v=by_id[last]['data']
            for k in ['fee','산재보험','고용보험']:v[k]=str(db.num(v[k])+db.num(e['data'].get(k,0)))
    chosen.extend(management)
    for kind,key in [('subcontract','subcontracts'),('recovery','recoveries')]:
        source={e['id']:e for e in source_entries(c,p,m,kind)}
        if not set(sel[key])<=set(source):raise ValueError('선택한 수기 내역이 해당 프로젝트·회원사의 자료가 아닙니다.')
        chosen.extend(source[id] for id in sel[key])
    raw=[x for x in db.ledger(c,p) if x['id'] in sel['claims']];al=[x for x in db.allocations(c,p,'2000-01','2100-12') if x['ledger_id'] in sel['claims']]
    d=db.assemble(c,p,m,raw,al,chosen)
    d.update(selection=sel,selection_mode=True,receipt_entries=sorted(receipt_list,key=lambda x:(x['entry_date'],x['id'])),management_entries=management)
    return d

def save_run(c,p,m,name,selection,id=None):
    if not name.strip():raise ValueError('정산명을 입력하세요.')
    if id and not c.execute('SELECT 1 FROM jv_runs WHERE id=? AND project_id=? AND member_id=?',(id,p,m)).fetchone():raise ValueError('정산 건을 확인하세요.')
    d=selected_settlement(c,p,m,selection)
    if not any(d['selection'].values()):raise ValueError('정산할 내역을 선택하세요.')
    for key,ids in d['selection'].items():
        overlap=set(ids)&set(used(c,p,m,key,id))
        if overlap:raise ValueError('이미 다른 정산에 포함된 '+{'receipts':'공사대금','fees':'관리비','claims':'청구','subcontracts':'하도급','recoveries':'회수'}[key]+' 내역입니다. 중복 정산할 수 없습니다.')
    with c:
        values=(p,m,name.strip(),json.dumps(d['selection']))
        if id:c.execute('UPDATE jv_runs SET project_id=?,member_id=?,name=?,selection=? WHERE id=?',values+(id,))
        else:id=c.execute('INSERT INTO jv_runs(project_id,member_id,name,selection) VALUES(?,?,?,?)',values).lastrowid
    return id

def month_letter(c,p,m,month):
    month=db.period(month);raw=[x for x in db.ledger(c,p) if x['allocation_month']==month];al=db.allocations(c,p,month,month)
    opening=source_entries(c,p,m,'opening')
    if any(e['period_start']<=month<=e['period_end'] and (e['period_start']!=month or e['period_end']!=month) for e in opening):raise ValueError('이전 버전의 전월 미수·이자가 여러 달에 걸쳐 있습니다. 해당 내역을 선택해 배분연월 하나로 수정한 뒤 마감하세요.')
    selected=[e for e in opening if e['period_start']==month and e['period_end']==month]
    pending=sum(not c.execute('SELECT 1 FROM jv_allocations WHERE ledger_id=?',(r['id'],)).fetchone() for r in raw)
    return db.assemble(c,p,m,raw,al,selected,month,month,pending)

def close_month(c,p,month,token):
    user=shared.validate_session(token)
    if not user:raise PermissionError('로그인 후 마감하세요.')
    month=db.period(month)
    if is_closed(c,p,month):raise ValueError('이미 마감한 배분월입니다.')
    raw=[x for x in db.ledger(c,p) if x['allocation_month']==month]
    if not raw:raise ValueError('해당 배분월의 원장이 없습니다.')
    ms=db.members(c,p);letters={str(m['id']):month_letter(c,p,m['id'],month) for m in ms}
    if any(d['unallocated'] for d in letters.values()):raise ValueError('미배분 원장이 있습니다. 원가배분을 완료한 뒤 마감하세요.')
    al=db.allocations(c,p,month,month)
    for r in raw:
        allocated=[a for a in al if a['ledger_id']==r['id']]
        if {a['member_id'] for a in allocated}!={m['id'] for m in ms}:raise ValueError('회원사 배분이 누락되었습니다.')
        if sum((db.num(a['base']) for a in allocated),Decimal(0))!=sum((db.num(r[k]) for k in ['tax_supply','invoice','receipt']),Decimal(0)) or sum((db.num(a['vat']) for a in allocated),Decimal(0))!=db.num(r['vat']):raise ValueError('원장과 배분 합계가 일치하지 않습니다.')
    originals=db.rows(c,'SELECT b.id,b.name,b.digest,s.content FROM jv_batches b JOIN jv_sources s ON s.batch_id=b.id WHERE b.id IN (SELECT DISTINCT batch_id FROM jv_ledger WHERE project_id=? AND allocation_month=?)',(p,month))
    package=dict(month=month,project=next(x for x in db.projects(c) if x['id']==p),ledger=raw,allocations=al,letters=letters,originals=originals)
    text=json.dumps(package,ensure_ascii=False)
    with c:
        c.execute('INSERT INTO jv_closes(project_id,month,closed,closed_by,snapshot) VALUES(?,?,1,?,?) ON CONFLICT(project_id,month) DO UPDATE SET closed=1,closed_by=excluded.closed_by,closed_at=CURRENT_TIMESTAMP,snapshot=excluded.snapshot',(p,month,user['username'],text))
        c.execute('INSERT INTO jv_close_history(project_id,month,action,actor,reason,snapshot) VALUES(?,?,?,?,?,?)',(p,month,'마감',user['username'],'',text))
    return package

def reopen(c,p,month,token,reason):
    user=shared.require_admin(token)
    if not reason.strip():raise ValueError('마감 해제 사유를 입력하세요.')
    row=c.execute('SELECT snapshot FROM jv_closes WHERE project_id=? AND month=? AND closed=1',(p,db.period(month))).fetchone()
    if not row:raise ValueError('마감된 배분월이 아닙니다.')
    with c:
        c.execute('UPDATE jv_closes SET closed=0 WHERE project_id=? AND month=?',(p,month))
        c.execute('INSERT INTO jv_close_history(project_id,month,action,actor,reason,snapshot) VALUES(?,?,?,?,?,?)',(p,month,'마감 해제',user['username'],reason.strip(),row[0]))

def closed_package(c,p,month):
    row=c.execute('SELECT snapshot FROM jv_closes WHERE project_id=? AND month=? AND closed=1',(p,db.period(month))).fetchone()
    if not row:raise ValueError('프로젝트의 해당 배분월을 마감해야 보고서를 출력할 수 있습니다.')
    return json.loads(row[0])

def delete_run(c,p,m,id):
    if not c.execute('SELECT 1 FROM jv_runs WHERE id=? AND project_id=? AND member_id=?',(id,p,m)).fetchone():raise ValueError('삭제할 정산 건을 확인하세요.')
    # Only removes the selection links. Input rows and previously issued documents stay.
    with c:c.execute('DELETE FROM jv_runs WHERE id=? AND project_id=? AND member_id=?',(id,p,m))
