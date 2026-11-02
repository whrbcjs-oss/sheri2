"""Non-lead project navigation and source-backed investment letters."""
from datetime import date
import json
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
import joint_store as db
import joint_workflow as flow
from joint_amounts import money_input, show as amount_table
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
        for i,(k,label) in enumerate(fields):payload[k]=money_input(label,v.get(k,'0'),where=[a,b][i%2],key=scope+k)
        total=db.num(payload['supply'])+db.num(payload['vat'])-sum((db.num(payload[k]) for k in ['asset','sub_input','own_input']),db.num(0))
        b.metric('계',money(total)+'원')
        if st.button('입력 저장',type='primary',key=scope+'_save'):
            db.save_entry(c,p,m['id'],'allocation_receipt',dt,dt.isoformat()[:7],dt.isoformat()[:7],payload,selected);app.saved()
    data=[{'청구일자':e['entry_date'],'구분':e['data'].get('label',''),**{label:e['data'][k] for k,label in fields},'계':e['data']['total']} for e in es]
    amount_table(data,[label for k,label in fields]+['계'])
    if selected and st.checkbox('선택한 접수 내역을 삭제합니다.',key=scope+'_confirm'):
        if st.button('선택 내역 삭제',key=scope+'_delete'):flow.delete_entry(c,p,m['id'],selected);app.saved()


def entry_page(c,p,m):
    import joint_app as app
    st.header('원가배분·기성·하도급·지급')
    tabs=st.tabs(['원가배분 접수','기성금 수금','관리비·보험료 정산','하도급 청구내역','지급내역 입력'])
    with tabs[0]:allocation_form(c,p,m)
    with tabs[1]:app.entry_form(c,p,m,'receipt',nonlead=True)
    with tabs[2]:app.fee_page(c,p,m)
    with tabs[3]:app.entry_form(c,p,m,'subcontract',nonlead=True)
    with tabs[4]:app.entry_form(c,p,m,'recovery',nonlead=True)


def investment_data(c,p,m,month):
    db.period(month)
    project=next(x for x in db.projects(c) if x['id']==p)
    rows=[r for r in db.ledger(c,p) if r['company_id']==project['owner_id'] and r['allocation_month']==month]
    totals={k:sum((db.num(r[k]) for r in rows),db.num(0)) for k in ['tax_supply','invoice','receipt','vat']}
    # Tax invoice supply and exempt invoices share the letter's 계산서 column.
    totals['invoice']+=totals['tax_supply'];totals['total']=totals['invoice']+totals['receipt']+totals['vat']
    data=db.assemble(c,p,m['id'],rows,[],[],month,month,claim_only=True)
    data.update(investment_letter=True,investment_totals={k:str(v) for k,v in totals.items()},investment_rows=rows)
    return data


def investment_letter(c,p,ms):
    import joint_app as app
    st.header('당사 투입비 · 공문 작성')
    project=next(x for x in db.projects(c) if x['id']==p)
    recipients=[m for m in ms if m['company_id']!=project['owner_id']]
    if not recipients:st.info('프로젝트·회원사에서 대표사를 등록하세요.');return
    rid=st.selectbox('수신 대표사',[m['id'] for m in recipients],format_func=lambda i:next(m['name'] for m in recipients if m['id']==i))
    m=next(m for m in recipients if m['id']==rid)
    month=st.text_input('통보월 (YYYY-MM)',date.today().strftime('%Y-%m'),key=f'investment_month_{p}')
    data=investment_data(c,p,m,month)
    number,issued,meta=app.issue_settings(p,m,'공문',data,month,investment=True)
    html=report_html(data,'공문',meta)
    st.download_button('공문 HTML 내려받기',html.encode(),file_name='당사투입비_공문_'+month+'.html',mime='text/html')
    detail_html=investment_attachment(data)
    st.download_button('첨부 투입내역서 HTML · 인쇄/PDF',detail_html.encode(),file_name='공동원가_투입내역_'+month+'.html',mime='text/html')
    details=pd.DataFrame(data['investment_rows']).rename(columns={'posting_date':'일자','allocation_month':'통보월','account':'과목','vendor':'거래처','description':'적요','tax_supply':'세금계산서 공급가액','invoice':'계산서','receipt':'영수증','vat':'VAT','note':'비고'})
    st.download_button('첨부 투입내역 CSV',app.safe_csv(details),file_name='공동원가_투입내역_'+month+'.csv')
    if st.button('공문 확정·발행',type='primary'):
        if not data['investment_rows']:raise ValueError('해당 통보월의 당사 투입비를 먼저 등록하세요.')
        db.snapshot(c,data,'공문',number,issued,meta);app.saved()
    components.html(html,height=1200,scrolling=True)


def investment_attachment(data):
    from joint_report import CSS, esc, table
    records=[];summary={}
    for r in data['investment_rows']:
        supply=sum((db.num(r[k]) for k in ['tax_supply','invoice','receipt']),db.num(0));vat=db.num(r['vat'])
        records.append([r['account'],r['posting_date'],r['description'],r['vendor'],money(supply),money(vat),money(supply+vat),r['note'],r['allocation_month']])
        bucket=summary.setdefault(r['account'],[db.num(0),db.num(0)])
        bucket[0]+=supply;bucket[1]+=vat
    supply=sum((v[0] for v in summary.values()),db.num(0));vat=sum((v[1] for v in summary.values()),db.num(0))
    records.append(['계','','','',money(supply),money(vat),money(supply+vat),'',''])
    rows=[[k,money(v[0]),money(v[1]),money(sum(v,db.num(0)))] for k,v in summary.items()]
    rows.append(['총합계',money(supply),money(vat),money(supply+vat)])
    return '<!doctype html><html lang="ko"><meta charset="utf-8"><title>공동원가 투입내역</title><style>'+CSS+'@page{size:A4 landscape;margin:12mm}</style><body><div class="tools"><button onclick="window.print()">인쇄 / PDF 저장</button></div><main class="document"><h1>공동원가 투입내역</h1><p>'+esc(data['project']['name'])+' · '+esc(period_label(data['start'],data['end']))+'</p>'+table(['과목','일자','적요','거래처','공급가액','VAT','합계금액','비고','통보월'],records)+'<h2>계정과목별 집계</h2>'+table(['계정과목','공급가액','VAT','합계금액'],rows)+'</main></body></html>'
