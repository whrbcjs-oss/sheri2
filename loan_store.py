"""Private loan ledger, versioned contracts, receipt ledger and attached source documents."""
from pathlib import Path
from datetime import date,datetime,timedelta,timezone
import base64,hashlib,json,re
import collaboration as shared
import loan_calc as calc


def today():return datetime.now(timezone(timedelta(hours=9))).date()
def rows(c,sql,args=()):
    q=c.execute(sql,args);return [dict(zip([x[0] for x in q.description],r)) for r in q]
def dump(value):return json.dumps(value,ensure_ascii=False)


def connect():
    shared.DATA.mkdir(parents=True,exist_ok=True)
    c=shared.connect(shared.DATA/'loans.db')
    c.executescript('''
    CREATE TABLE IF NOT EXISTS ln_borrowers(id INTEGER PRIMARY KEY,name TEXT NOT NULL,national_id TEXT NOT NULL,address TEXT NOT NULL,phone TEXT NOT NULL,kind TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS ln_loans(id INTEGER PRIMARY KEY,borrower_id INTEGER NOT NULL REFERENCES ln_borrowers(id),company TEXT NOT NULL,initial_principal INTEGER NOT NULL,start_date TEXT NOT NULL,created_date TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS ln_contracts(id INTEGER PRIMARY KEY,loan_id INTEGER NOT NULL REFERENCES ln_loans(id),version INTEGER NOT NULL,number TEXT NOT NULL UNIQUE,effective_date TEXT NOT NULL,payload TEXT NOT NULL,reason TEXT NOT NULL,created_at TEXT DEFAULT CURRENT_TIMESTAMP,UNIQUE(loan_id,version));
    CREATE TABLE IF NOT EXISTS ln_receipts(id INTEGER PRIMARY KEY,loan_id INTEGER NOT NULL REFERENCES ln_loans(id),contract_id INTEGER NOT NULL REFERENCES ln_contracts(id),receipt_date TEXT NOT NULL,principal INTEGER NOT NULL,interest INTEGER NOT NULL,method TEXT NOT NULL,note TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS ln_attachments(id INTEGER PRIMARY KEY,loan_id INTEGER NOT NULL REFERENCES ln_loans(id),contract_id INTEGER NOT NULL REFERENCES ln_contracts(id),receipt_id INTEGER REFERENCES ln_receipts(id),name TEXT NOT NULL,mime TEXT NOT NULL,digest TEXT NOT NULL,content TEXT NOT NULL,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS ln_transfers(source_id INTEGER PRIMARY KEY REFERENCES ln_loans(id),target_id INTEGER NOT NULL REFERENCES ln_loans(id),effective_date TEXT NOT NULL,snapshot TEXT NOT NULL,CHECK(source_id<>target_id));
    CREATE TABLE IF NOT EXISTS ln_status_events(id INTEGER PRIMARY KEY,loan_id INTEGER NOT NULL REFERENCES ln_loans(id),event TEXT NOT NULL CHECK(event IN ('cancel','restore')),effective_date TEXT NOT NULL,reason TEXT NOT NULL,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS ln_scenarios(id INTEGER PRIMARY KEY,borrower_id INTEGER NOT NULL REFERENCES ln_borrowers(id),company TEXT NOT NULL,as_of TEXT NOT NULL,payload TEXT NOT NULL,actor TEXT NOT NULL,memo TEXT NOT NULL,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS ln_scenario_links(scenario_id INTEGER NOT NULL REFERENCES ln_scenarios(id),loan_id INTEGER NOT NULL REFERENCES ln_loans(id),contract_id INTEGER NOT NULL REFERENCES ln_contracts(id),PRIMARY KEY(scenario_id,loan_id));
    CREATE TABLE IF NOT EXISTS ln_board_resolutions(id INTEGER PRIMARY KEY,doc_root TEXT NOT NULL,version INTEGER NOT NULL,number TEXT NOT NULL,company TEXT NOT NULL,status TEXT NOT NULL,payload TEXT NOT NULL,loan_id INTEGER,contract_id INTEGER,actor TEXT NOT NULL,created_at TEXT DEFAULT CURRENT_TIMESTAMP,UNIQUE(doc_root,version));
    CREATE TABLE IF NOT EXISTS ln_notes(id INTEGER PRIMARY KEY,loan_id INTEGER NOT NULL REFERENCES ln_loans(id),contract_id INTEGER NOT NULL REFERENCES ln_contracts(id),snapshot TEXT NOT NULL,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    ''')
    return shared.protect(c)


def borrowers(c):return rows(c,'SELECT * FROM ln_borrowers ORDER BY name,id')
def contracts(c,loan_id):return [dict(r,data=json.loads(r['payload'])) for r in rows(c,'SELECT * FROM ln_contracts WHERE loan_id=? ORDER BY version',(loan_id,))]
def receipts(c,loan_id):return rows(c,'SELECT * FROM ln_receipts WHERE loan_id=? ORDER BY receipt_date,id',(loan_id,))
def borrower(c,id):return next((r for r in borrowers(c) if r['id']==id),None)


def loan(c,id,as_of=None):
    roots=rows(c,'SELECT * FROM ln_loans WHERE id=?',(id,))
    if not roots:raise ValueError('차용 내역을 찾을 수 없습니다.')
    root=roots[0];versions=contracts(c,id)
    eligible=[v for v in versions if as_of is None or v['effective_date']<=str(as_of)]
    if not eligible:return None
    version=eligible[-1]
    transfer=rows(c,'SELECT * FROM ln_transfers WHERE source_id=?',(id,))
    transfer=transfer[0] if transfer and transfer[0]['effective_date']<=str(as_of or today()) else None
    status=rows(c,'SELECT * FROM ln_status_events WHERE loan_id=? AND effective_date<=? ORDER BY effective_date DESC,id DESC LIMIT 1',(id,str(as_of or today())))
    cancellation=status[0] if status and status[0]['event']=='cancel' else None
    return dict(root,cancellation=cancellation,transfer=transfer,closed=bool(transfer or cancellation),borrower=version['data'].get('borrower') or borrower(c,root['borrower_id']),terms=version['data'],contract_id=version['id'],number=version['number'],version=version['version'],versions=versions,receipts=receipts(c,id))


def loans(c,as_of=None,include_closed=False):
    return [v for r in rows(c,'SELECT id FROM ln_loans ORDER BY id DESC') if (v:=loan(c,r['id'],as_of)) is not None and (include_closed or not v['closed'])]


def require_active(c,loan_id):
    if loan(c,loan_id).get('cancellation'):raise ValueError('취소된 차용증입니다. 취소 해제 후 관리하세요.')
    if c.execute('SELECT 1 FROM ln_transfers WHERE source_id=?',(loan_id,)).fetchone():raise ValueError('통합 승계된 기존 차용건은 변경할 수 없습니다. 통합 갱신 계약에서 관리하세요.')


def next_number(c,issued):
    prefix=calc.day(issued).strftime('%Y%m%d')+'-';numbers=rows(c,'SELECT number FROM ln_contracts WHERE number LIKE ?',(prefix+'%',))
    suffix=max([int(r['number'].split('-')[1]) for r in numbers if re.fullmatch(r'\d{8}-\d{3,}',r['number'])]+[0])+1
    return prefix+f'{suffix:03}'


def validate_number(c,number,issued,exclude=None):
    number=str(number).strip()
    if not re.fullmatch(r'\d{8}-\d{3,}',number) or not number.startswith(calc.day(issued).strftime('%Y%m%d')+'-'):raise ValueError('관리번호는 작성일 기준 YYYYMMDD-001 형식으로 입력하세요.')
    if c.execute('SELECT 1 FROM ln_contracts WHERE number=? AND id<>?',(number,exclude or -1)).fetchone():raise ValueError('이미 사용한 관리번호입니다. 다음 순번을 입력하세요.')
    return number


def clean_borrower(data):
    v={k:str(data.get(k,'')).strip() for k in ['name','national_id','address','phone','kind']}
    if not v['name']:raise ValueError('차용인 성명을 입력하세요.')
    if v['kind'] not in ['직원','개인','법인']:raise ValueError('차용인 구분을 선택하세요.')
    digits=re.sub(r'\D','',v['national_id'])
    if digits and len(digits) not in [6,8,13]:raise ValueError('주민등록번호 13자리 또는 생년월일 6·8자리로 입력하세요.')
    v['national_id']=digits[:6]+'-'+digits[6:] if len(digits)==13 else digits
    return v


def _borrower(c,data,id=None):
    v=clean_borrower(data)
    if id and not borrower(c,id):raise ValueError('차용인을 확인하세요.')
    if v['national_id'] and c.execute('SELECT 1 FROM ln_borrowers WHERE national_id=? AND id<>?',(v['national_id'],id or -1)).fetchone():raise ValueError('등록된 차용인입니다. 기존 차용인을 선택하세요.')
    values=tuple(v[k] for k in ['name','national_id','address','phone','kind'])
    if id:c.execute('UPDATE ln_borrowers SET name=?,national_id=?,address=?,phone=?,kind=? WHERE id=?',values+(id,))
    else:id=c.execute('INSERT INTO ln_borrowers(name,national_id,address,phone,kind) VALUES(?,?,?,?,?)',values).lastrowid
    return id,v


def prepared_files(files):
    result=[]
    for f in files or []:
        content=f['content'];name=str(f['name']).replace('\\','/').rsplit('/',1)[-1].strip()
        if not name or not isinstance(content,bytes):raise ValueError('첨부파일을 확인하세요.')
        if len(content)>10*1024*1024:raise ValueError('첨부파일은 파일당 10MB 이하로 등록하세요.')
        result.append(dict(name=name,mime=str(f.get('mime') or 'application/octet-stream'),digest=hashlib.sha256(content).hexdigest(),content=base64.b64encode(content).decode('ascii')))
    if sum(len(f['content']) for f in result)>40*1024*1024:raise ValueError('한 번에 첨부하는 파일의 합계는 30MB 이하로 등록하세요.')
    return result


def _attach(c,loan_id,contract_id,files,receipt_id=None):
    for f in files:
        if c.execute('SELECT 1 FROM ln_attachments WHERE loan_id=? AND contract_id=? AND COALESCE(receipt_id,0)=? AND digest=? AND name=?',(loan_id,contract_id,receipt_id or 0,f['digest'],f['name'])).fetchone():continue
        c.execute('INSERT INTO ln_attachments(loan_id,contract_id,receipt_id,name,mime,digest,content) VALUES(?,?,?,?,?,?,?)',(loan_id,contract_id,receipt_id,f['name'],f['mime'],f['digest'],f['content']))


def save_loan(c,terms,person,company,number,borrower_id=None,loan_id=None,files=()):
    v=calc.validate(terms);company=str(company).strip();person=clean_borrower(person);uploads=prepared_files(files)
    if not company:raise ValueError('차용금 지급회사를 입력하세요.')
    calc.schedule(v)
    old=loan(c,loan_id) if loan_id else None
    with c:
        number=validate_number(c,number,v['issued_date'],old['contract_id'] if old else None)
        if old:
            require_active(c,loan_id)
            if status_events(c,loan_id):raise ValueError('취소·해제 이력이 있는 계약은 변경 계약으로 관리하세요.')
            if len(old['versions'])>1:raise ValueError('갱신 이력이 있는 계약은 계약 갱신 메뉴에서 관리하세요.')
            locked=c.execute("SELECT 1 FROM ln_board_resolutions WHERE loan_id=? AND status='final'",(loan_id,)).fetchone() or c.execute('SELECT 1 FROM ln_scenario_links WHERE loan_id=?',(loan_id,)).fetchone() or c.execute('SELECT 1 FROM ln_receipts WHERE loan_id=?',(loan_id,)).fetchone() or c.execute('SELECT 1 FROM ln_notes WHERE loan_id=?',(loan_id,)).fetchone()
            if locked:raise ValueError('회수 또는 발행 이력이 있는 계약은 직접 변경할 수 없습니다. 계약 갱신을 이용하세요.')
            borrower_id=old['borrower_id']
        borrower_id,snapshot=_borrower(c,person,borrower_id)
        v.update(borrower=snapshot,company=company,number=number,collateral=str(v.get('collateral','')),note=str(v.get('note','')))
        if old:
            c.execute('UPDATE ln_loans SET borrower_id=?,company=?,initial_principal=?,start_date=? WHERE id=?',(borrower_id,company,v['principal'],v['start_date'],loan_id))
            contract_id=old['contract_id'];c.execute('UPDATE ln_contracts SET number=?,effective_date=?,payload=? WHERE id=?',(number,v['start_date'],dump(v),contract_id))
        else:
            loan_id=c.execute('INSERT INTO ln_loans(borrower_id,company,initial_principal,start_date,created_date) VALUES(?,?,?,?,?)',(borrower_id,company,v['principal'],v['start_date'],v['issued_date'])).lastrowid
            contract_id=c.execute('INSERT INTO ln_contracts(loan_id,version,number,effective_date,payload,reason) VALUES(?,1,?,?,?,?)',(loan_id,number,v['start_date'],dump(v),'최초 작성')).lastrowid
        _attach(c,loan_id,contract_id,uploads)
    return loan_id


def save_receipt(c,loan_id,receipt_date,principal,interest,method='',note='',id=None,files=()):
    require_active(c,loan_id)
    current=loan(c,loan_id);date_=calc.day(receipt_date).isoformat();p=calc.number(principal);i=calc.number(interest);uploads=prepared_files(files)
    if min(p,i)<0 or p+i<=0 or p!=p.to_integral_value() or i!=i.to_integral_value():raise ValueError('회수액은 0 이상의 원 단위 금액이며 합계는 0보다 커야 합니다.')
    if date_<current['terms']['start_date']:raise ValueError('현재 계약 시작일 이전의 회수는 해당 계약 이력에서 확인하세요.')
    with c:
        old=next((r for r in current['receipts'] if r['id']==id),None) if id else None
        if id and (not old or old['contract_id']!=current['contract_id']):raise ValueError('갱신 이전 회수내역은 변경할 수 없습니다.')
        paid=sum(r['principal'] for r in current['receipts'] if r['id']!=id)
        if paid+int(p)>current['initial_principal']:raise ValueError('회수 원금이 대여 원금을 초과합니다.')
        values=(loan_id,current['contract_id'],date_,int(p),int(i),str(method),str(note))
        if id:c.execute('UPDATE ln_receipts SET loan_id=?,contract_id=?,receipt_date=?,principal=?,interest=?,method=?,note=? WHERE id=?',values+(id,))
        else:id=c.execute('INSERT INTO ln_receipts(loan_id,contract_id,receipt_date,principal,interest,method,note) VALUES(?,?,?,?,?,?,?)',values).lastrowid
        _attach(c,loan_id,current['contract_id'],uploads,id)
    return id


def delete_receipt(c,loan_id,id):
    require_active(c,loan_id)
    v=loan(c,loan_id);r=next((r for r in v['receipts'] if r['id']==id),None)
    if not r or r['contract_id']!=v['contract_id']:raise ValueError('갱신 이전 회수내역은 삭제할 수 없습니다.')
    with c:
        c.execute('DELETE FROM ln_attachments WHERE receipt_id=? AND loan_id=?',(id,loan_id))
        c.execute('DELETE FROM ln_receipts WHERE id=? AND loan_id=?',(id,loan_id))


def summary(c,item,as_of):
    v=item;date_=calc.day(as_of)
    if v.get('transfer'):date_=min(date_,calc.day(v['transfer']['effective_date']))
    if v.get('cancellation'):date_=min(date_,calc.day(v['cancellation']['effective_date']))
    paid=[r for r in v['receipts'] if calc.day(r['receipt_date'])<=date_]
    principal=sum(r['principal'] for r in paid);interest=sum(r['interest'] for r in paid)
    current_receipts=[r for r in paid if r['contract_id']==v['contract_id']]
    plan=calc.reconcile(v['terms'],current_receipts,date_)
    upcoming=next((r for r in plan if calc.day(r['due_date'])>=date_ and r['paid']<r['total']),None)
    accrued,credit=calc.accrued_interest(v['terms'],current_receipts,date_)
    return dict(loan=v,principal=v['initial_principal'],paid_principal=principal,paid_interest=interest,balance=v['initial_principal']-principal,unpaid=sum(r['unpaid'] for r in plan),unpaid_interest=accrued,interest_credit=credit,plan=plan,next_due=upcoming['due_date'] if upcoming else '',maturity_status=calc.maturity_status(v['terms'],v['initial_principal']-principal,accrued,date_))


def renew(c,loan_id,new_terms,number,effective_date,reason,*,extend=True,person=None,files=(),issue_copy=False):
    uploads=prepared_files(files)
    require_active(c,loan_id)
    old=loan(c,loan_id);effective=calc.day(effective_date).isoformat()
    if not str(reason).strip():raise ValueError('계약 연장·갱신 사유를 입력하세요.')
    if not old['terms']['start_date']<=effective<=today().isoformat():raise ValueError('갱신 적용일은 계약 시작일 이후, 오늘 이내로 입력하세요.')
    if any(r['receipt_date']>effective for r in old['receipts']):raise ValueError('갱신 적용일 이후 회수내역이 있습니다. 적용일을 확인하세요.')
    s=summary(c,old,effective)
    if s['balance']<=0:raise ValueError('남은 원금이 없는 계약은 갱신할 수 없습니다.')
    v=dict(new_terms,principal=s['balance'],start_date=effective,carry_interest=s['unpaid_interest'],interest_credit=s['interest_credit'])
    v=calc.validate(v)
    if extend and v['end_date']<=old['terms']['end_date']:raise ValueError('연장 만료일은 기존 만료일 이후로 입력하세요.')
    calc.schedule(v)
    with c:
        number=validate_number(c,number,v['issued_date'])
        snapshot=clean_borrower(person) if person is not None else dict(old['borrower'])
        if person is not None:_borrower(c,snapshot,old['borrower_id'])
        v.update(consolidation=consolidation_preview(c,[loan_id],effective),borrower=snapshot,company=old['company'],number=number,collateral=str(v.get('collateral','')),note=str(v.get('note','')),previous_number=old['number'])
        if not extend:v['document_kind']='amendment'
        id=c.execute('INSERT INTO ln_contracts(loan_id,version,number,effective_date,payload,reason) VALUES(?,?,?,?,?,?)',(loan_id,old['version']+1,number,effective,dump(v),str(reason).strip())).lastrowid
        _attach(c,loan_id,id,uploads)
        if issue_copy:issue(c,loan_id)
    return id


def attachments(c,loan_id,contract_id=None):
    return rows(c,'SELECT id,contract_id,receipt_id,name,mime,digest,created_at FROM ln_attachments WHERE loan_id=?'+(' AND contract_id=?' if contract_id else '')+' ORDER BY id',(loan_id,contract_id) if contract_id else (loan_id,))


def attachment_bytes(c,loan_id,id):
    r=rows(c,'SELECT * FROM ln_attachments WHERE id=? AND loan_id=?',(id,loan_id))
    if not r:raise ValueError('첨부파일을 찾을 수 없습니다.')
    data=base64.b64decode(r[0]['content'],validate=True)
    if hashlib.sha256(data).hexdigest()!=r[0]['digest']:raise ValueError('첨부파일 무결성을 확인할 수 없습니다.')
    return r[0],data


def delete_attachment(c,loan_id,id):
    require_active(c,loan_id)
    row=rows(c,'SELECT contract_id,receipt_id FROM ln_attachments WHERE id=? AND loan_id=?',(id,loan_id))
    current=loan(c,loan_id)
    if not row or row[0]['contract_id']!=current['contract_id']:raise ValueError('이전 계약의 첨부는 보존됩니다.')
    if c.execute('SELECT 1 FROM ln_notes WHERE contract_id=?',(current['contract_id'],)).fetchone():raise ValueError('발행 계약의 첨부는 삭제할 수 없습니다.')
    with c:c.execute('DELETE FROM ln_attachments WHERE id=? AND loan_id=?',(id,loan_id))


def issue(c,loan_id):
    v=loan(c,loan_id);data=dict(v['terms'],attachments=[r['name'] for r in attachments(c,loan_id,v['contract_id'])],version=v['version'])
    with c:id=c.execute('INSERT INTO ln_notes(loan_id,contract_id,snapshot) VALUES(?,?,?)',(loan_id,v['contract_id'],dump(data))).lastrowid
    return id


def issued(c,loan_id):return [dict(r,data=json.loads(r['snapshot'])) for r in rows(c,'SELECT * FROM ln_notes WHERE loan_id=? ORDER BY id DESC',(loan_id,))]


def alerts(c=None,current=None):
    if c is None:
        if not (shared.DATA/'loans.db').is_file():return []
        c=connect()
    current=current or today();result=[]
    for item in loans(c,current):
        s=summary(c,item,current)
        if s['maturity_status']:
            result.append(dict(loan_id=item['id'],number=item['number'],name=item['borrower']['name'],company=item['company'],due=item['terms']['end_date'],balance=s['balance'],interest=s['unpaid_interest'],status=s['maturity_status']))
    return sorted(result,key=lambda x:x['due'])


def mask_id(value):
    digits=re.sub(r'\D','',str(value))
    return digits[:6]+'-*******' if len(digits)==13 else '생년월일 등록' if digits else ''


CARRY_POLICIES=['첫 상환일 정산','마지막 상환일 정산','회차별 분할 정산']


def consolidation_preview(c,loan_ids,effective_date):
    ids=list(loan_ids);effective=calc.day(effective_date).isoformat()
    if not ids or len(ids)!=len(set(ids)):raise ValueError('통합할 차용건을 중복 없이 선택하세요.')
    if effective>today().isoformat():raise ValueError('갱신 적용일은 오늘 이내로 입력하세요.')
    items=[];details=[]
    for id in ids:
        require_active(c,id);v=loan(c,id)
        if effective<v['terms']['start_date']:raise ValueError('갱신 적용일은 모든 선택 계약의 현재 시작일 이후여야 합니다.')
        if any(r['receipt_date']>effective for r in v['receipts']):raise ValueError('적용일 이후 회수내역이 있는 차용건입니다. 갱신 적용일을 확인하세요.')
        items.append(v)
        current=[r for r in v['receipts'] if r['contract_id']==v['contract_id'] and r['receipt_date']<=effective]
        summary_=summary(c,v,effective);paid_interest=sum(r['interest'] for r in current)
        opening_credit=int(v['terms'].get('interest_credit',0));opening_carry=int(v['terms'].get('carry_interest',0))
        earned=summary_['unpaid_interest']-summary_['interest_credit']+paid_interest+opening_credit
        details.append(dict(loan_id=id,contract_id=v['contract_id'],version=v['version'],number=v['number'],start_date=v['start_date'],original_principal=v['initial_principal'],paid_principal=summary_['paid_principal'],balance=summary_['balance'],unpaid_interest=summary_['unpaid_interest'],interest_credit=summary_['interest_credit'],total=summary_['balance']+summary_['unpaid_interest'],interest_kind=v['terms']['interest_kind'],rate=v['terms']['rate'],fixed_interest=v['terms']['fixed_interest'],basis=v['terms']['basis'],interest_start=v['terms']['start_date'],interest_end=min(effective,v['terms']['end_date']),earned_interest=max(0,earned-opening_carry),opening_carry=opening_carry,paid_interest=paid_interest,opening_credit=opening_credit))
    if len({v['borrower_id'] for v in items})!=1 or len({v['company'] for v in items})!=1:raise ValueError('같은 차용인·같은 지급회사의 차용건끼리 통합하세요.')
    principal=sum(r['balance'] for r in details);interest=sum(r['unpaid_interest'] for r in details);credit=sum(r['interest_credit'] for r in details)
    if principal<=0:raise ValueError('통합할 원금잔액이 없습니다.')
    return dict(as_of=effective,borrower_id=items[0]['borrower_id'],borrower=dict(items[0]['borrower']),company=items[0]['company'],principal=principal,unpaid_interest=interest,interest_credit=credit,total=principal+interest,rows=details)


def consolidation_terms(c,loan_ids,new_terms,number,effective_date,reason):
    if not str(reason).strip():raise ValueError('통합 갱신 사유를 입력하세요.')
    preview=consolidation_preview(c,loan_ids,effective_date)
    v=dict(new_terms,principal=preview['principal'],start_date=preview['as_of'],carry_interest=preview['unpaid_interest'],interest_credit=preview['interest_credit'])
    v=calc.validate(v);calc.schedule(v)
    if v.get('carry_policy',CARRY_POLICIES[0]) not in CARRY_POLICIES:raise ValueError('기존 미회수 이자 정산방법을 선택하세요.')
    number=validate_number(c,number,v['issued_date'])
    v.update(number=number,borrower=preview['borrower'],company=preview['company'],consolidation=preview,consolidation_reason=str(reason).strip(),collateral=str(v.get('collateral','')),note=str(v.get('note','')))
    return v


def consolidate(c,loan_ids,new_terms,number,effective_date,reason,files=()):
    uploads=prepared_files(files)
    with c:
        v=consolidation_terms(c,loan_ids,new_terms,number,effective_date,reason);preview=v['consolidation']
        id=c.execute('INSERT INTO ln_loans(borrower_id,company,initial_principal,start_date,created_date) VALUES(?,?,?,?,?)',(preview['borrower_id'],preview['company'],v['principal'],v['start_date'],v['issued_date'])).lastrowid
        contract_id=c.execute('INSERT INTO ln_contracts(loan_id,version,number,effective_date,payload,reason) VALUES(?,1,?,?,?,?)',(id,number,v['start_date'],dump(v),str(reason).strip())).lastrowid
        for row in preview['rows']:
            c.execute('INSERT INTO ln_transfers(source_id,target_id,effective_date,snapshot) VALUES(?,?,?,?)',(row['loan_id'],id,v['start_date'],dump(row)))
        _attach(c,id,contract_id,uploads)
        data=dict(v,version=1,attachments=[r['name'] for r in attachments(c,id,contract_id)])
        c.execute('INSERT INTO ln_notes(loan_id,contract_id,snapshot) VALUES(?,?,?)',(id,contract_id,dump(data)))
    return id


def transfer_sources(c,loan_id):
    return [dict(r,data=json.loads(r['snapshot'])) for r in rows(c,'SELECT * FROM ln_transfers WHERE target_id=? ORDER BY source_id',(loan_id,))]



def management_state(c,loan_id):
    v=loan(c,loan_id)
    linked=bool(c.execute('SELECT 1 FROM ln_transfers WHERE source_id=? OR target_id=?',(loan_id,loan_id)).fetchone())
    history=linked or bool(c.execute("SELECT 1 FROM ln_board_resolutions WHERE loan_id=? AND status='final'",(loan_id,)).fetchone()) or bool(c.execute('SELECT 1 FROM ln_scenario_links WHERE loan_id=?',(loan_id,)).fetchone()) or len(v['versions'])>1 or bool(v['receipts']) or bool(issued(c,loan_id)) or bool(status_events(c,loan_id))
    return dict(loan=v,draft=not history and not v['closed'],linked=linked)


def delete_draft(c,loan_id):
    with c:
        state=management_state(c,loan_id)
        if not state['draft']:raise ValueError('발행·회수·갱신 이력이 있는 차용증은 삭제할 수 없습니다. 취소 처리를 이용하세요.')
        require_active(c,loan_id)
        c.execute('DELETE FROM ln_attachments WHERE loan_id=?',(loan_id,))
        c.execute('DELETE FROM ln_contracts WHERE loan_id=?',(loan_id,))
        c.execute('DELETE FROM ln_loans WHERE id=?',(loan_id,))


def amend_loan(c,loan_id,terms,person,number,effective_date,reason,files=()):
    if not str(reason).strip():raise ValueError('변경 사유를 입력하세요.')
    return renew(c,loan_id,terms,number,effective_date,'변경 계약: '+str(reason).strip(),extend=False,person=person,files=files,issue_copy=True)


def status_events(c,loan_id):return rows(c,'SELECT * FROM ln_status_events WHERE loan_id=? ORDER BY effective_date,id',(loan_id,))


def cancel_loan(c,loan_id,effective_date,reason):
    effective=calc.day(effective_date).isoformat()
    if not str(reason).strip():raise ValueError('취소 사유를 입력하세요.')
    with c:
        require_active(c,loan_id);v=loan(c,loan_id)
        if c.execute('SELECT 1 FROM ln_transfers WHERE target_id=?',(loan_id,)).fetchone():raise ValueError('통합 갱신 계약은 연결된 원본을 보존해야 하므로 취소할 수 없습니다. 변경 계약을 이용하세요.')
        if not v['terms']['start_date']<=effective<=today().isoformat():raise ValueError('취소 적용일은 현재 계약 시작일 이후, 오늘 이내여야 합니다.')
        if any(r['receipt_date']>effective for r in v['receipts']):raise ValueError('취소일 이후 회수내역이 있습니다. 적용일을 확인하세요.')
        events=status_events(c,loan_id)
        if events and effective<events[-1]['effective_date']:raise ValueError('이전 상태 변경일보다 빠르게 취소할 수 없습니다.')
        c.execute('INSERT INTO ln_status_events(loan_id,event,effective_date,reason) VALUES(?,?,?,?)',(loan_id,'cancel',effective,str(reason).strip()))


def restore_loan(c,loan_id,reason):
    if not str(reason).strip():raise ValueError('취소 해제 사유를 입력하세요.')
    with c:
        v=loan(c,loan_id)
        if not v.get('cancellation') or v.get('transfer'):raise ValueError('취소된 차용증만 해제할 수 있습니다.')
        c.execute('INSERT INTO ln_status_events(loan_id,event,effective_date,reason) VALUES(?,?,?,?)',(loan_id,'restore',today().isoformat(),str(reason).strip()))



def scenario_fingerprint(v):
    value=dict(contract_id=v['contract_id'],terms=v['terms'],receipts=v['receipts'],closed=v['closed'],company=v['company'],borrower_id=v['borrower_id'])
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False).encode()).hexdigest()


def scenario_sources(c,loan_ids,as_of):
    result=[];as_of=calc.day(as_of).isoformat()
    if as_of>today().isoformat():raise ValueError('기준일은 오늘 이내로 입력하세요.')
    for id in loan_ids:
        require_active(c,id);v=loan(c,id);s=summary(c,v,as_of)
        if as_of<v['terms']['start_date']:raise ValueError('현재 계약 시작일 이후를 기준일로 선택하세요.')
        if any(r['receipt_date']>as_of for r in v['receipts']):raise ValueError('기준일 이후 실제 회수내역이 있습니다. 최신 기준일을 선택하세요.')
        result.append(dict(loan_id=id,contract_id=v['contract_id'],borrower_id=v['borrower_id'],name=v['borrower']['name'],company=v['company'],number=v['number'],start_date=v['start_date'],principal=s['balance'],carry_interest=s['unpaid_interest'],interest_credit=s['interest_credit'],rate=v['terms']['rate'],interest_kind=v['terms']['interest_kind'],fixed_interest=v['terms']['fixed_interest'],fingerprint=scenario_fingerprint(v)))
    return result


def confirm_scenario(c,result,memo=''):
    import loan_scenario as scenario
    sources=result['sources'];options=result['options']
    with c:
        fresh=scenario_sources(c,[s['loan_id'] for s in sources],options['as_of'])
        if len(fresh)!=len(sources) or any(a['fingerprint']!=b['fingerprint'] for a,b in zip(fresh,sources)):raise ValueError('계약·회수내역이 변경됐습니다. 최신 자료로 다시 계산한 후 확정하세요.')
        for a,b in zip(fresh,sources):
            for key in ['loan_id','contract_id','borrower_id','company','principal','carry_interest','interest_credit']:
                if a[key]!=b[key]:raise ValueError('상환계획의 기준 잔액을 확인하세요.')
        canonical=scenario.forecast(sources,options)
        actor=shared.RUN.get()['user']['username'] if shared.RUN.get() else ''
        id=c.execute('INSERT INTO ln_scenarios(borrower_id,company,as_of,payload,actor,memo) VALUES(?,?,?,?,?,?)',(sources[0]['borrower_id'],sources[0]['company'],options['as_of'],dump(canonical),actor,str(memo).strip())).lastrowid
        for s in sources:c.execute('INSERT INTO ln_scenario_links(scenario_id,loan_id,contract_id) VALUES(?,?,?)',(id,s['loan_id'],s['contract_id']))
    return id


def confirmed_scenarios(c,loan_id):
    return [dict(r,data=json.loads(r['payload'])) for r in rows(c,'SELECT s.* FROM ln_scenarios s JOIN ln_scenario_links l ON l.scenario_id=s.id WHERE l.loan_id=? ORDER BY s.id DESC',(loan_id,))]



def board_resolutions(c):
    return [dict(r,data=json.loads(r['payload'])) for r in rows(c,'SELECT * FROM ln_board_resolutions ORDER BY id DESC')]


def board_source_digest(data):
    return hashlib.sha256(json.dumps(data,sort_keys=True,ensure_ascii=False).encode()).hexdigest()


def save_board_resolution(c,data,final=False,doc_root=None):
    import board_resolution as board
    import uuid
    v=board.validate(data,final)
    linked=v.get('loan_id');contract=v.get('contract_id')
    with c:
        if linked:
            source=loan(c,linked);version=next((x for x in source['versions'] if x['id']==contract),None)
            if not version or version['data'].get('company')!=v['company']:raise ValueError('연결 차용증과 지급회사를 확인하세요.')
            if final and board_source_digest(version['data'])!=v.get('source_digest'):raise ValueError('연결 차용증이 변경됐습니다. 최신 차용증을 다시 불러와 본문을 확인하세요.')
        existing=rows(c,'SELECT * FROM ln_board_resolutions WHERE doc_root=? ORDER BY version DESC LIMIT 1',(doc_root,)) if doc_root else []
        if doc_root and not existing:raise ValueError('원본 결의서를 찾을 수 없습니다.')
        if existing:version=existing[0]['version']+1;number=existing[0]['number']
        else:
            doc_root=uuid.uuid4().hex;version=1;prefix='BR-'+v['meeting_date'].replace('-','')+'-'
            numbers=[r['number'] for r in rows(c,'SELECT DISTINCT number FROM ln_board_resolutions WHERE number LIKE ?',(prefix+'%',))]
            seq=max([int(x.rsplit('-',1)[1]) for x in numbers]+[0])+1;number=prefix+f'{seq:03}'
        v.update(number=number,version=version)
        ctx=shared.RUN.get();actor=ctx['user']['username'] if ctx else ''
        return c.execute('INSERT INTO ln_board_resolutions(doc_root,version,number,company,status,payload,loan_id,contract_id,actor) VALUES(?,?,?,?,?,?,?,?,?)',(doc_root,version,number,v['company'],v['status'],dump(v),linked,contract,actor)).lastrowid
