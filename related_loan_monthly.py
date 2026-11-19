"""Per-deal monthly interest and accounting-entry summaries, without offsetting directions."""
from datetime import timedelta
import related_loan_calc as calc
import related_loan_store as db

def build(c,company,start,end,counter=None,deal_id=None,as_of=None):
 calc.period(start);calc.period(end)
 if start>end:raise ValueError('조회 시작월은 종료월 이전이어야 합니다.')
 as_of=calc.day(as_of or __import__('loan_store').today());names={r['id']:r['name'] for r in db.companies(c)};out=[];details=[]
 for t in db.deals(c,company):
  other=t['borrower_id'] if t['lender_id']==company else t['lender_id']
  if counter is not None and other!=counter or deal_id is not None and t['id']!=deal_id:continue
  es=db.events(c,t['id']);rs=db.rates(c,t)
  for month in calc.months(start+'-01',calc.month_end(end)):
   first=calc.day(month+'-01');last=calc.month_end(month)
   if last<calc.day(t['start']):continue
   prev=calc.balance(t,es,first-timedelta(days=1));closing=calc.balance(t,es,last)
   new=(calc.D(t['principal']) if first<=calc.day(t['start'])<=last else calc.D(0))+sum((calc.D(e['principal']) for e in es if e['kind']=='추가원금' and first.isoformat()<=e['event_date']<=last.isoformat()),calc.D(0))
   paid=sum((calc.D(e['principal']) for e in es if e['kind'] in ['원금상환·회수','원리금정산'] and first.isoformat()<=e['event_date']<=last.isoformat()),calc.D(0))
   old=db.month_record(c,t['id'],month);status='확정' if old and old['final'] else '예상';interest=None;rates='';parts=[];policy='확인 필요'
   if not any([prev,closing,new,paid]) and not old:continue
   try:
    result=db.calculate(c,t['id'],month);policy=result.get('rate_policy','확정 당시 기준' if old and old['final'] else '기존 약정이율');interest=result['final_interest'];parts=result['segments'];rates=' / '.join(dict.fromkeys(p['rate']+'%' for p in parts)) or '—'
   except ValueError as e:status='이율 확인 필요';rates=str(e)
   row={'귀속월':month,'구분':'대여' if t['lender_id']==company else '차입','거래처':names[other],'관리번호':t['number'],'차입·대여일':t['start'],'월초원금':int(prev),'당월차입원금':int(new),'당월상환원금':int(paid),'월말잔액':int(closing),'적용이율':rates,'이율기준':policy,'당월이자':interest,'상태':status,'거래ID':t['id']}
   if status=='예상' and last<=as_of:row['상태']='미확정'
   if closing and t.get('maturity') and calc.day(t['maturity'])<=last:row['만기안내']='만기 미상환'
   else:row['만기안내']='만기 미확인' if t.get('maturity_unverified') else ''
   out.append(row)
   for p in parts:details.append({'귀속월':month,'관리번호':t['number'],'계산시작일':p['start'],'계산종료일':p['end'],'계산원금':int(calc.D(p['principal'])),'연이율(%)':p['rate'],'일수':str(p['days']),'연간일수':str(p['denominator']),'구간이자':p['interest']})
   if interest is not None:details.append({'귀속월':month,'관리번호':t['number'],'계산시작일':'월 합계','계산종료일':'','계산원금':None,'연이율(%)':'','일수':'','연간일수':'','구간이자':interest})
 out.sort(key=lambda r:(r['귀속월'],r['구분'],r['거래처'],r['관리번호']))
 summaries=[]
 for month,kind,party in sorted({(r['귀속월'],r['구분'],r['거래처']) for r in out}):
  items=[r for r in out if (r['귀속월'],r['구분'],r['거래처'])==(month,kind,party)]
  # Keep confirmed and provisional totals separate so drafts cannot be mistaken for journal entries.
  for state in ['확정','미확정','예상','이율 확인 필요']:
   group=[r for r in items if r['상태']==state]
   if not group:continue
   summaries.append({'귀속월':month,'구분':kind,'거래처':party,'적요':month+' '+party+' '+('차입이자' if kind=='차입' else '대여이자'),'이자금액':None if any(r['당월이자'] is None for r in group) else sum(r['당월이자'] for r in group),'상태':state,'원장입력안내':'입력 검토 가능' if state=='확정' else '확정 후 입력','건수':str(len(group))})
 return dict(rows=out,details=details,summary=summaries)
