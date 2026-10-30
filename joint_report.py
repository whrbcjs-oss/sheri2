"""Excel-style settlement and official-letter layouts; all user content is escaped."""
from html import escape
from decimal import Decimal, ROUND_HALF_UP
import json
from joint_store import num, EXCLUSIONS


def esc(v):return escape(str(v if v is not None else ''))
def money(v):return f'{num(v).quantize(Decimal("1"),rounding=ROUND_HALF_UP):,}'
def amount(v):
    n=num(v)
    return '<span class="negative">'+esc(money(n))+'</span>' if n<0 else (esc(money(n)) if n else '−')
def td(value='',numeric=False,**attrs):
    attributes=''.join(' '+k+'="'+esc(v)+'"' for k,v in attrs.items())
    return '<td'+attributes+'>'+(amount(value) if numeric else esc(value))+'</td>'
def short_date(value):
    value=str(value or '')
    return value[2:].replace('-','.') if len(value)==10 and value[4]=='-' else value

def numeric_cells(values):return ''.join(td(v,True) for v in values)
def table(headers,records):
    return '<table><thead><tr>'+''.join('<th>'+esc(x)+'</th>' for x in headers)+'</tr></thead><tbody>'+''.join('<tr>'+''.join(td(x) for x in row)+'</tr>' for row in records)+'</tbody></table>'


def period_label(start,end):
    if start==end:return start[:4]+'년 '+start[5:]+'월'
    if start[:4]==end[:4]:return start[:4]+'년 '+start[5:]+'~'+end[5:]+'월'
    return start[:4]+'년 '+start[5:]+'월 ~ '+end[:4]+'년 '+end[5:]+'월'


def monthly_claims(d):
    m=d['member'];p=d['project'];monthly={}
    for x in d['allocations']:
        if x['member_id']==m['id']:
            v=monthly.setdefault(x['allocation_month'],[num(0),num(0),num(0)])
            v[0]+=num(x['base']);v[1]+=num(x['vat'])
    if m['company_id']!=p['owner_id']:
        for x in d['allocations']:
            if x['investing_company']==m['company_id']:
                monthly.setdefault(x['allocation_month'],[num(0),num(0),num(0)])[2]+=num(x['original_base'])
    return sorted(monthly.items())


def settlement_body(d,meta,number,issued):
    p,m,a=d['project'],d['member'],d['amounts'];entries=d['entries']
    progress=[e for e in entries if e['kind']=='progress'];recoveries=[e for e in entries if e['kind']=='recovery'];subs=[e for e in entries if e['kind']=='subcontract'];claims=monthly_claims(d)
    fee_label='관리비 ('+m['fee_rate']+'%)' if m['fee_enabled'] else '관리비 (미적용)'
    body='<section class="settlement-sheet"><div class="sheet-heading"><h1>■ 공동도급 공사원가 정산내역 · '+esc(m['name'])+' <span>'+esc(m['share'])+'%</span></h1><div>'+esc(p['name'])+'</div></div>'
    body+='<div class="sheet-meta"><span>대상 기간: '+esc(d['start'])+' ~ '+esc(d['end'])+'</span><span>문서번호: '+esc(number)+'　발행일: '+esc(issued)+'　[단위: 원]</span></div>'
    body+='<div class="sheet-scroll"><table id="settlement-grid" class="settlement-grid"><colgroup>'
    widths=[4.2,4.4,6.1,4.5,6.2,4.5,4.5,4.5,5.8,4.2,4.1,6.1,4.5,4.8,6.1,4.2,6.1,4.5,6.1,6.1,6.8]
    body+=''.join('<col style="width:'+str(w/sum(widths)*100)+'%">' for w in widths)+'</colgroup>'
    body+='<thead><tr><th colspan="5">공사대금 수령</th><th colspan="4">공 제 내 역</th><th colspan="6">원가분담금 청구내역</th><th colspan="4">회 수 내 역</th><th rowspan="2">미회수액<br>(①−②+③−④−⑤)</th><th rowspan="2">비 고</th></tr><tr>'
    body+=''.join('<th>'+esc(x).replace('\n','<br>')+'</th>' for x in ['수령일자','구분','공급가액\n①','VAT','계',fee_label,'산재보험','고용보험','공제계\n②','청구연월','구분','공급가액','VAT\n③','회원사투입\n④','계','회수일자','공급가액','VAT','회수액\n⑤'])+'</tr></thead><tbody>'
    for i in range(max(14,len(progress),len(claims),len(recoveries))):
        row=''
        if i<len(progress):
            e=progress[i];v=e['data'];fee=num(v['fee']) if m['fee_enabled'] else num(0);industrial=num(v['산재보험']);employment=num(v['고용보험'])
            row+=td(short_date(e['entry_date']))+td(v.get('label',''))+numeric_cells([v['supply'],v['vat'],num(v['supply'])+num(v['vat']),fee,industrial,employment,fee+industrial+employment])
        else:row+='<td></td>'*9
        if i<len(claims):
            month,v=claims[i];row+=td(month)+td(str(int(month[-2:]))+'월분')+numeric_cells(v+[v[0]+v[1]-v[2]])
        else:row+='<td></td>'*6
        if i<len(recoveries):
            e=recoveries[i];v=e['data'];row+=td(short_date(e['entry_date']))+numeric_cells([v['supply'],v['vat'],num(v['supply'])+num(v['vat'])]);note=v.get('note','')
        else:row+='<td></td>'*4;note=''
        body+='<tr class="data-row">'+row+td('')+td(note,**{'class':'text-note'})+'</tr>'
    base=num(a['base']);vat=num(a['vat']);invested=num(a['invested']);sub=num(a['subcontract']);subvat=num(a['subcontract_vat']);paid_supply=sum((num(e['data']['paid_supply']) for e in subs),num(0));paid_vat=sum((num(e['data']['paid_vat']) for e in subs),num(0));rs=sum((num(e['data']['supply']) for e in recoveries),num(0));rv=sum((num(e['data']['vat']) for e in recoveries),num(0))
    body+='<tr class="subtotal">'+td('',colspan='9')+td('소계(원가분담금)',colspan='2')+numeric_cells([base,vat,invested,base+vat-invested])+td('')+numeric_cells([rs,rv,rs+rv])+td('')+td('')+'</tr>'
    body+='<tr class="subtotal">'+td('',colspan='9')+td('소계(하도급대금)',colspan='2')+numeric_cells([sub,subvat,0,sub+subvat])+td('')+numeric_cells([paid_supply,paid_vat,paid_supply+paid_vat])+td('')+td('')+'</tr>'
    receipt_vat=sum((num(e['data']['vat']) for e in progress),num(0))
    body+='<tr class="grand-total">'+td('합 계',colspan='2')+numeric_cells([a['received'],receipt_vat,num(a['received'])+receipt_vat,a['fee'],a['industrial'],a['employment'],a['deductions']])+td('합 계',colspan='2')+numeric_cells([base+sub,vat+subvat,invested,a['claim']])+td('합 계')+numeric_cells([rs+paid_supply,rv+paid_vat,a['recovery'],a['remaining']])+td('')+'</tr></tbody></table></div>'
    rule='① − ② + ③ − ④ − ⑤' if m['fee_enabled'] else '청구내역 계 − 회수액 계'
    body+='<div class="sheet-bottom"><span>미회수액 산식: '+esc(rule)+'</span><span>청구연월은 원장의 배분월 기준입니다. 각 영역은 독립된 내역이며 같은 행이 동일 거래를 의미하지 않습니다.</span></div></section>'
    # Supporting sheet 2 follows the supplied horizontal milestone layout.
    body+='<section class="support-sheet"><h2>■ 관리비 산출내역 · '+esc(m['name'])+'</h2><div class="sheet-scroll"><table id="management-grid"><thead><tr><th>구분</th>'
    slots=progress or [None]
    body+=''.join('<th>'+esc(e['data'].get('label') or e['entry_date'] if e else '기성 입력 전')+'</th>' for e in slots)+'<th>소계</th></tr></thead><tbody>'
    lines=[('공급가액',lambda v:num(v['supply']))]+[(k,lambda v,k=k:num(v[k])) for k in EXCLUSIONS]+[('제외분 합계',lambda v:sum((num(v[k]) for k in EXCLUSIONS),num(0))),('관리대상액',lambda v:num(v['supply'])-sum((num(v[k]) for k in EXCLUSIONS),num(0))),('관리비',lambda v:num(v['fee']) if m['fee_enabled'] else num(0))]
    for label,fn in lines:
        if label=='관리비':
            body+='<tr>'+td('비율')+''.join(td((e['data']['fee_rate']+'%') if e and m['fee_enabled'] else '미적용') for e in slots)+td('')+'</tr>'
        values=[fn(e['data']) if e else num(0) for e in slots]
        body+='<tr class="'+('subtotal' if label in ['제외분 합계','관리대상액','관리비'] else '')+'">'+td(label)+numeric_cells(values+[sum(values,num(0))])+'</tr>'
    body+='</tbody></table></div><p class="sheet-bottom">보험료·제외항목은 회원사분 입력액입니다. 관리비는 기성별 원 미만 버림을 적용합니다.</p></section>'
    # Supporting sheet 3 mirrors the claim/payment columns of the original.
    body+='<section class="support-sheet"><h2>■ 하도급 청구 및 지급현황 ['+esc(m['name'])+']</h2><div class="sheet-scroll"><table id="subcontract-grid"><thead><tr>'
    headers=['청구년월','업체명','공급가액','VAT','합계금액','지급일자','공급가액','VAT','지급액','미지급액','공종명','지급방식']
    body+=''.join('<th>'+esc(x)+'</th>' for x in headers)+'</tr></thead><tbody>'
    for i in range(max(10,len(subs))):
        if i>=len(subs):body+='<tr class="data-row">'+'<td></td>'*12+'</tr>';continue
        e=subs[i];v=e['data'];pay=num(v['paid_supply'])+num(v['paid_vat']);claim=num(v['supply'])+num(v['vat']);method=v.get('method','')
        body+='<tr>'+td(short_date(e['entry_date']))+td(v.get('vendor',''))+numeric_cells([v['supply'],v['vat'],claim])+td(short_date(v.get('paid_date','')))+numeric_cells([v['paid_supply'],v['paid_vat'],pay,claim-pay])+td(v.get('work_type',''))+td(method)+'</tr>'
    body+='<tr class="grand-total">'+td('합 계',colspan='2')+numeric_cells([sub,subvat,sub+subvat])+td('')+numeric_cells([paid_supply,paid_vat,paid_supply+paid_vat,sub+subvat-paid_supply-paid_vat])+td('')+td('')+'</tr></tbody></table></div></section>'
    return body


def letter_body(d,meta,number,issued,owner,info):
    m,p,a=d['member'],d['project'],d['amounts'];title=meta.get('title') or period_label(d['start'],d['end'])+' 공동원가 안분정산 및 자금청구의 건'
    contacts=' '.join(str(info.get(k,'')) for k in ['직급','담당자','직급2','담당자2']).strip()
    body='<article class="official-letter"><h1 class="letter-company">'+esc(owner['name'])+'</h1><div class="letter-address">발신 : '+esc(info.get('주소',''))+' / 전화 '+esc(info.get('전화',''))+' / FAX '+esc(info.get('팩스',''))+'<br><span>담당자 : '+esc(contacts)+'</span></div>'
    body+='<div class="letter-top"><dl class="letter-fields">'
    for label,value in [('문서번호',number),('발신일자',str(issued).replace('-','.')),('수 신',m['name']),('참 조',meta.get('reference','공동도급 담당자')),('제 목',title)]:body+='<div><dt>'+esc(label)+' :</dt><dd>'+esc(value)+'</dd></div>'
    body+='</dl><table class="processing-box" aria-label="접수 및 처리란"><tr><th rowspan="2">접<br>수</th><th>일자</th><td></td></tr><tr><th>번호</th><td></td></tr><tr><th>처리과</th><td colspan="2"></td></tr><tr><th>담당자</th><td colspan="2"></td></tr><tr><th>결재</th><td colspan="2"></td></tr></table></div>'
    body+='<div class="letter-paragraphs"><p>1. 귀사의 무궁한 발전을 기원합니다.</p><p>2. 귀사와 공동도급으로 시공중인 「'+esc(p['name'])+'」의 현장에서 투자한 공사원가에 대하여 정산내역을 송부하오니, 업무에 참조하여 주시기 바랍니다.</p>'
    if meta.get('body'):body+='<p class="custom-body">'+esc(meta['body'])+'</p>'
    body+='</div><div class="letter-table-wrap"><table id="letter-amounts"><thead><tr><th rowspan="2">구 분</th><th rowspan="2">당월<br>총공사원가</th>'
    parties=d.get('parties') or [dict(name=m['name'],share=m['share'],**{k:a[k] for k in ['base','vat','invested','arrears','interest']})]
    columns='<colgroup><col style="width:26%"><col style="width:17%">'+''.join('<col style="width:'+str(48/len(parties))+'%">' for _ in parties)+'<col style="width:9%"></colgroup>'
    body=body.replace('<table id="letter-amounts">','<table id="letter-amounts">'+columns,1)
    body+=''.join('<th>'+esc(x['name'])+'</th>' for x in parties)+'<th rowspan="2">비 고</th></tr><tr>'+''.join('<th>'+esc(x['share'])+'%</th>' for x in parties)+'</tr></thead><tbody>'
    for label,fn in [('원가투입액 (①)',lambda x:num(x['base'])),('부가가치세 (②)',lambda x:num(x['vat'])),('합 계 (③, ①+②)',lambda x:num(x['base'])+num(x['vat'])),('공제액 (④)',lambda x:num(x['invested'])),('전월 미수액 (⑤)',lambda x:num(x['arrears'])),('지연이자 (⑥)',lambda x:num(x['interest'])),('금월청구액 (⑦, ③−④+⑤+⑥)',lambda x:num(x['base'])+num(x['vat'])-num(x['invested'])+num(x['arrears'])+num(x['interest']))]:
        values=[fn(x) for x in parties]
        body+='<tr class="'+('letter-claim' if label.startswith('금월') else '')+'">'+td(label)+numeric_cells([sum(values,num(0))]+values)+td('')+'</tr>'
    body+='</tbody></table></div><div class="letter-tail">'
    if meta.get('due'):body+='<p>'+esc(meta['due'])+'까지 아래의 예금계좌로 입금하여 주시기 바랍니다.</p>'
    body+='<p class="bank">※ 입금계좌 : '+esc(meta.get('bank',info.get('입금계좌','')))+'</p><div class="attachments"><span># 첨 부 :</span><div>'
    attachments=meta.get('attachments') or '공동원가 투입 및 배분내역서 1부, 현장별 원장 1부'
    for i,x in enumerate(attachments.replace('\n',',').split(','),1):
        if x.strip():body+='<div>'+esc(str(i)+'. '+x.strip())+'</div>'
    body+='끝.</div></div></div><div class="letter-signature"><div>'+esc(owner['name'])+'</div><div>대표이사　'+esc(info.get('대표자',''))+'</div>'
    # Only an explicitly selected PNG/JPEG data URL is embedded, never arbitrary markup.
    seal=meta.get('seal','')
    if isinstance(seal,str) and len(seal)<1500000 and seal.startswith(('data:image/png;base64,','data:image/jpeg;base64,')):
        import re
        if re.fullmatch(r'data:image/(?:png|jpeg);base64,[A-Za-z0-9+/=]+',seal):body+='<img class="seal" alt="선택한 직인" src="'+esc(seal)+'">'
    return body+'</div></article>'


CSS='''
*{box-sizing:border-box}body{margin:0;color:#111;font-family:"Malgun Gothic","Noto Sans CJK KR",Arial,sans-serif;background:#edf0f2;font-size:14px;line-height:1.5}.tools{display:flex;justify-content:space-between;align-items:center;padding:12px 20px;background:white;border-bottom:1px solid #d8dde1;gap:12px}.tools button{padding:9px 18px;background:#009f57;color:white;border:0;border-radius:5px;font:inherit;cursor:pointer}.status{color:#65717b;font-size:13px}.document{background:white;margin:18px auto;padding:24px;max-width:2400px}.sheet-heading{display:flex;justify-content:space-between;align-items:baseline;gap:15px;border-bottom:1px solid #111;padding-bottom:5px;min-width:900px}.sheet-heading h1{font-size:20px;margin:0}.sheet-heading h1 span{color:#225b91}.sheet-heading>div{font-size:18px;font-weight:600}.sheet-meta{display:flex;justify-content:space-between;gap:20px;font-size:12px;margin:6px 0}.sheet-scroll{overflow-x:auto}table{width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums;font-size:14px}th,td{border:1px solid #333;padding:5px 6px;text-align:right;vertical-align:middle}th{font-weight:600;text-align:center;background:white;line-height:1.35}td{white-space:nowrap}.negative{color:#c42121}.settlement-grid{min-width:2100px;table-layout:fixed}.settlement-grid th{font-size:13px}.settlement-grid td{padding:5px 3px;border-bottom-style:dotted}.settlement-grid .data-row td:nth-child(1),.settlement-grid .data-row td:nth-child(2),.settlement-grid .data-row td:nth-child(10),.settlement-grid .data-row td:nth-child(11),.settlement-grid .data-row td:nth-child(16){text-align:center}.settlement-grid .text-note{white-space:normal;font-size:12px}.data-row{height:28px}.data-row:nth-child(odd){background:#eef7fb}.subtotal{background:#f3f3ef;font-weight:650}.grand-total{font-weight:700;border-top:2px solid black}.grand-total td{border-bottom-style:solid}.sheet-bottom{font-size:12px;display:flex;justify-content:space-between;gap:20px;margin:7px 0 0;color:#4d555b}.support-sheet{margin-top:36px;border-top:1px solid #c5c9cc;padding-top:20px}.support-sheet h2{font-size:18px;margin:0 0 10px}.support-sheet td:first-child{text-align:left}.support-sheet #management-grid{min-width:850px}.support-sheet #subcontract-grid{min-width:1250px}.document-letter{max-width:210mm;padding:14mm 14mm 12mm;box-shadow:0 2px 8px #0001}.official-letter{font-family:Batang,"바탕","Noto Serif CJK KR","Malgun Gothic",serif;font-size:15px;line-height:1.8}.letter-company{text-align:center;font-size:30px;letter-spacing:5px;margin:0 0 15px;font-weight:700}.letter-address{font-family:"Malgun Gothic",sans-serif;font-size:11px;line-height:1.6;border-bottom:2px solid #111;padding-bottom:9px}.letter-address span{display:block;text-align:right}.letter-top{position:relative;min-height:160px;margin:22px 0}.letter-fields{margin:0;padding-right:138px}.letter-fields>div{display:flex;gap:5px;margin:5px 0}.letter-fields dt{flex:0 0 75px;white-space:pre;text-align:justify}.letter-fields dd{margin:0;overflow-wrap:anywhere}.letter-fields>div:last-child{padding-top:4px}.processing-box{position:absolute;right:0;top:0;width:124px;font-family:"Malgun Gothic",sans-serif;font-size:10px}.processing-box{table-layout:fixed;border:1px solid #111;outline:1px solid #111;outline-offset:-1px}.processing-box th,.processing-box td{padding:3px;height:22px}.processing-box th{width:33px}.processing-box td{min-width:0}.letter-paragraphs{margin:20px 0 22px}.letter-paragraphs p{margin:12px 0;text-align:justify}.custom-body{white-space:pre-wrap}.letter-table-wrap{margin:20px 0 26px}#letter-amounts{outline:1px solid #111;outline-offset:-1px;border:1px solid #111;max-width:100%;font-family:"Malgun Gothic",sans-serif;font-size:12px;table-layout:fixed}#letter-amounts th,#letter-amounts td{padding:7px 4px}#letter-amounts th:first-child{width:26%}#letter-amounts th:last-child{width:9%}#letter-amounts td:first-child{white-space:normal;text-align:left}#letter-amounts td{overflow-wrap:anywhere;white-space:normal}#letter-amounts .letter-claim{font-weight:700;border-top:2px solid black}.letter-tail{font-size:14px}.bank{margin:15px 0 18px}.attachments{display:flex;gap:12px;margin:12px 0}.attachments>span{white-space:nowrap}.letter-signature{position:relative;text-align:center;margin:30px auto 0;font-size:23px;line-height:1.8;letter-spacing:4px;font-weight:600;min-height:85px}.seal{position:absolute;width:24mm;height:24mm;object-fit:contain;right:6%;bottom:0}h1,h2{break-after:avoid}tr{break-inside:avoid}
@media(max-width:900px){.document{padding:14px}.document-letter{margin:12px;min-width:700px}.sheet-heading{min-width:800px}.sheet-meta{flex-wrap:wrap}.sheet-bottom{flex-wrap:wrap}}
@media print{body{background:white;margin:0}.tools{display:none!important}.document{margin:0;padding:0;max-width:none;box-shadow:none}.sheet-scroll{overflow:visible}.sheet-heading{min-width:0}.sheet-heading h1{font-size:15pt}.sheet-heading>div{font-size:12pt}.sheet-meta{font-size:9pt}.settlement-grid{min-width:0;width:100%;font-size:10pt}.settlement-grid th{font-size:9pt}.settlement-grid td{padding:4px 2px;line-height:1.25}.settlement-grid .text-note{font-size:9pt}.data-row{height:7mm}.sheet-bottom{font-size:8pt}.support-sheet{break-before:page;border:0;margin:0;padding:0}.support-sheet table{font-size:10pt}.support-sheet #management-grid,.support-sheet #subcontract-grid{min-width:0}.support-sheet th,.support-sheet td{padding:4px}.document-letter{width:auto;min-width:0;max-width:none;padding:0;margin:0}.official-letter{font-size:11pt;line-height:1.65}.letter-company{font-size:23pt;margin-bottom:10px}.letter-address{font-size:9pt}.letter-top{margin:16px 0;min-height:135px}.letter-fields>div{margin:4px 0}.letter-paragraphs{margin:14px 0 18px}.letter-paragraphs p{margin:9px 0}.letter-table-wrap{margin:16px 0 20px}#letter-amounts{font-size:9pt}#letter-amounts th,#letter-amounts td{padding:6px 4px}.letter-tail{font-size:10pt}.letter-signature{font-size:17pt;margin-top:22px;min-height:75px}td,th,.data-row,.subtotal{print-color-adjust:exact;-webkit-print-color-adjust:exact}}
'''


def render(d,kind='정산서',meta=None):
    meta=meta or d.get('meta',{});co={x['id']:x for x in d['companies']};owner=co[d['project']['owner_id']];info=json.loads(owner['info']);issued=d.get('issued',meta.get('issued',''));number=d.get('number',meta.get('number','미확정'))
    letter=kind=='공문';body=letter_body(d,meta,number,issued,owner,info) if letter else settlement_body(d,meta,number,issued)
    status='확정 발행본' if 'snapshot_id' in d or d.get('number') else '미확정 미리보기'
    page='A4 portrait' if letter else 'A3 landscape'
    return '<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>'+esc(kind)+'</title><style>'+CSS+'@page{size:'+page+';margin:12mm}</style></head><body><div class="tools"><span class="status">'+esc(status)+' · 금액 단위: 원</span><button onclick="window.print()">인쇄 / PDF 저장</button></div><main class="document '+('document-letter' if letter else 'document-settlement')+'">'+body+'</main></body></html>'
