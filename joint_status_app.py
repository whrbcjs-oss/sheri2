"""Editable monthly investment/performance/contract dashboard for nonlead projects."""
from datetime import date
from calendar import monthrange
from io import BytesIO
import json
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
import joint_store as db
import joint_workflow as flow
import joint_status as status
import joint_status_report as report
from joint_amounts import money_input,show as amount_table,total_input
from table_layout import aligned_config,format_excel

TITLE='당사투입비·기성·계약현황'
def done():
 from joint_app import saved
 saved()
def manual_form(c,p,m,month,months=None):
 rows=status.manual_periods(c,p,m,(months or [])+[month]);lookup={r['id']:r for r in rows};base=f'js_manual_{p}_{m}_{month}_'
 if base+'pending' in st.session_state:st.session_state[base+'load']=st.session_state.pop(base+'pending')
 selected=st.selectbox('수동입력 내역 불러오기',[None]+list(lookup),format_func=lambda id:'새 수동입력' if id is None else lookup[id]['kind']+' / '+lookup[id]['category']+' / '+lookup[id]['note'],key=base+'load');v=lookup.get(selected,{});key=base+str(selected)+'_'+str(v.get('version',0))
 edit_month=v.get('month',month)
 kind=st.radio('입력 구분',['영업비','안분제외'],index=0 if v.get('kind','안분제외')=='영업비' else 1,horizontal=True,key=key+'kind')
 category='영업비' if kind=='영업비' else st.selectbox('안분제외 비용구분',status.CATEGORIES,index=status.CATEGORIES.index(v.get('category','기타비용')),key=key+'category')
 entry_date=st.date_input('입력 기준일',date.fromisoformat(v.get('entry_date') or month+'-01'),key=key+'entry_date')
 amount=money_input('수동 입력 공급가액',v.get('amount','0'),key=key+'amount');note=st.text_input('사유·적요',v.get('note',''),key=key+'note')
 included=False
 if st.button('수동입력 수정 저장' if selected else '수동입력 등록',type='primary',key=key+'save'):
  id=status.save_manual(c,p,m,edit_month,kind,category,amount,note,included,selected,v.get('version'),entry_date=entry_date);st.session_state[base+'pending']=id;done()
 if selected:
  check=st.checkbox('수동입력 삭제 확인',key=key+'check')
  if st.button('수동입력 삭제',disabled=not check,key=key+'delete'):status.set_manual_deleted(c,p,m,edit_month,selected,v['version'],True);st.session_state[base+'pending']=None;done()
 st.caption('기준일 순 입력내역')
 amount_table([{'기준일':r['entry_date'],'내역번호':r['id'],'구분':r['kind'],'비용구분':r['category'],'공급가액':r['amount'],'사유':r['note']} for r in rows],['공급가액'])
 with st.expander('삭제 내역 복구'):
  removed=status.manual_periods(c,p,m,(months or [])+[month],True)
  if removed:
   lookup_removed={r['id']:r for r in removed};rid=st.selectbox('복구할 수동입력',list(lookup_removed),format_func=lambda id:lookup_removed[id]['note'],key=base+'restore')
   if st.button('수동입력 복구',key=base+'restore_btn'):status.set_manual_deleted(c,p,m,lookup_removed[rid]['month'],rid,lookup_removed[rid]['version'],False);st.session_state[base+'pending']=rid;done()

def _contract_changes(draft_key,widget_key,revision_key):
 rows=[dict(row) for row in st.session_state[draft_key]]
 fields={'계약금액':'contract','전회까지':'previous','금회':'current'}
 for index,changes in st.session_state.get(widget_key,{}).get('edited_rows',{}).items():
  index=int(index)
  if index>=len(rows):continue
  for label,field in fields.items():
   if label in changes:
    rows[index][field]=str(db.num(changes[label]))
    if field=='contract':rows[index]['contract_manual']=True
 st.session_state[draft_key]=rows
 st.session_state[revision_key]=st.session_state.get(revision_key,0)+1

def contract_editor(c,p,m,month,initial,key):
 defaults=status.contract_defaults(c,p,m,month,cumulative=True);stored={int(row['company_id']):row for row in initial.get('contracts',[])}
 draft_key=key+'contract_draft';revision_key=key+'contract_revision'
 if draft_key not in st.session_state:
  rows=[]
  for row in defaults:
   saved=stored.get(row['company_id']);row=dict(row)
   if saved:
    row.update({field:saved[field] for field in ['contract','previous','current']})
    row['contract_manual']=bool(saved.get('contract_manual',db.num(saved['contract'])!=db.num(row['basis_contract'])))
   rows.append(row)
  st.session_state[draft_key]=rows
 rows=st.session_state[draft_key]
 default_map={row['company_id']:row for row in defaults}
 for row in rows:
  basis=default_map[row['company_id']];row.update(name=basis['name'],share=basis['share'],basis_contract=basis['basis_contract'])
  if not row.get('contract_manual'):row['contract']=basis['basis_contract']
 supply=next(row['supply'] for row in db.projects(c) if row['id']==p)
 st.caption('계약금액 계산 기준 · 프로젝트 전체 공급가액: '+f'{db.num(supply):,.0f}'+'원')
 if st.button('전체 공급가액·지분율로 계약금액 다시 계산',key=key+'reset_contracts'):
  for row in rows:row.update(contract=row['basis_contract'],contract_manual=False)
  st.session_state[revision_key]=st.session_state.get(revision_key,0)+1
 frame=[]
 for row in rows:
  contract=db.num(row['contract']);previous=db.num(row['previous']);current=db.num(row['current']);total=previous+current
  frame.append({'법인':row['name'],'지분율(%)':float(db.num(row['share'])),'계약금액':int(contract) if contract==int(contract) else float(contract),'전회까지':int(previous) if previous==int(previous) else float(previous),'금회':int(current) if current==int(current) else float(current),'합계':int(total) if total==int(total) else float(total),'기성률':f'{total/contract*100:.2f}%' if contract else '—','계약금액 기준':'수동 수정' if row.get('contract_manual') else '공급가액×지분율'})
 sums={field:sum((db.num(row[field]) for row in frame),db.num(0)) for field in ['계약금액','전회까지','금회','합계']}
 frame.append({'법인':'전체 합계','지분율(%)':100,'계약금액':int(sums['계약금액']) if sums['계약금액']==int(sums['계약금액']) else float(sums['계약금액']),'전회까지':int(sums['전회까지']) if sums['전회까지']==int(sums['전회까지']) else float(sums['전회까지']),'금회':int(sums['금회']) if sums['금회']==int(sums['금회']) else float(sums['금회']),'합계':int(sums['합계']) if sums['합계']==int(sums['합계']) else float(sums['합계']),'기성률':f"{sums['합계']/sums['계약금액']*100:.2f}%" if sums['계약금액'] else '—','계약금액 기준':'자동 합계'})
 widget_key=key+'contract_grid_'+str(st.session_state.get(revision_key,0))
 config={label:st.column_config.NumberColumn(label,min_value=0,step=1,format='localized') for label in ['계약금액','전회까지','금회']}
 st.data_editor(pd.DataFrame(frame),hide_index=True,use_container_width=True,disabled=['법인','지분율(%)','합계','기성률','계약금액 기준'],column_config=aligned_config(frame,config),key=widget_key,on_change=_contract_changes,args=(draft_key,widget_key,revision_key))
 st.caption('합계 = 전회까지 + 금회 / 기성률 = 합계 ÷ 계약금액 × 100. 전체 합계 행은 자동 계산됩니다. 수동 수정값은 현황 저장 후 다시 조회·다른 기준월 작성 시에도 유지됩니다.')
 return [dict(row) for row in rows]

def view(c,p,m):
 st.subheader(TITLE);records=status.records(c,p,m['id']);lookup={r['id']:r for r in records};base=f'js_{p}_{m["id"]}_'
 if base+'pending' in st.session_state:st.session_state[base+'load']=st.session_state.pop(base+'pending')
 selected=st.selectbox('저장 현황 불러오기',[None]+list(lookup),format_func=lambda id:'새 현황 작성' if id is None else lookup[id]['month']+' / '+lookup[id]['data']['run_name']+' / '+lookup[id]['data']['as_of'],key=base+'load')
 record=lookup.get(selected,{});initial=record.get('data',{}).get('inputs',{});key=base+str(selected)+'_'+str(record.get('version',0))+'_'
 controls=st.columns(3);month=controls[0].text_input('기준월 (YYYY-MM)',record.get('month',date.today().strftime('%Y-%m')),key=key+'month',disabled=bool(selected));db.period(month);key=key+month+'_'
 end=date.fromisoformat(month+'-01').replace(day=monthrange(int(month[:4]),int(month[5:]))[1]);as_of=str(controls[1].date_input('기준일',end,key=key+'date',disabled=True))
 runs=flow.runs(c,p,m['id']);run_map={r['id']:r for r in runs}
 if not runs:st.info('원가정산서에서 정산 건을 먼저 저장하세요. 영업비·안분제외는 아래에서 미리 등록할 수 있습니다.')
 preferred_run=st.session_state.get('_jv_next_run',[])
 preferred_run=preferred_run[2] if preferred_run[:2]==[p,m['id']] else None
 run_id=controls[2].selectbox('연결 정산 건',list(run_map),index=list(run_map).index(record['run_id']) if record.get('run_id') in run_map else list(run_map).index(preferred_run) if preferred_run in run_map else 0,format_func=lambda id:run_map[id]['name'],key=key+'run',disabled=bool(selected)) if runs else None
 if run_id is not None:st.info('원가정산서 연결 대상: '+run_map[run_id]['name']+' · 저장 후 해당 정산서 하단에 자동 연결됩니다.')
 claim_months=status.cumulative_months(c,p,m['id'],month)
 st.caption('집계 범위: 최초 등록월 ~ '+month+' · 기준월 말일: '+as_of+' · 누계 현황')
 source_doc=None
 st.caption('집계 원본: 현재 등록된 당사투입비 원장 (기준월까지 누계)')
 st.caption('당사투입비·영업비·안분제외·수금·지급·하도급은 기준월 말일까지 누계로 집계합니다. 부가세는 당사투입비 합계에 포함하지 않습니다.')
 left,right=st.columns([1.45,1])
 with left,st.container(key='js_cost_card'):
  st.markdown('### ① 당사투입비 내역');source=status.investment(c,p,m['id'],month,source_doc,as_of,claim_months);manual=[r for r in status.manual_periods(c,p,m['id'],claim_months+[month]) if r['entry_date']<=as_of];rows=[]
  for category in status.CATEGORIES:
   target=sum((db.num(r['amount']) for r in manual if r['kind']=='영업비'),db.num(0)) if category=='영업비' else db.num(source['totals'][category]);excluded=sum((db.num(r['amount']) for r in manual if r['kind']=='안분제외' and r['category']==category),db.num(0))
   rows.append({'구분':category,'안분대상액':str(target),'안분제외액':str(excluded),'계':str(target+excluded)})
  rows.append({'구분':'합계',**{k:str(sum((db.num(row[k]) for row in rows),db.num(0))) for k in ['안분대상액','안분제외액','계']}})
  amount_table(rows,['안분대상액','안분제외액','계'],footer=False)
  if source['unmapped']:
   with st.expander('기타비용으로 합산한 원장 구분 확인'):st.dataframe(pd.DataFrame(source['unmapped']).rename(columns={'id':'원장번호','account':'구분','amount':'공급가액'}),hide_index=True,use_container_width=True)
 with right,st.container(key='js_manual_card'):
  st.markdown('### 영업비·안분제외 수동입력');manual_form(c,p,m['id'],month,claim_months)
 if run_id is None:return
 middle_left,middle_right=st.columns([1,1.6])
 with middle_left,st.container(key='js_cash_card'):
  st.markdown('### ② 수입·지출 현황');flow_preview=st.empty()
 with middle_right,st.container(key='js_contract_card'):
  st.markdown('### ③ 계약·실기성 현황')
  contract_rows=contract_editor(c,p,m['id'],month,initial,key+'run_'+str(run_id)+'_')
 with st.expander('수입·지출 계산 및 지급 예정액 입력',expanded=True):
  cols=st.columns(2)
  hold=money_input('유보액 (수동입력·부가세 포함)',initial.get('hold',initial.get('prior_balance','0')),key=key+'hold',where=cols[0])
  advance=money_input('선금반제 (수동입력·부가세 포함)',initial.get('advance','0'),key=key+'advance',where=cols[1])
  st.caption('수금·지급·하도급 지급은 해당 공사·당사의 기준일까지 누계입니다. 전회 잔액은 이전 기준월의 마지막 저장 현황에 연결된 원가정산서 미지급액입니다. 첫 현황의 전회 잔액은 0원입니다.')
 values=dict(aggregation='cumulative',as_of=as_of,contracts=contract_rows,source_doc=source_doc,hold=hold,advance=advance)
 data=None
 try:
  data=status.build(c,p,m['id'],run_id,month,values)
  cf=data['cash'];flow_rows=[{'구분':label,'입금 기준':int(db.num(cf[a])),'기성 기준':int(db.num(cf[b]))} for label,a,b in [('수입','income','earned'),('지출(전회까지)','previous','previous'),('지출(금회예정)','current','current'),('보험료·안분제외','extra','extra'),('지출총계','spending','spending'),('수입−지출','cash_balance','earned_balance')]]
  flow_preview.dataframe(pd.DataFrame(flow_rows),hide_index=True,use_container_width=True,column_config=aligned_config(flow_rows))
  st.markdown('### 지급 예정액 (부가세 포함)')
  pay=data['payment']
  amount_table([{'① 청구금액':pay['claim'],'② 기지급액':pay['paid'],'③ 전회미지급/유보액':pay['prior_balance'],'④ 당사투입비/선금반제':pay['offset'],'⑤ 지급예정액':pay['planned'],'⑥ 승인액':''}],['① 청구금액','② 기지급액','③ 전회미지급/유보액','④ 당사투입비/선금반제','⑤ 지급예정액'],footer=False)
  st.caption('④ = 안분대상 공급가액 + 선금반제 (안분제외액은 제외). ⑤ = ① − ② − ③ − ④. 금회예정 = ⑤ − 기준월까지 원가배분 VAT. ⑥ 승인액은 대표이사가 직접 작성합니다.')
  with st.expander('자동 집계 근거'):
   amount_table([{'항목':label,'금액':value} for label,value in [('전회 지급후 잔액',pay['previous_balance']),('유보액',pay['hold']),('당사투입비 안분대상 공급가액',pay['investment_offset']),('선금반제',pay['advance']),('원가정산서 미지급액',data['cash']['statement_remaining']),('기준월까지 원가배분 부가세',data['cash']['selected_vat'])]],['금액'],footer=False)
  st.markdown('### 원가정산서 하단 미리보기');components.html('<!doctype html><meta charset="utf-8">'+report.render(data),height=610,scrolling=True)
 except (ValueError,TypeError) as e:st.warning(str(e))
 cols=st.columns(3)
 if cols[0].button('현황 수정 저장' if selected else '현황 저장',type='primary',disabled=data is None,key=key+'save'):
  id=status.save(c,p,m['id'],run_id,month,values,selected,record.get('version'));st.session_state[base+'pending']=id;st.session_state['_jv_next_run']=[p,m['id'],run_id];done()
 if selected:
  check=cols[1].checkbox('현황 삭제 확인',key=key+'delete_confirm')
  if cols[2].button('현황 삭제',disabled=not check,key=key+'delete'):status.set_deleted(c,p,m['id'],selected,record['version'],True);st.session_state[base+'pending']=None;done()
 if data:
  st.download_button('현황 엑셀 다운로드',report.excel(data),file_name=f'당사투입비_기성_계약현황_{month}.xlsx',key=key+'xlsx')
 with st.expander('삭제 현황 복구'):
  removed=status.records(c,p,m['id'],deleted=True)
  if removed:
   lookup_removed={r['id']:r for r in removed};rid=st.selectbox('복구할 현황',list(lookup_removed),format_func=lambda id:lookup_removed[id]['month']+' / '+lookup_removed[id]['data']['run_name'],key=base+'restore')
   if st.button('현황 복구',key=base+'restore_btn'):status.set_deleted(c,p,m['id'],rid,lookup_removed[rid]['version'],False);st.session_state[base+'pending']=rid;done()
