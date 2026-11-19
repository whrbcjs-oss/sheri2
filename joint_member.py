"""Non-leading projects: reported costs, received allocations and payment approval snapshots."""
import json
from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP
import joint_store as db

KINDS={'investment':'당사 투입비','claim':'대표사 배분 원가','receipt':'기성금 수금','payment':'대표사 지급'}
FIELDS={
 'investment':{'supply':'공급가액','vat':'VAT'},
 'claim':{'supply':'배분 공급가액','vat':'배분 VAT','invested':'반영 당사 투입비','subcontract':'반영 하도급 직불'},
 'receipt':{'supply':'기성 공급가액','vat':'수금 VAT'},
 'payment':{'supply':'지급 공급가액','vat':'지급 VAT'}}

def install(c):
    c.executescript('''
    CREATE TABLE IF NOT EXISTS jv_participation(project_id INTEGER PRIMARY KEY REFERENCES jv_projects(id),role TEXT NOT NULL CHECK(role IN ('lead','member')),representative_id INTEGER REFERENCES jv_companies(id));
    CREATE TABLE IF NOT EXISTS jv_member_records(id INTEGER PRIMARY KEY,project_id INTEGER NOT NULL REFERENCES jv_projects(id),kind TEXT NOT NULL,entry_date TEXT NOT NULL,month TEXT NOT NULL,label TEXT NOT NULL,payload TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS jv_member_documents(id INTEGER PRIMARY KEY,project_id INTEGER NOT NULL REFERENCES jv_projects(id),kind TEXT NOT NULL,number TEXT NOT NULL UNIQUE,issued TEXT NOT NULL,status TEXT NOT NULL DEFAULT '출력용',snapshot TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS jv_member_links(document_id INTEGER NOT NULL REFERENCES jv_member_documents(id),record_id INTEGER NOT NULL REFERENCES jv_member_records(id),PRIMARY KEY(document_id,record_id));
    ''')

def config(c,p):
    return next(iter(db.rows(c,'SELECT * FROM jv_participation WHERE project_id=?',(p,))),dict(role='lead',representative_id=None))

def validate_config(c,p,owner,company_ids,role,representative):
    if role not in ('lead','member'):raise ValueError('공사 구분을 확인하세요.')
    if role=='member' and (representative==owner or representative not in company_ids):raise ValueError('당사와 다른 참여 회사를 대표사로 선택하세요.')
    if p:
        old=config(c,p)
        changed=old['role']!=role or (role=='member' and old['representative_id']!=representative)
        if changed:
            tables=['jv_ledger','jv_entries','jv_documents','jv_runs','jv_member_records','jv_member_documents']
            if any(c.execute('SELECT 1 FROM '+t+' WHERE project_id=? LIMIT 1',(p,)).fetchone() for t in tables):
                raise ValueError('연결 자료가 있는 공사의 구분·대표사는 변경할 수 없습니다. 별도 프로젝트로 등록하세요.')
        if old['role']=='member':
            own=c.execute('SELECT owner_id FROM jv_projects WHERE id=?',(p,)).fetchone()[0]
            if own!=owner and c.execute('SELECT 1 FROM jv_member_records WHERE project_id=?',(p,)).fetchone():raise ValueError('비주관 자료가 있는 공사의 당사는 변경할 수 없습니다.')

def require_member(c,p):
    if config(c,p)['role']!='member':raise ValueError('당사비주관공사를 선택하세요.')

def records(c,p,kind=None):
    return [dict(x,data=json.loads(x['payload'])) for x in db.rows(c,'SELECT * FROM jv_member_records WHERE project_id=?'+(' AND kind=?' if kind else '')+' ORDER BY entry_date,id',(p,kind) if kind else (p,))]

def record(c,p,kind,when,month,label,values,id=None):
    require_member(c,p)
    if kind not in KINDS or not label.strip():raise ValueError('구분과 내역명을 입력하세요.')
    when,month=db.day(when),db.period(month)
    data={k:str(db.num(values.get(k,0))) for k in FIELDS[kind]}
    data.update(category=str(values.get('category','기타')),note=str(values.get('note','')))
    if kind=='investment' and data['category'] not in ['급여','보증수수료','기타','하도급 직불']:raise ValueError('투입비 구분을 확인하세요.')
    if id and not c.execute('SELECT 1 FROM jv_member_records WHERE id=? AND project_id=? AND kind=?',(id,p,kind)).fetchone():raise ValueError('수정할 내역이 없습니다.')
    if id and c.execute('SELECT 1 FROM jv_member_links WHERE record_id=?',(id,)).fetchone():raise ValueError('공문·결재 출력본에 연결된 내역입니다. 반대금액으로 정정하세요.')
    approval=values.get('approval_id')
    if kind=='payment' and approval:
        doc=next(iter(db.rows(c,"SELECT * FROM jv_member_documents WHERE id=? AND project_id=? AND kind='approval' AND status='결재완료'",(int(approval),p))),None)
        if not doc:raise ValueError('이 공사의 결재완료 건만 지급에 연결할 수 있습니다.')
        data['approval_id']=int(approval)
        approved=db.num(json.loads(doc['snapshot'])['amounts']['remaining'])
        other=sum((db.num(x['data']['supply'])+db.num(x['data']['vat']) for x in records(c,p,'payment') if x['id']!=id and x['data'].get('approval_id')==int(approval)),Decimal(0))
        total=other+db.num(data['supply'])+db.num(data['vat'])
        if not min(Decimal(0),approved)<=total<=max(Decimal(0),approved):raise ValueError('이 결재건의 지급 잔액을 초과하거나 지급 방향이 일치하지 않습니다.')
    with c:
        if id:c.execute('UPDATE jv_member_records SET entry_date=?,month=?,label=?,payload=? WHERE id=? AND project_id=?',(when,month,label.strip(),json.dumps(data,ensure_ascii=False),id,p))
        else:id=c.execute('INSERT INTO jv_member_records(project_id,kind,entry_date,month,label,payload) VALUES(?,?,?,?,?,?)',(p,kind,when,month,label.strip(),json.dumps(data,ensure_ascii=False))).lastrowid
    return id

def totals(es):
    return {k:sum((db.num(x['data'].get(k,0)) for x in es),Decimal(0)) for k in ['supply','vat','invested','subcontract']}

def calculate(source,settings):
    r=totals([x for x in source if x['kind']=='receipt']);q=totals([x for x in source if x['kind']=='claim']);pay=totals([x for x in source if x['kind']=='payment'])
    mode=settings.get('mode','관리비 정산형')
    if mode not in ['관리비 정산형','원가분담 정산형']:raise ValueError('정산 방식을 확인하세요.')
    rate=db.num(settings.get('rate',0));excluded=db.num(settings.get('excluded',0))
    if not 0<=rate<=100:raise ValueError('관리비율은 0~100%입니다.')
    raw=(r['supply']-excluded)*rate/100
    rounding=settings.get('rounding','원 미만 버림')
    if rounding not in ['원 미만 버림','반올림','버림 후 1원 가산']:raise ValueError('단수 처리 방식을 확인하세요.')
    fee=raw.quantize(Decimal('1'),rounding=ROUND_HALF_UP if rounding=='반올림' else ROUND_DOWN)
    if rounding=='버림 후 1원 가산':fee+=1
    if mode=='원가분담 정산형':fee=Decimal(0)
    insurance=db.num(settings.get('industrial',0))+db.num(settings.get('employment',0))+db.num(settings.get('other_insurance',0))
    adjustment=db.num(settings.get('adjustment',0));paid=pay['supply']+pay['vat']
    claim=q['supply']+q['vat']-q['invested']-q['subcontract']
    # No-fee projects settle received allocation claims; this is deliberately not a 0% fee calculation.
    before=(r['supply']-fee-insurance+q['vat']-q['invested']-q['subcontract']) if mode=='관리비 정산형' else claim
    precise=before-paid+adjustment
    remaining=precise.quantize(Decimal(1),rounding=ROUND_HALF_UP)
    return {k:str(v) for k,v in dict(received=r['supply'],receipt_vat=r['vat'],excluded=excluded,fee_base=r['supply']-excluded,fee=fee,insurance=insurance,base=q['supply'],vat=q['vat'],invested=q['invested'],subcontract=q['subcontract'],claim=claim,paid=paid,adjustment=adjustment,remaining=remaining,rounding_difference=remaining-precise).items()}

def snapshot(c,p,ids,settings):
    require_member(c,p);all_={x['id']:x for x in records(c,p)}
    if not ids or len(ids)!=len(set(ids)) or not set(ids)<=set(all_):raise ValueError('이 공사의 정산 대상 내역을 선택하세요.')
    source=[all_[i] for i in ids]
    if not any(x['kind'] in ['receipt','claim'] for x in source):raise ValueError('기성금 또는 접수 원가를 선택하세요.')
    project=next(x for x in db.projects(c) if x['id']==p);companies={x['id']:x for x in db.companies(c)}
    return dict(project=project,owner=companies[project['owner_id']],representative=companies[config(c,p)['representative_id']],records=source,settings=settings,amounts=calculate(source,settings))

def documents(c,p,kind=None):
    return db.rows(c,'SELECT * FROM jv_member_documents WHERE project_id=?'+(' AND kind=?' if kind else '')+' ORDER BY id DESC',(p,kind) if kind else (p,))

def save_document(c,p,kind,number,issued,ids,settings):
    require_member(c,p)
    if kind not in ['notice','approval'] or not number.strip():raise ValueError('문서 종류와 번호를 확인하세요.')
    if c.execute('SELECT 1 FROM jv_member_documents WHERE number=?',(number.strip(),)).fetchone():raise ValueError('이미 사용한 문서번호입니다.')
    issued=db.day(issued)
    if kind=='approval':d=snapshot(c,p,ids,settings)
    else:
        es={x['id']:x for x in records(c,p,'investment')}
        if not ids or len(ids)!=len(set(ids)) or not set(ids)<=set(es):raise ValueError('통보할 당사 투입비를 선택하세요.')
        if any(c.execute("SELECT 1 FROM jv_member_links l JOIN jv_member_documents d ON d.id=l.document_id WHERE l.record_id=? AND d.kind='notice'",(i,)).fetchone() for i in ids):raise ValueError('이미 통보한 투입비가 포함되어 있습니다.')
        project=next(x for x in db.projects(c) if x['id']==p);companies={x['id']:x for x in db.companies(c)}
        d=dict(project=project,owner=companies[project['owner_id']],representative=companies[config(c,p)['representative_id']],records=[es[i] for i in ids],settings=settings)
    d.update(number=number.strip(),issued=issued,kind=kind)
    with c:
        id=c.execute('INSERT INTO jv_member_documents(project_id,kind,number,issued,snapshot) VALUES(?,?,?,?,?)',(p,kind,number.strip(),issued,json.dumps(d,ensure_ascii=False))).lastrowid
        c.executemany('INSERT INTO jv_member_links(document_id,record_id) VALUES(?,?)',[(id,i) for i in ids])
    return id

def approve(c,p,id):
    require_member(c,p)
    with c:
        if not c.execute("UPDATE jv_member_documents SET status='결재완료' WHERE id=? AND project_id=? AND kind='approval' AND status='출력용'",(id,p)).rowcount:raise ValueError('결재완료로 기록할 출력본을 확인하세요.')
