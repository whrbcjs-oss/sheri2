"""Decimal loan schedules, explicit payment allocation, and calendar-month reminders."""
from calendar import monthrange
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, localcontext

MODES=['원리금 매달 상환','만기일에 원리금 상환','이자만 매달 상환 · 원금은 만기 상환']
KINDS=['연이율','월정액','무이자']
BASES=['월 단위 (연이율 ÷ 12)','일할 (연 365일)']
METHODS=['원리금균등','원금균등']
ZERO=Decimal(0)


def number(v):
    try:
        d=Decimal(str(v if v is not None else '').replace(',','').strip() or '0')
        if not d.is_finite() or abs(d)>Decimal('1e15'):raise ValueError()
        return d
    except (ValueError,InvalidOperation):raise ValueError('금액·이율은 올바른 숫자로 입력하세요.')


def won(v):return int(number(v).quantize(Decimal('1'),rounding=ROUND_HALF_UP))
def money(v):return f'{won(v):,}'
def day(v):return v if isinstance(v,date) else date.fromisoformat(str(v))


def add_months(d,n,pay_day=None):
    d=day(d);index=d.year*12+d.month-1+n;y,m=divmod(index,12);m+=1
    return date(y,m,min(pay_day or d.day,monthrange(y,m)[1]))


def months_elapsed(start,end):
    start,end=day(start),day(end)
    if end<=start:return ZERO
    n=(end.year-start.year)*12+end.month-start.month
    if add_months(start,n)>end:n-=1
    anchor=add_months(start,n);next_=add_months(start,n+1)
    return Decimal(n)+Decimal((end-anchor).days)/Decimal((next_-anchor).days)


def validate(data):
    v=dict(data)
    for k in ['issued_date','start_date','end_date','first_due']:
        try:v[k]=day(v[k]).isoformat()
        except (KeyError,TypeError,ValueError):raise ValueError('작성일·차용기간·최초 상환일을 확인하세요.')
    start,end,first=map(day,[v['start_date'],v['end_date'],v['first_due']])
    if end<=start or end>add_months(start,600):raise ValueError('만료일은 시작일 이후, 50년 이내로 입력하세요.')
    if v.get('mode') not in MODES or v.get('interest_kind') not in KINDS:raise ValueError('상환방식과 이자 기준을 선택하세요.')
    if v.get('basis') not in BASES or v.get('method') not in METHODS:raise ValueError('이자 계산 기준과 분할 방식을 확인하세요.')
    if v['mode']!=MODES[1] and not start<first<=end:raise ValueError('최초 상환일은 시작일 이후, 만료일 이내여야 합니다.')
    for k in ['principal','fixed_interest','installment','carry_interest','interest_credit']:
        n=number(v.get(k,0))
        if n<0 or n!=n.to_integral_value():raise ValueError('금액은 0 이상의 원 단위 정수로 입력하세요.')
        v[k]=int(n)
    if v['principal']<=0:raise ValueError('차용금액은 0보다 커야 합니다.')
    rate=number(v.get('rate',0))
    if not 0<=rate<=100:raise ValueError('이율은 0~100 범위로 입력하세요.')
    v['rate']=str(rate)
    v['pay_day']=int(v.get('pay_day',first.day))
    if not 1<=v['pay_day']<=31:raise ValueError('매월 상환일은 1~31일로 입력하세요.')
    if v['mode']==MODES[1]:v['first_due']=v['end_date']
    return v


def due_dates(v):
    v=validate(v);end=day(v['end_date'])
    if v['mode']==MODES[1]:return [end]
    dates=[day(v['first_due'])]
    while dates[-1]<end:
        next_=add_months(dates[-1],1,v['pay_day'])
        if next_>=end:break
        dates.append(next_)
    if dates[-1]!=end:dates.append(end)
    return dates


def factor(v,a,b):
    if v['basis']==BASES[1]:return Decimal((day(b)-day(a)).days)/365
    return (months_elapsed(v['start_date'],b)-months_elapsed(v['start_date'],a))/12


def raw_interest(v,balance,a,b):
    if v['interest_kind']==KINDS[2] or balance<=0:return ZERO
    if v['interest_kind']==KINDS[1]:return number(v['fixed_interest'])*(months_elapsed(v['start_date'],b)-months_elapsed(v['start_date'],a))
    return number(balance)*number(v['rate'])/100*factor(v,a,b)


def adjusted_interest(v,balance,a,b,receipts,prior_principal):
    """Optional early-payment reduction; late charges are never invented."""
    if v.get('early_interest','약정 유지')!='잔여원금 기준' or v['interest_kind']!=KINDS[0]:return raw_interest(v,balance,a,b)
    a,b=day(a),day(b);paid=sum((number(r['principal']) for r in receipts if day(r['receipt_date'])<=a),ZERO)
    points=sorted({day(r['receipt_date']) for r in receipts if a<day(r['receipt_date'])<b})+[b]
    result=ZERO;cursor=a
    for point in points:
        effective=max(ZERO,number(balance)-max(ZERO,paid-prior_principal))
        result+=raw_interest(v,effective,cursor,point)
        paid+=sum((number(r['principal']) for r in receipts if day(r['receipt_date'])==point),ZERO)
        cursor=point
    return result


def schedule(data,receipts=()):
    v=validate(data);dates=due_dates(v);balance=v['principal'];rows=[];start=day(v['start_date']);n=len(dates)
    payment=ZERO
    with localcontext() as ctx:
        ctx.prec=40
        if v['mode']==MODES[0] and v['method']==METHODS[0] and not v['installment']:
            if v['interest_kind']==KINDS[0]:
                discount=Decimal(1);denominator=ZERO;cursor=start
                for due in dates:
                    discount/=1+number(v['rate'])/100*factor(v,cursor,due);denominator+=discount;cursor=due
                payment=Decimal(balance)/denominator
            else:payment=Decimal(balance)/n
        cursor=start;paid_planned=ZERO
        for i,due in enumerate(dates):
            regular=won(raw_interest(v,balance,cursor,due))
            interest=won(adjusted_interest(v,balance,cursor,due,receipts,paid_planned))
            if v['mode'] in [MODES[1],MODES[2]]:principal=balance if i==n-1 else 0
            elif i==n-1:principal=balance
            elif v['installment']:
                if v['installment']<=regular:raise ValueError('월 약정 상환액은 해당 회차의 이자보다 커야 합니다.')
                principal=min(balance,v['installment']-regular)
            elif v['method']==METHODS[1]:principal=min(balance,v['principal']//n)
            elif v['interest_kind']==KINDS[0]:principal=min(balance,max(0,won(payment)-regular))
            else:principal=min(balance,won(payment))
            balance-=principal
            carry=0
            rows.append(dict(index=i+1,begin=cursor.isoformat(),due_date=due.isoformat(),principal=principal,regular_interest=interest,carry_interest=carry,interest=interest+carry,total=principal+interest+carry,balance=balance))
            paid_planned+=principal;cursor=due
            if balance==0 and v['mode']==MODES[0]:break
    policy=v.get('carry_policy','첫 상환일 정산');carry=v['carry_interest']
    if policy not in ['첫 상환일 정산','마지막 상환일 정산','회차별 분할 정산']:raise ValueError('미회수 이자 정산방법을 확인하세요.')
    for i,row in enumerate(rows):
        amount=(carry//len(rows)+(carry%len(rows) if i==len(rows)-1 else 0)) if policy=='회차별 분할 정산' else carry if i==(len(rows)-1 if policy=='마지막 상환일 정산' else 0) else 0
        row['carry_interest']=amount;row['interest']+=amount;row['total']+=amount
    return rows


def reconcile(v,receipts,as_of):
    as_of=day(as_of);receipts=sorted([r for r in receipts if day(r['receipt_date'])<=as_of],key=lambda r:(r['receipt_date'],r.get('id',0)))
    rows=schedule(v,receipts);principal=sum((won(r['principal']) for r in receipts),0);interest=sum((won(r['interest']) for r in receipts),0)+won(v.get('interest_credit',0))
    result=[]
    for row in rows:
        p=min(principal,row['principal']);principal-=p;i=min(interest,row['interest']);interest-=i
        due=day(row['due_date'])<=as_of
        result.append(dict(row,paid_principal=p,paid_interest=i,paid=p+i,unpaid=max(0,row['total']-p-i) if due else 0,status='회수 완료' if p+i>=row['total'] else '미회수' if due else '예정'))
    return result


def accrued_interest(v,receipts,as_of):
    v=validate(v);as_of=day(as_of)
    receipts=[r for r in receipts if day(r['receipt_date'])<=as_of]
    cutoff=min(as_of,day(v['end_date']));earned=number(v.get('carry_interest',0));prior=0
    for row in schedule(v,receipts):
        a,b=day(row['begin']),day(row['due_date'])
        if cutoff<=a:break
        if cutoff>=b:earned+=row['regular_interest']
        else:earned+=adjusted_interest(v,v['principal']-prior,a,cutoff,receipts,number(prior))
        prior+=row['principal']
    paid=sum((number(r['interest']) for r in receipts),ZERO)+number(v.get('interest_credit',0))
    return max(0,won(earned-paid)),max(0,won(paid-earned))


def maturity_status(v,balance,unpaid_interest,current):
    end=day(v['end_date']);current=day(current)
    if balance<=0 and unpaid_interest<=0:return None
    if current<add_months(end,-1):return None
    return '기일 경과' if current>end else '오늘 만기' if current==end else '만기 도래 예정'


def scenario_rows(data):
    """Monthly forecast, separating interest earned from interest actually due."""
    v=validate(data);plan=schedule(v);credit=v['interest_credit'];result=[]
    if v['mode']==MODES[1]:
        first=min(add_months(v['start_date'],1,v['pay_day']),day(v['end_date']))
        dates=due_dates(dict(v,mode=MODES[2],first_due=str(first)))
        previous=0
        for index,due in enumerate(dates):
            earned=won(raw_interest(v,v['principal'],v['start_date'],due))
            final=index==len(dates)-1
            result.append(dict(index=index+1,due_date=str(due),accrued_interest=earned-previous,carry_interest=v['carry_interest'] if final else 0,principal=v['principal'] if final else 0,interest=plan[0]['interest'] if final else 0,balance=0 if final else v['principal']))
            previous=earned
    else:
        result=[dict(r,accrued_interest=r['regular_interest']) for r in plan]
    for row in result:
        applied=min(credit,row['interest']);credit-=applied
        row['interest_credit']=applied;row['interest']-=applied
        row['total']=row['principal']+row['interest']
    return result
