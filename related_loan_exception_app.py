"""Company-pair exception setup: register once, automatically apply to every matching loan."""
import streamlit as st
import related_loan_store as db
import related_loan_calc as calc
import related_loan_exceptions as ex
from related_loan_app import picker,table,action,deletion,restoration,today

def render(c):
 cos={r['id']:r for r in db.companies(c)}
 if len(cos)<2:st.info('회사정보 관리에서 대여회사·차입회사를 먼저 등록하세요.');return
 rules=db.entities(c,'exception_rules');lookup={r['id']:r for r in rules}
 def name(r):return cos.get(r['lender_id'],{}).get('name',str(r['lender_id']))+' → '+cos.get(r['borrower_id'],{}).get('name',str(r['borrower_id']))
 selected=st.selectbox('예외 회사 불러오기',[None]+list(lookup),format_func=lambda i:'신규 예외 회사' if i is None else name(lookup[i]),key='rl_exception_rule')
 old=lookup.get(selected);tag='rl_ex_pair_'+str(selected)+'_';ids=list(cos)
 a,b=st.columns(2);lender=a.selectbox('예외 대여회사',ids,index=ids.index(old['lender_id']) if old else 0,format_func=lambda i:cos[i]['name'],disabled=bool(old),key=tag+'lender')
 others=[i for i in ids if i!=lender];borrower=b.selectbox('예외 차입회사',others,index=others.index(old['borrower_id']) if old else 0,format_func=lambda i:cos[i]['name'],disabled=bool(old),key=tag+'borrower')
 selected_rule=ex.rule(c,lender,borrower);base='rl_exception_rates_'+str(lender)+'_'+str(borrower)+'_'
 st.info(cos[lender]['name']+' → '+cos[borrower]['name']+' 방향의 기존·신규 계약 전체에 자동 적용합니다. 반대 방향은 별도이며 계약별 선택은 필요하지 않습니다.')
 history=db.rows(c,'SELECT * FROM rlc_exception_rules WHERE lender_id=? AND borrower_id=?',(lender,borrower));inactive=bool(history and history[0]['deleted'])
 entries=[r for r in db.entities(c,'exception_rates') if selected_rule and r['rule_id']==selected_rule['id']]
 r=picker('예외이율 불러오기',entries,base) or {};key=base+str(r.get('id'))+'_'+str(r.get('version',0))
 a,b,d=st.columns(3);dt=a.date_input('예외이율 적용 시작일',calc.day(r.get('effective_date',today())),key=key+'date');rate=b.text_input('예외 연이율 (%)',r.get('rate',''),key=key+'rate');kb=d.text_input('예외 KB 참고이율 (%)',r.get('kb') or '',key=key+'kb');note=st.text_input('예외 변경 사유·비고',r.get('note',''),key=key+'note')
 ack=st.checkbox('이 회사 방향 전체에 예외이율을 적용하며, 이율이 없는 과거 기간은 확인 필요로 표시함을 확인했습니다.',key=key+'ack')
 if st.button('예외이율 수정 저장' if r else '예외이율 등록',disabled=not ack or inactive,type='primary',key=key+'save'):action(lambda:ex.save(c,lender,borrower,dict(effective_date=dt,rate=rate,kb=kb,note=note),r.get('id'),r.get('version')),base)
 if inactive:st.warning('예외 적용 해제 상태입니다. 아래 예외 회사 복구에서 먼저 복구하세요.')
 if selected_rule and not entries:st.warning('예외 적용 중이지만 활성 이율이 없습니다. 공통이율로 대체하지 않습니다. 이율을 등록·복구하거나 예외 적용을 해제하세요.')
 table([{'대여회사':cos[lender]['name'],'차입회사':cos[borrower]['name'],'적용 시작일':x['effective_date'],'예외 연이율(%)':x['rate'],'KB 참고(%)':x['kb'] or '', '비고':x['note']} for x in sorted(entries,key=lambda x:x['effective_date'])])
 st.caption('최초 차입·대여일부터 계산하려면 그 날짜 이전 또는 당일의 예외이율을 등록하세요. 확정 월과 발행본은 당시 결과를 보존합니다.')
 deletion(c,'exception_rates',r,key)
 if selected_rule:
  restoration(c,'exception_rates',[x for x in db.entities(c,'exception_rates',True) if x['rule_id']==selected_rule['id']],base)
  with st.expander('이 회사 방향의 예외 적용 해제'):
   st.warning('이 회사 방향의 미확정 계산이 공통이율로 전환됩니다. 개별 예외이율 기록·확정 월·발행본은 보존합니다.')
   reason=st.text_input('예외 적용 해제 사유',key=base+'disable_reason');ok=st.checkbox('선택 회사 방향의 예외를 해제하고 공통이율을 적용합니다.',key=base+'disable_ack')
   if st.button('예외 적용 해제',disabled=not ok or not reason.strip(),key=base+'disable'):action(lambda:db.set_deleted(c,'exception_rules',selected_rule['id'],selected_rule['version'],True,reason))
 with st.expander('예외 회사 복구'):
  removed={r['id']:r for r in db.entities(c,'exception_rules',True)}
  if not removed:st.caption('해제한 예외 회사가 없습니다.')
  else:
   id=st.selectbox('복구할 예외 회사',list(removed),format_func=lambda i:name(removed[i]),key='rl_ex_restore_pair');why=st.text_input('예외 회사 복구 사유',key='rl_ex_restore_reason');ok=st.checkbox('이 회사 방향 전체에 기존 예외이율을 다시 적용합니다.',key='rl_ex_restore_ack')
   if st.button('예외 회사 복구',disabled=not ok or not why.strip(),key='rl_ex_restore'):action(lambda:db.set_deleted(c,'exception_rules',id,removed[id]['version'],False,why))
