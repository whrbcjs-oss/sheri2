"""Construction revenue/cost workbook import and progress-revenue calculations."""
from io import BytesIO
from decimal import Decimal, ROUND_DOWN
import re
import openpyxl

def text(v):return re.sub(r'\s+',' ',str(v or '')).strip()
def num(v):
    if isinstance(v,(int,float)) and not isinstance(v,bool):return int(round(v))
    try:return int(Decimal(str(v or 0).replace(',','')))
    except Exception:return 0
def rate(v):
    try:
        x=Decimal(str(v or 0).replace('%','').replace(',',''))
        return float(x/100 if x>2 else x)
    except Exception:return 0.0
def trunc10(v):return int((Decimal(str(v))/Decimal('10')).quantize(Decimal('1'),rounding=ROUND_DOWN)*Decimal('10'))
def normalized(v):return re.sub(r'[^0-9A-Za-z가-힣]','',text(v)).replace('주식회사','').replace('㈜','')

ALIASES={'효성':['효성'],'다혜건설':['다혜','다혜건설'],'효성전문':['전문','효성전문'],'한길':['한길'],'효성엘비데크':['엘비','엘비데크','효성엘비데크']}
def company_tokens(company):
    wanted=normalized(company);key=next((k for k in ALIASES if normalized(k)==wanted),None)
    if not key:key=next((k for k,v in ALIASES.items() if any(normalized(a)==wanted for a in v)),None)
    if not key:key=next((k for k in sorted(ALIASES,key=lambda z:len(normalized(z)),reverse=True) if normalized(k) in wanted),None)
    return ALIASES.get(key,[company])
def sheet_candidates(blob,year,company):
    book=openpyxl.load_workbook(BytesIO(blob),data_only=True,read_only=False);tokens=company_tokens(company)
    names=[s for s in book.sheetnames if str(year) in s]
    matched=[s for s in names if any(normalized(t) in normalized(s) for t in tokens)]
    return matched or names

def parse(blob,year,company,sheet_name=None):
    values=openpyxl.load_workbook(BytesIO(blob),data_only=True,read_only=False)
    if sheet_name:chosen=sheet_name
    else:
        tokens=company_tokens(company);names=[name for name in values.sheetnames if str(year) in name and any(normalized(t) in normalized(name) for t in tokens)];chosen=names[0] if names else ''
    if chosen not in values.sheetnames:raise ValueError('선택한 결산연도·법인 시트를 찾을 수 없습니다.')
    s=values[chosen];header=next((r for r in range(1,min(s.max_row,30)+1) if '발주처' in normalized(s.cell(r,1).value) and '공사명' in normalized(s.cell(r,2).value)),None)
    if not header:raise ValueError('발주처·공사명 머리글을 찾지 못했습니다.')
    # Later helper rows repeat a project with a decimal expected cost rate in column I.
    expected={}
    for r in range(header+4,s.max_row+1):
        project=text(s.cell(r,2).value);rv=rate(s.cell(r,9).value)
        if project and 0<rv<2:
            expected[normalized(project)]={'rate':rv,'contract':num(s.cell(r,4).value),'prior_revenue':num(s.cell(r,5).value),'current_revenue':num(s.cell(r,6).value),'prior_cost':num(s.cell(r+1,5).value),'current_cost':num(s.cell(r+1,6).value)}
    out=[]
    r=header+4
    while r<=s.max_row:
        client=text(s.cell(r,1).value);project=text(s.cell(r,2).value)
        if '합계' in normalized(client):break
        contract=num(s.cell(r,4).value)
        if (client or project) and contract and r+1<=s.max_row:
            label=text(s.cell(r,9).value);label2=text(s.cell(r+1,9).value)
            j=num(s.cell(r,10).value);j2=num(s.cell(r+1,10).value)
            status=text(s.cell(r+1,8).value);actual_rate=(num(s.cell(r+1,7).value)/num(s.cell(r,7).value)) if num(s.cell(r,7).value) else 0
            helper=expected.get(normalized(project),{});exp=helper.get('rate',0)
            item=dict(source_row=r,client=client,project=project,start=text(s.cell(r,3).value),end=text(s.cell(r+1,3).value),contract=helper.get('contract') or contract,
                prior_revenue=helper.get('prior_revenue',num(s.cell(r,5).value)),current_revenue=helper.get('current_revenue',num(s.cell(r,6).value)),total_revenue=num(s.cell(r,7).value),
                prior_cost=helper.get('prior_cost',num(s.cell(r+1,5).value)),current_cost=helper.get('current_cost',num(s.cell(r+1,6).value)),total_cost=num(s.cell(r+1,7).value),
                actual_cost_rate=actual_rate,expected_cost_rate=exp,trade=text(s.cell(r,11).value or s.cell(r+1,11).value),status=status,
                prior_adjustment=j if label=='전기진행율' else 0,current_adjustment=(j if label=='당기진행율' else j2 if label2=='당기진행율' else 0),
                prior_unfinished=j if label=='전기미완성' else 0,current_unfinished=j2 if label2=='당기미완성' else 0,note='')
            out.append(recalculate(item));r+=2;continue
        r+=1
    if not out:raise ValueError('현장별 공사수입·원가 행을 찾지 못했습니다.')
    return chosen,out

def recalculate(row):
    x=dict(row);x['total_revenue']=num(x.get('prior_revenue'))+num(x.get('current_revenue'));x['total_cost']=num(x.get('prior_cost'))+num(x.get('current_cost'))
    x['actual_cost_rate']=x['total_cost']/x['total_revenue'] if x['total_revenue'] else 0
    er=rate(x.get('expected_cost_rate'))
    if er:
        x['expected_revenue']=int(Decimal(x['total_cost'])/Decimal(str(er)))
        x['calculated_adjustment']=trunc10(x['expected_revenue']-x['total_revenue'])
    else:
        x['expected_revenue']=x['total_revenue']+num(x.get('current_adjustment'));x['calculated_adjustment']=num(x.get('current_adjustment'))
    return x

def summary(rows,extra=None):
    active=[recalculate(r) for r in rows if not r.get('deleted')];extra=extra or {}
    table_revenue=sum(num(r.get('current_revenue')) for r in active);prior=sum(num(r.get('prior_adjustment')) for r in active);current=sum(num(r.get('calculated_adjustment')) for r in active)
    prior_unfinished=sum(num(r.get('prior_unfinished')) for r in active);current_unfinished=sum(num(r.get('current_unfinished')) for r in active)
    vat=num(extra.get('vat_adjustment'));manual=num(extra.get('manual_adjustment'))
    expected=-prior+current+prior_unfinished-current_unfinished+vat+manual
    return dict(table_revenue=table_revenue,prior_adjustment=prior,current_adjustment=current,prior_unfinished=prior_unfinished,current_unfinished=current_unfinished,vat_adjustment=vat,manual_adjustment=manual,expected_adjustment=expected,missing_rates=sum(1 for r in active if not rate(r.get('expected_cost_rate')) and '준공' not in normalized(r.get('status'))))
