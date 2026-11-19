"""Final-only letter list and explicit replacement/recovery controls."""
import json
import streamlit as st
import joint_letter_manage as store

def controls(c,p,m,month):
 rows=store.letters(c,p,m,month);expected=[(r['id'],r['snapshot']) for r in rows];key=f'final_letter_{p}_{m}_{month}'
 st.subheader('최종 공문 관리')
 if rows:
  st.success('최종 공문: '+rows[0]['number']+' · 발행일 '+rows[0]['issued'])
  cols=st.columns(3)
  if cols[0].button('불러와 갱신',key=key+'load',disabled=len(rows)>1):
   st.session_state[key+'draft']=rows[0]['data'];st.session_state[key+'draft_expected']=expected;st.session_state[key+'epoch']=st.session_state.get(key+'epoch',0)+1;st.rerun()
  with cols[1]:
   confirm=st.checkbox('최종 공문 삭제 확인',key=key+'delete_confirm')
   reason=st.text_input('공문 삭제 사유',key=key+'delete_reason')
   if st.button('최종 공문 삭제',disabled=not confirm or not reason.strip() or len(rows)>1,key=key+'delete'):
    store.remove(c,p,m,month,expected,reason=reason);st.session_state.pop(key+'draft',None)
    from joint_app import saved
    saved()
  if cols[2].button('갱신 취소 · 최종본 보기',key=key+'cancel'):
   st.session_state.pop(key+'draft',None);st.rerun()
 else:st.info('확정된 최종 공문이 없습니다.')
 if len(rows)>1:
  st.warning(f'기존 중복 공문 {len(rows)}건이 있습니다. 남길 최종본 1개를 확인해 정리하세요.')
  keep=st.selectbox('남길 최종 공문',[r['id'] for r in rows],format_func=lambda id:next(r['number']+' · '+r['issued'] for r in rows if r['id']==id),key=key+'keep')
  confirm=st.checkbox('선택한 최종 공문만 남기고 나머지를 삭제 내역으로 이동합니다.',key=key+'dedupe_confirm')
  if st.button('중복 공문 정리',disabled=not confirm,key=key+'dedupe'):
   store.remove(c,p,m,month,expected,keep,'중복 공문 정리')
   from joint_app import saved
   saved()
 with st.expander('삭제 내역·복구'):
  removed=store.recovery(c,p,m,month)
  if removed:
   id=st.selectbox('복구할 공문',[r['id'] for r in removed],format_func=lambda id:next(json.loads(r['payload'])['number']+' · '+r['reason']+' · '+r['created_at'] for r in removed if r['id']==id),key=key+'restore_id')
   ok=st.checkbox('복구 공문을 최종본으로 사용하며 현재 최종본은 복구용으로 보관합니다.',key=key+'restore_confirm')
   if st.button('공문 복구',disabled=not ok,key=key+'restore'):
    store.restore(c,p,m,month,id,expected);st.session_state.pop(key+'draft',None)
    from joint_app import saved
    saved()
  else:st.caption('삭제·갱신 전 공문이 없습니다.')
 draft=st.session_state.get(key+'draft')
 return rows,(st.session_state.get(key+'draft_expected',expected) if draft else expected),draft,st.session_state.get(key+'epoch',0),key
