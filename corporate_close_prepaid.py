"""Extract contract periods from ledger descriptions and calculate prepaid expenses."""
import hashlib,re
from datetime import date,datetime

DATE_RE=re.compile(r'(?<!\d)(\d{2,4})[.\-/](\d{1,2})[.\-/](\d{1,2})(?!\d)')
VEHICLE_RE=re.compile(r'(?<![가-힣\d])(?:[가-힣]{1,2}\s*)?\d{2,3}\s*[가-힣]\s*\d{4}(?!\d)')
VEHICLE_WORDS=('책임','종합보험료','책임보험료','차량보험료','보험료')
RENT_WORDS=('부지임차료','야적장 토지임차료','야적장임차료','토지임차료')
DEFAULT_KEYWORD_RULES=[
 {'action':'include','scope':'보험료 전체','keyword':'책임보험료'}, {'action':'include','scope':'보험료 전체','keyword':'종합보험료'},
 {'action':'include','scope':'보험료 전체','keyword':'차량보험료'}, {'action':'include','scope':'보험료 전체','keyword':'보험료'},
 {'action':'include','scope':'지급임차료(원가)','keyword':'부지임차료'}, {'action':'include','scope':'지급임차료(원가)','keyword':'야적장 토지임차료'},
 {'action':'include','scope':'지급임차료(원가)','keyword':'야적장임차료'}, {'action':'include','scope':'지급임차료(원가)','keyword':'토지임차료'},
 {'action':'exclude','scope':'전체','keyword':'기한경과 대체'}, {'action':'exclude','scope':'전체','keyword':'선급비용 대체'},
 {'action':'exclude','scope':'전체','keyword':'전기이월 대체'}, {'action':'exclude','scope':'전체','keyword':'기간경과분'},
]
def is_total_row(row):
    for field in ['date','posting_date','account','description','counterparty','business']:
        value=_keyword_text(row.get(field))
        if value in ('월계','누계') or re.fullmatch(r'(?:\d{1,2}월?)?(?:월계|누계)(?:합계|금액)?',value or ''):return True
    return False

def _date(match):
    year=int(match.group(1));year=2000+year if year<100 else year
    return date(year,int(match.group(2)),int(match.group(3)))
def _clean_identifier(value):
    value=re.sub(r'^[\s:：,，.()（）\[\]-]+|[\s:：,，.()（）\[\]-]+$','',str(value or ''))
    for word in sorted((*VEHICLE_WORDS,*RENT_WORDS),key=len,reverse=True):value=value.replace(word,'')
    return re.sub(r'^[\s:：,，.()（）\[\]-]+|[\s:：,，.()（）\[\]-]+$','',value)
def _identifier(text,first_date,kind,row):
    if kind.startswith('보험료'):
        vehicle=VEHICLE_RE.search(text)
        if vehicle:return re.sub(r'\s+','',vehicle.group())
    prefix=text[:first_date.start()] if first_date else text;start=max(prefix.rfind('('),prefix.rfind('（'))
    inside=_clean_identifier(prefix[start+1:]) if start>=0 else ''
    if inside:return inside
    subject=_clean_identifier(prefix[:start] if start>=0 else prefix)
    if kind.startswith('보험료'):
        site=str(row.get('business') or '').strip();counterparty=str(row.get('counterparty') or '').strip()
        if subject and site:return f'{site} · {subject}'
        if subject:return subject
        if site:return f'{site} · 보험'
        if counterparty:return f'{counterparty} · 보험'
        return '보험대상 확인'
    return subject or '지번 확인'
def source_key(kind,row):
    raw='|'.join(str(row.get(k,'') or '') for k in ['date','account','description','debit','amount'])
    return hashlib.sha256((kind+'|'+raw).encode()).hexdigest()[:24]
def extract(kind,row,year):
    text=str(row.get('description') or '').strip();matches=list(DATE_RE.finditer(text));start=end=None
    if len(matches)>=2:
        try:start,end=_date(matches[0]),_date(matches[1])
        except ValueError:start=end=None
    identifier=_identifier(text,matches[0] if matches else None,kind,row)
    amount=row.get('debit') if row.get('debit') is not None else row.get('amount',0)
    return {'source_key':source_key(kind,row),'ledger_row_id':row.get('id'),'posting_date':row.get('posting_date') or row.get('date') or '','kind':kind,'description':text,'identifier':identifier,'site':row.get('business',''),'counterparty':row.get('counterparty',''),'amount':int(amount or 0),'start':start.isoformat() if start else '','end':end.isoformat() if end else '','opening':0,'note':'','period_source':'적요 계약기간' if start and end and end>=start else '','valid':bool(start and end and end>=start)}
def parse_day(value):
    if isinstance(value,datetime):return value.date()
    if isinstance(value,date):return value
    text=str(value or '').strip().replace('.','-').replace('/','-')
    try:return date.fromisoformat(text)
    except ValueError:return None
def calculate(item,year):
    start=parse_day(item.get('start'));end=parse_day(item.get('end'));amount=max(0,int(item.get('amount') or 0));opening=max(0,int(item.get('opening') or 0));cutoff=date(int(year)+1,1,1)
    if not start or not end or end<start:return {**item,'opening':opening,'amount':amount,'total_days':0,'prepaid_start':'','prepaid_end':'','prepaid_days':0,'ending':0,'current_expense':amount,'combined':opening+amount,'valid':False}
    total=(end-start).days+1;prepaid_start=max(start,cutoff);prepaid_days=max(0,(end-prepaid_start).days+1) if end>=prepaid_start else 0;ending=(amount*prepaid_days)//total if total else 0
    current_expense=amount-ending
    return {**item,'opening':opening,'amount':amount,'total_days':total,'prepaid_start':prepaid_start.isoformat() if prepaid_days else '','prepaid_end':end.isoformat() if prepaid_days else '','prepaid_days':prepaid_days,'ending':ending,'current_expense':current_expense,'combined':opening+current_expense,'valid':True}
def validation_error(item):
    if str(item.get('kind') or '') not in ('보험료(원가)','보험료(판관비)','지급임차료(원가)'):return '구분 확인'
    identifier=re.sub(r'[\s\[\]()._-]','',str(item.get('identifier') or ''))
    if str(item.get('kind','')).startswith('보험료') and identifier in ('','차량번호확인','보험대상확인','미분류전기잔액'):return '보험대상 확인'
    if str(item.get('kind','')).startswith('지급임차료') and identifier in ('','지번확인','미분류전기잔액'):return '지번 확인'
    if int(item.get('amount') or 0) and not item.get('valid'):return '기간 확인'
    return ''
def opening_source_key(kind,identifier,index=0):
    raw=f'{kind}|{identifier}|{index}'
    return 'opening:'+hashlib.sha256(raw.encode()).hexdigest()[:24]
def grouped_openings(rows,amount_field='ending'):
    groups={}
    for row in rows or []:
        amount=int(row.get(amount_field) or 0);identifier=str(row.get('identifier') or '').strip();kind=str(row.get('kind') or '')
        if not amount or not kind:continue
        key=(kind,identifier)
        if key not in groups:groups[key]={'source_key':opening_source_key(kind,identifier,len(groups)),'kind':kind,'identifier':identifier,'opening':0,'note':'전년도 자동이월'}
        groups[key]['opening']+=amount
    return list(groups.values())
def _identifier_key(kind,identifier):
    return (str(kind or ''),re.sub(r'[\s\[\]()._-]','',str(identifier or '')).lower())
def merge_openings(items,opening_rows):
    """Put each vehicle/parcel opening on its first current contract row."""
    balances={}
    for index,row in enumerate(opening_rows or []):
        kind=str(row.get('kind') or '');identifier=str(row.get('identifier') or '').strip();opening=max(0,int(row.get('opening') or 0));key=_identifier_key(kind,identifier)
        if not opening and not identifier:continue
        if key not in balances:balances[key]={'source_key':row.get('source_key') or opening_source_key(kind,identifier,index),'kind':kind,'identifier':identifier,'opening':0,'note':str(row.get('note') or '')}
        balances[key]['opening']+=opening
        if row.get('note'):balances[key]['note']=str(row['note'])
    result=[]
    for source in items:
        item=dict(source);key=_identifier_key(item.get('kind'),item.get('identifier'));balance=balances.pop(key,None)
        item['opening']=int(balance.get('opening') or 0) if balance else 0
        if balance and balance.get('note') and not item.get('note'):item['note']=balance['note']
        item['combined']=item['opening']+int(item.get('current_expense') or 0)
        result.append(item)
    for balance in balances.values():
        opening=int(balance.get('opening') or 0)
        result.append({'source_key':balance['source_key'],'ledger_row_id':None,'kind':balance['kind'],'description':'전기 선급비용','identifier':balance['identifier'],'site':'','counterparty':'','amount':0,'start':'','end':'','opening':opening,'total_days':0,'prepaid_start':'','prepaid_end':'','prepaid_days':0,'ending':0,'current_expense':0,'combined':opening,'note':balance.get('note',''),'valid':True})
    return result
def opening_rows_from_items(items):
    groups={}
    for row in items:
        opening=max(0,int(row.get('opening') or 0));kind=str(row.get('kind') or '');identifier=str(row.get('identifier') or '').strip()
        if not opening:continue
        key=_identifier_key(kind,identifier)
        if key not in groups:groups[key]={'source_key':opening_source_key(kind,identifier,len(groups)),'kind':kind,'identifier':identifier,'opening':0,'note':str(row.get('note') or '')}
        groups[key]['opening']+=opening
    return list(groups.values())
def keyword_rules(saved=None):return [dict(r) for r in (DEFAULT_KEYWORD_RULES if saved is None else saved)]
def _rule_scope_matches(scope,kind):
    return scope=='전체' or scope==kind or (scope=='보험료 전체' and str(kind).startswith('보험료'))
def _keyword_text(value):return ''.join(ch for ch in str(value or '').lower() if ch.isalnum())
def keyword_decision(item,rules):
    if not int(item.get('amount') or 0) and item.get('ledger_row_id') is None:return True,'전기잔액'
    text=_keyword_text(item.get('description'));kind=str(item.get('kind') or '')
    active=[r for r in rules or [] if str(r.get('keyword') or '').strip() and _rule_scope_matches(str(r.get('scope') or '전체'),kind)]
    for rule in active:
        keyword=_keyword_text(rule.get('keyword'))
        if rule.get('action')=='exclude' and keyword and keyword in text:return False,'제외문구: '+str(rule['keyword'])
    for rule in active:
        keyword=_keyword_text(rule.get('keyword'))
        if rule.get('action')=='include' and keyword and keyword in text:return True,'포함문구: '+str(rule['keyword'])
    return False,'포함문구 없음 · 검토대상'
def build(current_rows,prior_closing,overrides,year):
    result=[];pending=[];seen=set();duplicate_counts={}
    for row in current_rows:
        if is_total_row(row):continue
        item=extract(row['kind'],row,year);base_key=item['source_key'];duplicate_counts[base_key]=duplicate_counts.get(base_key,0)+1;key=base_key
        if key in seen:
            discriminator=row.get('id') or f'duplicate-{duplicate_counts[base_key]}'
            key=base_key+'-'+hashlib.sha256(str(discriminator).encode()).hexdigest()[:10]
            while key in seen:key+='x'
            item['source_key']=key
        item.update(overrides.get(key,{}));seen.add(key);pending.append(item)
    periods={}
    for item in pending:
        start=parse_day(item.get('start'));end=parse_day(item.get('end'))
        if start and end and end>=start:periods.setdefault(_identifier_key(item.get('kind'),item.get('identifier')),[]).append((start,end))
    for item in pending:
        start=parse_day(item.get('start'));end=parse_day(item.get('end'))
        if not (start and end and end>=start) and int(item.get('amount') or 0):
            candidates=periods.get(_identifier_key(item.get('kind'),item.get('identifier')),[]);posted=parse_day(item.get('posting_date'))
            if candidates:
                containing=[period for period in candidates if posted and period[0]<=posted<=period[1]];chosen=max(containing or candidates,key=lambda period:period[1])
                item['start']=chosen[0].isoformat();item['end']=chosen[1].isoformat();item['period_source']='동일 보험대상 기간 자동연결'
        result.append(calculate(item,year))
    # Carry every prior closing item independently. This avoids merging two
    # policies for the same vehicle or two leases for the same parcel.
    for old in prior_closing or []:
        if not int(old.get('ending') or 0):continue
        key='carry:'+str(old.get('source_key') or hashlib.sha256(str(old).encode()).hexdigest()[:24])
        item={'source_key':key,'ledger_row_id':None,'kind':old['kind'],'description':old.get('description','전기 선급비용 이월'),'identifier':old.get('identifier',''),'site':old.get('site',''),'counterparty':old.get('counterparty',''),'amount':0,'start':'','end':'','opening':int(old['ending']),'note':'전년도 자동이월','valid':True};item.update(overrides.get(key,{}));result.append(calculate(item,year));seen.add(key)
    return result
def summary(items):
    out={k:{'opening':0,'amount':0,'ending':0,'current_expense':0} for k in ['보험료(원가)','보험료(판관비)','지급임차료(원가)']}
    for r in items:
        z=out[r['kind']]
        for key in z:z[key]+=int(r.get(key) or 0)
    return out
def grouped(items):
    groups={}
    for r in items:
        key=(r['kind'],r.get('identifier',''))
        if key not in groups:groups[key]={**r,'contract_count':0,'source_keys':[],'descriptions':[],'starts':[],'ends':[],'opening':0,'amount':0,'ending':0,'current_expense':0,'combined':0,'valid':True}
        g=groups[key];g['contract_count']+=int(bool(r.get('amount')));g['source_keys'].append(r['source_key']);g['descriptions'].append(r.get('description',''))
        if r.get('start'):g['starts'].append(r['start'])
        if r.get('end'):g['ends'].append(r['end'])
        for field in ['opening','amount','ending','current_expense','combined']:g[field]+=int(r.get(field) or 0)
        g['valid']=g['valid'] and bool(r.get('valid'))
    out=[]
    for g in groups.values():
        same_period=len(set(g['starts']))<=1 and len(set(g['ends']))<=1
        g['start']=g['starts'][0] if g['starts'] and same_period else '개별계산'
        g['end']=g['ends'][0] if g['ends'] and same_period else '개별계산'
        g['total_days']=g.get('total_days',0) if g['contract_count']==1 else 0
        g['prepaid_start']=g.get('prepaid_start','') if g['contract_count']==1 else '개별계산'
        g['prepaid_end']=g.get('prepaid_end','') if g['contract_count']==1 else '개별계산'
        g['prepaid_days']=g.get('prepaid_days',0) if g['contract_count']==1 else 0
        out.append(g)
    return out
