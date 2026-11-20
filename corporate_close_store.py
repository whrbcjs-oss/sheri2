"""Versioned corporate-close workbooks, adjustments, ledgers and reserve rollforwards."""
import base64,hashlib,json,re,uuid
from datetime import date
from pathlib import Path
import collaboration as shared
import corporate_close_calc as calc
import corporate_progress as progress

DEFAULT_COMPANIES=['㈜효성','다혜건설㈜','㈜효성전문','㈜한길','㈜효성엘비데크']
DEFAULT_EXEMPT_KEYWORDS=['환입','기부금시인액','보상비','고재매각','환수']
RECOMMENDED_EXEMPT_KEYWORDS=['공사원가환입','고용보험료환급','산재보험료환급','4대보험료환급','과오납환급','정산금환급','하자보수비환수','공사비환수','폐자재매각','고철매각','부산물매각','공사관련보상금','손해배상금','기부금시인','충당금환입','대손충당금환입','퇴직급여충당금환입']
DEFAULT_TAX_DUES_KEYWORDS=['법인세','법인지방소득세','가산세','가산금','과태료','벌금','과료','범칙금','체납처분비']
def dump(v):return json.dumps(v,ensure_ascii=False,allow_nan=False)
def rows(c,sql,args=()):
    cur=c.execute(sql,args);names=[d[0] for d in cur.description];return [dict(zip(names,r)) for r in cur]
def normalized(v):return ''.join(ch for ch in str(v or '').lower() if ch.isalnum())
def write_with_refresh(c,action):
    """Retry once after an unrelated database revision change.

    Row-level expected-version checks inside ``action`` still reject a real
    collision on the same record.  This only prevents unrelated edits from
    blocking a safe adjustment insert/update.
    """
    try:return action()
    except shared.StaleData:
        c.rollback();c.expected=shared.revision(c)
        return action()
def _seed_rules(c,company_id):
    for keyword in DEFAULT_EXEMPT_KEYWORDS:c.execute("INSERT OR IGNORE INTO cc_rules(company_id,kind,keyword,classification) VALUES(?, 'description', ?, '감면분')",(company_id,keyword))
    c.execute("INSERT OR IGNORE INTO cc_rules(company_id,kind,keyword,classification) VALUES(?, 'account', '잡손실', '감면분')",(company_id,))
def _seed_tax_dues_rules(c,company_id):
    for keyword in DEFAULT_TAX_DUES_KEYWORDS:c.execute("INSERT OR IGNORE INTO cc_statement_rules(company_id,statement,keyword) VALUES(?,'tax_dues',?)",(company_id,keyword))
def _seed_diagnostic_guideline(c):
    import corporate_close_capital as capital
    source=Path(__file__).resolve().parent/'docs'/'건설업체_기업진단지침_사용자제공본.txt';content=source.read_text(encoding='utf-8') if source.is_file() else ''
    c.execute('''INSERT OR IGNORE INTO cc_diagnostic_guidelines(name,source_status,effective_from,notification_no,source_note,content,active) VALUES(?,?,?,?,?,?,1)''',(capital.GUIDELINE_NAME,capital.GUIDELINE_STATUS,'','', '사용자가 2026-11-18 제공한 텍스트. 공식 시행일과 고시번호 확인 전까지 출처상태를 함께 표시합니다.',content))
    gid=c.execute('SELECT id FROM cc_diagnostic_guidelines WHERE name=?',(capital.GUIDELINE_NAME,)).fetchone()[0]
    for rule in capital.GUIDELINE_RULES:
        c.execute('''INSERT OR IGNORE INTO cc_diagnostic_rules(guideline_id,rule_code,article,title,aliases,recommendation,auto_kind,condition_text,evidence,summary,priority,active) VALUES(?,?,?,?,?,?,?,?,?,?,?,1)''',(gid,rule['code'],rule['article'],rule['title'],dump(rule['aliases']),rule['recommendation'],rule['auto_kind'],rule['condition'],rule['evidence'],rule['summary'],rule['priority']))
        existing=c.execute('SELECT id,aliases FROM cc_diagnostic_rules WHERE guideline_id=? AND rule_code=?',(gid,rule['code'])).fetchone()
        if existing:
            saved_aliases=json.loads(existing[1]);merged=list(dict.fromkeys([*saved_aliases,*rule['aliases']]))
            if merged!=saved_aliases:c.execute('UPDATE cc_diagnostic_rules SET aliases=?,version=version+1 WHERE id=?',(dump(merged),existing[0]))
def connect():
    shared.DATA.mkdir(parents=True,exist_ok=True);c=shared.connect(shared.DATA/'corporate_close.db');c.create_function('current_actor',0,lambda:'system')
    c.executescript('''
    CREATE TABLE IF NOT EXISTS cc_companies(id INTEGER PRIMARY KEY,name TEXT NOT NULL UNIQUE,payload TEXT NOT NULL,version INTEGER NOT NULL DEFAULT 1,deleted INTEGER NOT NULL DEFAULT 0);
    CREATE TABLE IF NOT EXISTS cc_cases(id INTEGER PRIMARY KEY,company_id INTEGER NOT NULL REFERENCES cc_companies(id),year INTEGER NOT NULL,payload TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'draft',version INTEGER NOT NULL DEFAULT 1,UNIQUE(company_id,year));
    CREATE TABLE IF NOT EXISTS cc_adjustments(id INTEGER PRIMARY KEY,case_id INTEGER NOT NULL REFERENCES cc_cases(id),side TEXT NOT NULL,name TEXT NOT NULL,amount INTEGER NOT NULL,target TEXT NOT NULL,cost_amount INTEGER NOT NULL DEFAULT 0,account_group TEXT NOT NULL DEFAULT '원가',note TEXT NOT NULL DEFAULT '',source_key TEXT NOT NULL DEFAULT '',version INTEGER NOT NULL DEFAULT 1,deleted INTEGER NOT NULL DEFAULT 0,UNIQUE(case_id,source_key));
    CREATE TABLE IF NOT EXISTS cc_reserves(id INTEGER PRIMARY KEY,company_id INTEGER NOT NULL REFERENCES cc_companies(id),name TEXT NOT NULL,origin_year INTEGER NOT NULL,initial_amount INTEGER NOT NULL,target TEXT NOT NULL,note TEXT NOT NULL DEFAULT '',version INTEGER NOT NULL DEFAULT 1,deleted INTEGER NOT NULL DEFAULT 0,UNIQUE(company_id,name,origin_year));
    CREATE TABLE IF NOT EXISTS cc_reserve_years(id INTEGER PRIMARY KEY,reserve_id INTEGER NOT NULL REFERENCES cc_reserves(id),year INTEGER NOT NULL,beginning INTEGER NOT NULL,increase INTEGER NOT NULL,deduction INTEGER NOT NULL,other INTEGER NOT NULL DEFAULT 0,ending INTEGER NOT NULL,confirmed INTEGER NOT NULL DEFAULT 0,version INTEGER NOT NULL DEFAULT 1,UNIQUE(reserve_id,year));
    CREATE TABLE IF NOT EXISTS cc_imports(id INTEGER PRIMARY KEY,case_id INTEGER NOT NULL REFERENCES cc_cases(id),kind TEXT NOT NULL,name TEXT NOT NULL,digest TEXT NOT NULL,content TEXT NOT NULL,payload TEXT NOT NULL,created_at TEXT DEFAULT CURRENT_TIMESTAMP,deleted INTEGER NOT NULL DEFAULT 0,UNIQUE(case_id,kind,digest));
    CREATE TABLE IF NOT EXISTS cc_ledger_rows(id INTEGER PRIMARY KEY,import_id INTEGER NOT NULL REFERENCES cc_imports(id),posting_date TEXT NOT NULL DEFAULT '',account TEXT NOT NULL,description TEXT NOT NULL,amount INTEGER NOT NULL,business TEXT NOT NULL DEFAULT '',classification TEXT NOT NULL DEFAULT '',deleted INTEGER NOT NULL DEFAULT 0);
    CREATE TABLE IF NOT EXISTS cc_rules(id INTEGER PRIMARY KEY,company_id INTEGER NOT NULL REFERENCES cc_companies(id),kind TEXT NOT NULL,keyword TEXT NOT NULL,classification TEXT NOT NULL,version INTEGER NOT NULL DEFAULT 1,deleted INTEGER NOT NULL DEFAULT 0,UNIQUE(company_id,kind,keyword));
    CREATE TABLE IF NOT EXISTS cc_statement_rules(id INTEGER PRIMARY KEY,company_id INTEGER NOT NULL REFERENCES cc_companies(id),statement TEXT NOT NULL,keyword TEXT NOT NULL,version INTEGER NOT NULL DEFAULT 1,deleted INTEGER NOT NULL DEFAULT 0,UNIQUE(company_id,statement,keyword));
    CREATE TABLE IF NOT EXISTS cc_progress_imports(id INTEGER PRIMARY KEY,case_id INTEGER NOT NULL REFERENCES cc_cases(id),name TEXT NOT NULL,sheet_name TEXT NOT NULL,digest TEXT NOT NULL,content TEXT NOT NULL,created_at TEXT DEFAULT CURRENT_TIMESTAMP,deleted INTEGER NOT NULL DEFAULT 0,UNIQUE(case_id,digest));
    CREATE TABLE IF NOT EXISTS cc_progress_projects(id INTEGER PRIMARY KEY,case_id INTEGER NOT NULL REFERENCES cc_cases(id),import_id INTEGER REFERENCES cc_progress_imports(id),source_row INTEGER NOT NULL DEFAULT 0,client TEXT NOT NULL DEFAULT '',project TEXT NOT NULL,start TEXT NOT NULL DEFAULT '',end TEXT NOT NULL DEFAULT '',contract INTEGER NOT NULL DEFAULT 0,prior_revenue INTEGER NOT NULL DEFAULT 0,current_revenue INTEGER NOT NULL DEFAULT 0,prior_cost INTEGER NOT NULL DEFAULT 0,current_cost INTEGER NOT NULL DEFAULT 0,expected_cost_rate REAL NOT NULL DEFAULT 0,trade TEXT NOT NULL DEFAULT '',status TEXT NOT NULL DEFAULT '',prior_adjustment INTEGER NOT NULL DEFAULT 0,current_adjustment INTEGER NOT NULL DEFAULT 0,prior_unfinished INTEGER NOT NULL DEFAULT 0,current_unfinished INTEGER NOT NULL DEFAULT 0,note TEXT NOT NULL DEFAULT '',version INTEGER NOT NULL DEFAULT 1,deleted INTEGER NOT NULL DEFAULT 0);
    CREATE TABLE IF NOT EXISTS cc_industry_publications(id INTEGER PRIMARY KEY,association TEXT NOT NULL,category TEXT NOT NULL,publication_year INTEGER NOT NULL,filename TEXT NOT NULL,digest TEXT NOT NULL,content TEXT NOT NULL,extracted_text TEXT NOT NULL DEFAULT '',ratios TEXT NOT NULL,created_at TEXT DEFAULT CURRENT_TIMESTAMP,version INTEGER NOT NULL DEFAULT 1,deleted INTEGER NOT NULL DEFAULT 0,UNIQUE(association,category,publication_year));
    CREATE TABLE IF NOT EXISTS cc_management_ratio_inputs(id INTEGER PRIMARY KEY,case_id INTEGER NOT NULL UNIQUE REFERENCES cc_cases(id),payload TEXT NOT NULL,source_name TEXT NOT NULL DEFAULT '',source_digest TEXT NOT NULL DEFAULT '',source_content TEXT,updated_at TEXT DEFAULT CURRENT_TIMESTAMP,version INTEGER NOT NULL DEFAULT 1);
    CREATE TABLE IF NOT EXISTS cc_real_capital_inputs(id INTEGER PRIMARY KEY,case_id INTEGER NOT NULL UNIQUE REFERENCES cc_cases(id),payload TEXT NOT NULL,source_name TEXT NOT NULL DEFAULT '',source_digest TEXT NOT NULL DEFAULT '',source_content TEXT,updated_at TEXT DEFAULT CURRENT_TIMESTAMP,version INTEGER NOT NULL DEFAULT 1);
    CREATE TABLE IF NOT EXISTS cc_company_licenses(id INTEGER PRIMARY KEY,company_id INTEGER NOT NULL REFERENCES cc_companies(id),name TEXT NOT NULL,effective_year INTEGER NOT NULL,required_capital INTEGER NOT NULL DEFAULT 0,adjustment INTEGER NOT NULL DEFAULT 0,note TEXT NOT NULL DEFAULT '',active INTEGER NOT NULL DEFAULT 1,version INTEGER NOT NULL DEFAULT 1,deleted INTEGER NOT NULL DEFAULT 0,UNIQUE(company_id,name,effective_year));
    CREATE TABLE IF NOT EXISTS cc_diagnostic_guidelines(id INTEGER PRIMARY KEY,name TEXT NOT NULL UNIQUE,source_status TEXT NOT NULL DEFAULT '',effective_from TEXT NOT NULL DEFAULT '',notification_no TEXT NOT NULL DEFAULT '',source_note TEXT NOT NULL DEFAULT '',content TEXT NOT NULL DEFAULT '',active INTEGER NOT NULL DEFAULT 1,version INTEGER NOT NULL DEFAULT 1,created_at TEXT DEFAULT CURRENT_TIMESTAMP,updated_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS cc_diagnostic_rules(id INTEGER PRIMARY KEY,guideline_id INTEGER NOT NULL REFERENCES cc_diagnostic_guidelines(id),rule_code TEXT NOT NULL,article TEXT NOT NULL,title TEXT NOT NULL,aliases TEXT NOT NULL,recommendation TEXT NOT NULL,auto_kind TEXT NOT NULL DEFAULT 'review',condition_text TEXT NOT NULL DEFAULT '',evidence TEXT NOT NULL DEFAULT '',summary TEXT NOT NULL DEFAULT '',priority INTEGER NOT NULL DEFAULT 999,active INTEGER NOT NULL DEFAULT 1,version INTEGER NOT NULL DEFAULT 1,deleted INTEGER NOT NULL DEFAULT 0,UNIQUE(guideline_id,rule_code));
    ''')
    columns={r[1] for r in c.execute('PRAGMA table_info(cc_adjustments)')}
    if 'account_group' not in columns:c.execute("ALTER TABLE cc_adjustments ADD COLUMN account_group TEXT NOT NULL DEFAULT '원가'")
    ledger_columns={r[1] for r in c.execute('PRAGMA table_info(cc_ledger_rows)')}
    if 'debit' not in ledger_columns:c.execute('ALTER TABLE cc_ledger_rows ADD COLUMN debit INTEGER')
    if 'credit' not in ledger_columns:c.execute('ALTER TABLE cc_ledger_rows ADD COLUMN credit INTEGER')
    if 'counterparty' not in ledger_columns:c.execute("ALTER TABLE cc_ledger_rows ADD COLUMN counterparty TEXT NOT NULL DEFAULT ''")
    progress_columns={r[1] for r in c.execute('PRAGMA table_info(cc_progress_projects)')}
    progress_added='project_key' not in progress_columns
    for column,definition in [
        ('project_key',"TEXT NOT NULL DEFAULT ''"),('allocation_mode',"TEXT NOT NULL DEFAULT 'auto'"),
        ('allocated_adjustment','INTEGER'),('carryover_eligible','INTEGER NOT NULL DEFAULT 1'),
        ('carryover_note',"TEXT NOT NULL DEFAULT ''"),('import_missing','INTEGER NOT NULL DEFAULT 0')]:
        if column not in progress_columns:c.execute(f'ALTER TABLE cc_progress_projects ADD COLUMN {column} {definition}')
    if progress_added:
        progress_rows=rows(c,'SELECT id,client,project,start,status FROM cc_progress_projects')
        for row in progress_rows:
            key='|'.join([normalized(row['client']),normalized(row['project']),normalized(row['start'])])
            carry=0 if '준공' in normalized(row['status']) else 1
            c.execute('UPDATE cc_progress_projects SET project_key=?,carryover_eligible=? WHERE id=?',(key,carry,row['id']))
    # Account groups are user decisions.  Never reclassify existing rows when
    # opening the screen: doing so overwrote a user's 고정자산→원가 change and
    # also advanced the collaboration revision before the save could complete.
    for name in DEFAULT_COMPANIES:c.execute('INSERT OR IGNORE INTO cc_companies(name,payload) VALUES(?,?)',(name,dump({'businesses':['건설업']})))
    for company_id, in c.execute('SELECT id FROM cc_companies'):_seed_rules(c,company_id);_seed_tax_dues_rules(c,company_id)
    _seed_diagnostic_guideline(c)
    c.commit();return shared.protect(c)

def companies(c,include_deleted=False):
    out=[]
    for r in rows(c,'SELECT * FROM cc_companies ORDER BY id'):
        if r['deleted'] and not include_deleted:continue
        out.append({**json.loads(r['payload']),'id':r['id'],'name':r['name'],'version':r['version'],'deleted':bool(r['deleted'])})
    return out
def save_company(c,name,businesses,id=None,expected=None):
    name=str(name).strip();bs=list(dict.fromkeys(str(x).strip() for x in businesses if str(x).strip()))
    if not name or not bs:raise ValueError('법인명과 한 개 이상의 업종을 입력하세요.')
    with c:
        if id:
            old=next((x for x in companies(c,True) if x['id']==id),None)
            if not old or old['version']!=expected:raise ValueError('법인 정보가 변경되었습니다. 다시 불러오세요.')
            c.execute('UPDATE cc_companies SET name=?,payload=?,version=version+1,deleted=0 WHERE id=?',(name,dump({'businesses':bs}),id));return id
        id=c.execute('INSERT INTO cc_companies(name,payload) VALUES(?,?)',(name,dump({'businesses':bs}))).lastrowid;_seed_rules(c,id);_seed_tax_dues_rules(c,id);return id
def delete_company(c,id,expected,reason):
    if c.execute('SELECT 1 FROM cc_cases WHERE company_id=?',(id,)).fetchone():raise ValueError('결산 자료가 있는 법인은 삭제할 수 없습니다.')
    if not str(reason).strip():raise ValueError('삭제 사유를 입력하세요.')
    with c:c.execute('UPDATE cc_companies SET deleted=1,version=version+1 WHERE id=? AND version=?',(id,expected))
def restore_company(c,id,expected):
    with c:c.execute('UPDATE cc_companies SET deleted=0,version=version+1 WHERE id=? AND version=?',(id,expected))

def company_license_records(c,company_id,include_deleted=False):
    result=rows(c,'SELECT * FROM cc_company_licenses WHERE company_id=? ORDER BY name,effective_year',(int(company_id),))
    return [{**row,'active':bool(row['active'])} for row in result if include_deleted or not row['deleted']]
def company_license_current_records(c,company_id):
    latest={}
    for row in company_license_records(c,company_id):
        if row['name'] not in latest or row['effective_year']>=latest[row['name']]['effective_year']:latest[row['name']]=row
    return sorted(latest.values(),key=lambda row:(row['name'],row['id']))
def save_company_license_records(c,company_id,records):
    cleaned=[];names=set()
    def integer(value,default=0):
        if value in (None,'') or value!=value:return int(default)
        return int(float(str(value).replace(',','').strip()))
    for raw in records or []:
        name=str(raw.get('면허명·업종','') or '').strip()
        if not name or name.lower()=='nan':continue
        required=max(0,integer(raw.get('요구자본금')));adjustment=integer(raw.get('중복·겸업 조정액'));note=str(raw.get('근거·비고','') or '').strip();active=bool(raw.get('적용',True))
        if name in names:raise ValueError(f'같은 면허가 중복되었습니다: {name}')
        names.add(name);cleaned.append((name,required,adjustment,note,int(active)))
    with c:
        for name,required,adjustment,note,active in cleaned:
            c.execute('''INSERT INTO cc_company_licenses(company_id,name,effective_year,required_capital,adjustment,note,active) VALUES(?,?,?,?,?,?,?)
                         ON CONFLICT(company_id,name,effective_year) DO UPDATE SET required_capital=excluded.required_capital,adjustment=excluded.adjustment,note=excluded.note,active=excluded.active,deleted=0,version=cc_company_licenses.version+1''',(int(company_id),name,0,required,adjustment,note,active))
        if names:
            placeholders=','.join('?' for _ in names);c.execute(f'''UPDATE cc_company_licenses SET deleted=1,version=version+1 WHERE company_id=? AND deleted=0 AND (effective_year<>0 OR name NOT IN ({placeholders}))''',(int(company_id),*names))
        else:c.execute('UPDATE cc_company_licenses SET deleted=1,version=version+1 WHERE company_id=? AND deleted=0',(int(company_id),))
    return company_license_current_records(c,company_id)
def company_licenses_for_year(c,company_id,year):
    return [{'면허명·업종':row['name'],'요구자본금':row['required_capital'],'중복·겸업 조정액':row['adjustment'],'적용연도':int(year),'근거·비고':row['note']} for row in company_license_current_records(c,company_id) if row['active']]

def diagnostic_guidelines(c):
    return [{**row,'active':bool(row['active'])} for row in rows(c,'SELECT * FROM cc_diagnostic_guidelines ORDER BY id')]
def diagnostic_rules(c,guideline_id=None,active_only=False):
    clauses=['deleted=0'];args=[]
    if guideline_id is not None:clauses.append('guideline_id=?');args.append(int(guideline_id))
    if active_only:clauses.append('active=1')
    result=[]
    for row in rows(c,'SELECT * FROM cc_diagnostic_rules WHERE '+' AND '.join(clauses)+' ORDER BY priority,id',tuple(args)):
        row['aliases']=json.loads(row['aliases']);row['active']=bool(row['active']);result.append(row)
    return result
def save_diagnostic_guideline(c,id,source_status,effective_from,notification_no,source_note,active,expected):
    with c:
        cur=c.execute('''UPDATE cc_diagnostic_guidelines SET source_status=?,effective_from=?,notification_no=?,source_note=?,active=?,version=version+1,updated_at=CURRENT_TIMESTAMP WHERE id=? AND version=?''',(str(source_status).strip(),str(effective_from).strip(),str(notification_no).strip(),str(source_note).strip(),int(bool(active)),int(id),int(expected)))
        if cur.rowcount!=1:raise ValueError('기업진단지침 정보가 변경되었습니다. 최신 자료를 다시 불러오세요.')
def save_diagnostic_rules(c,guideline_id,records):
    cleaned=[];codes=set()
    for raw in records or []:
        title=str(raw.get('규칙명','') or '').strip()
        if not title or title.lower()=='nan':continue
        code=str(raw.get('규칙코드','') or '').strip() or 'user_'+hashlib.sha1(title.encode()).hexdigest()[:12]
        if code in codes:raise ValueError(f'규칙코드가 중복되었습니다: {code}')
        codes.add(code);aliases=[part.strip() for part in re.split(r'[,|\n]',str(raw.get('계정별칭','') or '')) if part.strip()]
        cleaned.append({'code':code,'article':str(raw.get('조문','') or '').strip(),'title':title,'aliases':aliases,'recommendation':str(raw.get('권고판정','검토 필요') or '검토 필요').strip(),'auto_kind':str(raw.get('자동유형','review') or 'review').strip(),'condition':str(raw.get('확인조건','') or '').strip(),'evidence':str(raw.get('필요증빙','') or '').strip(),'summary':str(raw.get('규칙요약','') or '').strip(),'priority':int(float(raw.get('우선순위') or 999)),'active':int(bool(raw.get('적용',True)))})
    with c:
        for rule in cleaned:
            c.execute('''INSERT INTO cc_diagnostic_rules(guideline_id,rule_code,article,title,aliases,recommendation,auto_kind,condition_text,evidence,summary,priority,active) VALUES(?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(guideline_id,rule_code) DO UPDATE SET article=excluded.article,title=excluded.title,aliases=excluded.aliases,recommendation=excluded.recommendation,auto_kind=excluded.auto_kind,condition_text=excluded.condition_text,evidence=excluded.evidence,summary=excluded.summary,priority=excluded.priority,active=excluded.active,deleted=0,version=cc_diagnostic_rules.version+1''',(int(guideline_id),rule['code'],rule['article'],rule['title'],dump(rule['aliases']),rule['recommendation'],rule['auto_kind'],rule['condition'],rule['evidence'],rule['summary'],rule['priority'],rule['active']))
        if codes:
            placeholders=','.join('?' for _ in codes);c.execute(f'UPDATE cc_diagnostic_rules SET deleted=1,version=version+1 WHERE guideline_id=? AND deleted=0 AND rule_code NOT IN ({placeholders})',(int(guideline_id),*codes))
        else:c.execute('UPDATE cc_diagnostic_rules SET deleted=1,version=version+1 WHERE guideline_id=? AND deleted=0',(int(guideline_id),))

def case(c,company_id,year,create=True):
    r=c.execute('SELECT * FROM cc_cases WHERE company_id=? AND year=?',(company_id,int(year))).fetchone()
    if not r and create:
        with c:c.execute('INSERT INTO cc_cases(company_id,year,payload) VALUES(?,?,?)',(company_id,int(year),dump({'values':{},'review':{},'business_revenue':{},'tax':{},'losses':{},'disposal_date':f'{int(year)+1}-03-31'})))
        r=c.execute('SELECT * FROM cc_cases WHERE company_id=? AND year=?',(company_id,int(year))).fetchone()
    if not r:return None
    names=[d[0] for d in c.execute('SELECT * FROM cc_cases LIMIT 0').description]
    d=dict(zip(names,r));return {**json.loads(d['payload']),'id':d['id'],'company_id':d['company_id'],'year':d['year'],'status':d['status'],'version':d['version']}
def ensure_open(x):
    if x['status']=='confirmed':raise ValueError('확정된 법인결산입니다. 확정을 해제한 뒤 수정하세요.')
def save_case(c,x,payload,expected):
    ensure_open(x)
    if expected!=x['version']:raise ValueError('결산 자료가 변경되었습니다. 다시 불러오세요.')
    with c:c.execute('UPDATE cc_cases SET payload=?,version=version+1 WHERE id=?',(dump(payload),x['id']))
def confirm(c,x):
    ensure_open(x)
    sync_all_reserves(c,x)
    with c:
        c.execute("UPDATE cc_cases SET status='confirmed',version=version+1 WHERE id=?",(x['id'],))
        c.execute('''UPDATE cc_reserve_years SET confirmed=1,version=version+1
                     WHERE year=? AND reserve_id IN
                     (SELECT id FROM cc_reserves WHERE company_id=?)''',(x['year'],x['company_id']))
def reopen(c,x,reason):
    if x['status']!='confirmed':raise ValueError('확정된 결산이 아닙니다.')
    if not str(reason).strip():raise ValueError('확정 해제 사유를 입력하세요.')
    with c:
        c.execute("UPDATE cc_cases SET status='draft',version=version+1 WHERE id=?",(x['id'],))
        c.execute('''UPDATE cc_reserve_years SET confirmed=0,version=version+1
                     WHERE year=? AND reserve_id IN
                     (SELECT id FROM cc_reserves WHERE company_id=?)''',(x['year'],x['company_id']))

def prior_case(c,company_id,year):
    return case(c,company_id,int(year)-1,create=False)

def industry_publications(c,association=None,category=None,include_deleted=False):
    clauses=[];args=[]
    if association:clauses.append('association=?');args.append(str(association))
    if category:clauses.append('category=?');args.append(str(category))
    if not include_deleted:clauses.append('deleted=0')
    where=(' WHERE '+' AND '.join(clauses)) if clauses else ''
    out=[]
    for row in rows(c,'SELECT * FROM cc_industry_publications'+where+' ORDER BY publication_year,association,category',tuple(args)):
        row['ratios']=json.loads(row['ratios']);row['content']=base64.b64decode(row['content']) if row.get('content') else b'';out.append(row)
    return out
def save_industry_publication(c,association,category,publication_year,filename,content,extracted_text,ratios):
    association=str(association).strip();category=str(category).strip();filename=str(filename).strip();year=int(publication_year)
    if not association or not category or year<1990:raise ValueError('협회명·업종·공시연도를 확인하세요.')
    payload={str(k):(None if v in (None,'') else float(v)) for k,v in dict(ratios or {}).items()}
    if not any(v not in (None,0) for v in payload.values()):raise ValueError('협회 공시 비율이 모두 0입니다. 비율값을 입력한 뒤 저장하세요.')
    digest=hashlib.sha256(content or b'').hexdigest()
    with c:
        c.execute('''INSERT INTO cc_industry_publications(association,category,publication_year,filename,digest,content,extracted_text,ratios)
                     VALUES(?,?,?,?,?,?,?,?)
                     ON CONFLICT(association,category,publication_year) DO UPDATE SET filename=excluded.filename,digest=excluded.digest,content=excluded.content,extracted_text=excluded.extracted_text,ratios=excluded.ratios,deleted=0,version=cc_industry_publications.version+1,created_at=CURRENT_TIMESTAMP''',
                  (association,category,year,filename,digest,base64.b64encode(content or b'').decode(),str(extracted_text or ''),dump(payload)))
    return next(r for r in industry_publications(c,association,category) if r['publication_year']==year)
def delete_industry_publication(c,id,expected):
    with c:
        cur=c.execute('UPDATE cc_industry_publications SET deleted=1,version=version+1 WHERE id=? AND version=?',(int(id),int(expected)))
        if cur.rowcount!=1:raise ValueError('협회 공시자료가 변경되었습니다. 다시 불러오세요.')
def management_ratio_input(c,case_id):
    row=c.execute('SELECT * FROM cc_management_ratio_inputs WHERE case_id=?',(int(case_id),)).fetchone()
    if not row:return {'payload':{},'source_name':'','source_digest':'','version':0}
    names=[d[0] for d in c.execute('SELECT * FROM cc_management_ratio_inputs LIMIT 0').description];item=dict(zip(names,row));item['payload']=json.loads(item['payload']);return item
def save_management_ratio_input(c,case_id,payload,source_name='',source_content=b'',expected=None):
    current=management_ratio_input(c,case_id)
    if expected is not None and int(expected)!=int(current.get('version',0)):raise ValueError('경영상태 점검자료가 변경되었습니다. 최신 자료를 다시 불러오세요.')
    digest=hashlib.sha256(source_content or b'').hexdigest() if source_content else current.get('source_digest','')
    content=base64.b64encode(source_content).decode() if source_content else None
    with c:
        if current.get('version'):
            c.execute('''UPDATE cc_management_ratio_inputs SET payload=?,source_name=?,source_digest=?,source_content=COALESCE(?,source_content),updated_at=CURRENT_TIMESTAMP,version=version+1 WHERE case_id=?''',
                      (dump(payload),str(source_name or current.get('source_name','')),digest,content,int(case_id)))
        else:c.execute('INSERT INTO cc_management_ratio_inputs(case_id,payload,source_name,source_digest,source_content) VALUES(?,?,?,?,?)',(int(case_id),dump(payload),str(source_name or ''),digest,content))
    return management_ratio_input(c,case_id)
def management_ratio_history(c,company_id):
    out=[]
    for row in rows(c,'''SELECT i.*,k.year,k.status FROM cc_management_ratio_inputs i JOIN cc_cases k ON k.id=i.case_id WHERE k.company_id=? ORDER BY k.year''',(int(company_id),)):
        row['payload']=json.loads(row['payload']);out.append(row)
    return out

def real_capital_input(c,case_id):
    row=c.execute('SELECT * FROM cc_real_capital_inputs WHERE case_id=?',(int(case_id),)).fetchone()
    if not row:return {'payload':{'items':[],'licenses':[]},'source_name':'','source_digest':'','version':0}
    names=[d[0] for d in c.execute('SELECT * FROM cc_real_capital_inputs LIMIT 0').description];item=dict(zip(names,row));item['payload']=json.loads(item['payload']);return item
def save_real_capital_input(c,case_id,payload,source_name='',source_content=b'',expected=None):
    current=real_capital_input(c,case_id)
    if expected is not None and int(expected)!=int(current.get('version',0)):raise ValueError('실질자본금 점검자료가 변경되었습니다. 최신 자료를 다시 불러오세요.')
    digest=hashlib.sha256(source_content or b'').hexdigest() if source_content else current.get('source_digest','')
    content=base64.b64encode(source_content).decode() if source_content else None
    with c:
        if current.get('version'):
            c.execute('''UPDATE cc_real_capital_inputs SET payload=?,source_name=?,source_digest=?,source_content=COALESCE(?,source_content),updated_at=CURRENT_TIMESTAMP,version=version+1 WHERE case_id=?''',(dump(payload),str(source_name or current.get('source_name','')),digest,content,int(case_id)))
        else:c.execute('INSERT INTO cc_real_capital_inputs(case_id,payload,source_name,source_digest,source_content) VALUES(?,?,?,?,?)',(int(case_id),dump(payload),str(source_name or ''),digest,content))
    return real_capital_input(c,case_id)
def real_capital_history(c,company_id):
    out=[]
    for row in rows(c,'''SELECT i.*,k.year,k.status FROM cc_real_capital_inputs i JOIN cc_cases k ON k.id=i.case_id WHERE k.company_id=? ORDER BY k.year''',(int(company_id),)):
        row['payload']=json.loads(row['payload']);out.append(row)
    return out

def adjustments(c,case_id,include_deleted=False):
    order="CASE account_group WHEN '원가' THEN 1 WHEN '자산' THEN 2 WHEN '영업외비용' THEN 3 WHEN '영업외수익' THEN 4 WHEN '법인세' THEN 5 ELSE 9 END";out=rows(c,f'SELECT * FROM cc_adjustments WHERE case_id=? ORDER BY side,{order},id',(case_id,));return [r for r in out if include_deleted or not r['deleted']]
def save_adjustment(c,x,side,name,amount,target,cost_amount=0,note='',id=None,expected=None,source_key='',account_group='원가'):
    ensure_open(x);name=str(name).strip();amount=calc.won(calc.nonnegative(amount));cost=calc.won(calc.nonnegative(cost_amount))
    if side not in ['add','deduct'] or target not in ['원가','판관비','공통'] or account_group not in calc.ACCOUNT_GROUPS or not name:raise ValueError('세무조정 구분과 과목을 확인하세요.')
    if target=='공통' and cost>amount:raise ValueError('원가 배분액은 입력금액 이하여야 합니다.')
    sync_names=[name]
    def change():
        with c:
            if id:
                old=c.execute('SELECT version,source_key,name FROM cc_adjustments WHERE id=? AND case_id=?',(id,x['id'])).fetchone()
                if not old or old[0]!=expected:raise ValueError('같은 조정항목이 다른 화면에서 변경되었습니다. 최신 자료를 확인하세요.')
                if old[1] and old[1].startswith('reserve:'):raise ValueError('유보 연계 항목은 유보잔액 관리에서 수정하세요.')
                sync_names.append(old[2])
                c.execute('UPDATE cc_adjustments SET side=?,name=?,amount=?,target=?,cost_amount=?,account_group=?,note=?,version=version+1,deleted=0 WHERE id=?',(side,name,amount,target,cost,account_group,note,id));return id
            key=source_key or f'manual:{uuid.uuid4().hex}'
            return c.execute('INSERT INTO cc_adjustments(case_id,side,name,amount,target,cost_amount,account_group,note,source_key) VALUES(?,?,?,?,?,?,?,?,?)',(x['id'],side,name,amount,target,cost,account_group,note,key)).lastrowid
    result=write_with_refresh(c,change);sync_all_reserves(c,x,sync_names);return result
def delete_adjustment(c,x,id,expected,reason):
    ensure_open(x)
    if not str(reason).strip():raise ValueError('삭제 사유를 입력하세요.')
    sync_names=[]
    def change():
        row=c.execute('SELECT version,source_key,name FROM cc_adjustments WHERE id=? AND case_id=?',(id,x['id'])).fetchone()
        if not row or row[0]!=expected:raise ValueError('같은 조정항목이 다른 화면에서 변경되었습니다. 최신 자료를 확인하세요.')
        if row[1] and row[1].startswith('reserve:'):raise ValueError('유보 연계 항목은 유보잔액 관리에서 수정하세요.')
        sync_names.append(row[2])
        with c:c.execute('UPDATE cc_adjustments SET deleted=1,note=note||?,version=version+1 WHERE id=?',('\n삭제: '+reason,id))
    result=write_with_refresh(c,change);sync_all_reserves(c,x,sync_names);return result
def restore_adjustment(c,x,id,expected):
    ensure_open(x)
    row=c.execute('SELECT name FROM cc_adjustments WHERE id=? AND case_id=?',(id,x['id'])).fetchone()
    with c:c.execute('UPDATE cc_adjustments SET deleted=0,version=version+1 WHERE id=? AND version=?',(id,expected))
    if row:sync_all_reserves(c,x,[row[0]])

def reserves(c,company_id,include_deleted=False):
    out=rows(c,'SELECT * FROM cc_reserves WHERE company_id=? ORDER BY origin_year,id',(company_id,));return [r for r in out if include_deleted or not r['deleted']]
def reserve_years(c,reserve_id):return rows(c,'SELECT * FROM cc_reserve_years WHERE reserve_id=? ORDER BY year',(reserve_id,))
RESERVE_TARGETS=['원가','판관비','영업외수익','영업외비용']
def _reserve_group(target):return target if target in ['영업외수익','영업외비용'] else '원가'
def _reserve_target(target):return target if target in ['원가','판관비'] else '판관비'
def reserve_adjustment_status(c,x,reserve):
    duplicate=sum(1 for r in reserves(c,x['company_id']) if r['name']==reserve['name'])>1
    manual=[r for r in adjustments(c,x['id']) if r['name']==reserve['name'] and not str(r.get('source_key','')).startswith('reserve:')]
    increase=sum(r['amount'] for r in manual if r['side']=='add');deduction=sum(r['amount'] for r in manual if r['side']=='deduct')
    prior=c.execute('SELECT ending FROM cc_reserve_years WHERE reserve_id=? AND year<? ORDER BY year DESC LIMIT 1',(reserve['id'],x['year'])).fetchone();beginning=prior[0] if prior else reserve['initial_amount']
    current=c.execute('SELECT other FROM cc_reserve_years WHERE reserve_id=? AND year=?',(reserve['id'],x['year'])).fetchone();other=current[0] if current else 0
    available=beginning+increase+other;overage=max(0,deduction-available)
    return {'ambiguous':duplicate,'count':len(manual),'increase':increase,'deduction':deduction,'beginning':beginning,'other':other,'available':available,'overage':overage,'valid':not duplicate and overage==0}
def sync_reserve_from_adjustments(c,x,reserve_id,force=False):
    reserve=next((r for r in reserves(c,x['company_id']) if r['id']==reserve_id),None)
    if not reserve:return False
    status=reserve_adjustment_status(c,x,reserve)
    if status['ambiguous']:return False
    prefix=f'reserve:{reserve_id}:{x["year"]}:'
    active=adjustments(c,x['id']);manual=[r for r in active if r['name']==reserve['name'] and not str(r.get('source_key','')).startswith('reserve:')]
    linked=[r for r in active if str(r.get('source_key','')).startswith(prefix)]
    source=manual if manual else linked
    existing=c.execute('SELECT beginning,increase,deduction,other,ending FROM cc_reserve_years WHERE reserve_id=? AND year=?',(reserve_id,x['year'])).fetchone()
    history=any(r['name']==reserve['name'] for r in adjustments(c,x['id'],True))
    if not source and not force and not history:return False
    prior=c.execute('SELECT ending FROM cc_reserve_years WHERE reserve_id=? AND year<? ORDER BY year DESC LIMIT 1',(reserve_id,x['year'])).fetchone();beginning=prior[0] if prior else reserve['initial_amount'];increase=sum(r['amount'] for r in source if r['side']=='add');deduction=sum(r['amount'] for r in source if r['side']=='deduct');other=existing[3] if existing else 0
    # An invalid manual adjustment must not make the entire reserve page
    # unreachable. Keep the user's source amount intact and skip only this
    # automatic roll-forward; the UI shows the exact excess to correct.
    if deduction>beginning+increase+other:return False
    ending=calc.reserve_rollforward(beginning,increase,deduction,other);values=(beginning,increase,deduction,other,ending)
    if existing and tuple(existing)==values:return False
    with c:
        if manual:c.execute("UPDATE cc_adjustments SET deleted=1,version=version+1 WHERE case_id=? AND source_key LIKE ?",(x['id'],prefix+'%'))
        c.execute('INSERT INTO cc_reserve_years(reserve_id,year,beginning,increase,deduction,other,ending) VALUES(?,?,?,?,?,?,?) ON CONFLICT(reserve_id,year) DO UPDATE SET beginning=excluded.beginning,increase=excluded.increase,deduction=excluded.deduction,other=excluded.other,ending=excluded.ending,version=cc_reserve_years.version+1',(reserve_id,x['year'],*values))
    return True
def sync_all_reserves(c,x,force_names=()):
    names=set(force_names or ());changed=0
    for reserve in reserves(c,x['company_id']):changed+=int(sync_reserve_from_adjustments(c,x,reserve['id'],reserve['name'] in names))
    return changed
def save_reserve(c,x,name,origin_year,initial,target,note='',id=None,expected=None):
    ensure_open(x);name=str(name).strip();initial=calc.won(calc.nonnegative(initial))
    if not name or target not in RESERVE_TARGETS:raise ValueError('유보항목과 반영 구분을 확인하세요.')
    with c:
        if id:
            row=c.execute('SELECT version FROM cc_reserves WHERE id=? AND company_id=?',(id,x['company_id'])).fetchone()
            if not row or row[0]!=expected:raise ValueError('유보항목을 다시 불러오세요.')
            c.execute('UPDATE cc_reserves SET name=?,origin_year=?,initial_amount=?,target=?,note=?,version=version+1,deleted=0 WHERE id=?',(name,int(origin_year),initial,target,note,id));rid=id
        else:rid=c.execute('INSERT INTO cc_reserves(company_id,name,origin_year,initial_amount,target,note) VALUES(?,?,?,?,?,?)',(x['company_id'],name,int(origin_year),initial,target,note)).lastrowid
        c.execute("""UPDATE cc_adjustments SET name=?,target=?,account_group=?,version=version+1
                     WHERE source_key LIKE ? AND case_id IN (SELECT id FROM cc_cases WHERE status='draft')""",(name,_reserve_target(target),_reserve_group(target),f'reserve:{rid}:%'))
    sync_reserve_from_adjustments(c,x,rid);return rid
def save_reserve_year(c,x,reserve_id,year,increase,deduction,other=0):
    ensure_open(x);r=next((r for r in reserves(c,x['company_id']) if r['id']==reserve_id),None)
    if not r:raise ValueError('유보항목을 확인하세요.')
    prior=c.execute('SELECT ending FROM cc_reserve_years WHERE reserve_id=? AND year<? ORDER BY year DESC LIMIT 1',(reserve_id,int(year))).fetchone();beginning=prior[0] if prior else r['initial_amount']
    status=reserve_adjustment_status(c,x,r)
    if status['ambiguous']:raise ValueError('같은 이름의 유보항목이 여러 개입니다. 관리항목 이름을 구분해 주세요.')
    manual=status['count']>0
    if manual:increase=status['increase'];deduction=status['deduction']
    ending=calc.reserve_rollforward(beginning,increase,deduction,other)
    with c:
        c.execute('INSERT INTO cc_reserve_years(reserve_id,year,beginning,increase,deduction,other,ending) VALUES(?,?,?,?,?,?,?) ON CONFLICT(reserve_id,year) DO UPDATE SET beginning=excluded.beginning,increase=excluded.increase,deduction=excluded.deduction,other=excluded.other,ending=excluded.ending,version=cc_reserve_years.version+1',(reserve_id,int(year),beginning,calc.won(increase),calc.won(deduction),calc.won(other),ending))
        if manual:c.execute("UPDATE cc_adjustments SET deleted=1,version=version+1 WHERE case_id=? AND source_key LIKE ?",(x['id'],f'reserve:{reserve_id}:{year}:%'))
        else:
            for side,amount,label in [('add',increase,r['name']),('deduct',deduction,r['name'])]:
                key=f'reserve:{reserve_id}:{year}:{side}'
                c.execute('INSERT INTO cc_adjustments(case_id,side,name,amount,target,cost_amount,account_group,note,source_key) VALUES(?,?,?,?,?,0,?,?,?) ON CONFLICT(case_id,source_key) DO UPDATE SET amount=excluded.amount,name=excluded.name,target=excluded.target,account_group=excluded.account_group,deleted=0,version=cc_adjustments.version+1',(x['id'],side,label,calc.won(amount),_reserve_target(r['target']),_reserve_group(r['target']),'유보잔액 자동 연계',key))
    return ending
def delete_reserve(c,x,id,expected,reason):
    ensure_open(x)
    if c.execute('SELECT 1 FROM cc_reserve_years WHERE reserve_id=? AND confirmed=1',(id,)).fetchone():raise ValueError('확정 이력이 있는 유보항목은 삭제할 수 없습니다.')
    if not str(reason).strip():raise ValueError('삭제 사유를 입력하세요.')
    with c:c.execute('UPDATE cc_reserves SET deleted=1,note=note||?,version=version+1 WHERE id=? AND version=?',('\n삭제: '+reason,id,expected))
def restore_reserve(c,x,id,expected):
    ensure_open(x)
    with c:c.execute('UPDATE cc_reserves SET deleted=0,version=version+1 WHERE id=? AND version=?',(id,expected))

def save_import(c,x,kind,name,content,parsed):
    ensure_open(x);digest=hashlib.sha256(content).hexdigest()
    if len(content)>20*1024*1024:raise ValueError('원장 파일은 20MB 이하만 등록할 수 있습니다.')
    with c:
        old=c.execute('SELECT id FROM cc_imports WHERE case_id=? AND kind=? AND digest=?',(x['id'],kind,digest)).fetchone()
        if old:raise ValueError('같은 원장 파일이 이미 등록되어 있습니다.')
        iid=c.execute('INSERT INTO cc_imports(case_id,kind,name,digest,content,payload) VALUES(?,?,?,?,?,?)',(x['id'],kind,name,digest,base64.b64encode(content).decode(),dump({'count':len(parsed),'amount_basis':'debit_credit_v1'}))).lastrowid
        _insert_ledger_rows(c,iid,kind,parsed)
    apply_income_rules(c,x)
    return iid
def imports(c,case_id):return rows(c,'SELECT id,kind,name,digest,payload,created_at,deleted FROM cc_imports WHERE case_id=? ORDER BY id DESC',(case_id,))
def _insert_ledger_rows(c,import_id,kind,parsed):
    import corporate_close_import as ledger_import
    values=[]
    for r in parsed:
        debit=r.get('debit');credit=r.get('credit')
        values.append((import_id,r.get('date',''),r.get('account',''),r.get('description',''),
                       calc.won(ledger_import.effective_amount(r,kind)),
                       None if debit is None else calc.won(debit),None if credit is None else calc.won(credit),
                       r.get('business',''),r.get('counterparty',''),r.get('classification','')))
    c.executemany('INSERT INTO cc_ledger_rows(import_id,posting_date,account,description,amount,debit,credit,business,counterparty,classification) VALUES(?,?,?,?,?,?,?,?,?,?)',values)
def imports_need_amount_rebuild(c,case_id):
    for r in imports(c,case_id):
        if r['deleted']:continue
        try:payload=json.loads(r['payload'] or '{}')
        except (TypeError,ValueError):payload={}
        if payload.get('amount_basis')!='debit_credit_v1':return True
    return False
def rebuild_ledger_amounts(c,x):
    """Reparse stored source files and replace legacy balance-based amounts."""
    ensure_open(x)
    import corporate_close_import as ledger_import
    targets=[r for r in rows(c,'SELECT * FROM cc_imports WHERE case_id=? AND deleted=0 ORDER BY id',(x['id'],))
             if json.loads(r['payload'] or '{}').get('amount_basis')!='debit_credit_v1']
    rebuilt=0
    with c:
        for item in targets:
            parsed=ledger_import.parse(item['name'],base64.b64decode(item['content']))
            old=rows(c,'SELECT * FROM cc_ledger_rows WHERE import_id=? ORDER BY id',(item['id'],))
            for index,r in enumerate(parsed):
                if index<len(old) and old[index].get('business')=='수동':
                    r['business']='수동';r['classification']=old[index].get('classification','')
            c.execute('DELETE FROM cc_ledger_rows WHERE import_id=?',(item['id'],))
            _insert_ledger_rows(c,item['id'],item['kind'],parsed)
            c.execute('UPDATE cc_imports SET payload=? WHERE id=?',(dump({'count':len(parsed),'amount_basis':'debit_credit_v1'}),item['id']))
            rebuilt+=1
    if rebuilt:apply_income_rules(c,x)
    return rebuilt
def ledger_rows(c,case_id,kind=None):
    sql="""SELECT r.*,CASE
      WHEN r.account LIKE '%영업외수익%' OR r.account LIKE '%잡이익%' OR r.account LIKE '%처분이익%' THEN '영업외수익'
      WHEN r.account LIKE '%영업외비용%' OR r.account LIKE '%잡손실%' OR r.account LIKE '%처분손실%' OR r.account LIKE '%이자비용%' OR r.account LIKE '%기부금%' THEN '영업외비용'
      ELSE i.kind END kind,i.name source_name
      FROM cc_ledger_rows r JOIN cc_imports i ON i.id=r.import_id
      WHERE i.case_id=? AND i.deleted=0 AND r.deleted=0""";args=[case_id]
    if kind:sql+=' AND i.kind=?';args.append(kind)
    return rows(c,sql+' ORDER BY r.id',args)
def classify_rows(c,x,changes):
    ensure_open(x)
    with c:
        for id,classification,business in changes:
            if classification not in ['','감면분','기타분']:raise ValueError('소득구분을 확인하세요.')
            c.execute('UPDATE cc_ledger_rows SET classification=?,business=? WHERE id=?',(classification,business or '수동',id))
def income_rules(c,company_id,include_deleted=False):
    out=rows(c,"SELECT * FROM cc_rules WHERE company_id=? ORDER BY CASE kind WHEN 'account' THEN 1 ELSE 2 END,id",(company_id,));return [r for r in out if include_deleted or not r['deleted']]
def save_income_rule(c,x,kind,keyword,id=None,expected=None):
    ensure_open(x);keyword=str(keyword).strip()
    if kind not in ['description','account'] or not keyword:raise ValueError('적요 문구와 적용 대상을 확인하세요.')
    with c:
        if id:
            old=c.execute('SELECT version FROM cc_rules WHERE id=? AND company_id=?',(id,x['company_id'])).fetchone()
            if not old or old[0]!=expected:raise ValueError('감면분 문구가 변경되었습니다. 다시 불러오세요.')
            c.execute("UPDATE cc_rules SET kind=?,keyword=?,classification='감면분',version=version+1,deleted=0 WHERE id=?",(kind,keyword,id))
        else:c.execute("INSERT INTO cc_rules(company_id,kind,keyword,classification) VALUES(?,?,?,'감면분')",(x['company_id'],kind,keyword))
    apply_income_rules(c,x)
def delete_income_rule(c,x,id,expected):
    ensure_open(x)
    with c:c.execute('UPDATE cc_rules SET deleted=1,version=version+1 WHERE id=? AND company_id=? AND version=?',(id,x['company_id'],expected))
    apply_income_rules(c,x)
def restore_income_rule(c,x,id,expected):
    ensure_open(x)
    with c:c.execute('UPDATE cc_rules SET deleted=0,version=version+1 WHERE id=? AND company_id=? AND version=?',(id,x['company_id'],expected))
    apply_income_rules(c,x)
def apply_income_rules(c,x):
    ensure_open(x);rules=income_rules(c,x['company_id']);rs=ledger_rows(c,x['id'])
    with c:
        for r in rs:
            # Only 잡이익 needs ledger-description classification.  Expense
            # exempt/other amounts are entered directly on the statement.
            if r['kind']!='영업외수익':continue
            if '잡이익' not in normalized(r['account']):
                if r.get('business')!='수동':c.execute("UPDATE cc_ledger_rows SET classification='',business='' WHERE id=?",(r['id'],))
                continue
            if r.get('business')=='수동':continue
            account=normalized(r['account']);description=normalized(r['description']);matched=''
            for rule in rules:
                needle=normalized(rule['keyword']);hay=account if rule['kind']=='account' else description
                if needle and needle in hay:matched=rule['keyword'];break
            c.execute('UPDATE cc_ledger_rows SET classification=?,business=? WHERE id=?',('감면분' if matched else '기타분',('자동:'+matched) if matched else '자동:기타분',r['id']))
def rule_recommendations(c,x):
    existing={normalized(r['keyword']) for r in income_rules(c,x['company_id'])};out=[]
    for keyword in RECOMMENDED_EXEMPT_KEYWORDS:
        if normalized(keyword) in existing:continue
        matches=[r for r in ledger_rows(c,x['id']) if r['kind']=='영업외수익' and '잡이익' in normalized(r['account']) and normalized(keyword) in normalized(r['description'])]
        if matches:out.append({'추천 문구':keyword,'발견 건수':len(matches),'합계금액':sum(r['amount'] for r in matches),'대표 적요':matches[0]['description']})
    return out

TAX_DUES_KINDS=['세금과공과(원가)','세금과공과(판관비)']
PREPAID_KINDS=['보험료(원가)','보험료(판관비)','지급임차료(원가)']
PROMOTION_KINDS=['접대비(신용카드등,원가)','접대비(경조사비,원가)','접대비(기타접대비,원가)','접대비(신용카드등,판관비)','접대비(경조사비,판관비)','접대비(기타접대비,판관비)']
STATEMENT_TOTAL_LABELS={'월계','누계'}
def is_statement_total_row(row):
    """Identify accounting-ledger monthly/cumulative subtotal rows."""
    for field in ['date','posting_date','account','description','counterparty','business']:
        value=normalized(row.get(field))
        if value in STATEMENT_TOTAL_LABELS or re.fullmatch(r'(?:\d{1,2}월?)?(?:월계|누계)(?:합계|금액)?',value or ''):return True
    return False
def filter_statement_rows(items):return [row for row in items if not is_statement_total_row(row)]
def statement_ledger_rows(c,case_id,kinds):return filter_statement_rows([r for r in ledger_rows(c,case_id) if r['kind'] in kinds])
def refresh_statement_projects(c,x,kinds,force=False):
    """Restore project names from stored source files without replacing row IDs."""
    import corporate_close_import as ledger_import
    placeholders=','.join('?' for _ in kinds);args=[x['id'],*kinds]
    targets=[]
    for item in rows(c,f'SELECT * FROM cc_imports WHERE case_id=? AND deleted=0 AND kind IN ({placeholders}) ORDER BY id',args):
        try:payload=json.loads(item.get('payload') or '{}')
        except (TypeError,ValueError):payload={}
        if force or payload.get('project_basis')!='project_alias_v3':targets.append(item)
    changed=0
    with c:
        for item in targets:
            parsed=ledger_import.parse(item['name'],base64.b64decode(item['content']));stored=rows(c,'SELECT * FROM cc_ledger_rows WHERE import_id=? AND deleted=0 ORDER BY id',(item['id'],));projects={};used={}
            for new in parsed:
                signature=(str(new.get('date') or ''),str(new.get('account') or ''),str(new.get('description') or ''),new.get('debit'),new.get('credit'),str(new.get('counterparty') or ''))
                projects.setdefault(signature,[]).append(str(new.get('business') or '').strip())
            for old in stored:
                signature=(str(old.get('posting_date') or ''),str(old.get('account') or ''),str(old.get('description') or ''),old.get('debit'),old.get('credit'),str(old.get('counterparty') or ''));index=used.get(signature,0);choices=projects.get(signature,[]);project=choices[index] if index<len(choices) else '';used[signature]=index+1
                if project and project!=str(old.get('business') or ''):c.execute('UPDATE cc_ledger_rows SET business=? WHERE id=?',(project,old['id']));changed+=1
            try:payload=json.loads(item.get('payload') or '{}')
            except (TypeError,ValueError):payload={}
            payload['project_basis']='project_alias_v3';c.execute('UPDATE cc_imports SET payload=? WHERE id=?',(dump(payload),item['id']))
    return changed
def statement_rules(c,company_id,statement='tax_dues',include_deleted=False):
    out=rows(c,'SELECT * FROM cc_statement_rules WHERE company_id=? AND statement=? ORDER BY id',(company_id,statement));return [r for r in out if include_deleted or not r['deleted']]
def apply_tax_dues_rules(c,x):
    ensure_open(x);rules=statement_rules(c,x['company_id']);rs=statement_ledger_rows(c,x['id'],TAX_DUES_KINDS)
    with c:
        for r in rs:
            if r.get('business')=='수동':continue
            description=normalized(r['description']);matched=next((z['keyword'] for z in rules if normalized(z['keyword']) in description),'')
            c.execute('UPDATE cc_ledger_rows SET classification=?,business=? WHERE id=?',('손금불산입' if matched else '손금산입',('자동:'+matched) if matched else '자동:해당없음',r['id']))
def save_statement_rule(c,x,keyword,id=None,expected=None):
    ensure_open(x);keyword=str(keyword).strip()
    if not keyword:raise ValueError('손금불산입 검색 문구를 입력하세요.')
    with c:
        if id:
            old=c.execute("SELECT version FROM cc_statement_rules WHERE id=? AND company_id=? AND statement='tax_dues'",(id,x['company_id'])).fetchone()
            if not old or old[0]!=expected:raise ValueError('검색 문구가 변경되었습니다. 다시 불러오세요.')
            c.execute("UPDATE cc_statement_rules SET keyword=?,version=version+1,deleted=0 WHERE id=?",(keyword,id))
        else:c.execute("INSERT INTO cc_statement_rules(company_id,statement,keyword) VALUES(?,'tax_dues',?)",(x['company_id'],keyword))
    apply_tax_dues_rules(c,x)
def delete_statement_rule(c,x,id,expected):
    ensure_open(x)
    with c:c.execute("UPDATE cc_statement_rules SET deleted=1,version=version+1 WHERE id=? AND company_id=? AND statement='tax_dues' AND version=?",(id,x['company_id'],expected))
    apply_tax_dues_rules(c,x)
def restore_statement_rule(c,x,id,expected):
    ensure_open(x)
    with c:c.execute("UPDATE cc_statement_rules SET deleted=0,version=version+1 WHERE id=? AND company_id=? AND statement='tax_dues' AND version=?",(id,x['company_id'],expected))
    apply_tax_dues_rules(c,x)
def save_statement_import(c,x,kind,name,content,parsed):
    if kind not in TAX_DUES_KINDS+PREPAID_KINDS+PROMOTION_KINDS:raise ValueError('명세서 원장 구분을 확인하세요.')
    iid=save_import(c,x,kind,name,content,filter_statement_rows(parsed))
    if kind in TAX_DUES_KINDS:apply_tax_dues_rules(c,x)
    return iid
def classify_tax_dues_rows(c,x,changes):
    ensure_open(x)
    with c:
        for id,classification in changes:
            if classification not in ['손금불산입','손금산입']:raise ValueError('세무조정 판정을 확인하세요.')
            c.execute("UPDATE cc_ledger_rows SET classification=?,business='수동' WHERE id=? AND import_id IN (SELECT id FROM cc_imports WHERE case_id=? AND kind IN ('세금과공과(원가)','세금과공과(판관비)'))",(classification,id,x['id']))
def sync_tax_dues_adjustments(c,x):
    ensure_open(x);rs=[r for r in statement_ledger_rows(c,x['id'],TAX_DUES_KINDS) if r['classification']=='손금불산입'];changed=[]
    with c:
        for kind,target in [('세금과공과(원가)','원가'),('세금과공과(판관비)','판관비')]:
            amount=sum((r['debit'] if r['debit'] is not None else r['amount']) for r in rs if r['kind']==kind);key='statement:tax_dues:'+('cost' if target=='원가' else 'sga')
            c.execute('''INSERT INTO cc_adjustments(case_id,side,name,amount,target,cost_amount,account_group,note,source_key,deleted)
              VALUES(?,'add',?,?,?,0,'원가','세금과공과명세서 자동 연계',?,?)
              ON CONFLICT(case_id,source_key) DO UPDATE SET amount=excluded.amount,name=excluded.name,target=excluded.target,note=excluded.note,deleted=excluded.deleted,version=cc_adjustments.version+1''',(x['id'],kind,amount,target,key,int(amount==0)));changed.append(kind)
    sync_all_reserves(c,x,changed)
def sync_prepaid_adjustments(c,x,summary):
    ensure_open(x);changed=[]
    with c:
        for kind in PREPAID_KINDS:
            target='판관비' if kind=='보험료(판관비)' else '원가';name='선급비용('+kind.replace('보험료(','보험료·').replace('지급임차료(','지급임차료·').rstrip(')')+')'
            for side,field in [('add','ending'),('deduct','opening')]:
                amount=calc.won(summary.get(kind,{}).get(field,0));key=f'statement:prepaid:{kind}:{side}'
                c.execute('''INSERT INTO cc_adjustments(case_id,side,name,amount,target,cost_amount,account_group,note,source_key,deleted)
                  VALUES(?,?,?,?,?,0,'원가','선급비용명세서 자동 연계',?,?)
                  ON CONFLICT(case_id,source_key) DO UPDATE SET amount=excluded.amount,name=excluded.name,target=excluded.target,note=excluded.note,deleted=excluded.deleted,version=cc_adjustments.version+1''',(x['id'],side,name,amount,target,key,int(amount==0)));changed.append(name)
    sync_all_reserves(c,x,changed)
def delete_import(c,x,id):
    ensure_open(x)
    with c:c.execute('UPDATE cc_imports SET deleted=1 WHERE id=? AND case_id=?',(id,x['id']))
def restore_import(c,x,id):
    ensure_open(x)
    with c:c.execute('UPDATE cc_imports SET deleted=0 WHERE id=? AND case_id=?',(id,x['id']))

def progress_imports(c,case_id,include_deleted=False):
    out=rows(c,'SELECT id,name,sheet_name,digest,created_at,deleted FROM cc_progress_imports WHERE case_id=? ORDER BY id DESC',(case_id,));return [r for r in out if include_deleted or not r['deleted']]
def progress_projects(c,case_id,include_deleted=False):
    out=rows(c,'SELECT * FROM cc_progress_projects WHERE case_id=? ORDER BY deleted,source_row,id',(case_id,));return [r for r in out if include_deleted or not r['deleted']]
def save_progress_import(c,x,name,sheet_name,content,projects):
    ensure_open(x);digest=hashlib.sha256(content).hexdigest()
    if len(content)>20*1024*1024:raise ValueError('공사수입·원가대비 파일은 20MB 이하만 등록할 수 있습니다.')
    if c.execute('SELECT 1 FROM cc_progress_imports WHERE case_id=? AND digest=?',(x['id'],digest)).fetchone():raise ValueError('같은 공사수입·원가대비 파일이 이미 등록되어 있습니다.')
    with c:
        c.execute('UPDATE cc_progress_imports SET deleted=1 WHERE case_id=? AND deleted=0',(x['id'],))
        iid=c.execute('INSERT INTO cc_progress_imports(case_id,name,sheet_name,digest,content) VALUES(?,?,?,?,?)',(x['id'],name,sheet_name,digest,base64.b64encode(content).decode())).lastrowid
        c.execute('UPDATE cc_progress_projects SET import_missing=1,version=version+1 WHERE case_id=? AND deleted=0 AND import_id IS NOT NULL',(x['id'],))
        base_fields=['source_row','client','project','start','end','contract','prior_revenue','current_revenue','prior_cost','current_cost','expected_cost_rate','trade','status','prior_adjustment','current_adjustment','prior_unfinished','current_unfinished','note']
        text_fields={'client','project','start','end','trade','status','note'}
        for p in projects:
            key=str(p.get('project_key') or '|'.join([normalized(p.get('client')),normalized(p.get('project')),normalized(p.get('start'))]))
            existing=c.execute('SELECT id,allocation_mode FROM cc_progress_projects WHERE case_id=? AND project_key=? ORDER BY deleted,id LIMIT 1',(x['id'],key)).fetchone()
            values=[p.get(k,'' if k in text_fields else 0) for k in base_fields]
            carry=int(p.get('carryover_eligible',0 if '준공' in normalized(p.get('status')) else 1))
            if existing:
                clear_allocation=',allocated_adjustment=NULL' if existing[1]!='fixed' else ''
                c.execute('UPDATE cc_progress_projects SET import_id=?,'+','.join(k+'=?' for k in base_fields)+',project_key=?,carryover_eligible=?,import_missing=0,deleted=0,version=version+1'+clear_allocation+' WHERE id=?',(iid,*values,key,carry,existing[0]))
            else:
                c.execute('INSERT INTO cc_progress_projects(case_id,import_id,'+','.join(base_fields)+',project_key,allocation_mode,allocated_adjustment,carryover_eligible,import_missing) VALUES(?,?,'+','.join('?' for _ in base_fields)+',?,?,?,?,0)',(x['id'],iid,*values,key,p.get('allocation_mode','auto'),p.get('allocated_adjustment'),carry))
    return iid
def save_progress_project(c,x,id,expected,values):
    ensure_open(x);row=c.execute('SELECT version FROM cc_progress_projects WHERE id=? AND case_id=?',(id,x['id'])).fetchone()
    if not row or row[0]!=expected:raise ValueError('현장 자료가 변경되었습니다. 다시 불러오세요.')
    fields=['client','project','start','end','contract','prior_revenue','current_revenue','prior_cost','current_cost','expected_cost_rate','trade','status','prior_adjustment','current_adjustment','prior_unfinished','current_unfinished','note','allocation_mode','allocated_adjustment','carryover_eligible','carryover_note'];text_fields={'client','project','start','end','trade','status','note','allocation_mode','carryover_note'}
    with c:c.execute('UPDATE cc_progress_projects SET '+','.join(k+'=?' for k in fields)+',version=version+1,deleted=0 WHERE id=?',(*[values.get(k,'' if k in text_fields else 0) for k in fields],id))
def add_progress_project(c,x,values):
    ensure_open(x);fields=['client','project','start','end','contract','prior_revenue','current_revenue','prior_cost','current_cost','expected_cost_rate','trade','status','prior_adjustment','current_adjustment','prior_unfinished','current_unfinished','note','allocation_mode','allocated_adjustment','carryover_eligible','carryover_note']
    key=str(values.get('project_key') or '|'.join([normalized(values.get('client')),normalized(values.get('project')),normalized(values.get('start'))]))
    if c.execute('SELECT 1 FROM cc_progress_projects WHERE case_id=? AND project_key=? AND deleted=0',(x['id'],key)).fetchone():raise ValueError('같은 공사관리번호의 현장이 이미 있습니다.')
    text_fields={'client','project','start','end','trade','status','note','allocation_mode','carryover_note'}
    with c:return c.execute('INSERT INTO cc_progress_projects(case_id,project_key,'+','.join(fields)+') VALUES(?,?,'+','.join('?' for _ in fields)+')',(x['id'],key,*[values.get(k,'' if k in text_fields else 0) for k in fields])).lastrowid
def save_progress_allocations(c,x,allocations):
    ensure_open(x)
    with c:
        for id,amount in allocations.items():c.execute('UPDATE cc_progress_projects SET allocated_adjustment=?,version=version+1 WHERE id=? AND case_id=? AND deleted=0',(int(amount),int(id),x['id']))
def carryover_progress_projects(c,x,next_case):
    if x['status']!='confirmed':raise ValueError('당해 법인결산을 확정한 뒤 차기 이월하세요.')
    ensure_open(next_case);source=progress_projects(c,x['id']);carried=0;excluded=0
    with c:
        for row in source:
            if not row.get('carryover_eligible') or '준공' in normalized(row.get('status')):excluded+=1;continue
            key=row.get('project_key') or '|'.join([normalized(row.get('client')),normalized(row.get('project')),normalized(row.get('start'))])
            final=progress.final_adjustment(row)
            values=(row['client'],row['project'],row['start'],row['end'],row['contract'],int(row['prior_revenue'])+int(row['current_revenue']),0,int(row['prior_cost'])+int(row['current_cost']),0,row['expected_cost_rate'],row['trade'],'진행중',int(final or 0),0,0,0,row.get('note',''),'auto',None,1,row.get('carryover_note',''))
            existing=c.execute('SELECT id FROM cc_progress_projects WHERE case_id=? AND project_key=?',(next_case['id'],key)).fetchone()
            fields=['client','project','start','end','contract','prior_revenue','current_revenue','prior_cost','current_cost','expected_cost_rate','trade','status','prior_adjustment','current_adjustment','prior_unfinished','current_unfinished','note','allocation_mode','allocated_adjustment','carryover_eligible','carryover_note']
            if existing:c.execute('UPDATE cc_progress_projects SET '+','.join(k+'=?' for k in fields)+',import_missing=0,deleted=0,version=version+1 WHERE id=?',(*values,existing[0]))
            else:c.execute('INSERT INTO cc_progress_projects(case_id,project_key,'+','.join(fields)+') VALUES(?,?,'+','.join('?' for _ in fields)+')',(next_case['id'],key,*values))
            carried+=1
    return {'carried':carried,'excluded':excluded}
def delete_progress_project(c,x,id,expected,reason):
    ensure_open(x)
    if not str(reason).strip():raise ValueError('삭제 사유를 입력하세요.')
    with c:c.execute('UPDATE cc_progress_projects SET deleted=1,note=note||?,version=version+1 WHERE id=? AND case_id=? AND version=?',('\n삭제: '+reason,id,x['id'],expected))
def restore_progress_project(c,x,id,expected):
    ensure_open(x)
    with c:c.execute('UPDATE cc_progress_projects SET deleted=0,version=version+1 WHERE id=? AND case_id=? AND version=?',(id,x['id'],expected))
def delete_progress_import(c,x,id):
    ensure_open(x)
    with c:c.execute('UPDATE cc_progress_imports SET deleted=1 WHERE id=? AND case_id=?',(id,x['id']))
def restore_progress_import(c,x,id):
    ensure_open(x)
    with c:c.execute('UPDATE cc_progress_imports SET deleted=0 WHERE id=? AND case_id=?',(id,x['id']))
