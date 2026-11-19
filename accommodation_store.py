"""Private accommodation contracts, monthly payments and deposit returns."""
from datetime import date, datetime, timedelta, timezone
import base64, calendar, hashlib, json
import collaboration as shared

FIELDS=['site','name','kind','site_zip','site_address','site_detail','zip','address','detail','tenant','tenant_phone','manager','manager_phone','landlord','landlord_phone','start','end','deposit','rent','maintenance','pay_day','alert_days','note','terminated','registration_status','registration_date','registration_amount','registration_number']

def today():return datetime.now(timezone(timedelta(hours=9))).date()
def rows(c,sql,args=()):
    q=c.execute(sql,args);return [dict(zip([v[0] for v in q.description],r)) for r in q]
def connect():
    shared.DATA.mkdir(parents=True,exist_ok=True)
    c=shared.connect(shared.DATA/'accommodations.db')
    c.executescript('''
    CREATE TABLE IF NOT EXISTS ac_contracts(id INTEGER PRIMARY KEY,payload TEXT NOT NULL,version INTEGER NOT NULL);
    CREATE TABLE IF NOT EXISTS ac_versions(id INTEGER PRIMARY KEY,contract_id INTEGER NOT NULL REFERENCES ac_contracts(id),version INTEGER NOT NULL,payload TEXT NOT NULL,created_at TEXT DEFAULT CURRENT_TIMESTAMP,UNIQUE(contract_id,version));
    CREATE TABLE IF NOT EXISTS ac_files(id INTEGER PRIMARY KEY,contract_id INTEGER NOT NULL REFERENCES ac_contracts(id),name TEXT NOT NULL,mime TEXT NOT NULL,content TEXT NOT NULL,digest TEXT NOT NULL,removed INTEGER NOT NULL DEFAULT 0);
    CREATE TABLE IF NOT EXISTS ac_payments(id INTEGER PRIMARY KEY,contract_id INTEGER NOT NULL REFERENCES ac_contracts(id),period TEXT NOT NULL,paid_date TEXT NOT NULL,rent INTEGER NOT NULL,maintenance INTEGER NOT NULL,note TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS ac_returns(id INTEGER PRIMARY KEY,contract_id INTEGER NOT NULL REFERENCES ac_contracts(id),paid_date TEXT NOT NULL,amount INTEGER NOT NULL,note TEXT NOT NULL);
    ''')
    return shared.protect(c)
REGISTRATION_DEFAULTS=dict(registration_status='미설정',registration_date='',registration_amount=0,registration_number='')
def contracts(c):return [dict({**REGISTRATION_DEFAULTS,**json.loads(r['payload'])},id=r['id'],version=r['version']) for r in rows(c,'SELECT * FROM ac_contracts ORDER BY id DESC')]
def contract(c,id):
    v=next((v for v in contracts(c) if v['id']==id),None)
    if v is None:raise ValueError('계약을 찾을 수 없습니다.')
    return v
def clean(v):
    x={k:str(v.get(k,'')).strip() for k in FIELDS}
    for key,label in [('site','현장명'),('name','숙소명'),('tenant','임차인'),('tenant_phone','임차인 연락처'),('landlord','임대인'),('landlord_phone','임대인 연락처'),('site_address','현장 주소'),('address','숙소 주소')]:
        if not x[key]:raise ValueError(label+'을 입력하세요.')
    for key in ['start','end']:x[key]=str(date.fromisoformat(x[key]))
    if x['start']>x['end']:raise ValueError('계약 종료일은 시작일 이후로 지정하세요.')
    for key in ['deposit','rent','maintenance','pay_day','alert_days']:
        try:x[key]=int(v.get(key,0))
        except (ValueError,TypeError):raise ValueError('금액·납부일·알림일을 확인하세요.')
        if x[key]<0:raise ValueError('금액은 음수일 수 없습니다.')
    if not 1<=x['pay_day']<=31 or not 1<=x['alert_days']<=365:raise ValueError('납부일 또는 만기 알림일을 확인하세요.')
    if x['kind'] not in ['전세','월세']:raise ValueError('계약구분을 선택하세요.')
    if x['kind']=='전세' and x['rent']:raise ValueError('전세 계약의 월 임차료는 0원으로 입력하세요.')
    x['terminated']=str(v.get('terminated','')).strip()
    if x['terminated']:
        date.fromisoformat(x['terminated'])
        if not x['start']<=x['terminated']<=x['end']:raise ValueError('종료일은 계약기간 내로 지정하세요.')
    status=str(v.get('registration_status','미설정')).strip()
    if status not in ['미설정','설정 완료']:raise ValueError('전세권 설정 여부를 확인하세요.')
    x.update(REGISTRATION_DEFAULTS);x['registration_status']=status
    if status=='설정 완료':
        raw_date=str(v.get('registration_date','')).strip()
        try:x['registration_date']=str(date.fromisoformat(raw_date))
        except ValueError:raise ValueError('전세권 설정일을 입력하세요.')
        try:
            raw_amount=v.get('registration_amount',0);amount=int(raw_amount)
            if amount<=0 or str(raw_amount).strip() not in [str(amount),str(float(amount))]:raise ValueError()
        except (ValueError,TypeError,OverflowError):raise ValueError('전세권 설정금액은 0원보다 큰 정수로 입력하세요.')
        x['registration_amount']=amount;x['registration_number']=str(v.get('registration_number','')).strip()
        if not x['registration_number']:raise ValueError('등기 접수번호를 입력하세요.')
    return x

def prepare_files(files):
    out=[]
    if len(files or [])>20:raise ValueError('첨부파일은 한 번에 20개까지 등록하세요.')
    for f in files or []:
        name=str(f['name']).replace('\\','/').rsplit('/',1)[-1];data=f['content'];suffix=name.lower().rsplit('.',1)[-1]
        if suffix not in ['pdf','jpg','jpeg','png'] or not isinstance(data,bytes) or not data or len(data)>20*1024*1024:raise ValueError('계약서는 PDF/JPG/PNG, 파일당 20MB 이하로 등록하세요.')
        mime={'pdf':'application/pdf','jpg':'image/jpeg','jpeg':'image/jpeg','png':'image/png'}[suffix]
        if not (data.startswith(b'%PDF-') if suffix=='pdf' else data.startswith(b'\x89PNG\r\n\x1a\n') if suffix=='png' else data.startswith(b'\xff\xd8\xff')):raise ValueError('첨부파일 형식과 내용을 확인하세요.')
        out.append((name,mime,base64.b64encode(data).decode(),hashlib.sha256(data).hexdigest()))
    return out

def save(c,v,id=None,expected=None,files=None,remove=None):
    x=clean(v);uploads=prepare_files(files)
    with c:
        old=contract(c,id) if id else None
        if old and expected!=old['version']:raise ValueError('계약이 변경되었습니다. 다시 불러오세요.')
        if old:
            paid=c.execute('SELECT COALESCE(SUM(amount),0) FROM ac_returns WHERE contract_id=?',(id,)).fetchone()[0]
            if x['deposit']<paid:raise ValueError('보증금을 이미 반환받은 금액보다 줄일 수 없습니다.')
            if (old['start']!=x['start'] or old['end']!=x['end'] or old['terminated']!=x['terminated']):
                invalid=[p for p in payments(c,id) if p['period'] not in periods(x)]
                if invalid:raise ValueError('납부 이력이 있는 월을 계약기간에서 제외할 수 없습니다.')
            for period in periods(x):
                existing=[p for p in payments(c,id) if p['period']==period]
                if sum(p['rent'] for p in existing)>x['rent'] or sum(p['maintenance'] for p in existing)>x['maintenance']:raise ValueError('월 약정액은 기존 지급액보다 줄일 수 없습니다.')
            version=old['version']+1
            c.execute('UPDATE ac_contracts SET payload=?,version=? WHERE id=?',(json.dumps(x,ensure_ascii=False),version,id))
        else:
            version=1;id=c.execute('INSERT INTO ac_contracts(payload,version) VALUES(?,?)',(json.dumps(x,ensure_ascii=False),version)).lastrowid
        c.execute('INSERT INTO ac_versions(contract_id,version,payload) VALUES(?,?,?)',(id,version,json.dumps(x,ensure_ascii=False)))
        for fid in remove or []:c.execute('UPDATE ac_files SET removed=1 WHERE id=? AND contract_id=?',(fid,id))
        for f in uploads:c.execute('INSERT INTO ac_files(contract_id,name,mime,content,digest) VALUES(?,?,?,?,?)',(id,)+f)
    return id

def files(c,id):return rows(c,'SELECT id,name,mime,digest FROM ac_files WHERE contract_id=? AND removed=0 ORDER BY id',(id,))
def file_bytes(c,id,fid):
    r=rows(c,'SELECT * FROM ac_files WHERE id=? AND contract_id=? AND removed=0',(fid,id))
    if not r:raise ValueError('첨부파일을 찾을 수 없습니다.')
    data=base64.b64decode(r[0]['content'])
    if hashlib.sha256(data).hexdigest()!=r[0]['digest']:raise ValueError('첨부파일 무결성을 확인하세요.')
    return r[0],data

def periods(v):
    start=date.fromisoformat(v['start']).replace(day=1);end=date.fromisoformat(v.get('terminated') or v['end']);out=[]
    while start<=end:
        due=start.replace(day=min(v['pay_day'],calendar.monthrange(start.year,start.month)[1]))
        due=max(due,date.fromisoformat(v['start']));due=min(due,end)
        out.append((str(start)[:7],str(due)))
        start=date(start.year+start.month//12,start.month%12+1,1)
    return dict(out)
def payments(c,id):return rows(c,'SELECT * FROM ac_payments WHERE contract_id=? ORDER BY paid_date,id',(id,))
def add_payment(c,id,period,paid_date,rent,maintenance,note=''):
    v=contract(c,id)
    if period not in periods(v):raise ValueError('계약기간 내 귀속월을 선택하세요.')
    date.fromisoformat(str(paid_date));rent=int(rent);maintenance=int(maintenance)
    if min(rent,maintenance)<0 or rent+maintenance<=0:raise ValueError('지급액을 확인하세요.')
    existing=[p for p in payments(c,id) if p['period']==period]
    if sum(p['rent'] for p in existing)+rent>v['rent'] or sum(p['maintenance'] for p in existing)+maintenance>v['maintenance']:raise ValueError('해당 월의 약정액을 초과합니다. 계약금액 또는 기존 지급 내역을 확인하세요.')
    with c:c.execute('INSERT INTO ac_payments(contract_id,period,paid_date,rent,maintenance,note) VALUES(?,?,?,?,?,?)',(id,period,str(paid_date),rent,maintenance,note))
def returns(c,id):return rows(c,'SELECT * FROM ac_returns WHERE contract_id=? ORDER BY paid_date,id',(id,))
def returned(c,id,as_of=None):return sum(r['amount'] for r in returns(c,id) if r['paid_date']<=str(as_of or today()))
def add_return(c,id,paid_date,amount,note=''):
    v=contract(c,id);date.fromisoformat(str(paid_date));amount=int(amount)
    if amount<=0 or amount+sum(r['amount'] for r in returns(c,id))>v['deposit']:raise ValueError('반환액은 보증금 잔액 이내로 입력하세요.')
    with c:c.execute('INSERT INTO ac_returns(contract_id,paid_date,amount,note) VALUES(?,?,?,?)',(id,str(paid_date),amount,note))
def remove_entry(c,table,id,cid):
    if table not in ['ac_payments','ac_returns']:raise ValueError('지원하지 않는 내역입니다.')
    with c:c.execute('DELETE FROM '+table+' WHERE id=? AND contract_id=?',(id,cid))
def state(v,as_of=None):
    d=str(as_of or today())
    return '예정' if d<v['start'] else '종료' if d>(v.get('terminated') or v['end']) else '사용 중'
def monthly(c,v,as_of=None):
    d=str(as_of or today());p=payments(c,v['id']);out=[]
    for period,due in periods(v).items():
        paid=[x for x in p if x['period']==period and x['paid_date']<=d]
        r=sum(x['rent'] for x in paid);m=sum(x['maintenance'] for x in paid)
        out.append(dict(귀속월=period,납부예정일=due,약정임차료=v['rent'],약정관리비=v['maintenance'],지급임차료=r,지급관리비=m,미지급액=max(0,v['rent']-r)+max(0,v['maintenance']-m),상태='납부 완료' if r>=v['rent'] and m>=v['maintenance'] else '미납' if due<d else '납부 예정'))
    return out

def alerts(c,as_of=None):
    day=as_of or today();out=[]
    for v in contracts(c):
        end=date.fromisoformat(v.get('terminated') or v['end']);days=(end-day).days;balance=v['deposit']-returned(c,v['id'],day)
        if state(v,day)!='종료' and 0<=days<=v['alert_days']:out.append((v,f'계약 만기 D-{days} · 연장 여부 확인'))
        elif days<0 and balance>0:out.append((v,f'계약 종료 · 미반환 보증금 {balance:,}원'))
    return out
