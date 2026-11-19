"""Reviewable administrator workflow for management-company identity corrections."""
import json
from datetime import datetime,timezone,timedelta
import streamlit as st
import joint_store as db
import joint_owner as owner
import collaboration as shared
from joint_amounts import show as amount_table

def render(c,p):
 ctx=shared.RUN.get()
 if not ctx or not ctx['user']['admin']:return
 project=next(r for r in db.projects(c) if r['id']==p);companies={r['id']:r for r in db.companies(c)};base='jv_owner_fix_'+str(p)+'_'
 with st.expander('관리자 · 관리법인 등록 오류 정정',expanded=bool(st.session_state.get(base+'keep_open'))):
  st.caption('프로젝트를 삭제하지 않고 관리법인과 잘못된 회사 명의의 원장 연결을 함께 정정합니다. 회원사 번호·지분율·금액과 과거 확정 발행본은 유지합니다.')
  st.session_state[base+'old']=companies[project['owner_id']]['name']
  cols=st.columns(2);cols[0].text_input('현재 관리법인',companies[project['owner_id']]['name'],disabled=True,key=base+'old')
  choices=[id for id,row in companies.items() if id!=project['owner_id'] and json.loads(row['info']).get('회사구분')!='외부 회원사']
  if base+'target' in st.session_state and st.session_state[base+'target'] not in choices:st.session_state.pop(base+'target')
  target=cols[1].radio('올바른 관리법인',choices,index=None,horizontal=True,format_func=lambda id:companies[id]['name'],key=base+'target')
  if st.button('정정 영향 확인',disabled=target is None,key=base+'preview'):
   st.session_state[base+'keep_open']=True
   try:st.session_state[base+'plan']=owner.preview(c,p,target)
   except ValueError as e:st.session_state.pop(base+'plan',None);st.warning(str(e))
  plan=st.session_state.get(base+'plan')
  if plan and (plan['old_company']!=project['owner_id'] or plan['new_company']!=target):plan=None
  if plan:
   st.info(plan['old_name']+' → '+plan['new_name']+' / 유지 지분율 '+plan['share']+'%')
   amount_table([{'구분':'회사 명의 정정 원장','건수':plan['ledger_count'],'공급가액':plan['ledger_supply'],'VAT':plan['ledger_vat']}],['공급가액','VAT'],footer=False)
   st.caption('회원사 번호 유지 · 기성/지급/정산 연결 유지 · 저장 현황의 회사 연결 정정 · 확정 발행본과 월 마감 원본 '+str(plan['counts']['jv_documents'])+'건/'+str(plan['counts']['jv_closes'])+'건 보존')
   reason=st.text_input('정정 사유',key=base+'reason')
   confirmed=st.checkbox('미리보기의 회사 연결을 정정하며 원장 거래내용·금액과 과거 발행본을 유지하는 것을 확인했습니다.',key=base+'confirm')
   if st.button('백업 후 관리법인 정정',type='primary',disabled=not confirmed or not reason.strip(),key=base+'apply'):
    owner.correct(c,p,target,reason,ctx['token'],plan['fingerprint']);st.session_state.pop(base+'plan',None)
    from joint_app import saved
    saved()
  rows=owner.history(c,p)
  if rows:
   st.caption('관리법인 정정 이력')
   st.dataframe([{'번호':r['id'],'일시(KST)':datetime.fromisoformat(r['at']).replace(tzinfo=timezone.utc).astimezone(timezone(timedelta(hours=9))).strftime('%Y-%m-%d %H:%M:%S'),'이전 관리법인':companies[r['old_company']]['name'],'정정 관리법인':companies[r['new_company']]['name'],'사유':r['reason'],'처리자':r['actor']} for r in rows],hide_index=True,use_container_width=True)
   with st.expander('정정 되돌리기',expanded=bool(st.session_state.get(base+'undo_reason') or st.session_state.get(base+'undo_confirm'))):
    id=st.selectbox('되돌릴 정정', [r['id'] for r in rows],key=base+'undo_id');reason=st.text_input('되돌리기 사유',key=base+'undo_reason')
    st.caption('해당 정정 이후 공사 자료가 바뀌지 않은 경우에만 즉시 되돌릴 수 있습니다. 변경 이력은 남깁니다.')
    check=st.checkbox('선택 정정을 되돌립니다.',key=base+'undo_confirm')
    if st.button('관리법인 정정 되돌리기',disabled=not check or not reason.strip(),key=base+'undo'):
     owner.undo(c,p,id,reason,ctx['token'])
     from joint_app import saved
     saved()
