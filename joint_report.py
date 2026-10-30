"""Self-contained printable reports. User content is escaped, never executable."""
from html import escape
from decimal import Decimal,ROUND_HALF_UP
import json
from joint_store import num,EXCLUSIONS

def esc(v):return escape(str(v or ''))
def money(v):return f'{num(v).quantize(Decimal("1"),rounding=ROUND_HALF_UP):,}'
def table(headers,records):
    return '<table><thead><tr>'+''.join('<th>'+esc(x)+'</th>' for x in headers)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+esc(x)+'</td>' for x in row)+'</tr>' for row in records)+'</tbody></table>'

def render(d,kind='정산서',meta=None):
    meta=meta or d.get('meta',{});p=d['project'];m=d['member'];a=d['amounts'];co={x['id']:x for x in d['companies']};owner=co[p['owner_id']];info=json.loads(owner['info']);issued=d.get('issued',meta.get('issued',''));number=d.get('number',meta.get('number','미확정'))
    if kind=='공문':
        title=meta.get('title') or f"{d['start']} ~ {d['end']} 공동원가 안분정산 및 자금청구의 건"
        body=f'<header><h1>{esc(owner["name"])}</h1><p>{esc(info.get("주소"))} · 전화 {esc(info.get("전화"))} · 팩스 {esc(info.get("팩스"))}</p><p>담당자: {esc(info.get("담당자"))}</p></header>'
        body+=table(['문서번호','발신일자','수신','참조'],[[number,issued,m['name'],meta.get('reference','공동도급 담당자')]])
        body+=f'<h2>{esc(title)}</h2><p>1. 귀사의 무궁한 발전을 기원합니다.</p><p>2. 귀사와 공동도급으로 시공 중인 「{esc(p["name"])}」의 공동원가 정산 및 청구 내역을 아래와 같이 알려드립니다.</p><p>{esc(meta.get("body",""))}</p>'
        parties=d.get('parties',[])
        if not parties:parties=[dict(name=m['name'],share=m['share'],**{k:a[k] for k in ['base','vat','invested','arrears','interest']})]
        records=[]
        for label,fn in [('원가투입액 ①',lambda x:num(x['base'])),('부가가치세 ②',lambda x:num(x['vat'])),('합계 ③',lambda x:num(x['base'])+num(x['vat'])),('공제액(회원사투입) ④',lambda x:num(x['invested'])),('전월 미수액 ⑤',lambda x:num(x['arrears'])),('지연이자 ⑥',lambda x:num(x['interest'])),('금월청구액 ③−④+⑤+⑥',lambda x:num(x['base'])+num(x['vat'])-num(x['invested'])+num(x['arrears'])+num(x['interest']))]:
            values=[fn(x) for x in parties];records.append([label,money(sum(values))]+[money(x) for x in values])
        body+=table(['구분','전체']+[x['name']+' ('+x['share']+'%)' for x in parties],records)
        body+=f'<p>대상 기간: {esc(d["start"])} ~ {esc(d["end"])}</p><p>입금 요청기한: {esc(meta.get("due",""))}</p><p>입금계좌: {esc(meta.get("bank",info.get("입금계좌","")))}</p><p>첨부: {esc(meta.get("attachments","공동원가 투입 및 배분내역서 1부, 현장별 원장 1부"))}</p><h2 class="signature">{esc(owner["name"])} 대표이사 {esc(info.get("대표자"))}</h2>'
    else:
        body=f'<div class="approvals">담당　　　　　　　　　검토　　　　　　　　　승인<br><br><br></div><h1>공동도급 공사원가 정산내역</h1><h2>{esc(p["name"])}</h2><p>{esc(m["name"])} · 지분 {esc(m["share"])}% · {esc(d["start"])} ~ {esc(d["end"])}</p><p>문서번호: {esc(number)} · 발행일: {esc(issued)}</p>'
        body+=table(['공사대금 수령 공급가액','관리비','산재보험','고용보험','공제계'],[[money(a[k]) for k in ['received','fee','industrial','employment','deductions']]])
        body+='<h2>원가분담금 청구·회수 및 정산</h2>'+table(['구분','공급가액','VAT','회원사투입 차감','계'],[['원가분담금',money(a['base']),money(a['vat']),money(a['invested']),money(num(a['base'])+num(a['vat'])-num(a['invested']))],['하도급대금',money(a['subcontract']),money(a['subcontract_vat']),'—',money(num(a['subcontract'])+num(a['subcontract_vat']))],['청구 합계','','','',money(a['claim'])],['회수 합계(하도급 지급 포함)','','','',money(a['recovery'])],['미회수액','','','',money(a['remaining'])]])
        rule='공사대금 수령 공급가액 − 공제계 + 청구 VAT − 회수액 − 회원사투입액' if m['fee_enabled'] else '청구 합계 − 회수 합계'
        body+=f'<p>적용 산식: {esc(rule)}</p>'
        monthly={}
        for x in d['allocations']:
            if x['member_id']==m['id']:
                v=monthly.setdefault(x['allocation_month'],[num(0),num(0),num(0)])
                v[0]+=num(x['base']);v[1]+=num(x['vat'])
        if m['company_id']!=p['owner_id']:
            for x in d['allocations']:
                if x['investing_company']==m['company_id']:
                    monthly.setdefault(x['allocation_month'],[num(0),num(0),num(0)])[2]+=num(x['original_base'])
        body+='<h2>월별 원가분담금 청구내역</h2>'+table(['배분월','공급가액','VAT','회원사투입 차감','청구액'],[[month]+[money(x) for x in values]+[money(values[0]+values[1]-values[2])] for month,values in sorted(monthly.items())])
        for kind_,heading,headers,fn in [
            ('progress','기성별 관리비·공제내역',['기성','기간','수령 공급가액','수령 VAT','관리비율','관리비','산재','고용'],lambda e:[e['data'].get('label',''),e['period_start']+'~'+e['period_end'],money(e['data']['supply']),money(e['data']['vat']),e['data']['fee_rate']+'%',money(e['data']['fee']) if m['fee_enabled'] else '0',money(e['data']['산재보험']),money(e['data']['고용보험'])]),
            ('subcontract','하도급 청구·지급현황',['업체','청구일','청구 공급가액','청구 VAT','지급일','지급 공급가액','지급 VAT','미지급액','공종·방식'],lambda e:[e['data'].get('vendor',''),e['entry_date'],money(e['data']['supply']),money(e['data']['vat']),e['data'].get('paid_date',''),money(e['data']['paid_supply']),money(e['data']['paid_vat']),money(num(e['data']['supply'])+num(e['data']['vat'])-num(e['data']['paid_supply'])-num(e['data']['paid_vat'])),e['data'].get('method','')]),
            ('recovery','회수내역',['회수일','해당 기간','공급가액','VAT','합계','비고'],lambda e:[e['entry_date'],e['period_start']+'~'+e['period_end'],money(e['data']['supply']),money(e['data']['vat']),money(num(e['data']['supply'])+num(e['data']['vat'])),e['data'].get('note','')])]:
            body+='<h2>'+heading+'</h2>'+table(headers,[fn(e) for e in d['entries'] if e['kind']==kind_])
        progress=[e for e in d['entries'] if e['kind']=='progress']
        if progress:body+='<h2>관리비 제외항목 상세</h2>'+table(['항목']+[e['data'].get('label',e['entry_date']) for e in progress],[[x]+[money(e['data'][x]) for e in progress] for x in EXCLUSIONS])
    status='확정 발행본' if 'snapshot_id' in d or d.get('number') else '미확정 미리보기'
    return '''<!doctype html><html lang="ko"><meta charset="utf-8"><title>'''+esc(kind)+'''</title><style>
    *{box-sizing:border-box}body{font:15px/1.7 'Malgun Gothic',sans-serif;color:#20282e;margin:30px auto;max-width:1400px;padding:25px}h1{font-size:28px}h2{font-size:20px;margin-top:24px}header{text-align:center;border-bottom:2px solid #303840;padding-bottom:10px}table{width:100%;border-collapse:collapse;margin:15px 0;font-variant-numeric:tabular-nums}th,td{border:1px solid #ccd3d8;padding:9px;text-align:right;overflow-wrap:anywhere}th{background:#edf6f1}td:first-child,th:first-child{text-align:left}tbody tr:last-child{background:#f1f3f5}.approvals{float:right;border:1px solid #aab5bb;padding:10px;font-size:13px}.signature{text-align:right;margin-top:40px}.status{color:#65737d;font-size:13px}.tools button{padding:10px 18px;background:#009f57;color:#fff;border:0;border-radius:5px}@page{size:'''+('A4 portrait' if kind=='공문' else 'A3 landscape')+''';margin:12mm}@media print{body{margin:0;padding:0;max-width:none;font-size:11pt;line-height:1.35}h1{font-size:19pt;margin:8px 0}h2{font-size:14pt;margin:14px 0 8px}p{margin:7px 0}header{padding-bottom:7px}table{margin:10px 0}td,th{padding:5px}.signature{margin-top:20px}.tools{display:none}th{background:#edf6f1!important}td,th{print-color-adjust:exact}tr{break-inside:avoid}h2{break-after:avoid}}</style><div class="tools"><button onclick="window.print()">인쇄 / PDF 저장</button></div><p class="status">'''+esc(status)+''' · 금액 단위: 원</p>'''+body+'</html>'
