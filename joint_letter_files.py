"""Scoped letter drafts and self-contained attachment snapshots."""
import base64,hashlib,json,mimetypes,zipfile,re
from pathlib import PurePosixPath
from io import BytesIO
import joint_store as db

EXT={'pdf':'application/pdf','png':'image/png','jpg':'image/jpeg','jpeg':'image/jpeg','xlsx':'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet','xls':'application/vnd.ms-excel','docx':'application/vnd.openxmlformats-officedocument.wordprocessingml.document','doc':'application/msword','hwp':'application/x-hwp','hwpx':'application/haansofthwpx','txt':'text/plain'}
LIMIT=10*1024*1024;TOTAL=20*1024*1024

def install(c):
 c.execute('''CREATE TABLE IF NOT EXISTS jv_letter_files(id INTEGER PRIMARY KEY,project_id INTEGER NOT NULL REFERENCES jv_projects(id),member_id INTEGER NOT NULL REFERENCES jv_members(id),month TEXT NOT NULL,name TEXT NOT NULL,mime TEXT NOT NULL,content TEXT NOT NULL,digest TEXT NOT NULL,size INTEGER NOT NULL,version INTEGER NOT NULL DEFAULT 1,deleted INTEGER NOT NULL DEFAULT 0)''')

def scope(c,p,m,month):
 if m not in [r['id'] for r in db.members(c,p)]:raise ValueError('해당 공사의 수신 회원사를 확인하세요.')
 return db.period(month)
def name(value):
 value=str(value).replace('\\','/').split('/')[-1].strip()
 value=re.sub(r'[<>:"|?*]','_',value).rstrip(' .')
 if value.split('.')[0].upper() in {'CON','PRN','AUX','NUL',*[f'COM{i}' for i in range(1,10)],*[f'LPT{i}' for i in range(1,10)]}:value='_'+value
 if not value or len(value)>150 or any(ord(c)<32 for c in value):raise ValueError('첨부 파일명을 확인하세요.')
 if value.rsplit('.',1)[-1].lower() not in EXT:raise ValueError('PDF·이미지·엑셀·한글·워드·텍스트 파일을 선택하세요.')
 return value

def packed(filename,blob):
 filename=name(filename);ext=filename.rsplit('.',1)[-1].lower();blob=bytes(blob)
 if not blob or len(blob)>LIMIT:raise ValueError('첨부는 파일당 10MB 이하의 빈 파일이 아닌 자료를 선택하세요.')
 if ext=='pdf' and not blob.startswith(b'%PDF-'):raise ValueError('PDF 파일 내용을 확인하세요.')
 if ext in ['png','jpg','jpeg']:
  from PIL import Image
  try:
   with Image.open(BytesIO(blob)) as image:
    if image.format!=('PNG' if ext=='png' else 'JPEG'):raise ValueError()
    image.verify()
  except Exception:raise ValueError('첨부 이미지 내용을 확인하세요.')
 if ext in ['xlsx','docx','hwpx'] and not zipfile.is_zipfile(BytesIO(blob)):raise ValueError('문서 파일 내용을 확인하세요.')
 if ext in ['xls','doc','hwp'] and not blob.startswith(b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1'):raise ValueError('문서 파일 내용을 확인하세요.')
 if blob.startswith(b'MZ'):raise ValueError('실행 파일은 첨부할 수 없습니다.')
 if ext=='txt':
  try:blob.decode('utf-8')
  except UnicodeDecodeError:
   try:blob.decode('cp949')
   except UnicodeDecodeError:raise ValueError('텍스트 파일 인코딩을 확인하세요.')
 return dict(name=filename,mime=EXT[ext],content=base64.b64encode(blob).decode(),digest=hashlib.sha256(blob).hexdigest(),size=len(blob))
def unpack(row):
 try:blob=base64.b64decode(row['content'],validate=True)
 except Exception:raise ValueError('첨부자료가 손상되었습니다.')
 if hashlib.sha256(blob).hexdigest()!=row.get('digest'):raise ValueError('첨부자료 무결성을 확인할 수 없습니다.')
 return blob

def files(c,p,m,month,deleted=False):
 scope(c,p,m,month)
 return db.rows(c,'SELECT * FROM jv_letter_files WHERE project_id=? AND member_id=? AND month=? AND deleted=? ORDER BY id',(p,m,month,int(deleted)))
def save(c,p,m,month,uploads,id=None,version=None):
 scope(c,p,m,month);items=[packed(n,b) for n,b in uploads];existing=files(c,p,m,month)
 old=next((r for r in existing if r['id']==id),None)
 if id and (not old or old['version']!=version or len(items)!=1):raise ValueError('교체할 첨부를 다시 선택하고 파일 한 개를 올리세요.')
 if not id:
  unique={}
  for item in items:
   if not any(r['name']==item['name'] and r['digest']==item['digest'] for r in existing):unique[(item['name'],item['digest'])]=item
  items=list(unique.values())
 if sum(r['size'] for r in existing if r['id']!=id)+sum(r['size'] for r in items)>TOTAL:raise ValueError('공문별 첨부 합계는 20MB 이하로 등록하세요.')
 with c:
  for item in items:
   if id:c.execute('UPDATE jv_letter_files SET name=?,mime=?,content=?,digest=?,size=?,version=version+1 WHERE id=?',tuple(item[k] for k in ['name','mime','content','digest','size'])+(id,))
   elif not any(r['name']==item['name'] and r['digest']==item['digest'] for r in existing):
    c.execute('INSERT INTO jv_letter_files(project_id,member_id,month,name,mime,content,digest,size) VALUES(?,?,?,?,?,?,?,?)',(p,m,month,*[item[k] for k in ['name','mime','content','digest','size']]))
def edit(c,p,m,month,id,version,filename=None,deleted=None):
 row=next((r for r in files(c,p,m,month,deleted=not deleted if deleted is not None else False) if r['id']==id),None)
 if not row or row['version']!=version:raise ValueError('첨부가 변경되었습니다. 다시 불러오세요.')
 if deleted is False and sum(r['size'] for r in files(c,p,m,month))+row['size']>TOTAL:raise ValueError('복구 후 첨부 합계가 20MB를 초과합니다.')
 if filename is not None and filename.rsplit('.',1)[-1].lower()!=row['name'].rsplit('.',1)[-1].lower():raise ValueError('파일 확장자는 유지하세요.')
 with c:c.execute('UPDATE jv_letter_files SET name=?,deleted=?,version=version+1 WHERE id=?',(name(filename) if filename is not None else row['name'],int(deleted) if deleted is not None else row['deleted'],id))

def with_files(c,p,m,month,meta):
 return dict(meta,uploaded_files=[{k:r[k] for k in ['id','name','mime','content','digest','size']} for r in files(c,p,m,month)])
def bundle(data,meta=None):
 from joint_report import render
 meta=meta or data.get('meta',{});out=BytesIO()
 with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
  z.writestr('공문_원장_미리보기.html',render(data,'공문',meta).encode('utf-8'))
  for i,row in enumerate(meta.get('uploaded_files',[]),1):z.writestr('추가서류/'+str(i)+'_'+name(row['name']),unpack(row))
 return out.getvalue()
