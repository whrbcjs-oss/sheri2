"""Print layouts using the existing joint ledger's table and official-letter styling."""
import json
from joint_report import CSS,esc,td,numeric_cells,money
from joint_member import totals
from joint_store import num

def grid(headers,rows):
    return '<table><thead><tr>'+''.join('<th>'+esc(h)+'</th>' for h in headers)+'</tr></thead><tbody>'+''.join('<tr>'+''.join(td(v,i>0) for i,v in enumerate(row))+'</tr>' for row in rows)+'</tbody></table>'

def ledger(d):
    groups=[[x for x in d['records'] if x['kind']==kind] for kind in ['receipt','claim','payment']]
    body='<section class="support-sheet"><h2>■ 공동도급 공사원가 정산내역 · '+esc(d['project']['name'])+'</h2><table class="member-ledger"><thead><tr><th colspan="5">공사대금 수금</th><th colspan="7">원가분담 접수내역</th><th colspan="4">대표사 지급내역</th></tr><tr>'
    body+=''.join('<th>'+x+'</th>' for x in ['수금일','구분','공급가액','VAT','계','접수일','구분','공급가액','VAT','당사투입','하도급직불','차인액','지급일','공급가액','VAT','지급액'])+'</tr></thead><tbody>'
    for i in range(max(8,*[len(g) for g in groups])):
        body+='<tr>'
        for kind,g,width in zip(['receipt','claim','payment'],groups,[5,7,4]):
            if i>=len(g):body+='<td></td>'*width;continue
            x=g[i];v=x['data'];base=num(v.get('supply',0));vat=num(v.get('vat',0))
            body+=td(x['entry_date'])
            if kind!='payment':body+=td(x['label'])
            body+=numeric_cells([base,vat])
            if kind=='claim':
                invested=num(v.get('invested',0));sub=num(v.get('subcontract',0));body+=numeric_cells([invested,sub,base+vat-invested-sub])
            else:body+=numeric_cells([base+vat])
        body+='</tr>'
    r,q,p=[totals(g) for g in groups]
    body+='<tr class="grand-total">'+td('합계',colspan='2')+numeric_cells([r['supply'],r['vat'],r['supply']+r['vat']])+td('합계',colspan='2')+numeric_cells([q['supply'],q['vat'],q['invested'],q['subcontract'],q['supply']+q['vat']-q['invested']-q['subcontract']])+td('합계')+numeric_cells([p['supply'],p['vat'],p['supply']+p['vat']])+'</tr></tbody></table><p>각 영역은 독립된 내역이며 같은 행이 같은 거래를 뜻하지 않습니다.</p></section>'
    return body


def render(d):
    notice=d['kind']=='notice';title='공동원가 투입내역 통보' if notice else '실행내역검토서 · 대표사 지급 결재'
    p=d['project'];owner=d['owner'];rep=d['representative'];es=d['records']
    body='<h1>'+esc(owner['name'] if notice else title)+'</h1><p>문서번호: '+esc(d['number'])+'　작성일: '+esc(d['issued'])+'</p>'
    if notice:
        info=json.loads(owner.get('info','{}'))
        body+='<p>'+esc(info.get('주소',''))+'　전화 '+esc(info.get('전화',''))+'　FAX '+esc(info.get('팩스',''))+'</p>'
        body+='<p>수신: '+esc(rep['name'])+'　귀중</p><p>제목: '+title+'</p><p>공사명: '+esc(p['name'])+'</p><p>아래 당사 공동원가 투입내역을 통보하오니 원가배분 시 반영하여 주시기 바랍니다.</p>'
        v=totals(es);body+=grid(['구분','공급가액','VAT','합계'],[['당사 투입비',v['supply'],v['vat'],v['supply']+v['vat']]])
    else:
        body+='<table class="approval"><tr><th>결재</th><th>담당</th><th>차장</th><th>부장</th><th>상무</th><th>대표이사</th></tr><tr><td>서명</td>'+''.join('<td style="height:55px"></td>' for _ in range(5))+'</tr></table>'
        body+='<p>공사명: '+esc(p['name'])+'</p><p>당사: '+esc(owner['name'])+'　지급처(대표사): '+esc(rep['name'])+'</p><p>정산명: '+esc(d['settings'].get('name',''))+'　방식: '+esc(d['settings']['mode'])+'</p>'
        a=d['amounts'];labels=[('기성 공급가액','received'),('관리비 계산 제외액','excluded'),('관리비 계산 대상액','fee_base'),('관리비','fee'),('보험료 공제','insurance'),('접수 원가 공급가액','base'),('접수 매입 VAT','vat'),('반영 당사 투입비','invested'),('반영 하도급 직불','subcontract'),('접수 원가 차인액','claim'),('기지급액','paid'),('전회 잔액·기타 조정','adjustment'),('정산금 단수 조정','rounding_difference'),('정산 지급예정액','remaining')]
        body+=grid(['정산 항목','금액(원)'],[(label,a[key]) for label,key in labels])
        rule='기성 공급가액 − 관리비 − 보험료 + 접수 VAT − 반영 당사 투입비 − 반영 직불 − 기지급액 + 조정액' if d['settings']['mode']=='관리비 정산형' else '접수 원가 공급가액 + VAT − 반영 당사 투입비 − 반영 직불 − 기지급액 + 조정액'
        body+='<p>산식: '+esc(rule)+'</p><p>관리비율: '+esc(d['settings']['rate'])+'% · 단수처리: '+esc(d['settings']['rounding'])+'</p><p>양수는 당사 → 대표사 지급, 음수는 대표사에서 받을 정산금입니다. 수금 VAT는 별도 표시하며 정산 산식에 중복 가산하지 않습니다.</p>'
        body+=ledger(d)
        body+='<section class="support-sheet"><h2>관리대장 정산 근거 내역</h2>'
    headers=['일자','귀속월','구분','내역','공급가액','VAT','합계'] if notice else ['일자','귀속월','구분','내역','공급가액','VAT','반영 당사 투입비','반영 하도급 직불']
    body+='<table><thead><tr>'+''.join('<th>'+x+'</th>' for x in headers)+'</tr></thead><tbody>'
    from joint_member import KINDS
    for e in es:
        v=e['data'];body+='<tr>'+''.join(td(x) for x in [e['entry_date'],e['month'],v.get('category','기타') if notice else KINDS[e['kind']],e['label']])
        body+=numeric_cells([v.get('supply',0),v.get('vat',0),num(v.get('supply',0))+num(v.get('vat',0))] if notice else [v.get(k,0) for k in ['supply','vat','invested','subcontract']])+'</tr>'
    body+='</tbody></table>'
    if not notice:body+='</section>'
    else:body+='<p>첨부: 공동원가 투입내역 1부.</p><h2 style="text-align:right;margin-top:35px">'+esc(owner['name'])+'　대표이사 '+esc(info.get('대표자명',''))+'</h2>'
    body+='<p>비고: '+esc(d['settings'].get('note',''))+'</p>'
    return '<!doctype html><html lang="ko"><head><meta charset="utf-8"><title>'+esc(title)+'</title><style>'+CSS+'@page{size:A4 '+('portrait' if notice else 'landscape')+';margin:12mm}table{width:100%;table-layout:auto}.member-ledger{font-size:9px}.member-ledger th,.member-ledger td{padding:4px 3px}td{white-space:normal}h1{font-size:23px}.approval{width:65%;margin-left:auto} .support-sheet{break-before:page}</style></head><body><div class="tools"><button onclick="window.print()">인쇄 / PDF 저장</button><span> 저장된 출력본 · 금액 단위: 원</span></div><main class="document">'+body+'</main></body></html>'
