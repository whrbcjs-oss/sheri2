"""Exact daily intercompany loan interest with explicit day and rounding rules."""
from datetime import date,timedelta
from calendar import monthrange,isleap
from decimal import Decimal,ROUND_FLOOR,ROUND_HALF_UP
import loan_calc as common
D=common.number
def day(v):
 try:return common.day(v)
 except (ValueError,TypeError):raise ValueError('날짜를 YYYY-MM-DD 형식으로 입력하세요.')
def period(v):
 v=str(v)
 try:
  dt=day(v+'-01')
  if not 1990<=dt.year<=2100:raise ValueError()
 except ValueError:raise ValueError('기준월은 YYYY-MM 형식으로 입력하세요.')
 return v
def month_end(v):
 d=day(period(v)+'-01');return d.replace(day=monthrange(d.year,d.month)[1])
def months(start,end):
 start=day(start).replace(day=1);end=day(end)
 while start<=end:
  yield start.strftime('%Y-%m');start=common.add_months(start,1)
def won(v,mode='절사'):return int(D(v).quantize(D(1),rounding=ROUND_FLOOR if mode=='절사' else ROUND_HALF_UP))
def change(e):return D(e.get('principal',0))*(1 if e['kind']=='추가원금' else -1)
def effective(e,t):
 d=day(e['event_date'])
 return d+timedelta(days=1) if e['kind']!='추가원금' and t.get('repay_inclusive',True) else d

def balance(t,events,as_of):
 if day(as_of)<day(t['start']):return D(0)
 return D(t['principal'])+sum((change(e) for e in events if day(e['event_date'])<=day(as_of)),D(0))
def rate_at(t,rates,d):
 applicable=[r for r in rates if day(r['effective_date'])<=day(d)]
 exception=[r for r in rates if r.get('exception_rate')]
 if exception:
  available=[r for r in exception if day(r['effective_date'])<=day(d) and r['rate'] is not None]
  if not available:raise ValueError('해당 날짜의 회사별 예외이율이 없습니다. 공통이율로 대체하지 않습니다: '+str(day(d)))
  chosen=max(available,key=lambda r:(r['effective_date'],r['id']));return D(chosen['rate']),chosen.get('kb')
 common=[r for r in rates if r.get('common_rate')]
 if common:
  available=[r for r in common if day(r['effective_date'])<=day(d) and r['rate'] is not None]
  if not available:raise ValueError('해당 날짜에 적용할 공통이율이 없습니다: '+str(day(d)))
  chosen=max(available,key=lambda r:(r['effective_date'],r['id']));return D(chosen['rate']),chosen.get('kb')
 cutoff=t.get('import_rate_until')
 if cutoff and day(d)>day(cutoff) and not any(r.get('deal_id')==t.get('id') and cutoff<r['effective_date']<=day(d).isoformat() for r in applicable):raise ValueError('엑셀 이후 기간의 약정이율을 등록하세요: '+str(day(d)))
 if t.get('ledger_source'):
  # Explicit per-loan overrides remain deliberate; copied snapshots must not hide live company rates.
  manual=[r for r in applicable if r.get('deal_id')==t.get('id') and not r.get('ledger_template') and not str(r.get('note','')).startswith('원장 기준 약정 ')]
  if manual:
   chosen=max(manual,key=lambda r:(r['effective_date'],r['id']));return D(chosen['rate']),chosen.get('kb')
  pair=[r for r in rates if r.get('deal_id') is None and (r['lender_id'],r['borrower_id'])==(t['lender_id'],t['borrower_id'])]
  if pair:
   available=[r for r in pair if day(r['effective_date'])<=day(d)]
   if not available:raise ValueError('해당 기간의 회사 간 기본이율이 없습니다: '+str(day(d)))
   chosen=max(available,key=lambda r:(r['effective_date'],r['id']));return D(chosen['rate']),chosen.get('kb')
 own=sorted([r for r in applicable if r.get('deal_id')==t.get('id')],key=lambda r:(r['effective_date'],r['id']))
 if own:return D(own[-1]['rate']),own[-1].get('kb')
 if t.get('rate_mode','거래별')=='회사 기본이율':
  pair=sorted([r for r in applicable if r.get('deal_id') is None and r['lender_id']==t['lender_id'] and r['borrower_id']==t['borrower_id']],key=lambda r:(r['effective_date'],r['id']))
  if not pair:raise ValueError('이율이 등록되지 않았습니다: '+str(day(d))+'. 회사 기본이율 또는 거래별 약정이율을 등록하세요.')
  return D(pair[-1]['rate']),pair[-1].get('kb')
 if t.get('rate') in (None,''):raise ValueError('거래별 약정이율을 입력하세요. 무이자는 0을 입력합니다.')
 return D(t['rate']),t.get('kb')
def calculation(t,events,rates,month):
 start=max(day(t['interest_start'])+timedelta(days=0 if t.get('first_inclusive',True) else 1),day(period(month)+'-01'))
 end=month_end(month);parts=[]
 if start>end:return dict(month=month,segments=[],calculated=0,adjustment=0,final_interest=0)
 boundary={start,end+timedelta(days=1)}
 boundary.update(effective(e,t) for e in events if start<effective(e,t)<=end)
 boundary.update(day(r['effective_date']) for r in rates if start<day(r['effective_date'])<=end)
 for y in range(start.year+1,end.year+1):boundary.add(date(y,1,1))
 edges=sorted(boundary);raw=D(0)
 for a,b in zip(edges,edges[1:]):
  principal=D(t['principal'])+sum((change(e) for e in events if effective(e,t)<=a),D(0))
  if principal<0:raise ValueError('원금 상환·회수액이 잔액보다 큽니다.')
  if not principal:continue
  rate,kb=rate_at(t,rates,a);days=(b-a).days;denom=366 if t.get('basis','365')=='실제연도' and isleap(a.year) else 365
  interest=principal*days*rate/D(denom)/100;raw+=interest
  parts.append(dict(start=a.isoformat(),end=(b-timedelta(days=1)).isoformat(),principal=str(principal),days=days,rate=str(rate),kb=kb,denominator=denom,raw=str(interest)))
 mode=t.get('rounding','절사');rounding_unit=t.get('rounding_unit','월 합계')
 if rounding_unit=='구간별':amount=sum(won(p['raw'],mode) for p in parts)
 else:amount=won(raw,mode)
 for p in parts:p['interest']=won(p['raw'],mode)
 policy=next((r.get('rate_policy','회사별 예외이율') for r in rates if r.get('exception_rate')), '공통이율' if any(r.get('common_rate') for r in rates) else '기존 약정이율')
 return dict(rate_policy=policy,month=month,segments=parts,raw=str(raw),calculated=amount,adjustment=0,final_interest=amount,rounding=mode,rounding_unit=rounding_unit)
