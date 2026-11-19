"""Non-lead project navigation and source-backed investment letters."""
from datetime import date
import json
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
import joint_store as db
import joint_workflow as flow
from joint_amounts import money_input, total_input, show as amount_table
from joint_report import render as report_html, money, period_label


is_nonlead = db.is_nonlead
set_mode = db.set_project_mode

def allocation_form(c,p,m):
    import joint_app as app
    es=flow.source_entries(c,p,m['id'],'allocation_receipt');scope=f"alloc_{p}_{m['id']}"
    selected=st.selectbox('등록·수정할 접수 내역',[None]+[e['id'] for e in es],format_func=lambda i:'새 내역' if i is None else next(e['entry_date']+' · '+e['data'].get('label','') for e in es if e['id']==i),key=scope)
    old=next((e for e in es if e['id']==selected),{});v=old.get('data',{});scope+='_'+str(selected)
    with st.container(border=True):
        a,b=st.columns(2)
        dt=a.date_input('청구일자',date.fromisoformat(old.get('entry_date',date.today().isoformat())),key=scope+'_date')
        payload={'label':b.text_input('구분',v.get('label','원가대체'),key=scope+'_label')}
        fields=[('supply','공급가액'),('vat','부가세'),('asset','자산투입'),('sub_input','하도급투입'),('own_input','당사투입')]
        amounts=st.columns(3)
        payload['supply']=money_input('공급가액',v.get('supply','0'),where=amounts[0],key=scope+'supply')
        payload['vat']=money_input('부가세',v.get('vat','0'),where=amounts[1],key=scope+'vat')
        gross=db.num(payload['supply'])+db.num(payload['vat'])
        total_input('차감 전 합계',gross,key=scope+'_gross',where=amounts[2])
        deductions=st.columns(4)
        for column,(k,label) in zip(deductions,fields[2:]):payload[k]=money_input(label,v.get(k,'0'),where=column,key=scope+k)
        total=gross-sum((db.num(payload[k]) for k in ['asset','sub_input','own_input']),db.num(0))
        total_input('계',total,key=scope+'_total',where=deductions[3])
        if st.button('입력 저장',type='primary',key=scope+'_save'):
            db.save_entry(c,p,m['id'],'allocation_receipt',dt,dt.isoformat()[:7],dt.isoformat()[:7],payload,selected);app.saved()
    data=[{'청구일자':e['entry_date'],'구분':e['data'].get('label',''),**{label:e['data'][k] for k,label in fields},'계':e['data']['total']} for e in es]
    amount_table(data,[label for k,label in fields]+['계'])
    if selected and st.checkbox('선택한 접수 내역을 삭제합니다.',key=scope+'_confirm'):
        if st.button('선택 내역 삭제',key=scope+'_delete'):flow.delete_entry(c,p,m['id'],selected);app.saved()


def entry_page(c,p,m):
    import joint_app as app
    st.header('원가배분·기성·하도급·지급')
    tabs=st.tabs(['원가배분 접수','기성금 수금','관리비·보험료 정산','하도급 청구내역','지급내역 입력','당사투입비·기성·계약현황'],key=f'nonlead_entry_tabs_{p}_{m["id"]}',on_change='rerun')
    with tabs[0]:allocation_form(c,p,m)
    with tabs[1]:app.entry_form(c,p,m,'receipt',nonlead=True)
    with tabs[2]:app.fee_page(c,p,m)
    with tabs[3]:app.entry_form(c,p,m,'subcontract',nonlead=True)
    with tabs[4]:app.entry_form(c,p,m,'recovery',nonlead=True)
    with tabs[5]:
        from joint_status_app import view
        view(c,p,m)


def investment_data(c,p,m,month):
    db.period(month)
    project=next(x for x in db.projects(c) if x['id']==p)
    rows=[r for r in db.ledger(c,p) if r['company_id']==project['owner_id'] and r['allocation_month']==month]
    totals={k:sum((db.num(r[k]) for r in rows),db.num(0)) for k in ['tax_supply','invoice','receipt','vat']}
    # Tax invoice supply and exempt invoices share the letter's 계산서 column.
    totals['invoice']+=totals['tax_supply'];totals['total']=totals['invoice']+totals['receipt']+totals['vat']
    data=db.assemble(c,p,m['id'],rows,[],[],month,month,claim_only=True)
    data.update(letter_layout_version=4,investment_letter=True,investment_totals={k:str(v) for k,v in totals.items()},investment_rows=rows)
    return data


def investment_letter(c,p,ms):
    import joint_app as app
    st.header('당사 투입비 · 공문 작성')
    project=next(x for x in db.projects(c) if x['id']==p)
    recipients=[m for m in ms if m['company_id']!=project['owner_id']]
    if not recipients:st.info('프로젝트·회원사에서 대표사를 등록하세요.');return
    rid=st.selectbox('수신 대표사',[m['id'] for m in recipients],format_func=lambda i:next(m['name'] for m in recipients if m['id']==i))
    m=next(m for m in recipients if m['id']==rid)
    from joint_progress_app import sync as sync_month
    month=st.text_input('통보월 (YYYY-MM)',key=f'investment_month_{p}',on_change=sync_month,args=(p,f'investment_month_{p}'))
    from joint_letter_manage_app import controls
    import joint_letter_manage as lm
    rows,expected,draft,epoch,key=controls(c,p,rid,month)
    data=investment_data(c,p,m,month)
    if draft:st.info('갱신 중 · 최신 원장과 추가 서류를 반영합니다. 수정 후 갱신 확정하세요.')
    number,issued,meta=app.issue_settings(p,m,'공문',data,month,investment=True,c=c,defaults=draft.get('meta') if draft else None,epoch=epoch)
    shown=rows[0]['data'] if rows and not draft else data
    shown_meta=shown.get('meta',meta) if rows and not draft else meta
    html=report_html(shown,'공문',shown_meta)
    from joint_letter_files import bundle as letter_bundle
    with st.container(horizontal=True):
        st.download_button('공문 HTML 내려받기',html.encode(),file_name='당사투입비_공문_'+month+'.html',mime='text/html')
        st.download_button('공문·원장·추가 서류 ZIP',letter_bundle(shown,shown_meta),file_name='당사투입비_공문_첨부_'+month+'.zip',mime='application/zip')
        st.download_button('첨부 투입내역서 HTML · 인쇄/PDF',investment_attachment(shown).encode(),file_name='공동원가_투입내역_'+month+'.html',mime='text/html')
        details=pd.DataFrame(shown['investment_rows']).rename(columns={'posting_date':'일자','allocation_month':'통보월','account':'과목','vendor':'거래처','description':'적요','tax_supply':'세금계산서 공급가액','invoice':'계산서','receipt':'영수증','vat':'VAT','note':'비고'})
        st.download_button('첨부 투입내역 CSV',app.safe_csv(details),file_name='공동원가_투입내역_'+month+'.csv')
    if st.button('공문 갱신 확정' if draft else '공문 확정·발행',type='primary',disabled=len(rows)>1 or bool(rows and not draft)):
        lm.save(c,data,number,issued,meta,expected);st.session_state.pop(key+'draft',None);app.saved()
    components.html(html,height=1200,scrolling=True)


def investment_attachment(data):
    from joint_investment_print import document
    return document(data)
