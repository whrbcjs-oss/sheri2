"""One visible final letter per project/member/month; recoverable prior contents."""
import json,base64
from io import BytesIO
import joint_store as db

def install(c):
 c.executescript('''CREATE TABLE IF NOT EXISTS jv_letter_hidden(document_id INTEGER PRIMARY KEY REFERENCES jv_documents(id),reason TEXT NOT NULL);
 CREATE TABLE IF NOT EXISTS jv_letter_recovery(id INTEGER PRIMARY KEY,project_id INTEGER NOT NULL,member_id INTEGER NOT NULL,month TEXT NOT NULL,document_id INTEGER NOT NULL,payload TEXT NOT NULL,reason TEXT NOT NULL,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
 CREATE TABLE IF NOT EXISTS jv_company_seals(company_id INTEGER PRIMARY KEY REFERENCES jv_companies(id),seal TEXT NOT NULL);''')
def letters(c,p,m,month):
 db.period(month)
 result=[]
 for r in db.rows(c,"SELECT * FROM jv_documents WHERE project_id=? AND member_id=? AND kind='공문' AND id NOT IN (SELECT document_id FROM jv_letter_hidden) ORDER BY id DESC",(p,m)):
  d=json.loads(r['snapshot'])
  if d.get('investment_letter') and d['start']==month and d['end']==month:result.append(dict(r,data=d))
 return result

def visible(c,p):
 seen=set();out=[]
 for r in db.rows(c,'SELECT * FROM jv_documents WHERE project_id=? AND id NOT IN (SELECT document_id FROM jv_letter_hidden) ORDER BY id DESC',(p,)):
  d=json.loads(r['snapshot'])
  if r['kind']=='공문' and d.get('investment_letter'):
   key=(r['member_id'],d['start'],d['end'])
   if key in seen:continue
   seen.add(key)
  out.append(r)
 return out

def check(c,p,m,month,expected):
 rows=letters(c,p,m,month)
 if [(r['id'],r['snapshot']) for r in rows]!=expected:raise ValueError('공문이 변경되었습니다. 새로 조회하세요.')
 return rows

def retain(c,row,month,reason):
 c.execute('INSERT INTO jv_letter_recovery(project_id,member_id,month,document_id,payload,reason) VALUES(?,?,?,?,?,?)',(row['project_id'],row['member_id'],month,row['id'],row['snapshot'],reason))

def save(c,data,number,issued,meta,expected):
 p=data['project']['id'];m=data['member']['id'];month=data['start'];db.period(month)
 if not data.get('investment_letter') or data['end']!=month:raise ValueError('당사 투입비 통보월을 확인하세요.')
 if not data.get('investment_rows'):raise ValueError('해당 통보월 원장을 먼저 등록하세요.')
 if not number.strip():raise ValueError('문서번호를 입력하세요.')
 payload=dict(data,meta=meta,kind='공문',number=number.strip(),issued=db.day(issued))
 with c:
  c.execute('DELETE FROM jv_letter_hidden WHERE document_id=-1')
  rows=check(c,p,m,month,expected)
  if len(rows)>1:raise ValueError('기존 중복 공문을 먼저 정리하세요.')
  if rows:
   row=rows[0]
   if c.execute('SELECT 1 FROM jv_documents WHERE number=? AND id<>?',(number.strip(),row['id'])).fetchone():raise ValueError('이미 사용한 문서번호입니다.')
   retain(c,row,month,'갱신 전 공문')
   c.execute('UPDATE jv_documents SET number=?,issued=?,snapshot=? WHERE id=?',(number.strip(),db.day(issued),json.dumps(payload,ensure_ascii=False),row['id']))
  else:db.snapshot(c,data,'공문',number,issued,meta)
 return payload

def remove(c,p,m,month,expected,keep=None,reason='삭제'):
 if not reason.strip():raise ValueError('삭제 사유를 입력하세요.')
 with c:
  c.execute('DELETE FROM jv_letter_hidden WHERE document_id=-1');rows=check(c,p,m,month,expected)
  if keep is not None and keep not in [r['id'] for r in rows]:raise ValueError('남길 공문을 확인하세요.')
  for r in rows:
   if r['id']==keep:continue
   retain(c,r,month,reason);c.execute('INSERT INTO jv_letter_hidden VALUES(?,?)',(r['id'],reason))

def recovery(c,p,m,month):return db.rows(c,'SELECT * FROM jv_letter_recovery WHERE project_id=? AND member_id=? AND month=? ORDER BY id DESC',(p,m,month))
def restore(c,p,m,month,id,expected):
 row=next((r for r in recovery(c,p,m,month) if r['id']==id),None)
 if not row:raise ValueError('복구할 공문을 확인하세요.')
 d=json.loads(row['payload'])
 with c:
  c.execute('DELETE FROM jv_letter_hidden WHERE document_id=-1');active=check(c,p,m,month,expected)
  if len(active)>1:raise ValueError('중복 공문을 먼저 정리하세요.')
  for r in active:
   retain(c,r,month,'복구 전 최종 공문');c.execute('INSERT OR REPLACE INTO jv_letter_hidden VALUES(?,?)',(r['id'],'복구로 교체'))
  target=row['document_id']
  if c.execute('SELECT 1 FROM jv_documents WHERE number=? AND id<>?',(d['number'],target)).fetchone():raise ValueError('다른 공문에서 사용 중인 문서번호입니다.')
  c.execute('UPDATE jv_documents SET snapshot=?,number=?,issued=? WHERE id=?',(row['payload'],d['number'],d['issued'],target));c.execute('DELETE FROM jv_letter_hidden WHERE document_id=?',(target,))
  c.execute('DELETE FROM jv_letter_recovery WHERE id=?',(id,))

def seal(c,company):
 r=c.execute('SELECT seal FROM jv_company_seals WHERE company_id=?',(company,)).fetchone()
 if r:return r[0]
 # Reuse a seal already embedded in this sender company's latest letter.
 for r in db.rows(c,"SELECT snapshot FROM jv_documents WHERE kind='공문' ORDER BY id DESC"):
  d=json.loads(r['snapshot'])
  if d.get('project',{}).get('owner_id')==company and d.get('meta',{}).get('seal'):return d['meta']['seal']
 return ''
def save_seal(c,company,blob=None):
 if company not in [r['id'] for r in db.companies(c)]:raise ValueError('발신 회사를 확인하세요.')
 value=''
 if blob is not None:
  from PIL import Image
  if not blob or len(blob)>1024*1024:raise ValueError('직인은 1MB 이하 PNG/JPG를 선택하세요.')
  try:
   with Image.open(BytesIO(blob)) as im:
    fmt=im.format;im.verify()
   if fmt not in ['PNG','JPEG']:raise ValueError()
  except Exception:raise ValueError('정상 PNG/JPG 이미지를 선택하세요.')
  value='data:image/'+('png' if fmt=='PNG' else 'jpeg')+';base64,'+base64.b64encode(blob).decode()
 with c:c.execute('INSERT OR REPLACE INTO jv_company_seals VALUES(?,?)',(company,value))
 return value
