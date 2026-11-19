"""Review monthly partner shares; the representative's share is calculated automatically."""
import json
import pandas as pd
import streamlit as st
import joint_store as db
import joint_workflow as flow
import joint_month_shares as shares
import collaboration as shared
from joint_amounts import show as amount_table

def editor(c,p,month):
 with st.expander('월별 배분비율 조정'):
  old=shares.record(c,p,month);ms=shares.members(c,p,month);project=next(r for r in db.projects(c) if r['id']==p);owner=next(m for m in ms if m['company_id']==project['owner_id']);key=f'month_share_{p}_{month}_{old["version"] if old else 0}_'
  closed=flow.is_closed(c,p,month);existing=db.allocations(c,p,month,month);manual=any(r['reason'].strip() for r in existing);revision=shared.revision(c)
  st.caption(month+'에만 적용합니다. 프로젝트 계약 지분율·다른 월은 유지하며 회원사 합계의 나머지를 대표사에 자동 반영합니다.')
  frame=pd.DataFrame([{'회원사':m['name'],'계약 지분율(%)':str(m['contract_share']),'월 배분비율(%)':str(m['share']),'회원사번호':m['id']} for m in ms if m['id']!=owner['id']])
  if frame.empty:st.info('대표사만 등록되어 있어 대표사 비율은 100%입니다.');return
  edit=st.data_editor(frame,hide_index=True,use_container_width=True,disabled=True if closed else ['회원사','계약 지분율(%)','회원사번호'],key=key+'editor',column_config={'회원사번호':None,'월 배분비율(%)':st.column_config.TextColumn('월 배분비율(%)',help='0~100, 소수점 입력 가능')})
  values={int(r['회원사번호']):r['월 배분비율(%)'] for r in edit.to_dict('records')}
  try:
   normalized=shares.normalize(c,p,values);st.metric('대표사 월 배분비율',normalized[str(owner['id'])]+'%');st.caption(owner['name']+' · 계약 지분율 '+str(owner['contract_share'])+'%')
  except (ValueError,PermissionError) as ex:st.error(str(ex));return
  reason=st.text_input('월 배분비율 변경 사유',old['reason'] if old else '',key=key+'reason')
  ack=st.checkbox('해당 월 비율 저장 및 배분 적용을 확인했습니다.',disabled=closed,key=key+'ack_'+str(revision))
  reset=st.checkbox('기존 원장별 수동 배분액을 초기화하고 이 비율로 재배분합니다.',disabled=closed,key=key+'reset_'+str(revision)) if manual else False
  if existing:st.warning('기존 해당 월 배분액을 다시 계산합니다. 정산 연결이 있으면 먼저 해제해야 합니다.')
  if closed:st.info('마감된 월입니다. 관리자 마감 해제 후 변경하세요.')
  def change(**kwargs):
   try:
    shares.change(c,p,month,reason=reason,expected=old['version'] if old else None,apply=True,reset_manual=reset,revision=revision,**kwargs);st.session_state['_jv_success']='월 배분비율을 저장하고 해당 월 배분을 적용했습니다.';st.rerun()
   except (ValueError,PermissionError) as ex:st.error(str(ex))
  disabled=closed or not ack or not reason.strip() or manual and not reset
  if st.button('월 비율 저장·배분 적용',disabled=disabled,key=key+'save'):change(values=values)
  if old and not old['deleted']:
   drop=st.checkbox('이 월 조정비율을 삭제하고 계약 지분율로 재배분합니다.',disabled=closed,key=key+'drop')
   if st.button('월 조정비율 삭제·계약 비율 적용',disabled=disabled or not drop,key=key+'delete'):change(values=None,deleted=True)
  if old and old['deleted']:
   st.caption('삭제된 월 비율: '+old['payload'])
   restore=st.checkbox('삭제된 월 조정비율을 복구하여 재배분합니다.',disabled=closed,key=key+'restore')
   if st.button('월 조정비율 복구·적용',disabled=disabled or not restore,key=key+'restore_btn'):change(values=None,restore=True)
