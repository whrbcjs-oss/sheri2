"""Posting-date ledger selection, reviewed soft delete and restore."""
from datetime import datetime,timezone,timedelta
import hashlib,json
import pandas as pd
import streamlit as st
import joint_store as db
import joint_ledger_manage as manage
from joint_amounts import frame as amount_frame,formatted
from table_layout import aligned_config

LABELS={'id':'원장번호','company':'원가투입 회사','posting_date':'기표일자','allocation_month':'배분연월','account':'계정과목','vendor':'거래처명','description':'적요','tax_supply':'세금계산서 공급가액','vat':'VAT','invoice':'계산서 금액','receipt':'기타영수증 금액','note':'비고'}
CURRENCY=['세금계산서 공급가액','VAT','계산서 금액','기타영수증 금액','합계금액']
def panel(c,p,cid,dt,restore):
 rows=manage.records(c,p,cid,restore)
 if dt:rows=[r for r in rows if r['posting_date']==dt.isoformat()]
 base=f'ledger_manage_{p}_{cid}_{dt}_{restore}_'
 if not rows:st.caption('조회한 삭제 내역이 없습니다.' if restore else '조회한 원장이 없습니다.');return
 data=[]
 for row in rows:
  item={'선택':False,**{LABELS[k]:row[k] for k in LABELS}}
  item['합계금액']=str(sum((db.num(row[k]) for k in ['tax_supply','invoice','receipt','vat']),db.num(0)))
  if restore:
   item['삭제 사유']=row['delete_reason'];item['삭제일시(KST)']=datetime.fromisoformat(row['deleted_at']).replace(tzinfo=timezone.utc).astimezone(timezone(timedelta(hours=9))).strftime('%Y-%m-%d %H:%M:%S')
  data.append(item)
 controls=st.columns([1,1,4]);revision=base+'table_revision'
 if controls[0].button('조회 행 전체 선택',key=base+'all'):st.session_state[base+'initial']=[r['id'] for r in rows];st.session_state[revision]=st.session_state.get(revision,0)+1
 if controls[1].button('선택 해제',key=base+'none'):st.session_state[base+'initial']=[];st.session_state[revision]=st.session_state.get(revision,0)+1
 for item in data:item['선택']=item['원장번호'] in st.session_state.get(base+'initial',[])
 frame=amount_frame(data,CURRENCY,footer=False)
 fingerprint=hashlib.sha256(json.dumps(data,ensure_ascii=False).encode()).hexdigest()[:12]
 selected_frame=st.data_editor(frame,hide_index=True,use_container_width=True,disabled=[k for k in frame if k!='선택'],column_config=aligned_config(frame,{'선택':st.column_config.CheckboxColumn('선택')}),key=base+fingerprint+'_'+str(st.session_state.get(revision,0)))
 ids=[int(r['원장번호']) for r in selected_frame.to_dict('records') if r['선택']]
 if not restore:
  from joint_app import safe_csv
  st.download_button('원장 CSV 내려받기',safe_csv(amount_frame([{LABELS[k]:row[k] for k in LABELS} for row in rows],CURRENCY[:-1],CURRENCY[:-1])),file_name='공동도급_원장.csv',key=base+'csv')
 if not ids:return
 lookup={r['id']:r for r in rows};supply=sum((sum((db.num(lookup[id][k]) for k in ['tax_supply','invoice','receipt']),db.num(0)) for id in ids),db.num(0));vat=sum((db.num(lookup[id]['vat']) for id in ids),db.num(0))
 st.info(f'조회 {len(rows):,}건 · 선택 {len(ids):,}건 · 공급가액 {formatted(supply)}원 · VAT {formatted(vat)}원 · 합계 {formatted(supply+vat)}원')
 try:plan=manage.preview(c,p,cid,ids,restore)
 except ValueError as e:st.warning(str(e));return
 if plan['reallocate']:st.caption('미정산 배분 자동 재계산: '+', '.join(plan['reallocate'])+' / 남은 원장의 수동조정 금액은 유지합니다.')
 action='복구' if restore else '삭제';confirm_key=base+'confirm_'+hashlib.sha256(json.dumps([ids,plan['revision']]).encode()).hexdigest()[:12]
 reason=st.text_input(action+' 사유',key=base+'reason')
 check=st.checkbox(f'선택한 {len(ids)}건을 '+('복구하는' if restore else '삭제 목록으로 이동하는')+' 것을 확인했습니다.',key=confirm_key)
 if st.button(f'선택 원장 {len(ids)}건 '+action,disabled=not check or not reason.strip(),key=base+('restore_execute' if restore else 'delete_execute')):
  import collaboration as shared
  manage.change(c,p,cid,ids,reason,shared.RUN.get()['token'],plan['revision'],restore)
  for phase in [False,True]:
   other=f'ledger_manage_{p}_{cid}_{dt}_{phase}_'
   st.session_state[other+'initial']=[]
   st.session_state[other+'table_revision']=st.session_state.get(other+'table_revision',0)+1
  st.session_state['_jv_success']=f'선택 원장 {len(ids)}건 '+action+' 완료. 원장 번호·원본 자료는 보존했습니다.'
  st.rerun()

def render(c,p,members):
 base='ledger_filters_'+str(p)+'_';cols=st.columns([1.3,1.3,1],vertical_alignment='bottom')
 choices=[r['company_id'] for r in members]
 if st.session_state.get(base+'company') not in choices:st.session_state[base+'company']=choices[0]
 cid=cols[0].selectbox('원가투입 회사 조회',choices,format_func=lambda id:next(r['name'] for r in members if r['company_id']==id),key=base+'company')
 dt=cols[1].date_input('기표일자 조회',value=None,key=base+'date',help='배분연월과 구분합니다. 예: 기표일자 2026-11-02, 배분연월 2026-10.')
 cols[2].button('조건으로 조회',key=base+'search')
 tabs=st.tabs(['등록 원장 조회·선택 삭제','삭제 내역·복구'])
 with tabs[0]:panel(c,p,cid,dt,False)
 with tabs[1]:panel(c,p,cid,dt,True)
