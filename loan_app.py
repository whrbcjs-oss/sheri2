"""Loan overview, certificates, actual collections and contract renewal."""
from datetime import date
from io import BytesIO
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
import loan_calc as calc
import loan_store as db
import loan_report as report

PAGES=['대여금 총현황','차용증 작성','인별 차용현황','이사회 결의서']

def go(page,id=None):
    st.session_state['loan_page']=page
    st.session_state['loan_section']='대여금(임직원)'
    if id is not None:st.session_state['loan_selected']=id

def uploads(files):return [dict(name=f.name,mime=f.type,content=f.getvalue()) for f in files or []]
def act(fn):
    try:fn();st.success('저장했습니다.');st.rerun()
    except ValueError as e:st.error(str(e))

def render_alerts(c=None,home=False):
    items=db.alerts(c)
    if not items:return
    st.subheader('대여금 상환 알림현황판')
    for a in items:
        text=f"{a['status']} · {a['name']} / {a['company']} · 상환기일 {a['due']} · 잔여원금 {calc.money(a['balance'])}원"
        if a['status']=='기일 경과':st.error(text)
        else:st.warning(text)
    if home and st.button('대여금 현황 확인',key='loan_home_open'):
        st.session_state['main_system']='대여금관리';go(PAGES[0]);st.rerun()
    st.caption('상환기일 한 달 전부터 안내합니다. 원금·이자 회수 완료 계약은 제외합니다.')

def fields(prefix,initial=None,renew=False,c=None,effective_date=None,amend=False):
    today=db.today();v=initial or {};key=lambda n:prefix+n
    with st.container(border=True):
        st.markdown('**작성 정보**')
        cols=st.columns(2)
        issued=cols[0].date_input('작성일자',today if amend else calc.day(v.get('issued_date',today)),key=key('issued'))
        suggested=v['number'] if not renew and v.get('number') and str(issued)==str(v.get('issued_date')) else db.next_number(c,issued) if c is not None else ''
        number=cols[1].text_input('변경 관리번호' if amend else '갱신 관리번호' if renew else '관리번호',suggested,key=key('number_')+str(issued)+suggested) if c is not None else ''
    with st.container(border=True):
        st.markdown('**차용기간**')
        cols=st.columns(2)
        start=cols[0].date_input('변경 적용일' if amend else '갱신 적용일' if renew else '대여일/차용시작일',calc.day(effective_date) if effective_date is not None else today if renew else calc.day(v.get('start_date',today)),key=key('start'),disabled=effective_date is not None)
        end=cols[1].date_input('상환기일 / 차용 종료일',max(calc.day(v.get('end_date',today)),calc.add_months(start,1)) if amend else calc.add_months(calc.day(v.get('end_date',today)),12) if renew else calc.day(v.get('end_date',calc.add_months(today,12))),min_value=start,key=key('end'))
    with st.container(border=True):
        st.markdown('**차용금액 · 이자**')
        cols=st.columns(2)
        principal=cols[0].number_input('차용금액 (원)',min_value=0,value=int(v.get('principal',0)),step=100000,key=key('principal'),disabled=renew)
        kind=cols[1].selectbox('차용이자 구분',calc.KINDS,index=calc.KINDS.index(v.get('interest_kind',calc.KINDS[0])),key=key('kind'))
        cols=st.columns(2)
        rate=cols[0].number_input('연이율 (%)',min_value=0.,max_value=100.,value=float(v.get('rate',5)),step=.1,key=key('rate'),disabled=kind!=calc.KINDS[0])
        fixed=cols[1].number_input('매월 약정 이자 (원)',min_value=0,value=int(v.get('fixed_interest',0)),key=key('fixed'),disabled=kind!=calc.KINDS[1])
    with st.container(border=True):
        st.markdown('**상환 조건 · 일정**')
        mode=st.radio('상환조건',calc.MODES,index=calc.MODES.index(v.get('mode',calc.MODES[2])),key=key('mode'))
        cols=st.columns(2)
        first_default=min(calc.add_months(start,1),end)
        first=cols[0].date_input('첫 상환일',end if mode==calc.MODES[1] else (calc.day(v.get('first_due',first_default)) if not renew else first_default),key=key('first'),disabled=mode==calc.MODES[1])
        pay_day=cols[1].number_input('매월 상환일 (일)',1,31,int(v.get('pay_day',first.day)),key=key('payday'))
        cols=st.columns(2)
        method=cols[0].selectbox('매월 원리금 계산',calc.METHODS,index=calc.METHODS.index(v.get('method',calc.METHODS[0])),key=key('method'),disabled=mode!=calc.MODES[0])
        manual=cols[1].checkbox('매월 원리금 상환액 직접 지정',value=bool(v.get('installment',0)),key=key('manual'),disabled=mode!=calc.MODES[0])
        installment=st.number_input('매월 원리금 합계 (원)',min_value=0,value=int(v.get('installment',0)),key=key('installment'),disabled=not manual)
        with st.expander('이자 계산 기준'):
            basis=st.selectbox('계산 기준',calc.BASES,index=calc.BASES.index(v.get('basis',calc.BASES[0])),key=key('basis'))
            early=st.selectbox('중도 원금상환 후 이자',['잔여원금 기준','약정 유지'],index=0 if v.get('early_interest','잔여원금 기준')=='잔여원금 기준' else 1,key=key('early'))
            st.caption('월 단위는 연이율 ÷ 12를 적용하며, 일부 월은 해당 계약 월의 경과 비율로 계산합니다. 마지막 회차에 원 단위 차액과 남은 원금을 정산합니다.')
    with st.container(border=True):
        st.markdown('**담보 · 기타 약정**')
        cols=st.columns(2)
        collateral=cols[0].text_area('기타 조건 / 담보 (아파트·퇴직연금 등)',v.get('collateral',''),key=key('collateral'))
        note=cols[1].text_area('비고 / 추가 약정',v.get('note',''),key=key('note'))
    return dict(issued_date=str(issued),start_date=str(start),end_date=str(end),principal=principal,interest_kind=kind,rate=rate,fixed_interest=fixed,mode=mode,method=method,first_due=str(end if mode==calc.MODES[1] else first),pay_day=pay_day,installment=installment if manual and mode==calc.MODES[0] else 0,basis=basis,early_interest=early,collateral=collateral,note=note,number=number)

def downloads(c,item,prefix):
    show=st.checkbox('출력물에 주민등록번호 전체 표시',key=prefix+'showid')
    snapshots=db.issued(c,item['id'])
    if st.button('현재 차용증 발행 기록 저장',key=prefix+'issue',disabled=item.get('closed',False)):act(lambda:db.issue(c,item['id']))
    versions=[dict(data=dict(v['data'],attachments=[f['name'] for f in db.attachments(c,item['id'],v['id']) if not f['receipt_id']]),label=f"{v['version']}차 계약 · {v['number']}") for v in reversed(item['versions'])]
    docs=[dict(data=x['data'],label=f"발행본 #{x['id']} · {x['created_at']}") for x in snapshots]+versions
    doc=st.selectbox('계약·발행 이력',docs,format_func=lambda x:x['label'],key=prefix+'doc')['data']
    components.html(report.certificate_html(doc,show),height=740,scrolling=True)
    st.download_button('차용증 인쇄 HTML',report.certificate_html(doc,show),file_name=doc['number']+'.html',mime='text/html',key=prefix+'html')
    if st.button('PDF 만들기',key=prefix+'pdfmake'):
        st.download_button('차용증 PDF 다운로드',report.certificate_pdf(doc,show),file_name=doc['number']+'.pdf',mime='application/pdf',key=prefix+'pdf')
    with st.expander('첨부서류 / 회수 증빙'):
        for f in db.attachments(c,item['id']):
            r,data=db.attachment_bytes(c,item['id'],f['id'])
            st.download_button(f['name'],data,file_name=f['name'],mime=f['mime'],key=prefix+'file'+str(f['id']))
    for source in db.transfer_sources(c,item['id']):
        old=db.loan(c,source['source_id'])
        with st.expander('승계 원본 · '+source['data']['number']):
            source_terms=next(v['data'] for v in old['versions'] if v['id']==source['data']['contract_id'])
            st.download_button('원본 차용증 인쇄',report.certificate_html(source_terms,show),file_name=source['data']['number']+'.html',mime='text/html',key=prefix+'source'+str(old['id']))
            for f in db.attachments(c,old['id']):
                r,data=db.attachment_bytes(c,old['id'],f['id'])
                st.download_button(f['name'],data,file_name=f['name'],mime=f['mime'],key=prefix+'sourcefile'+str(f['id']))


def overview(c):
    st.header('대여금 총현황')
    render_alerts(c)
    cols=st.columns(3);asof=cols[0].date_input('기준일',db.today(),key='loan_asof')
    items=db.loans(c,asof)
    company=cols[1].selectbox('지급회사',['전체']+sorted({v['company'] for v in items}))
    person=cols[2].selectbox('차용인',['전체']+sorted({v['borrower']['name'] for v in items}))
    items=[v for v in items if (company=='전체' or v['company']==company) and (person=='전체' or v['borrower']['name']==person)]
    summaries=[db.summary(c,v,asof) for v in items]
    cols=st.columns(4)
    for col,key,label in zip(cols,['principal','paid_principal','balance','unpaid_interest'],['총 대여원금','회수 원금','미회수 원금','발생 미회수 이자']):col.metric(label,calc.money(sum(s[key] for s in summaries))+'원')
    html=report.register_html(summaries,asof)
    st.html(report.overview_html(summaries,asof))
    records=[dict(관리번호=v['number'],구분=v['borrower']['kind'],차용인=v['borrower']['name'],지급회사=v['company'],대여일=v['start_date'],적요='일시 대여금',채권금액=s['principal'],상환원금=s['paid_principal'],잔액=s['balance'],상환일=v['terms']['end_date'],이자=report.interest_label(v['terms']),증빙='차용증',비고=v['terms'].get('note','')) for s in summaries for v in [s['loan']]]
    out=BytesIO()
    with pd.ExcelWriter(out,engine='openpyxl') as writer:
        pd.DataFrame(report.borrower_records(summaries)).to_excel(writer,index=False,sheet_name='차용인별 요약',startrow=2)
        pd.DataFrame(records,columns=['관리번호','구분','차용인','지급회사','대여일','적요','채권금액','상환원금','잔액','상환일','이자','증빙','비고']).to_excel(writer,index=False,sheet_name='대여금총현황',startrow=4)
        from openpyxl.styles import Font,PatternFill,Alignment
        from openpyxl.utils import get_column_letter
        sheet=writer.sheets['대여금총현황'];sheet.merge_cells('A1:I2');sheet['A1']='임직원 차용현황표';sheet['A1'].font=Font(size=20,bold=True);sheet['A1'].alignment=Alignment(horizontal='center',vertical='center')
        for col,label in zip(range(10,14),['담당','부장','상무','사장']):sheet.cell(1,col,label)
        sheet['A4']='기준일: '+str(asof);sheet.freeze_panes='A6';sheet.auto_filter.ref=sheet.dimensions
        for col in range(1,14):sheet.column_dimensions[get_column_letter(col)].width=20 if col in [1,4,13] else 16
        for cell in sheet[5]:cell.fill=PatternFill('solid',fgColor='DFF3E7');cell.font=Font(bold=True)
        for row in sheet.iter_rows(min_row=6,min_col=7,max_col=9):
            for cell in row:cell.number_format='#,##0'
        sheet.append(['전체 합계','','','','','']+[sum(s[k] for s in summaries) for k in ['principal','paid_principal','balance']])
        from table_layout import format_excel
        format_excel(sheet,min_row=5)
        summary_sheet=writer.sheets['차용인별 요약'];summary_sheet['A1']='차용인별 대여금 요약 · 기준일 '+str(asof);summary_sheet.freeze_panes='A4'
        for col in range(1,8):summary_sheet.column_dimensions[get_column_letter(col)].width=24 if col==2 else 20
        for cell in summary_sheet[3]:cell.fill=PatternFill('solid',fgColor='DFF3E7');cell.font=Font(bold=True)
        for cell in summary_sheet[summary_sheet.max_row]:cell.fill=PatternFill('solid',fgColor='DFF3E7');cell.font=Font(bold=True)
        format_excel(summary_sheet,min_row=3)
        for sheet in writer.sheets.values():
            sheet.sheet_properties.pageSetUpPr.fitToPage=True;sheet.page_setup.orientation='landscape';sheet.page_setup.paperSize=sheet.PAPERSIZE_A3;sheet.page_setup.fitToWidth=1;sheet.page_setup.fitToHeight=0
    with st.container(key='loan_overview_actions'):
        buttons=st.columns([1,1,1.2],gap='small')
        buttons[0].download_button('총현황표 인쇄',html,file_name='대여금총현황.html',mime='text/html',use_container_width=True)
        buttons[1].download_button('엑셀 다운로드',out.getvalue(),file_name='대여금총현황.xlsx',use_container_width=True)
        if buttons[2].button('새 차용증 작성',type='primary',use_container_width=True):go(PAGES[1]);st.rerun()

def compose(c):
    st.header('차용증 작성')
    operation=st.radio('작성 작업',['신규 작성','저장된 차용증 수정·삭제'],horizontal=True,key='loan_compose_operation')
    if operation=='저장된 차용증 수정·삭제':
        manage_certificates(c);return
    people=db.borrowers(c);options=[None]+people
    person=st.selectbox('차용인 선택',options,format_func=lambda p:'신규 차용인' if p is None else p['name']+' · '+p['phone'],key='loan_person') or {}
    left,right=st.columns([1.15,1])
    with left:
        with st.container(border=True):
            st.markdown('**차용인 정보**')
            cols=st.columns(2)
            name=cols[0].text_input('차용인',person.get('name',''),key='loan_name'+str(person.get('id',0)))
            kind=cols[1].selectbox('차용인 구분',['직원','개인','법인'],index=['직원','개인','법인'].index(person.get('kind','직원')))
            cols=st.columns(2)
            nid=cols[0].text_input('주민등록번호 / 생년월일',person.get('national_id',''),type='password',key='loan_nid'+str(person.get('id',0)),help='주민등록번호 13자리 또는 생년월일 6·8자리를 입력하세요. 생년월일은 차용증에 그대로 표시됩니다.')
            phone=cols[1].text_input('전화번호',person.get('phone',''),key='loan_phone'+str(person.get('id',0)))
            address=st.text_input('주소',person.get('address',''),key='loan_address'+str(person.get('id',0)))
        with st.container(border=True):
            st.markdown('**지급회사**')
            company=st.text_input('차용금 지급회사명')
        v=fields('new_',c=c)
        number=v.pop('number')
        with st.container(border=True):
            st.markdown('**첨부서류**')
            files=st.file_uploader('첨부서류 · 파일당 10MB / 합계 30MB',accept_multiple_files=True,key='loan_upload')
        p=dict(name=name,national_id=nid,phone=phone,address=address,kind=kind)
        if st.button('차용증 저장',type='primary'):
            def save():
                id=db.save_loan(c,v,p,company,number,borrower_id=person.get('id'),files=uploads(files));go(PAGES[2],id)
            act(save)
    with right:
        st.subheader('차용증 미리보기')
        try:
            draft=calc.validate(v);calc.schedule(draft)
            draft.update(borrower=p,company=company,number=number,attachments=[f.name for f in files or []])
            components.html(report.certificate_html(draft),height=830,scrolling=True)
        except ValueError as e:st.info(str(e))


def manage_certificates(c):
    items=db.loans(c,include_closed=True)
    if not items:st.info('저장된 차용증이 없습니다. 신규 작성에서 등록하세요.');return
    names=sorted({v['borrower']['name'] for v in items})
    who=st.selectbox('수정·삭제할 차용인',['전체']+names,key='loan_manage_person')
    options=[v['id'] for v in items if who=='전체' or v['borrower']['name']==who]
    lookup={v['id']:v for v in items}
    previous=st.session_state.get('_loan_manage_choice',options[0])
    def remember():st.session_state['_loan_manage_choice']=st.session_state['loan_manage_selected']
    id=st.selectbox('저장된 차용증 선택',options,index=options.index(previous) if previous in options else 0,on_change=remember,format_func=lambda id:lookup[id]['number']+' · '+lookup[id]['borrower']['name']+' · '+lookup[id]['company']+(' · 취소' if lookup[id].get('cancellation') else ' · 통합 승계' if lookup[id].get('transfer') else ''),key='loan_manage_selected')
    st.session_state['_loan_manage_choice']=id
    state=db.management_state(c,id);item=state['loan'];key='manage_'+str(id)+'_'+str(item['contract_id'])+'_'
    events=db.status_events(c,id)
    if events:
        with st.expander('취소·해제 이력'):
            st.dataframe(pd.DataFrame([{'일자':e['effective_date'],'처리':'취소' if e['event']=='cancel' else '취소 해제','사유':e['reason']} for e in events]),hide_index=True,use_container_width=True)
    if item.get('transfer'):
        st.info('통합 승계된 기존 차용증은 원본 보존을 위해 수정·삭제할 수 없습니다. 승계 계약에서 관리하세요.')
        downloads(c,item,key+'readonly_');return
    if item.get('cancellation'):
        st.warning('취소된 차용증입니다. 원본·회수·첨부는 보존하며 취소 적용일부터 현황·알림에서 제외됩니다.')
        reason=st.text_input('취소 해제 사유',key=key+'restore_reason')
        st.caption('취소를 해제하면 오늘부터 현황에 다시 포함되고, 원래 약정 기준으로 이자를 계산합니다.')
        if st.button('취소 해제',key=key+'restore'):act(lambda:db.restore_loan(c,id,reason))
        downloads(c,item,key+'cancelled_');return
    draft=state['draft'];summary=db.summary(c,item,db.today())
    if draft:st.info('발행·회수·갱신 이력이 없는 건입니다. 입력 내용 수정과 삭제가 가능합니다.')
    else:st.info('이력이 있는 차용증입니다. 원본을 보존하고 새 관리번호의 변경 계약을 작성합니다. 변경 원금은 실제 잔여원금으로 고정합니다.')
    left,right=st.columns([1.15,1])
    with left:
        person=item['borrower']
        with st.container(border=True):
            st.markdown('**차용인 정보**');cols=st.columns(2)
            name=cols[0].text_input('차용인 성명',person['name'],key=key+'name')
            kind=cols[1].selectbox('차용인 구분',['직원','개인','법인'],index=['직원','개인','법인'].index(person['kind']),key=key+'kind')
            cols=st.columns(2)
            nid=cols[0].text_input('주민등록번호 / 생년월일',person['national_id'],type='password',key=key+'nid')
            phone=cols[1].text_input('전화번호',person['phone'],key=key+'phone')
            address=st.text_input('주소',person['address'],key=key+'address')
        company=st.text_input('차용금 지급회사명',item['company'],disabled=not draft,key=key+'company')
        initial=dict(item['terms'],principal=item['initial_principal'] if draft else summary['balance'])
        v=fields(key+'fields_',initial,not draft,c=c,amend=not draft)
        number=v.pop('number');person=dict(name=name,national_id=nid,address=address,phone=phone,kind=kind)
        files=st.file_uploader('추가 첨부서류',accept_multiple_files=True,key=key+'files')
        reason=st.text_input('변경 사유',key=key+'reason') if not draft else ''
        if st.button('입력 내용 수정 저장' if draft else '변경 계약 저장·발행',type='primary',disabled=not draft and summary['balance']<=0,key=key+'save'):
            if draft:act(lambda:db.save_loan(c,v,person,company,number,loan_id=id,files=uploads(files)))
            else:act(lambda:db.amend_loan(c,id,v,person,number,v['start_date'],reason,files=uploads(files)))
        if draft:
            st.caption('삭제하면 해당 건과 첨부파일이 삭제되며 차용인 등록정보는 유지됩니다.')
            confirm=st.checkbox('선택한 차용증과 첨부 삭제 확인',key=key+'delete_confirm')
            if st.button('차용증 삭제',disabled=not confirm,key=key+'delete'):act(lambda:db.delete_draft(c,id))
        elif not db.transfer_sources(c,id):
            with st.expander('차용증 취소 처리'):
                effective=st.date_input('취소 적용일',db.today(),max_value=db.today(),key=key+'cancel_date')
                cancellation_reason=st.text_input('취소 사유',key=key+'cancel_reason')
                confirm=st.checkbox('원본 보존 및 취소일부터 현황·알림 제외 확인',key=key+'cancel_confirm')
                st.caption('취소는 입금·상환 처리가 아닙니다. 기존 회수내역은 그대로 남습니다.')
                if st.button('차용증 취소',disabled=not confirm,key=key+'cancel'):act(lambda:db.cancel_loan(c,id,effective,cancellation_reason))
        else:st.caption('통합 갱신 계약은 연결된 원본 보존을 위해 취소하지 않으며 변경 계약으로 관리합니다.')
    with right:
        st.subheader('수정·변경 미리보기')
        try:
            if draft:
                preview=calc.validate(v);calc.schedule(preview);preview.update(borrower=person,company=company,number=number)
            else:
                base=db.consolidation_preview(c,[id],v['start_date'])
                preview=calc.validate(dict(v,principal=base['principal'],carry_interest=base['unpaid_interest'],interest_credit=base['interest_credit']));calc.schedule(preview)
                preview.update(borrower=person,company=company,number=number,consolidation=base,document_kind='amendment')
            preview['attachments']=([r['name'] for r in db.attachments(c,id,item['contract_id'])] if draft else [])+[f.name for f in files or []]
            components.html(report.certificate_html(preview),height=800,scrolling=True)
        except ValueError as e:st.info(str(e))
        with st.expander('기존 차용증·발행본·첨부 확인'):
            downloads(c,item,key+'history_')

def detail(c):
    st.header('인별 차용현황')
    history=st.checkbox('통합 승계·취소된 기존 차용건도 조회',key='loan_show_transferred')
    items=db.loans(c,include_closed=history)
    if not items:st.info('차용증을 먼저 작성하세요.');return
    cols=st.columns(2)
    names=sorted({v['borrower']['name'] for v in items})
    person=cols[0].selectbox('차용인 조회',['전체']+names)
    company=cols[1].selectbox('지급회사 조회',['전체']+sorted({v['company'] for v in items}))
    filtered=[v for v in items if (person=='전체' or v['borrower']['name']==person) and (company=='전체' or v['company']==company)]
    if not filtered:st.info('해당 내역이 없습니다.');return
    selected=st.session_state.get('loan_selected');index=next((i for i,v in enumerate(filtered) if v['id']==selected),0)
    item=st.selectbox('차용 계약',filtered,index=index,format_func=lambda v:f"{v['number']} · {v['borrower']['name']} · {v['company']}")
    if item.get('cancellation'):
        st.warning('취소된 차용증 · '+item['cancellation']['effective_date']+' · '+item['cancellation']['reason']+' · 아래 잔액은 취소 시점의 보존 내역입니다.')
    elif item.get('transfer'):
        destination=db.loan(c,item['transfer']['target_id'])
        st.warning('통합 승계 완료 · '+item['transfer']['effective_date']+' → '+destination['number']+' · 아래 잔액은 승계 시점의 보존 내역입니다.')
    if st.button('이사회 결의서 작성',key='loan_start_board'):
        from board_app import start
        start(item['id']);st.rerun()
    s=db.summary(c,item,db.today());cols=st.columns(4)
    for col,label,value in zip(cols,['대여 원금','회수 원금','남은 원금','기일 도래 미회수액'],[s['principal'],s['paid_principal'],s['balance'],s['unpaid']]):col.metric(label,calc.money(value)+'원')
    month=db.today().strftime('%Y-%m');planned=[r for r in s['plan'] if r['due_date'].startswith(month)];actual=[r for r in item['receipts'] if r['receipt_date'].startswith(month) and r['receipt_date']<=str(db.today())]
    st.info(f"이번 달 예정 원금 {calc.money(sum(r['principal'] for r in planned))}원 + 이자 {calc.money(sum(r['interest'] for r in planned))}원 · 실제 회수 {calc.money(sum(r['principal']+r['interest'] for r in actual))}원 · 다음 상환일 {s['next_due'] or '없음'}")
    tabs=st.tabs(['월별 상환·회수','차용증·첨부서류','예상 시나리오','계약 연장·갱신 이력'])
    with tabs[0]:
        frame=pd.DataFrame(s['plan']).rename(columns={'index':'회차','due_date':'상환일','principal':'예정 원금','interest':'예정 이자','total':'예정 합계','balance':'예정 잔액','paid_principal':'배분 회수원금','paid_interest':'배분 회수이자','paid':'배분 회수합계','unpaid':'기일 미회수','status':'상태'})
        st.dataframe(frame[[x for x in ['회차','상환일','예정 원금','예정 이자','예정 합계','예정 잔액','배분 회수원금','배분 회수이자','기일 미회수','상태'] if x in frame]],hide_index=True,use_container_width=True)
        st.caption('회수액은 원금·이자를 구분하여 오래된 회차부터 배분합니다. 예정 잔액은 약정 기준이며, 실제 남은 원금은 상단에 표시합니다.')
        st.subheader('실제 회수내역')
        st.dataframe(pd.DataFrame([{'회수일':r['receipt_date'],'회수원금':r['principal'],'회수이자':r['interest'],'입금방법':r['method'],'메모':r['note']} for r in item['receipts']]),hide_index=True,use_container_width=True)
        current=[r for r in item['receipts'] if r['contract_id']==item['contract_id']]
        edit=st.selectbox('회수 등록 / 수정',[None]+current,format_func=lambda r:'신규 등록' if r is None else f"{r['receipt_date']} · 원금 {calc.money(r['principal'])} / 이자 {calc.money(r['interest'])}") or {}
        with st.form('loan_receipt_'+str(item['id'])+'_'+str(edit.get('id',0))):
            st.markdown('**회수 정보**')
            cols=st.columns(2)
            rd=cols[0].date_input('회수일',calc.day(edit.get('receipt_date',db.today())))
            method=cols[1].text_input('입금방법',edit.get('method',''))
            st.markdown('**회수 금액**')
            cols=st.columns(2)
            rp=cols[0].number_input('실제 회수원금 (원)',min_value=0,value=int(edit.get('principal',0)))
            ri=cols[1].number_input('실제 회수이자 (원)',min_value=0,value=int(edit.get('interest',0)))
            st.markdown('**메모 · 증빙**')
            note=st.text_input('회수 메모',edit.get('note',''))
            evidence=st.file_uploader('입금 증빙',accept_multiple_files=True)
            if st.form_submit_button('회수내역 저장',disabled=item.get('closed',False)):act(lambda:db.save_receipt(c,item['id'],rd,rp,ri,method,note,id=edit.get('id'),files=uploads(evidence)))
        if not item.get('closed') and edit and st.checkbox('선택한 회수내역 삭제 확인') and st.button('회수내역 삭제'):act(lambda:db.delete_receipt(c,item['id'],edit['id']))
    with tabs[1]:downloads(c,item,'detail_'+str(item['id']))
    with tabs[2]:
        from loan_scenario_app import render as render_scenario
        render_scenario(c,item)
    with tabs[3]:
        if item.get('closed'):
            st.info('통합 승계·취소로 보존 중인 차용건입니다. 차용증 작성의 수정·삭제 화면에서 상태와 이력을 확인하세요.')
        else:
            renewal_type=st.radio('갱신 방식',['현재 건 계약 연장','여러 차용건 통합 갱신'],horizontal=True,key='renewal_type_'+str(item['id']))
            if renewal_type=='여러 차용건 통합 갱신':
                render_consolidation(c,item)
            else:
                st.subheader('계약 연장 / 차용증 갱신')
                st.caption('기존 차용증·첨부·회수 이력을 보존하고 새 관리번호로 갱신합니다. 잔여원금은 한 번만 집계하며, 발생 미회수 이자는 별도로 이월합니다.')
                v=fields('renew_'+str(item['id'])+'_',dict(item['terms'],principal=s['balance']),True,c=c)
                number=v.pop('number')
                reason=st.text_input('계약 연장·갱신 사유')
                v['carry_policy']=st.selectbox('기존 미회수 이자 정산방법',db.CARRY_POLICIES,key='single_carry_'+str(item['id']))
                if st.checkbox('잔여원금·미회수 이자 승계 및 기존 계약 보존 확인') and st.button('계약 갱신 저장',type='primary'):act(lambda:db.renew(c,item['id'],v,number,v['start_date'],reason))
                st.dataframe(pd.DataFrame([dict(차수=x['version'],관리번호=x['number'],적용일=x['effective_date'],만기일=x['data']['end_date'],사유=x['reason']) for x in item['versions']]),hide_index=True,use_container_width=True)
                st.caption('갱신 차용증은 차용증·첨부서류 탭에서 확인·발행·출력하세요.')


def render_consolidation(c,item):
    st.subheader('여러 차용건 통합 갱신')
    st.caption('같은 차용인·같은 지급회사의 선택한 건을 통합합니다. 기존 계약·회수·첨부는 보존하고 갱신일부터 새 계약만 현황에 집계합니다.')
    key='merge_'+str(item['id'])+'_'
    candidates=[v for v in db.loans(c) if v['borrower_id']==item['borrower_id'] and v['company']==item['company']]
    lookup={v['id']:v for v in candidates}
    with st.container(border=True):
        st.markdown('**통합 대상 · 잔액 기준일**')
        ids=st.multiselect('통합할 차용건',list(lookup),default=list(lookup),format_func=lambda id:lookup[id]['number']+' · '+lookup[id]['terms']['end_date']+' 만기',key=key+'sources')
        effective=st.date_input('통합 갱신일 / 잔액 산정 기준일',db.today(),max_value=db.today(),key=key+'effective')
    try:preview=db.consolidation_preview(c,ids,effective)
    except ValueError as e:st.info(str(e));return
    cols=st.columns(3)
    for col,label,value in zip(cols,['합산 원금잔액','합산 미회수 이자','갱신 대상 총액'],[preview['principal'],preview['unpaid_interest'],preview['total']]):col.metric(label,calc.money(value)+'원')
    if preview['interest_credit']:st.info('선납이자 '+calc.money(preview['interest_credit'])+'원은 원금과 구분하여 새 약정 이자에서 공제합니다.')
    st.dataframe(pd.DataFrame([{'기존 관리번호':r['number'],'대여일':r['start_date'],'최초 차용원금':r['original_principal'],'회수원금':r['paid_principal'],'원금잔액':r['balance'],'미회수 이자':r['unpaid_interest'],'갱신 대상 합계':r['total']} for r in preview['rows']]),hide_index=True,use_container_width=True)
    with st.expander('건별 이자 산정 상세'):
        st.dataframe(pd.DataFrame([{'관리번호':r['number'],'산정 시작일':r['interest_start'],'산정 종료일':r['interest_end'],'적용이자':report.interest_label(r),'계산 기준':r['basis'],'금회 발생이자':r['earned_interest'],'이전 이월이자':r['opening_carry'],'금회 회수이자':r['paid_interest'],'이전 선납공제':r['opening_credit'],'미회수 이자':r['unpaid_interest'],'선납이자 잔액':r['interest_credit']} for r in preview['rows']]),hide_index=True,use_container_width=True)
    signature='_'.join(map(str,sorted(ids)))+'_'+str(effective)+'_'
    initial=dict(item['terms'],principal=preview['principal'],end_date=max(lookup[id]['terms']['end_date'] for id in ids))
    v=fields(key+signature,initial,True,c=c,effective_date=effective)
    number=v.pop('number')
    with st.container(border=True):
        st.markdown('**기존 이자 정산 · 갱신 사유**')
        v['carry_policy']=st.selectbox('기존 미회수 이자 정산방법',db.CARRY_POLICIES,key=key+'carry')
        st.caption('분할 정산은 새 계약의 실제 상환회차에 균등 배분합니다. 만기 일시상환처럼 상환회차가 하나이면 만기에 정산합니다.')
        reason=st.text_input('통합 갱신 사유',key=key+'reason')
        files=st.file_uploader('통합 갱신 첨부서류',accept_multiple_files=True,key=key+'files')
    try:
        draft=db.consolidation_terms(c,ids,v,number,effective,reason)
        draft['attachments']=[f.name for f in files or []]
        st.subheader('통합 갱신 차용증 미리보기')
        components.html(report.certificate_html(draft),height=780,scrolling=True)
        st.caption('차용증 본문 뒤 별첨 페이지에 기존 차용건별 잔액 명세를 출력합니다. 명세 마지막 페이지에 전체 합계와 차용인 확인 서명란을 표시합니다.')
    except ValueError as e:
        st.info(str(e));draft=None
    confirmed=st.checkbox('건별 잔액과 합계 확인 · 원본 보존 및 통합 승계 동의',key=key+'confirmed')
    if st.button('통합 갱신 저장·발행',type='primary',disabled=not confirmed or draft is None,key=key+'save'):
        def save():
            id=db.consolidate(c,ids,v,number,effective,reason,files=uploads(files));go(PAGES[2],id)
        act(save)
    sources=db.transfer_sources(c,item['id'])
    if sources:st.caption('이 계약의 이전 통합 이력은 차용증·첨부서류에서 확인할 수 있습니다.')

def render(user):
    section=st.session_state.get('loan_section','대여금(임직원)')
    with st.container(key='app_secondary_navigation'):
        cols=st.columns([1.2,1.2,3])
        for col,name in zip(cols,['대여금(임직원)','대여금(관계사)']):
            if col.button(name,key='loan_section_'+name,type='primary' if section==name else 'secondary',use_container_width=True):
                st.session_state['loan_section']=name;st.rerun()
    if section=='대여금(관계사)':
        from related_loan_app import render as related_render
        related_render(user);return
    c=db.connect()
    with st.sidebar:
        page=st.session_state.get('loan_page',PAGES[0])
        for name in PAGES:
            if st.button(name,key='loan_nav_'+name,use_container_width=True,type='primary' if page==name else 'secondary'):go(name);st.rerun()
    if page==PAGES[3]:
        from board_app import render as render_board
        render_board(c)
    else:{PAGES[0]:overview,PAGES[1]:compose,PAGES[2]:detail}.get(page,overview)(c)
