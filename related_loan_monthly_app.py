"""Compact period view and accounting reference export for intercompany interest."""
import pandas as pd
import streamlit as st
import related_loan_store as db
import related_loan_calc as calc
import related_loan_monthly as monthly
from related_loan_app import table,excel,table_print,today,action

def render(c,company,cos,user):
 ds=db.deals(c,company);others=sorted({t['borrower_id'] if t['lender_id']==company else t['lender_id'] for t in ds})
 a,b,d,e=st.columns([1,1,1,2]);start=a.text_input('조회 시작월',today().strftime('%Y')+'-01',key='rl_range_start');end=b.text_input('조회 종료월',today().strftime('%Y-%m'),key='rl_range_end');other=d.selectbox('상대 거래처',[None]+others,format_func=lambda i:'전체' if i is None else cos[i]['name'],key='rl_range_counter')
 available=[t for t in ds if other is None or other in (t['lender_id'],t['borrower_id'])];lookup={t['id']:t for t in available};id=e.selectbox('조회 차입·대여 건',[None]+list(lookup),format_func=lambda i:'전체' if i is None else lookup[i]['number'],key='rl_range_deal')
 st.caption('회사별 예외이율이 있는 거래는 예외이율, 그 외 거래는 공통이율을 적용합니다. 예외 기간의 이율 누락은 공통이율로 대체하지 않습니다.')
 st.caption('등록된 약정·적용일별 이율로 실제 원금 상환 완료일까지 계산합니다. 만기 이후 잔액은 별도 표시합니다. 미확정·미래 예상 이자는 원장 입력 전에 확인·확정하세요.')
 try:data=monthly.build(c,company,start,end,other,id)
 except ValueError as ex:st.warning(str(ex));return
 if not data['rows']:st.info('선택 기간의 거래가 없습니다.');return
 a,b=st.columns(2)
 values=[r['당월이자'] for r in data['rows']]
 a.metric('선택기간 이자 (확정·미확정·예상 포함)','확인 필요' if any(v is None for v in values) else f'{sum(values):,}원')
 b.metric('조회 종료월 원금잔액',f"{sum(r['월말잔액'] for r in data['rows'] if r['귀속월']==end):,}원")
 mode=st.radio('표 구성',['월별 명세','아마란스 입력용 요약'],horizontal=True,key='rl_range_mode')
 fields=['월초원금','당월차입원금','당월상환원금','월말잔액','당월이자']
 if mode=='월별 명세':
  grouped=[]
  for m,k,p in sorted({(r['귀속월'],r['구분'],r['거래처']) for r in data['rows']}):
   items=[{a:b for a,b in r.items() if a!='거래ID'} for r in data['rows'] if (r['귀속월'],r['구분'],r['거래처'])==(m,k,p)];grouped+=items
   subtotal={col:'' for col in items[0]};subtotal.update(귀속월=m,구분=k,거래처=p,관리번호='거래처 소계',**{f:None if any(r[f] is None for r in items) else sum(r[f] for r in items) for f in fields});grouped.append(subtotal)
  frame=table(grouped,fields)
 else:frame=table(data['summary'],['이자금액'])
 st.info('아마란스 입력용 요약은 전표 작성 참고자료입니다. 아마란스 전용 업로드 양식은 아닙니다. 차입·대여와 확정·미확정 상태를 나누어 표시합니다.')
 selected=st.selectbox('계산 근거 대상',list(range(len(data['rows']))),format_func=lambda i:data['rows'][i]['귀속월']+' / '+data['rows'][i]['관리번호'],key='rl_range_detail')
 r=data['rows'][selected]
 with st.expander('선택 차입 건 계산 근거',expanded=True):
  table([p for p in data['details'] if (p['귀속월'],p['관리번호'])==(r['귀속월'],r['관리번호'])],['계산원금','구간이자'])
  old=db.month_record(c,r['거래ID'],r['귀속월']);st.caption('월 합계는 구간 원 단위 처리와 저장된 조정액을 반영합니다. 조정·확정 해제는 월 계산·조정·확정 탭에서 처리하세요.')
  st.caption('선택 월 조정액: '+str((old or {}).get('data',{}).get('adjustment',0))+' / '+str((old or {}).get('data',{}).get('adjustment_reason','')))
  ok=st.checkbox('선택 거래·월의 이자와 계산 근거를 확인했습니다.',key='rl_range_final_ack')
  if st.button('선택 월 계산 확정',disabled=not ok or r['상태'] in ['확정','이율 확인 필요'] or calc.month_end(r['귀속월'])>today()):
   action(lambda:db.save_month(c,r['거래ID'],r['귀속월'],(old or {}).get('data',{}).get('adjustment',0),(old or {}).get('data',{}).get('adjustment_reason',''),True,old['version'] if old else None))
 with st.container(horizontal=True):
  st.download_button('월별 명세·요약 엑셀',excel({'월별명세':pd.DataFrame([{k:v for k,v in r.items() if k!='거래ID'} for r in data['rows']]),'아마란스입력참고':pd.DataFrame(data['summary']),'계산근거':pd.DataFrame(data['details'])}),file_name='관계사_월별이자명세.xlsx')
  st.download_button('현재 표 인쇄 HTML',table_print(cos[company]['name']+' '+start+' ~ '+end+' '+mode,frame),file_name='관계사_월별이자명세.html')
