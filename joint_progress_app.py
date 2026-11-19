"""Compact monthly work dashboard and navigation; never sends or closes anything."""
from datetime import date
import streamlit as st
import joint_store as db
import joint_progress as guide

def month_key(p):return 'jv_work_month_'+str(p)
def keep_month(p):st.session_state.setdefault('jv_work_periods',{})[p]=st.session_state[month_key(p)]
def sync(p,key):
 st.session_state[month_key(p)]=st.session_state[key];keep_month(p)
def ensure_month(p):
 key=month_key(p);month=st.session_state.get(key,st.session_state.get('jv_work_periods',{}).get(p,date.today().strftime('%Y-%m')));st.session_state.setdefault(key,month)
 marker=(p,month)
 if st.session_state.get('_jv_month_context')!=marker:
  for field in ['close_month','letter_month',f'jv_allocation_month_{p}',f'investment_month_{p}']:st.session_state[field]=month
  st.session_state['_jv_month_context']=marker
 for field in ['close_month','letter_month',f'jv_allocation_month_{p}',f'investment_month_{p}']:
  if field not in st.session_state:st.session_state[field]=month
 return month

def go(page):st.session_state['jv_page']=page

def sidebar_label(page,nonlead):
 for i,(_,_,target) in enumerate(guide.steps(nonlead)):
  if target==page:return guide.NUMBERS[i]+' '+page
 if page=='공문 작성' and not nonlead:return '⑥ '+page
 return page

def header(c,p,m,page,nonlead):
 if p is None or not m:
  st.info('프로젝트와 회원사를 등록하면 공사·기준월별 다음 업무를 안내합니다.')
  if page=='업무 진행 현황':st.button('프로젝트·회원사 등록으로 이동',on_click=go,args=('프로젝트·회원사',),key='jv_guide_start')
  return None
 ensure_month(p)
 cols=st.columns([1,2.6,1],vertical_alignment='bottom');month=cols[0].text_input('업무 기준월 (YYYY-MM)',key=month_key(p),on_change=keep_month,args=(p,));db.period(month)
 rows=guide.state(c,p,m['id'],month,nonlead);pending=next((r for r in rows if r['status'] not in ['완료','해당 없음']),rows[-1]);current=next((r for r in rows if r['target']==page),None)
 if page=='공문 작성' and not nonlead:current=next(r for r in rows if r['step']=='close')
 cols[1].caption(('현재: '+current['number']+' '+current['label']+' · ' if current else '')+'확인 '+str(sum(r['status'] in ['완료','해당 없음'] for r in rows))+'/'+str(len(rows))+' · 다음 할 일: '+pending['number']+' '+pending['label'])
 cols[2].button('다음 할 일로 이동',key='jv_guide_next_task',on_click=go,args=(pending['target'],),use_container_width=True)
 with st.expander('업무 순서 · 진행 현황',expanded=page=='업무 진행 현황'):
  st.caption('선택 공사·업무 기준월·대상 회원사 기준입니다. 단계 확인은 검토 표시이며 실제 입력·정산 저장·공문 발행·월마감·메일 발송을 대신하지 않습니다.')
  for row in rows:
   a,b,d=st.columns([2.3,2.7,1],vertical_alignment='center');a.markdown('**'+row['number']+' '+row['label']+' · '+row['status']+'**');b.caption(row['detail']);d.button('이동',key='jv_guide_to_'+row['step'],on_click=go,args=(row['target'],),use_container_width=True)
  target=st.selectbox('검토 표시할 단계',[r['step'] for r in rows],format_func=lambda key:next(r['number']+' '+r['label'] for r in rows if r['step']==key),index=next(i for i,r in enumerate(rows) if r['step']==(current or pending)['step']),key=f'jv_guide_review_{p}_{m["id"]}_{month}_{page}')
  selected=next(r for r in rows if r['step']==target);st.caption(selected['tip'])
  key=f'jv_guide_mark_{p}_{m["id"]}_{month}_{target}_';reason=st.text_input('검토 메모 · 해당 없음은 사유 필수',key=key+'reason')
  ack=st.checkbox('해당 업무 자료와 실제 처리 여부를 확인했습니다.',key=key+selected['fingerprint'][:12]+'ack')
  buttons=st.columns(3)
  def save(status):
   try:guide.review(c,p,m['id'],month,target,status,reason,selected['fingerprint']);st.session_state['_jv_success']='업무 검토 표시를 저장했습니다. 실제 마감·발행·메일 발송은 각 메뉴에서 처리하세요.';st.rerun()
   except (ValueError,PermissionError) as ex:st.error(str(ex))
  if buttons[0].button('검토 완료 표시',disabled=not ack or not selected['ready'],key=key+'done'):save('reviewed')
  if buttons[1].button('해당 없음 표시',disabled=not ack or not selected['optional'] or not selected['empty'] or not reason.strip(),key=key+'na'):save('na')
  if buttons[2].button('검토 표시 해제',disabled=not ack or not selected['mark'],key=key+'reset'):save('reset')
 return month

def footer(page,nonlead):
 steps=guide.steps(nonlead);i=next((i for i,s in enumerate(steps) if s[2]==page),None)
 if page=='공문 작성' and not nonlead:i=5
 if i is None:return
 st.divider()
 with st.container(horizontal=True):
  if i>0:st.button('← 이전 업무: '+steps[i-1][1],on_click=go,args=(steps[i-1][2],),key='jv_guide_previous')
  st.button('업무 진행 현황',on_click=go,args=('업무 진행 현황',),key='jv_guide_home')
  if i<len(steps)-1:st.button('다음 업무: '+steps[i+1][1]+' →',on_click=go,args=(steps[i+1][2],),key='jv_guide_next')
