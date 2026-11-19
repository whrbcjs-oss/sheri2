"""Preview, resolve, explicitly approve and atomically import historical Excel data."""
import hashlib,json
from datetime import datetime,timezone,timedelta
import pandas as pd
import streamlit as st
import related_loan_store as db
import related_loan_import as importer
from related_loan_app import table,action,excel

@st.cache_data(ttl=600,max_entries=3,show_spinner=False)
def parse(blob,corrections):return importer.read(blob,corrections)
def render(c):
 cos={r['id']:r for r in db.companies(c)}
 if not cos:st.info('거래회사거래/이율관리에서 조회회사를 먼저 등록하세요.');return
 basis=st.selectbox('엑셀 조회회사',list(cos),format_func=lambda id:cos[id]['name'],key='rl_import_basis')
 file=st.file_uploader('차입·대여 이자계산서 XLSX',type=['xlsx'],key='rl_import_file')
 st.caption('상세 계산표 기준으로 거래·상환·이율·월별 조정을 가져옵니다. 개인 차입 시트는 제외합니다. 수식은 실행하지 않으며 Excel에서 계산 후 저장된 결과를 읽습니다.')
 if file:
  blob=file.getvalue();key='rl_import_'+hashlib.sha256(blob).hexdigest()[:16]+'_'+str(basis)+'_'
  try:initial=parse(blob,{})
  except Exception as e:st.error('파일을 읽지 못했습니다. 정상 XLSX인지 확인하세요. '+str(e));return
  for s in initial['excluded']:st.caption('제외: '+s)
  selected=st.multiselect('가져올 회사 시트',[s['name'] for s in initial['sheets']],default=[s['name'] for s in initial['sheets']],key=key+'sheets')
  with st.expander('날짜 확인·수정 (원본은 변경하지 않음)',expanded=bool(initial['errors'])):
   rows=[dict(셀=t['date_cell'],원본=str(t['start'] or ''),구분='거래일',수정날짜='') for s in initial['sheets'] for t in s['trades'] if s['name'] in selected]
   rows += [dict(셀=r['key'],원본=r['raw'],구분=r['reason'],수정날짜='') for r in initial['errors']]
   rows=list({r['셀']:r for r in rows}.values())
   edits=st.data_editor(pd.DataFrame(rows),hide_index=True,use_container_width=True,disabled=['셀','원본','구분'],key=key+'dates') if rows else pd.DataFrame()
   corrections={r['셀']:str(r['수정날짜']).strip() for r in edits.to_dict('records') if str(r['수정날짜'] or '').strip()}
   st.caption('잘못된 날짜는 YYYY-MM-DD로 직접 확인해 입력하세요. 이율·일수·이자 캐시가 없는 경우 Excel에서 재계산·저장 후 다시 올리세요.')
  try:parsed=parse(blob,corrections)
  except Exception as e:st.error(str(e));return
  mapping={};new_names=[]
  st.subheader('회사 연결')
  for s in parsed['sheets']:
   if s['name'] not in selected:continue
   choices=[None]+[id for id in cos if id!=basis]
   normalize=lambda x:''.join(str(x).replace('㈜','').replace('(주)','').replace('주식회사','').split())
   matches=[id for id in choices if id is not None and normalize(cos[id]['name'])==normalize(s['party'])]
   widget_key=key+s['name']+'company'
   if widget_key+'pending' in st.session_state:st.session_state[widget_key]=st.session_state.pop(widget_key+'pending')
   partner=st.selectbox(s['name']+' → '+s['party'],choices,index=choices.index(matches[0]) if len(matches)==1 else 0,format_func=lambda id:'미연결' if id is None else cos[id]['name'],key=key+s['name']+'company');mapping[s['name']]=partner
   if partner is None:new_names.append(s['party'])
   for warning in s['warnings']:st.warning(s['name']+' · '+warning)
  if new_names:
   st.caption('미연결 회사명: '+', '.join(new_names))
   check=st.checkbox('시트 회사명으로 미등록 회사를 신규 등록합니다. 법인번호·대표자·이사는 나중에 보완합니다.',key=key+'new_confirm')
   if st.button('미연결 회사 일괄 등록',disabled=not check,key=key+'new'):
    def create():
     with c:
      for name in dict.fromkeys(new_names):
       if c.execute('SELECT 1 FROM rlc_companies WHERE name=?',(name,)).fetchone():raise ValueError('동일 이름이 이미 등록되었거나 삭제 목록에 있습니다. 회사 연결/복구하세요: '+name)
      created={}
      for name in dict.fromkeys(new_names):created[name]=c.execute('INSERT INTO rlc_companies(name,payload) VALUES(?,?)',(name,db.dump(dict(total_directors=0,directors=[])))).lastrowid
     for sheet in parsed['sheets']:
      if sheet['name'] in selected and sheet['party'] in created:st.session_state[key+sheet['name']+'companypending']=created[sheet['party']]
    action(create)
  table([{'시트':s['name'],'거래키':t['key'],'거래일':t['start'] or '확인 필요','원금':t['principal'],'계산월수':str(len(t['months'])),'만기':'원본 확인 필요'} for s in parsed['sheets'] if s['name'] in selected for t in s['trades']],['원금'])
  try:proposed=importer.propose(parsed,selected)
  except ValueError as e:st.error(str(e));proposed=[]
  allocations=[]
  if proposed:
   st.subheader('상환 배분 확인')
   st.caption('최초 제안은 오래된 거래 우선입니다. 원본 비고와 대조해 대상·금액을 수정하세요. 행을 나누어 여러 거래에 배분할 수 있습니다.')
   keys=[t['key'] for s in parsed['sheets'] if s['name'] in selected for t in s['trades']]
   frame=pd.DataFrame([{'상환키':r['payment'],'거래키':r['trade'],'배분액':r['amount']} for r in proposed])
   view=st.data_editor(frame,num_rows='dynamic',hide_index=True,use_container_width=True,column_config={'거래키':st.column_config.SelectboxColumn(options=keys),'배분액':st.column_config.NumberColumn(min_value=1,format='localized')},key=key+'alloc_'+hashlib.sha256(db.dump(selected).encode()).hexdigest()[:8])
   for r in view.to_dict('records'):
    if pd.isna(r.get('상환키')):continue
    allocations.append(dict(payment=r['상환키'],trade=r['거래키'],amount=r['배분액']))
  accepted=st.checkbox('상세 계산표를 기준으로 가져옵니다. 원금 집계 날짜 차이·상환 배분·수동 가감은 미리보기에서 확인하겠습니다.',key=key+'details')
  if st.button('등록 전 미리보기',type='primary',key=key+'preview'):
   try:
    plan=importer.prepare(c,parsed,basis,mapping,selected,allocations,accepted);st.session_state[key+'plan']=dict(data=plan,signature=db.dump(dict(mapping=mapping,selected=selected,alloc=allocations,corrections=corrections,revision=db.shared.revision(c))))
   except (ValueError,KeyError) as e:st.error(str(e))
  pending=st.session_state.get(key+'plan');signature=db.dump(dict(mapping=mapping,selected=selected,alloc=allocations,corrections=corrections,revision=db.shared.revision(c)))
  if pending and pending['signature']==signature:
   plan=pending['data'];st.success('거래 '+str(len(plan['plans']))+'건 · 등록 전 대조 결과')
   comparison=table([{'거래키':p['source'],'월':m['month'],'엑셀금액':m['excel'],'재계산액':m['recalculated'],'조정액':m['adjustment'],'연소계보정':m['year_adjustment']} for p in plan['plans'] for m in p['months']],['엑셀금액','재계산액','조정액','연소계보정'])
   st.download_button('대조 결과 엑셀',excel({'대조':comparison}),file_name='가져오기_대조.xlsx',key=key+'export')
   if plan['ledger_differences']:
    st.warning('별도 집계표와 상세 계산표가 다릅니다. 아래 차이는 자동 덮어쓰지 않고, 선택한 상세 계산표 기준으로 등록합니다.');table([{'시트':r['sheet'],'월':r['month'],'집계표금액':r['ledger'],'상세계산금액':r['details'],'원본셀':r['cell']} for r in plan['ledger_differences']],['집계표금액','상세계산금액'])
   st.info('과거 월별 이자 차이는 조정 사유와 함께 저장합니다. 원본에 없는 이자 지급·회수액은 추정 등록하지 않습니다. 미정산 잔액은 실제 입출금 보완 후 확인하세요. 만기는 미확인으로 등록하며 약정서를 확인하기 전 문서 확정은 제한됩니다. 엑셀 마지막 계산월 이후 이율은 별도로 등록해야 합니다.')
   confirm=st.checkbox('대조 차이·상환 배분·만기 미확인·엑셀 이후 이율 미등록을 확인하고 선택 자료를 등록합니다.',key=key+'confirm_'+hashlib.sha256(signature.encode()).hexdigest()[:10])
   if st.button('선택 자료 등록 실행',disabled=not confirm,key=key+'commit'):action(lambda:importer.commit(c,blob,file.name,basis,mapping,selected,allocations,corrections,plan,confirm))
  elif pending:st.caption('선택·연결·자료가 바뀌었습니다. 미리보기를 다시 만드세요.')
 st.subheader('가져오기 이력·되돌리기')
 history=importer.history(c);st.dataframe([dict(번호=r['id'],파일=r['filename'],**{'일시(KST)':datetime.fromisoformat(r['created_at']).replace(tzinfo=timezone.utc).astimezone(timezone(timedelta(hours=9))).strftime('%Y-%m-%d %H:%M:%S')},되돌림=bool(r['reverted'])) for r in history],hide_index=True)
 active=[r for r in history if not r['reverted']]
 if active:
  id=st.selectbox('되돌릴 가져오기',[r['id'] for r in active],format_func=lambda id:next(r['filename']+' / '+str(id) for r in active if r['id']==id),key='rl_import_undo')
  reason=st.text_input('되돌리기 사유',key='rl_import_undo_reason');confirm=st.checkbox('이 가져오기에서 새로 등록한 자료만 삭제 목록으로 이동합니다.',key='rl_import_undo_confirm')
  if st.button('가져오기 되돌리기',disabled=not confirm or not reason.strip(),key='rl_import_undo_execute'):action(lambda:importer.undo(c,id,reason))
