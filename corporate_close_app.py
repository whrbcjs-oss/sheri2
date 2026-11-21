"""Corporate close workspace centered on the approved Excel-shaped tax flow."""
from datetime import date
from html import escape
from io import BytesIO
import hashlib,time
import pandas as pd
from pandas.io.formats.style import Styler
import streamlit as st
import streamlit.components.v1 as components
import corporate_close_store as db
import corporate_close_calc as calc
import corporate_close_import as ledger
import corporate_close_report as report
import corporate_close_dashboard as dashboard
import corporate_close_prepaid as prepaid
import corporate_close_promotion as promotion
import corporate_close_ratio as ratio
import corporate_close_capital as capital
import corporate_progress as progress
import corporate_progress_report as progress_report

VERSION='2026.11.21.49'
ADJUSTMENT_SUBPAGES=['세금과공과명세서','선급비용명세서','기업업무추진비명세서']
PAGES=['대시보드','법인세 계산 흐름표','기초정보입력','공사수입·원가대비','세무조정 항목',*ADJUSTMENT_SUBPAGES,'소득구분계산서','세액 계산','유보잔액 관리','결산 확정·출력','경영상태비율 점검','실질자본금 점검','기업진단지침 관리','법인·업종 설정']
VALUE_FIELDS=[('construction_revenue','공사수입'),('service_revenue','용역수입'),('progress_adjustment','진행률조정수입(예상)'),('cost','매출원가'),('sga','판매관리비'),('nonop_income','영업외수익'),('nonop_expense','영업외비용'),('prior_sales','전기매출'),('prior_progress','전기 진행률 수입조정'),('prior_unfinished','전기 미완성공사'),('current_unfinished','당기 미완성공사')]
REVIEW_FIELDS=[('entertainment_cost','접대비·경비'),('entertainment_sga','접대비·판관비'),('tax_cost','세금과공과·경비'),('tax_sga','세금과공과·판관비'),('interest','이자비용'),('donation','기부금')]
TAX_FIELDS=[('donation_excess','기부금한도초과'),('donation_carry_deduction','기부금이월손금'),('carry_loss','전기이월결손금'),('special_reduction','중소기업 특별세액감면'),('rd_prior','R&D 세액공제 전기이월'),('rd_current','R&D 세액공제 당기'),('undocumented_base','증빙미수취 대상금액'),('land_gain','토지 등 양도차익'),('prepaid_corp_interim','법인세 중간예납'),('prepaid_corp_withholding','법인세 원천납부'),('prepaid_local','지방소득세 기납부'),('accrued_tax','미지급법인세')]
NEXT_FIELDS=[('donation_carry_next','차기 기부금 이월잔액'),('carry_loss_next','차기 이월결손금'),('rd_carry_next','차기 R&D 세액공제 이월액')]
CSS='''<style>.cc-title{background:#087a4f;color:#fff;border-radius:7px;padding:8px 12px;font-weight:800;font-size:18px;margin:5px 0 8px}.cc-card{border:1px solid #b8d5c6;border-radius:8px;padding:10px;background:#fff;margin-bottom:8px}.cc-legend{font-size:12px;color:#60776c;text-align:right}.cc-blue{color:#2788e8;font-weight:700}.cc-red{color:#ef2424;font-weight:700}.cc-yellow{background:#fff600;padding:1px 5px;font-weight:700}.st-key-cc_direct_flow [data-testid="stNumberInput"] input,.st-key-cc_direct_flow [data-testid="stTextInput"] input,.st-key-cc_tax_direct [data-testid="stNumberInput"] input,.st-key-cc_tax_direct [data-testid="stTextInput"] input{background:#eef6ff;color:#176dc2;font-weight:700}.cc-auto{background:#fff600;border:1px solid #b9ad00;padding:8px;border-radius:5px;text-align:right;font-weight:800;color:#ef2424;margin-bottom:7px}.cc-section{background:#c8c8c8;border:1px solid #777;padding:7px;text-align:center;font-weight:800;margin:4px 0 7px}.cc-adjust-title{background:#087a4f;color:#fff;border-radius:7px 7px 0 0;padding:8px 11px;font-weight:800;font-size:15px;margin-top:12px}.cc-grid-head{text-align:center;font-weight:800;color:#36594a;padding:6px 2px;border-bottom:2px solid #90b6a3}.cc-grid-auto{height:38px;display:flex;align-items:center;justify-content:flex-end;padding:0 9px;background:#fff7bd;border:1px solid #dfcd5a;border-radius:6px;color:#d92323;font-weight:800;font-variant-numeric:tabular-nums}.cc-grid-na{height:38px;display:flex;align-items:center;justify-content:center;background:#f2f5f3;border:1px solid #d7dfdb;border-radius:6px;color:#8a9992}.cc-adjust-total{text-align:right;background:#fff200;border:1px solid #d6c900;border-radius:6px;padding:10px 12px;color:#e32323;font-weight:800;font-variant-numeric:tabular-nums;margin:5px 0 13px}[class*="st-key-cc_add_"][class*="_amount"] input,[class*="st-key-cc_add_"][class*="_cost"] input,[class*="st-key-cc_deduct_"][class*="_amount"] input,[class*="st-key-cc_deduct_"][class*="_cost"] input,[class*="st-key-flow_"] input,[class*="st-key-tax_"] input,[class*="st-key-reserve_"] input{color:#126bb0!important;text-align:right!important;font-weight:700!important;font-variant-numeric:tabular-nums}.st-key-cc_case_banner{background:#edf4f8;border:1px solid #9db8c9;border-left:6px solid #315f7d;border-radius:8px;padding:10px 14px;margin-bottom:8px}.st-key-cc_case_banner label{color:#244b64!important;font-size:15px!important;font-weight:800!important}.st-key-cc_case_banner input{font-size:17px!important;font-weight:800!important;color:#173f59!important}.st-key-cc_case_banner [data-baseweb="select"]{font-size:17px!important;font-weight:800!important}.cc-case-current{display:grid;grid-template-columns:1fr .55fr .35fr;gap:10px;background:#173f59;color:#fff;border-radius:8px;padding:11px 15px;margin:4px 0 10px}.cc-case-current div{display:flex;align-items:baseline;gap:10px}.cc-case-current span{color:#cfe0ea;font-size:12px;font-weight:700}.cc-case-current strong{font-size:20px;font-weight:800}.cc-input-title{background:#e8f1f8;color:#1d5679;border-left:6px solid #2c739f;border-bottom:2px solid #88b3ce;border-radius:5px 5px 0 0;padding:8px 11px;margin:12px 0 7px;font-size:18px;font-weight:800}.cc-input-lock{background:#f2f5f6;color:#53656f;border:1px solid #cbd5da;border-radius:6px;padding:7px 10px;margin-bottom:8px;font-size:13px}.cc-input-edit{background:#fff8d9;color:#725700;border:1px solid #dec75a;border-radius:6px;padding:7px 10px;margin-bottom:8px;font-size:13px;font-weight:700}[class*="st-key-cc_ratio_locked_"] input{background:#eef1f3!important;color:#50616b!important;font-weight:700!important;text-align:right!important}[class*="st-key-cc_ratio_editing_"] input{background:#fffbe8!important;color:#126bb0!important;border-color:#d4b52c!important;font-weight:800!important;text-align:right!important}@media(max-width:700px){.cc-case-current{grid-template-columns:1fr}.cc-case-current strong{font-size:17px}}</style>'''
PREPAID_CSS='''<style>.cc-pp-head{height:36px;display:flex;align-items:center;justify-content:center;text-align:center;background:#e8f2ed;border:1px solid #b9d0c4;border-radius:5px;color:#28483a;font-size:12px;font-weight:800}.cc-pp-cell{height:38px;display:flex;align-items:center;justify-content:center;text-align:center;background:#fff;border:1px solid #d6e1db;border-radius:5px;font-size:12px;overflow:hidden}.cc-pp-desc{height:auto;min-height:38px;justify-content:flex-start;text-align:left;padding:5px 8px;line-height:1.3;white-space:normal;overflow-wrap:anywhere}.cc-pp-num{justify-content:flex-end;padding:0 8px;color:#126bb0;font-weight:700;font-variant-numeric:tabular-nums}.cc-pp-auto{justify-content:flex-end;padding:0 8px;background:#fff5a8;border-color:#ddcf65;color:#d92c25;font-weight:800;font-variant-numeric:tabular-nums}.cc-pp-days{color:#765b00;background:#fffbe5;font-weight:800;font-variant-numeric:tabular-nums}.cc-pp-ok{color:#087a4f;font-weight:700}.cc-pp-error{background:#fff0ef;border-color:#efb8b4;color:#d92c25;font-weight:700}.cc-pp-row{padding:3px 0;border-bottom:1px solid #e3ebe7}[class*="st-key-cc_pp_"] input{background:#eaf4ff!important;color:#126bb0!important;text-align:right!important;font-weight:700!important;font-size:12px!important;height:38px!important}[class*="st-key-cc_pp_id_"] input,[class*="st-key-cc_pp_start_"] input,[class*="st-key-cc_pp_end_"] input{text-align:center!important}</style>'''
CAPITAL_CSS='''<style>.cc-capital-hero{background:linear-gradient(125deg,#173f59,#245f72);color:#fff;border-radius:10px;padding:16px 19px;margin:7px 0 12px;box-shadow:0 5px 13px #173f5920}.cc-capital-hero .eyebrow{color:#bfe2ed;font-size:12px;font-weight:700}.cc-capital-hero .headline{font-size:23px;font-weight:850;margin-top:3px}.cc-capital-cards{display:grid;grid-template-columns:repeat(5,1fr);gap:8px;margin:9px 0 15px}.cc-capital-card{background:#fff;border:1px solid #b9ccd5;border-top:4px solid #2c739f;border-radius:8px;padding:10px 12px;box-shadow:0 2px 7px #173f590c}.cc-capital-card span{display:block;color:#607782;font-size:12px;font-weight:700}.cc-capital-card strong{display:block;text-align:right;color:#126bb0;font-size:18px;margin-top:5px;font-variant-numeric:tabular-nums}.cc-capital-card.result{background:#fffbe3;border-color:#d7bd36;border-top-color:#e0b900}.cc-capital-card.result strong{color:#d92c25}.cc-capital-status{border-radius:8px;padding:10px 14px;text-align:center;font-weight:850;font-size:17px}.cc-capital-ok{background:#e5f6ed;border:1px solid #86c9a5;color:#087a4f}.cc-capital-bad{background:#fff0ef;border:1px solid #efb8b4;color:#d92c25}.cc-capital-pending{background:#fff8dc;border:1px solid #ddc968;color:#765b00}.cc-capital-section{background:#e8f1f8;color:#1d5679;border-left:6px solid #2c739f;border-bottom:2px solid #88b3ce;border-radius:5px 5px 0 0;padding:9px 12px;margin:15px 0 7px;font-size:18px;font-weight:850}.cc-capital-map-cards{display:grid;grid-template-columns:repeat(5,1fr);gap:8px;margin:8px 0}.cc-capital-map-card{background:#fff;border:1px solid #c8d8d1;border-radius:8px;padding:9px 12px}.cc-capital-map-card span{display:block;color:#687b74;font-size:12px;font-weight:700}.cc-capital-map-card strong{display:block;color:#087a4f;font-size:20px;margin-top:2px}.cc-capital-map-card.review strong{color:#806300}.st-key-cc_capital_item_editor [data-testid="stDataFrame"],.st-key-cc_capital_license_editor [data-testid="stDataFrame"]{border:1px solid #aac6d4;border-radius:7px}.st-key-cc_capital_item_editor [data-testid="stDataFrame"] input,.st-key-cc_capital_license_editor [data-testid="stDataFrame"] input{color:#126bb0!important;text-align:right!important;font-weight:700!important}@media(max-width:900px){.cc-capital-cards,.cc-capital-map-cards{grid-template-columns:1fr 1fr}.cc-capital-hero .headline{font-size:19px}}</style>'''
BRIGHT_THEME_CSS='''<style>
#root [data-testid="stSidebar"]{background:#f8fafb;border-right:1px solid #dce7eb}
#root [data-testid="stSidebar"] [data-testid="stRadio"] label{border-left:4px solid transparent;border-radius:7px;padding:5px 8px;margin:1px 0;color:#425b68;transition:background .12s,border-color .12s}
#root [data-testid="stSidebar"] [data-testid="stRadio"] label:hover{background:#f0f7fb;color:#24566e}
#root [data-testid="stSidebar"] [data-testid="stRadio"] label:has(input:checked){background:#e8f4fc;border-left-color:#4b9ac8;color:#24566e;font-weight:800;box-shadow:inset 0 0 0 1px #d2e8f5}
#root [data-testid="stSidebar"] [data-testid="stRadio"] label:has(input:checked) p{color:#24566e!important;font-weight:800!important}
#root .cc-title{background:linear-gradient(180deg,#e7f2f9,#dcecf6);color:#24566e;border:1px solid #b9d5e5;border-left:6px solid #4b9ac8;border-radius:7px;padding:9px 12px;box-shadow:0 2px 6px #24566e0c}
#root .cc-adjust-title{background:#eaf7f2;color:#245d4c;border:1px solid #bfe1d4;border-left:6px solid #45a985;border-radius:7px 7px 0 0}
#root .cc-section{background:#f0f5f8;border:1px solid #ccd9e0;color:#355665;border-radius:6px}
#root .cc-input-title,#root .cc-capital-section{background:#edf6fc;color:#24566e;border-left-color:#4b9ac8;border-bottom-color:#a9cde2}
#root .cc-capital-hero{background:linear-gradient(125deg,#eef8fc,#dcecf6);color:#24566e;border:1px solid #b9d5e5;box-shadow:0 4px 12px #24566e12}
#root .cc-capital-hero .eyebrow{color:#4b7f99}
#root .cc-capital-hero .headline{color:#24566e}
#root .cc-card,#root .cc-capital-card,#root .cc-capital-map-card{border-color:#d4e1e7;box-shadow:0 2px 7px #24566e0a}
#root .st-key-cc_case_banner{background:#f1f7fd;border-color:#c7ddea;border-left-color:#4b9ac8}
#root [data-testid="stFileUploaderDropzone"]{background:#ffffff;border-color:#cfdde4}
#root [data-testid="stFileUploaderDropzone"]:hover{background:#f7fbfd;border-color:#8fbdd5}
#root [data-testid="stDataFrame"]{border-color:#d3e0e6;border-radius:7px}
#root button[kind="primary"]{background:#24a878!important;border-color:#1e9369!important;color:#fff!important;box-shadow:0 2px 6px #1e93691f}
#root button[kind="primary"] p{color:#fff!important}
</style>'''
PROGRESS_REVIEW_CSS='''<style>
.st-key-cc_progress_review_metrics [data-testid="stMetric"]{background:#fff;border:1px solid #cdded8;border-top:4px solid #4b9ac8;border-radius:7px;padding:10px 12px}.st-key-cc_progress_review_metrics [data-testid="stMetricValue"]{text-align:right;color:#173f59;font-weight:800}.st-key-cc_progress_review_notice{background:#e9f4fa;border-left:5px solid #4b9ac8;border-radius:5px;padding:9px 12px;color:#244b64;margin:4px 0 9px}.st-key-cc_progress_detail{background:#fff;border:1px solid #cdded8;border-radius:8px;padding:13px 14px;margin-top:10px}.st-key-cc_progress_detail h3{color:#24566e;font-size:16px}.st-key-cc_progress_detail [data-testid="stTextInput"] input,.st-key-cc_progress_detail [data-testid="stNumberInput"] input{color:#126bb0!important;text-align:right!important;font-weight:750!important}.st-key-cc_progress_detail [data-testid="stTextInput"] input:disabled,.st-key-cc_progress_detail [data-testid="stNumberInput"] input:disabled{background:#eef2f3!important;color:#62736d!important}.st-key-cc_progress_detail_result [data-testid="stMetric"]{background:#eaf7f1;border:1px solid #b9d9ca;border-radius:6px;padding:8px 10px}.st-key-cc_progress_detail_result [data-testid="stMetricValue"]{color:#087a4f;font-weight:850}.cc-progress-detail-head{display:flex;align-items:center;justify-content:space-between;background:#edf6fc;border-left:6px solid #4b9ac8;padding:9px 12px;margin-bottom:8px}.cc-progress-detail-head span{color:#607782;font-size:12px}.cc-progress-detail-head strong{display:block;color:#173f59;font-size:19px;margin-top:2px}.cc-progress-chip{background:#e5f6ed;color:#087a4f;border-radius:999px;padding:4px 9px;font-weight:700}.cc-progress-group-title{color:#24566e;font-weight:800;border-bottom:2px solid #b9d5e5;padding-bottom:5px;margin-bottom:4px}.cc-progress-result-title{color:#087a4f;font-weight:800;border-bottom:2px solid #9bcbb4;padding-bottom:5px;margin-bottom:4px}@media(max-width:800px){.st-key-cc_progress_review_metrics [data-testid="stHorizontalBlock"]{flex-wrap:wrap}.st-key-cc_progress_review_metrics [data-testid="column"]{min-width:45%}}</style>'''
def money(v):
    if v is None or v=='':return 0
    try:
        if pd.isna(v):return 0
    except (TypeError,ValueError):pass
    return int(float(str(v).replace(',','').replace('원','').strip() or 0))
def money_field(scope,label,value,key=None,disabled=False,label_visibility='visible'):
    return money(scope.text_input(label,value=f'{money(value):,}',key=key,disabled=disabled,label_visibility=label_visibility))
def show_frame(data,*args,**kwargs):
    if isinstance(data,Styler):return st.dataframe(data,*args,**kwargs)
    frame=pd.DataFrame(data);numeric=[c for c in frame.columns if pd.api.types.is_numeric_dtype(frame[c]) and not pd.api.types.is_bool_dtype(frame[c])];text=[c for c in frame.columns if c not in numeric]
    styled=frame.style.format({c:'{:,.0f}' for c in numeric},na_rep='').set_properties(subset=numeric,**{'text-align':'right','color':'#126bb0','font-weight':'600'}).set_properties(subset=text,**{'text-align':'center'}).set_table_styles([{'selector':'th','props':[('text-align','center'),('font-weight','700'),('background','#edf5f1')]}])
    return st.dataframe(styled,*args,**kwargs)
def capital_review_frame(records,changed_account=''):
    """Right-hand approved review layout with readable status colors."""
    rows=[]
    for row in records or []:
        mapping=str(row.get('지침 매핑','') or '').strip();note=str(row.get('근거·비고','') or '').strip()
        changed=bool(changed_account and capital.norm(row.get('계정과목',''))==capital.norm(changed_account));status=str(row.get('검토상태','') or '')+(' · 수정 반영' if changed else '')
        rows.append({'계정과목':row.get('계정과목',''),'차변잔액':money(row.get('차변잔액')),'대변잔액':money(row.get('대변잔액')),'구분':row.get('구분',''),'분류':row.get('분류',''),'특수처리':row.get('특수처리',''),'계정 반영금액':money(row.get('순금액')),'지침 매핑 · 근거/비고':mapping+('\n'+note if note else ''),'검토상태':status})
    frame=pd.DataFrame(rows,columns=['계정과목','차변잔액','대변잔액','구분','분류','특수처리','계정 반영금액','지침 매핑 · 근거/비고','검토상태'])
    def styles(data):
        result=pd.DataFrame('',index=data.index,columns=data.columns)
        for index,row in data.iterrows():
            group=str(row['구분']);classification=str(row['분류']);status=str(row['검토상태'])
            if '수정 반영' in status:result.loc[index,:]='background-color:#e8f7ef'
            result.loc[index,'구분']='background-color:#e7f2fb;color:#176ba0;font-weight:700;text-align:center' if group in ['자산','부채'] else 'background-color:#edf1ef;color:#687b74;font-weight:700;text-align:center'
            if classification=='검토 필요':result.loc[index,'분류']='background-color:#fff0a8;color:#725a00;font-weight:700;text-align:center'
            elif classification in ['인정','일반']:result.loc[index,'분류']='background-color:#e7f2fb;color:#176ba0;font-weight:700;text-align:center'
            elif classification=='부실':result.loc[index,'분류']='background-color:#fff0ef;color:#c93335;font-weight:700;text-align:center'
            elif classification=='겸업':result.loc[index,'분류']='background-color:#eee9fb;color:#6247a6;font-weight:700;text-align:center'
            if str(row['특수처리']):result.loc[index,'특수처리']='background-color:#e7f2fb;color:#176ba0;font-weight:700;text-align:center'
            if '작업자 확정' in status:result.loc[index,'검토상태']='background-color:#dff4e8;color:#087a4f;font-weight:800;text-align:center'
            elif '검토' in status or '확인' in status:result.loc[index,'검토상태']='color:#806300;font-weight:700;text-align:center'
            elif '자동 초안' in status:result.loc[index,'검토상태']='color:#087a4f;font-weight:700;text-align:center'
            else:result.loc[index,'검토상태']='color:#687b74;font-weight:700;text-align:center'
        return result
    numeric=['차변잔액','대변잔액','계정 반영금액']
    return frame.style.format({column:'{:,.0f}' for column in numeric},na_rep='').apply(styles,axis=None).set_properties(subset=numeric,**{'text-align':'right','color':'#126bb0','font-weight':'600'}).set_properties(subset=['계정과목'],**{'text-align':'left','font-weight':'700'}).set_properties(subset=['지침 매핑 · 근거/비고'],**{'text-align':'left','white-space':'pre-line'}).set_table_styles([{'selector':'th','props':[('text-align','center'),('font-weight','700'),('background','#edf3f0'),('color','#557068')]}])
def statement_print_html(title,year,sections):
    """Create a standalone A4-landscape calculation sheet for browser printing."""
    tables=[]
    for heading,data in sections:
        frame=pd.DataFrame(data).copy()
        numeric=[c for c in frame.columns if pd.api.types.is_numeric_dtype(frame[c]) and not pd.api.types.is_bool_dtype(frame[c])]
        formatters={c:(lambda v: '' if pd.isna(v) else f'{int(v):,}') for c in numeric}
        tables.append(f'<h2>{escape(str(heading))}</h2>'+frame.to_html(index=False,border=0,na_rep='',formatters=formatters,escape=True))
    return f'''<!doctype html><html lang="ko"><head><meta charset="utf-8"><title>{escape(str(title))}</title><style>
    @page{{size:A4 landscape;margin:10mm}}body{{font-family:"Malgun Gothic",sans-serif;color:#111;margin:0}}h1{{font-size:20px;text-align:center;margin:0 0 4px}}.year{{text-align:right;font-size:12px;margin-bottom:12px}}h2{{font-size:14px;background:#087a4f;color:white;padding:6px 8px;margin:14px 0 0}}table{{width:100%;border-collapse:collapse;font-size:10px;page-break-inside:auto}}thead{{display:table-header-group}}tr{{page-break-inside:avoid}}th,td{{border:1px solid #777;padding:4px 5px}}th{{background:#e7eeea;text-align:center}}td{{text-align:center}}td:nth-child(n+2){{font-variant-numeric:tabular-nums}}.print{{margin-bottom:8px;padding:6px 12px}}@media print{{.print{{display:none}}}}
    </style></head><body><button class="print" onclick="window.print()">인쇄</button><h1>{escape(str(title))}</h1><div class="year">결산연도 {int(year)}년</div>{''.join(tables)}</body></html>'''
def tax_input_values(raw):
    tax=dict(raw or {});parts=calc.prepaid_tax(tax)
    tax.update(parts);return tax
def refresh():st.rerun()
def queue_session_value(key,value):st.session_state[key]=value
def active_company(c,id):return next(x for x in db.companies(c) if x['id']==id)
def reserve_summary(c,x):
    out=[]
    for r in db.reserves(c,x['company_id']):
        y=next((z for z in db.reserve_years(c,r['id']) if z['year']==x['year']),None)
        if y:period={k:y[k] for k in ['beginning','increase','deduction','other','ending']}
        else:
            prior=[z for z in db.reserve_years(c,r['id']) if z['year']<x['year']]
            beginning=prior[-1]['ending'] if prior else r['initial_amount']
            period={'beginning':beginning,'increase':0,'deduction':0,'other':0,'ending':beginning}
        out.append({**r,**period})
    return out
def readiness(c,x,company,inc):
    missing=[]
    value_keys={k for k,_ in VALUE_FIELDS};tax_keys={k for k,_ in TAX_FIELDS}
    if not value_keys.issubset(x.get('values',{})):missing.append('손익계산서·예상금액 저장')
    if not tax_keys.issubset(x.get('tax',{})):missing.append('세액 계산 입력 저장')
    if inc['check']!=0:missing.append('업종별 매출액 합계 일치')
    if not inc.get('expense_manual'):missing.append('영업외비용 감면분·기타분 직접 입력')
    elif inc.get('expense_check'):missing.append('영업외비용 구분 합계 일치')
    blanks=[r for r in db.ledger_rows(c,x['id']) if r['kind']=='영업외수익' and '잡이익' in db.normalized(r['account']) and not r['classification']]
    if blanks:missing.append(f'잡이익 적요 분류 {len(blanks)}건')
    projects=db.progress_projects(c,x['id'])
    if projects:
        ps=progress.summary(projects,x.get('progress',{}));values=x.get('values',{})
        if money(values.get('construction_revenue'))!=ps['table_revenue'] or money(values.get('progress_adjustment'))!=ps['expected_adjustment']:missing.append('공사수입·진행률조정 검산값 흐름표 반영')
    return missing
def computed(c,x,company):
    adjustments=db.adjustments(c,x['id']);lr=db.ledger_rows(c,x['id']);other_income=sum(r['amount'] for r in lr if r['kind']=='영업외수익' and '잡이익' in db.normalized(r['account']) and r['classification']=='감면분');manual=x.get('income_manual',{})
    values=x.get('values',{});f=calc.flow(values,adjustments);businesses=[{'name':name,'revenue':x.get('business_revenue',{}).get(name,0)} for name in company.get('businesses',['건설업'])]
    if len(businesses)==1 and not businesses[0]['revenue']:businesses[0]['revenue']=f['sales']
    inc=calc.income_division(values,adjustments,businesses,other_income,manual.get('nonop_expense_exempt'),manual.get('nonop_expense_other'),x.get('losses',{}));inc['classification_details']=[{'kind':r['kind'],'account':r['account'],'description':r['description'],'reason':str(r.get('business','')).replace('자동:',''),'classification':r['classification'],'amount':r['amount']} for r in lr if r['kind']=='영업외수익' and '잡이익' in db.normalized(r['account'])];tax=calc.tax_calculation(inc['current_income'],{**x.get('tax',{}),'pre_tax':f['pre_tax']});return adjustments,inc,tax,reserve_summary(c,x)
def performance_snapshot(c,x,company,values=None,tax_inputs=None):
    """Live expected ratios while preserving the saved tax-adjustment base."""
    adjustments,inc,_,_=computed(c,x,company);saved=calc.flow(x.get('values',{}),adjustments);current=calc.flow(values if values is not None else x.get('values',{}),adjustments)
    current_income=inc['current_income']+(current['pre_tax']-saved['pre_tax']);tax=calc.tax_calculation(current_income,{**x.get('tax',{}),**(tax_inputs or {}),'pre_tax':current['pre_tax']})
    sales=current['sales'];construction=current['construction_revenue']+current['progress_adjustment'];pre_tax=current['pre_tax'];tax_expense=tax['tax_expense']
    return {'cost_rate':current['cost']/construction*100 if construction else 0,'gross_rate':current['gross_profit']/sales*100 if sales else 0,'operating_rate':current['operating_profit']/sales*100 if sales else 0,'pre_tax_rate':pre_tax/sales*100 if sales else 0,'net_rate':tax['net_income']/sales*100 if sales else 0,'tax_expense':tax_expense,'effective_tax_rate':tax_expense/pre_tax*100 if pre_tax>0 else 0}
def save_payload(c,x,payload):db.save_case(c,x,payload,x['version']);refresh()

def dashboard_page(c,x,company):
    adjustments,inc,tax_result,reserves=computed(c,x,company);view=dashboard.html(company['name'],x['year'],x,adjustments,inc,tax_result)
    comparison=[]
    for co in db.companies(c):
        case=db.case(c,co['id'],x['year'],create=False)
        if not case:comparison.append({'name':co['name'],'entered':False});continue
        a,i,t,_=computed(c,case,co);f=calc.flow(case.get('values',{}),a);sales=f['sales']
        comparison.append({'name':co['name'],'entered':True,'sales':sales,'gross':f['gross_profit'],'operating':f['operating_profit'],'pretax':f['pre_tax'],'net':t['net_income'],'gross_rate':(f['gross_profit']/sales*100 if sales else 0),'operating_rate':(f['operating_profit']/sales*100 if sales else 0),'pretax_rate':f['pre_tax_rate'],'net_rate':(t['net_income']/sales*100 if sales else 0),'cost_rate':f['cost_rate'],'taxable':t['taxable'],'credits':t['credits'],'payable':t['corp_payable']+t['local_payable']})
    st.html('<div class="cc-title">대시보드</div>');st.caption('저장된 기초정보·세무조정·소득구분·세액 계산 결과를 한 화면에 표시합니다. 별도 입력 없이 자동 갱신됩니다.')
    individual_tab,compare_tab=st.tabs(['개별회사 분석','회사 비교'])
    with individual_tab:components.html(view,height=930,scrolling=True)
    with compare_tab:components.html(dashboard.comparison_html(x['year'],comparison),height=900,scrolling=True)

def basic_input_page(c,x,company):
    st.html('<div class="cc-title">기초정보입력</div>');st.caption('기존 법인세 계산 흐름표의 입력 항목과 계산 기준을 그대로 유지했습니다. 연파랑 칸에 입력하고 저장하세요.')
    with st.container(key='cc_direct_flow'):
      # This page intentionally does not use st.form: the detail-mode checkbox
      # must rerun immediately so its dependent inputs become editable.
      with st.container():
        values=dict(x.get('values',{}));review=dict(x.get('review',{}));tax=tax_input_values(x.get('tax',{}));business=dict(x.get('business_revenue',{}));disabled=x['status']=='confirmed';p1,p2,p3,p4=st.columns([1.05,1.05,1.35,1.0])
        p1.html('<div class="cc-section">손익계산서 점검</div>')
        for key,label in VALUE_FIELDS[:7]:values[key]=money_field(p1,label,values.get(key),key='flow_'+key,disabled=disabled)
        live=calc.flow(values,db.adjustments(c,x['id']));p1.html(f'<div class="cc-auto">매출계　{live["sales"]:,}</div><div class="cc-auto">영업이익　{live["operating_profit"]:,}</div>')
        p2.html('<div class="cc-section">전기·예상 지표</div>')
        for key,label in VALUE_FIELDS[7:]:values[key]=money_field(p2,label,values.get(key),key='flow_'+key,disabled=disabled)
        p2.html(f'<div class="cc-auto">진행률조정 계　{money(values.get("prior_progress"))+money(values.get("progress_adjustment")):,}</div>');p3.html('<div class="cc-section">조정 전 검토사항</div>')
        for key,label in REVIEW_FIELDS:review[key]=money_field(p3,label,review.get(key),key='flow_review_'+key,disabled=disabled)
        p4.html('<div class="cc-section">기납부세액</div>');tax['prepaid_corp_interim']=money_field(p4,'법인세 중간예납',tax.get('prepaid_corp_interim'),key='flow_prepaid_interim',disabled=disabled);tax['prepaid_corp_withholding']=money_field(p4,'법인세 원천납부',tax.get('prepaid_corp_withholding'),key='flow_prepaid_withholding',disabled=disabled);tax['prepaid_local']=money_field(p4,'지방소득세 기납부',tax.get('prepaid_local'),key='flow_prepaid_local',disabled=disabled);tax['prepaid_corp']=tax['prepaid_corp_interim']+tax['prepaid_corp_withholding'];p4.html(f'<div class="cc-auto">선납세금 합계　{tax["prepaid_corp"]+tax["prepaid_local"]:,}</div>')
        current_metrics=performance_snapshot(c,x,company,values,tax);prior_case=db.case(c,x['company_id'],x['year']-1,create=False);prior_metrics=performance_snapshot(c,prior_case,company) if prior_case else None
        st.markdown('**전년도 대비 예상 손익·세율 검산**')
        labels=[('조정 후 공사원가율','cost_rate','%'),('매출총이익률','gross_rate','%'),('영업이익률','operating_rate','%'),('세전이익률','pre_tax_rate','%'),('당기순이익률','net_rate','%'),('유효세율','effective_tax_rate','%'),('법인세비용','tax_expense','원')]
        comparison=[]
        for label,key,unit in labels:
            old=prior_metrics.get(key,0) if prior_metrics else 0;now=current_metrics[key];difference=now-old
            status='전년도 없음' if not prior_metrics else ('유사' if (abs(difference)<=1 if unit=='%' else abs(difference)<=max(abs(old)*.1,1000000)) else '확인')
            comparison.append({'검토항목':label,'전년도':f'{old:,.2f}%' if unit=='%' else f'{old:,.0f}원','당해 예상':f'{now:,.2f}%' if unit=='%' else f'{now:,.0f}원','증감':f'{difference:+,.2f}%p' if unit=='%' else f'{difference:+,.0f}원','판정':status})
        st.dataframe(pd.DataFrame(comparison),hide_index=True,use_container_width=True)
        st.markdown('**연구 및 인력개발비(세액공제)**');old=calc.research_totals(review);detail=st.checkbox('세부항목으로 계산',value=old['detail_enabled'] or not review,disabled=disabled);r1,r2,r3,r4=st.columns(4);review['rnd_employee_count']=r1.number_input('연구 인건비 인원(명)',min_value=0,value=old['employee_count'],disabled=disabled or not detail);review['rnd_labor']=money_field(r1,f'인건비({review["rnd_employee_count"]}명)',old['labor'],key='rnd_labor',disabled=disabled or not detail);review['rnd_material']=money_field(r2,'재료비',old['material'],key='rnd_material',disabled=disabled or not detail);review['rnd_other']=money_field(r2,'기타 연구개발비',old['other'],key='rnd_other',disabled=disabled or not detail);review['rnd_outsourced']=money_field(r3,'위탁·공동연구비',old['outsourced'],key='rnd_outsourced',disabled=disabled or not detail);review['training_sga']=money_field(r3,'(판)교육훈련비',old['training_sga'],key='training_sga',disabled=disabled or not detail);review['training_cost']=money_field(r4,'(경)교육훈련비',old['training_cost'],key='training_cost',disabled=disabled or not detail);review['rnd_detail_enabled']=detail;rt=calc.research_totals(review);review['rnd']=rt['current_total'];review['tech_total']=rt['tech_total'];r4.html(f'<div class="cc-auto">경상연구개발비 계　{rt["current_total"]:,}</div><div class="cc-auto">인력개발비 계　{rt["personnel_total"]:,}</div><div class="cc-auto">기술개발투자비　{rt["tech_total"]:,}</div>')
        if len(company.get('businesses',[]))>1:
            st.markdown('**겸업 업종별 매출액**');cols=st.columns(min(4,len(company['businesses'])))
            for i,name in enumerate(company['businesses']):business[name]=money_field(cols[i%len(cols)],name+' 매출액',business.get(name),key='business_'+str(i),disabled=disabled)
        disposal=st.date_input('처분확정일',value=date.fromisoformat(x.get('disposal_date',f'{x["year"]+1}-03-31')),disabled=disabled);submit=st.button('흐름표 입력값 저장',type='primary',disabled=disabled,key='cc_values_save')
    if submit:
        payload={k:v for k,v in x.items() if k not in ['id','company_id','year','status','version']};payload.update(values=values,review=review,tax=tax,business_revenue=business,disposal_date=str(disposal));save_payload(c,x,payload)

def entry_page(c,x,company):
    adjustments,inc,tax_result,reserves=computed(c,x,company);preview=report.html(company['name'],x['year'],x,adjustments,inc,tax_result,reserves);xlsx=report.workbook(company['name'],x['year'],x,adjustments,inc,tax_result,reserves)
    st.html('<div class="cc-title">법인세 계산 흐름표</div>');st.caption('기초정보입력과 각 세부 메뉴에서 저장한 내용을 기존 흐름표 구조로 표시합니다.')
    a,b=st.columns(2);a.download_button('인쇄용 HTML 내려받기',preview,file_name=f'{x["year"]}_{company["name"]}_법인세계산흐름표.html',mime='text/html',use_container_width=True);b.download_button('Excel 내려받기',xlsx,file_name=f'{x["year"]}_{company["name"]}_법인세계산흐름표.xlsx',mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',use_container_width=True)
    components.html(preview,height=1180,scrolling=True)

def _adjustment_group(name,existing=''):
    if existing in calc.ACCOUNT_GROUPS:return existing
    text=str(name or '')
    if '법인세' in text:return '법인세'
    if any(k in text for k in ['선급','퇴직급여충당','감가상각','유형자산','대손충당']):return '자산'
    if any(k in text for k in ['수익','환입','보상','매각','환수']):return '영업외수익'
    if any(k in text for k in ['이자비용','기부금','잡손실','처분손실']):return '영업외비용'
    return '원가'

GROUP_LABELS={'원가계정':'원가','고정자산':'자산','영업외비용':'영업외비용','영업외수익':'영업외수익','법인세':'법인세'}
GROUP_NAMES={v:k for k,v in GROUP_LABELS.items()}

def _adjustment_inline_grid(c,x,active,side,title,cost_label,sga_label):
    rows=[r for r in active if r['side']==side and not r['source_key'].startswith('reserve:')]
    st.html(f'<div class="cc-adjust-title">{title}</div>')
    with st.container(key=f'cc_{side}_grid'):
        heads=st.columns([1.05,1.25,1.05,1.0,1.0,1.2,.46,.46])
        for col,label in zip(heads,['계정 구분','과목','금액 · 직접입력',cost_label,sga_label,'근거·메모','저장','삭제']):col.html(f'<div class="cc-grid-head">{label}</div>')
        for r in rows:
            cols=st.columns([1.05,1.25,1.05,1.0,1.0,1.2,.46,.46]);prefix=f'cc_{side}_{r["id"]}'
            current=GROUP_NAMES.get(r.get('account_group') or '원가','원가계정');group_label=cols[0].selectbox('계정 구분',list(GROUP_LABELS),index=list(GROUP_LABELS).index(current),key=prefix+'_group',label_visibility='collapsed',disabled=x['status']=='confirmed');group=GROUP_LABELS[group_label]
            name=cols[1].text_input('과목',value=r['name'],key=prefix+'_name',label_visibility='collapsed',disabled=x['status']=='confirmed');amount=money_field(cols[2],'금액',r['amount'],key=prefix+'_amount',disabled=x['status']=='confirmed',label_visibility='collapsed')
            old_cost=r['amount'] if r['target']=='원가' else r.get('cost_amount',0) if r['target']=='공통' else 0
            if group=='원가':cost=money_field(cols[3],cost_label,old_cost,key=prefix+'_cost',disabled=x['status']=='confirmed',label_visibility='collapsed');cols[4].html(f'<div class="cc-grid-auto">{amount-cost:,}</div>')
            else:cost=0;cols[3].text_input(cost_label,value='',key=prefix+'_cost_blank',disabled=True,label_visibility='collapsed');cols[4].html('<div class="cc-grid-na">―</div>')
            note=cols[5].text_input('근거·메모',value=r.get('note',''),key=prefix+'_note',label_visibility='collapsed',disabled=x['status']=='confirmed')
            if cols[6].button('저장',key=prefix+'_save',disabled=x['status']=='confirmed',use_container_width=True):
                if not name.strip():st.error('과목을 입력하세요.');return
                if group=='원가' and (cost<0 or cost>amount):st.error(name+'의 원가 조정액은 0 이상이며 금액 이하여야 합니다.');return
                target='원가' if group=='원가' and cost==amount else '공통' if group=='원가' and cost else '판관비';db.save_adjustment(c,x,side,name,amount,target,cost,note,r['id'],r['version'],account_group=group);refresh()
            if cols[7].button('삭제',key=prefix+'_delete',disabled=x['status']=='confirmed',use_container_width=True):db.delete_adjustment(c,x,r['id'],r['version'],'입력표에서 삭제');refresh()
        # Always-visible new row at the bottom of the same grid.
        cols=st.columns([1.05,1.25,1.05,1.0,1.0,1.2,.94]);prefix=f'cc_{side}_new';group_label=cols[0].selectbox('새 계정 구분',list(GROUP_LABELS),key=prefix+'_group',label_visibility='collapsed',disabled=x['status']=='confirmed');group=GROUP_LABELS[group_label];name=cols[1].text_input('새 과목',placeholder='새 과목 추가',key=prefix+'_name',label_visibility='collapsed',disabled=x['status']=='confirmed');amount=money_field(cols[2],'새 금액',0,key=prefix+'_amount',disabled=x['status']=='confirmed',label_visibility='collapsed')
        if group=='원가':cost=money_field(cols[3],cost_label,0,key=prefix+'_cost',disabled=x['status']=='confirmed',label_visibility='collapsed');cols[4].html(f'<div class="cc-grid-auto">{amount-cost:,}</div>')
        else:cost=0;cols[3].text_input(cost_label,value='',key=prefix+'_cost_blank',disabled=True,label_visibility='collapsed');cols[4].html('<div class="cc-grid-na">―</div>')
        note=cols[5].text_input('새 근거·메모',key=prefix+'_note',label_visibility='collapsed',disabled=x['status']=='confirmed')
        if cols[6].button('＋ 추가',key=prefix+'_add',type='primary',disabled=x['status']=='confirmed',use_container_width=True):
            if not name.strip():st.error('새 과목명을 입력하세요.');return
            if group=='원가' and (cost<0 or cost>amount):st.error('원가 조정액은 0 이상이며 금액 이하여야 합니다.');return
            target='원가' if group=='원가' and cost==amount else '공통' if group=='원가' and cost else '판관비';db.save_adjustment(c,x,side,name,amount,target,cost,note,account_group=group);refresh()
    current=[r for r in active if r['side']==side];totals=calc.adjustment_totals(current)
    st.html(f'<div class="cc-adjust-total">계　금액 {totals[side+"_amount"]:,}　/　{cost_label} {totals[side+"_cost"]:,}　/　{sga_label} {totals[side+"_sga"]:,}</div>')

def adjustment_page(c,x):
    st.html('<div class="cc-title">과목별 세무조정 내역</div>');st.caption('표의 각 행에서 직접 수정·저장·삭제할 수 있습니다. 새 과목은 각 표의 마지막 행에서 바로 추가합니다. 원가계정 외 구분은 금액만 입력합니다.')
    active=db.adjustments(c,x['id']);deleted=[r for r in db.adjustments(c,x['id'],True) if r['deleted']]
    left,right=st.columns(2,gap='medium')
    with left:_adjustment_inline_grid(c,x,active,'add','익금산입 및 손금불산입','원가부인','판관비부인')
    with right:_adjustment_inline_grid(c,x,active,'deduct','손금산입 및 익금불산입','원가추인','판관비추인')
    linked=[r for r in active if r['source_key'].startswith('reserve:')]
    if linked:
        st.caption('유보잔액 연계 항목은 유보잔액 관리에서 수정합니다.');show_frame(pd.DataFrame([{'과목':r['name'],'금액':r['amount'],'구분':'익금산입' if r['side']=='add' else '손금산입'} for r in linked]),hide_index=True,use_container_width=True)
    if deleted:
        with st.expander('삭제자료 복구'):
            did=st.selectbox('삭제 조정항목',[r['id'] for r in deleted],format_func=lambda z:next(r['name'] for r in deleted if r['id']==z))
            if st.button('조정항목 복구',disabled=x['status']=='confirmed'):r=next(r for r in deleted if r['id']==did);db.restore_adjustment(c,x,did,r['version']);refresh()

def _statement_uploads(c,x,kinds,prefix):
    pending_delete_key=prefix+'_pending_delete';pending_delete=st.session_state.pop(pending_delete_key,None);delete_notice=''
    if pending_delete is not None:
        db.delete_import(c,x,int(pending_delete));delete_notice='선택한 원장을 삭제했습니다.'
    active=[r for r in db.imports(c,x['id']) if not r['deleted'] and r['kind'] in kinds]
    if delete_notice:st.success(delete_notice)
    for start in range(0,len(kinds),3):
        group=kinds[start:start+3];cols=st.columns(len(group))
        for col,kind in zip(cols,group):
            with col:
                st.markdown('**'+kind+' 원장**');up=st.file_uploader('XLS, XLSX 또는 CSV',type=['xls','xlsx','csv'],key=prefix+'_'+kind);parsed=None
                if up:
                    try:
                        original=ledger.parse(up.name,up.getvalue());parsed=db.filter_statement_rows(original);excluded=len(original)-len(parsed);st.caption(f'{len(parsed):,}행 인식'+(f' · [월 계]·[누 계] {excluded:,}행 제외' if excluded else '')+' · 등록 전 미리보기');show_frame(pd.DataFrame(parsed[:10]),hide_index=True,use_container_width=True)
                    except ValueError as e:st.error(str(e))
                if st.button(kind+' 원장 등록',key=prefix+'_save_'+kind,disabled=not parsed or x['status']=='confirmed',use_container_width=True):db.save_statement_import(c,x,kind,up.name,up.getvalue(),parsed);refresh()
    if active:
        with st.expander('등록 원장 관리'):
            show_frame(pd.DataFrame(active),hide_index=True,use_container_width=True);iid=st.selectbox('삭제할 원장',[r['id'] for r in active],format_func=lambda z:next(r['kind']+' · '+r['name'] for r in active if r['id']==z),key=prefix+'_delete_select')
            st.button('선택 원장 삭제',key=prefix+'_delete',disabled=x['status']=='confirmed',on_click=queue_session_value,args=(pending_delete_key,iid))

def tax_dues_page(c,x):
    st.html('<div class="cc-title">세금과공과명세서</div>');st.caption('원가·판관비 원장의 적요 문구로 손금불산입 검토대상을 찾습니다. 자동판정은 작업자가 표에서 직접 변경한 뒤 세무조정에 반영합니다.')
    _statement_uploads(c,x,db.TAX_DUES_KINDS,'cc_tax_dues')
    with st.expander('손금불산입 적요 문구 추가·수정·삭제',expanded=True):
        rules=db.statement_rules(c,x['company_id']);deleted=[r for r in db.statement_rules(c,x['company_id'],'tax_dues',True) if r['deleted']]
        show_frame(pd.DataFrame([{'ID':r['id'],'검색 문구':r['keyword']} for r in rules]),hide_index=True,use_container_width=True)
        selected=st.selectbox('수정할 문구',['새 문구']+[r['id'] for r in rules],format_func=lambda z:'새 문구' if z=='새 문구' else next(r['keyword'] for r in rules if r['id']==z),key='cc_tax_dues_rule_select');rr=next((r for r in rules if r['id']==selected),None)
        with st.form('cc_tax_dues_rule_form'):
            keyword=st.text_input('적요에 포함되는 문구',value=rr['keyword'] if rr else '');save_rule=st.form_submit_button('문구 저장·재판정',disabled=x['status']=='confirmed')
        if save_rule:db.save_statement_rule(c,x,keyword,rr['id'] if rr else None,rr['version'] if rr else None);refresh()
        if rr and st.button('선택 문구 삭제',disabled=x['status']=='confirmed'):db.delete_statement_rule(c,x,rr['id'],rr['version']);refresh()
        if deleted:
            rid=st.selectbox('삭제 문구 복구',[r['id'] for r in deleted],format_func=lambda z:next(r['keyword'] for r in deleted if r['id']==z),key='cc_tax_dues_rule_restore')
            if st.button('문구 복구',disabled=x['status']=='confirmed'):r=next(r for r in deleted if r['id']==rid);db.restore_statement_rule(c,x,rid,r['version']);refresh()
    rows=db.statement_ledger_rows(c,x['id'],db.TAX_DUES_KINDS)
    if not rows:st.info('세금과공과(원가) 또는 세금과공과(판관비) 원장을 등록하세요.');return
    frame=pd.DataFrame([{'ID':r['id'],'구분':'원가' if r['kind'].endswith('(원가)') else '판관비','일자':r['posting_date'],'계정과목':r['account'],'적요':r['description'],'차변금액':r['debit'] if r['debit'] is not None else r['amount'],'찾은 문구':str(r['business']).replace('자동:','') if str(r['business']).startswith('자동:') else '수동','세무조정 판정':r['classification'] or '손금산입'} for r in rows])
    edited=st.data_editor(frame,hide_index=True,use_container_width=True,disabled=['ID','구분','일자','계정과목','적요','차변금액','찾은 문구'],column_config={'차변금액':st.column_config.NumberColumn(format='%,d'),'세무조정 판정':st.column_config.SelectboxColumn(options=['손금불산입','손금산입'])},key='cc_tax_dues_grid')
    amounts={'원가':0,'판관비':0}
    for _,r in edited.iterrows():
        if r['세무조정 판정']=='손금불산입':amounts[r['구분']]+=money(r['차변금액'])
    cards=st.columns(3);cards[0].metric('원가 손금불산입',f'{amounts["원가"]:,}원');cards[1].metric('판관비 손금불산입',f'{amounts["판관비"]:,}원');cards[2].metric('손금불산입 합계',f'{sum(amounts.values()):,}원')
    tax_summary=pd.DataFrame([{'구분':'원가 손금불산입','금액':amounts['원가']},{'구분':'판관비 손금불산입','금액':amounts['판관비']},{'구분':'손금불산입 합계','금액':sum(amounts.values())}])
    a,b,c1,d=st.columns(4)
    if a.button('판정내역 저장',type='primary',disabled=x['status']=='confirmed',use_container_width=True):db.classify_tax_dues_rows(c,x,[(int(r['ID']),r['세무조정 판정']) for _,r in edited.iterrows()]);refresh()
    b.download_button('인쇄용 계산내역',statement_print_html('세금과공과명세서',x['year'],[('손금불산입 집계',tax_summary),('원장 판정내역',edited)]),file_name=f'{x["year"]}_세금과공과명세서_인쇄.html',mime='text/html',use_container_width=True)
    c1.download_button('CSV 내려받기',edited.to_csv(index=False).encode('utf-8-sig'),file_name=f'{x["year"]}_세금과공과명세서.csv',mime='text/csv',use_container_width=True)
    if d.button('세무조정 항목에 반영',disabled=x['status']=='confirmed',use_container_width=True):db.classify_tax_dues_rows(c,x,[(int(r['ID']),r['세무조정 판정']) for _,r in edited.iterrows()]);db.sync_tax_dues_adjustments(c,x);refresh()

def _prepaid_payload(x,items,overrides,opening_rows):
    payload={k:v for k,v in x.items() if k not in ['id','company_id','year','status','version']};payload['prepaid_overrides']=overrides;payload['prepaid_opening_rows']=opening_rows;payload.pop('prepaid_initial_opening',None)
    payload['prepaid_closing']=[{k:r.get(k) for k in ['source_key','kind','description','identifier','site','counterparty','ending']} for r in items if r.get('amount') and r.get('ending')]
    return payload
def prepaid_page(c,x):
    st.html(PREPAID_CSS);st.html('<div class="cc-title">선급비용 계산현황</div>');st.caption('기준일은 결산연도 12월 31일입니다. 차량보험은 차량번호별, 승강기·공사손해보험 등은 프로젝트와 보험대상별, 지급임차료는 지번별로 합산합니다.')
    _statement_uploads(c,x,db.PREPAID_KINDS,'cc_prepaid')
    with st.expander('프로젝트명이 비어 있을 때 · 원본에서 다시 인식'):
        st.caption('메뉴 진입 속도를 위해 원본 파일을 자동 재분석하지 않습니다. 프로젝트명이 비어 있는 경우에만 아래 버튼을 한 번 누르세요.')
        if st.button('프로젝트명 다시 인식',key='cc_prepaid_restore_projects',disabled=x['status']=='confirmed'):
            restored_at=time.perf_counter()
            with st.spinner('저장된 원본 원장에서 프로젝트명을 확인하고 있습니다…'):restored_projects=db.refresh_statement_projects(c,x,db.PREPAID_KINDS,force=True)
            st.success(f'프로젝트명 {restored_projects:,}건 확인·복원 완료 · {time.perf_counter()-restored_at:.2f}초')
    draft_override_key=f'cc_prepaid_draft_overrides_{x["id"]}';draft_opening_key=f'cc_prepaid_draft_openings_{x["id"]}'
    if draft_override_key not in st.session_state:st.session_state[draft_override_key]={}
    if draft_opening_key not in st.session_state:st.session_state[draft_opening_key]={}
    prior=db.prior_case(c,x['company_id'],x['year']);prior_closing=prior.get('prepaid_closing',[]) if prior else [];overrides=dict(x.get('prepaid_overrides',{}));overrides.update(st.session_state[draft_override_key]);current=db.statement_ledger_rows(c,x['id'],db.PREPAID_KINDS);items=prepaid.build(current,[],overrides,x['year'])
    saved_openings=x.get('prepaid_opening_rows')
    if saved_openings is not None:opening_rows=[dict(r) for r in saved_openings]
    elif prior_closing:opening_rows=prepaid.grouped_openings(prior_closing)
    else:
        opening_rows=[];legacy=dict(x.get('prepaid_initial_opening',{}))
        for kind,amount in legacy.items():
            if money(amount):opening_rows.append({'source_key':prepaid.opening_source_key(kind,'미분류 전기잔액',len(opening_rows)),'kind':kind,'identifier':'미분류 전기잔액','opening':money(amount),'note':'기존 총액 입력자료 · 차량번호·보험대상·지번을 수정하세요.'})
        for item in items:
            if item.get('opening'):opening_rows.append({'source_key':prepaid.opening_source_key(item['kind'],item['identifier'],len(opening_rows)),'kind':item['kind'],'identifier':item['identifier'],'opening':item['opening'],'note':'기존 개별 입력자료'})
    if prior_closing and saved_openings is None:st.success(f'{x["year"]-1}년 기말 선급비용 {sum(int(r.get("ending") or 0) for r in prior_closing):,}원을 차량번호·보험대상·지번별 전기잔액으로 자동 이월했습니다.')
    elif not prior_closing:st.info('최초 적용연도입니다. 당기계약 행의 전기잔액 칸에 직접 입력하세요. 당기계약이 없는 차량번호·보험대상·지번만 전기잔액 전용 행으로 추가합니다.')
    saved_rules=x.get('prepaid_keyword_rules') if 'prepaid_keyword_rules' in x else None
    active_rules=prepaid.keyword_rules(saved_rules)
    with st.expander('적요 포함·제외문구 설정'):
        st.caption('제외문구가 포함문구보다 먼저 적용됩니다. “대체”처럼 범위가 너무 넓은 단어 대신 “기한경과 대체”처럼 구체적인 문구를 사용하세요.')
        rule_cols=st.columns(2)
        scope_options=['전체','보험료 전체',*db.PREPAID_KINDS]
        include_frame=pd.DataFrame([{'적용 원장':r.get('scope','전체'),'적요 문구':r.get('keyword','')} for r in active_rules if r.get('action')=='include'],columns=['적용 원장','적요 문구'])
        exclude_frame=pd.DataFrame([{'적용 원장':r.get('scope','전체'),'적요 문구':r.get('keyword','')} for r in active_rules if r.get('action')=='exclude'],columns=['적용 원장','적요 문구'])
        with rule_cols[0]:
            st.markdown('**포함문구**')
            include_edit=st.data_editor(include_frame,hide_index=True,use_container_width=True,num_rows='dynamic',disabled=x['status']=='confirmed',column_config={'적용 원장':st.column_config.SelectboxColumn(options=scope_options,required=True),'적요 문구':st.column_config.TextColumn(required=True)},key='cc_prepaid_include_rules')
        with rule_cols[1]:
            st.markdown('**제외문구**')
            exclude_edit=st.data_editor(exclude_frame,hide_index=True,use_container_width=True,num_rows='dynamic',disabled=x['status']=='confirmed',column_config={'적용 원장':st.column_config.SelectboxColumn(options=scope_options,required=True),'적요 문구':st.column_config.TextColumn(required=True)},key='cc_prepaid_exclude_rules')
        active_rules=[]
        for action,frame in [('include',include_edit),('exclude',exclude_edit)]:
            for _,rule in frame.iterrows():
                keyword=str(rule.get('적요 문구') or '').strip()
                if keyword:active_rules.append({'action':action,'scope':str(rule.get('적용 원장') or '전체'),'keyword':keyword})
    extra_key=f'cc_prepaid_extra_openings_{x["id"]}'
    if extra_key not in st.session_state:st.session_state[extra_key]=[]
    with st.expander('＋ 당기계약이 없는 전기잔액 전용 행 추가'):
        with st.form('cc_prepaid_add_opening_form',clear_on_submit=True):
            add_cols=st.columns([1.2,1.2,1,1.4]);add_kind=add_cols[0].selectbox('구분',db.PREPAID_KINDS,key='cc_prepaid_add_kind');add_identifier=add_cols[1].text_input('차량번호·보험대상·지번',key='cc_prepaid_add_identifier');add_opening=money_field(add_cols[2],'전기잔액',0,key='cc_prepaid_add_amount');add_note=add_cols[3].text_input('비고',key='cc_prepaid_add_note');add_submit=st.form_submit_button('전기잔액 전용 행 추가',disabled=x['status']=='confirmed')
        if add_submit:
            if not add_identifier.strip() or add_opening<=0:st.error('차량번호·보험대상·지번과 전기잔액을 입력하세요.')
            else:
                st.session_state[extra_key].append({'source_key':prepaid.opening_source_key(add_kind,add_identifier,len(st.session_state[extra_key])),'kind':add_kind,'identifier':add_identifier.strip(),'opening':add_opening,'note':add_note});refresh()
    for opening_row in opening_rows:
        for source_key,draft in st.session_state[draft_opening_key].items():
            same_source=str(opening_row.get('source_key') or '')==str(source_key);same_identifier=str(opening_row.get('kind') or '')==str(draft.get('kind') or '') and str(opening_row.get('identifier') or '')==str(draft.get('original_identifier') or '')
            if same_source or same_identifier:opening_row['identifier']=draft.get('identifier',opening_row.get('identifier',''));opening_row['opening']=money(draft.get('opening',opening_row.get('opening')))
    integrated=prepaid.merge_openings(items,[*opening_rows,*st.session_state[extra_key]])
    deleted_key=f'cc_prepaid_deleted_openings_{x["id"]}'
    if deleted_key not in st.session_state:st.session_state[deleted_key]=[]
    integrated=[r for r in integrated if r['source_key'] not in st.session_state[deleted_key]]
    for row in integrated:
        draft=st.session_state[draft_opening_key].get(row['source_key'],{})
        if draft:
            row.update({k:draft[k] for k in ['identifier','opening'] if k in draft});row['combined']=money(row.get('opening'))+money(row.get('current_expense'))
    if not integrated:st.info('보험료 또는 지급임차료 원장을 등록하거나 전기잔액 전용 행을 추가하세요.');return
    st.markdown('**당기원장 계약별 통합 계산내역**')
    st.caption('제외가 명확한 자료는 숨기고, 기간·보험대상·포함문구·자동연결을 확인해야 하는 자료만 기본 표시합니다. 전체 자료는 계속 계산되며 페이지 이동 중 수정값도 임시 보관됩니다.')
    def prepaid_state(source):
        base=dict(source);is_contract=base.get('ledger_row_id') is not None
        if is_contract:z=prepaid.calculate(base,x['year']);manual_mode=str(base.get('manual_inclusion') or '자동판정')
        else:z={**base,'combined':money(base.get('opening')),'valid':True};manual_mode='반영'
        error=prepaid.validation_error(z);rule_ok,rule_reason=prepaid.keyword_decision(z,active_rules)
        if manual_mode=='반영':rule_ok,rule_reason=True,'수동 반영'
        elif manual_mode=='제외':rule_ok,rule_reason=False,'수동 제외'
        z['manual_inclusion']=manual_mode;z['rule_ok']=rule_ok;z['rule_reason']=rule_reason
        clear_excluded=manual_mode=='제외' or (not rule_ok and (str(rule_reason).startswith('제외문구:') or rule_reason=='수동 제외'))
        needs_review=bool(error) or '포함문구 없음' in str(rule_reason) or z.get('period_source')=='동일 보험대상 기간 자동연결'
        category='제외' if clear_excluded else ('검토 필요' if needs_review else '정상 반영')
        return {'z':z,'manual_mode':manual_mode,'error':error,'rule_ok':rule_ok,'rule_reason':rule_reason,'category':category}
    initial_states={r['source_key']:prepaid_state(r) for r in integrated};counts={name:sum(state['category']==name for state in initial_states.values()) for name in ['검토 필요','정상 반영','제외']}
    summary_cols=st.columns(3);summary_cols[0].metric('검토 필요',f'{counts["검토 필요"]:,}건');summary_cols[1].metric('정상 반영',f'{counts["정상 반영"]:,}건');summary_cols[2].metric('화면 숨김·제외',f'{counts["제외"]:,}건')
    view_key=f'cc_prepaid_view_{x["id"]}';view_mode=st.radio('표시 자료',['검토 필요만','정상 반영자료 보기','제외자료를 뺀 전체'],horizontal=True,key=view_key)
    display_integrated=[r for r in integrated if (initial_states[r['source_key']]['category']=='검토 필요' if view_mode=='검토 필요만' else initial_states[r['source_key']]['category']=='정상 반영' if view_mode=='정상 반영자료 보기' else initial_states[r['source_key']]['category']!='제외')]
    page_size=25;page_count=max(1,(len(display_integrated)+page_size-1)//page_size);page_key=f'cc_prepaid_page_{x["id"]}_{view_mode}';saved_page=max(1,min(page_count,int(st.session_state.get(page_key) or 1)));st.session_state[page_key]=saved_page
    if display_integrated:
        page_cols=st.columns([1,3]);page=page_cols[0].selectbox('계산내역 페이지',list(range(1,page_count+1)),key=page_key);page_start=(page-1)*page_size;page_end=min(len(display_integrated),page_start+page_size);page_items=display_integrated[page_start:page_end];page_cols[1].info(f'선택 자료 {len(display_integrated):,}건 중 {page_start+1:,}~{page_end:,}건 표시 · {page}/{page_count} 페이지')
    else:
        page_items=[];st.success('현재 표시 조건에 해당하는 자료가 없습니다.')
    visible_keys={r['source_key'] for r in page_items}
    ratios=[.62,.78,.86,1.55,.88,.66,.66,.76,.76,.68,.68,.68,.82,.76,1.0];headers=['자료구분','구분','프로젝트명','원장 적요','차량번호·보험대상·지번','전기잔액','원장금액','계약시작일','계약종료일','선급일수/전체일수','선급비용','당기비용','전기잔액+당기비용','반영선택','판정결과'];head=st.columns(ratios,gap='small')
    if page_items:
        for col,label in zip(head,headers):col.html(f'<div class="cc-pp-head">{label}</div>')
    contract_keys={r['source_key'] for r in integrated if r.get('ledger_row_id') is not None};new_overrides={key:dict(value) for key,value in overrides.items() if key in contract_keys};rebuilt=[]
    for index,source in enumerate(integrated):
        base=dict(source);key=base['source_key'];is_contract=base.get('ledger_row_id') is not None;visible=key in visible_keys
        if not visible:
            rebuilt.append(initial_states[key]['z']);continue
        cols=st.columns(ratios,gap='small')
        description=str(base.get('description') or '전기 선급비용')
        cols[0].html('<div class="cc-pp-cell">'+('당기계약' if is_contract else '전기잔액 전용')+'</div>');cols[1].html(f'<div class="cc-pp-cell">{escape(str(base["kind"]))}</div>');cols[2].html(f'<div class="cc-pp-cell">{escape(str(base.get("site") or "－"))}</div>');cols[3].html(f'<div class="cc-pp-cell cc-pp-desc" title="{escape(description,quote=True)}">{escape(description)}</div>')
        identifier=cols[4].text_input('차량번호·보험대상·지번',value=str(base.get('identifier') or ''),key=f'cc_pp_id_{key}',disabled=x['status']=='confirmed',label_visibility='collapsed')
        opening=money_field(cols[5],'전기잔액',base.get('opening'),key=f'cc_pp_opening_{key}',disabled=x['status']=='confirmed',label_visibility='collapsed')
        cols[6].html(f'<div class="cc-pp-cell cc-pp-num">{money(base.get("amount")):,}</div>')
        if is_contract:
            start=cols[7].text_input('계약시작일',value=str(base.get('start') or ''),key=f'cc_pp_start_{key}',disabled=x['status']=='confirmed',label_visibility='collapsed');end=cols[8].text_input('계약종료일',value=str(base.get('end') or ''),key=f'cc_pp_end_{key}',disabled=x['status']=='confirmed',label_visibility='collapsed');change={'identifier':identifier.strip(),'start':start,'end':end,'opening':0,'note':str(base.get('note') or '')};base.update(change);base['opening']=opening;z=prepaid.calculate(base,x['year'])
        else:
            cols[7].html('<div class="cc-pp-cell">－</div>');cols[8].html('<div class="cc-pp-cell">－</div>');z={**base,'identifier':identifier.strip(),'opening':opening,'combined':opening,'valid':True};change=None
        days=f'{money(z.get("prepaid_days")):,}/{money(z.get("total_days")):,}' if is_contract and z.get('valid') else '－'
        cols[9].html(f'<div class="cc-pp-cell cc-pp-days">{days}</div>');cols[10].html(f'<div class="cc-pp-cell cc-pp-num">{money(z.get("ending")):,}</div>');cols[11].html(f'<div class="cc-pp-cell cc-pp-num">{money(z.get("current_expense")):,}</div>');cols[12].html(f'<div class="cc-pp-cell cc-pp-auto">{money(z.get("combined")):,}</div>')
        if is_contract:
            modes=['자동판정','반영','제외'];saved_mode=str(base.get('manual_inclusion') or '자동판정');saved_mode=saved_mode if saved_mode in modes else '자동판정';manual_mode=cols[13].selectbox('반영선택',modes,index=modes.index(saved_mode),key=f'cc_pp_mode_{key}',disabled=x['status']=='confirmed',label_visibility='collapsed');change['manual_inclusion']=manual_mode;st.session_state[draft_override_key][key]=dict(change);new_overrides[key]=dict(change)
        else:manual_mode='반영';cols[13].html('<div class="cc-pp-cell cc-pp-ok">자동반영</div>')
        st.session_state[draft_opening_key][key]={'kind':str(base.get('kind') or ''),'original_identifier':str(source.get('identifier') or ''),'identifier':identifier.strip(),'opening':opening}
        error=prepaid.validation_error(z);rule_ok,rule_reason=prepaid.keyword_decision(z,active_rules)
        if manual_mode=='반영':rule_ok,rule_reason=True,'수동 반영'
        elif manual_mode=='제외':rule_ok,rule_reason=False,'수동 제외'
        z['manual_inclusion']=manual_mode;z['rule_ok']=rule_ok;z['rule_reason']=rule_reason
        if error:status=('반영 대기 · ' if manual_mode=='반영' else '저장 제외 · ')+error
        elif not rule_ok:status='계산 제외 · '+rule_reason
        else:status=('정상 반영 · '+rule_reason)+((' · '+str(z.get('period_source'))) if z.get('period_source')=='동일 보험대상 기간 자동연결' else '')
        cols[14].html(f'<div class="cc-pp-cell {"cc-pp-error" if error or not rule_ok else "cc-pp-ok"}">{escape(status)}</div>')
        if not is_contract and cols[14].button('전기잔액 행 삭제',key=f'cc_pp_delete_{key}',disabled=x['status']=='confirmed',use_container_width=True):st.session_state[deleted_key].append(key);refresh()
        rebuilt.append(z)
    excluded=[r for r in rebuilt if prepaid.validation_error(r) or not r.get('rule_ok',True)];included=[r for r in rebuilt if not prepaid.validation_error(r) and r.get('rule_ok',True)]
    opening_rows_to_save=prepaid.opening_rows_from_items(included)
    grouped=prepaid.grouped(included);grouped_frame=pd.DataFrame([{'구분':r['kind'],'차량번호·보험대상·지번':r['identifier'],'계약건수':r['contract_count'],'전기잔액':r['opening'],'원장금액':r['amount'],'선급비용':r['ending'],'당기비용':r['current_expense'],'전기+당기비용':r['combined']} for r in grouped]);st.markdown('**차량번호·보험대상·지번별 합산 결과**');show_frame(grouped_frame,hide_index=True,use_container_width=True)
    sums=prepaid.summary(included);cards=st.columns(3)
    for col,kind in zip(cards,db.PREPAID_KINDS):col.metric(kind+' 기말 선급비용',f'{sums[kind]["ending"]:,}원',delta=f'전기 {sums[kind]["opening"]:,}원')
    if excluded:
        reasons={}
        for row in excluded:
            reason=prepaid.validation_error(row) or row.get('rule_reason') or '검토대상';reasons[reason]=reasons.get(reason,0)+1
        st.warning(' · '.join(f'{reason} {count:,}건' for reason,count in reasons.items())+'은 합계·저장·세무조정 반영에서 제외됩니다. 오류 입력 또는 적요문구 설정을 수정하면 다시 포함됩니다.')
    current_print=pd.DataFrame([{'자료구분':'당기계약' if r.get('ledger_row_id') is not None else '전기잔액 전용','구분':r['kind'],'프로젝트명':r.get('site',''),'원장 적요':r.get('description',''),'차량번호·보험대상·지번':r['identifier'],'거래처':r.get('counterparty',''),'전기잔액':r['opening'],'원장금액':r['amount'],'계약시작일':r['start'],'계약종료일':r['end'],'기간판정':r.get('period_source',''),'전체일수':r.get('total_days',0),'선급일수':r.get('prepaid_days',0),'선급비용':r['ending'],'당기비용':r['current_expense'],'전기잔액+당기비용':r['combined'],'반영선택':r.get('manual_inclusion','자동판정'),'반영상태':'정상 반영 · '+str(r.get('rule_reason') or '')} for r in included])
    a,b,c1,d=st.columns(4);payload=_prepaid_payload(x,included,new_overrides,opening_rows_to_save);payload['prepaid_keyword_rules']=active_rules
    if a.button('계산내역 저장',type='primary',disabled=x['status']=='confirmed',use_container_width=True):
        saved_at=time.perf_counter();db.save_case(c,x,payload,x['version']);elapsed=time.perf_counter()-saved_at;st.session_state[extra_key]=[];st.session_state[deleted_key]=[];st.session_state[draft_override_key]={};st.session_state[draft_opening_key]={};st.success(f'계산내역 저장 완료 · 실제 DB 저장 {elapsed:.2f}초')
    b.download_button('인쇄용 계산내역',statement_print_html('선급비용명세서',x['year'],[('당기원장 계약별 통합 계산내역',current_print),('차량번호·보험대상·지번별 검산 결과',grouped_frame)]),file_name=f'{x["year"]}_선급비용명세서_인쇄.html',mime='text/html',use_container_width=True)
    c1.download_button('CSV 내려받기',grouped_frame.to_csv(index=False).encode('utf-8-sig'),file_name=f'{x["year"]}_선급비용명세서.csv',mime='text/csv',use_container_width=True)
    if d.button('세무조정·유보잔액에 반영',disabled=x['status']=='confirmed',use_container_width=True):
        saved_at=time.perf_counter();db.save_case(c,x,payload,x['version']);db.sync_prepaid_adjustments(c,x,sums);elapsed=time.perf_counter()-saved_at;st.session_state[extra_key]=[];st.session_state[deleted_key]=[];st.session_state[draft_override_key]={};st.session_state[draft_opening_key]={};st.success(f'세무조정·유보잔액 반영 완료 · 실제 DB 처리 {elapsed:.2f}초')

def promotion_page(c,x):
    st.html('<div class="cc-title">기업업무추진비 조정명세서 금액 집계</div>');st.caption('위하고 입력 행 ⑤~⑱을 그대로 구성합니다. 수입금액·수입금액 한도·한도초과액은 계산하지 않으며, 6개 원장의 차변 거래금액만 사용합니다.')
    _statement_uploads(c,x,db.PROMOTION_KINDS,'cc_promotion')
    ledger_rows=db.statement_ledger_rows(c,x['id'],db.PROMOTION_KINDS)
    if not ledger_rows:st.info('접대비(신용카드등·경조사비·기타접대비)의 원가·판관비 원장을 등록하세요.');return

    settings=dict(x.get('promotion_settings',{}));threshold_cols=st.columns([1,1,2])
    condolence_threshold=money_field(threshold_cols[0],'경조사비 기준금액',settings.get('condolence_threshold',200000),key='cc_promotion_condolence_threshold',disabled=x['status']=='confirmed')
    general_threshold=money_field(threshold_cols[1],'일반 기준금액',settings.get('general_threshold',30000),key='cc_promotion_general_threshold',disabled=x['status']=='confirmed')
    threshold_cols[2].info('기본 자동판정: 경조사비는 20만원 초과 거래, 일반 기업업무추진비는 3만원 초과 거래입니다. 원장만으로 확정할 수 없는 금액은 아래 표에서 직접 수정합니다.')
    working=promotion.build_rows(ledger_rows,x.get('promotion_overrides',{}),condolence_threshold,general_threshold)
    labels={
        'private':'⑥ 사적사용','condolence_unused':'⑨ 경조 미사용','condolence_total':'⑩ 경조 총액',
        'foreign_unused':'⑪ 국외 미사용','foreign_total':'⑫ 국외 총액','farmer_unsubmitted':'⑬ 농어민 미제출',
        'farmer_total':'⑭ 농어민 총액','general_unused':'⑮ 일반 미사용','general_total':'⑯ 일반 총액',
        'culture':'문화사업','traditional_market':'전통시장','local_gift':'지역사랑상품권'}
    detail_rows=[]
    for row in working:
        item={'ID':row['id'],'판/도':row['division'],'원장 구분':row['kind'],'일자':row['date'],'거래처':row['counterparty'],'적요':row['description'],'차변금액':row['amount']}
        item.update({label:row[field] for field,label in labels.items()});detail_rows.append(item)
    st.markdown('**거래별 판정·수정**')
    st.caption('파란색 차변금액은 원장값이며 변경하지 않습니다. ⑥·⑨~⑯과 별도 구분금액은 작업자가 거래별로 직접 수정할 수 있습니다. 각 입력금액은 해당 거래의 차변금액을 초과할 수 없습니다.')
    detail=pd.DataFrame(detail_rows)
    editable_columns=list(labels.values());disabled_columns=['ID','판/도','원장 구분','일자','거래처','적요','차변금액']
    edited=st.data_editor(detail,hide_index=True,use_container_width=True,disabled=disabled_columns,column_config={name:st.column_config.NumberColumn(format='%,d') for name in ['차변금액',*editable_columns]},key='cc_promotion_grid')
    by_id={row['id']:dict(row) for row in working};reverse={label:field for field,label in labels.items()};rebuilt=[]
    for _,record in edited.iterrows():
        row=by_id[int(record['ID'])]
        for label,field in reverse.items():row[field]=money(record[label])
        rebuilt.append(row)
    errors=promotion.validate(rebuilt)
    if errors:
        st.error('\n'.join(errors[:10])+(f'\n외 {len(errors)-10:,}건' if len(errors)>10 else ''))

    summary=promotion.summary(rebuilt);summary_rows=[]
    for label,values in summary:
        if values is None:summary_rows.append({'위하고 입력 구분':label,'합계':None,'접대비(기업업무추진비)(판)':None,'접대비(기업업무추진비)(도)':None})
        else:summary_rows.append({'위하고 입력 구분':label,'합계':values['합계'],'접대비(기업업무추진비)(판)':values['판'],'접대비(기업업무추진비)(도)':values['도']})
    st.markdown('**위하고 입력용 집계금액**');show_frame(pd.DataFrame(summary_rows),hide_index=True,use_container_width=True)
    account=summary[0][1];disallowance=summary[16][1]
    cards=st.columns(4);cards[0].metric('⑤ 계정금액',f'{account["합계"]:,}원');cards[1].metric('판관비(판)',f'{account["판"]:,}원');cards[2].metric('공사원가(도)',f'{account["도"]:,}원');cards[3].metric('⑱ 부인액',f'{disallowance["합계"]:,}원')

    payload={k:v for k,v in x.items() if k not in ['id','company_id','year','status','version']};payload['promotion_settings']={'condolence_threshold':condolence_threshold,'general_threshold':general_threshold};payload['promotion_overrides']=promotion.overrides_from_rows(rebuilt)
    save_col,reset_col,print_col,excel_col,csv_col=st.columns(5)
    if save_col.button('판정내역 저장',type='primary',disabled=x['status']=='confirmed' or bool(errors),use_container_width=True):db.save_case(c,x,payload,x['version']);refresh()
    if reset_col.button('자동 판정으로 초기화',disabled=x['status']=='confirmed',use_container_width=True):
        reset_payload=dict(payload);reset_payload['promotion_overrides']={};db.save_case(c,x,reset_payload,x['version']);refresh()
    print_col.download_button('인쇄용 계산내역',statement_print_html('기업업무추진비명세서',x['year'],[('위하고 입력용 집계금액',pd.DataFrame(summary_rows)),('거래별 판정내역',edited)]),file_name=f'{x["year"]}_기업업무추진비명세서_인쇄.html',mime='text/html',use_container_width=True)
    out=BytesIO()
    with pd.ExcelWriter(out,engine='openpyxl') as writer:pd.DataFrame(summary_rows).to_excel(writer,index=False,sheet_name='위하고 입력금액');edited.to_excel(writer,index=False,sheet_name='거래별 판정내역')
    excel_col.download_button('Excel 내려받기',out.getvalue(),file_name=f'{x["year"]}_기업업무추진비_위하고입력.xlsx',mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',use_container_width=True)
    csv_col.download_button('CSV 내려받기',pd.DataFrame(summary_rows).to_csv(index=False).encode('utf-8-sig'),file_name=f'{x["year"]}_기업업무추진비_위하고입력.csv',mime='text/csv',use_container_width=True)

def adjustment_statement_page(c,x,name):
    if name=='세금과공과명세서':return tax_dues_page(c,x)
    if name=='선급비용명세서':return prepaid_page(c,x)
    if name=='기업업무추진비명세서':return promotion_page(c,x)
    st.html(f'<div class="cc-title">{name}</div>');st.info('원본 명세서 양식과 계산 기준을 반영하기 전까지 임의 계산하지 않습니다.')

def import_page(c,x,embedded=False):
    pending_delete_key='cc_income_pending_delete';pending_delete=st.session_state.pop(pending_delete_key,None);delete_notice=''
    if pending_delete is not None:
        db.delete_import(c,x,int(pending_delete));delete_notice='선택한 원장을 삭제했습니다.'
    if not embedded:st.html('<div class="cc-title">계정별 원장 업로드·소득구분</div>')
    else:st.subheader('소득구분용 원장 업로드·적요 분류')
    if delete_notice:st.success(delete_notice)
    kind=st.selectbox('원장 종류',['합계잔액·계정별원장','영업외수익','영업외비용']);up=st.file_uploader('XLSX 또는 CSV 원장',type=['xlsx','csv'])
    parsed=None
    if up:
        try:parsed=ledger.parse(up.name,up.getvalue());show_frame(pd.DataFrame(parsed[:200]),hide_index=True,use_container_width=True);st.caption(f'전체 {len(parsed):,}행 중 최대 200행 미리보기')
        except ValueError as e:st.error(str(e))
    if st.button('미리보기 자료 등록',disabled=not parsed or x['status']=='confirmed'):
        db.save_import(c,x,kind,up.name,up.getvalue(),parsed);refresh()
    imports=db.imports(c,x['id']);active=[r for r in imports if not r['deleted']]
    if active:
        st.subheader('등록 원장');show_frame(active,hide_index=True,use_container_width=True)
        if db.imports_need_amount_rebuild(c,x['id']):
            st.warning('기존 원장에 잔액 기준 금액이 남아 있습니다. 아래 버튼을 한 번 누르면 원본 파일을 다시 읽어 영업외수익은 대변, 영업외비용은 차변 기준으로 고칩니다.')
            if st.button('기존 원장 차변·대변 기준 재계산',type='primary',disabled=x['status']=='confirmed'):
                count=db.rebuild_ledger_amounts(c,x);st.success(f'{count:,}개 원장을 차변·대변 기준으로 재계산했습니다.');refresh()
        iid=st.selectbox('관리할 원장',[r['id'] for r in active],format_func=lambda z:next(r['kind']+' · '+r['name'] for r in active if r['id']==z))
        st.button('선택 원장 삭제',disabled=x['status']=='confirmed',on_click=queue_session_value,args=(pending_delete_key,iid),key='cc_income_delete')
    allrows=db.ledger_rows(c,x['id'])
    if allrows:
        with st.expander('감면분 적요 문구 관리·추천',expanded=True):
            rules=db.income_rules(c,x['company_id']);deleted_rules=[r for r in db.income_rules(c,x['company_id'],True) if r['deleted']]
            st.caption('잡이익 적요에서 환입, 기부금시인액, 보상비, 고재매각, 환수 등의 등록 문구를 찾아 감면분으로 분류합니다.')
            show_frame(pd.DataFrame([{'ID':r['id'],'적용 대상':'계정과목' if r['kind']=='account' else '적요','문구':r['keyword']} for r in rules]),hide_index=True,use_container_width=True)
            selected=st.selectbox('수정할 감면분 문구',['새 문구']+[r['id'] for r in rules],format_func=lambda z:'새 문구' if z=='새 문구' else next(r['keyword'] for r in rules if r['id']==z));rr=next((r for r in rules if r['id']==selected),None)
            with st.form('cc_income_rule'):
                q1,q2=st.columns(2);rule_kind=q1.selectbox('검색 대상',['description','account'],index=['description','account'].index(rr['kind']) if rr else 0,format_func=lambda z:'적요' if z=='description' else '계정과목');keyword=q2.text_input('포함 문구',value=rr['keyword'] if rr else '');rule_save=st.form_submit_button('문구 저장·원장 재분류',disabled=x['status']=='confirmed')
            if rule_save:db.save_income_rule(c,x,rule_kind,keyword,rr['id'] if rr else None,rr['version'] if rr else None);refresh()
            if rr and st.button('선택 문구 삭제',disabled=x['status']=='confirmed'):db.delete_income_rule(c,x,rr['id'],rr['version']);refresh()
            recommendations=db.rule_recommendations(c,x)
            if recommendations:st.markdown('**추천 문구**');show_frame(pd.DataFrame(recommendations),hide_index=True,use_container_width=True)
            if st.button('현재 문구로 원장 다시 분류',disabled=x['status']=='confirmed'):db.apply_income_rules(c,x);refresh()
            if deleted_rules:
                rid=st.selectbox('삭제 문구 복구',[r['id'] for r in deleted_rules],format_func=lambda z:next(r['keyword'] for r in deleted_rules if r['id']==z))
                if st.button('감면분 문구 복구',disabled=x['status']=='confirmed'):r=next(r for r in deleted_rules if r['id']==rid);db.restore_income_rule(c,x,rid,r['version']);refresh()
        summary=ledger.aggregate(allrows)
        if st.button('원장 집계금액을 파란색 항목에 적용',disabled=x['status']=='confirmed'):
            payload={k:v for k,v in x.items() if k not in ['id','company_id','year','status','version']};values=dict(payload.get('values',{}));tax=dict(payload.get('tax',{}))
            for k in ['construction_revenue','service_revenue','cost','sga','nonop_income','nonop_expense']:
                if summary.get(k):values[k]=summary[k]
            for k in ['prepaid_corp_interim','prepaid_corp_withholding','prepaid_local']:
                if summary.get(k):tax[k]=summary[k]
            tax['prepaid_corp']=money(tax.get('prepaid_corp_interim'))+money(tax.get('prepaid_corp_withholding'))
            payload.update(values=values,tax=tax);save_payload(c,x,payload)
        subset=[r for r in allrows if r['kind']=='영업외수익' and '잡이익' in db.normalized(r['account'])]
        if subset:
            st.subheader('잡이익 적요 분류');frame=pd.DataFrame([{'ID':r['id'],'구분':r['kind'],'계정과목':r['account'],'적요':r['description'],'금액':r['amount'],'소득구분':r['classification']} for r in subset]);edited=st.data_editor(frame,hide_index=True,use_container_width=True,disabled=['ID','구분','계정과목','적요','금액'],column_config={'소득구분':st.column_config.SelectboxColumn(options=['','감면분','기타분'])})
            if st.button('소득구분 저장',disabled=x['status']=='confirmed'):db.classify_rows(c,x,[(int(r['ID']),r['소득구분'],'') for _,r in edited.iterrows()]);refresh()
    deleted=[r for r in imports if r['deleted']]
    if deleted:
        with st.expander('삭제 원장 복구'):
            iid=st.selectbox('삭제 원장',[r['id'] for r in deleted],format_func=lambda z:next(r['name'] for r in deleted if r['id']==z),key='cc_restore_import')
            if st.button('원장 복구'):db.restore_import(c,x,iid);refresh()

def progress_page(c,x,company):
    st.html('<div class="cc-title">공사수입·원가대비 및 진행률 조정 검산</div>');st.caption('기초정보의 예상 진행률조정 총액을 적격 현장의 조정 가능범위 안에서 배분하고 차기까지 이월 관리합니다.')
    up=st.file_uploader('공사수입·원가대비표 Excel',type=['xlsx'],key='cc_progress_upload');parsed=None;sheet=''
    if up:
        try:
            choices=progress.sheet_candidates(up.getvalue(),x['year'],company['name']);sheet=st.selectbox('가져올 법인·연도 시트',choices) if choices else ''
            if sheet:sheet,parsed=progress.parse(up.getvalue(),x['year'],company['name'],sheet);st.success(f'{sheet} · 현장 {len(parsed):,}건을 확인했습니다. 기존 공사관리번호는 수정하고 새로운 현장만 추가합니다.');show_frame(pd.DataFrame(parsed[:20]),hide_index=True,use_container_width=True)
        except ValueError as e:st.error(str(e))
    if st.button('미리보기 현장자료 등록·갱신',type='primary',disabled=not parsed or x['status']=='confirmed'):
        try:db.save_progress_import(c,x,up.name,sheet,up.getvalue(),parsed);refresh()
        except ValueError as e:st.error(str(e))
    rows=db.progress_projects(c,x['id']);extra=dict(x.get('progress',{}));flow_revenue=money(x.get('values',{}).get('construction_revenue'));ledger_revenue=money(extra.get('ledger_construction_revenue',flow_revenue));flow_adjustment=money(x.get('values',{}).get('progress_adjustment'));calculation_extra={**extra,'ledger_construction_revenue':ledger_revenue};s=progress.summary(rows,calculation_extra)
    tabs=st.tabs(['현장별 자동배분','현장별 진행률 검산','원가율·조정값 관리','업로드·변경 이력·차기이월','A4 출력·Excel'])
    with tabs[0]:
        target_col,save_col=st.columns([3,1]);target_amount=money_field(target_col,'목표 공사진행율 총액',flow_adjustment,key='progress_target_amount',disabled=x['status']=='confirmed');save_target=save_col.button('목표금액 저장',type='primary',use_container_width=True,disabled=x['status']=='confirmed' or target_amount==flow_adjustment)
        if target_amount!=flow_adjustment:st.info(f'입력한 목표 {target_amount:,}원을 먼저 저장하면 아래 자동배분 기준에 적용됩니다. 현재 저장된 목표는 {flow_adjustment:,}원입니다.')
        if save_target:
            payload={k:v for k,v in x.items() if k not in ['id','company_id','year','status','version']};values=dict(payload.get('values',{}));values['progress_adjustment']=target_amount;payload['values']=values;save_payload(c,x,payload)
        methods={'excel':'① Excel 당기조정액 그대로','cost':'② 목표 차액만 당기원가 비율로 배분','rate':'③ 예상원가율로 정밀 배분'};method=st.radio('배분 기준',list(methods),format_func=lambda key:methods[key],horizontal=True,key='progress_allocation_method');plan=progress.allocate(rows,flow_adjustment,method);cards=st.columns(5)
        for col,label,value in zip(cards,['배분 목표','Excel 당기조정액 합계','목표와 Excel 차이','추가배분 가능범위','배분안 합계'],[plan['target'],plan['excel_total'],plan['difference'],plan['available'],plan['allocated']]):col.metric(label,f'{value:,}원')
        if method=='excel' and plan['residual']:st.info(f'Excel 당기조정액을 그대로 적용하면 목표와 {plan["residual"]:,}원 차이납니다. 차이를 맞추려면 ② 차액 자동배분을 선택하세요.')
        elif plan['residual']:st.error(f'선택한 기준으로 {plan["residual"]:,}원을 배분할 수 없습니다. 당기원가·계약잔액·준공상태·작업자 고정값을 확인하세요.')
        elif rows:st.success('예상 진행률조정 총액과 현장별 배분안 합계가 일치합니다.')
        allocation_view=[]
        for r in plan['rows']:
            reason=('예상원가율 확인' if method=='rate' and not r['rate_ready'] and r['eligible'] else r['allocation_reason'])
            adjusted_total=r['total_revenue']+r['proposed_adjustment'];adjusted_rate=(r['total_cost']/adjusted_total*100 if adjusted_total else 0)
            allocation_view.append({'공사관리번호':r['project_key'],'발주처':r['client'],'공사명':r['project'],'상태':r['status'],'배분방식':r['allocation_mode'],'자동판정':reason,'수입누계·조정전':r['total_revenue'],'원가누계':r['total_cost'],'누계원가율·조정전(%)':round(r['actual_cost_rate']*100,3),'Excel당기진행율':r['current_adjustment'],'적정진행율':r['natural_adjustment'],'목표공사진행율·배분안':r['proposed_adjustment'],'수입누계·조정후':adjusted_total,'누계원가율·조정후(%)':round(adjusted_rate,3),'차기이월':'Y' if r.get('carryover_eligible') else 'N'})
        show_frame(pd.DataFrame(allocation_view),hide_index=True,use_container_width=True,column_config={k:st.column_config.NumberColumn(format='%,d') for k in ['수입누계·조정전','원가누계','Excel당기진행율','적정진행율','목표공사진행율·배분안','수입누계·조정후']})
        save_label='Excel 당기조정액 그대로 저장' if method=='excel' else '목표금액과 일치하는 배분안 저장';can_save=bool(rows) and x['status']!='confirmed' and (method=='excel' or not plan['residual'])
        if st.button(save_label,type='primary',disabled=not can_save):db.save_progress_allocations(c,x,plan['allocations']);refresh()
        st.caption('예상원가율은 ③ 정밀 배분에서만 필요합니다. 기본은 Excel 금액을 사용하고, 목표와 차이가 있을 때만 ②에서 진행 중 현장의 당기원가 비율로 차액을 나눕니다.')
    with tabs[1]:
        cards=st.columns(5)
        for col,label,value in zip(cards,['원장 공사수입','현장표 당기 공사수입','공사수입 검산차이','당기진행율 배분합계','목표 대비 차이'],[ledger_revenue,s['table_revenue'],ledger_revenue-s['table_revenue'],s['current_adjustment'],flow_adjustment-s['current_adjustment']]):col.metric(label,f'{value:,}원')
        vat_cards=st.columns(3)
        for col,label,value in zip(vat_cards,['전기진행율 합계','당기진행율 합계','VAT 신고 작업진행률 수입차액 · 조정 후'],[s['prior_adjustment'],s['current_adjustment'],s['vat_progress_difference']]):col.metric(label,f'{value:,}원')
        st.caption('VAT 신고 작업진행률 수입차액 조정 후 차액 = −(현장별 전기진행율 합계 + 현장별 최종 당기진행율 합계)')
        view=[]
        for r in rows:
            z=progress.allocation_analysis(r);view.append({'ID':r['id'],'검산':z['allocation_reason'],'발주처':z['client'],'공사명':z['project'],'계약공급가액':z['contract'],'전기수입':z['prior_revenue'],'당기수입':z['current_revenue'],'누계수입':z['total_revenue'],'전기원가':z['prior_cost'],'당기원가':z['current_cost'],'누계원가':z['total_cost'],'예상원가율(%)':round(z['expected_cost_rate']*100,4),'예상누적수입':z['expected_revenue'],'적정조정액':z['natural_adjustment'],'최종당기진행율':progress.final_adjustment(r),'상태':z['status']})
        show_frame(pd.DataFrame(view),hide_index=True,use_container_width=True,column_config={k:st.column_config.NumberColumn(format='%,d') for k in ['계약공급가액','전기수입','당기수입','누계수입','전기원가','당기원가','누계원가','예상누적수입','적정조정액','최종당기진행율']})
        if not rows:st.info('공사수입·원가대비표 Excel을 업로드하거나 현장을 직접 추가하세요.')
        elif s['missing_rates']:st.warning(f'이월공사 중 예상원가율이 없는 현장 {s["missing_rates"]:,}건을 확인하세요.')
        if rows and st.button('검산값을 흐름표 공사수입·당기진행율에 반영',type='primary',disabled=x['status']=='confirmed' or flow_adjustment!=s['current_adjustment']):
            payload={k:v for k,v in x.items() if k not in ['id','company_id','year','status','version']};values=dict(payload.get('values',{}));extra.setdefault('ledger_construction_revenue',flow_revenue);values['construction_revenue']=s['table_revenue'];values['progress_adjustment']=s['current_adjustment'];payload.update(values=values,progress=extra);save_payload(c,x,payload)
    with tabs[2]:
        st.html(PROGRESS_REVIEW_CSS)
        if rows:
            prepared=[]
            for r in rows:
                z=progress.allocation_analysis(r);target=progress.final_adjustment(r);after_current=z['current_revenue']+target;after_total=z['total_revenue']+target;after_rate=z['total_cost']/after_total*100 if after_total else 0
                excluded=progress.completed(z['status']) or z.get('allocation_mode')=='exclude';needs_review=(not z['expected_cost_rate'] and not excluded) or bool(z.get('import_missing'));decision='자동 제외' if excluded else '확인 필요' if needs_review else '적정'
                prepared.append({'row':r,'calc':z,'target':target,'after_current':after_current,'after_total':after_total,'after_rate':after_rate,'excluded':excluded,'needs_review':needs_review,'decision':decision})
            metrics_slot=st.empty()
            st.html('<div class="st-key-cc_progress_review_notice">당기수입은 Excel 당기수입에서 당기진행율을 차감한 조정 전 금액입니다. 핵심표에서 한 현장을 선택하면 아래에서 해당 현장만 안전하게 수정할 수 있습니다.</div>')
            review_filter=st.radio('검토 구분',['핵심 검토표','확인 필요','배분 제외'],horizontal=True,label_visibility='collapsed',key='cc_progress_review_filter')
            displayed=[p for p in prepared if review_filter=='핵심 검토표' or review_filter=='확인 필요' and p['needs_review'] or review_filter=='배분 제외' and p['excluded']]
            if not displayed:st.info('선택한 구분에 해당하는 현장이 없습니다.')
            else:
                compact=pd.DataFrame([{'현장명':p['row']['project'],'상태':p['row']['status'],'수입누계·조정전':p['calc']['total_revenue'],'원가누계':p['calc']['total_cost'],'원가율·조정전(%)':round(p['calc']['actual_cost_rate']*100,2),'Excel당기진행율':p['calc']['current_adjustment'],'목표공사진행율':p['target'],'원가율·조정후(%)':round(p['after_rate'],2),'판정':p['decision']} for p in displayed])
                event=st.dataframe(compact,hide_index=True,use_container_width=True,on_select='rerun',selection_mode='single-row',key='cc_progress_summary_table',column_config={k:st.column_config.NumberColumn(format='%,d') for k in ['수입누계·조정전','원가누계','Excel당기진행율','목표공사진행율']})
                selected_indices=list(event.selection.rows);selected_id=displayed[selected_indices[0]]['row']['id'] if selected_indices else st.session_state.get('cc_progress_selected_id',displayed[0]['row']['id'])
                selected=next((p for p in displayed if p['row']['id']==selected_id),displayed[0]);st.session_state['cc_progress_selected_id']=selected['row']['id']
                excel_total=sum(p['calc']['current_adjustment'] for p in prepared if not p['excluded']);difference=flow_adjustment-excel_total
                with metrics_slot.container(key='cc_progress_review_metrics'):
                    m1,m2,m3,m4=st.columns(4);m1.metric('목표 공사진행율 총액',f'{flow_adjustment:,}원');m2.metric('Excel 당기진행율 합계',f'{excel_total:,}원');m3.metric('추가·감액할 차액',f'{difference:,}원');m4.metric('선택 현장 조정 후 원가율',f'{selected["after_rate"]:,.2f}%')
                r=selected['row'];z=selected['calc'];disabled=x['status']=='confirmed'
                with st.container(key='cc_progress_detail'):
                    st.html(f'<div class="cc-progress-detail-head"><div><span>선택 현장 상세수정</span><strong>{escape(r["project"])}</strong></div><div class="cc-progress-chip">{escape(selected["decision"])}</div></div>')
                    with st.form(f'cc_progress_detail_form_{r["id"]}'):
                        income_col,cost_col,adjust_col,result_col=st.columns(4)
                        income_col.html('<div class="cc-progress-group-title">수입</div>');prior_revenue=money_field(income_col,'전기수입',z['prior_revenue'],key=f'progress_prior_revenue_{r["id"]}',disabled=disabled);current_revenue=money_field(income_col,'당기수입·조정 전',z['current_revenue'],key=f'progress_current_revenue_{r["id"]}',disabled=disabled);income_col.metric('수입누계·조정 전',f'{prior_revenue+current_revenue:,}원')
                        cost_col.html('<div class="cc-progress-group-title">원가</div>');prior_cost=money_field(cost_col,'전기원가',z['prior_cost'],key=f'progress_prior_cost_{r["id"]}',disabled=disabled);current_cost=money_field(cost_col,'당기원가',z['current_cost'],key=f'progress_current_cost_{r["id"]}',disabled=disabled);cost_col.metric('원가누계',f'{prior_cost+current_cost:,}원')
                        adjust_col.html('<div class="cc-progress-group-title">진행율 조정</div>');expected_rate=adjust_col.number_input('예상원가율(%)',min_value=0.0,max_value=999.0,value=float(z['expected_cost_rate']*100),step=.01,key=f'progress_expected_rate_{r["id"]}',disabled=disabled);money_field(adjust_col,'Excel 당기진행율',z['current_adjustment'],key=f'progress_excel_adjustment_{r["id"]}',disabled=True);target=money_field(adjust_col,'목표 공사진행율',selected['target'],key=f'progress_target_{r["id"]}',disabled=disabled);mode=adjust_col.selectbox('배분방식',['auto','fixed','exclude'],index=['auto','fixed','exclude'].index(z.get('allocation_mode','auto')),format_func=lambda q:{'auto':'자동배분','fixed':'금액 고정','exclude':'배분 제외'}[q],key=f'progress_mode_{r["id"]}',disabled=disabled)
                        total_revenue=prior_revenue+current_revenue;total_cost=prior_cost+current_cost;after_current=current_revenue+(0 if mode=='exclude' else target);after_total=total_revenue+(0 if mode=='exclude' else target);before_rate=total_cost/total_revenue*100 if total_revenue else 0;after_rate=total_cost/after_total*100 if after_total else 0
                        with result_col.container(key='cc_progress_detail_result'):
                            st.html('<div class="cc-progress-result-title">조정 결과</div>');st.metric('조정 전 누계원가율',f'{before_rate:,.2f}%');st.metric('당기수입·조정 후',f'{after_current:,}원');st.metric('수입누계·조정 후',f'{after_total:,}원');st.metric('누계원가율·조정 후',f'{after_rate:,.2f}%')
                        with st.expander('기본정보·이월·기타금액 수정'):
                            a,b,c1=st.columns(3);client=a.text_input('발주처',value=r['client'],key=f'progress_client_{r["id"]}',disabled=disabled);project=b.text_input('공사명',value=r['project'],key=f'progress_project_{r["id"]}',disabled=disabled);trade=c1.text_input('공종',value=r['trade'],key=f'progress_trade_{r["id"]}',disabled=disabled);d,e,f=st.columns(3);start=d.text_input('착공일',value=r['start'],key=f'progress_start_{r["id"]}',disabled=disabled);end=e.text_input('준공일',value=r['end'],key=f'progress_end_{r["id"]}',disabled=disabled);status=f.text_input('상태',value=r['status'],key=f'progress_status_{r["id"]}',disabled=disabled);g,h,i=st.columns(3);contract=money_field(g,'계약공급가액',r['contract'],key=f'progress_contract_{r["id"]}',disabled=disabled);prior_adjustment=money_field(h,'전기진행율',r['prior_adjustment'],key=f'progress_prior_adjustment_{r["id"]}',disabled=disabled);prior_unfinished=money_field(i,'전기미완성',r['prior_unfinished'],key=f'progress_prior_unfinished_{r["id"]}',disabled=disabled);j,k,l=st.columns(3);current_unfinished=money_field(j,'당기미완성',r['current_unfinished'],key=f'progress_current_unfinished_{r["id"]}',disabled=disabled);carry=k.checkbox('차기이월',value=bool(r.get('carryover_eligible',1)),key=f'progress_carry_{r["id"]}',disabled=disabled);carry_note=l.text_input('이월메모',value=r.get('carryover_note',''),key=f'progress_carry_note_{r["id"]}',disabled=disabled);note=st.text_area('비고',value=r['note'],key=f'progress_note_{r["id"]}',disabled=disabled)
                        action1,action2,action3=st.columns([1,1,3]);exclude_project=action1.form_submit_button('배분 제외',disabled=disabled,use_container_width=True);cancel=action2.form_submit_button('수정 취소',disabled=disabled,use_container_width=True);save=action3.form_submit_button('선택 현장 저장',type='primary',disabled=disabled,use_container_width=True)
                    if cancel:refresh()
                    if save or exclude_project:
                        final_mode='exclude' if exclude_project else mode;allocated=0 if final_mode=='exclude' else target;vals={'client':client,'project':project,'start':start,'end':end,'contract':contract,'prior_revenue':prior_revenue,'current_revenue':current_revenue,'prior_cost':prior_cost,'current_cost':current_cost,'expected_cost_rate':expected_rate/100,'trade':trade,'status':status,'prior_adjustment':prior_adjustment,'current_adjustment':z['current_adjustment'],'allocation_mode':final_mode,'allocated_adjustment':allocated,'carryover_eligible':0 if exclude_project else int(carry),'carryover_note':carry_note,'prior_unfinished':prior_unfinished,'current_unfinished':current_unfinished,'note':note};db.save_progress_project(c,x,r['id'],r['version'],vals);refresh()
                with st.expander('전체 원본 데이터 보기 · 읽기 전용'):
                    full=pd.DataFrame([{'공사관리번호':p['row'].get('project_key',''),'발주처':p['row']['client'],'공사명':p['row']['project'],'착공일':p['row']['start'],'준공일':p['row']['end'],'계약공급가액':p['row']['contract'],'전기수입':p['calc']['prior_revenue'],'당기수입·조정전':p['calc']['current_revenue'],'수입누계·조정전':p['calc']['total_revenue'],'전기원가':p['calc']['prior_cost'],'당기원가':p['calc']['current_cost'],'원가누계':p['calc']['total_cost'],'예상원가율(%)':p['calc']['expected_cost_rate']*100,'Excel당기진행율':p['calc']['current_adjustment'],'목표공사진행율':p['target'],'수입누계·조정후':p['after_total'],'원가율·조정후(%)':p['after_rate'],'상태':p['row']['status'],'판정':p['decision']} for p in prepared]);show_frame(full,hide_index=True,use_container_width=True)
                with st.expander('선택 현장 삭제'):
                    reason=st.text_input('삭제 사유',key=f'progress_delete_reason_{r["id"]}');ack=st.checkbox('삭제가 합계와 흐름표 검산에 미치는 영향을 확인했습니다.',key=f'progress_delete_ack_{r["id"]}')
                    if st.button('선택 현장 삭제',disabled=disabled or not ack,key=f'progress_delete_{r["id"]}'):db.delete_progress_project(c,x,r['id'],r['version'],reason);refresh()
        else:st.info('공사수입·원가대비표 Excel을 업로드하거나 현장을 직접 추가하세요.')
        with st.expander('현장 직접 추가'):
            with st.form('cc_progress_add_project'):
                a,b,c1=st.columns(3);client=a.text_input('발주처');project=b.text_input('공사명');start=c1.text_input('착공일');d,e,f=st.columns(3);end=d.text_input('준공일');contract=money_field(e,'계약공급가액',0);expected_rate=f.number_input('예상원가율(%)',min_value=0.0,max_value=100.0,value=0.0,step=.1);add=st.form_submit_button('현장 추가',disabled=x['status']=='confirmed')
            if add:
                if not project:st.error('공사명을 입력하세요.')
                else:db.add_progress_project(c,x,{'client':client,'project':project,'start':start,'end':end,'contract':contract,'expected_cost_rate':expected_rate/100,'status':'진행중','allocation_mode':'auto','carryover_eligible':1});refresh()
        with st.form('cc_progress_extra'):
            a,b=st.columns(2);a.metric('VAT 신고 작업진행률 수입차액 · 자동',f'{s["vat_progress_difference"]:,}원');extra['manual_adjustment']=money_field(b,'기타 수동 조정',extra.get('manual_adjustment'),key='progress_manual_adjustment',disabled=x['status']=='confirmed');extra['note']=st.text_input('조정 근거·메모',value=extra.get('note',''),disabled=x['status']=='confirmed');save_extra=st.form_submit_button('조정값 저장',disabled=x['status']=='confirmed')
            st.caption(f'−({s["prior_adjustment"]:,}원(전기진행율) + {s["current_adjustment"]:,}원(당기진행율)) = {s["vat_progress_difference"]:,}원(조정 후 차액)')
        if save_extra:payload={k:v for k,v in x.items() if k not in ['id','company_id','year','status','version']};extra.pop('vat_adjustment',None);payload['progress']=extra;save_payload(c,x,payload)
        deleted=[r for r in db.progress_projects(c,x['id'],True) if r['deleted']]
        if deleted:
            with st.expander('삭제 현장 복구'):
                pid=st.selectbox('복구할 현장',[r['id'] for r in deleted],format_func=lambda z:next(r['project'] for r in deleted if r['id']==z),key='cc_progress_restore_project')
                if st.button('선택 현장 복구',disabled=x['status']=='confirmed'):r=next(r for r in deleted if r['id']==pid);db.restore_progress_project(c,x,pid,r['version']);refresh()
    with tabs[3]:
        imports=db.progress_imports(c,x['id'],True);show_frame(pd.DataFrame(imports),hide_index=True,use_container_width=True);active=[r for r in imports if not r['deleted']];deleted=[r for r in imports if r['deleted']]
        if active:
            iid=st.selectbox('숨길 업로드 이력',[r['id'] for r in active],format_func=lambda z:next(r['name']+' · '+r['sheet_name'] for r in active if r['id']==z))
            if st.button('업로드 이력 숨김',disabled=x['status']=='confirmed'):db.delete_progress_import(c,x,iid);refresh()
        if deleted:
            iid=st.selectbox('복구할 업로드',[r['id'] for r in deleted],format_func=lambda z:next(r['name']+' · '+r['sheet_name'] for r in deleted if r['id']==z),key='cc_progress_restore_import')
            if st.button('업로드 자료 복구',disabled=x['status']=='confirmed'):db.restore_progress_import(c,x,iid);refresh()
        eligible=sum(1 for r in rows if r.get('carryover_eligible') and not progress.completed(r.get('status')));excluded=len(rows)-eligible;st.markdown('**차기 이월**');st.info(f'진행 중 이월 대상 {eligible:,}건 · 준공 또는 작업자 제외 {excluded:,}건')
        if st.button(f'{x["year"]+1}년 현장자료 생성',type='primary',disabled=x['status']!='confirmed'):
            next_case=db.case(c,x['company_id'],x['year']+1,create=True);result=db.carryover_progress_projects(c,x,next_case);st.success(f'{x["year"]+1}년으로 {result["carried"]:,}건을 이월하고 {result["excluded"]:,}건을 제외했습니다.')
        if x['status']!='confirmed':st.caption('당해 법인결산 확정 후 차기 이월자료를 생성할 수 있습니다.')
    with tabs[4]:
        html=progress_report.html(company['name'],x['year'],rows,flow_revenue,calculation_extra);xlsx=progress_report.workbook(company['name'],x['year'],rows,flow_revenue,calculation_extra)
        a,b=st.columns(2);a.download_button('A4 인쇄 HTML',html,file_name=f'{x["year"]}_{company["name"]}_공사수입원가대비.html',mime='text/html',use_container_width=True);b.download_button('검산·차기이월 Excel',xlsx,file_name=f'{x["year"]}_{company["name"]}_공사수입원가대비.xlsx',mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',use_container_width=True);components.html(html,height=800,scrolling=True)

def income_summary_page(c,x,company):
    adjustments,inc,tax,reserves=computed(c,x,company);st.caption('영업외수익은 잡이익 원장만 적요로 감면·기타 구분합니다. 영업외비용 전체 합계는 장부금액에서 손금불산입을 빼고 손금산입을 더하며, 감면분·기타분은 직접 입력합니다.')
    with st.form('cc_income_expense_manual'):
        st.markdown('**영업외비용 소득구분 직접 입력**');m1,m2,m3=st.columns(3)
        expense_exempt=money_field(m1,'감면분',inc['exempt_expense'],key='income_expense_exempt',disabled=x['status']=='confirmed');expense_other=money_field(m2,'기타분',inc['other_expense'],key='income_expense_other',disabled=x['status']=='confirmed');m3.metric('조정 후 전체 합계',f'{inc["totals"]["nonop_expense"]:,}원',delta=f'입력 차액 {inc["expense_check"]:,}원',delta_color='inverse' if inc['expense_check'] else 'off');save_expense=st.form_submit_button('영업외비용 구분 저장',type='primary',disabled=x['status']=='confirmed')
    if save_expense:
        payload={k:v for k,v in x.items() if k not in ['id','company_id','year','status','version']};payload['income_manual']={'nonop_expense_exempt':expense_exempt,'nonop_expense_other':expense_other};save_payload(c,x,payload)
    if inc['expense_check']:st.error(f'영업외비용 감면분과 기타분의 합계가 조정 후 전체 합계와 {abs(inc["expense_check"]):,}원 차이납니다.')
    metrics=[('매출액','revenue'),('매출원가','cost'),('판매관리비','sga'),('영업외수익','nonop_income'),('영업외비용','nonop_expense'),('각사업연도소득','current_income'),('이월결손금','loss'),('과세표준','taxable')]
    view=[]
    for label,key in metrics:
        total_key={'revenue':'sales'}.get(key,key);row={'구분':label,'전체 합계':money(inc['totals'].get(total_key,sum(money(r[key]) for r in inc['rows'])))}
        if key in ['current_income','loss','taxable']:row['전체 합계']=sum(money(r[key]) for r in inc['rows'])
        row.update({r['name']:money(r[key]) for r in inc['rows']});view.append(row)
    frame=pd.DataFrame(view);money_cols=[c for c in frame.columns if c!='구분']
    styled=frame.style.format({c:'{:,.0f}' for c in money_cols}).set_properties(subset=money_cols,**{'text-align':'right'}).set_properties(subset=['구분'],**{'text-align':'center'}).apply(lambda r:['background-color:#fff600;font-weight:700' if r['구분'] in ['각사업연도소득','과세표준'] else 'background-color:#eef6ff' if r['구분']=='이월결손금' else '' for _ in r],axis=1)
    show_frame(styled,hide_index=True,use_container_width=True)
    flow=calc.flow(x.get('values',{}),adjustments);groups=calc.adjustment_group_totals(adjustments);basis=[]
    for label,key,flow_key in [('매출액','sales','sales'),('매출원가','cost','cost'),('판매관리비','sga','sga'),('영업외수익','nonop_income','nonop_income'),('영업외비용','nonop_expense','nonop_expense')]:
        total=money(inc['totals'][key]);base=money(flow[flow_key]);detail=''
        if key=='nonop_income':detail=f'익금산입 +{groups["영업외수익"]["add"]:,} / 익금불산입 -{groups["영업외수익"]["deduct"]:,}'
        elif key=='nonop_expense':detail=f'손금불산입 -{groups["영업외비용"]["add"]:,} / 손금산입 +{groups["영업외비용"]["deduct"]:,}'
        basis.append({'항목':label,'흐름표 금액':f'{base:,}','세무조정 계산':detail or f'{total-base:+,}','세무조정 반영액':f'{total-base:,}','소득구분 전체 합계':f'{total:,}'})
    st.markdown('**전체 합계 계산 근거**');show_frame(pd.DataFrame(basis),hide_index=True,use_container_width=True)
    classified=[r for r in db.ledger_rows(c,x['id']) if r['kind']=='영업외수익' and '잡이익' in db.normalized(r['account'])]
    if classified:
        st.markdown('**잡이익 적요 판정 내역**');st.caption('등록한 감면분 검색 문구가 잡이익 적요에 포함되면 감면분, 그 밖의 잡이익은 기타분으로 표시합니다.')
        detail=pd.DataFrame([{'구분':r['kind'],'계정과목':r['account'],'적요':r['description'],'판정 근거':str(r.get('business','')).replace('자동:',''),'소득구분':r['classification'],'금액':f'{r["amount"]:,}'} for r in classified])
        show_frame(detail,hide_index=True,use_container_width=True)
        sums=[]
        for cls in ['감면분','기타분']:
            sums.append({'구분':'영업외수익·잡이익','소득구분':cls,'합계금액':f'{sum(r["amount"] for r in classified if r["classification"]==cls):,}'})
        show_frame(pd.DataFrame(sums),hide_index=True,use_container_width=True)
    else:st.info('원장 업로드·적요 분류 탭에서 잡이익 원장을 등록하면 적요 판정 내역이 여기에 표시됩니다.')
    if inc['check']:st.error(f'업종별 매출액 합계와 매출계가 {inc["check"]:,}원 차이납니다.')
    with st.form('cc_losses'):
        losses=dict(x.get('losses',{}));cols=st.columns(min(4,len(inc['rows'])))
        for i,r in enumerate(inc['rows']):losses[r['name']]=money_field(cols[i%len(cols)],r['name']+' 이월결손금',losses.get(r['name']),key='loss_'+str(i),disabled=x['status']=='confirmed')
        save=st.form_submit_button('이월결손금 저장',disabled=x['status']=='confirmed')
    if save:
        payload={k:v for k,v in x.items() if k not in ['id','company_id','year','status','version']};payload['losses']=losses;save_payload(c,x,payload)

def income_page(c,x,company):
    st.html('<div class="cc-title">소득구분계산서</div>')
    summary_tab,ledger_tab=st.tabs(['소득구분계산서','원장 업로드·적요 분류'])
    with summary_tab:income_summary_page(c,x,company)
    with ledger_tab:import_page(c,x,embedded=True)

def reserve_page(c,x):
    if x['status']!='confirmed' and db.sync_all_reserves(c,x):refresh()
    st.html('<div class="cc-title">유보잔액 관리대장</div>');rs=db.reserves(c,x['company_id']);deleted=[r for r in db.reserves(c,x['company_id'],True) if r['deleted']];summary=reserve_summary(c,x)
    show_frame(pd.DataFrame([{'ID':r['id'],'관리항목':r['name'],'발생연도':r['origin_year'],'최초유보액':r['initial_amount'],'기초유보액':r['beginning'],'당기증가액':r['increase'],'당기추인액':r['deduction'],'기말유보잔액':r['ending'],'반영':r['target']} for r in summary]),hide_index=True,use_container_width=True)
    selected=st.selectbox('등록·수정할 유보항목',['새 항목']+[r['id'] for r in rs],format_func=lambda z:'새 항목' if z=='새 항목' else next(r['name'] for r in rs if r['id']==z));r=next((r for r in rs if r['id']==selected),None)
    with st.form('cc_reserve'):
        a,b,c1=st.columns(3);name=a.text_input('관리항목',value=r['name'] if r else '');origin=b.number_input('발생연도',2000,2100,value=r['origin_year'] if r else x['year']);initial=money_field(c1,'최초 유보액',r['initial_amount'] if r else 0,key='reserve_initial',disabled=x['status']=='confirmed');target=st.selectbox('세무조정 반영 계정',db.RESERVE_TARGETS,index=db.RESERVE_TARGETS.index(r['target']) if r and r['target'] in db.RESERVE_TARGETS else 1);note=st.text_input('기간·추인계획·근거',value=r['note'] if r else '');save=st.form_submit_button('유보항목 저장',type='primary',disabled=x['status']=='confirmed')
    if save:db.save_reserve(c,x,name,origin,initial,target,note,r['id'] if r else None,r['version'] if r else None);refresh()
    if r:
        current=next((z for z in db.reserve_years(c,r['id']) if z['year']==x['year']),None)
        link=db.reserve_adjustment_status(c,x,r)
        if link['ambiguous']:st.error('같은 이름의 유보항목이 여러 개라 세무조정 자동 연결을 중지했습니다. 관리항목 이름을 구분해 주세요.')
        elif link['overage']:
            st.error(f'손금추인액이 사용 가능 잔액을 {link["overage"]:,}원 초과했습니다. 원본 금액은 변경하지 않았습니다.')
            st.info(f'사용 가능액 {link["available"]:,}원 / 입력된 손금추인액 {link["deduction"]:,}원입니다. 「세무조정 항목」에서 과목 「{r["name"]}」의 금액을 수정하거나 삭제한 뒤 다시 확인하세요.')
        elif link['count']:st.success(f'세무조정 {link["count"]:,}건 연계: 당기증가액 {link["increase"]:,}원 / 당기추인액 {link["deduction"]:,}원')
        with st.form('cc_reserve_year'):
            cols=st.columns(3);auto=bool(link['count']);increase=money_field(cols[0],'당기 유보 증가액',link['increase'] if auto else current['increase'] if current else 0,key='reserve_increase',disabled=x['status']=='confirmed' or auto);deduction=money_field(cols[1],'당기 손금추인액',link['deduction'] if auto else current['deduction'] if current else 0,key='reserve_deduction',disabled=x['status']=='confirmed' or auto);other=money_field(cols[2],'기타 조정액',current['other'] if current else 0,key='reserve_other',disabled=x['status']=='confirmed');saveyear=st.form_submit_button('당해연도 유보잔액 저장·세무조정 반영',disabled=x['status']=='confirmed' or link['ambiguous'] or bool(link['overage']))
        if saveyear:db.save_reserve_year(c,x,r['id'],x['year'],increase,deduction,other);refresh()
        show_frame(pd.DataFrame(db.reserve_years(c,r['id'])),hide_index=True,use_container_width=True)
        reason=st.text_input('유보항목 삭제 사유');ack=st.checkbox('이월·세무조정 영향을 확인했습니다.')
        if st.button('유보항목 삭제',disabled=x['status']=='confirmed' or not ack):db.delete_reserve(c,x,r['id'],r['version'],reason);refresh()
    if deleted:
        with st.expander('삭제자료 복구'):
            rid=st.selectbox('삭제 유보항목',[r['id'] for r in deleted],format_func=lambda z:next(r['name'] for r in deleted if r['id']==z));rr=next(r for r in deleted if r['id']==rid)
            if st.button('유보항목 복구'):db.restore_reserve(c,x,rid,rr['version']);refresh()

def tax_page(c,x,company):
    adjustments,inc,result,reserves=computed(c,x,company);st.html('<div class="cc-title">세액 계산</div>');st.caption('연파랑 칸은 작업자 입력, 노란색 칸은 자동 계산 결과입니다.')
    prior=db.prior_case(c,x['company_id'],x['year'])
    if prior and st.button(f'{x["year"]-1}년 차기 이월자료 불러오기',disabled=x['status']=='confirmed'):
        payload={k:v for k,v in x.items() if k not in ['id','company_id','year','status','version']};tax=dict(payload.get('tax',{}));pt=prior.get('tax',{})
        tax.update(donation_excess=pt.get('donation_carry_next',0),carry_loss=pt.get('carry_loss_next',0),rd_prior=pt.get('rd_carry_next',0));payload['tax']=tax;save_payload(c,x,payload)
    elif not prior:st.caption('전년도 결산자료가 없어 이월자료를 수동 입력합니다.')
    with st.container(key='cc_tax_direct'):
      with st.form('cc_tax'):
        tax=tax_input_values(x.get('tax',{}));disabled=x['status']=='confirmed';a,b,c1=st.columns([1,1.8,1.3])
        a.markdown('**과세표준 계산**')
        for key,label in TAX_FIELDS[:3]:tax[key]=money_field(a,label,tax.get(key),key='tax_'+key,disabled=disabled)
        a.html(f'<div class="cc-auto">각사업연도소득　{result["current_income"]:,}</div><div class="cc-auto">과세표준　{result["taxable"]:,}</div>')
        b.markdown('**공제·감면 및 가산세**');x1,x2= b.columns(2)
        tax['special_base']=money_field(x1,'중소기업 감면 대상금액',tax.get('special_base'),key='tax_special_base',disabled=disabled);tax['special_rate']=x2.number_input('중소기업 감면율(%)',value=float(tax.get('special_rate',15)),step=.1,disabled=disabled);tax['reduced_headcount']=x2.number_input('감소 인원(명)',min_value=0,value=int(tax.get('reduced_headcount',0) or 0),disabled=disabled)
        tax['rd_prior']=money_field(x1,'R&D 세액공제 전기이월',tax.get('rd_prior'),key='tax_rd_prior',disabled=disabled);tax['rd_current']=money_field(x2,'R&D 세액공제 당기',tax.get('rd_current'),key='tax_rd_current',disabled=disabled)
        tax['undocumented_base']=money_field(x1,'증빙미수취 대상금액',tax.get('undocumented_base'),key='tax_undocumented_base',disabled=disabled);tax['undocumented_rate']=x2.number_input('증빙미수취 가산세율(%)',value=float(tax.get('undocumented_rate',2)),step=.1,disabled=disabled)
        tax['land_gain']=money_field(x1,'토지 등 양도차익',tax.get('land_gain'),key='tax_land_gain',disabled=disabled);tax['land_rate']=x2.number_input('토지 등 양도소득 세율(%)',value=float(tax.get('land_rate',20)),step=.1,disabled=disabled)
        c1.markdown('**납부·환급 및 이월**');tax['prepaid_corp_interim']=money_field(c1,'법인세 중간예납',tax.get('prepaid_corp_interim'),key='tax_prepaid_interim',disabled=disabled);tax['prepaid_corp_withholding']=money_field(c1,'법인세 원천납부',tax.get('prepaid_corp_withholding'),key='tax_prepaid_withholding',disabled=disabled);tax['prepaid_local']=money_field(c1,'지방소득세 기납부',tax.get('prepaid_local'),key='tax_prepaid_local',disabled=disabled);tax['accrued_tax']=money_field(c1,'미지급법인세',tax.get('accrued_tax'),key='tax_accrued',disabled=disabled);tax['prepaid_corp']=tax['prepaid_corp_interim']+tax['prepaid_corp_withholding']
        for key,label in NEXT_FIELDS:tax[key]=money_field(c1,label,tax.get(key),key='tax_next_'+key,disabled=disabled)
        live=calc.tax_calculation(inc['current_income'],{**tax,'pre_tax':calc.flow(x.get('values',{}),adjustments)['pre_tax']});b.html(f'<div class="cc-auto">산출세액　{live["output_tax"]:,}</div><div class="cc-auto">공제·감면　{live["credits"]:,}</div><div class="cc-auto">법인세 총부담　{live["corp_total"]:,}</div>');c1.html(f'<div class="cc-auto">확정 법인세등　{live["confirmed_tax"]:,}</div>')
        save=st.form_submit_button('세액 계산 입력 저장',type='primary',disabled=disabled)
    if save:
        payload={k:v for k,v in x.items() if k not in ['id','company_id','year','status','version']};payload['tax']=tax;save_payload(c,x,payload)
    show_frame(pd.DataFrame([{'항목':k,'금액':v} for k,v in [('각사업연도소득',result['current_income']),('과세표준',result['taxable']),('산출세액',result['output_tax']),('중소기업 특별세액감면',result['special_reduction']),('공제·감면',result['credits']),('가산세',result['penalty']),('토지 등 양도소득 법인세',result['land_tax']),('법인세 총부담',result['corp_total']),('법인세 납부·환급',result['corp_payable']),('지방소득세 총부담',result['local_total']),('지방소득세 납부·환급',result['local_payable']),('확정 법인세등',result['confirmed_tax'])]]),hide_index=True,use_container_width=True)

def ratio_page(c,x,company):
    st.html('<div class="cc-title">경영상태비율 점검</div>')
    st.caption('전년도 협회 공식 공시율로 등급·평점을 판정하고, 최근 5개년 가중 추세와 이상치 보정으로 다음 연도 예상 업종비율을 계산합니다. 현금흐름비율은 영업활동현금흐름÷총자산으로 계산합니다.')
    if x['status']!='confirmed':st.info('현재 결산은 작성 중입니다. 예상 점검은 가능하지만 최종 결과는 법인결산 확정 후 다시 확인하세요.')
    check_tab,publication_tab=st.tabs(['경영상태비율 점검','협회 공시자료 등록'])
    category_default=(company.get('businesses') or ['건설업'])[0]
    with publication_tab:
        st.markdown('#### 협회 PDF 자동등록')
        st.caption('문자형 PDF는 항목과 수치를 자동 추출합니다. 스캔 PDF나 표 구조가 변경된 자료는 추출값을 직접 수정한 뒤 확정 등록하세요.')
        pdf=st.file_uploader('협회 공시 PDF',type=['pdf'],key='cc_ratio_pdf')
        preview={'year':x['year']-1,'ratios':{},'text':'','warning':''};pdf_content=b'';pdf_name='직접입력'
        if pdf:
            pdf_content=pdf.getvalue();pdf_name=pdf.name;digest=hashlib.sha256(pdf_content).hexdigest()
            cache_key='cc_ratio_pdf_cache'
            cached=st.session_state.get(cache_key)
            if not cached or cached.get('digest')!=digest:
                try:cached={'digest':digest,'preview':ratio.extract_pdf_ratios(pdf_content,pdf.name)}
                except ValueError as e:st.error(str(e));cached={'digest':digest,'preview':preview}
                st.session_state[cache_key]=cached
            preview=cached['preview']
            if preview.get('warning'):st.warning(preview['warning'])
            found=sum(v is not None for v in preview.get('ratios',{}).values());st.success(f'PDF에서 {found}/{len(ratio.RATIOS)}개 항목을 찾았습니다. 저장 전에 아래 값을 확인하세요.')
        with st.form('cc_ratio_publication_form'):
            head=st.columns([1.2,1.2,.7]);association=head[0].text_input('협회명',value='대한건설협회');category=head[1].text_input('업종 구분',value=category_default);pub_year=head[2].number_input('공시연도',1990,2100,value=int(preview.get('year') or x['year']-1))
            ratio_values={};cols=st.columns(3)
            for i,(key,spec) in enumerate(ratio.RATIOS.items()):
                raw=preview.get('ratios',{}).get(key);ratio_values[key]=cols[i%3].number_input(f'{spec["label"]} ({spec["unit"]})',value=float(raw or 0),format='%.4f',key=f'cc_pub_{hashlib.sha1((pdf_name+str(pub_year)+key).encode()).hexdigest()[:12]}')
            save_pub=st.form_submit_button('협회 공시자료 확정 등록',type='primary')
        if save_pub:
            try:db.save_industry_publication(c,association,category,pub_year,pdf_name,pdf_content,preview.get('text',''),ratio_values)
            except ValueError as e:st.error(str(e))
            else:st.success(f'{pub_year}년 {association} {category} 공시자료를 등록했습니다.');refresh()
        publications=db.industry_publications(c)
        if publications:
            st.markdown('#### 등록 이력')
            history=pd.DataFrame([{'ID':r['id'],'협회':r['association'],'업종':r['category'],'공시연도':r['publication_year'],'비율입력':f'{sum(v not in (None,0) for v in r["ratios"].values())}/{len(ratio.RATIOS)}','상태':'정상' if any(v not in (None,0) for v in r['ratios'].values()) else '수정 필요(전체 0)','원본파일':r['filename'],'등록일':r['created_at']} for r in publications])
            show_frame(history,hide_index=True,use_container_width=True)
            selected=st.selectbox('원본 확인·삭제할 공시자료',[r['id'] for r in reversed(publications)],format_func=lambda rid:next(f'{r["publication_year"]}년 · {r["association"]} · {r["category"]}' for r in publications if r['id']==rid),key='cc_pub_history')
            record=next(r for r in publications if r['id']==selected)
            with st.expander('선택 연도의 공시 비율 확인·수정',expanded=not any(v not in (None,0) for v in record['ratios'].values())):
                st.caption('0으로 잘못 저장된 연도는 아래 값을 수정해 다시 저장하세요. 수정하면 기존 PDF와 등록연도는 유지됩니다.')
                reparsed={}
                if record.get('content') and not any(v not in (None,0) for v in record['ratios'].values()):
                    try:reparsed=ratio.extract_pdf_ratios(record['content'],record['filename']).get('ratios',{})
                    except ValueError:reparsed={}
                    recovered=sum(v not in (None,0) for v in reparsed.values())
                    if recovered:st.info(f'보관된 원본 PDF에서 {recovered}개 비율을 다시 찾았습니다. 아래 값을 확인하고 수정 저장하세요.')
                with st.form(f'cc_pub_edit_{record["id"]}'):
                    edit_values={};edit_cols=st.columns(3)
                    for i,(key,spec) in enumerate(ratio.RATIOS.items()):
                        edit_values[key]=edit_cols[i%3].number_input(f'{spec["label"]} ({spec["unit"]})',value=float(record['ratios'].get(key) or reparsed.get(key) or 0),format='%.4f',key=f'cc_pub_edit_{record["id"]}_{key}')
                    edit_save=st.form_submit_button('선택 연도 비율 수정 저장',type='primary')
                if edit_save:
                    try:db.save_industry_publication(c,record['association'],record['category'],record['publication_year'],record['filename'],record['content'],record.get('extracted_text',''),edit_values)
                    except ValueError as e:st.error(str(e))
                    else:st.success(f'{record["publication_year"]}년 공시 비율을 수정했습니다.');refresh()
            actions=st.columns([1,1,4])
            actions[0].download_button('원본 PDF',record['content'],file_name=record['filename'] or f'{record["publication_year"]}_협회공시.pdf',mime='application/pdf',disabled=not bool(record['content']))
            confirm_delete=actions[1].checkbox('삭제 확인',key='cc_pub_delete_ack')
            if actions[2].button('선택 공시자료 삭제',disabled=not confirm_delete,key='cc_pub_delete'):db.delete_industry_publication(c,record['id'],record['version']);refresh()
    with check_tab:
        saved=db.management_ratio_input(c,x['id']);saved_values=dict(saved.get('payload') or {})
        has_saved=bool(saved.get('version'));edit_key=f'cc_ratio_edit_mode_{x["id"]}';active_case_key='cc_ratio_active_case'
        if st.session_state.get(active_case_key)!=x['id']:
            st.session_state[active_case_key]=x['id'];st.session_state[edit_key]=not has_saved
        elif edit_key not in st.session_state:st.session_state[edit_key]=not has_saved
        edit_mode=bool(st.session_state[edit_key])
        flow=calc.flow(x.get('values',{}),db.adjustments(c,x['id']));review=x.get('review',{});case_values=x.get('values',{})
        automatic={'sales':flow['sales'],'operating_profit':flow['operating_profit'],'pre_tax_income':flow['pre_tax'],'interest_expense':money(review.get('interest')),'construction_sales':money(case_values.get('construction_revenue')),'tech_development':money(review.get('tech_total') or review.get('rnd'))}
        if has_saved:
            edit_actions=st.columns([1,1,4])
            if not edit_mode and edit_actions[0].button('원천금액 수정',type='primary',key=f'cc_ratio_edit_start_{x["id"]}'):
                st.session_state[edit_key]=True;refresh()
            if edit_mode and edit_actions[1].button('수정 취소',key=f'cc_ratio_edit_cancel_{x["id"]}'):
                st.session_state[edit_key]=False;refresh()
        st.html('<div class="cc-input-edit">수정 중입니다. 회사와 결산연도를 다시 확인한 뒤 저장하세요.</div>' if edit_mode else '<div class="cc-input-lock">저장된 원천금액은 잠겨 있습니다. 변경하려면 「원천금액 수정」을 누르세요.</div>')
        uploaded=st.file_uploader('합계잔액시산표 또는 재무상태표·손익계산서',type=['xls','xlsx','csv'],key=f'cc_ratio_financial_{x["id"]}',disabled=not edit_mode)
        upload_content=b'';upload_name='';extracted={};evidence={}
        if uploaded:
            upload_content=uploaded.getvalue();upload_name=uploaded.name;digest=hashlib.sha256(upload_content).hexdigest();cache_key=f'cc_ratio_fin_cache_{x["id"]}';cache=st.session_state.get(cache_key)
            if not cache or cache.get('digest')!=digest:
                try:cache={'digest':digest,'result':ratio.extract_financial_statement(uploaded.name,upload_content)}
                except Exception as e:st.error('재무자료 자동인식 실패: '+str(e));cache={'digest':digest,'result':{'values':{},'evidence':{},'missing':list(ratio.FINANCIAL_FIELDS)}}
                st.session_state[cache_key]=cache
            extracted=cache['result'].get('values',{});evidence=cache['result'].get('evidence',{});found=sum(v is not None for v in extracted.values());st.success(f'재무자료에서 {found}/{len(ratio.FINANCIAL_FIELDS)}개 원천금액을 찾았습니다. 파란 입력값을 확인한 뒤 저장하세요.')
        initial={key:(extracted.get(key) if extracted.get(key) is not None else saved_values.get(key,automatic.get(key,0))) for key in ratio.FINANCIAL_FIELDS}
        st.html('<div class="cc-input-title">비율 계산 원천금액</div>')
        input_token=(hashlib.sha1(upload_content).hexdigest()[:8] if upload_content else 'saved');container_key=f'cc_ratio_{"editing" if edit_mode else "locked"}_{x["id"]}'
        with st.container(key=container_key):
          with st.form(f'cc_ratio_financial_form_{x["id"]}_{input_token}'):
            values={};cols=st.columns(3)
            for i,(key,(label,_)) in enumerate(ratio.FINANCIAL_FIELDS.items()):
                suffix=f' · {evidence[key]}' if key in evidence else (' · 결산흐름 자동연결' if key in automatic and not saved_values.get(key) else '')
                values[key]=money_field(cols[i%3],label+suffix,initial.get(key),key=f'cc_ratio_fin_{x["id"]}_{input_token}_{key}',disabled=not edit_mode)
            values['established_date']=st.text_input('설립일(YYYY-MM-DD)',value=str(saved_values.get('established_date','')),placeholder='예: 1994-01-15',key=f'cc_ratio_fin_{x["id"]}_{input_token}_established_date',disabled=not edit_mode)
            save_fin=st.form_submit_button('경영상태 원천금액 저장',type='primary',disabled=not edit_mode)
        if save_fin:
            st.session_state[edit_key]=False;db.save_management_ratio_input(c,x['id'],values,upload_name or saved.get('source_name',''),upload_content,saved.get('version',0));st.success('경영상태 원천금액을 저장하고 입력칸을 잠갔습니다.');refresh()
        actual=ratio.financial_ratios(values,x['year'])
        publications=db.industry_publications(c)
        associations=sorted({r['association'] for r in publications}) or ['대한건설협회'];association=st.selectbox('비교 협회',associations,key='cc_ratio_association')
        categories=sorted({r['category'] for r in publications if r['association']==association}) or [category_default];category=st.selectbox('비교 업종',categories,index=categories.index(category_default) if category_default in categories else 0,key='cc_ratio_category')
        selected_records=[r for r in publications if r['association']==association and r['category']==category and r['publication_year']<=x['year']-1]
        invalid_years=[r['publication_year'] for r in selected_records if not ratio.publication_has_values(r)]
        matching=[r for r in selected_records if ratio.publication_has_values(r)]
        prior=next((r for r in matching if r['publication_year']==x['year']-1),matching[-1] if matching else None)
        official_ratios,official_sources=ratio.latest_official_ratios(matching)
        if invalid_years:st.error('비율값이 모두 0이라 계산에서 제외된 공시연도: '+', '.join(f'{year}년' for year in invalid_years)+'. 「협회 공시자료 등록」 탭에서 해당 연도를 선택해 수정하세요.')
        st.caption('예상 계산에 사용되는 정상 공시연도: '+(', '.join(f'{r["publication_year"]}년' for r in matching[-5:]) if matching else '없음'))
        if prior and prior['publication_year']!=x['year']-1:st.warning(f'{x["year"]-1}년 공식자료가 없어 가장 최근 {prior["publication_year"]}년 자료를 전년도 기준으로 임시 사용합니다.')
        if not prior:st.warning('유효한 전년도 협회 공시자료가 없습니다. 「협회 공시자료 등록」 탭에서 연도별 비율값을 확인하세요.')
        missing_official=[ratio.RATIOS[key]['label'] for key,value in official_ratios.items() if value is None and key!='business_years']
        if missing_official:st.warning('공식 비율값이 없어 계산하지 못한 항목: '+', '.join(missing_official))
        forecasts={}
        for key in ratio.RATIOS:
            points=[(r['publication_year'],r['ratios'].get(key)) for r in matching if r['ratios'].get(key) not in (None,0)]
            forecasts[key]=ratio.trend_forecast(points)
        result_rows=ratio.evaluation_rows(actual,official_ratios,forecasts)
        display=[]
        for row in result_rows:
            key=row['key'];display.append({'점검 항목':row['점검 항목'],'당사비율':ratio.format_ratio(key,row['당사비율']),'전년도 기준':ratio.format_ratio(key,row['전년도 기준']),'예상 업종비율':ratio.format_ratio(key,row['예상 업종비율']),'예상 범위':f'{ratio.format_ratio(key,row["예상 하한"])} ~ {ratio.format_ratio(key,row["예상 상한"])}' if row['예상 하한'] is not None else '-','예상 신뢰도':row['신뢰도'],'평균대비율':f'{row["평균대비율"]:,.2f}%' if row['평균대비율'] is not None else '-','등급':row['등급'],'평점':f'{row["평점"]:,.1f}','판정':row['판정'],'계산식':row['계산식']})
        st.markdown('#### 경영상태비율 검산표')
        frame=pd.DataFrame(display)
        def ratio_row_style(row):
            return [('color:#087a4f;font-weight:800' if value in ['A','B','양호'] else 'color:#d98200;font-weight:800' if value in ['C','확인'] else 'color:#d92c25;font-weight:800' if value in ['D','E','보완'] else '') if column in ['등급','판정'] else '' for column,value in row.items()]
        styled=frame.style.set_properties(**{'text-align':'center'}).set_properties(subset=['당사비율','전년도 기준','예상 업종비율','평균대비율','평점'],**{'text-align':'right','color':'#126bb0','font-weight':'700'}).apply(ratio_row_style,axis=1)
        st.dataframe(styled,hide_index=True,use_container_width=True,height=390)
        total=sum(float(r['평점']) for r in result_rows);grades={g:sum(1 for r in result_rows if r['등급']==g) for g in 'ABCDE'};metrics=st.columns(3);metrics[0].metric('총 평점',f'{total:,.1f}점');metrics[1].metric('등급 분포',' · '.join(f'{g} {n}' for g,n in grades.items() if n));metrics[2].metric('전년도 공식기준',f'{prior["publication_year"]}년' if prior else '미등록')
        selected_key=st.selectbox('5개년 변동 확인',[k for k in ratio.RATIOS if k!='business_years'],format_func=lambda k:ratio.RATIOS[k]['label'],key='cc_ratio_chart')
        chart_rows=[]
        for record in matching[-5:]:
            value=record['ratios'].get(selected_key)
            if value not in (None,0):chart_rows.append({'연도':int(record['publication_year']),'구분':'협회 공시율','비율':float(value)})
        for record in db.management_ratio_history(c,company['id']):
            value=ratio.financial_ratios(record['payload'],record['year']).get(selected_key)
            if value is not None:chart_rows.append({'연도':int(record['year']),'구분':'당사비율','비율':float(value)})
        if actual.get(selected_key) is not None:chart_rows.append({'연도':int(x['year']),'구분':'당사비율','비율':float(actual[selected_key])})
        for year,value in ratio.trend_chart_points(forecasts[selected_key]):chart_rows.append({'연도':int(year),'구분':'추세 예상','비율':float(value)})
        if chart_rows:
            chart_data=pd.DataFrame(chart_rows).drop_duplicates(['연도','구분'],keep='last')
            domain=['당사비율','추세 예상','협회 공시율'];colors=['#126bb0','#6bb7e8','#ef2424']
            encoding={'x':{'field':'연도','type':'ordinal','sort':'ascending','axis':{'title':'연도','labelAngle':0}},'y':{'field':'비율','type':'quantitative','axis':{'title':ratio.RATIOS[selected_key]['unit']}},'color':{'field':'구분','type':'nominal','sort':domain,'scale':{'domain':domain,'range':colors},'legend':{'title':None,'orient':'bottom'}},'tooltip':[{'field':'연도','type':'ordinal','title':'연도'},{'field':'구분','type':'nominal','title':'구분'},{'field':'비율','type':'quantitative','title':'비율','format':',.2f'}]}
            st.vega_lite_chart(chart_data,{'height':320,'encoding':encoding,'layer':[{'mark':{'type':'line','strokeWidth':2}},{'mark':{'type':'point','filled':True,'size':75}}]},use_container_width=True)
        else:st.info('그래프에 표시할 공시율 또는 당사비율이 없습니다.')
        note=forecasts[selected_key];st.caption(f'예상 산식: 최근 최대 5개년 최근연도 가중 선형추세 · 이상치 {note.get("outliers",0)}건 보정 · 신뢰도 {note.get("confidence","자료없음")} · 결정계수 {note.get("r2",0):.2f}. 예상치는 참고용이며 공식 등급은 전년도 협회 공시값으로만 판정합니다.')
        official_year=prior['publication_year'] if prior else x['year']-1
        report_xlsx=ratio.management_report_workbook(company['name'],x['year'],values,actual,official_ratios,forecasts,matching,official_year)
        report_html=ratio.management_report_html(company['name'],x['year'],values,actual,official_ratios,forecasts,matching,official_year)
        downloads=st.columns(3)
        downloads[0].download_button('경영상태평가표 Excel',report_xlsx,file_name=f'{x["year"]}_{company["name"]}_경영상태평가표.xlsx',mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',use_container_width=True)
        downloads[1].download_button('PDF·인쇄 미리보기',report_html,file_name=f'{x["year"]}_{company["name"]}_경영상태평가표.html',mime='text/html',use_container_width=True)
        downloads[2].download_button('경영상태비율 CSV',frame.to_csv(index=False).encode('utf-8-sig'),file_name=f'{x["year"]}_{company["name"]}_경영상태비율.csv',mime='text/csv',use_container_width=True)

def capital_page(c,x,company):
    saved=db.real_capital_input(c,x['id']);payload=dict(saved.get('payload') or {});has_saved=bool(saved.get('version'))
    edit_key=f'cc_capital_edit_mode_{x["id"]}';active_key='cc_capital_active_case'
    if st.session_state.get(active_key)!=x['id']:
        st.session_state[active_key]=x['id'];st.session_state[edit_key]=not has_saved
    edit_mode=bool(st.session_state.get(edit_key,not has_saved))
    st.html(f'<div class="cc-capital-hero"><div class="eyebrow">CONSTRUCTION COMPANY · REAL CAPITAL REVIEW</div><div class="headline">{escape(company["name"])}　{x["year"]}년 실질자본금 적격여부 검토</div></div>')
    actions=st.columns([1,1,4])
    if has_saved and not edit_mode and actions[0].button('계산내역 수정',type='primary',key=f'cc_capital_edit_{x["id"]}'):
        st.session_state[edit_key]=True;refresh()
    if edit_mode and has_saved and actions[1].button('수정 취소',key=f'cc_capital_cancel_{x["id"]}'):
        st.session_state[edit_key]=False;refresh()
    if not edit_mode:st.html('<div class="cc-input-lock">저장된 시산표와 조정값은 잠겨 있습니다. 면허 기준자본금은 「법인·업종 설정」에서 회사별로 관리합니다.</div>')
    else:st.html('<div class="cc-input-edit">수정 중입니다. 차변·대변 원본은 그대로 두고 구분·분류·특수처리와 근거만 확인하세요.</div>')

    upload_cols=st.columns(2)
    uploaded=upload_cols[0].file_uploader('합계잔액시산표 · 계정별 조정용',type=['xls','xlsx','csv'],key=f'cc_capital_file_{x["id"]}',disabled=not edit_mode)
    statement_uploaded=upload_cols[1].file_uploader('재무상태표 · 회계상 총계 기준',type=['xls','xlsx','csv'],key=f'cc_capital_statement_{x["id"]}',disabled=not edit_mode)
    source_content=b'';source_name=saved.get('source_name','');extracted_rows=None;imported_adjustments={};reference_required_capital=None;token='saved'
    statement_totals=dict(payload.get('statement_totals') or {});statement_source_name=str(payload.get('statement_source_name') or '');statement_source_digest=str(payload.get('statement_source_digest') or '')
    if uploaded:
        source_content=uploaded.getvalue();source_name=uploaded.name;digest=hashlib.sha256(source_content).hexdigest();token=digest[:9]
        cache_key=f'cc_capital_extract_{x["id"]}';cached=st.session_state.get(cache_key)
        if not cached or cached.get('digest')!=digest:
            try:cached={'digest':digest,'result':capital.extract_trial_balance(uploaded.name,source_content)}
            except Exception as e:st.error('재무자료 자동인식 실패: '+str(e));cached={'digest':digest,'result':{'trial_rows':[],'adjustments':{},'reference_required_capital':None,'found':0,'unclassified':0}}
            st.session_state[cache_key]=cached
        extracted_rows=cached['result'].get('trial_rows',[]);imported_adjustments=cached['result'].get('adjustments',{});reference_required_capital=cached['result'].get('reference_required_capital')
        if extracted_rows:st.success(f'{uploaded.name}에서 잔액이 있는 계정 {len(extracted_rows)}개를 읽었습니다. 차변·대변 순잔액과 자산·부채 분류를 확인하세요.')
        else:st.warning('계정과목·차변잔액·대변잔액 열을 찾지 못했습니다. 아래 표에 개별 항목을 직접 추가할 수 있습니다.')
    elif source_name:st.caption(f'저장된 원본: {source_name}')
    if statement_uploaded:
        statement_content=statement_uploaded.getvalue();statement_source_name=statement_uploaded.name;statement_source_digest=hashlib.sha256(statement_content).hexdigest();statement_cache_key=f'cc_capital_statement_extract_{x["id"]}';statement_cached=st.session_state.get(statement_cache_key)
        if not statement_cached or statement_cached.get('digest')!=statement_source_digest:
            try:statement_cached={'digest':statement_source_digest,'result':capital.extract_balance_sheet_totals(statement_uploaded.name,statement_content)}
            except Exception as e:st.error('재무상태표 총계 인식 실패: '+str(e));statement_cached={'digest':statement_source_digest,'result':{'totals':{},'complete':False,'difference':None}}
            st.session_state[statement_cache_key]=statement_cached
        statement_result=statement_cached['result'];statement_totals=dict(statement_result.get('totals') or {})
        if statement_result.get('complete'):st.success(f'{statement_uploaded.name}에서 자산 {statement_totals["assets"]:,}원 · 부채 {statement_totals["liabilities"]:,}원 · 자본 {statement_totals["equity"]:,}원을 읽었습니다.')
        else:st.error('재무상태표에서 당기 자산총계·부채총계·자본총계를 모두 찾지 못했습니다.')
    elif statement_source_name:st.caption(f'저장된 재무상태표: {statement_source_name}')
    if not all(capital.number(statement_totals.get(key)) is not None for key in ['assets','liabilities','equity']):st.warning('회계상 총계 기준이 없습니다. 재무상태표를 함께 업로드해 주세요.')

    legacy=bool(payload.get('items')) and not payload.get('trial_rows')
    if legacy:st.error('이전 단순 계산방식으로 저장된 자료입니다. 정확한 자산·부채 순잔액 계산을 위해 합계잔액시산표를 다시 올려 주세요.')
    active_guidelines=[row for row in db.diagnostic_guidelines(c) if row['active']];active_rules=[]
    for guideline in active_guidelines:active_rules.extend(db.diagnostic_rules(c,guideline['id'],active_only=True))
    base_rows=capital.rows_before_capital(extracted_rows if extracted_rows is not None else payload.get('trial_rows',[]))
    work_key=f'cc_capital_trial_work_{x["id"]}';source_key=f'cc_capital_trial_source_{x["id"]}';epoch_key=f'cc_capital_trial_epoch_{x["id"]}';change_key=f'cc_capital_last_change_{x["id"]}'
    source_identity=f'two-line-ending-balance-v6:{token}:{saved.get("version",0)}:{len(base_rows)}'
    if not edit_mode and has_saved:
        st.session_state[work_key]=capital.auto_map_trial_rows(base_rows,active_rules,overwrite=False);st.session_state[source_key]=source_identity;st.session_state[epoch_key]=0;st.session_state.pop(change_key,None)
    elif st.session_state.get(source_key)!=source_identity or work_key not in st.session_state:
        st.session_state[work_key]=capital.auto_map_trial_rows(base_rows,active_rules,overwrite=extracted_rows is not None);st.session_state[source_key]=source_identity;st.session_state[epoch_key]=0;st.session_state.pop(change_key,None)
    initial_rows=st.session_state.get(work_key,[])
    for row in initial_rows:
        for column in capital.TRIAL_REVIEW_COLUMNS:row.setdefault(column,'' if column not in ['차변잔액','대변잔액','순금액'] else 0)
    st.html('<div class="cc-capital-section">① 합계잔액시산표 · 지침 자동분류</div>')
    if active_guidelines:
        statuses=' · '.join(f'{row["name"]} ({row["source_status"]})' for row in active_guidelines);st.caption('적용 지침: '+statuses)
    st.caption('계정 반영금액은 일반 자산의 차변잔액, 일반 부채의 대변잔액을 사용하고 자산 차감계정만 대변잔액을 음수로 반영합니다. 반대편 금액은 차감하지 않고 확인 대상으로 표시합니다.')
    trial_records=capital.auto_map_trial_rows(initial_rows,active_rules,overwrite=False);st.session_state[work_key]=trial_records
    if edit_mode:
        remap_col,save_hint_col=st.columns([1,4])
        if remap_col.button('자동 매핑 다시 실행',key=f'cc_capital_remap_{x["id"]}_{token}',use_container_width=True):
            st.session_state[work_key]=capital.auto_map_trial_rows(trial_records,active_rules,overwrite=True);st.session_state[epoch_key]=st.session_state.get(epoch_key,0)+1;st.session_state[change_key]={'message':'등록된 지침 기준으로 전체 자동매핑을 다시 반영했습니다.','account':''};trial_records=st.session_state[work_key]
        save_hint_col.info('표는 오른쪽 시안 형태로 표시합니다. 아래 `선택 계정 수정·추가`에서 계정을 고르면 해당 행의 자동값을 수정할 수 있습니다.')
    map_summary=capital.auto_mapping_summary(trial_records)
    st.html('<div class="cc-capital-map-cards">'+''.join([f'<div class="cc-capital-map-card{(" review" if key=="검토필요" else "")}"><span>{label}</span><strong>{map_summary[key]:,}</strong></div>' for key,label in [('전체','업로드 계정'),('자동처리','자동 초안'),('작업자확정','작업자 확정'),('검토필요','작업자 검토 필요'),('제외','합계·제목행 제외')]])+'</div>')
    last_change=st.session_state.get(change_key,{})
    if last_change:st.success(last_change.get('message','변경사항을 상단 검토표에 반영했습니다.'))
    show_frame(capital_review_frame(trial_records,last_change.get('account','') if last_change else ''),hide_index=True,use_container_width=True,height=min(720,max(220,38+len(trial_records)*38)))
    if edit_mode:
        with st.expander('선택 계정 수정·추가',expanded=True):
            options=[-1]+list(range(len(trial_records)));review_index=next((i for i,row in enumerate(trial_records) if '검토' in str(row.get('검토상태','')) or '확인' in str(row.get('검토상태',''))),0 if trial_records else -1);default_option=options.index(review_index) if review_index in options else 0
            selected=st.selectbox('수정할 계정',options,index=default_option,format_func=lambda index:'＋ 새 계정 직접 추가' if index==-1 else f'{trial_records[index].get("계정과목","")}　|　{trial_records[index].get("검토상태","")}',key=f'cc_capital_selected_row_{x["id"]}_{token}')
            current={} if selected==-1 else dict(trial_records[selected]);edit_token=f'{x["id"]}_{token}_{selected}_{capital.norm(current.get("계정과목","new"))}'
            line1=st.columns([1.4,1,1,1,1,1.2]);account=line1[0].text_input('계정과목',value=str(current.get('계정과목','') or ''),key='cc_capital_account_'+edit_token);debit=money_field(line1[1],'차변잔액',current.get('차변잔액',0),key='cc_capital_debit_'+edit_token);credit=money_field(line1[2],'대변잔액',current.get('대변잔액',0),key='cc_capital_credit_'+edit_token)
            current_group=str(current.get('구분','미분류') or '미분류');group=line1[3].selectbox('구분',capital.TRIAL_GROUPS,index=capital.TRIAL_GROUPS.index(current_group) if current_group in capital.TRIAL_GROUPS else capital.TRIAL_GROUPS.index('미분류'),key='cc_capital_group_'+edit_token)
            current_class=str(current.get('분류','') or '');classification=line1[4].selectbox('분류',capital.TRIAL_CLASSES,index=capital.TRIAL_CLASSES.index(current_class) if current_class in capital.TRIAL_CLASSES else len(capital.TRIAL_CLASSES)-1,key='cc_capital_class_'+edit_token)
            current_special=str(current.get('특수처리','') or '');special=line1[5].selectbox('특수처리',capital.SPECIAL_OPTIONS,index=capital.SPECIAL_OPTIONS.index(current_special) if current_special in capital.SPECIAL_OPTIONS else len(capital.SPECIAL_OPTIONS)-1,key='cc_capital_special_'+edit_token)
            if current.get('지침 매핑'):st.caption('자동매핑: '+str(current.get('지침 매핑'))+'　/　출처: '+str(current.get('출처','')))
            note=st.text_area('근거·비고',value=str(current.get('근거·비고','') or ''),height=75,key='cc_capital_note_'+edit_token)
            st.info('`작업자 판정 확정·저장`한 행은 다른 계정 수정이나 전체 자동 매핑을 실행해도 선택한 분류가 바뀌지 않습니다.')
            save_row,reset_row,delete_row,spacer=st.columns([1.4,1.2,1,3])
            if save_row.button('작업자 판정 확정·저장' if selected!=-1 else '새 계정 확정·추가',type='primary',use_container_width=True,key='cc_capital_row_save_'+edit_token):
                if not account.strip():st.error('계정과목을 입력하세요.')
                else:
                    candidate={**current,'계정과목':account.strip(),'차변잔액':debit,'대변잔액':credit,'구분':group,'분류':classification,'특수처리':special,'근거·비고':note,'출처':current.get('출처','직접입력') or '직접입력','수동확정':True};mapped=capital.auto_map_trial_rows([candidate],active_rules,overwrite=False)[0];updated=list(trial_records)
                    if selected==-1:updated.append(mapped)
                    else:updated[selected]=mapped
                    st.session_state[work_key]=updated;st.session_state[change_key]={'message':f'「{account.strip()}」을 작업자 판정으로 확정했습니다. 다른 계정을 수정해도 이 판정은 유지됩니다.','account':account.strip()};refresh()
            if selected!=-1 and reset_row.button('자동판정으로 되돌리기',use_container_width=True,key='cc_capital_row_reset_'+edit_token):
                candidate={**current,'수동확정':False};mapped=capital.auto_map_trial_rows([candidate],active_rules,overwrite=True)[0];updated=list(trial_records);updated[selected]=mapped;st.session_state[work_key]=updated;st.session_state[change_key]={'message':f'「{current.get("계정과목","")}」의 작업자 확정을 해제하고 자동판정을 다시 적용했습니다.','account':current.get('계정과목','')};refresh()
            if selected!=-1 and delete_row.button('선택 계정 삭제',use_container_width=True,key='cc_capital_row_delete_'+edit_token):
                removed=str(trial_records[selected].get('계정과목',''));updated=list(trial_records);updated.pop(selected);st.session_state[work_key]=updated;st.session_state[change_key]={'message':f'「{removed}」 계정을 삭제하고 상단 검토표와 자동계산을 갱신했습니다.','account':''};refresh()

    st.html('<div class="cc-capital-section">② 진단 조정값</div>')
    st.caption('노란 입력값만 직접 확인합니다. 업로드한 계산기 파일에 입력값이 있으면 함께 불러옵니다.')
    saved_adjustments=dict(payload.get('adjustments') or {});initial_adjustments={**saved_adjustments,**imported_adjustments}
    def optional_amount(scope,label,key):
        value=initial_adjustments.get(key);text_value='' if value in (None,'') else f'{money(value):,}'
        entered=scope.text_input(label,value=text_value,key=f'cc_capital_adj_{x["id"]}_{token}_{key}',disabled=not edit_mode,placeholder='미입력 시 조정 없음')
        return None if not str(entered).strip() else money(entered)
    adjustment_cols=st.columns(3)
    adjustment_values={
        'deposit_average':optional_amount(adjustment_cols[0],'예금 결산일 전후 30일 평균잔액','deposit_average'),
        'expired_receivables':optional_amount(adjustment_cols[1],'공사미수금 인정기간 초과분','expired_receivables'),
        'other_bad_assets':optional_amount(adjustment_cols[2],'기타 부실자산 조정','other_bad_assets'),
        'retirement_estimate':optional_amount(adjustment_cols[0],'퇴직급여추계액','retirement_estimate'),
        'other_offbook_liabilities':optional_amount(adjustment_cols[1],'기타 부외부채','other_offbook_liabilities'),
    }

    license_records=db.company_licenses_for_year(c,company['id'],x['year'])
    st.html('<div class="cc-capital-section">③ 회사별 면허 기준자본금</div>')
    st.caption('「법인·업종 설정」에서 현재 결산법인에 등록한 면허 기준자본금을 자동으로 불러옵니다. 기준이 변경되면 설정 화면에서 금액을 직접 수정하세요.')
    live=capital.calculate_trial_balance(trial_records,adjustment_values,license_records,x['year'],statement_totals)
    if live['licenses']:
        license_display=pd.DataFrame([{'면허명·업종':r['면허명·업종'],'요구자본금':r['요구자본금'],'중복·겸업 조정액':r['중복·겸업 조정액'],'최종 적용자본금':r['최종 적용자본금'],'근거·비고':r['근거·비고']} for r in live['licenses']])
        show_frame(license_display,hide_index=True,use_container_width=True)
    else:
        reference=f' 업로드 파일의 참고 기준자본금은 {reference_required_capital:,}원입니다.' if reference_required_capital is not None else ''
        st.warning('적용할 면허 기준자본금이 없습니다. 법인·업종 설정에서 회사별 면허를 먼저 등록하세요.'+reference)
        st.button('법인·업종 설정으로 이동',key=f'cc_capital_go_company_{x["id"]}',on_click=queue_session_value,args=('cc_page','법인·업종 설정'))
    if live['has_statement_totals']:
        if live['reconciliation_issue']:
            st.error(f'재무상태표와 시산표 계정합계가 일치하지 않습니다. 자산 차이 {live["asset_reconciliation"]:,}원 · 부채 차이 {live["liability_reconciliation"]:,}원 · 재무상태표 등식 차이 {live["statement_difference"]:,}원을 확인하세요.')
        else:st.success('재무상태표 총계와 합계잔액시산표의 자산·부채 계정합계가 원 단위까지 일치합니다.')
    guideline_checks=capital.guideline_matches(trial_records,active_rules,live);live['guideline_matches']=guideline_checks
    matched={row['계정과목'] for row in guideline_checks};unmatched=sorted({row.get('계정과목','') for row in capital.clean_trial_rows(trial_records) if row.get('순금액') and row.get('구분') in ['자산','부채'] and row.get('계정과목') not in matched})
    if unmatched:st.info('지침 별칭과 매칭되지 않은 계정: '+', '.join(unmatched)+'. 필요하면 기업진단지침 관리에서 계정별칭을 추가하세요.')
    if guideline_checks:st.warning('지침 자동분류는 검토 초안입니다. 계약·금융·등기·사업관련성 등 사실관계가 필요한 노란 항목은 증빙 확인 후 위 표에서 최종 확정하세요.')
    if live['unclassified']:st.error(f'잔액이 있는 미분류 계정 {live["unclassified"]}건이 있어 결과를 확정할 수 없습니다.')
    if live['review_count']:st.warning(f'인정 여부를 확인할 자산계정이 {live["review_count"]}건 있습니다. 분류와 근거를 검토하세요.')
    detail=pd.DataFrame([
        {'구분':'재무상태표 기준','항목':'회계상 자산총계','금액':live['accounting_assets']},{'구분':'시산표 검산','항목':'자산 계정합계','금액':live['trial_assets']},{'구분':'시산표 검산','항목':'자산 차이','금액':live['asset_reconciliation']},
        {'구분':'재무상태표 기준','항목':'회계상 부채총계','금액':live['accounting_liabilities']},{'구분':'시산표 검산','항목':'부채 계정합계','금액':live['trial_liabilities']},{'구분':'시산표 검산','항목':'부채 차이','금액':live['liability_reconciliation']},
        {'구분':'재무상태표 기준','항목':'회계상 자본총계','금액':live['accounting_equity']},{'구분':'재무상태표 검산','항목':'자산-부채-자본 차이','금액':live['statement_difference']},
        {'구분':'실질자산','항목':'계정분류상 부실자산','금액':live['classified_bad']},{'구분':'실질자산','항목':'현금 한도초과분','금액':live['cash_excess']},{'구분':'실질자산','항목':'예금 평균잔액 조정','금액':live['deposit_adjustment']},{'구분':'실질자산','항목':'공사미수금 인정기간 초과분','금액':live['expired_receivables']},{'구분':'실질자산','항목':'기타 부실자산 조정','금액':live['other_bad_assets']},{'구분':'실질자산','항목':'겸업자산','금액':live['concurrent_assets']},{'구분':'실질자산','항목':'검토대기 자산','금액':live['review_assets']},{'구분':'실질자산','항목':'실질자산','금액':live['real_assets']},
        {'구분':'실질부채','항목':'퇴직급여 부외부채','금액':live['retirement_offbook']},{'구분':'실질부채','항목':'기타 부외부채','금액':live['other_offbook_liabilities']},{'구분':'실질부채','항목':'겸업부채 차감','금액':live['concurrent_liabilities']},{'구분':'실질부채','항목':'실질부채','금액':live['real_liabilities']},
    ])
    st.html('<div class="cc-capital-section">④ 실질자산·실질부채 계산근거</div>');show_frame(detail,hide_index=True,use_container_width=True,height=390)
    status_class='cc-capital-ok' if live['status']=='충족' else 'cc-capital-bad' if live['status']=='미달' else 'cc-capital-pending'
    cards=''.join([f'<div class="cc-capital-card"><span>회계상 자본총계</span><strong>{live["accounting_equity"]:,}원</strong></div>',f'<div class="cc-capital-card"><span>자산 차감·검토대기</span><strong>{live["bad_total"]+live["concurrent_assets"]+live["review_assets"]:,}원</strong></div>',f'<div class="cc-capital-card result"><span>실질자본금</span><strong>{live["real_capital"]:,}원</strong></div>',f'<div class="cc-capital-card"><span>등록기준 자본금</span><strong>{live["required"]:,}원</strong></div>',f'<div class="cc-capital-card result"><span>여유액(부족액)</span><strong>{live["surplus"]:,}원</strong></div>'])
    st.html('<div class="cc-capital-section">⑤ 충족 여부 자동판정</div><div class="cc-capital-cards">'+cards+'</div>')
    st.info(f'자동계산 검산식: 실질자산 {live["real_assets"]:,}원 - 실질부채 {live["real_liabilities"]:,}원 = 실질자본금 {live["real_capital"]:,}원 / 법정 기준자본금 {live["required"]:,}원 / 여유·부족액 {live["surplus"]:,}원')
    st.html(f'<div class="cc-capital-status {status_class}">{live["status"]}　·　실질자본금/기준자본금 {(live["real_capital"]/live["required"]*100 if live["required"] else 0):,.2f}%</div>')
    if edit_mode:
        save=st.button('실질자본금 계산내역 저장',type='primary',use_container_width=True,key=f'cc_capital_save_{x["id"]}')
        if save:
            clean_rows=capital.clean_trial_rows(trial_records)
            if not clean_rows:st.error('합계잔액시산표 계정을 한 개 이상 입력하세요.')
            elif not live['has_statement_totals']:st.error('재무상태표를 업로드하여 회계상 자산·부채·자본총계를 확인하세요.')
            elif live['reconciliation_issue']:st.error('재무상태표와 시산표 계정합계 차이를 먼저 해결하세요.')
            elif live['unclassified']:st.error('미분류 계정을 모두 분류한 뒤 저장하세요.')
            elif not license_records:st.error('법인·업종 설정에서 회사별 면허 기준자본금을 먼저 등록하세요.')
            else:
                guideline_refs=[{'id':row['id'],'name':row['name'],'version':row['version'],'source_status':row['source_status']} for row in active_guidelines]
                db.save_real_capital_input(c,x['id'],{'trial_rows':clean_rows,'adjustments':adjustment_values,'license_snapshot':license_records,'guideline_refs':guideline_refs,'statement_totals':statement_totals,'statement_source_name':statement_source_name,'statement_source_digest':statement_source_digest},source_name,source_content,saved.get('version',0));st.session_state[edit_key]=False;st.success('재무상태표 총계, 시산표 계정잔액, 진단 조정값과 적용 지침 버전을 저장했습니다.');refresh()
    if has_saved and not edit_mode:
        history=[]
        for record in db.real_capital_history(c,company['id']):
            record_licenses=record['payload'].get('license_snapshot') or db.company_licenses_for_year(c,company['id'],record['year']);result=capital.calculate_trial_balance(record['payload'].get('trial_rows',[]),record['payload'].get('adjustments',{}),record_licenses,record['year'],record['payload'].get('statement_totals'));history.append({'결산연도':record['year'],'실질자본금':result['real_capital'],'필요자본금':result['required'],'여유액(부족액)':result['surplus'],'판정':result['status']})
        if history:
            st.html('<div class="cc-capital-section">연도별 실질자본금 이력</div>');show_frame(pd.DataFrame(history[-5:]),hide_index=True,use_container_width=True)
        downloads=st.columns(2)
        downloads[0].download_button('실질자본금 검토표 Excel',capital.trial_report_workbook(company['name'],x['year'],live),file_name=f'{x["year"]}_{company["name"]}_실질자본금검토표.xlsx',mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',use_container_width=True)
        downloads[1].download_button('PDF·인쇄 미리보기',capital.trial_report_html(company['name'],x['year'],live),file_name=f'{x["year"]}_{company["name"]}_실질자본금검토표.html',mime='text/html',use_container_width=True)

def guideline_page(c):
    st.html('<div class="cc-title">기업진단지침 관리</div>')
    st.caption('지침 원문을 버전별로 보관하고 조문을 계정 매칭규칙으로 관리합니다. 시행일과 고시번호가 확인되지 않은 자료는 출처상태를 항상 함께 표시합니다.')
    guidelines=db.diagnostic_guidelines(c)
    if not guidelines:st.error('등록된 기업진단지침이 없습니다.');return
    selected=st.selectbox('등록 지침',[row['id'] for row in guidelines],format_func=lambda z:next(row['name'] for row in guidelines if row['id']==z),key='cc_guideline_select');record=next(row for row in guidelines if row['id']==selected)
    if '미확인' in record['source_status']:st.warning('이 지침은 사용자가 제공한 원문으로 등록되었으며 공식 시행일·고시번호가 아직 확인되지 않았습니다. 규칙 적용 시 이 상태를 진단화면과 저장이력에 함께 남깁니다.')
    with st.form(f'cc_guideline_meta_{record["id"]}'):
        cols=st.columns([1.2,.8,.8]);source_status=cols[0].text_input('출처상태',value=record['source_status']);effective_from=cols[1].text_input('시행일',value=record['effective_from'],placeholder='YYYY-MM-DD 또는 미확인');notification_no=cols[2].text_input('고시·훈령번호',value=record['notification_no'],placeholder='미확인')
        source_note=st.text_area('출처·검토 메모',value=record['source_note'],height=80);active=st.checkbox('실질자본금 점검에 적용',value=record['active']);save_meta=st.form_submit_button('지침 기본정보 저장',type='primary')
    if save_meta:db.save_diagnostic_guideline(c,record['id'],source_status,effective_from,notification_no,source_note,active,record['version']);st.success('기업진단지침 기본정보를 저장했습니다.');refresh()
    with st.expander('등록된 지침 원문 보기'):
        st.text_area('원문',value=record['content'],height=420,disabled=True,label_visibility='collapsed')
    st.html('<div class="cc-input-title">조문별 계정 매칭규칙</div>')
    st.caption('계정별칭은 쉼표로 구분합니다. 자동유형은 계산방식을 결정하므로 기존 자동규칙은 신중하게 변경하세요. 사실관계가 필요한 규칙은 자동으로 확정하지 않고 권고판정만 표시합니다.')
    rule_rows=[]
    for row in db.diagnostic_rules(c,record['id']):
        rule_rows.append({'적용':row['active'],'우선순위':row['priority'],'조문':row['article'],'규칙명':row['title'],'계정별칭':', '.join(row['aliases']),'권고판정':row['recommendation'],'자동유형':row['auto_kind'],'확인조건':row['condition_text'],'필요증빙':row['evidence'],'규칙요약':row['summary'],'규칙코드':row['rule_code']})
    editor=st.data_editor(pd.DataFrame(rule_rows,columns=['적용','우선순위','조문','규칙명','계정별칭','권고판정','자동유형','확인조건','필요증빙','규칙요약','규칙코드']),num_rows='dynamic',hide_index=True,use_container_width=True,height=560,key=f'cc_guideline_rules_{record["id"]}',disabled=['규칙코드'],column_config={'적용':st.column_config.CheckboxColumn('적용',default=True),'우선순위':st.column_config.NumberColumn('우선순위',min_value=1,max_value=999,format='%d'),'조문':st.column_config.TextColumn('조문',width='small'),'규칙명':st.column_config.TextColumn('규칙명',required=True,width='medium'),'계정별칭':st.column_config.TextColumn('계정별칭',width='large'),'권고판정':st.column_config.TextColumn('권고판정',width='medium'),'자동유형':st.column_config.SelectboxColumn('자동유형',options=['cash','deposit','receivable','loan','tangible','intangible','liability','capital','allocation','review'],width='small'),'확인조건':st.column_config.TextColumn('확인조건',width='large'),'필요증빙':st.column_config.TextColumn('필요증빙',width='large'),'규칙요약':st.column_config.TextColumn('규칙요약',width='large'),'규칙코드':st.column_config.TextColumn('규칙코드',width='small')})
    if st.button('조문별 매칭규칙 저장',type='primary',use_container_width=True,key=f'cc_guideline_rule_save_{record["id"]}'):
        db.save_diagnostic_rules(c,record['id'],editor.to_dict('records'));st.success('조문별 계정 매칭규칙을 저장했습니다.');refresh()

def company_page(c,active_company_id=None):
    st.html('<div class="cc-title">법인·겸업 업종 설정</div>');allc=db.companies(c);r=next((row for row in allc if row['id']==active_company_id),None) if active_company_id is not None else None
    if r:st.info(f'현재 결산법인 「{r["name"]}」의 정보만 수정합니다. 다른 법인은 화면 상단의 결산법인을 먼저 변경하세요.')
    else:st.info('등록된 법인이 없습니다. 첫 결산법인을 등록하세요.')
    with st.form(f'cc_company_{r["id"] if r else "new"}'):
        name=st.text_input('법인명',value=r['name'] if r else '');business=st.text_input('업종명(쉼표로 구분)',value=', '.join(r.get('businesses',[])) if r else '건설업');save=st.form_submit_button('법인·업종 저장',type='primary')
    if save:db.save_company(c,name,business.split(','),r['id'] if r else None,r['version'] if r else None);refresh()
    if r:
        st.html('<div class="cc-input-title">회사별 면허 기준자본금</div>')
        st.caption('현재 적용할 면허별 요구자본금을 등록합니다. 기준금액이 변경되면 해당 금액을 바로 수정하고, 사용하지 않는 면허는 적용을 해제하거나 행을 삭제하세요.')
        license_rows=[{'면허명·업종':row['name'],'요구자본금':row['required_capital'],'중복·겸업 조정액':row['adjustment'],'적용':row['active'],'근거·비고':row['note']} for row in db.company_license_current_records(c,r['id'])]
        license_editor=st.data_editor(pd.DataFrame(license_rows,columns=['면허명·업종','요구자본금','중복·겸업 조정액','적용','근거·비고']),num_rows='dynamic',hide_index=True,use_container_width=True,key=f'cc_company_license_{r["id"]}',column_config={
            '면허명·업종':st.column_config.TextColumn('면허명·업종',required=True,width='large'),'요구자본금':st.column_config.NumberColumn('요구자본금',min_value=0,format='localized'),'중복·겸업 조정액':st.column_config.NumberColumn('중복·겸업 조정액',format='localized',help='감액은 음수, 가산은 양수'),'적용':st.column_config.CheckboxColumn('적용',default=True),'근거·비고':st.column_config.TextColumn('근거·비고',width='large')})
        if st.button('회사별 면허 기준자본금 저장',type='primary',key=f'cc_company_license_save_{r["id"]}'):
            db.save_company_license_records(c,r['id'],license_editor.to_dict('records'));st.success('회사별 면허 기준자본금을 저장했습니다.');refresh()
        reason=st.text_input('법인 삭제 사유');ack=st.checkbox('법인 삭제 영향을 확인했습니다.')
        if st.button('법인 삭제',disabled=not ack):db.delete_company(c,r['id'],r['version'],reason);refresh()
    deleted=[r for r in db.companies(c,True) if r['deleted']]
    if deleted:
        rid=st.selectbox('삭제 법인',[r['id'] for r in deleted],format_func=lambda z:next(r['name'] for r in deleted if r['id']==z))
        if st.button('법인 복구'):r=next(r for r in deleted if r['id']==rid);db.restore_company(c,rid,r['version']);refresh()

def output_page(c,x,company):
    adjustments,inc,tax,reserves=computed(c,x,company);html=report.html(company['name'],x['year'],x,adjustments,inc,tax,reserves);xlsx=report.workbook(company['name'],x['year'],x,adjustments,inc,tax,reserves)
    st.html('<div class="cc-title">결산 확정·출력</div>');st.download_button('법인결산 전체 인쇄 HTML',html,file_name=f'{x["year"]}_{company["name"]}_법인결산.html',mime='text/html');st.download_button('법인결산 전체 Excel',xlsx,file_name=f'{x["year"]}_{company["name"]}_법인결산.xlsx',mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    if x['status']=='confirmed':
        reason=st.text_input('확정 해제 사유');ack=st.checkbox('확정 해제 후 자료가 다시 수정 가능해짐을 확인했습니다.')
        if st.button('결산 확정 해제',disabled=not ack):db.reopen(c,x,reason);refresh()
    else:
        missing=readiness(c,x,company,inc);ready=not missing;ack=st.checkbox('소득구분 검산과 세액 계산 결과를 확인했습니다.')
        if st.button('법인결산 확정',type='primary',disabled=not ready or not ack):db.confirm(c,x);refresh()
        if not ready:st.error('확정 전 완료할 사항: '+', '.join(missing))

def render(user):
    st.html(CSS+CAPITAL_CSS+BRIGHT_THEME_CSS);c=db.connect();companies=db.companies(c)
    if not companies:st.warning('법인·업종 설정에서 법인을 먼저 등록하세요.');company_page(c);return
    with st.container(key='cc_case_banner'):
        top=st.columns([1.4,.7,.7]);cid=top[0].selectbox('결산법인',[r['id'] for r in companies],format_func=lambda z:next(r['name'] for r in companies if r['id']==z),key='cc_company');year=top[1].number_input('결산연도',2015,2100,value=date.today().year-1,key='cc_year');company=active_company(c,cid);x=db.case(c,cid,year)
        top[2].metric('상태','확정' if x['status']=='confirmed' else '작성 중')
    with st.sidebar:page=st.radio('법인결산 메뉴',PAGES,key='cc_page',format_func=lambda z:'　↳ '+z if z in ADJUSTMENT_SUBPAGES else z)
    if page=='대시보드':dashboard_page(c,x,company)
    elif page=='법인세 계산 흐름표':entry_page(c,x,company)
    elif page=='기초정보입력':basic_input_page(c,x,company)
    elif page=='공사수입·원가대비':progress_page(c,x,company)
    elif page=='세무조정 항목':adjustment_page(c,x)
    elif page in ADJUSTMENT_SUBPAGES:adjustment_statement_page(c,x,page)
    elif page=='소득구분계산서':income_page(c,x,company)
    elif page=='세액 계산':tax_page(c,x,company)
    elif page=='유보잔액 관리':reserve_page(c,x)
    elif page=='경영상태비율 점검':ratio_page(c,x,company)
    elif page=='실질자본금 점검':capital_page(c,x,company)
    elif page=='기업진단지침 관리':guideline_page(c)
    elif page=='법인·업종 설정':company_page(c,company['id'])
    elif page=='결산 확정·출력':output_page(c,x,company)
