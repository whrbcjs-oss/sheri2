"""Common letter attachment editor for lead and nonlead outgoing letters."""
import streamlit as st
import joint_letter_files as store

def editor(c,p,m,month):
 base=f'jv_letter_files_{p}_{m}_{month}_';rows=store.files(c,p,m,month);lookup={r['id']:r for r in rows}
 with st.expander('추가 서류 첨부 · 등록/교체/삭제/복구'):
  st.caption('파일당 10MB, 공문별 20MB까지. 추가 서류는 원본으로 보관하며 공문·첨부 ZIP에서 함께 내려받습니다. 공문과 당사 원장은 연속 미리보기·인쇄로 제공합니다.')
  if st.session_state.get(base+'load') not in [None]+list(lookup):st.session_state[base+'load']=None
  selected=st.selectbox('수정할 추가 서류',[None]+list(lookup),format_func=lambda id:'새 첨부 등록' if id is None else lookup[id]['name'],key=base+'load')
  uploads=st.file_uploader('추가 서류 선택',type=list(store.EXT),accept_multiple_files=True,key=base+'uploads')
  if st.button('선택 첨부 교체' if selected else '추가 서류 등록',disabled=not uploads,key=base+'save'):
   store.save(c,p,m,month,[(f.name,f.getvalue()) for f in uploads],selected,lookup[selected]['version'] if selected else None)
   from joint_app import saved
   saved()
  if selected:
   row=lookup[selected];filename=st.text_input('첨부 파일명',row['name'],key=base+str(selected)+'_'+str(row['version'])+'name')
   if st.button('첨부 파일명 수정 저장',key=base+'rename'):
    store.edit(c,p,m,month,selected,row['version'],filename=filename)
    from joint_app import saved
    saved()
   check=st.checkbox('선택 첨부 삭제 확인',key=base+'confirm')
   if st.button('첨부 삭제',disabled=not check,key=base+'delete'):
    store.edit(c,p,m,month,selected,row['version'],deleted=True)
    from joint_app import saved
    saved()
  for row in rows:st.download_button(row['name']+' · 원본 내려받기',store.unpack(row),file_name=row['name'],mime=row['mime'],key=base+'download_'+str(row['id']))
  removed=store.files(c,p,m,month,True)
  if removed:
   deleted={r['id']:r for r in removed};rid=st.selectbox('삭제 첨부 복구',list(deleted),format_func=lambda id:deleted[id]['name'],key=base+'removed')
   if st.button('첨부 복구',key=base+'restore'):
    store.edit(c,p,m,month,rid,deleted[rid]['version'],deleted=False)
    from joint_app import saved
    saved()
 if rows:st.caption('추가 서류: '+', '.join(row['name'] for row in rows))
