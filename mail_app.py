"""Admin SMTP setup and reviewed document mail composer."""
import hashlib,json
from datetime import datetime,timezone,timedelta
import streamlit as st
import mail_service as mail
import collaboration as shared

def notice(status,detail):
 if status=='서버 접수':st.success(status+' · '+detail)
 elif status in ['일부 서버 접수','접수 확인 필요','전송중']:st.warning(status+' · '+detail)
 else:st.error(status+' · '+detail)

def settings_panel(token):
 mail.actor(token,True);v=mail.settings(token,True);key='smtp_'+v['version']+'_'
 st.subheader('메일서버 설정')
 st.caption('네이트 기본값: smtp.mail.nate.com / 465 / SSL. 네이트 환경설정에서 외부 프로그램 사용 조건을 확인하세요. 인증정보는 이 서버에 암호화하여 저장합니다.')
 st.link_button('네이트 공식 SMTP 설정 안내','https://mail3.nate.com/outmail/pop3_guide03.html')
 with st.form(key+'form',clear_on_submit=True):
  a,b,c=st.columns([2,1,1]);host=a.text_input('SMTP 서버',v['host']);port=b.number_input('SMTP 포트',1,65535,int(v['port']));security=c.selectbox('보안 연결',['SSL','STARTTLS'],index=0 if v['security']=='SSL' else 1)
  a,b=st.columns(2);sender=a.text_input('발신 메일주소',v['sender']);name=b.text_input('발신자명',v['name'])
  a,b=st.columns(2);username=a.text_input('SMTP 로그인 ID',v['username']);password=b.text_input('메일 인증정보 (빈칸이면 기존 값 유지)',type='password')
  submit=st.form_submit_button('메일서버 설정 저장',type='primary')
 if submit:
  try:mail.save_settings(token,dict(host=host,port=port,security=security,sender=sender,name=name,username=username),password,v['version']);st.session_state['_mail_notice']='메일서버 설정을 저장했습니다.';st.rerun()
  except (ValueError,PermissionError) as e:st.error(str(e))
 if st.session_state.get('_mail_notice'):st.success(st.session_state.pop('_mail_notice'))
 a,b=st.columns(2)
 if a.button('연결·인증 테스트 (메일 발송 없음)',disabled=not v['has_secret'],key=key+'connection'):
  try:st.success(mail.test_connection(token))
  except (ValueError,PermissionError) as e:st.error(str(e))
 with b:
  remove=st.checkbox('메일서버 설정 삭제 확인',key=key+'confirm_delete')
  if st.button('메일서버 설정 삭제',disabled=not remove or not v['version'],key=key+'delete'):
   try:mail.delete_settings(token,v['version']);st.rerun()
   except (ValueError,PermissionError) as e:st.error(str(e))
 with st.expander('테스트 메일 발송'):
  test_to=st.text_input('테스트 수신 메일주소',v['sender'],key=key+'test_to')
  confirm=st.checkbox('입력한 주소로 테스트 메일 1통 발송에 동의합니다.',key=key+'test_confirm')
  if st.button('테스트 메일 발송 실행',disabled=not confirm or not v['has_secret'],key=key+'test_send'):
   try:
    id=mail.prepare(token,'smtp-test','test:'+v['version'],test_to,'','HS 경리Jobs 메일 연결 테스트','관리자가 실행한 메일 발송 테스트입니다.',[])
    notice(*mail.send(token,id,'test:'+v['version'],True))
   except (ValueError,PermissionError) as e:st.error(str(e))


def history(token,scope,key):
 with st.expander('발송 이력 · 성공/실패 · 재발송'):
  rows=mail.history(token,scope)
  st.caption('서버 접수는 상대방 수신·열람 완료를 의미하지 않습니다. 전송중/접수 확인 필요는 수신 여부를 확인한 뒤 재발송하세요. 재발송은 주소·본문만 불러오며 첨부는 현재 화면에서 선택한 문서를 사용합니다. 문서와 대상 월을 확인하고 새 미리보기·발송 확인을 거치세요.')
  data=[]
  for r in rows:
   dt=datetime.fromisoformat(r['created_at']).replace(tzinfo=timezone.utc).astimezone(timezone(timedelta(hours=9)))
   data.append({'일시(KST)':dt.strftime('%Y-%m-%d %H:%M:%S'),'실행자':r['actor'],'받는 사람':', '.join(r['payload']['to']),'참조':', '.join(r['payload']['cc']),'제목':r['payload']['subject'],'첨부':', '.join(f['name'] for f in r['payload']['files']),'상태':r['status'],'안내':r['detail']})
  st.dataframe(data,hide_index=True,use_container_width=True)
  if rows:
   ids=[r['id'] for r in rows];selected=st.selectbox('재발송할 메일 내용 불러오기',ids,format_func=lambda id:next(r['payload']['subject']+' · '+r['status']+' · '+r['created_at'] for r in rows if r['id']==id),key=key+'history_pick')
   if st.button('재발송 초안으로 불러오기',key=key+'retry'):
    r=next(r for r in rows if r['id']==selected);st.session_state[key+'reload']=dict(to=', '.join(r['payload']['to']),cc=', '.join(r['payload']['cc']),subject=r['payload']['subject'],body=r['payload']['body']);st.session_state[key+'epoch']=st.session_state.get(key+'epoch',0)+1;st.rerun()


def compose(c,p,m,doc):
 import joint_mail
 token=st.session_state.get('_auth_token') or shared.RUN.get()['token'];mail.actor(token)
 scope=joint_mail.scope(c,p,m);root='mail_compose_'+hashlib.sha256((scope+doc['source']).encode()).hexdigest()[:18]+'_'
 st.subheader('메일 송부');st.caption('송부 대상: '+doc['label']+' · 수신 회원사: '+doc.get('recipient_name','')+' · 선택한 보고서의 서류를 아래에서 골라 첨부합니다. HTML 문서는 인쇄/PDF 저장이 가능한 출력 양식입니다.')
 v=mail.settings(token)
 if not v['has_secret']:
  st.info('관리자가 작업화면 → 사용자 관리 → 메일서버 설정을 먼저 저장하세요.');history(token,scope,root);return
 st.caption('발신: '+v['name']+' <'+v['sender']+'>')
 defaults=st.session_state.get(root+'reload') or mail.draft(token,scope+':'+doc['source'])
 epoch=st.session_state.get(root+'epoch',0);key=root+str(epoch)+'_'
 a,b=st.columns(2)
 to=a.text_input('받는 사람 메일주소',defaults.get('to',joint_mail.recipient(c,p,m)),key=key+'to',help='회원사 등록 이메일을 자동 입력합니다. 여러 주소는 쉼표 또는 세미콜론으로 구분하세요.')
 cc=b.text_input('참조 메일주소',defaults.get('cc',''),key=key+'cc')
 subject=st.text_input('메일 제목',defaults.get('subject',doc['label']+' 송부'),key=key+'subject')
 body=st.text_area('메일 본문',defaults.get('body','안녕하세요.\n'+doc['label']+' 자료를 첨부하오니 확인 부탁드립니다.\n감사합니다.'),height=130,key=key+'body')
 st.markdown('**첨부 선택**');selected=[]
 for i,f in enumerate(doc['files']):
  if st.checkbox(f['name']+' ('+f"{len(f['content']):,}"+' bytes)',value=True,key=key+'file_'+str(i)):selected.append(f)
 payload=dict(to=to,cc=cc,subject=subject,body=body)
 # Any source, recipient, content, attachment or config change invalidates confirmation.
 try:docs=mail.manifest(selected)
 except ValueError as e:
  st.warning(str(e));history(token,scope,root);return
 fingerprint=hashlib.sha256(json.dumps(dict(payload=payload,files=docs,source=doc['source'],config=v['version']),sort_keys=True,ensure_ascii=False).encode()).hexdigest()
 a,b=st.columns(2)
 if a.button('메일 초안 저장',key=key+'draft'):
  mail.draft(token,scope+':'+doc['source'],payload);st.success('초안을 저장했습니다. 첨부는 다음 조회 시 현재 선택 문서를 다시 확인하세요.')
 if b.button('메일 미리보기',type='primary',key=key+'preview'):
  try:
   id=mail.prepare(token,scope,doc['source'],to,cc,subject,body,selected);st.session_state[root+'pending']=(id,fingerprint)
  except (ValueError,PermissionError) as e:st.error(str(e))
 pending=st.session_state.get(root+'pending')
 if pending and pending[1]==fingerprint:
  try:
   job=mail.job(token,pending[0]);draft=job['payload']
   st.markdown('**발송 전 최종 확인**');st.write('받는 사람: '+', '.join(draft['to']));st.write('참조: '+(', '.join(draft['cc']) or '없음'));st.write('제목: '+draft['subject']);st.text(draft['body']);st.write('첨부: '+(', '.join(f['name'] for f in draft['files']) or '없음'))
   st.download_button('미리보기 메일 EML 내려받기',job['eml'],file_name='송부메일_미리보기.eml',mime='message/rfc822',key=key+'eml')
   duplicate=mail.duplicates(token,job['id']);again=False
   if duplicate:
    st.warning('같은 내용의 발송 이력이 있습니다. 수신 여부를 먼저 확인하세요.');again=st.checkbox('같은 내용임을 확인하고 재발송합니다.',key=key+'duplicate_'+job['id'])
   check=st.checkbox('받는 사람·본문·선택 첨부를 확인했으며 이 메일 발송에 동의합니다.',key=key+'confirm_'+job['id'])
   if st.button('확인한 메일 발송',disabled=not check or bool(duplicate and not again) or job['status']!='발송대기',key=key+'send_'+job['id']):
    with st.spinner('메일 서버에 송부 중입니다…'):
     status,detail=mail.send(token,job['id'],doc['source'],again)
    notice(status,detail)
  except (ValueError,PermissionError) as e:st.error(str(e))
 elif pending:st.caption('입력 내용이 변경되었습니다. 메일 미리보기를 다시 눌러 확인하세요.')
 history(token,scope,root)
