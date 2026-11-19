"""Intercompany loan workspace: daily interest, receipts, bilateral original-style prints."""
from datetime import date,timedelta,datetime,timezone
from io import BytesIO
import base64,hashlib,json
from zipfile import ZipFile,ZIP_DEFLATED
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
import collaboration as shared
import related_loan_store as db
import related_loan_calc as calc
import related_loan_report as report
from table_layout import aligned_config,format_excel
from joint_amounts import money_input

PAGES=['차입·대여 총현황','거래회사거래/이율관리','차입·대여 등록','원금·이자 입출금','이율 관리','월별 이자계산서','약정서·이사회결의서 일괄출력']
def today():return __import__('loan_store').today()
def action(fn,key=None):
 try:
  id=fn()
  if key:st.session_state[key+'pending']=id
  st.session_state['_rl_success']='저장했습니다.';st.rerun()
 except (ValueError,PermissionError) as e:st.error(str(e))
def picker(label,rows,key,new=True):
 lookup={r['id']:r for r in rows};choices=([None] if new else [])+list(lookup)
 if key+'pending' in st.session_state:st.session_state[key]=st.session_state.pop(key+'pending')
 if st.session_state.get(key) not in choices:st.session_state[key]=choices[0] if choices else None
 if not choices:st.info('등록 자료가 없습니다.');return None
 id=st.selectbox(label,choices,format_func=lambda id:'새 등록' if id is None else str(lookup[id].get('number') or lookup[id].get('name') or lookup[id].get('effective_date') or lookup[id].get('event_date') or id),key=key)
 return lookup.get(id)
def table(data,money=(),total=False):
 data=[dict(r) for r in data]
 if not data:st.caption('조회 자료가 없습니다.');return pd.DataFrame()
 if total:
  row={k:'' for k in data[0]};row[next(k for k in row if k not in money)]='합계'
  for k in money:row[k]=None if any(r.get(k) is None for r in data) else sum((calc.D(r.get(k,0)) for r in data),calc.D(0))
  data.append(row)
 for r in data:
  for k in money:r[k]=None if r.get(k) is None else int(calc.D(r[k]))
 frame=pd.DataFrame(data);style=frame.style.set_properties(**{'text-align':'center'})
 if money:style=style.set_properties(subset=list(money),**{'text-align':'right'}).format({k:lambda v:'—' if pd.isna(v) else f'{v:,.0f}' for k in money})
 indices=[i for i,row in enumerate(data) if any('소계' in str(value) for k,value in row.items() if k in ['구분','관리번호'])]
 if total:indices.append(len(frame)-1)
 if indices:style=style.set_properties(subset=pd.IndexSlice[sorted(set(indices)),:],**{'font-weight':'bold','background-color':'#e7f2eb'})
 st.dataframe(style,hide_index=True,use_container_width=True,column_config=aligned_config(frame,{k:st.column_config.NumberColumn(k,format='localized') for k in money}));return frame

def excel(sheets):
 out=BytesIO()
 with pd.ExcelWriter(out,engine='openpyxl') as writer:
  for title,frame in sheets.items():
   frame=frame.copy()
   for k in frame:
    if any(word in k for word in ['원금','이자','금액','잔액','증감','조정액','누계']) and not any(word in k for word in ['시작일','종료일','이율']):
     frame[k]=pd.to_numeric(frame[k],errors='coerce')
   frame.to_excel(writer,sheet_name=title,index=False);sheet=writer.sheets[title];format_excel(sheet);sheet.freeze_panes='A2'
   for col in sheet.columns:
    sheet.column_dimensions[col[0].column_letter].width=20
    for cell in col:
     if cell.data_type=='f':cell.data_type='s'
 return out.getvalue()
def table_print(title,frame):
 from html import escape
 money=[k for k in frame if any(word in k for word in ['원금','이자','금액','잔액','증감','조정액','누계']) and not any(word in k for word in ['시작일','종료일','이율'])]
 headers='<tr>'+''.join('<th>'+escape(str(k))+'</th>' for k in frame)+'</tr>';rows=[]
 for row in frame.to_dict('records'):
  cells=[]
  for k in frame:
   value=row[k]
   if pd.isna(value):text='—'
   else:text=f'{calc.D(value):,.0f}' if k in money else str(value)
   cells.append('<td class="'+('number' if k in money else 'text')+'">'+escape(text)+'</td>')
  subtotal=any('소계' in str(v) or str(v)=='합계' for v in row.values())
  rows.append('<tr'+(' class="subtotal"' if subtotal else '')+'>'+''.join(cells)+'</tr>')
 return '<!doctype html><html lang="ko"><meta charset="utf-8"><style>@page{size:A4 landscape;margin:20mm}body{font-family:"Malgun Gothic",sans-serif}table{border-collapse:collapse;width:100%;font-size:9pt}td,th{border:1px solid #9aaba1;padding:5px;text-align:center}td.number{text-align:right}th{background:#e6f1eb}tr.subtotal{font-weight:bold;background:#e7f2eb}thead{display:table-header-group}tr{break-inside:avoid}@media print{button{display:none}}</style><button onclick="window.print()">인쇄 / PDF 저장</button><h2>'+escape(title)+'</h2><table><thead>'+headers+'</thead><tbody>'+''.join(rows)+'</tbody></table></html>'


def deletion(c,kind,r,key):
 if not r:return
 with st.expander('선택 자료 삭제'):
  reason=st.text_input('삭제 사유',key=key+'reason');ok=st.checkbox('선택 자료를 삭제 목록으로 이동합니다. 관련 확정 자료가 있으면 제한됩니다.',key=key+'confirm')
  if st.button('선택 자료 삭제',disabled=not ok or not reason.strip(),key=key+'delete'):
   action(lambda:db.set_deleted(c,kind,r['id'],r['version'],True,reason),key=None)
def restoration(c,kind,rows,key):
 with st.expander('삭제 내역·복구'):
  r=picker('복구할 자료',rows,key+'restore',False)
  if r:
   reason=st.text_input('복구 사유',key=key+'restore_reason');ok=st.checkbox('선택 자료 복구 확인',key=key+'restore_check')
   if st.button('선택 자료 복구',disabled=not ok or not reason.strip(),key=key+'restore_btn'):action(lambda:db.set_deleted(c,kind,r['id'],r['version'],False,reason))

def company_page(c):
 rows=db.companies(c);base='rl_company_';r=picker('등록·수정할 회사',rows,base) or {};key=base+str(r.get('id'))+'_'+str(r.get('version',0))
 st.caption('조회회사와 거래회사를 등록하세요. 회사는 계속 추가할 수 있고 회사별 대표이사·출석이사 정보를 문서에 사용합니다.')
 a,b=st.columns(2);v=dict(name=a.text_input('회사명',r.get('name',''),key=key+'name'),registration=b.text_input('법인등록번호',r.get('registration',''),key=key+'registration'))
 a,b=st.columns(2);v['representative']=a.text_input('대표이사',r.get('representative',''),key=key+'representative');v['phone']=b.text_input('회사 연락처',r.get('phone',''),key=key+'phone')
 v['address']=st.text_input('회사 주소',r.get('address',''),key=key+'address')
 a,b=st.columns(2);v['place']=a.text_input('회의 장소',r.get('place','본사 회의실'),key=key+'place');v['total_directors']=b.number_input('이사 총수',min_value=0,max_value=100,value=int(r.get('total_directors',0)),key=key+'total')
 frame=pd.DataFrame([{'직위':d['role'],'성명':d['name'],'출석':d['present']} for d in r.get('directors',[])] or [{'직위':'대표이사','성명':'','출석':True}])
 edited=st.data_editor(frame,num_rows='dynamic',hide_index=True,use_container_width=True,key=key+'directors',column_config={'출석':st.column_config.CheckboxColumn(default=True)})
 v['directors']=[dict(role='' if pd.isna(x.get('직위')) else str(x.get('직위') or ''),name='' if pd.isna(x.get('성명')) else str(x.get('성명') or ''),present=False if pd.isna(x.get('출석')) else bool(x.get('출석',False))) for x in edited.to_dict('records')]
 with st.expander('결의서 기본 본문 · 회사 직인'):
  v['lending_intro']=st.text_area('대여 승인 기본 본문 (빈칸은 원본 양식 기본 문구)',r.get('lending_intro',''),key=key+'lending')
  v['borrowing_intro']=st.text_area('차입 승인 기본 본문 (빈칸은 자금차입 기본 문구)',r.get('borrowing_intro',''),key=key+'borrowing');st.caption('{상대회사}는 거래 상대회사명으로 바뀝니다.')
  seal=st.file_uploader('회사 직인 PNG/JPG · 1MB 이하',type=['png','jpg','jpeg'],key=key+'seal')
  v['seal']=r.get('seal','')
  if v['seal']:st.image(v['seal'],width=80)
  clear=st.checkbox('등록 직인 삭제',key=key+'clear_seal')
  if clear:v['seal']=''
 def save():
  if seal:
   from joint_letter_files import packed
   from PIL import Image
   data=seal.getvalue()
   if len(data)>1024*1024:raise ValueError('직인은 1MB 이하로 올리세요.')
   with Image.open(BytesIO(data)) as im:
    if max(im.size)>3000:raise ValueError('직인 가로·세로는 3000픽셀 이하로 올리세요.')
   f=packed(seal.name,data);v['seal']='data:'+f['mime']+';base64,'+f['content']
  return db.save_company(c,v,r.get('id'),r.get('version'))
 if st.button('회사 수정 저장' if r else '회사 등록',type='primary',key=key+'save'):action(save,base)
 table([{'회사번호':str(x['id']),'회사명':x['name'],'대표이사':x.get('representative',''),'이사총수':str(x.get('total_directors',0))} for x in rows])
 deletion(c,'companies',r,key);restoration(c,'companies',db.companies(c,True),base)

def choose_deal(c,company,key):return picker('대상 거래',db.deals(c,company),key,False)
def deal_page(c,company,cos):
 base='rl_deal_'+str(company)+'_';r=picker('등록·수정할 거래',db.deals(c,company),base) or {};key=base+str(r.get('id'))+'_'+str(r.get('version',0));ids=list(cos)
 a,b,d=st.columns([1,1,2]);kind=a.selectbox('조회회사 입장',['차입','대여'],index=1 if r.get('lender_id')==company else 0,key=key+'kind');other=[id for id in ids if id!=company]
 if not other:st.info('거래 상대회사를 먼저 추가하세요.');return
 counter=r.get('borrower_id') if kind=='대여' else r.get('lender_id');counter=b.selectbox('상대회사',other,index=other.index(counter) if counter in other else 0,format_func=lambda id:cos[id]['name'],key=key+'counter')
 v=dict(number=d.text_input('관리번호',r.get('number',''),key=key+'number'),lender_id=company if kind=='대여' else counter,borrower_id=counter if kind=='대여' else company)
 v['title']=st.text_input('계약명',r.get('title',''),key=key+'title')
 a,b,d=st.columns(3);v['start']=a.date_input('거래일',calc.day(r.get('start',today())),key=key+'start');v['interest_start']=b.date_input('이자 계산 시작일',calc.day(r.get('interest_start',v['start'])),key=key+'interest_start');v['maturity']=d.date_input('만기일',calc.day(r.get('maturity') or __import__('loan_calc').add_months(v['start'],12)),key=key+'maturity')
 a,b=st.columns([1,2]);v['principal']=money_input('약정 원금',r.get('principal',0),key=key+'principal',where=a);v['rate_mode']=r.get('rate_mode','회사 기본이율');v['rate']=r.get('rate','');b.info(__import__('related_loan_exceptions').label(c,v['lender_id'],v['borrower_id'])+' 자동 적용 · 계약별 선택 불필요')
 with st.expander('일수·원 단위 처리 기준',expanded=not bool(r)):
  a,b=st.columns(2);v['first_inclusive']=a.checkbox('이자 계산 시작일 포함',value=r.get('first_inclusive',True),key=key+'first');v['repay_inclusive']=b.checkbox('상환일 이자 포함 (원금 감소는 다음날부터)',value=r.get('repay_inclusive',True),key=key+'last')
  a,b,d=st.columns(3);v['basis']=a.selectbox('연간 일수',['365','실제연도'],index=1 if r.get('basis')=='실제연도' else 0,key=key+'basis');v['rounding']=b.selectbox('원 단위 처리',['절사','반올림'],index=1 if r.get('rounding')=='반올림' else 0,key=key+'rounding');v['rounding_unit']=d.selectbox('처리 시점',['월 합계','구간별'],index=1 if r.get('rounding_unit')=='구간별' else 0,key=key+'roundunit')
  v['kb']=st.text_input('KB 참고 연이율 (%) · 계산에는 약정이율 사용',r.get('kb') or '',key=key+'kb')
 if r.get('maturity_unverified'):
  st.warning('엑셀에 만기일이 없어 미확인 상태입니다. 아래 날짜는 제안값이며 원본 약정으로 확인해야 문서 발행이 가능합니다.')
  v['maturity_verified']=st.checkbox('원본 약정으로 만기일을 확인했습니다.',key=key+'maturity_verified')
 v['purpose']=st.text_area('자금 용도',r.get('purpose',''),key=key+'purpose');v['collateral']=st.text_area('담보 조건 · 없으면 없음',r.get('collateral',''),key=key+'collateral');v['repayment']=st.text_input('상환방법',r.get('repayment','원리금 일시상환'),key=key+'repayment');v['collateral_list']=st.checkbox('결의서에 담보 물건 목록 첨부 문구 표시',r.get('collateral_list',False),key=key+'collist')
 with st.expander('약정서·결의서 개별 조항 문구 (빈칸은 원본 기본 구성)'):
  for k,label in [('agreement_maturity','약정서 제2조 상환기일'),('agreement_interest','약정서 제3조 이자율'),('agreement_calculation','약정서 제4조 계산방법'),('agreement_interest_payment','약정서 제5조 이자수수방법'),('board_maturity','결의서 상환일자 문구'),('board_interest','결의서 이자적용 문구')]:v[k]=st.text_area(label,r.get(k,''),key=key+k)
 with st.expander('문서별 작성일·양사 회의일'):
  a,b,d=st.columns(3);v['agreement_date']=a.date_input('등록 약정서 작성일',calc.day(r.get('agreement_date',v['start'])),key=key+'agreement_date');v['lender_meeting']=b.date_input('대여회사 회의일',calc.day(r.get('lender_meeting',v['start'])),key=key+'lender_meeting');v['borrower_meeting']=d.date_input('차입회사 회의일',calc.day(r.get('borrower_meeting',v['start'])),key=key+'borrower_meeting')
 v['note']=st.text_input('비고',r.get('note',''),key=key+'note')
 if st.button('거래 수정 저장' if r else '차입·대여 등록',type='primary',key=key+'save'):action(lambda:db.save_deal(c,v,r.get('id'),r.get('version')),base)
 deletion(c,'deals',r,key);restoration(c,'deals',db.deals(c,company,True),base)
 if r:
  with st.expander('계약서·증빙 등록/교체·조회·삭제·복구'):
   fs=[f for f in db.entities(c,'files') if f['deal_id']==r['id']];f=picker('계약서·증빙 선택',fs,key+'file_')
   upload=st.file_uploader('계약서·증빙 파일',type=['pdf','hwp','hwpx','doc','docx','xlsx','png','jpg','jpeg','txt'],key=key+'file_up')
   if st.button('증빙 교체' if f else '증빙 등록',disabled=not upload,key=key+'file_save'):action(lambda:db.save_file(c,r['id'],upload.name,upload.getvalue(),f['id'] if f else None,f['version'] if f else None))
   from joint_letter_files import unpack
   for file in fs:st.download_button(file['name'],unpack(file),file_name=file['name'],key=key+'file_down_'+str(file['id']))
   deletion(c,'files',f,key+'file_');restoration(c,'files',[f for f in db.entities(c,'files',True) if f['deal_id']==r['id']],key+'files_')

def event_page(c,company):
 t=choose_deal(c,company,'rl_event_deal_'+str(company))
 if not t:return
 base='rl_events_'+str(t['id'])+'_';r=picker('입출금 불러오기',db.events(c,t['id']),base) or {};key=base+str(r.get('id'))+'_'+str(r.get('version',0))
 kinds=['추가원금','원금상환·회수','이자지급·수취','원리금정산'];a,b=st.columns(2);v=dict(event_date=a.date_input('입출금일',calc.day(r.get('event_date',today())),key=key+'date'),kind=b.selectbox('입출금 구분',kinds,index=kinds.index(r.get('kind',kinds[1])),key=key+'kind'))
 a,b=st.columns(2);v['principal']=money_input('원금 금액',r.get('principal',0),key=key+'principal',where=a);v['interest']=money_input('지급·수취 이자',r.get('interest',0),key=key+'interest',where=b);v['note']=st.text_input('적요·정산 대상월 등',r.get('note',''),key=key+'note')
 if st.button('입출금 수정 저장' if r else '입출금 등록',type='primary',key=key+'save'):action(lambda:db.save_event(c,t['id'],v,r.get('id'),r.get('version')),base)
 table([{'번호':str(e['id']),'처리일':e['event_date'],'구분':e['kind'],'원금':e['principal'],'이자':e['interest'],'비고':e['note']} for e in db.events(c,t['id'])],['원금','이자'],True)
 deletion(c,'events',r,key);restoration(c,'events',[r for r in db.entities(c,'events',True) if r['deal_id']==t['id']],base)

def rate_page(c,company=None,cos=None):
 tab=st.radio('이율 구분',['공통이율','회사별 예외이율'],horizontal=True,key='rl_rate_kind')
 if tab=='공통이율':common_rate_page(c,company,cos)
 else:
  from related_loan_exception_app import render as exception_render
  exception_render(c)

def common_rate_page(c,company=None,cos=None):
 base='rl_common_rates_';pool=db.entities(c,'common_rates');r=picker('공통이율 불러오기',pool,base) or {};key=base+str(r.get('id'))+'_'+str(r.get('version',0))
 st.info('적용 시작일과 연이율만 등록하면 회사별 예외를 제외한 관계사 차입·대여 전체 계약에 자동 적용합니다. 계약별·회사별 선택은 필요하지 않습니다. 확정 월과 발행본은 기존 결과를 보존합니다.')
 a,b,d=st.columns(3);dt=a.date_input('이율 적용 시작일',calc.day(r.get('effective_date',today())),key=key+'date');rate=b.text_input('공통 연이율 (%)',r.get('rate',''),key=key+'rate');kb=d.text_input('KB 참고이율 (%)',r.get('kb') or '',key=key+'kb');note=st.text_input('변경 사유·비고',r.get('note',''),key=key+'note')
 if st.button('이율 수정 저장' if r else '이율 등록',type='primary',key=key+'save'):action(lambda:db.save_common_rate(c,dict(effective_date=dt,rate=rate,kb=kb,note=note),r.get('id'),r.get('version')),base)
 table([{'적용 시작일':x['effective_date'],'공통 연이율(%)':x['rate'],'KB 참고이율(%)':x['kb'] or '', '적용범위':'예외 회사 외 전체 계약','비고':x['note']} for x in sorted(pool,key=lambda x:x['effective_date'])])
 if not pool:st.warning('공통이율을 등록하거나 아래에서 기존 회사 간 기본이율을 가져오세요. 최초 계산일 이전 또는 당일의 이율부터 등록해야 합니다.')
 deletion(c,'common_rates',r,key);restoration(c,'common_rates',db.entities(c,'common_rates',True),base)
 with st.expander('기존 회사 간 기본이율을 공통으로 가져오기'):
  st.caption('기존 이율은 자동으로 선택하지 않습니다. 같은 적용일의 회사별 이율이 서로 다르면 가져오지 않습니다. 기존 개별 이율 기록은 보존하며, 공통이율 등록 후에는 전체 계약이 공통이율을 사용합니다.')
  try:
   candidates=db.common_rate_candidates(c)
   table([{'적용 시작일':x['effective_date'],'공통 연이율(%)':x['rate']} for x in candidates])
   ack=st.checkbox('위 이율을 전체 관계사 계약의 공통이율로 적용합니다.',key='rl_common_copy_ack')
   if st.button('기존 기본이율 일괄 가져오기',disabled=not ack or not candidates):action(lambda:db.copy_common_rates(c,candidates))
  except ValueError as ex:st.warning(str(ex))


def overview(c,company,cos,month=None):
 if month is None:month=st.text_input('기준월 (YYYY-MM)',today().strftime('%Y-%m'),key='rl_overview_month')
 end=calc.month_end(month);before=calc.day(month+'-01')-timedelta(days=1);data=[];errors=[]
 for t in db.deals(c,company):
  if calc.day(t['start'])>end:continue
  kind='대여' if t['lender_id']==company else '차입';counter=t['borrower_id'] if kind=='대여' else t['lender_id'];es=db.events(c,t['id']);v=calc.balance(t,es,end);previous=calc.balance(t,es,before)
  try:monthly=db.calculate(c,t['id'],month)['final_interest'];s=db.totals(c,t,end);unpaid=s['unpaid']
  except ValueError as e:errors.append(t['number']+': '+str(e));monthly=unpaid=None
  data.append({'구분':kind,'상대회사':cos[counter]['name'],'관리번호':t['number'],'전월 원금잔액':str(previous),'당월 증감':str(v-previous),'월말 원금잔액':str(v),'당월 이자':monthly,'미정산 이자':unpaid})
 for error in errors:st.warning(error)
 columns=st.columns(4)
 for col,kind,field,label in [(columns[0],'차입','월말 원금잔액','차입원금 잔액'),(columns[1],'차입','미정산 이자','미지급 차입이자'),(columns[2],'대여','월말 원금잔액','대여원금 잔액'),(columns[3],'대여','미정산 이자','미수 대여이자')]:
  values=[r[field] for r in data if r['구분']==kind];col.metric(label,'확인 필요' if any(v is None for v in values) else report.money(sum((calc.D(v) for v in values),calc.D(0)))+'원')
 grouped=[]
 for kind,name in sorted({(r['구분'],r['상대회사']) for r in data}):
  items=[r for r in data if (r['구분'],r['상대회사'])==(kind,name)];row={'구분':kind,'상대회사':name}
  for k in ['전월 원금잔액','당월 증감','월말 원금잔액','당월 이자','미정산 이자']:row[k]=None if any(r[k] is None for r in items) else str(sum((calc.D(r[k]) for r in items),calc.D(0)))
  grouped.append(row)
 grouped_with_subtotals=[]
 for kind in ['차입','대여']:
  items=[r for r in grouped if r['구분']==kind]
  grouped_with_subtotals+=items
  if items:
   subtotal={'구분':kind+' 소계','상대회사':''}
   for k in ['전월 원금잔액','당월 증감','월말 원금잔액','당월 이자','미정산 이자']:subtotal[k]=None if any(r[k] is None for r in items) else str(sum((calc.D(r[k]) for r in items),calc.D(0)))
   grouped_with_subtotals.append(subtotal)
 frame=table(grouped_with_subtotals,['전월 원금잔액','당월 증감','월말 원금잔액','당월 이자','미정산 이자'])
 with st.expander('거래 건별 원금·이자 상세',expanded=False):table(data,['전월 원금잔액','당월 증감','월말 원금잔액','당월 이자','미정산 이자'])
 st.caption('선택 월 말일 기준이며 미확정 이자는 예상 계산액입니다. 미정산 이자가 음수이면 이자를 미리 정산한 금액입니다. 차입·대여를 상계하지 않고 구분합니다.')
 if not frame.empty:
  with st.container(horizontal=True):st.download_button('현황표 인쇄 HTML',table_print(cos[company]['name']+' '+month+' 차입·대여 총현황',frame),file_name='관계사_총현황.html');st.download_button('현황 엑셀 다운로드',excel({'총현황':frame,'거래별상세':pd.DataFrame(data)}),file_name='관계사_총현황.xlsx')

def month_detail_page(c,company,cos,user):
 a,b=st.columns(2);month=a.text_input('계산월 (YYYY-MM)',today().strftime('%Y-%m'),key='rl_calc_month');calc.period(month)
 ds=[t for t in db.deals(c,company) if t['interest_start'][:7]<=month]
 t=picker('상세 계산 거래',ds,'rl_calc_deal_'+str(company),False)
 if not t:return
 try:s=db.calculate(c,t['id'],month)
 except ValueError as e:st.warning(str(e));return
 old=db.month_record(c,t['id'],month);key='rl_month_'+str(t['id'])+'_'+month+'_'+str(old['version'] if old else 0)
 parts=[{'계산 시작일':r['start'],'계산 종료일':r['end'],'계산 원금':r['principal'],'일수':r['days'],'약정 연이율(%)':r['rate'],'KB 참고이율(%)':r['kb'] or '', '연간일수':str(r['denominator']),'구간 이자':r['interest']} for r in s['segments']]
 st.caption('산식: 원금 × 일수 ÷ 연간일수 × 약정 연이율. KB 이율은 참고값입니다. 구간 이자 표시와 월 합계 처리 시점에 따라 원 단위 차이가 날 수 있습니다.')
 detail=table(parts,['계산 원금','구간 이자'])
 a,b,d=st.columns(3);a.metric('자동 계산 이자',report.money(s['calculated'])+'원');adjustment=money_input('조정 금액 (차감은 음수)',s.get('adjustment',0),key=key+'adjust',where=b);reason=d.text_input('조정 사유',s.get('adjustment_reason',''),key=key+'reason')
 try:st.metric('최종 이자',report.money(calc.D(s['calculated'])+calc.D(adjustment))+'원')
 except ValueError:st.warning('조정 금액을 확인하세요.')
 is_final=bool(old and old['final']);st.success('월 계산 확정 · 저장 당시 계산 근거 보관') if is_final else st.info('미확정 계산 · 원금·이율이 바뀌면 다시 계산합니다.')
 a,b=st.columns(2)
 if a.button('계산·조정 저장',disabled=is_final,key=key+'save'):action(lambda:db.save_month(c,t['id'],month,adjustment,reason,False,old['version'] if old else None))
 confirm=b.checkbox('월 계산 결과 확인',key=key+'confirm')
 if b.button('월 계산 확정',disabled=is_final or not confirm,key=key+'final'):action(lambda:db.save_month(c,t['id'],month,adjustment,reason,True,old['version'] if old else None))
 if is_final and user['admin']:
  with st.expander('관리자 월 확정 해제'):
   why=st.text_input('확정 해제 사유',key=key+'reopen_reason')
   if st.button('확정 해제',key=key+'reopen',disabled=not why.strip()):action(lambda:db.reopen(c,t['id'],month,st.session_state['_auth_token'],why))
 st.markdown('### 회사별 월 이자 합계 · 연간 누계')
 totals=[]
 for loan in ds:
  counter=loan['borrower_id'] if loan['lender_id']==company else loan['lender_id']
  try:
   current=db.calculate(c,loan['id'],month);annual=sum(db.calculate(c,loan['id'],m)['final_interest'] for m in calc.months(max(calc.day(loan['interest_start']),date(int(month[:4]),1,1)),calc.month_end(month)))
   totals.append({'구분':'대여' if loan['lender_id']==company else '차입','상대회사':cos[counter]['name'],'관리번호':loan['number'],'계산 이자':current['calculated'],'조정액':current['adjustment'],'월 확정·예상 이자':current['final_interest'],'해당년 누계':annual,'상태':'확정' if (db.month_record(c,loan['id'],month) or {}).get('final') else '미확정'})
  except ValueError as e:
   st.warning(loan['number']+': '+str(e));totals.append({'구분':'대여' if loan['lender_id']==company else '차입','상대회사':cos[counter]['name'],'관리번호':loan['number'],'계산 이자':None,'조정액':None,'월 확정·예상 이자':None,'해당년 누계':None,'상태':'이율 확인 필요'})
 grouped=[]
 for direction,name in sorted({(r['구분'],r['상대회사']) for r in totals}):
  items=[r for r in totals if (r['구분'],r['상대회사'])==(direction,name)];grouped+=items
  grouped.append({'구분':direction,'상대회사':name,'관리번호':'회사 소계',**{k:None if any(r[k] is None for r in items) else sum(calc.D(r[k]) for r in items) for k in ['계산 이자','조정액','월 확정·예상 이자','해당년 누계']},'상태':'이율 확인 필요' if any(r['계산 이자'] is None for r in items) else '확정' if all(r['상태']=='확정' for r in items) else '미확정 포함'})
 frame=table(grouped,['계산 이자','조정액','월 확정·예상 이자','해당년 누계'])
 if not frame.empty:
  with st.container(horizontal=True):st.download_button('이자계산서 인쇄 HTML',table_print(cos[company]['name']+' '+month+' 이자계산서',frame),file_name='관계사_이자계산서.html');st.download_button('이자계산서 엑셀',excel({'월집계':frame,'거래별구간':detail}),file_name='관계사_이자계산서.xlsx')

def month_page(c,company,cos,user):
 tab=st.radio('이자계산서 보기',['차입 건별 월별 명세','월 계산·조정·확정'],horizontal=True,key='rl_month_view')
 if tab=='월 계산·조정·확정':month_detail_page(c,company,cos,user);return
 from related_loan_monthly_app import render as monthly_render
 monthly_render(c,company,cos,user)

@st.cache_data(max_entries=6,ttl=600,show_spinner=False)
def pdf_bytes(documents):return report.pdf(documents)
@st.cache_data(max_entries=4,ttl=600,show_spinner=False)
def zip_bytes(data):return report.bundle(data)
def downloads(data,key):
 docs=[doc for item in data['items'] for doc in item['documents']]
 st.caption('약정서는 양사 보관용으로 동일 내용 2부, 결의서는 대여·차입 회사 기준으로 각각 1부입니다. 단건 기본 4부이며 긴 본문·많은 이사는 다음 페이지로 이어집니다.')
 with st.container(horizontal=True):
  st.download_button('일괄 인쇄 HTML',report.html(docs).encode(),file_name='양사_약정서_결의서.html',key=key+'html')
  if st.button('PDF·ZIP 파일 준비',key=key+'prepare'):st.session_state[key+'ready']=True
 if st.session_state.get(key+'ready'):
  with st.spinner('출력 파일을 준비합니다…'):
   pdf=pdf_bytes(docs);zip_=zip_bytes(data)
  with st.container(horizontal=True):
   st.download_button('전체 PDF 다운로드',pdf,file_name='양사_약정서_결의서.pdf',mime='application/pdf',key=key+'pdf');st.download_button('개별 문서·첨부 ZIP',zip_,file_name='양사_약정서_결의서.zip',mime='application/zip',key=key+'zip')
 components.html(report.html(docs),height=1000,scrolling=True)

def batch_page(c,company,cos):
 base='rl_print_'+str(company)+'_';a,b,d=st.columns(3);unit=a.selectbox('출력 기준',['해당월','해당년'],key=base+'unit')
 if unit=='해당월':
  month=b.text_input('대상월 (YYYY-MM)',today().strftime('%Y-%m'),key=base+'month');start=calc.day(calc.period(month)+'-01');end=calc.month_end(month)
 else:
  year=b.number_input('대상년도',1990,2100,today().year,key=base+'year');start=date(year,1,1);end=date(year,12,31)
 kind=d.selectbox('거래구분',['전체','차입','대여'],key=base+'kind');mode=st.radio('대상 거래 범위',['기간 내 등록 거래','기간 중 원금 보유·변동 거래'],horizontal=True,key=base+'mode')
 pool=db.candidates(c,company,start,end,mode);pool=[r for r in pool if kind=='전체' or ('대여' if r['lender_id']==company else '차입')==kind]
 opts=sorted({r['borrower_id'] if r['lender_id']==company else r['lender_id'] for r in pool});counter=st.selectbox('상대회사 조회',[None]+opts,format_func=lambda id:'전체' if id is None else cos[id]['name'],key=base+'counter')
 if counter:pool=[r for r in pool if counter in (r['lender_id'],r['borrower_id'])]
 frame=pd.DataFrame([{'선택':False,'거래번호':r['id'],'관리번호':r['number'],'대여회사':cos[r['lender_id']]['name'],'차입회사':cos[r['borrower_id']]['name'],'거래일':r['start'],'약정원금':int(calc.D(r['principal'])),'만기일':r['maturity']} for r in pool])
 selected=[]
 if not frame.empty:
  grid_scope=base+'grid_'+str(start)+str(end)+mode+kind+str(counter)
  a,b=st.columns([1,4])
  if a.button('조회 대상 전체 선택',key=grid_scope+'all'):
   st.session_state[grid_scope+'initial']=True;st.session_state[grid_scope+'rev']=st.session_state.get(grid_scope+'rev',0)+1
  if b.button('선택 해제',key=grid_scope+'none'):
   st.session_state[grid_scope+'initial']=False;st.session_state[grid_scope+'rev']=st.session_state.get(grid_scope+'rev',0)+1
  frame['선택']=st.session_state.get(grid_scope+'initial',False)
  view=st.data_editor(frame,hide_index=True,use_container_width=True,disabled=[k for k in frame if k!='선택'],column_config=aligned_config(frame,{'선택':st.column_config.CheckboxColumn(),'약정원금':st.column_config.NumberColumn(format='localized')}),key=grid_scope+'_'+str(st.session_state.get(grid_scope+'rev',0)))
  selected=[int(r['거래번호']) for r in view.to_dict('records') if r['선택']]
 else:st.info('선택 기간의 출력 대상 거래가 없습니다.')
 a,b,d=st.columns(3);issued=a.date_input('약정서 작성일',today(),key=base+'issued');meeting=b.date_input('양사 회의일',today(),key=base+'meeting');rate_until=d.date_input('약정 이율 적용 종료일 (제3조)',date(end.year,12,31),key=base+'rate_until_'+str(end.year));include=st.checkbox('등록된 계약서·증빙 원본을 ZIP에 함께 보관',key=base+'files')
 registered_dates=st.checkbox('거래별 등록 작성일·회의일 사용 (해제 시 위 날짜로 일괄 적용)',value=True,key=base+'registered_dates')
 signature=db.dump(dict(ids=selected,issued=issued,meeting=meeting,end=end,rate_until=rate_until,registered_dates=registered_dates,include=include,revision=shared.revision(c)))
 if st.button('선택 문서 미리보기',disabled=not selected,key=base+'preview',type='primary'):
  try:
   data=db.prepare_batch(c,company,selected,issued,meeting,end,include,False,rate_until,registered_dates);st.session_state[base+'preview_data']=(signature,data)
  except ValueError as e:st.warning(str(e))
 pending=st.session_state.get(base+'preview_data')
 if pending and pending[0]==signature:
  data=pending[1];st.info(f"거래 {len(data['items'])}건 · 기본 문서 {len(data['items'])*4}부")
  ok=st.checkbox('양사 회사정보·참석이사·금액·기간·이율·문구를 확인했습니다.',key=base+'confirm_'+hashlib.sha256(signature.encode()).hexdigest()[:12])
  if st.button('일괄 출력 발행본 저장',disabled=not ok,key=base+'save'):
   action(lambda:db.save_batch(c,data,st.session_state['_auth_token']))
  downloads(data,base+'preview_'+hashlib.sha256(signature.encode()).hexdigest()[:12])
 elif pending:st.caption('대상·조건·자료가 변경되었습니다. 미리보기를 다시 만드세요.')
 st.markdown('### 저장 발행본 조회·재출력')
 batches=[r for r in db.entities(c,'batches') if r['basis_company']==company];r=picker('저장 발행본',batches,base+'archive',False)
 if r:
  st.caption(r['number']+' · '+datetime.fromisoformat(r['created_at']).replace(tzinfo=timezone.utc).astimezone(timezone(timedelta(hours=9))).strftime('%Y-%m-%d %H:%M:%S')+' KST · '+r['actor'])
  if st.checkbox('저장 발행본 미리보기·다운로드',key=base+'show_'+str(r['id'])):downloads(r,base+'archive_'+str(r['id']))
  with st.expander('선택 발행본 삭제'):
   reason=st.text_input('발행본 삭제 사유',key=base+'archive_reason');ok=st.checkbox('선택 발행본을 삭제 목록으로 이동',key=base+'archive_check')
   if st.button('발행본 삭제',disabled=not ok or not reason.strip(),key=base+'archive_delete'):action(lambda:db.set_batch_deleted(c,r['id'],True,reason))
 with st.expander('삭제 발행본 복구'):
  removed=[r for r in db.entities(c,'batches',True) if r['basis_company']==company];r=picker('복구할 발행본',removed,base+'deleted',False)
  if r:
   why=st.text_input('발행본 복구 사유',key=base+'archive_restore_reason');ok=st.checkbox('발행본 복구 확인',key=base+'archive_restore_check')
   if st.button('발행본 복구',disabled=not ok or not why.strip(),key=base+'archive_restore'):action(lambda:db.set_batch_deleted(c,r['id'],False,why))

def render(user):
 c=db.connect();page=st.session_state.get('related_loan_page',PAGES[0])
 with st.sidebar:
  for name in [p for p in PAGES if p!='이율 관리']+['원장 업로드','기존 엑셀 가져오기']:
   if st.button('약정서·결의서 일괄출력' if name==PAGES[6] else name,key='related_nav_'+name,use_container_width=True,type='primary' if page==name else 'secondary'):st.session_state['related_loan_page']=name;st.rerun()
 st.subheader(page)
 if st.session_state.get('_rl_success'):st.success(st.session_state.pop('_rl_success'))
 if page==PAGES[1]:
  tab=st.radio('관리 항목',['회사정보 관리','이율 관리'],horizontal=True,key='rl_company_rate_tab')
  if tab=='회사정보 관리':company_page(c);return
  rate_page(c);return
 if page=='원장 업로드':
  from related_loan_ledger_app import render as ledger_render
  ledger_render(c);return
 if page=='기존 엑셀 가져오기':
  from related_loan_import_app import render as import_render
  import_render(c);return
 cos={r['id']:r for r in db.companies(c)}
 if not cos:st.info('거래회사거래/이율관리에서 조회회사와 상대회사 정보를 먼저 등록하세요.');return
 if page==PAGES[0]:
  a,b=st.columns([2,1]);company=a.selectbox('조회회사',list(cos),format_func=lambda id:cos[id]['name'],key='rl_basis_company');month=b.text_input('기준월 (YYYY-MM)',today().strftime('%Y-%m'),key='rl_overview_month')
 else:company=st.selectbox('조회회사',list(cos),format_func=lambda id:cos[id]['name'],key='rl_basis_company')
 st.caption('한 거래는 한 번만 등록합니다. 조회회사에 들어온 원금은 차입, 지급한 원금은 대여로 양사에서 자동 구분됩니다.')
 try:
  if page==PAGES[0]:overview(c,company,cos,month)
  elif page==PAGES[2]:deal_page(c,company,cos)
  elif page==PAGES[3]:event_page(c,company)
  elif page==PAGES[4]:rate_page(c,company,cos)
  elif page==PAGES[5]:month_page(c,company,cos,user)
  elif page==PAGES[6]:batch_page(c,company,cos)
 except (ValueError,PermissionError) as e:st.warning(str(e))
