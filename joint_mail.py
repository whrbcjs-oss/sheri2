"""Recipient contacts and attachments derived only from the selected business scope."""
import hashlib,json
import joint_store as db
import joint_letter_files as files
from joint_report import render,monthly_package

def install(c):
 c.execute('''CREATE TABLE IF NOT EXISTS jv_member_emails(member_id INTEGER PRIMARY KEY REFERENCES jv_members(id) ON DELETE CASCADE,project_id INTEGER NOT NULL REFERENCES jv_projects(id),email TEXT NOT NULL)''')
def recipient(c,p,m):
 row=next((r for r in db.members(c,p) if r['id']==m),None)
 if not row:raise ValueError('해당 공사의 회원사를 확인하세요.')
 return row.get('email','')
def scope(c,p,m):return 'joint:'+hashlib.sha256(str(c.path.resolve()).encode()).hexdigest()[:16]+':'+str(p)+':'+str(m)
def item(name,blob,mime='text/html'):return dict(name=name,content=blob.encode('utf-8') if isinstance(blob,str) else blob,mime=mime)
def extras(meta):return [item(str(i)+'_'+r['name'],files.unpack(r),r['mime']) for i,r in enumerate(meta.get('uploaded_files',[]),1)]
def archived(c,p,id):
 from joint_letter_manage import visible
 row=next((r for r in visible(c,p) if r['id']==id),None)
 if not row or not db.is_nonlead(c,p):raise ValueError('당사비주관공사의 현재 확정 발행본을 선택하세요.')
 d=json.loads(row['snapshot']);m=d['member']['id'];recipient(c,p,m)
 docs=[item('공문.html' if row['kind']=='공문' else '원가정산서.html',render(d,row['kind'],dict(d.get('meta',{}),mail_no_embedded_files=True,mail_no_ledger_append=True)))]
 if d.get('investment_letter'):
  from joint_nonlead import investment_attachment
  docs.append(item('공동원가_투입내역서.html',investment_attachment(d)))
 docs+=extras(d.get('meta',{}))
 return dict(member=m,recipient_name=d['member']['name'],source='archive:'+str(id)+':'+hashlib.sha256(row['snapshot'].encode()).hexdigest(),files=docs,label=row['number']+' · '+d['start']+' ~ '+d['end'],month=d['end'])
def closed(c,p,m,month,meta):
 import joint_workflow as flow
 if db.is_nonlead(c,p):raise ValueError('당사주관공사의 마감 보고서를 선택하세요.')
 recipient(c,p,m);package=flow.closed_package(c,p,month)
 if str(m) not in package['letters']:raise ValueError('마감 보고서의 회원사를 확인하세요.')
 d=dict(package['letters'][str(m)],letter_layout_version=2,lead_letter_layout_version=1)
 _,ledger,allocation=monthly_package(package,m,meta)
 docs=[item('공문.html',render(d,'공문',dict(meta,mail_no_embedded_files=True,mail_no_ledger_append=True))),item('해당월_원장.html',ledger),item('원가배분내역서.html',allocation)]+extras(meta)
 source=hashlib.sha256(json.dumps(dict(package=package,meta=meta),ensure_ascii=False,sort_keys=True).encode()).hexdigest()
 return dict(member=m,recipient_name=package['letters'][str(m)]['member']['name'],source='close:'+month+':'+source,files=docs,label=month+' 마감 보고서',month=month)
