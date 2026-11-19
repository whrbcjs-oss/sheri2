"""Reviewed upload UI for a single counterparty borrower ledger."""
import hashlib,json
import pandas as pd
import streamlit as st
import related_loan_store as db
import related_loan_ledger as ledger
from related_loan_app import table,action,excel

def render(c):
 cos={r['id']:r for r in db.companies(c)}
 if len(cos)<2:st.info('거래회사거래/이율관리에서 양사를 먼저 등록하세요.');return
 a,b=st.columns(2);borrower=a.selectbox('차입회사',list(cos),format_func=lambda i:cos[i]['name'],key='lg_borrower');lender=b.selectbox('대여회사',[i for i in cos if i!=borrower],format_func=lambda i:cos[i]['name'],key='lg_lender')
 st.caption('현재 적용 기준: '+__import__('related_loan_exceptions').label(c,lender,borrower))
 st.caption('파일당 거래처 1개 · 대변은 신규 차입, 차변은 원금 상환입니다. 적요에 적힌 이율은 계산에서 제외합니다.')
 templates=[t for t in db.deals(c) if (t['borrower_id'],t['lender_id'])==(borrower,lender) and not t.get('import_rate_until')]
 if not templates:st.info('선택한 양사의 실제 약정 조건을 차입·대여 등록에 먼저 등록하세요. 회사 기본이율 방식이면 이율 관리에도 적용일별 이율이 필요합니다.');history(c,borrower,lender);return
 lookup={t['id']:t for t in templates};template=st.selectbox('신규 차입에 적용할 등록 약정',list(lookup),format_func=lambda i:lookup[i]['number'],key='lg_template')
 st.info('선택 약정의 일수·반올림 기준과 등록 이율을 사용합니다. 선택한 회사 방향의 예외이율이 있으면 예외이율, 그 외에는 날짜별 공통이율을 자동 적용합니다. 기준 약정은 일수·원 단위 처리 등 계산 조건으로 사용합니다. 기존 차입 건의 상환에는 해당 건의 약정을 유지합니다.')
 file=st.file_uploader('날짜·적요란·차변·대변 XLSX',type=['xlsx'],key='lg_file')
 if file:
  blob=file.getvalue();tag='lg_'+hashlib.sha256(blob).hexdigest()[:12]+'_'+str(borrower)+'_'+str(lender)+'_'+str(template)
  try:
   rows=ledger.read(blob);pool=ledger.choices(c,borrower,lender,rows);proposed=ledger.propose(c,borrower,lender,rows)
   table([{'원본행':r['key'],'날짜':r['date'],'적요':r['note'],'차변(상환)':r['debit'],'대변(차입)':r['credit']} for r in rows],['차변(상환)','대변(차입)'],True)
   allocations=[]
   if proposed:
    st.subheader('상환 배분 확인');st.caption('오래된 거래부터 제안합니다. 실제 상환 대상에 맞게 바꾸고, 필요하면 행을 추가해 나누세요.')
    v=st.data_editor(pd.DataFrame([{'상환행':x['payment'],'대상거래':x['trade'],'배분금액':x['amount']} for x in proposed]),num_rows='dynamic',hide_index=True,use_container_width=True,key=tag+'alloc',column_config={'대상거래':st.column_config.SelectboxColumn(options=list(pool)),'배분금액':st.column_config.NumberColumn(min_value=1,format='localized')})
    table([{'거래키':k,'관리번호':t['number'],'차입일':t['start'],'원금':t['principal']} for k,t in pool.items()],['원금'])
    allocations=[dict(payment=r['상환행'],trade=r['대상거래'],amount=r['배분금액']) for r in v.to_dict('records') if not pd.isna(r.get('상환행'))]
   sig=db.dump(dict(alloc=allocations,revision=db.shared.revision(c)))
   if st.button('등록 전 검증·미리보기',key=tag+'preview'):
    st.session_state[tag+'plan']=dict(signature=sig,plan=ledger.prepare(c,blob,borrower,lender,template,allocations))
   pending=st.session_state.get(tag+'plan')
   if pending and pending['signature']==sig:
    p=pending['plan'];st.success('신규 차입 '+str(len(p['new']))+'건 · 상환 배분 '+str(sum(len(v) for v in p['events'].values()))+'건 · 등록 가능')
    st.warning('차변에 이자 지급이 섞여 있으면 먼저 원본에서 분리하세요. 만기는 미확인으로 등록됩니다. 기준 약정이 실제 원장에도 적용되는지 확인하세요.')
    ack=st.checkbox('차변은 원금 상환이며, 등록 약정·상환 배분·만기 미확인을 확인했습니다.',key=tag+'ack')
    if st.button('선택 원장 등록',disabled=not ack,key=tag+'commit'):action(lambda:ledger.commit(c,blob,file.name,borrower,lender,template,allocations,p,ack))
   elif pending:st.caption('자료가 바뀌었습니다. 다시 검증하세요.')
  except (ValueError,KeyError,TypeError) as e:st.error(str(e))
 history(c,borrower,lender)

def history(c,borrower,lender):
 st.subheader('원장 가져오기 이력·되돌리기')
 hist=db.rows(c,'SELECT id,filename,reverted,created_at,payload FROM rlc_ledger_imports ORDER BY id DESC')
 hist=[r for r in hist if (json.loads(r['payload'])['plan']['borrower'],json.loads(r['payload'])['plan']['lender'])==(borrower,lender)]
 table([{'번호':str(r['id']),'파일':r['filename'],'등록일시(UTC)':r['created_at'],'상태':'되돌림' if r['reverted'] else '등록'} for r in hist])
 active={r['id']:r for r in hist if not r['reverted']}
 if active:
  id=st.selectbox('되돌릴 원장',list(active),format_func=lambda i:str(i)+' / '+active[i]['filename'],key='lg_undo_id');reason=st.text_input('원장 되돌리기 사유',key='lg_undo_reason');ok=st.checkbox('이 원장으로 만든 신규 차입과 상환만 삭제 목록으로 이동합니다. 기존 차입 원금은 유지합니다.',key='lg_undo_ack')
  if st.button('원장 가져오기 되돌리기',disabled=not ok or not reason.strip()):action(lambda:ledger.undo(c,id,reason))
