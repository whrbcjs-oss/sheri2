"""Deterministic corporate-close calculations; no persistence or UI state."""
from decimal import Decimal, ROUND_HALF_UP

ZERO=Decimal('0')
ACCOUNT_GROUPS=['원가','자산','영업외비용','영업외수익','법인세']
def dec(v):
    if v in (None,''):return ZERO
    return Decimal(str(v).replace(',',''))
def won(v):return int(dec(v).quantize(Decimal('1'),rounding=ROUND_HALF_UP))
def tax_won(v):return int(dec(v))
def nonnegative(v,label='금액'):
    x=dec(v)
    if x<0:raise ValueError(label+'은 0 이상이어야 합니다.')
    return x

def adjustment_totals(rows):
    out={'add_amount':ZERO,'add_cost':ZERO,'add_sga':ZERO,'deduct_amount':ZERO,'deduct_cost':ZERO,'deduct_sga':ZERO}
    for r in rows:
        if r.get('deleted'):continue
        side=r['side'];amount=dec(r.get('amount'));target=r.get('target','판관비')
        out[side+'_amount']+=amount
        if (r.get('account_group') or '원가')!='원가':continue
        if target=='원가':out[side+'_cost']+=amount
        elif target=='판관비':out[side+'_sga']+=amount
        else:
            cost=dec(r.get('cost_amount'))
            if cost<0 or cost>amount:raise ValueError(r['name']+' 원가 배분액을 확인하세요.')
            out[side+'_cost']+=cost;out[side+'_sga']+=amount-cost
    return {k:won(v) for k,v in out.items()}

def adjustment_group_totals(rows):
    out={g:{'add':ZERO,'deduct':ZERO} for g in ACCOUNT_GROUPS}
    for r in rows:
        if r.get('deleted'):continue
        group=r.get('account_group') or '원가'
        if group not in out:group='원가'
        out[group][r['side']]+=dec(r.get('amount'))
    return {g:{k:won(v) for k,v in sides.items()} for g,sides in out.items()}

def research_totals(review):
    r=dict(review or {});detail=bool(r.get('rnd_detail_enabled')) or any(k in r for k in ('rnd_labor','rnd_material','rnd_other','rnd_outsourced','training_sga','training_cost','rnd_employee_count'))
    if not detail:
        current=won(r.get('rnd',0));personnel=max(0,won(r.get('tech_total',0))-current)
        return {'detail_enabled':False,'employee_count':0,'labor':0,'material':0,'other':0,'outsourced':0,'current_total':current,'training_sga':0,'training_cost':personnel,'personnel_total':personnel,'tech_total':won(r.get('tech_total',current))}
    labor=won(r.get('rnd_labor',0));material=won(r.get('rnd_material',0));other=won(r.get('rnd_other',0));outsourced=won(r.get('rnd_outsourced',0));training_sga=won(r.get('training_sga',0));training_cost=won(r.get('training_cost',0));current=labor+material+other+outsourced;personnel=training_sga+training_cost
    return {'detail_enabled':True,'employee_count':max(0,int(r.get('rnd_employee_count',0) or 0)),'labor':labor,'material':material,'other':other,'outsourced':outsourced,'current_total':current,'training_sga':training_sga,'training_cost':training_cost,'personnel_total':personnel,'tech_total':current+personnel}

def flow(values,adjustments=()):
    v={k:won(values.get(k,0)) for k in ['construction_revenue','service_revenue','progress_adjustment','cost','sga','nonop_income','nonop_expense','prior_sales','prior_progress','prior_unfinished','current_unfinished']}
    a=adjustment_totals(adjustments)
    v['sales']=v['construction_revenue']+v['service_revenue']+v['progress_adjustment']
    v['gross_profit']=v['sales']-v['cost']
    v['operating_profit']=v['gross_profit']-v['sga']
    v['pre_tax']=v['operating_profit']+v['nonop_income']-v['nonop_expense']
    v['sales_growth']=float(dec(v['sales']-v['prior_sales'])/dec(v['prior_sales'])*100) if v['prior_sales'] else 0
    v['pre_tax_rate']=float(dec(v['pre_tax'])/dec(v['sales'])*100) if v['sales'] else 0
    v['cost_rate']=float(dec(v['cost'])/dec(v['construction_revenue'])*100) if v['construction_revenue'] else 0
    v.update(a);return v

def adjusted_income_totals(values,adjustments):
    f=flow(values,adjustments);g=adjustment_group_totals(adjustments)
    # The income-division statement only adjusts cost/SG&A with rows classified
    # as operating-cost accounts. Asset, non-operating and corporate-tax rows
    # remain outside those two totals even if their deduction target was used
    # for the tax-adjustment schedule.
    operating=[r for r in adjustments if not r.get('deleted') and (r.get('account_group') or '원가')=='원가'];a=adjustment_totals(operating)
    return {'sales':f['sales'],'cost':f['cost']-a['add_cost']+a['deduct_cost'],'sga':f['sga']-a['add_sga']+a['deduct_sga'],'nonop_income':f['nonop_income']+g['영업외수익']['add']-g['영업외수익']['deduct'],'nonop_expense':f['nonop_expense']-g['영업외비용']['add']+g['영업외비용']['deduct']}

def income_division(values,adjustments,businesses,exempt_income=0,exempt_expense=None,other_expense=None,losses=None):
    totals=adjusted_income_totals(values,adjustments);bs=[]
    supplied=sum((dec(b.get('revenue')) for b in businesses),ZERO)
    if not businesses:businesses=[{'name':'감면분','revenue':totals['sales']}];supplied=dec(totals['sales'])
    if supplied==0 and totals['sales']:businesses=[dict(businesses[0],revenue=totals['sales'])]+[dict(b,revenue=0) for b in businesses[1:]];supplied=dec(totals['sales'])
    ei=min(nonnegative(exempt_income,'영업외수익 감면분'),nonnegative(totals['nonop_income'],'영업외수익'));other_income=dec(totals['nonop_income'])-ei
    expense_total=nonnegative(totals['nonop_expense'],'영업외비용')
    if exempt_expense is None and other_expense is None:
        ee=ZERO;oe=expense_total;expense_manual=False
    else:
        ee=nonnegative(exempt_expense or 0,'영업외비용 감면분');oe=nonnegative(other_expense or 0,'영업외비용 기타분');expense_manual=True
    revenues=[won(b.get('revenue',0)) for b in businesses]
    def split(total):
        vals=[won(dec(total)*(dec(v)/supplied if supplied else ZERO)) for v in revenues]
        if vals:vals[max(range(len(revenues)),key=lambda i:revenues[i])]+=won(total)-sum(vals)
        return vals
    costs=split(totals['cost']);sgas=split(totals['sga']);incomes=split(ei);expenses=split(ee)
    for idx,b in enumerate(businesses):
        revenue=revenues[idx];ratio=dec(revenue)/supplied if supplied else ZERO;name=('감면분('+b['name']+')') if len(businesses)>1 else '감면분';loss=won((losses or {}).get(name,(losses or {}).get(b['name'],0)));current=revenue-costs[idx]-sgas[idx]+incomes[idx]-expenses[idx];taxable=max(0,current-loss)
        bs.append({'name':name,'revenue':revenue,'ratio':float(ratio*100),'cost':costs[idx],'sga':sgas[idx],'nonop_income':incomes[idx],'nonop_expense':expenses[idx],'current_income':current,'loss':loss,'taxable':taxable})
    other_current=other_income-oe;other_loss=dec((losses or {}).get('기타분',0));bs.append({'name':'기타분','revenue':0,'ratio':0,'cost':0,'sga':0,'nonop_income':won(other_income),'nonop_expense':won(oe),'current_income':won(other_current),'loss':won(other_loss),'taxable':won(max(ZERO,other_current-other_loss))})
    return {'rows':bs,'totals':totals,'current_income':sum(r['current_income'] for r in bs),'taxable':sum(r['taxable'] for r in bs),'check':sum(r['revenue'] for r in bs)-totals['sales'],'exempt_income':won(ei),'exempt_expense':won(ee),'other_expense':won(oe),'expense_check':won(ee+oe-expense_total),'expense_manual':expense_manual}

def corporate_tax(base):
    x=max(ZERO,dec(base));bands=[(Decimal('200000000'),Decimal('.09')),(Decimal('20000000000'),Decimal('.19')),(Decimal('300000000000'),Decimal('.21'))]
    tax=ZERO;lower=ZERO
    for upper,rate in bands:
        part=min(x,upper)-lower
        if part>0:tax+=part*rate
        if x<=upper:return won(tax)
        lower=upper
    return won(tax+(x-lower)*Decimal('.24'))
def local_tax(base):return won(dec(corporate_tax(base))*Decimal('.10'))

def prepaid_tax(inputs):
    """Return split prepaid taxes while preserving legacy combined values."""
    has_split='prepaid_corp_interim' in inputs or 'prepaid_corp_withholding' in inputs
    legacy=won(inputs.get('prepaid_corp',0))
    interim=won(inputs.get('prepaid_corp_interim',legacy if not has_split else 0))
    withholding=won(inputs.get('prepaid_corp_withholding',0))
    local=won(inputs.get('prepaid_local',0))
    return {'prepaid_corp_interim':interim,'prepaid_corp_withholding':withholding,
            'prepaid_corp':interim+withholding,'prepaid_local':local,
            'prepaid_total':interim+withholding+local}

def tax_calculation(current_income,inputs):
    i={k:won(inputs.get(k,0)) for k in ['donation_excess','donation_carry_deduction','carry_loss','special_reduction','rd_prior','rd_current','undocumented_base','land_gain','accrued_tax']}
    i.update(prepaid_tax(inputs))
    income=won(dec(current_income)+dec(i['donation_excess'])-dec(i['donation_carry_deduction']));taxable=max(0,income-i['carry_loss']);output=corporate_tax(taxable);penalty_rate=dec(inputs.get('undocumented_rate',2))/100;penalty=tax_won(dec(i['undocumented_base'])*penalty_rate);land_rate=dec(inputs.get('land_rate',20))/100;land_tax=tax_won(dec(i['land_gain'])*land_rate)
    if 'special_base' in inputs:i['special_reduction']=tax_won(max(ZERO,dec(inputs.get('special_base',0))-dec(inputs.get('reduced_headcount',0))*Decimal('5000000'))*dec(inputs.get('special_rate',15))/100)
    credits=min(output,max(0,i['special_reduction'])+max(0,i['rd_prior'])+max(0,i['rd_current']));ordinary_corp=max(0,output-credits+penalty);corp_total=ordinary_corp+land_tax;corp_payable=corp_total-i['prepaid_corp'];local_total=local_tax(taxable)+tax_won(dec(penalty)*Decimal('.10'));local_payable=local_total-i['prepaid_local']
    return {**i,'current_income':won(current_income),'income':income,'taxable':taxable,'output_tax':output,'credits':credits,'penalty':penalty,'penalty_rate':float(penalty_rate*100),'land_rate':float(land_rate*100),'land_tax':land_tax,'ordinary_corp':ordinary_corp,'corp_total':corp_total,'corp_payable':corp_payable,'local_total':local_total,'local_payable':local_payable,'confirmed_tax':corp_total+local_total,'tax_expense':corp_total+local_total,'net_income':won(dec(inputs.get('pre_tax',0))-(corp_total+local_total))}

def reserve_rollforward(beginning,increase,deduction,other=0):
    ending=dec(beginning)+dec(increase)-dec(deduction)+dec(other)
    if ending<0:raise ValueError('당기 손금추인액은 사용 가능한 유보잔액을 초과할 수 없습니다.')
    return won(ending)
