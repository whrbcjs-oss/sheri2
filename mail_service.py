"""Private SMTP settings and explicitly confirmed, idempotent outgoing jobs."""
import base64,ctypes,hashlib,imaplib,json,os,re,secrets,smtplib,socket,sqlite3,ssl
from contextlib import closing
from datetime import datetime,timezone,timedelta
from email.message import EmailMessage
from email import message_from_bytes
from email.header import decode_header
from email.policy import SMTP
from email.utils import format_datetime,make_msgid,formataddr,parsedate_to_datetime
from pathlib import Path
import collaboration as shared

LIMIT=18*1024*1024
DEFAULTS=dict(host='smtp.mail.nate.com',port=465,security='SSL',sender='',name='',username='')

def actor(token,admin=False):
 user=shared.require_admin(token) if admin else shared.validate_session(token)
 if not user:raise PermissionError('다시 로그인하세요.')
 return user

def database():
 shared.STATE.mkdir(parents=True,exist_ok=True,mode=0o700)
 path=shared.STATE/'mail.db';c=sqlite3.connect(path,timeout=30);c.row_factory=sqlite3.Row
 c.executescript('''CREATE TABLE IF NOT EXISTS settings(id INTEGER PRIMARY KEY CHECK(id=1),payload TEXT NOT NULL,secret TEXT NOT NULL,version TEXT NOT NULL);
 CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,actor TEXT NOT NULL,scope TEXT NOT NULL,source TEXT NOT NULL,fingerprint TEXT NOT NULL,config_version TEXT NOT NULL,payload TEXT NOT NULL,eml BLOB NOT NULL,status TEXT NOT NULL,detail TEXT NOT NULL DEFAULT '',created_at TEXT DEFAULT CURRENT_TIMESTAMP,updated_at TEXT DEFAULT CURRENT_TIMESTAMP);
 CREATE INDEX IF NOT EXISTS job_scope ON jobs(scope,created_at);
 CREATE TABLE IF NOT EXISTS drafts(actor TEXT NOT NULL,scope TEXT NOT NULL,payload TEXT NOT NULL,PRIMARY KEY(actor,scope));''')
 try:os.chmod(path,0o600)
 except OSError:pass
 return c

def _protect(blob,decrypt=False):
 if os.name=='nt':
  from ctypes import wintypes
  class DATA(ctypes.Structure):_fields_=[('size',wintypes.DWORD),('data',ctypes.POINTER(ctypes.c_char))]
  buf=ctypes.create_string_buffer(blob);src=DATA(len(blob),ctypes.cast(buf,ctypes.POINTER(ctypes.c_char)));out=DATA()
  if decrypt:ok=ctypes.windll.crypt32.CryptUnprotectData(ctypes.byref(src),None,None,None,None,1,ctypes.byref(out))
  else:ok=ctypes.windll.crypt32.CryptProtectData(ctypes.byref(src),ctypes.c_wchar_p('HS Mail'),None,None,None,1,ctypes.byref(out))
  if not ok:raise ValueError('인증정보를 이 Windows 계정에서 사용할 수 없습니다. 관리자 설정에서 다시 입력하세요.')
  try:return ctypes.string_at(out.data,out.size)
  finally:ctypes.windll.kernel32.LocalFree(out.data)
 try:from cryptography.fernet import Fernet
 except ImportError:raise ValueError('이 운영체제에서는 cryptography 설치 후 메일 설정을 사용할 수 있습니다.')
 path=shared.STATE/'mail.key'
 if not path.exists():
  if decrypt:raise ValueError('메일 암호화 키가 없습니다. 인증정보를 다시 등록하세요.')
  try:
   fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
   with os.fdopen(fd,'wb') as f:f.write(Fernet.generate_key())
  except FileExistsError:pass
 try:return (Fernet(path.read_bytes()).decrypt(blob) if decrypt else Fernet(path.read_bytes()).encrypt(blob))
 except Exception:raise ValueError('메일 인증정보를 복호화할 수 없습니다. 관리자 설정에서 다시 입력하세요.')

def address(value):
 value=str(value).strip()
 if len(value)>254 or not re.fullmatch(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,63}",value) or '..' in value or value.startswith('.') or '.@' in value:raise ValueError('이메일 주소 형식을 확인하세요.')
 local,domain=value.rsplit('@',1)
 if any(not x or x.startswith('-') or x.endswith('-') for x in domain.split('.')):raise ValueError('이메일 도메인을 확인하세요.')
 return local+'@'+domain.lower()
def addresses(value):
 parts=[p.strip() for p in re.split(r'[,;\n]+',value) if p.strip()] if isinstance(value,str) else list(value)
 out=[]
 for p in parts:
  p=address(p)
  if p.casefold() not in [s.casefold() for s in out]:out.append(p)
 if len(out)>50:raise ValueError('한 번에 받는 사람과 참조는 각각 50명 이하로 입력하세요.')
 return out
def clean(value,limit):
 value=str(value).strip()
 if not value or len(value)>limit or any(ord(c)<32 or ord(c)==127 for c in value):raise ValueError('메일 제목·발신자·서버 설정을 확인하세요.')
 return value

def settings(token,admin=False):
 actor(token,admin)
 with closing(database()) as c:r=c.execute('SELECT * FROM settings WHERE id=1').fetchone()
 return dict(json.loads(r['payload']),version=r['version'],has_secret=bool(r['secret'])) if r else dict(DEFAULTS,version='',has_secret=False)
def save_settings(token,values,password='',expected=''):
 actor(token,True);v={k:values.get(k,DEFAULTS[k]) for k in DEFAULTS}
 v['host']=clean(v['host'],253)
 if not re.fullmatch(r'[A-Za-z0-9.-]+',v['host']):raise ValueError('SMTP 서버명만 입력하세요.')
 try:v['port']=int(v['port'])
 except (ValueError,TypeError):raise ValueError('포트를 확인하세요.')
 if not 1<=v['port']<=65535 or v['security'] not in ['SSL','STARTTLS']:raise ValueError('SSL 또는 STARTTLS 보안 연결과 포트를 확인하세요.')
 v['sender']=address(v['sender']);v['name']=clean(v['name'],100);v['username']=clean(v['username'],254)
 if len(password)>4096:raise ValueError('인증정보 길이를 확인하세요.')
 encrypted=base64.b64encode(_protect(password.encode())).decode() if password else None
 with closing(database()) as c,c:
  c.execute('BEGIN IMMEDIATE');old=c.execute('SELECT * FROM settings WHERE id=1').fetchone()
  if (old['version'] if old else '')!=expected:raise ValueError('메일 설정이 변경되었습니다. 다시 조회하세요.')
  if not encrypted and (not old or any(json.loads(old['payload'])[k]!=v[k] for k in ['host','port','security','sender','username'])):raise ValueError('서버·계정 변경 시 인증정보를 다시 입력하세요.')
  c.execute('INSERT OR REPLACE INTO settings VALUES(1,?,?,?)',(json.dumps(v,ensure_ascii=False),encrypted or old['secret'],secrets.token_hex(16)))
def delete_settings(token,expected):
 actor(token,True)
 with closing(database()) as c,c:
  r=c.execute('SELECT version FROM settings WHERE id=1').fetchone()
  if not r or r['version']!=expected:raise ValueError('메일 설정이 변경되었습니다.')
  c.execute('DELETE FROM settings')
def _config():
 with closing(database()) as c:r=c.execute('SELECT * FROM settings WHERE id=1').fetchone()
 if not r:raise ValueError('관리자가 사용자 관리에서 메일서버를 먼저 설정하세요.')
 v=json.loads(r['payload']);v['password']=_protect(base64.b64decode(r['secret']),True).decode();v['version']=r['version'];return v

def connect(v):
 client=None
 try:
  context=ssl.create_default_context()
  if v['security']=='SSL':client=smtplib.SMTP_SSL(v['host'],v['port'],timeout=20,context=context)
  else:
   client=smtplib.SMTP(v['host'],v['port'],timeout=20);client.ehlo();client.starttls(context=context);client.ehlo()
  client.login(v['username'],v['password']);return client
 except Exception:
  if client:
   try:client.close()
   except Exception:pass
  raise

def finish(client):
 try:client.quit()
 except Exception:
  try:client.close()
  except Exception:pass

def failure(e):
 if isinstance(e,smtplib.SMTPAuthenticationError):return '인증 실패: 네이트 외부 메일 사용 설정·로그인 ID·인증정보를 확인하세요.'
 if isinstance(e,ssl.SSLError):return '보안 연결 실패: 서버·포트·인증서와 PC 시간을 확인하세요.'
 if isinstance(e,smtplib.SMTPRecipientsRefused):return '수신 주소가 서버에서 거부되었습니다. 주소와 서버 정책을 확인하세요.'
 if isinstance(e,smtplib.SMTPResponseException):return '메일 서버가 요청을 거부했습니다. SMTP 코드 '+str(e.smtp_code)+'; 서버 정책과 첨부 용량을 확인하세요.'
 return '서버 연결이 중단되었습니다. 서버명·포트·네트워크 상태를 확인하세요.'
def test_connection(token):
 actor(token,True);client=None
 try:client=connect(_config());client.noop();return '보안 연결·인증 성공 (메일을 발송하지 않았습니다.)'
 except Exception as e:raise ValueError(failure(e))
 finally:
  if client:finish(client)

def manifest(files):
 out=[];total=0
 for f in files:
  name=Path(f['name'].replace('\\','/')).name
  if not name or any(ord(ch)<32 for ch in name):raise ValueError('첨부 파일명을 확인하세요.')
  blob=bytes(f['content']);total+=len(blob)
  out.append(dict(name=name,size=len(blob),sha256=hashlib.sha256(blob).hexdigest(),mime=f.get('mime','application/octet-stream')))
 if total>LIMIT:raise ValueError('메일 첨부는 합계 18MB 이하로 선택하세요. ZIP 또는 파일을 나누어 송부하세요.')
 if len({r['name'] for r in out})!=len(out):raise ValueError('동일한 첨부 파일명이 있습니다.')
 return out

def prepare(token,scope,source,to,cc,subject,body,files):
 user=actor(token);v=_config();to=addresses(to);cc=[x for x in addresses(cc) if x.casefold() not in {a.casefold() for a in to}]
 if not to:raise ValueError('받는 사람 이메일을 입력하세요.')
 subject=clean(subject,200);body=str(body)
 if len(body)>100000:raise ValueError('본문은 100,000자 이하로 입력하세요.')
 docs=manifest(files)
 message_id=make_msgid(domain=v['sender'].split('@')[1])
 payload=dict(to=to,cc=cc,subject=subject,body=body,files=docs,sender=v['sender'],name=v['name'],message_id=message_id)
 fingerprint_payload={k:value for k,value in payload.items() if k!='message_id'}
 fingerprint=hashlib.sha256(json.dumps(dict(payload=fingerprint_payload,source=source,config=v['version']),ensure_ascii=False,sort_keys=True).encode()).hexdigest()
 msg=EmailMessage(policy=SMTP);msg['From']=formataddr((v['name'],v['sender']));msg['To']=', '.join(to)
 if cc:msg['Cc']=', '.join(cc)
 msg['Subject']=subject;msg['Date']=format_datetime(datetime.now(timezone(timedelta(hours=9))));msg['Message-ID']=message_id;msg.set_content(body)
 for f,d in zip(files,docs):
  major,minor=d['mime'].split('/',1);msg.add_attachment(bytes(f['content']),maintype=major,subtype=minor,filename=d['name'])
 eml=msg.as_bytes()
 if len(eml)>25*1024*1024:raise ValueError('인코딩된 메일이 25MB를 초과합니다. 첨부를 줄이세요.')
 with closing(database()) as c,c:
  old=c.execute("SELECT id FROM jobs WHERE actor=? AND scope=? AND fingerprint=? AND status='발송대기'",(user['username'],scope,fingerprint)).fetchone()
  if old:return old['id']
  id=secrets.token_hex(16);c.execute('INSERT INTO jobs(id,actor,scope,source,fingerprint,config_version,payload,eml,status) VALUES(?,?,?,?,?,?,?,?,?)',(id,user['username'],scope,source,fingerprint,v['version'],json.dumps(payload,ensure_ascii=False),eml,'발송대기'))
 return id

def job(token,id):
 user=actor(token)
 with closing(database()) as c:r=c.execute('SELECT * FROM jobs WHERE id=?',(id,)).fetchone()
 if not r or r['actor']!=user['username']:raise ValueError('본인이 미리보기한 메일을 다시 선택하세요.')
 return dict(r,payload=json.loads(r['payload']))
def history(token,scope):
 actor(token)
 with closing(database()) as c:rows=c.execute("SELECT id,actor,payload,status,detail,created_at,updated_at FROM jobs WHERE scope=? AND status<>'발송대기' ORDER BY created_at DESC,rowid DESC LIMIT 100",(scope,)).fetchall()
 return [dict(r,payload=json.loads(r['payload'])) for r in rows]
def duplicates(token,id):
 r=job(token,id)
 with closing(database()) as c:return c.execute("SELECT count(*) FROM jobs WHERE scope=? AND fingerprint=? AND id<>? AND status IN ('전송중','서버 접수','일부 서버 접수','접수 확인 필요')",(r['scope'],r['fingerprint'],id)).fetchone()[0]

def send(token,id,source,allow_duplicate=False):
 r=job(token,id);v=_config()
 if r['source']!=source or r['config_version']!=v['version']:raise ValueError('문서 또는 메일 설정이 바뀌었습니다. 미리보기를 다시 만드세요.')
 if duplicates(token,id) and not allow_duplicate:raise ValueError('같은 내용의 발송 이력이 있습니다. 재발송 확인이 필요합니다.')
 with closing(database()) as c,c:
  c.execute('BEGIN IMMEDIATE')
  # Re-check duplicates while holding the write lock across all workers.
  if not allow_duplicate and c.execute("SELECT 1 FROM jobs WHERE scope=? AND fingerprint=? AND id<>? AND status IN ('전송중','서버 접수','일부 서버 접수','접수 확인 필요')",(r['scope'],r['fingerprint'],id)).fetchone():raise ValueError('다른 요청에서 같은 메일을 발송했습니다. 발송 이력을 확인하세요.')
  if c.execute("UPDATE jobs SET status='전송중',updated_at=CURRENT_TIMESTAMP WHERE id=? AND status='발송대기'",(id,)).rowcount!=1:raise ValueError('이미 처리된 메일입니다. 발송 이력을 확인하세요.')
 client=None;submitted=False;status='실패';detail=''
 try:
  client=connect(v);submitted=True
  refused=client.sendmail(v['sender'],r['payload']['to']+r['payload']['cc'],r['eml'])
  status='일부 서버 접수' if refused else '서버 접수'
  detail='거부 주소: '+', '.join(refused) if refused else '발송 서버가 접수했습니다. 실제 수신·열람 여부는 확인되지 않습니다.'
 except Exception as e:
  status='접수 확인 필요' if submitted and not isinstance(e,(smtplib.SMTPDataError,smtplib.SMTPSenderRefused,smtplib.SMTPRecipientsRefused)) else '실패'
  detail=failure(e)
  if status=='접수 확인 필요':detail+=' 수신 여부를 확인하기 전에는 재발송하지 마세요.'
 finally:
  if client:finish(client)
  with closing(database()) as c,c:c.execute('UPDATE jobs SET status=?,detail=?,updated_at=CURRENT_TIMESTAMP WHERE id=?',(status,detail,id))
 return status,detail

def draft(token,scope,values=None):
 user=actor(token)
 with closing(database()) as c,c:
  if values is not None:c.execute('INSERT OR REPLACE INTO drafts VALUES(?,?,?)',(user['username'],scope,json.dumps(values,ensure_ascii=False)))
  r=c.execute('SELECT payload FROM drafts WHERE actor=? AND scope=?',(user['username'],scope)).fetchone()
 return json.loads(r['payload']) if r else {}

def _decode_header(value):
 out=[]
 for part,encoding in decode_header(value or ''):
  if isinstance(part,bytes):
   for codec in (encoding,'utf-8','cp949','latin1'):
    if not codec:continue
    try:part=part.decode(codec);break
    except (UnicodeDecodeError,LookupError):continue
   if isinstance(part,bytes):part=part.decode('utf-8','replace')
  out.append(str(part))
 return ''.join(out).strip()

def inbox_headers(token,limit=300):
 """Read recent Nate IMAP headers without changing their read/unread state."""
 actor(token);v=_config()
 if 'nate' not in v['host'].lower() and not v['sender'].lower().endswith('@nate.com'):
  raise ValueError('자동 회신 확인은 현재 네이트 메일 계정만 지원합니다.')
 client=None
 try:
  client=imaplib.IMAP4_SSL('imap.nate.com',993,ssl_context=ssl.create_default_context(),timeout=25)
  client.login(v['username'],v['password'])
  status,_=client.select('INBOX',readonly=True)
  if status!='OK':raise ValueError('네이트 받은메일함을 열 수 없습니다.')
  status,data=client.uid('search',None,'ALL')
  if status!='OK':raise ValueError('네이트 받은메일함을 조회할 수 없습니다.')
  ids=(data[0].split() if data and data[0] else [])[-max(1,min(int(limit),1000)):]
  result=[]
  query='(BODY.PEEK[HEADER.FIELDS (SUBJECT FROM DATE MESSAGE-ID IN-REPLY-TO REFERENCES)])'
  for uid in reversed(ids):
   status,parts=client.uid('fetch',uid,query)
   if status!='OK':continue
   raw=next((part[1] for part in parts if isinstance(part,tuple) and isinstance(part[1],bytes)),b'')
   if not raw:continue
   msg=message_from_bytes(raw)
   date_iso=''
   try:
    parsed=parsedate_to_datetime(msg.get('Date',''))
    if parsed:
     if parsed.tzinfo is None:parsed=parsed.replace(tzinfo=timezone.utc)
     date_iso=parsed.astimezone(timezone(timedelta(hours=9))).isoformat(timespec='seconds')
   except (TypeError,ValueError,OverflowError):pass
   result.append({'uid':uid.decode('ascii','ignore'),'subject':_decode_header(msg.get('Subject','')),
    'from':_decode_header(msg.get('From','')),'date_iso':date_iso,'message_id':str(msg.get('Message-ID','')).strip(),
    'in_reply_to':str(msg.get('In-Reply-To','')).strip(),'references':str(msg.get('References','')).strip()})
  return result
 except ValueError:raise
 except imaplib.IMAP4.error as e:raise ValueError('네이트 IMAP 인증에 실패했습니다. 외부 프로그램 사용 설정과 로그인 정보를 확인하세요.') from e
 except (OSError,ssl.SSLError) as e:raise ValueError('네이트 받은메일함에 연결할 수 없습니다. 네트워크와 IMAP 설정을 확인하세요.') from e
 finally:
  if client:
   try:client.logout()
   except Exception:pass
