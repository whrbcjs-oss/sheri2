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
def project_key(row):
    supplied=text(row.get('project_key'))
    if supplied:return supplied
    return '|'.join([normalized(row.get('client')),normalized(row.get('project')),normalized(row.get('start'))])
def completed(v):return '준공' in normalized(v) or normalized(v) in ['완료','정산완료']

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
    headers={normalized(s.cell(header,col).value):col for col in range(1,s.max_column+1)}
    if '공사관리번호' in headers:
        def value(row,*names):
            col=next((headers.get(normalized(name)) for name in names if headers.get(normalized(name))),None)
            return s.cell(row,col).value if col else None
        out=[]
        for row in range(header+1,s.max_row+1):
            client=text(value(row,'발주처'));project=text(value(row,'공사명'))
            if not client and not project:continue
            item=dict(source_row=row,project_key=text(value(row,'공사관리번호')),client=client,project=project,start=text(value(row,'착공일')),end=text(value(row,'준공일')),
                contract=num(value(row,'계약공급가액')),prior_revenue=num(value(row,'전기수입')),current_revenue=num(value(row,'당기수입')),
                prior_cost=num(value(row,'전기원가')),current_cost=num(value(row,'당기원가')),expected_cost_rate=rate(value(row,'예상원가율')),
                trade=text(value(row,'공종')),status=text(value(row,'상태')),prior_adjustment=num(value(row,'전기진행률조정','전기진행율')),
                current_adjustment=num(value(row,'가져온당기조정','당기진행율')),prior_unfinished=num(value(row,'전기미완성')),
                current_unfinished=num(value(row,'당기미완성')),note=text(value(row,'비고')),allocation_mode=text(value(row,'배분방식')) or 'auto',
                allocated_adjustment=(num(value(row,'최종당기진행율')) if value(row,'최종당기진행율') not in (None,'') else None),
                carryover_eligible=0 if text(value(row,'차기이월')).upper() in ['N','아니오','제외'] else 1)
            item['project_key']=project_key(item);out.append(recalculate(item))
        if not out:raise ValueError('현장별 공사수입·원가 행을 찾지 못했습니다.')
        return chosen,out
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
                prior_unfinished=j if label=='전기미완성' else 0,current_unfinished=j2 if label2=='당기미완성' else 0,note='',allocation_mode='auto',allocated_adjustment=None)
            item['project_key']=project_key(item);item['carryover_eligible']=int(not completed(status))
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
        if num(x.get('contract'))>0:x['expected_revenue']=min(x['expected_revenue'],num(x.get('contract')))
        x['calculated_adjustment']=trunc10(x['expected_revenue']-x['total_revenue'])
    else:
        x['expected_revenue']=x['total_revenue']+num(x.get('current_adjustment'));x['calculated_adjustment']=num(x.get('current_adjustment'))
    return x

def allocation_analysis(row):
    x=recalculate(row);natural=num(x.get('calculated_adjustment'));mode=text(x.get('allocation_mode')) or 'auto'
    reasons=[]
    if x.get('deleted'):reasons.append('삭제 현장')
    if x.get('import_missing'):reasons.append('최근 업로드 누락')
    if completed(x.get('status')):reasons.append('준공 현장')
    if mode=='exclude':reasons.append('작업자 배분 제외')
    eligible=not reasons and mode!='fixed'
    minimum=min(0,natural) if eligible else 0;maximum=max(0,natural) if eligible else 0
    fixed=num(x.get('allocated_adjustment')) if mode=='fixed' else 0
    cost_ready=eligible and abs(num(x.get('current_cost')))>0
    rate_ready=eligible and num(x.get('contract'))>0 and bool(rate(x.get('expected_cost_rate')))
    reason=' · '.join(reasons) if reasons else ('작업자 고정' if mode=='fixed' else '차액배분 가능' if cost_ready else '당기원가 없음')
    return {**x,'project_key':project_key(x),'allocation_mode':mode,'eligible':eligible,'cost_ready':cost_ready,'rate_ready':rate_ready,'allocation_reason':reason,'minimum_adjustment':minimum,'maximum_adjustment':maximum,'natural_adjustment':natural,'fixed_adjustment':fixed}

def _weighted_spread(amount,candidates):
    """Return positive integer shares using weights while respecting capacities."""
    remaining=max(0,num(amount));shares={row_id:0 for row_id,_,_ in candidates};active=list(candidates)
    while remaining and active:
        total_weight=sum(max(1,weight) for _,weight,_ in active);progressed=0
        for row_id,weight,capacity in active:
            room=capacity-shares[row_id]
            if room<=0:continue
            share=min(room,max(1,(remaining*max(1,weight))//total_weight));share=min(share,remaining-progressed)
            if share<=0:continue
            shares[row_id]+=share;progressed+=share
            if progressed>=remaining:break
        remaining-=progressed;active=[item for item in active if shares[item[0]]<item[2]]
        if not progressed:break
    return shares,remaining

def allocate(rows,target,method='excel'):
    """Use Excel adjustments first; optionally spread only the difference."""
    if method not in ['excel','cost','rate']:raise ValueError('배분 기준을 확인하세요.')
    analyzed=[allocation_analysis(r) for r in rows if not r.get('deleted')];target=num(target);allocations={}
    for r in analyzed:
        if r.get('id') is None:continue
        if r['allocation_mode']=='fixed':allocations[r['id']]=r['fixed_adjustment']
        elif not r['eligible']:allocations[r['id']]=0
        else:allocations[r['id']]=num(r.get('current_adjustment')) if method in ['excel','cost'] else 0
    excel_total=sum(allocations.values());difference=target-excel_total;available=0
    if method=='cost' and difference:
        sign=1 if difference>0 else -1;candidates=[]
        for r in analyzed:
            if not r.get('id') or not r['cost_ready'] or r['allocation_mode']!='auto':continue
            base=allocations[r['id']]
            capacity=max(0,num(r.get('contract'))-num(r.get('total_revenue'))-base) if sign>0 and num(r.get('contract')) else max(0,num(r.get('current_revenue'))+base) if sign<0 else 0
            if capacity:candidates.append((r['id'],abs(num(r.get('current_cost'))),capacity));available+=capacity
        shares,_=_weighted_spread(abs(difference),candidates)
        for row_id,share in shares.items():allocations[row_id]+=sign*share
    elif method=='rate':
        allocations={r['id']:r['fixed_adjustment'] if r['allocation_mode']=='fixed' else 0 for r in analyzed if r.get('id') is not None};fixed=sum(allocations.values());difference=target-fixed;sign=1 if difference>=0 else -1;candidates=[]
        for r in analyzed:
            capacity=r['maximum_adjustment'] if sign>0 else abs(r['minimum_adjustment'])
            if r.get('id') and r['rate_ready'] and r['allocation_mode']=='auto' and capacity:candidates.append((r['id'],capacity,capacity));available+=capacity
        shares,_=_weighted_spread(abs(difference),candidates)
        for row_id,share in shares.items():allocations[row_id]+=sign*share
    allocated=sum(allocations.values());residual=target-allocated
    result=[]
    for r in analyzed:
        proposed=allocations.get(r.get('id'),r['fixed_adjustment'] if r['allocation_mode']=='fixed' else 0)
        result.append({**r,'proposed_adjustment':proposed})
    return {'method':method,'target':target,'excel_total':excel_total,'difference':target-excel_total,'fixed':sum(r['fixed_adjustment'] for r in analyzed),'available':available,'allocated':allocated,'residual':residual,'rows':result,'allocations':allocations}

def final_adjustment(row):
    value=row.get('allocated_adjustment')
    return num(value) if value is not None else num(recalculate(row).get('calculated_adjustment'))

def summary(rows,extra=None):
    active=[recalculate(r) for r in rows if not r.get('deleted')];extra=extra or {}
    table_revenue=sum(num(r.get('current_revenue')) for r in active);prior=sum(num(r.get('prior_adjustment')) for r in active);current=sum(final_adjustment(r) for r in active)
    prior_unfinished=sum(num(r.get('prior_unfinished')) for r in active);current_unfinished=sum(num(r.get('current_unfinished')) for r in active)
    vat_revenue=num(extra.get('ledger_construction_revenue'));adjusted_progress_revenue=table_revenue+current
    vat_progress_difference=adjusted_progress_revenue-vat_revenue
    manual=num(extra.get('manual_adjustment'))
    tax_flow=-prior+current+prior_unfinished-current_unfinished+manual
    return dict(table_revenue=table_revenue,prior_adjustment=prior,current_adjustment=current,prior_unfinished=prior_unfinished,current_unfinished=current_unfinished,vat_revenue=vat_revenue,adjusted_progress_revenue=adjusted_progress_revenue,vat_progress_difference=vat_progress_difference,manual_adjustment=manual,expected_adjustment=current,tax_flow_adjustment=tax_flow,missing_rates=sum(1 for r in active if not rate(r.get('expected_cost_rate')) and not completed(r.get('status'))))
