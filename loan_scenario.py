"""Loan-by-loan forecasts and spreadsheet-style printable repayment statements."""
from datetime import date
from decimal import Decimal
from io import BytesIO
from html import escape
import loan_calc as calc

BASIS=['월할 (매회 연이율 ÷ 12)','계약 기준 (부분월 반영)','일할 (365일)']

def allocate(amount,weights):
    amount=int(amount);weights=[int(w) for w in weights];total=sum(weights)
    if not total:return [0]*len(weights)
    amount=min(amount,total);raw=[Decimal(amount)*w/total for w in weights];result=[int(x) for x in raw]
    order=sorted(range(len(weights)),key=lambda i:(raw[i]-result[i],-i),reverse=True)
    for i in order[:amount-sum(result)]:result[i]+=1
    return result


def forecast(sources,options):
    sources=[dict(s) for s in sources];o=dict(options)
    start=calc.day(o['as_of']);end=calc.day(o['end_date']);first=calc.day(o['first_due']);mode=o['mode'];basis=o.get('basis',BASIS[0])
    if mode not in calc.MODES or basis not in BASIS:raise ValueError('상환방식과 이자 계산 기준을 선택하세요.')
    if not sources or len({s['loan_id'] for s in sources})!=len(sources):raise ValueError('차용건을 중복 없이 선택하세요.')
    if len({(s['borrower_id'],s['company']) for s in sources})!=1:raise ValueError('같은 차용인·지급회사의 건을 선택하세요.')
    manual=bool(o.get('manual')) and mode==calc.MODES[0];auto=manual and bool(o.get('auto_payoff'));amount=calc.won(o.get('installment',0));payday=int(o.get('pay_day',first.day))
    if not 1<=payday<=31 or end<=start or not start<first or (not auto and first>end):raise ValueError('기준일 이후의 첫 상환일·만기·상환일을 확인하세요.')
    if end>calc.add_months(start,600):raise ValueError('만기는 기준일로부터 50년 이내로 입력하세요.')
    if manual and amount<=0:raise ValueError('매월 원리금 납부액을 입력하세요.')
    for s in sources:
        for k in ['principal','carry_interest','interest_credit','fixed_interest']:
            v=calc.number(s.get(k,0))
            if v<0 or v!=v.to_integral_value():raise ValueError('금액은 0 이상의 원 단위로 입력하세요.')
            s[k]=int(v)
        rate=calc.number(s.get('rate',0))
        if not 0<=rate<=100 or s['interest_kind'] not in calc.KINDS:raise ValueError('이율·이자 구분을 확인하세요.')
        s['rate']=str(rate)
    balances=[s['principal'] for s in sources];pre=calc.won(o.get('prepayment',0))
    if not 0<=pre<sum(balances):raise ValueError('추가 상환 가정은 잔여원금보다 작게 입력하세요.')
    deductions=allocate(pre,balances);balances=[p-d for p,d in zip(balances,deductions)]
    arrears=[s['carry_interest'] for s in sources];credits=[s['interest_credit'] for s in sources]
    if o.get('method',calc.METHODS[0]) not in calc.METHODS:raise ValueError('원리금 계산방식을 확인하세요.')
    schedule_dates=calc.due_dates(dict(issued_date=str(start),start_date=str(start),end_date=str(end),first_due=str(first),pay_day=payday,principal=1,rate=0,interest_kind=calc.KINDS[2],fixed_interest=0,mode=calc.MODES[2],method=calc.METHODS[0],basis=calc.BASES[0])) if not auto else []
    flat_payments=[];flat_principal=list(balances)
    for s,p in zip(sources,balances):
        n=len(schedule_dates) or 1;r=calc.number(s['rate'])/1200
        payment=Decimal(p)*r/(1-(1+r)**(-n)) if r and s['interest_kind']==calc.KINDS[0] else Decimal(p)/n
        flat_payments.append(calc.won(payment))
    schedules=[]
    for s,p in zip(sources,balances):
        v=dict(issued_date=str(start),start_date=str(start),end_date=str(end),first_due=str(first),pay_day=payday,principal=p or 1,rate=s['rate'],interest_kind=s['interest_kind'],fixed_interest=s['fixed_interest'],mode=mode,method=o.get('method',calc.METHODS[0]),basis=calc.BASES[1] if basis==BASIS[2] else calc.BASES[0],installment=0)
        schedules.append(calc.schedule(v) if not manual and basis!=BASIS[0] else [])
    rows=[];cursor=start
    for n in range(600):
        due=first if n==0 else calc.add_months(first,n,payday)
        if not auto:due=min(due,end)
        final=not auto and due==end
        opening=list(balances);old=list(arrears);opening_arrears=list(arrears);earned=[]
        for s,p in zip(sources,balances):
            v=dict(s,start_date=str(start),basis=calc.BASES[1] if basis==BASIS[2] else calc.BASES[0])
            value=0 if p<=0 else (Decimal(p)*calc.number(s['rate'])/1200 if s['interest_kind']==calc.KINDS[0] else s['fixed_interest'] if s['interest_kind']==calc.KINDS[1] else 0) if basis==BASIS[0] else calc.raw_interest(v,p,cursor,due)
            earned.append(calc.won(value))
        current=list(earned);used=[]
        for i in range(len(sources)):
            apply=min(credits[i],old[i]);old[i]-=apply;credits[i]-=apply
            extra=min(credits[i],current[i]);current[i]-=extra;credits[i]-=extra;used.append(apply+extra)
        interest_due=[a+b for a,b in zip(old,current)]
        if mode==calc.MODES[1]:budget=sum(balances)+sum(interest_due) if final else 0
        elif mode==calc.MODES[2]:budget=sum(interest_due)+(sum(balances) if final else 0)
        elif manual:budget=sum(balances)+sum(interest_due) if final else min(amount,sum(balances)+sum(interest_due))
        else:
            if basis==BASIS[0]:
                ps=[p if final else min(p,max(0,flat_principal[i]//len(schedule_dates) if o.get('method')==calc.METHODS[1] else flat_payments[i]-earned[i] if sources[i]['interest_kind']==calc.KINDS[0] else flat_payments[i])) for i,p in enumerate(balances)]
            else:ps=[min(p,schedules[i][n]['principal'] if n<len(schedules[i]) else p if final else 0) for i,p in enumerate(balances)]
            budget=sum(interest_due)+sum(ps)
        current_paid=allocate(min(budget,sum(current)),current);remaining=budget-sum(current_paid)
        old_paid=allocate(min(remaining,sum(old)),old);remaining-=sum(old_paid)
        ip=[a+b for a,b in zip(current_paid,old_paid)]
        pp=allocate(min(remaining,sum(balances)),balances) if manual or mode!=calc.MODES[0] else ps
        balances=[p-paid for p,paid in zip(balances,pp)];arrears=[p-paid for p,paid in zip(interest_due,ip)]
        parts=[dict(loan_id=s['loan_id'],opening=opening[i],earned=earned[i],old_interest=opening_arrears[i],interest_paid=ip[i],principal_paid=pp[i],balance=balances[i],interest_balance=arrears[i],credit_used=used[i],credit_balance=credits[i]) for i,s in enumerate(sources)]
        rows.append(dict(index=n+1,due_date=str(due),parts=parts,earned_interest=sum(earned),old_interest=sum(r['old_interest'] for r in parts),interest_paid=sum(ip),principal_paid=sum(pp),total=sum(ip)+sum(pp),balance=sum(balances),interest_balance=sum(arrears),credit_balance=sum(credits),credit_used=sum(used)))
        if sum(balances)+sum(arrears)==0 or final:break
        if auto and sum(pp)==0 and amount<=sum(current) and not any(credits):raise ValueError('월 납부액이 월 이자보다 작거나 같아 완제할 수 없습니다. 납부액을 늘리세요.')
        cursor=due
    else:raise ValueError('600회 이내에 상환되지 않습니다. 납부액·기간을 확인하세요.')
    return dict(sources=sources,options=o,rows=rows,totals=dict(principal=sum(r['principal_paid'] for r in rows),interest=sum(r['interest_paid'] for r in rows),payment=sum(r['total'] for r in rows),end_date=rows[-1]['due_date'],count=len(rows),balance=rows[-1]['balance'],unpaid_interest=rows[-1]['interest_balance'],prepayment=pre))


def statement_records(result):
    records=[];sources=result['sources']
    for r in result['rows']:
        values={'회차':r['index'],'상환일':r['due_date']}
        for i,s in enumerate(sources):values[s['number']+' 기초원금']=r['parts'][i]['opening']
        for i,s in enumerate(sources):values[s['number']+' 월이자']=r['parts'][i]['earned']
        values['과거 미납이자']=r['old_interest'];values['총 이자상환']=r['interest_paid']
        for i,s in enumerate(sources):values[s['number']+' 원금상환']=r['parts'][i]['principal_paid']
        values['상환원금합계']=r['principal_paid'];values['월 납부액']=r['total']
        for i,s in enumerate(sources):values[s['number']+' 기말원금']=r['parts'][i]['balance']
        values['총 원금잔액']=r['balance'];values['이월 미납이자']=r['interest_balance'];values['선납이자 잔액']=r['credit_balance'];records.append(values)
    return records


def summary_records(r):
    t=r['totals'];return [('기준일',r['options']['as_of']),('상환방식',r['options']['mode']),('이자 계산 기준',r['options']['basis']),('초기 원금',sum(s['principal'] for s in r['sources'])),('기존 미회수 이자',sum(s['carry_interest'] for s in r['sources'])),('추가 원금상환 가정',t['prepayment']),('예상 상환 횟수',t['count']),('예상 종료일',t['end_date']),('총 원금 상환',t['principal']),('총 이자 상환',t['interest']),('총 납부액',t['payment']),('최종 원금 잔액',t['balance']),('최종 미납이자 잔액',t['unpaid_interest'])]


def html(result,printable=False,status='예상 시나리오'):
    esc=lambda x:escape(str(x),quote=True);records=statement_records(result);headers=list(records[0]);cls='loan-scenario-report';source=result['sources'][0]
    css=f'''#{cls}{{font:13px "Malgun Gothic",sans-serif;color:#193b30;width:100%}}#{cls} h2{{text-align:center;font-size:22px}}#{cls} .scroll{{overflow-x:auto}}#{cls} table{{border-collapse:collapse;width:100%;font-size:12px}}#{cls} th,#{cls} td{{border:1px solid #9db5a8;padding:7px 5px;text-align:center;overflow-wrap:anywhere}}#{cls} th{{background:#deebf7}}#{cls} td.money{{text-align:right;white-space:nowrap;font-variant-numeric:tabular-nums}}#{cls} .total{{background:#e2f0d9;font-weight:bold}}#{cls} .meta{{font-size:13px;margin:8px 0}}#{cls} .summary{{margin:15px 0}}@page{{size:A3 landscape;margin:10mm}}@media print{{.tools{{display:none}}#{cls} .scroll{{overflow:visible}}#{cls} table{{font-size:{max(6,10-len(result['sources'])*.4)}px}}#{cls} td.money{{white-space:normal}}thead{{display:table-header-group}}tr{{break-inside:avoid}}}}'''
    summary='<table class="summary"><tr>'+''.join('<th>'+esc(label)+'</th><td>'+esc(calc.money(value) if isinstance(value,int) else value)+'</td>' for label,value in summary_records(result)[-7:-2])+'</tr></table>'
    table='<table><thead><tr>'+''.join('<th>'+esc(h)+'</th>' for h in headers)+'</tr></thead><tbody>'
    for row in records:table+='<tr>'+''.join('<td class="'+('money' if i>=2 else '')+'">'+esc(calc.money(row[h]) if i>=2 else row[h])+'</td>' for i,h in enumerate(headers))+'</tr>'
    total={'회차':'합계','상환원금합계':result['totals']['principal'],'총 이자상환':result['totals']['interest'],'월 납부액':result['totals']['payment'],'총 원금잔액':result['totals']['balance'],'이월 미납이자':result['totals']['unpaid_interest']}
    table+='<tr class="total">'+''.join('<td class="'+('money' if i>=2 else '')+'">'+esc(calc.money(total[h]) if isinstance(total.get(h),int) else total.get(h,''))+'</td>' for i,h in enumerate(headers))+'</tr></tbody></table>'
    conditions='<table class="summary"><thead><tr>'+''.join('<th>'+h+'</th>' for h in ['관리번호','대여일','초기 원금','이자 조건','기존 미납이자','선납이자'])+'</tr></thead><tbody>'
    for s in result['sources']:
        interest=('연 '+s['rate']+'%') if s['interest_kind']==calc.KINDS[0] else ('월 '+calc.money(s['fixed_interest'])+'원') if s['interest_kind']==calc.KINDS[1] else '무이자'
        values=[s['number'],s['start_date'],calc.money(s['principal']),interest,calc.money(s['carry_interest']),calc.money(s['interest_credit'])]
        conditions+='<tr>'+''.join('<td class="'+('money' if i in [2,4,5] else '')+'">'+esc(v)+'</td>' for i,v in enumerate(values))+'</tr>'
    conditions+='</tbody></table>'
    assumption='<div class="meta">'+esc('월 납부액 직접 지정 · 원금 비율 배분' if result['options'].get('manual') and result['options']['mode']==calc.MODES[0] else result['options'].get('method',''))+' · 추가 원금상환 가정 '+calc.money(result['totals']['prepayment'])+'원 · '+('월 납부액 '+calc.money(result['options'].get('installment',0))+'원' if result['options'].get('manual') and result['options']['mode']==calc.MODES[0] else '약정 방식에 따라 자동 계산')+'</div>'
    body='<section id="'+cls+'"><h2>월별 상환명세</h2><div class="meta">'+esc(status)+' · '+esc(source['name'])+' · '+esc(source['company'])+' · 기준일 '+esc(result['options']['as_of'])+'</div><div class="meta">'+esc(result['options']['mode'])+' · '+esc(result['options']['basis'])+' · 이자 우선 충당, 월정액의 잔여 납부액은 원금 비율로 배분</div>'+assumption+conditions+summary+'<div class="scroll">'+table+'</div><p>미납이자는 다음 회차에 이월하며 원금에 더하여 이자를 부과하지 않습니다. 추가 상환 가정은 실제 입금 내역이 아닙니다.</p></section>'
    if not printable:return '<style>'+css+'</style>'+body
    return '<!doctype html><html lang="ko"><meta charset="utf-8"><title>월별 상환명세</title><style>'+css+'</style><div class="tools"><button onclick="window.print()">인쇄 / PDF 저장</button></div>'+body+'</html>'


def excel(result,status='예상 시나리오'):
    from openpyxl import Workbook
    from openpyxl.styles import Font,PatternFill,Alignment
    from openpyxl.utils import get_column_letter
    from table_layout import format_excel
    w=Workbook();conditions=w.active;conditions.title='차용조건'
    conditions.append(['차용조건 · '+status]);conditions.append(['항목']+[s['number'] for s in result['sources']])
    for label,key in [('차용인','name'),('지급회사','company'),('대여일','start_date'),('초기 원금','principal'),('연이율 (%)','rate'),('이자 구분','interest_kind'),('매월 약정이자','fixed_interest'),('기존 미회수 이자','carry_interest'),('선납이자','interest_credit')]:conditions.append([label]+[s.get(key,'') for s in result['sources']])
    for label,value in summary_records(result):conditions.append([label,value])
    sheet=w.create_sheet('월별상환명세');records=statement_records(result);headers=list(records[0]);sheet.append(['월별 상환명세 · '+status]);sheet.append(['이자 우선 충당 · 미납이자 이월 · 금액 단위: 원']);sheet.append([]);sheet.append(headers)
    for r in records:sheet.append([r[h] for h in headers])
    totals={h:sum(r[h] for r in records) for h in headers if h.endswith(' 월이자') or h.endswith(' 원금상환') or h in ['총 이자상환','상환원금합계','월 납부액']}
    totals.update({'회차':'최종 합계','총 원금잔액':result['totals']['balance'],'이월 미납이자':result['totals']['unpaid_interest']});sheet.append([totals.get(h,'') for h in headers]);sheet.merge_cells(start_row=1,start_column=1,end_row=1,end_column=len(headers));sheet.merge_cells(start_row=2,start_column=1,end_row=2,end_column=len(headers));sheet.freeze_panes='C5';sheet.print_title_rows='1:4';sheet.row_dimensions[4].height=48
    summary=w.create_sheet('상환요약');summary.append(['원리금 상환 요약 · '+status]);summary.append(['항목','금액 / 일정'])
    for row in summary_records(result):summary.append(row)
    for s in w:
        format_excel(s)
        for col in range(1,s.max_column+1):s.column_dimensions[get_column_letter(col)].width=18 if s==sheet else 28
        for rownum in ([4,s.max_row] if s==sheet else [1,2]):
            for cell in s[rownum]:cell.fill=PatternFill('solid',fgColor='DEEBF7');cell.font=Font(bold=True);cell.alignment=Alignment(horizontal='right' if isinstance(cell.value,(int,float)) and s==sheet and rownum==s.max_row else 'center',vertical='center',wrap_text=True)
        s.row_dimensions[1].height=28;s.page_setup.orientation='landscape';s.page_setup.paperSize=s.PAPERSIZE_A3;s.sheet_properties.pageSetUpPr.fitToPage=True;s.page_setup.fitToWidth=1;s.page_setup.fitToHeight=0;s.print_options.horizontalCentered=True
    for row in range(5,sheet.max_row+1):sheet.cell(row,1).alignment=Alignment(horizontal='center',vertical='center')
    conditions.merge_cells(start_row=1,start_column=1,end_row=1,end_column=max(2,len(result['sources'])+1))
    for s in w:
        for row in s:
            for cell in row:
                if isinstance(cell.value,str) and cell.value.startswith(('=','+','-','@')):cell.data_type='s'
    out=BytesIO();w.save(out);return out.getvalue()
