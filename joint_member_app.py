"""Non-leading project screens integrated with the existing ledger menu."""
from datetime import date
import json
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
import joint_store as db
import joint_member as member
from joint_amounts import money_input,show
from joint_member_report import render as report

PAGES=['당사 투입비','원가배분 접수','기성금 수금','정산·결재','대표사 지급','공문·결재 보관']
PAGE_KIND={'당사 투입비':'investment','원가배분 접수':'claim','기성금 수금':'receipt','대표사 지급':'payment'}

def done():
    st.session_state['_jv_success']='저장했습니다.';st.rerun()

def settings(prefix):
    mode=st.radio('정산 방식',['관리비 정산형','원가분담 정산형'],horizontal=True,key=prefix+'mode')
    a,b=st.columns(2)
    rate=money_input('관리비율 (%)',6,key=prefix+'rate',where=a)
    excluded=money_input('관리비 계산 제외액',key=prefix+'excluded',where=b)
    rounding=st.selectbox('관리비 단수 처리',['원 미만 버림','반올림','버림 후 1원 가산'],key=prefix+'rounding')
    a,b,c=st.columns(3)
    values=dict(mode=mode,rate=rate,excluded=excluded,rounding=rounding)
    for col,key,label in [(a,'industrial','산재보험료'),(b,'employment','고용보험료'),(c,'other_insurance','기타 보험료 공제')]:values[key]=money_input(label,key=prefix+key,where=col)
    values['adjustment']=money_input('전회 잔액·기타 조정 (가산 + / 차감 −)',key=prefix+'adjustment')
    st.caption('관리비 계산 제외액과 실제 보험료 공제는 별도입니다. 원가분담 정산형에서는 관리비·보험료 입력을 계산에 사용하지 않습니다. 전회 잔액은 선택 내역에 이미 포함된 금액을 다시 입력하지 마세요.')
    return values

def listing(es):
    rows=[dict(ID=x['id'],일자=x['entry_date'],귀속월=x['month'],구분=member.KINDS[x['kind']],내역=x['label'],공급가액=x['data']['supply'],VAT=x['data']['vat'],반영투입비=x['data'].get('invested','0'),반영직불=x['data'].get('subcontract','0'),비고=x['data'].get('note','')) for x in es]
    show(rows,['공급가액','VAT','반영투입비','반영직불'])

def entry_page(c,p,kind):
    es=member.records(c,p,kind)
    st.header(member.KINDS[kind]+' 등록·조회')
    if es:listing(es)
    prefix=f'nl_{p}_{kind}_'
    edit=st.selectbox('등록·수정할 내역',[None]+[x['id'] for x in es],format_func=lambda id:'새 내역' if id is None else next(f"{x['entry_date']} · {x['label']}" for x in es if x['id']==id),key=prefix+'edit')
    old=next((x for x in es if x['id']==edit),{});v=old.get('data',{});prefix+=str(edit)+'_'
    if edit and c.execute('SELECT 1 FROM jv_member_links WHERE record_id=?',(edit,)).fetchone():st.info('이 내역은 출력본에 연결되어 수정할 수 없습니다. 새 내역에 반대금액을 등록해 정정하세요.')
    a,b=st.columns(2);when=a.date_input('일자',date.fromisoformat(old.get('entry_date',date.today().isoformat())),key=prefix+'date');month=b.text_input('귀속월 (YYYY-MM)',old.get('month',date.today().strftime('%Y-%m')),key=prefix+'month')
    label=st.text_input('내역명',old.get('label',''),key=prefix+'label');values={}
    cols=st.columns(2)
    for i,(key,title) in enumerate(member.FIELDS[kind].items()):values[key]=money_input(title,v.get(key,0),key=prefix+key,where=cols[i%2])
    if kind=='investment':
        categories=['급여','보증수수료','기타','하도급 직불'];values['category']=st.selectbox('투입비 구분',categories,index=categories.index(v.get('category','기타')),key=prefix+'category')
    if kind=='claim':st.caption('대표사에서 접수한 당사분 금액을 입력합니다. 당사 투입비·하도급 직불은 대표사가 실제 반영한 공급가액을 입력하세요.')
    if kind=='payment':
        docs=[x for x in member.documents(c,p,'approval') if x['status']=='결재완료']
        options=[None]+[x['id'] for x in docs];current=v.get('approval_id')
        values['approval_id']=st.selectbox('결재완료 출력본 연결',options,index=options.index(current) if current in options else 0,format_func=lambda id:'기존 지급액·이월 지급 (결재 연결 없음)' if id is None else next(x['number'] for x in docs if x['id']==id),key=prefix+'approval')
        st.caption('신규 지급은 결재완료 건을 연결하고, 과거 기지급액은 결재 연결 없이 등록할 수 있습니다.')
    values['note']=st.text_input('비고',v.get('note',''),key=prefix+'note')
    if st.button('내역 저장',type='primary',key=prefix+'save'):member.record(c,p,kind,when.isoformat(),month,label,values,edit);done()
    if kind=='investment':
        st.divider();st.subheader('공동원가 투입내역 통보 공문')
        reported={x[0] for x in c.execute("SELECT l.record_id FROM jv_member_links l JOIN jv_member_documents d ON d.id=l.document_id WHERE d.project_id=? AND d.kind='notice'",(p,))}
        unreported=[x for x in es if x['id'] not in reported]
        ids=st.multiselect('통보할 투입비',[x['id'] for x in unreported],format_func=lambda id:next(x['entry_date']+' · '+x['label'] for x in unreported if x['id']==id),key=f'notice_ids_{p}')
        number=st.text_input('공문 문서번호',key=f'notice_no_{p}');issued=st.date_input('공문 발신일',key=f'notice_date_{p}')
        note=st.text_input('공문 비고',key=f'notice_note_{p}')
        st.caption('공문 저장은 송부할 출력본을 보관하는 기능입니다. 실제 송부 후 보관함에서 송부완료로 기록하세요.')
        if st.button('공문·첨부내역 저장',key=f'notice_save_{p}'):
            member.save_document(c,p,'notice',number,issued.isoformat(),ids,dict(note=note));done()
    if kind=='claim':
        st.divider();st.subheader('당사 투입비 반영 대조 (전체 누계)')
        investments=member.records(c,p,'investment');claims=member.records(c,p,'claim')
        ordinary=sum((db.num(x['data']['supply']) for x in investments if x['data']['category']!='하도급 직불'),db.num(0));sub=sum((db.num(x['data']['supply']) for x in investments if x['data']['category']=='하도급 직불'),db.num(0));q=member.totals(claims)
        show([dict(구분='급여·보증수수료·기타',투입누계=ordinary,반영누계=q['invested'],미반영=ordinary-q['invested']),dict(구분='하도급 직불',투입누계=sub,반영누계=q['subcontract'],미반영=sub-q['subcontract'])],['투입누계','반영누계','미반영'])

def settlement(c,p):
    st.header('비주관공사 정산·대표이사 결재')
    prefix=f'nl_settle_{p}_';es=[x for x in member.records(c,p) if x['kind']!='investment']
    cutoff=st.date_input('정산 기준일',key=prefix+'cutoff');available=[x for x in es if x['entry_date']<=cutoff.isoformat()]
    scope=st.radio('출력 범위',['공사 전체 누계','금회 선택 내역'],horizontal=True,key=prefix+'scope')
    options=[x['id'] for x in available]
    ids=options if scope=='공사 전체 누계' else st.multiselect('금회 정산에 반영할 내역',options,format_func=lambda id:next(member.KINDS[x['kind']]+' · '+x['entry_date']+' · '+x['label'] for x in available if x['id']==id),key=prefix+'ids')
    st.caption('전체 누계는 기준일까지의 접수 원가·기성금·지급 내역을 포함합니다. 금회 선택은 선택한 내역만 계산하며 이전 지급액도 필요한 만큼 선택하세요.')
    if ids:listing([x for x in available if x['id'] in ids])
    values=settings(prefix);values['scope']=scope;values['cutoff']=cutoff.isoformat()
    values['name']=st.text_input('정산명',key=prefix+'name');values['note']=st.text_input('정산 비고',key=prefix+'note')
    if ids:
        d=member.snapshot(c,p,ids,values);a=d['amounts'];cols=st.columns(3)
        cols[0].metric('관리비',f"{db.num(a['fee']):,.0f}원");cols[1].metric('기지급액',f"{db.num(a['paid']):,.0f}원");cols[2].metric('대표사 지급예정액' if db.num(a['remaining'])>=0 else '대표사에서 받을 금액',f"{abs(db.num(a['remaining'])):,.0f}원")
        st.caption('관리비 정산형: 기성 공급가액 − 관리비 − 보험료 + 접수 VAT − 반영 투입비 − 반영 직불 − 기지급액 + 조정액. 원가분담 정산형: 접수 원가 차인액 − 기지급액 + 조정액.')
        preview=dict(d,kind='approval',number='미리보기',issued=date.today().isoformat())
        with st.expander('결재양식 미리보기'):components.html(report(preview),height=700,scrolling=True)
    number=st.text_input('결재 문서번호',key=prefix+'number');issued=st.date_input('결재양식 작성일',key=prefix+'issued')
    if st.button('결재 출력본 저장',type='primary',key=prefix+'save'):
        if not values['name'].strip():raise ValueError('정산명을 입력하세요.')
        member.save_document(c,p,'approval',number,issued.isoformat(),ids,values);done()

def archive(c,p):
    st.header('투입비 공문·결재 출력본 보관')
    docs=member.documents(c,p)
    if not docs:st.info('저장한 공문·결재 출력본이 없습니다.');return
    id=st.selectbox('보관 문서',[x['id'] for x in docs],format_func=lambda id:next(x['number']+' · '+('투입비 공문' if x['kind']=='notice' else '지급 결재')+' · '+x['status'] for x in docs if x['id']==id),key=f'member_doc_{p}')
    doc=next(x for x in docs if x['id']==id);d=json.loads(doc['snapshot']);html=report(d)
    st.download_button('양식 내려받기 · 인쇄/PDF',html.encode('utf-8'),file_name=doc['number'].replace('/','_')+'.html',mime='text/html',key=f'member_download_{id}')
    components.html(html,height=800,scrolling=True)
    if doc['kind']=='approval':
        paid=sum((db.num(x['data']['supply'])+db.num(x['data']['vat']) for x in member.records(c,p,'payment') if x['data'].get('approval_id')==id),db.num(0))
        st.metric('이 결재건 지급 후 잔액',f"{db.num(d['amounts']['remaining'])-paid:,.0f}원")
        if doc['status']=='출력용' and st.checkbox('출력물에 대표이사 결재를 받았습니다.',key=f'approved_check_{id}'):
            if st.button('결재완료 기록',key=f'approved_{id}'):member.approve(c,p,id);done()
    elif doc['status']=='출력용' and st.checkbox('공문과 첨부내역을 대표사에 송부했습니다.',key=f'sent_check_{id}'):
        if st.button('송부완료 기록',key=f'sent_{id}'):
            with c:c.execute("UPDATE jv_member_documents SET status='송부완료' WHERE id=? AND project_id=? AND kind='notice'",(id,p))
            done()

def render(c,p,page):
    cfg=member.config(c,p);project=next(x for x in db.projects(c) if x['id']==p);names={x['id']:x['name'] for x in db.companies(c)}
    st.info('당사비주관공사 · 당사: '+names[project['owner_id']]+' → 대표사: '+names[cfg['representative_id']])
    if page in PAGE_KIND:entry_page(c,p,PAGE_KIND[page])
    elif page=='정산·결재':settlement(c,p)
    elif page=='공문·결재 보관':archive(c,p)
