"""Company/month survey drafts, immutable print editions and manual fax records."""
from datetime import date,datetime,timezone,timedelta
import base64,json,hashlib
import collaboration as shared

ITEMS=[('staff','인력사정','해당월 수준',['과잉','적정','부족']),('sales','매출규모','전년 동월 대비',['확대','비슷','둔화']),('profit','채산성','전월 대비',['호전','비슷','악화']),('funds','자금사정','전월 대비',['호전','비슷','악화']),('business','업황','귀사의 업황 · 계절요인 제외',['좋음','보통','나쁨'])]
FACTORS=['수출부진','내수부진','인력난·인건비상승','노사분규','생산설비노후','자금부족','경쟁심화','불확실한 경제상황','원자재가격(유가포함) 상승','정부규제','환율','비수기 등 계절적 요인','기타','없음']
FIELDS={'name':'기업체명','phone':'전화번호','address':'주소','factory':'주공장 소재지(시·도)','product1':'주요제품·상품 ①','product2':'주요제품·상품 ②','export_ratio':'매출액 중 수출비중(%)','employees':'상시 종업원수(명)','author':'작성자','email':'이메일','department':'부서','position':'직위','fax':'수신 팩스번호'}

def today():return datetime.now(timezone(timedelta(hours=9))).date()
def korean_time(value):
 return (datetime.fromisoformat(value).replace(tzinfo=timezone.utc).astimezone(timezone(timedelta(hours=9)))).strftime('%Y-%m-%d %H:%M')

def rows(c,sql,args=()):
 cur=c.execute(sql,args);return [dict(zip([x[0] for x in cur.description],r)) for r in cur]
def month(value):
 value=str(value)
 try:
  parsed=date.fromisoformat(value+'-01')
  if parsed.strftime('%Y-%m')!=value:raise ValueError
 except ValueError:raise ValueError('조사월은 YYYY-MM 형식으로 입력하세요.')
 return value
def next_month(value):
 d=date.fromisoformat(month(value)+'-01');return f'{d.year+(d.month==12):04d}-{d.month%12+1:02d}'
def connect():
 shared.DATA.mkdir(parents=True,exist_ok=True);c=shared.connect(shared.DATA/'business_survey.db')
 c.executescript('''CREATE TABLE IF NOT EXISTS bs_companies(id INTEGER PRIMARY KEY,name TEXT UNIQUE NOT NULL,profile TEXT NOT NULL);
 CREATE TABLE IF NOT EXISTS bs_surveys(id INTEGER PRIMARY KEY,company_id INTEGER NOT NULL REFERENCES bs_companies(id),month TEXT NOT NULL,payload TEXT NOT NULL,updated_at TEXT DEFAULT CURRENT_TIMESTAMP,UNIQUE(company_id,month));
 CREATE TABLE IF NOT EXISTS bs_documents(id INTEGER PRIMARY KEY,survey_id INTEGER NOT NULL REFERENCES bs_surveys(id),snapshot TEXT NOT NULL,pdf TEXT NOT NULL,digest TEXT NOT NULL,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
 CREATE TABLE IF NOT EXISTS bs_faxes(id INTEGER PRIMARY KEY,document_id INTEGER NOT NULL REFERENCES bs_documents(id),sent_date TEXT NOT NULL,recipient TEXT NOT NULL,note TEXT NOT NULL,created_at TEXT DEFAULT CURRENT_TIMESTAMP);''')
 c=shared.protect(c)
 with c:
  for id,name in enumerate(['(주)효성','다혜건설(주)'],1):
   if not c.execute('SELECT id FROM bs_companies WHERE id=?',(id,)).fetchone():
    c.execute('INSERT INTO bs_companies(id,name,profile) VALUES(?,?,?)',(id,name,json.dumps({'name':name,'fax':'033-640-0165'},ensure_ascii=False)))
 return c

def companies(c):return rows(c,'SELECT * FROM bs_companies ORDER BY id')
def company(c,id):
 r=c.execute('SELECT profile FROM bs_companies WHERE id=?',(id,)).fetchone()
 if not r:raise ValueError('회사를 확인하세요.')
 return json.loads(r[0])
def profile(c,id,values):
 values={k:str(values.get(k,'')).strip() for k in FIELDS}
 if not values['name']:raise ValueError('기업체명을 입력하세요.')
 if c.execute('SELECT id FROM bs_companies WHERE name=? AND id<>?',(values['name'],id)).fetchone():raise ValueError('다른 회사와 같은 기업체명을 사용할 수 없습니다.')
 for k,limit in [('employees',10000000),('export_ratio',100)]:
  if values[k]:
   try:
    from decimal import Decimal
    n=Decimal(values[k].replace(',',''))
    if not n.is_finite() or not 0<=n<=limit or k=='employees' and n!=int(n):raise ValueError
   except Exception:raise ValueError(FIELDS[k]+'를 확인하세요.')
   values[k]=format(n,'f')
 for k,v in values.items():
  if len(v)>({'address':130,'product1':65,'product2':65,'email':80}.get(k,45)):raise ValueError(FIELDS[k]+'가 너무 깁니다. 출력 칸에 맞게 줄여주세요.')
 with c:c.execute('UPDATE bs_companies SET name=?,profile=? WHERE id=?',(values['name'],json.dumps(values,ensure_ascii=False),id))
def draft(c,company_id,period):
 r=c.execute('SELECT id,payload FROM bs_surveys WHERE company_id=? AND month=?',(company_id,month(period))).fetchone()
 return (r[0],json.loads(r[1])) if r else (None,{})
def validate(payload,complete=False):
 p=dict(payload);month(p['month']);date.fromisoformat(p['written'])
 for k,_,_,options in ITEMS:
  for side in ['now','next']:
   v=p.get(side,{}).get(k)
   if v is not None and v not in options:raise ValueError('응답을 확인하세요.')
   if complete and v is None:raise ValueError('당월 동향과 다음 달 전망의 모든 항목을 선택하세요.')
 factor=p.get('factor')
 if factor is not None and (type(factor)!=int or not 1<=factor<=14):raise ValueError('경영애로사항을 확인하세요.')
 if complete and factor is None:raise ValueError('경영애로사항을 1개 선택하세요.')
 if factor==13 and complete and not str(p.get('other','')).strip():raise ValueError('기타 경영애로사항의 내용을 입력하세요.')
 if len(str(p.get('other','')))>18:raise ValueError('기타 내용은 출력 칸에 맞게 18자 이내로 입력하세요.')
 if complete and any(not p['profile'].get(k,'').strip() for k in ['name','phone','author']):raise ValueError('회사 기본정보의 기업체명·전화번호·작성자를 먼저 입력하세요.')
 return p
def save(c,company_id,period,payload):
 period=month(period);payload=dict(payload,month=period);validate(payload)
 payload['profile']=company(c,company_id)
 with c:c.execute('INSERT INTO bs_surveys(company_id,month,payload) VALUES(?,?,?) ON CONFLICT(company_id,month) DO UPDATE SET payload=excluded.payload,updated_at=CURRENT_TIMESTAMP',(company_id,period,json.dumps(payload,ensure_ascii=False)))
 return draft(c,company_id,period)[0]
def issue(c,survey_id):
 r=c.execute('SELECT payload FROM bs_surveys WHERE id=?',(survey_id,)).fetchone()
 if not r:raise ValueError('조사표를 먼저 저장하세요.')
 p=validate(json.loads(r[0]),True)
 from survey_report import pdf
 content=pdf([p]);digest=hashlib.sha256(content).hexdigest()
 with c:
  cur=c.execute('INSERT INTO bs_documents(survey_id,snapshot,pdf,digest) VALUES(?,?,?,?)',(survey_id,json.dumps(p,ensure_ascii=False),base64.b64encode(content).decode(),digest))
 return cur.lastrowid

def status(c,survey_id):
 current=c.execute('SELECT payload FROM bs_surveys WHERE id=?',(survey_id,)).fetchone()
 latest=c.execute('SELECT id,snapshot FROM bs_documents WHERE survey_id=? ORDER BY id DESC LIMIT 1',(survey_id,)).fetchone()
 if not latest:return '작성 중'
 if json.loads(current[0])!=json.loads(latest[1]):return '수정 후 재출력 필요'
 return '발송 기록 있음' if c.execute('SELECT 1 FROM bs_faxes WHERE document_id=?',(latest[0],)).fetchone() else '출력본 보관'

def document(c,id):
 r=rows(c,'SELECT * FROM bs_documents WHERE id=?',(id,))
 if not r:raise ValueError('출력본을 확인하세요.')
 return r[0]
def document_pdf(c,id):
 r=document(c,id);content=base64.b64decode(r['pdf'],validate=True)
 if hashlib.sha256(content).hexdigest()!=r['digest']:raise ValueError('출력본의 무결성이 맞지 않습니다.')
 return content
def record_fax(c,id,sent_date,recipient,note):
 document(c,id);date.fromisoformat(str(sent_date));recipient=str(recipient).strip()
 if not recipient:raise ValueError('실제 수신 팩스번호를 입력하세요.')
 if date.fromisoformat(str(sent_date))>today():raise ValueError('미래 날짜를 발송일로 기록할 수 없습니다.')
 with c:c.execute('INSERT INTO bs_faxes(document_id,sent_date,recipient,note) VALUES(?,?,?,?)',(id,str(sent_date),recipient,str(note)))
