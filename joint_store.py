"""Joint venture ledger, exact-decimal allocation and immutable document snapshots."""
from decimal import Decimal, InvalidOperation, ROUND_DOWN, ROUND_HALF_UP
from datetime import date
import hashlib
import json
import collaboration as shared

EXCLUSIONS=['산재보험','고용보험','건강보험','장기요양보험','국민연금','퇴직공제부금','환경보전비','하도급대금보증','건설기계대여보증','산업안전보건관리비','공사이행보증수수료','미확정설계공종','기타 제외']

def num(v):
    try:
        d=Decimal(str(v if v is not None else '').replace(',','').strip() or '0')
        if not d.is_finite() or abs(d)>Decimal('1e18'):raise ValueError('금액 범위를 확인하세요.')
        return d
    except (InvalidOperation,ValueError):raise ValueError(f'금액을 확인하세요: {v!r}')

def day(v):return date.fromisoformat(str(v)[:10]).isoformat()
def period(v):
    v=str(v);date.fromisoformat(v+'-01');return v

def rows(c,sql,args=()):
    cur=c.execute(sql,args);return [dict(zip([x[0] for x in cur.description],r)) for r in cur]

def connect():
    shared.DATA.mkdir(parents=True,exist_ok=True)
    c=shared.connect(shared.DATA/'joint_venture.db')
    c.executescript('''
    CREATE TABLE IF NOT EXISTS jv_companies(id INTEGER PRIMARY KEY,code TEXT NOT NULL UNIQUE,name TEXT NOT NULL,info TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS jv_projects(id INTEGER PRIMARY KEY,name TEXT NOT NULL,owner_id INTEGER NOT NULL REFERENCES jv_companies(id),contract TEXT NOT NULL,supply TEXT NOT NULL,vat TEXT NOT NULL,start TEXT NOT NULL,end TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS jv_members(id INTEGER PRIMARY KEY,project_id INTEGER NOT NULL REFERENCES jv_projects(id),company_id INTEGER NOT NULL REFERENCES jv_companies(id),share TEXT NOT NULL,fee_enabled INTEGER NOT NULL,fee_rate TEXT NOT NULL,UNIQUE(project_id,company_id));
    CREATE TABLE IF NOT EXISTS jv_batches(id INTEGER PRIMARY KEY,project_id INTEGER NOT NULL REFERENCES jv_projects(id),company_id INTEGER NOT NULL REFERENCES jv_companies(id),digest TEXT NOT NULL,name TEXT NOT NULL,created_at TEXT DEFAULT CURRENT_TIMESTAMP,UNIQUE(project_id,company_id,digest));
    CREATE TABLE IF NOT EXISTS jv_ledger(id INTEGER PRIMARY KEY,project_id INTEGER NOT NULL REFERENCES jv_projects(id),company_id INTEGER NOT NULL REFERENCES jv_companies(id),posting_date TEXT NOT NULL,allocation_month TEXT NOT NULL,account TEXT NOT NULL,vendor TEXT NOT NULL,description TEXT NOT NULL,tax_supply TEXT NOT NULL,vat TEXT NOT NULL,invoice TEXT NOT NULL,receipt TEXT NOT NULL,note TEXT NOT NULL,source_key TEXT NOT NULL,batch_id INTEGER REFERENCES jv_batches(id),UNIQUE(project_id,company_id,source_key));
    CREATE TABLE IF NOT EXISTS jv_allocations(id INTEGER PRIMARY KEY,ledger_id INTEGER NOT NULL REFERENCES jv_ledger(id),member_id INTEGER NOT NULL REFERENCES jv_members(id),share TEXT NOT NULL,base TEXT NOT NULL,vat TEXT NOT NULL,original_base TEXT NOT NULL,original_vat TEXT NOT NULL,reason TEXT NOT NULL DEFAULT '',UNIQUE(ledger_id,member_id));
    CREATE TABLE IF NOT EXISTS jv_entries(id INTEGER PRIMARY KEY,project_id INTEGER NOT NULL REFERENCES jv_projects(id),member_id INTEGER NOT NULL REFERENCES jv_members(id),kind TEXT NOT NULL,entry_date TEXT NOT NULL,period_start TEXT NOT NULL,period_end TEXT NOT NULL,payload TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS jv_documents(id INTEGER PRIMARY KEY,project_id INTEGER NOT NULL REFERENCES jv_projects(id),member_id INTEGER NOT NULL REFERENCES jv_members(id),kind TEXT NOT NULL,number TEXT NOT NULL UNIQUE,issued TEXT NOT NULL,snapshot TEXT NOT NULL,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    ''')
    return shared.protect(c)

def companies(c):return rows(c,'SELECT * FROM jv_companies ORDER BY name')
def projects(c):return rows(c,'SELECT * FROM jv_projects ORDER BY id DESC')
def members(c,p):return rows(c,'SELECT m.*,c.name,c.code FROM jv_members m JOIN jv_companies c ON c.id=m.company_id WHERE project_id=? ORDER BY m.id',(p,))

def company(c,code,name,info,id=None):
    if not code.strip() or not name.strip():raise ValueError('법인코드와 법인명을 입력하세요.')
    with c:
        if id:c.execute('UPDATE jv_companies SET code=?,name=?,info=? WHERE id=?',(code.strip(),name.strip(),json.dumps(info,ensure_ascii=False),id))
        else:c.execute('INSERT INTO jv_companies(code,name,info) VALUES(?,?,?)',(code.strip(),name.strip(),json.dumps(info,ensure_ascii=False)))

def project(c,name,owner,contract,supply,vat,start,end,entries,id=None):
    if not name.strip():raise ValueError('공사명을 입력하세요.')
    start,end=day(start),day(end)
    if start>end:raise ValueError('공사기간을 확인하세요.')
    contract,supply,vat=map(num,[contract,supply,vat])
    if min(contract,supply,vat)<0 or contract!=supply+vat:raise ValueError('계약금액은 공급가액+VAT와 일치해야 합니다.')
    ids=[int(e['company_id']) for e in entries]
    if not entries or len(ids)!=len(set(ids)) or int(owner) not in ids:raise ValueError('당사를 포함해 중복 없이 회원사를 등록하세요.')
    if sum((num(e['share']) for e in entries),Decimal(0))!=100:raise ValueError('지분율 합계는 100%여야 합니다.')
    for e in entries:
        if not 0<num(e['share'])<=100 or not 0<=num(e['fee_rate'])<=100:raise ValueError('지분율·관리비율 범위를 확인하세요.')
    with c:
        values=(name.strip(),owner,str(contract),str(supply),str(vat),start,end)
        if id:
            if c.execute('SELECT 1 FROM jv_ledger WHERE project_id=?',(id,)).fetchone():raise ValueError('원장이 등록된 프로젝트의 지분 수정은 지원하지 않습니다. 정산 이력 보호를 위해 별도 프로젝트로 등록하세요.')
            c.execute('UPDATE jv_projects SET name=?,owner_id=?,contract=?,supply=?,vat=?,start=?,end=? WHERE id=?',values+(id,))
            c.execute('DELETE FROM jv_members WHERE project_id=?',(id,))
        else:id=c.execute('INSERT INTO jv_projects(name,owner_id,contract,supply,vat,start,end) VALUES(?,?,?,?,?,?,?)',values).lastrowid
        c.executemany('INSERT INTO jv_members(project_id,company_id,share,fee_enabled,fee_rate) VALUES(?,?,?,?,?)',[(id,e['company_id'],str(num(e['share'])),int(e['fee_enabled']),str(num(e['fee_rate']))) for e in entries])
    return id

LEDGER_FIELDS=['posting_date','allocation_month','account','vendor','description','tax_supply','vat','invoice','receipt','note']
def ledger(c,p):return rows(c,'SELECT l.*,c.name AS company FROM jv_ledger l JOIN jv_companies c ON c.id=l.company_id WHERE project_id=? ORDER BY posting_date,id',(p,))
def normalize(record):
    r={k:str(record.get(k,'') or '').strip() for k in LEDGER_FIELDS}
    r['posting_date']=day(r['posting_date']);r['allocation_month']=period(r['allocation_month'] or r['posting_date'][:7])
    for k in ['tax_supply','vat','invoice','receipt']:r[k]=str(num(r[k]))
    if not r['account']:raise ValueError('계정과목을 입력하세요.')
    if not any(num(r[k]) for k in ['tax_supply','vat','invoice','receipt']):raise ValueError('금액이 모두 0인 행입니다.')
    return r

def add_ledger(c,p,company_id,records,blob=None,name='수기입력'):
    if company_id not in [m['company_id'] for m in members(c,p)]:raise ValueError('프로젝트 참여사만 원가를 등록할 수 있습니다.')
    parsed=[];keys=set()
    for i,rec in enumerate(records,1):
        try:
            r=normalize(rec);voucher=str(rec.get('voucher','')).strip();line=str(rec.get('line','')).strip()
            if blob is not None and (not voucher or not line):raise ValueError('중복 방지를 위해 전표번호와 전표행 식별값이 모두 필요합니다.')
            key='voucher:'+json.dumps([r['posting_date'],voucher,line],ensure_ascii=False) if blob is not None else 'manual:'+__import__('secrets').token_hex(16)
            if key in keys or c.execute('SELECT 1 FROM jv_ledger WHERE project_id=? AND company_id=? AND source_key=?',(p,company_id,key)).fetchone():raise ValueError('중복 전표입니다. 변경 전표는 자동 덮어쓰지 않습니다.')
            keys.add(key);parsed.append((r,key))
        except ValueError as e:raise ValueError(f'{i}번째 행: {e}')
    if not parsed:raise ValueError('등록할 원장이 없습니다.')
    with c:
        batch=None
        if blob is not None:
            digest=hashlib.sha256(blob).hexdigest()
            if c.execute('SELECT 1 FROM jv_batches WHERE project_id=? AND company_id=? AND digest=?',(p,company_id,digest)).fetchone():raise ValueError('이미 업로드한 파일입니다.')
            batch=c.execute('INSERT INTO jv_batches(project_id,company_id,digest,name) VALUES(?,?,?,?)',(p,company_id,digest,name)).lastrowid
        c.executemany('INSERT INTO jv_ledger(project_id,company_id,'+','.join(LEDGER_FIELDS)+',source_key,batch_id) VALUES('+','.join(['?']*14)+')',[(p,company_id,*[r[k] for k in LEDGER_FIELDS],key,batch) for r,key in parsed])
    return len(parsed)

def split(amount,ms):
    # Round each share to won; assign rounding remainder to the largest shareholder.
    amount=num(amount);out=[(amount*num(m['share'])/100).quantize(Decimal('1'),rounding=ROUND_HALF_UP) for m in ms]
    i=max(range(len(ms)),key=lambda i:num(ms[i]['share']));out[i]+=amount-sum(out)
    return out

def allocate(c,p):
    ms=members(c,p)
    if not ms or sum((num(m['share']) for m in ms),Decimal(0))!=100:raise ValueError('지분 합계가 100%인지 확인하세요.')
    pending=rows(c,'SELECT * FROM jv_ledger l WHERE project_id=? AND NOT EXISTS(SELECT 1 FROM jv_allocations a WHERE a.ledger_id=l.id)',(p,))
    with c:
        for r in pending:
            bs=split(num(r['tax_supply'])+num(r['invoice'])+num(r['receipt']),ms);vs=split(r['vat'],ms)
            c.executemany('INSERT INTO jv_allocations(ledger_id,member_id,share,base,vat,original_base,original_vat) VALUES(?,?,?,?,?,?,?)',[(r['id'],m['id'],m['share'],str(b),str(v),str(b),str(v)) for m,b,v in zip(ms,bs,vs)])
    return len(pending)

def allocations(c,p,start,end):
    return rows(c,'''SELECT a.*,l.allocation_month,l.account,l.description,l.company_id AS investing_company,m.company_id,c.name FROM jv_allocations a JOIN jv_ledger l ON l.id=a.ledger_id JOIN jv_members m ON m.id=a.member_id JOIN jv_companies c ON c.id=m.company_id WHERE l.project_id=? AND l.allocation_month BETWEEN ? AND ? ORDER BY l.id,m.id''',(p,period(start),period(end)))

def revise(c,p,ledger_id,changes):
    existing=rows(c,'SELECT a.* FROM jv_allocations a JOIN jv_ledger l ON l.id=a.ledger_id WHERE a.ledger_id=? AND l.project_id=?',(ledger_id,p))
    if set(x['id'] for x in existing)!=set(x['id'] for x in changes):raise ValueError('해당 전표의 모든 회원사 배분액을 함께 수정하세요.')
    if any(not str(x['reason']).strip() for x in changes):raise ValueError('수정 사유를 입력하세요.')
    for col,orig in [('base','original_base'),('vat','original_vat')]:
        if sum((num(x[col]) for x in changes),Decimal(0))!=sum((num(x[orig]) for x in existing),Decimal(0)):raise ValueError('회원사 배분 합계는 원장의 공급가액·VAT와 각각 일치해야 합니다.')
    with c:c.executemany('UPDATE jv_allocations SET base=?,vat=?,reason=? WHERE id=?',[(str(num(x['base'])),str(num(x['vat'])),str(x['reason']),x['id']) for x in changes])

def entries(c,p,m,kind=None):
    return rows(c,'SELECT * FROM jv_entries WHERE project_id=? AND member_id=?'+(' AND kind=?' if kind else '')+' ORDER BY entry_date,id',(p,m,kind) if kind else (p,m))

def save_entry(c,p,m,kind,entry_date,start,end,payload,id=None):
    if m not in [x['id'] for x in members(c,p)]:raise ValueError('회원사를 확인하세요.')
    if kind not in ['progress','subcontract','recovery','opening']:raise ValueError('입력 유형을 확인하세요.')
    start,end=period(start),period(end)
    if start>end:raise ValueError('대상 기간을 확인하세요.')
    payload=dict(payload)
    required={'progress':['supply','vat','fee_rate']+EXCLUSIONS,'subcontract':['supply','vat','paid_supply','paid_vat'],'recovery':['supply','vat'],'opening':['arrears','interest']}[kind]
    for k in required:payload[k]=str(num(payload.get(k,0)))
    if kind=='progress':
        if not 0<=num(payload['fee_rate'])<=100:raise ValueError('관리비율을 확인하세요.')
        payload['fee']=str(((num(payload['supply'])-sum((num(payload[k]) for k in EXCLUSIONS),Decimal(0)))*num(payload['fee_rate'])/100).quantize(Decimal('1'),rounding=ROUND_DOWN))
    with c:
        vals=(p,m,kind,day(entry_date),start,end,json.dumps(payload,ensure_ascii=False))
        if id:
            if not c.execute('SELECT 1 FROM jv_entries WHERE id=? AND project_id=? AND member_id=? AND kind=?',(id,p,m,kind)).fetchone():raise ValueError('수정할 자료가 없습니다.')
            c.execute('UPDATE jv_entries SET project_id=?,member_id=?,kind=?,entry_date=?,period_start=?,period_end=?,payload=? WHERE id=?',vals+(id,))
        else:c.execute('INSERT INTO jv_entries(project_id,member_id,kind,entry_date,period_start,period_end,payload) VALUES(?,?,?,?,?,?,?)',vals)

def settlement(c,p,m,start,end):
    start,end=period(start),period(end)
    if start>end:raise ValueError('대상 기간을 확인하세요.')
    project=next(x for x in projects(c) if x['id']==p);ms=members(c,p);member=next(x for x in ms if x['id']==m)
    unallocated=c.execute('SELECT count(*) FROM jv_ledger l WHERE project_id=? AND allocation_month BETWEEN ? AND ? AND NOT EXISTS(SELECT 1 FROM jv_allocations a WHERE a.ledger_id=l.id)',(p,start,end)).fetchone()[0]
    al=allocations(c,p,start,end);mine=[x for x in al if x['member_id']==m]
    raw=[x for x in ledger(c,p) if start<=x['allocation_month']<=end]
    es=entries(c,p,m);selected=[]
    for e in es:
        if e['period_start']<=end and e['period_end']>=start:
            if e['period_start']<start or e['period_end']>end:raise ValueError('선택 기간에 일부만 걸치는 수기 자료가 있습니다. 기간을 넓히거나 입력 기간을 나누세요.')
            selected.append(dict(e,data=json.loads(e['payload'])))
    def total(kind,key):return sum((num(e['data'].get(key,0)) for e in selected if e['kind']==kind),Decimal(0))
    base=sum((num(x['base']) for x in mine),Decimal(0));vat=sum((num(x['vat']) for x in mine),Decimal(0))
    # Member's directly invested base is deducted, not allocated to them twice.
    invested=sum((num(x['tax_supply'])+num(x['invoice'])+num(x['receipt']) for x in raw if x['company_id']==member['company_id']),Decimal(0)) if member['company_id']!=project['owner_id'] else Decimal(0)
    sub=total('subcontract','supply');subvat=total('subcontract','vat');paid=total('subcontract','paid_supply')+total('subcontract','paid_vat')
    received=total('progress','supply');fee=total('progress','fee') if member['fee_enabled'] else Decimal(0)
    industrial=total('progress','산재보험');employment=total('progress','고용보험');deductions=fee+industrial+employment
    recovery=total('recovery','supply')+total('recovery','vat')+paid
    claim=base+vat-invested+sub+subvat
    remaining=received-deductions+vat+subvat-recovery-invested if member['fee_enabled'] else claim-recovery
    arrears=total('opening','arrears');interest=total('opening','interest')
    vals=dict(base=base,vat=vat,invested=invested,subcontract=sub,subcontract_vat=subvat,subcontract_paid=paid,received=received,fee=fee,industrial=industrial,employment=employment,deductions=deductions,recovery=recovery,claim=claim,remaining=remaining,arrears=arrears,interest=interest,letter_claim=base+vat-invested+arrears+interest,total_base=sum((num(x['tax_supply'])+num(x['invoice'])+num(x['receipt']) for x in raw),Decimal(0)),total_vat=sum((num(x['vat']) for x in raw),Decimal(0)))
    parties=[]
    for party in ms:
        party_base=sum((num(x['base']) for x in al if x['member_id']==party['id']),Decimal(0))
        party_vat=sum((num(x['vat']) for x in al if x['member_id']==party['id']),Decimal(0))
        party_invested=sum((num(x['tax_supply'])+num(x['invoice'])+num(x['receipt']) for x in raw if x['company_id']==party['company_id']),Decimal(0)) if party['company_id']!=project['owner_id'] else Decimal(0)
        prior=[json.loads(e['payload']) for e in entries(c,p,party['id'],'opening') if start<=e['period_start']<=e['period_end']<=end]
        parties.append(dict(name=party['name'],share=party['share'],base=str(party_base),vat=str(party_vat),invested=str(party_invested),arrears=str(sum((num(e.get('arrears')) for e in prior),Decimal(0))),interest=str(sum((num(e.get('interest')) for e in prior),Decimal(0)))))
    return dict(project=project,member=member,members=ms,start=start,end=end,amounts={k:str(v) for k,v in vals.items()},entries=selected,allocations=al,unallocated=unallocated,companies=companies(c),parties=parties)

def snapshot(c,data,kind,number,issued,meta):
    if kind not in ['정산서','공문'] or not number.strip():raise ValueError('문서 종류와 문서번호를 확인하세요.')
    if data['unallocated']:raise ValueError('미배분 원장이 있습니다. 배분을 완료한 뒤 확정하세요.')
    payload=dict(data,meta=meta,kind=kind,number=number.strip(),issued=day(issued))
    with c:c.execute('INSERT INTO jv_documents(project_id,member_id,kind,number,issued,snapshot) VALUES(?,?,?,?,?,?)',(data['project']['id'],data['member']['id'],kind,number.strip(),day(issued),json.dumps(payload,ensure_ascii=False)))
    return payload


def restore(c,payload,token):
    import sqlite3
    import tempfile
    from pathlib import Path
    # Validate cross-table references before the shared, schema-preserving restore.
    with tempfile.TemporaryDirectory() as folder:
        path=Path(folder)/'candidate.sqlite';path.write_bytes(payload)
        with sqlite3.connect(f'file:{path}?mode=ro',uri=True) as candidate:
            if candidate.execute('PRAGMA foreign_key_check').fetchone():raise ValueError('백업의 프로젝트·회원사 연결이 손상되었습니다.')
    c.rollback()
    return shared.restore_database(token,c.path,payload,c.expected)
