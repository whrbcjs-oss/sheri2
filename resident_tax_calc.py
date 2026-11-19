"""Decimal-based resident business tax and corporate allocation worksheets."""
from decimal import Decimal, InvalidOperation, ROUND_DOWN
from datetime import date
import re

SOURCES=[('서울특별시 주민세 안내','https://news.seoul.go.kr/gov/archives/200096'),('정부민원안내 주민세 안내','https://www.110.go.kr/data/counselView.do?curPage=46&num=A01_660147&scCate1=&scCate2=&scIntt=&scText=&scType='),('법인지방소득세 안분 세부기준','https://law.go.kr/LSW/lsLinkCommonInfo.do?lspttninfSeq=138312')]
KINDS=['본사','지점','공장','현장사무실','기타']
def dec(v):
    try:
        x=Decimal(str(v if v not in [None,''] else 0).replace(',',''))
        if not x.is_finite():raise ValueError('숫자를 확인하세요.')
        return x
    except (InvalidOperation,TypeError):raise ValueError('숫자를 확인하세요: '+str(v))
def num(v):return float(dec(v))
def nonnegative(v):
    x=dec(v)
    if x<0:raise ValueError('면적·금액·인원은 음수일 수 없습니다.')
    return x
def basic(capital):
    v=nonnegative(capital)
    return 50000 if v<=3000000000 else 100000 if v<=5000000000 else 200000
def jurisdiction(address):
    parts=str(address).split()
    if not parts:return ''
    # Suggest only; municipalities with administrative wards require reviewer confirmation.
    out=[parts[0]]
    for p in parts[1:4]:
        if p.endswith(('시','군','구')):out.append(p)
        else:break
    return ' '.join(out) if len(out)>1 or parts[0].startswith('세종') else ''
def area(rows):
    total=taxable=Decimal(0)
    for r in rows:
        a=nonnegative(r.get('area',0));t=nonnegative(r.get('taxable',0))
        if t>a:raise ValueError('과세면적은 사용면적을 초과할 수 없습니다.')
        total+=a;taxable+=t
    return dict(total=float(total),taxable=float(taxable),excluded=float(total-taxable))
def present(b,year):
    cutoff=f'{int(year)}-07-01'
    if b.get('start') and b['start']>cutoff:return False
    if b.get('demolished') and b['demolished']<cutoff:return False
    if b.get('presence')=='미존치':return False
    return True if b.get('presence')=='존치 확인' else None

def tax(area_value,base,rate,education,reduce_base=0,reduce_area=0,reduce_education=0,floor_area=True):
    a=nonnegative(area_value);base=nonnegative(base);rate=nonnegative(rate);edu=nonnegative(education)
    if edu>100:raise ValueError('지방교육세율을 확인하세요.')
    measure=a.to_integral_value(rounding=ROUND_DOWN) if floor_area else a
    raw_area=(measure*rate).to_integral_value(rounding=ROUND_DOWN) if a>330 else Decimal(0)
    raw_edu=(base*edu/100).to_integral_value(rounding=ROUND_DOWN)
    reductions=[nonnegative(x) for x in [reduce_base,reduce_area,reduce_education]]
    raw=[base,raw_area,raw_edu]
    if any(r>v for r,v in zip(reductions,raw)):raise ValueError('감면세액은 산출세액 이내로 입력하세요.')
    values=[int(v-r) for v,r in zip(raw,reductions)]
    return dict(base=values[0],area_tax=values[1],education_tax=values[2],total=sum(values),raw_base=int(base),raw_area=int(raw_area),raw_education=int(raw_edu))

def allocate(items,total):
    """Equal employee/area weights; explicit missing-input and zero-denominator errors."""
    if not items:raise ValueError('사업연도 말 사업장 자료를 입력하세요.')
    if len({x['site_id'] for x in items})!=len(items):raise ValueError('중복 사업장이 있습니다.')
    employee=sum((nonnegative(x['employees']) for x in items),Decimal(0));area_total=sum((nonnegative(x['area']) for x in items),Decimal(0));total=nonnegative(total)
    if employee==0 or area_total==0:raise ValueError('총 종업원 수 또는 안분면적이 0입니다. 특수 안분기준은 별도 검토가 필요합니다.')
    regions={}
    for x in items:
        if not str(x.get('jurisdiction','')).strip():raise ValueError('관할 지자체를 확인하세요.')
        v=regions.setdefault(x['jurisdiction'],dict(employees=Decimal(0),area=Decimal(0)))
        v['employees']+=nonnegative(x['employees']);v['area']+=nonnegative(x['area'])
    out=[]
    for region,v in sorted(regions.items()):
        ratio=(v['employees']/employee+v['area']/area_total)/2
        raw=total*ratio;amount=int(raw.to_integral_value(rounding=ROUND_DOWN))
        out.append(dict(jurisdiction=region,employees=float(v['employees']),area=float(v['area']),ratio=float(ratio),amount=amount,_fraction=raw-amount))
    remainder=int(total)-sum(x['amount'] for x in out)
    # Preserve total for a review worksheet, showing the one-won adjustment explicitly.
    order=sorted(range(len(out)),key=lambda i:(-out[i]['_fraction'],out[i]['jurisdiction']))
    for i,x in enumerate(out):x['adjustment']=1 if i in order[:remainder] else 0;x['amount']+=x['adjustment'];del x['_fraction']
    return out
