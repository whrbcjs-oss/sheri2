"""Private annual resident tax ledger, review snapshots and filing/payment evidence."""
import json,base64,hashlib,re
from contextlib import nullcontext
from datetime import date
import collaboration as shared
import resident_tax_calc as calc
from accommodation_store import today,rows,prepare_files

def dump(x):return json.dumps(x,ensure_ascii=False,allow_nan=False)
def connect():
    shared.DATA.mkdir(parents=True,exist_ok=True);c=shared.connect(shared.DATA/'resident_tax.db')
    c.executescript('''
    CREATE TABLE IF NOT EXISTS rt_sites(id INTEGER PRIMARY KEY,year INTEGER NOT NULL,company TEXT NOT NULL,name TEXT NOT NULL,payload TEXT NOT NULL,version INTEGER NOT NULL,UNIQUE(year,company,name));
    CREATE TABLE IF NOT EXISTS rt_buildings(id INTEGER PRIMARY KEY,site_id INTEGER NOT NULL REFERENCES rt_sites(id),name TEXT NOT NULL,payload TEXT NOT NULL,digest TEXT NOT NULL,UNIQUE(site_id,name),UNIQUE(site_id,digest));
    CREATE TABLE IF NOT EXISTS rt_sources(id INTEGER PRIMARY KEY,site_id INTEGER NOT NULL REFERENCES rt_sites(id),name TEXT NOT NULL,content TEXT NOT NULL,digest TEXT NOT NULL,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS rt_filings(id INTEGER PRIMARY KEY,kind TEXT NOT NULL,year INTEGER NOT NULL,company TEXT NOT NULL,region TEXT NOT NULL,unit TEXT NOT NULL,payload TEXT NOT NULL,filed_date TEXT NOT NULL DEFAULT '',receipt TEXT NOT NULL DEFAULT '',version INTEGER NOT NULL DEFAULT 1,UNIQUE(kind,year,company,region,unit));
    CREATE TABLE IF NOT EXISTS rt_payments(id INTEGER PRIMARY KEY,filing_id INTEGER NOT NULL REFERENCES rt_filings(id),paid_date TEXT NOT NULL,amount INTEGER NOT NULL,note TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS rt_evidence(id INTEGER PRIMARY KEY,filing_id INTEGER NOT NULL REFERENCES rt_filings(id),name TEXT NOT NULL,mime TEXT NOT NULL,content TEXT NOT NULL,digest TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS rt_corporate(id INTEGER PRIMARY KEY,year INTEGER NOT NULL,company TEXT NOT NULL,payload TEXT NOT NULL,version INTEGER NOT NULL,UNIQUE(year,company));
    ''');return shared.protect(c)
def sites(c,year=None,include_deleted=False):
    values=[dict(json.loads(r['payload']),id=r['id'],year=r['year'],company=r['company'],name=r['name'],version=r['version']) for r in rows(c,'SELECT * FROM rt_sites'+(' WHERE year=?' if year is not None else '')+' ORDER BY company,name',(year,) if year is not None else ())]
    return [v for v in values if include_deleted or not v.get('deleted')]
def site(c,id,include_deleted=False):
    v=next((v for v in sites(c,include_deleted=include_deleted) if v['id']==id),None)
    if v is None:raise ValueError('사업장을 확인하세요.')
    return v

def buildings(c,id):return [dict(json.loads(r['payload']),id=r['id'],name=r['name'],digest=r['digest']) for r in rows(c,'SELECT * FROM rt_buildings WHERE site_id=? ORDER BY id',(id,))]
def filings(c,year=None,kind=None):
    out=[dict(r,data=json.loads(r['payload'])) for r in rows(c,'SELECT * FROM rt_filings ORDER BY year DESC,company,region,unit')]
    return [r for r in out if (year is None or r['year']==year) and (kind is None or r['kind']==kind)]
def filing(c,id):
    v=next((r for r in filings(c) if r['id']==id),None)
    if not v:raise ValueError('신고 자료를 확인하세요.')
    return v
def site_locks(c,id):
    s=site(c,id,include_deleted=True)
    return [f for f in filings(c) if id in f['data'].get('site_ids',[]) or (f['kind']=='corporate' and f['year']==s['year'] and f['company']==s['company'])]
def unlocked(c,id):
    if site_locks(c,id):raise ValueError('검토 확정된 신고에 포함된 사업장입니다. 신고·납부 메뉴에서 확정 해제 후 수정·삭제하세요.')

def clean_site(v):
    x=dict(v);x.pop('id',None);x.pop('version',None)
    x['year']=int(v['year'])
    if not 2000<=x['year']<=2100:raise ValueError('신고연도를 확인하세요.')
    for k in ['company','name','address','region']:
        x[k]=str(v.get(k,'')).strip()
        if not x[k]:raise ValueError({'company':'법인명','name':'사업장명','address':'사업장 주소','region':'관할 지자체'}[k]+'을 입력하세요.')
    if x.get('kind') not in calc.KINDS:raise ValueError('사업장 구분을 확인하세요.')
    x['unit']=str(v.get('unit','')).strip() or x['name']
    for k,d in [('capital',0),('base',50000),('rate',250),('education',10),('reduce_base',0),('reduce_area',0),('reduce_education',0)]:x[k]=float(calc.nonnegative(v.get(k,d)))
    if x['education']>100:raise ValueError('지방교육세율을 확인하세요.')
    x['deadline']=str(v.get('deadline',f"{x['year']}-08-31"));date.fromisoformat(x['deadline'])
    x['confirmed']=bool(v.get('confirmed',False));x['floor_area']=bool(v.get('floor_area',True))
    if x['confirmed'] and any('확인 필요' in x[k] for k in ['address','region']):raise ValueError('사업장 주소와 관할 지자체를 실제 값으로 입력하세요.')
    if x['confirmed'] and not str(x.get('rule_note','')).strip():raise ValueError('관할·세율 확인 근거를 입력하세요.')
    return x

def _save_site(c,x,id=None,expected=None,restoring=False):
    old=site(c,id,include_deleted=True) if id else None
    if old:
        unlocked(c,id)
        if old.get('deleted') and not restoring:raise ValueError('삭제된 사업장입니다. 삭제 목록에서 복구하세요.')
        if old['version']!=expected:raise ValueError('사업장 정보가 변경되었습니다. 다시 불러오세요.')
        if old['year']!=x['year']:raise ValueError('등록 후 연도는 변경할 수 없습니다. 연도 이월을 이용하세요.')
    if c.execute("SELECT 1 FROM rt_filings WHERE kind='corporate' AND year=? AND company=?",(x['year'],x['company'])).fetchone():raise ValueError('법인지방소득세 안분 확정된 법인입니다. 확정 해제 후 사업장을 변경하세요.')
    dup=c.execute('SELECT id FROM rt_sites WHERE year=? AND company=? AND name=? AND id<>?',(x['year'],x['company'],x['name'],id or -1)).fetchone()
    if dup:raise ValueError('같은 연도·법인의 사업장이 이미 등록되어 있습니다. 삭제 목록에 있으면 복구하세요.')
    # A return's identity must not be silently expanded after confirmation.
    if c.execute("SELECT 1 FROM rt_filings WHERE kind='business' AND year=? AND company=? AND region=? AND unit=?",(x['year'],x['company'],x['region'],x['unit'])).fetchone():raise ValueError('이미 확정된 신고 단위입니다. 확정 해제 후 사업장을 추가하세요.')
    if old:c.execute('UPDATE rt_sites SET company=?,name=?,payload=?,version=version+1 WHERE id=?',(x['company'],x['name'],dump(x),id))
    else:id=c.execute('INSERT INTO rt_sites(year,company,name,payload,version) VALUES(?,?,?,?,1)',(x['year'],x['company'],x['name'],dump(x))).lastrowid
    return id

def save_site(c,v,id=None,expected=None):
    x=clean_site(v)
    with c:return _save_site(c,x,id,expected)

def delete_site(c,id,expected,reason):
    with c:
        old=site(c,id);unlocked(c,id)
        if old['version']!=expected:raise ValueError('사업장 정보가 변경되었습니다. 다시 불러오세요.')
        if not str(reason).strip():raise ValueError('삭제 사유를 입력하세요.')
        x={k:v for k,v in old.items() if k not in ['id','version']}
        x.update(deleted=True,delete_reason=str(reason).strip(),deleted_at=str(today()))
        c.execute('UPDATE rt_sites SET payload=?,version=version+1 WHERE id=?',(dump(x),id))
def restore_site(c,id,expected):
    with c:
        old=site(c,id,include_deleted=True)
        if not old.get('deleted'):raise ValueError('삭제된 사업장이 아닙니다.')
        x={k:v for k,v in old.items() if k not in ['id','version','deleted','delete_reason','deleted_at']}
        return _save_site(c,clean_site(x),id,expected,restoring=True)

def save_building(c,id,name,v,source=None,bid=None,managed=True):
    s=site(c,id);unlocked(c,id);name=str(name).strip();x=dict(v)
    if not name:raise ValueError('건물명·관리번호를 입력하세요.')
    if bid is None and any(b.get('legacy') for b in buildings(c,id)):raise ValueError('기존 집계 명세를 먼저 선택해 실제 건물 명세로 대체하거나 삭제하세요. 중복 면적 합산을 방지합니다.')
    if x.get('presence') not in ['미확인','존치 확인','미존치']:raise ValueError('7월 1일 존치 여부를 확인하세요.')
    for key in ['start','permit_end','demolished']:
        x[key]=str(x.get(key,'')).strip()
        if x[key]:date.fromisoformat(x[key])
    if x.get('start') and x.get('demolished') and x['start']>x['demolished']:raise ValueError('철거일은 축조·사용시작일 이후여야 합니다.')
    totals=calc.area(x.get('rows',[]))
    if not x.get('rows') or totals['total']==0:raise ValueError('건물 사용면적을 입력하세요.')
    x['reported']=float(calc.nonnegative(x.get('reported',totals['total'])))
    if x.get('reviewed'):
        if abs(calc.dec(x['reported'])-calc.dec(totals['total']))>calc.dec('.005') and not str(x.get('difference_reason','')).strip():raise ValueError('면적 차이 확인 사유를 입력하세요.')
        if any(calc.dec(r['taxable'])<calc.dec(r['area']) and not str(r.get('reason','')).strip() for r in x['rows']):raise ValueError('제외면적이 있는 행마다 제외 근거를 입력하세요.')
    digest=hashlib.sha256(source['content']).hexdigest() if source else hashlib.sha256(dump(dict(name=name,rows=x['rows'])).encode()).hexdigest()
    duplicate=c.execute('SELECT id FROM rt_buildings WHERE site_id=? AND (name=? OR digest=?) AND id<>?',(id,name,digest,bid or -1)).fetchone()
    if duplicate:raise ValueError('같은 건물명 또는 같은 파일이 등록되어 있습니다. 기존 건물을 선택해 수정하세요.')
    if bid and not c.execute('SELECT 1 FROM rt_buildings WHERE id=? AND site_id=?',(bid,id)).fetchone():raise ValueError('건물을 확인하세요.')
    with (c if managed else nullcontext()):
        if bid:c.execute('UPDATE rt_buildings SET name=?,payload=?,digest=? WHERE id=? AND site_id=?',(name,dump(x),digest,bid,id))
        else:bid=c.execute('INSERT INTO rt_buildings(site_id,name,payload,digest) VALUES(?,?,?,?)',(id,name,dump(x),digest)).lastrowid
        if source:
            if len(source['content'])>20*1024*1024:raise ValueError('파일 용량을 확인하세요.')
            c.execute('INSERT INTO rt_sources(site_id,name,content,digest) VALUES(?,?,?,?)',(id,source['name'],base64.b64encode(source['content']).decode(),digest))
    return bid

def remove_building(c,id,bid):
    unlocked(c,id)
    with c:c.execute('DELETE FROM rt_buildings WHERE site_id=? AND id=?',(id,bid))

def inspect_site(c,s):
    bs=buildings(c,s['id']);total=taxable=calc.dec(0);issues=[]
    if not bs:issues.append('건물 명세 미등록')
    if not s.get('confirmed'):issues.append('관할·세율 미확인')
    if s.get('legacy') and not s.get('legacy_checked'):issues.append('기존 집계 대조 필요')
    for b in bs:
        present=calc.present(b,s['year'])
        if present is None:issues.append(b['name']+' 존치 미확인')
        if present is False:continue
        a=calc.area(b['rows']);total+=calc.dec(a['total']);taxable+=calc.dec(a['taxable'])
        if not b.get('reviewed'):issues.append(b['name']+' 면적 미확인')
        if abs(calc.dec(b['reported'])-calc.dec(a['total']))>calc.dec('.005') and not b.get('difference_reason'):issues.append(b['name']+' 신고면적 차이')
    return dict(site=s,total=float(total),taxable=float(taxable),excluded=float(total-taxable),issues=issues,target=not bs or any(calc.present(b,s['year']) is not False for b in bs))

def business_groups(c,year):
    groups={}
    for s in sites(c,year):
        key=(s['company'],s['region'],s['unit']);groups.setdefault(key,[]).append(inspect_site(c,s))
    out=[]
    for (company,region,unit),members in groups.items():
        config=members[0]['site'];issues=[f"{m['site']['name']}: {x}" for m in members for x in m['issues']]
        fields=['base','rate','education','reduce_base','reduce_area','reduce_education','floor_area','deadline']
        if any(any(m['site'].get(k)!=config.get(k) for k in fields) for m in members):issues.append('같은 신고 단위의 세율·감면·기한 설정 불일치')
        a=sum((calc.dec(m['taxable']) for m in members),calc.dec(0))
        target=any(m['target'] for m in members)
        try:t=calc.tax(a,*[config.get(k,0) if target else 0 for k in ['base','rate','education','reduce_base','reduce_area','reduce_education']],floor_area=config.get('floor_area',True))
        except ValueError as e:t=dict(base=0,area_tax=0,education_tax=0,total=0);issues.append(str(e))
        out.append(dict(year=year,company=company,region=region,unit=unit,target=target,site_ids=[m['site']['id'] for m in members],members=members,total_area=sum(m['total'] for m in members),taxable=float(a),excluded=sum(m['excluded'] for m in members),issues=issues,deadline=config['deadline'],**t))
    return out

def confirm_business(c,group):
    current=next((g for g in business_groups(c,group['year']) if (g['company'],g['region'],g['unit'])==(group['company'],group['region'],group['unit'])),None)
    if not current or current['issues']:raise ValueError('미확인 항목을 모두 검토하세요.')
    with c:
        if c.execute("SELECT 1 FROM rt_filings WHERE kind='business' AND year=? AND company=? AND region=? AND unit=?",(current['year'],current['company'],current['region'],current['unit'])).fetchone():raise ValueError('이미 확정된 신고입니다.')
        return c.execute("INSERT INTO rt_filings(kind,year,company,region,unit,payload) VALUES('business',?,?,?,?,?)",(current['year'],current['company'],current['region'],current['unit'],dump(current))).lastrowid

def payments(c,id):return rows(c,'SELECT * FROM rt_payments WHERE filing_id=? ORDER BY paid_date,id',(id,))
def balance(c,id):return filing(c,id)['data']['total']-sum(r['amount'] for r in payments(c,id))
def record_filing(c,id,day,receipt,files=None,expected=None):
    f=filing(c,id);date.fromisoformat(str(day))
    if expected!=f['version']:raise ValueError('신고 기록이 변경되었습니다. 다시 불러오세요.')
    if not str(receipt).strip():raise ValueError('신고 접수번호를 입력하세요.')
    prepared=prepare_files(files)
    with c:
        c.execute('UPDATE rt_filings SET filed_date=?,receipt=?,version=version+1 WHERE id=?',(str(day),receipt,id))
        for p in prepared:c.execute('INSERT INTO rt_evidence(filing_id,name,mime,content,digest) VALUES(?,?,?,?,?)',(id,)+p)
def pay(c,id,day,amount,note='',files=None):
    f=filing(c,id);date.fromisoformat(str(day));a=int(calc.nonnegative(amount))
    if not f['filed_date']:raise ValueError('신고 완료를 기록한 뒤 납부를 입력하세요.')
    if str(day)<f['filed_date']:raise ValueError('납부일은 신고일 이후로 입력하세요.')
    if a<=0 or a>balance(c,id):raise ValueError('납부액은 미납잔액 이내로 입력하세요.')
    prepared=prepare_files(files)
    with c:
        c.execute('INSERT INTO rt_payments(filing_id,paid_date,amount,note) VALUES(?,?,?,?)',(id,str(day),a,note))
        for p in prepared:c.execute('INSERT INTO rt_evidence(filing_id,name,mime,content,digest) VALUES(?,?,?,?,?)',(id,)+p)
def undo_payment(c,id,pid):
    filing(c,id)
    with c:c.execute('DELETE FROM rt_payments WHERE id=? AND filing_id=?',(pid,id))
def release(c,id,reason):
    f=filing(c,id)
    targets=[x for x in filings(c,f['year'],'corporate') if x['company']==f['company']] if f['kind']=='corporate' else [f]
    if any(x['filed_date'] or payments(c,x['id']) for x in targets):raise ValueError('신고·납부 기록이 있는 자료는 확정 해제할 수 없습니다.')
    if not str(reason).strip():raise ValueError('확정 해제 사유를 입력하세요.')
    with c:
        for x in targets:
            c.execute('UPDATE rt_filings SET receipt=? WHERE id=?',('확정 해제: '+reason,x['id']))
            c.execute('DELETE FROM rt_filings WHERE id=?',(x['id'],))

def evidence(c,id):return rows(c,'SELECT id,name,mime,digest FROM rt_evidence WHERE filing_id=? ORDER BY id',(id,))
def evidence_bytes(c,id,fid):
    r=rows(c,'SELECT * FROM rt_evidence WHERE filing_id=? AND id=?',(id,fid))
    if not r:raise ValueError('첨부자료를 찾을 수 없습니다.')
    b=base64.b64decode(r[0]['content'])
    if hashlib.sha256(b).hexdigest()!=r[0]['digest']:raise ValueError('첨부자료 무결성을 확인하세요.')
    return b

def import_aggregate(c,parsed,source,region_overrides=None):
    year=parsed['year']
    if not year:raise ValueError('집계표의 신고연도를 확인하세요.')
    planned=[]
    for r in parsed['sites']:
        x=dict(r,year=year,name=r['site'],kind='기타',unit=r['site'],region=(region_overrides or {}).get(str(r['source_row'])) or calc.jurisdiction(r['address']) or '관할 확인 필요',confirmed=False,legacy=True,legacy_checked=False,deadline=f'{year}-08-31')
        if not x['address']:x['address']='주소 확인 필요'
        planned.append(clean_site(x))
    with c:
        ids=[]
        for x in planned:
            id=_save_site(c,x);ids.append(id)
            building=dict(rows=[dict(floor='',room='',entered='',area=x['reported'],purpose='기존 집계 이관',taxable=x['taxable'],reason='기존 집계표 차감면적 · 근거 재확인')],reported=x['reported'],presence='미확인',reviewed=False,start='',permit_end='',demolished='',legacy=True)
            if x['reported']>0:save_building(c,id,'기존 집계 명세',building,managed=False)
            c.execute('INSERT INTO rt_sources(site_id,name,content,digest) VALUES(?,?,?,?)',(id,source['name'],base64.b64encode(source['content']).decode(),hashlib.sha256(source['content']).hexdigest()))
    return ids

def carry(c,source_year,target_year):
    if source_year==target_year:raise ValueError('서로 다른 연도를 선택하세요.')
    originals=sites(c,source_year)
    if not originals:raise ValueError('이월할 사업장이 없습니다.')
    with c:
        ids=[]
        for s in originals:
            if c.execute('SELECT 1 FROM rt_sites WHERE year=? AND company=? AND name=?',(target_year,s['company'],s['name'])).fetchone():continue
            x=dict(s,year=target_year,confirmed=False,legacy_checked=False,deadline=f'{target_year}-08-31');id=_save_site(c,clean_site(x));ids.append(id)
            for b in buildings(c,s['id']):
                v=dict(b,reviewed=False,presence='미확인');v.pop('id',None);v.pop('digest',None)
                save_building(c,id,b['name'],v,managed=False)
    return ids

def corporate(c,year,company):
    r=rows(c,'SELECT * FROM rt_corporate WHERE year=? AND company=?',(year,company))
    return dict(json.loads(r[0]['payload']),version=r[0]['version']) if r else None

def save_corporate(c,year,company,v,expected=None):
    if any(f['company']==company for f in filings(c,year,'corporate')):raise ValueError('확정된 법인지방소득세 자료입니다. 확정 해제 후 수정하세요.')
    date.fromisoformat(v['fiscal_end']);date.fromisoformat(v['deadline'])
    if int(v['fiscal_end'][:4])!=year:raise ValueError('귀속연도와 사업연도 종료일을 확인하세요.')
    if v['deadline']<=v['fiscal_end']:raise ValueError('신고기한은 사업연도 종료일 이후로 입력하세요.')
    actual={s['id']:s for s in sites(c,year) if s['company']==company};seen=set()
    for item in v['items']:
        id=int(item['site_id'])
        if id not in actual or id in seen:raise ValueError('사업장 선택·중복을 확인하세요.')
        seen.add(id);calc.nonnegative(item['employees']);calc.nonnegative(item['area'])
        item.update(company=company,name=actual[id]['name'],jurisdiction=actual[id]['region'],address=actual[id]['address'])
    if set(actual)!=seen:raise ValueError('모든 사업장의 연말 대상 여부를 표시하세요.')
    active=[i for i in v['items'] if i.get('include')]
    v=dict(v,allocation=calc.allocate(active,v['total']))
    if not v.get('reviewed') or not str(v.get('note','')).strip():raise ValueError('연말 인원·면적·세액과 특수 안분 여부를 검토하고 근거를 입력하세요.')
    with c:
        old=corporate(c,year,company)
        if old and old['version']!=expected:raise ValueError('안분자료가 변경되었습니다. 다시 불러오세요.')
        if old:c.execute('UPDATE rt_corporate SET payload=?,version=version+1 WHERE year=? AND company=?',(dump(v),year,company))
        else:c.execute('INSERT INTO rt_corporate(year,company,payload,version) VALUES(?,?,?,1)',(year,company,dump(v)))

def confirm_corporate(c,year,company):
    v=corporate(c,year,company)
    if not v:raise ValueError('검토한 안분자료를 먼저 저장하세요.')
    current={s['id']:s for s in sites(c,year) if s['company']==company}
    if set(current)!={int(x['site_id']) for x in v['items']} or any(current[int(x['site_id'])]['region']!=x['jurisdiction'] or current[int(x['site_id'])]['address']!=x['address'] or current[int(x['site_id'])]['name']!=x['name'] for x in v['items']):raise ValueError('저장 후 사업장 정보가 변경되었습니다. 안분자료를 다시 저장하세요.')
    if filings(c,year,'corporate') and any(f['company']==company for f in filings(c,year,'corporate')):raise ValueError('이미 확정된 안분자료입니다.')
    with c:
        for r in v['allocation']:
            data=dict(total=r['amount'],deadline=v['deadline'],fiscal_end=v['fiscal_end'],allocation=r,items=[x for x in v['items'] if x['jurisdiction']==r['jurisdiction']],site_ids=[x['site_id'] for x in v['items'] if x['jurisdiction']==r['jurisdiction']])
            c.execute("INSERT INTO rt_filings(kind,year,company,region,unit,payload) VALUES('corporate',?,?,?,?,?)",(year,company,r['jurisdiction'],'법인지방소득세',dump(data)))
