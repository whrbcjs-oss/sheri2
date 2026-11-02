"""Authenticated monthly Bank of Korea survey workflow."""
from datetime import date
import base64,json
import streamlit as st
import streamlit.components.v1 as components
import survey_store as db
from survey_report import html_preview,pdf
VERSION='2026.11.02.3'

def notice(message):st.session_state['_bs_notice']=message;st.rerun()
def download_document(c,id):
 r=db.document(c,id);p=json.loads(r['snapshot']);label=p['profile']['name']+'_'+p['month']+'_기업경기조사표'
 actions=st.columns([1,2])
 actions[0].download_button('PDF 저장',db.document_pdf(c,id),file_name=label+'.pdf',mime='application/pdf',key='bs_pdf_'+str(id))
 actions[1].download_button('인쇄용 파일 내려받기',html_preview([p]).encode(),file_name=label+'.html',mime='text/html',key='bs_html_'+str(id),help='내려받은 HTML을 열고 인쇄를 누르세요. A4 한 장으로 출력됩니다.')
 components.html(html_preview([p]),height=1070,scrolling=True)

def render(user):
 st.caption('한국은행 기업경기조사 · 버전 '+VERSION)
 with st.sidebar:
  st.subheader('한국은행 기업경기조사')
  page=st.radio('기업경기조사 업무',['월별 조사표 작성','작성 내역·출력','회사 기본정보'],key='bs_page')
 c=db.connect();companies=db.companies(c)
 selectors=st.columns([2,1,1])
 with selectors[0]:company_id=st.selectbox('작성 회사',[x['id'] for x in companies],format_func=lambda id:next(x['name'] for x in companies if x['id']==id),key='bs_company')
 with selectors[1]:period=st.text_input('조사 연월 (YYYY-MM)',db.today().strftime('%Y-%m'),key='bs_month')
 try:period=db.month(period)
 except ValueError as e:st.error(str(e));return
 with selectors[2]:st.text_input('전망 연월',db.next_month(period),disabled=True,key='bs_forecast_'+period)
 if '_bs_notice' in st.session_state:st.success(st.session_state.pop('_bs_notice'))
 if page=='회사 기본정보':
  st.title('회사 기본정보');st.caption('회사별로 한 번 등록합니다. 저장된 월별 조사표와 과거 출력본은 자동으로 바뀌지 않습니다.')
  values=db.company(c,company_id);new={}
  with st.form('bs_profile_'+str(company_id)):
   cols=st.columns(3)
   for i,(k,label) in enumerate(db.FIELDS.items()):
    with cols[i%3]:new[k]=st.text_input(label,values.get(k,''))
   submit=st.form_submit_button('회사 기본정보 저장',type='primary')
  if submit:
   try:db.profile(c,company_id,new);notice('회사 기본정보를 저장했습니다.')
   except ValueError as e:st.error(str(e))
  return
 if page=='작성 내역·출력':
  st.title('조사표 출력 미리보기')
  surveys=db.rows(c,'''SELECT s.id,s.month,s.updated_at,(SELECT COUNT(*) FROM bs_documents d WHERE d.survey_id=s.id) AS editions,(SELECT COUNT(*) FROM bs_faxes f JOIN bs_documents d ON d.id=f.document_id WHERE d.survey_id=s.id) AS fax_records FROM bs_surveys s WHERE company_id=? ORDER BY month DESC''',(company_id,))
  if not surveys:st.info('작성한 조사표가 없습니다. 월별 조사표 작성에서 먼저 저장하세요.');return
  with st.expander('월별 작성 내역',expanded=False):
   st.dataframe([{'조사월':x['month'],'최근 저장(한국시간)':db.korean_time(x['updated_at']),'상태':db.status(c,x['id']),'출력본 수':x['editions']} for x in surveys],hide_index=True,use_container_width=True)
  selected=period
  record=next((x for x in surveys if x['month']==selected),None)
  if not record:st.info('선택한 조사월에 저장한 조사표가 없습니다. 상단 조사 연월을 바꾸거나 새 조사표를 작성하세요.');return
  sid=record['id']
  docs=db.rows(c,'SELECT id,created_at FROM bs_documents WHERE survey_id=? ORDER BY id DESC',(sid,))
  if docs:
   docid=st.selectbox('보관된 출력본',[x['id'] for x in docs],format_func=lambda id:f"출력본 #{id} · "+db.korean_time(next(x['created_at'] for x in docs if x['id']==id)))
   with st.expander('팩스 발송 기록',expanded=False):
    st.info('팩스를 직접 보낸 뒤 기록하세요. 이 프로그램은 팩스를 자동 전송하지 않습니다.')
    snap=json.loads(db.document(c,docid)['snapshot'])
    with st.form('bs_fax_'+str(docid)):
     sent=st.date_input('실제 발송일',db.today(),max_value=db.today());recipient=st.text_input('실제 수신 팩스번호',snap['profile'].get('fax',''));note=st.text_input('발송 메모')
     confirm=st.checkbox('팩스 전송 결과를 직접 확인했습니다.')
     submitted=st.form_submit_button('발송 기록 저장')
    if submitted:
     try:
      if not confirm:raise ValueError('직접 전송 결과를 확인한 뒤 체크하세요.')
      db.record_fax(c,docid,sent,recipient,note);notice('발송 기록을 저장했습니다.')
     except ValueError as e:st.error(str(e))
    faxes=db.rows(c,'SELECT sent_date AS 발송일,recipient AS 수신번호,note AS 메모 FROM bs_faxes WHERE document_id=? ORDER BY id DESC',(docid,))
    if faxes:st.dataframe(faxes,hide_index=True,use_container_width=True)
   download_document(c,docid)
  else:st.info('이 월은 작성 중입니다. 월별 조사표 작성에서 응답을 확인한 뒤 출력본을 만드세요.')
  bundle=[];missing=[]
  for co in companies:
   saved=c.execute('SELECT d.id,s.id FROM bs_documents d JOIN bs_surveys s ON s.id=d.survey_id WHERE s.company_id=? AND s.month=? ORDER BY d.id DESC LIMIT 1',(co['id'],selected)).fetchone()
   if saved and db.status(c,saved[1])!='수정 후 재출력 필요':bundle.append(json.loads(db.document(c,saved[0])['snapshot']))
   else:missing.append(co['name'])
  st.subheader('두 회사 일괄 출력')
  if missing:st.caption('해당월 출력본 필요: '+', '.join(missing))
  else:st.download_button('두 회사 인쇄용 파일',html_preview(bundle).encode(),file_name=selected+'_두회사_기업경기조사표.html',mime='text/html')
  return
 st.title('월별 기업경기조사표')
 sid,existing=db.draft(c,company_id,period);scope=str(company_id)+'_'+period
 written=st.date_input('작성일',date.fromisoformat(existing.get('written',db.today().isoformat())),key='bs_written_'+scope)
 prev=date.fromisoformat(period+'-01');previous=f'{prev.year-(prev.month==1):04d}-{(prev.month-2)%12+1:02d}'
 if st.button('전월 응답 불러오기',help='이번 달 응답을 전월 응답으로 바꿉니다. 검토 후 저장하세요.'):
  _,old=db.draft(c,company_id,previous)
  if not old:st.warning('전월에 저장한 조사표가 없습니다.')
  else:
   for k,_,_,_ in db.ITEMS:
    for side in ['now','next']:st.session_state['bs_'+scope+'_'+side+'_'+k]=old.get(side,{}).get(k)
   st.session_state['bs_factor_'+scope]=old.get('factor');st.session_state['bs_other_'+scope]=old.get('other','');st.info('전월 응답을 불러왔습니다. 이번 달 상황에 맞게 검토하세요.')
 with st.expander('이번 출력에 사용할 회사 기본정보',expanded=False):
  st.dataframe([{'항목':label,'내용':db.company(c,company_id).get(k,'')} for k,label in db.FIELDS.items()],hide_index=True,use_container_width=True);st.caption('수정은 왼쪽 회사 기본정보에서 합니다. 이번 조사표를 저장하면 최신 회사정보가 함께 저장됩니다.')
 st.info('매출규모는 전년 동월 대비, 채산성·자금사정은 전월 대비입니다. 업황은 계절요인을 제외한 귀사 상황으로 판단하세요.')
 h=st.columns([1.1,2,2]);h[0].markdown('**조사 항목 / 판단 기준**');h[1].markdown('**'+period+' 동향**');h[2].markdown('**'+db.next_month(period)+' 전망**')
 answers={'now':{},'next':{}}
 for k,label,basis,options in db.ITEMS:
  cols=st.columns([1.1,2,2]);cols[0].markdown('**'+label+'**');cols[0].caption(basis)
  for side,col in [('now',cols[1]),('next',cols[2])]:
   value=existing.get(side,{}).get(k)
   with col:answers[side][k]=st.radio(label+(' 동향' if side=='now' else ' 전망'),options,index=options.index(value) if value in options else None,horizontal=True,key='bs_'+scope+'_'+side+'_'+k,label_visibility='collapsed')
 st.subheader('경영애로사항');st.caption('가장 주요한 요인 1개만 선택하세요.')
 factor=st.selectbox('경영애로요인',list(range(1,15)),index=existing['factor']-1 if existing.get('factor') else None,format_func=lambda i:f'{i:02d} '+db.FACTORS[i-1],placeholder='선택하세요',key='bs_factor_'+scope)
 other=st.text_input('기타 내용',existing.get('other',''),max_chars=18,disabled=factor!=13,key='bs_other_'+scope)
 payload=dict(month=period,written=written.isoformat(),factor=factor,other=other,profile=db.company(c,company_id),**answers)
 a,b=st.columns([1,2]);save=a.button('임시 저장');issue=b.button('검토 완료·저장하고 출력본 만들기',type='primary')
 try:
  if issue:
   db.validate(payload,True);sid=db.save(c,company_id,period,payload);docid=db.issue(c,sid);st.session_state['bs_preview_'+scope]=docid;notice('출력본을 보관했습니다. 아래에서 PDF를 받거나 인쇄하세요.')
  elif save:db.save(c,company_id,period,payload);notice('조사표를 저장했습니다.')
 except ValueError as e:st.error(str(e))
 docid=st.session_state.get('bs_preview_'+scope)
 if docid:
  st.subheader('보관된 출력 미리보기');st.caption('아래 문서는 마지막으로 만든 출력본입니다. 위 응답을 수정하면 새 출력본을 만들어 주세요.');download_document(c,docid)
 elif st.checkbox('현재 입력 미리보기 (저장·확정 전)',key='bs_draft_preview_'+scope):
  st.caption('미응답 칸은 선택 표시 없이 보입니다. 출력본을 만들려면 모든 항목을 검토하세요.')
  components.html(html_preview([payload]),height=1070,scrolling=True)
