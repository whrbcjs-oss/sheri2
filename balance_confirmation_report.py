"""Printable confirmation form based on the user-supplied 2025 workbook."""
import base64
from datetime import datetime, timezone, timedelta
from html import escape


KST = timezone(timedelta(hours=9))


def won(value): return f'{int(value or 0):,}'


def _rows(lines, minimum=2):
    body=[]
    for line in lines:
        body.append('<tr><td>'+escape(line.get('account',''))+'</td><td>'+escape(line.get('note',''))+'</td><td class="num">'+won(line.get('balance',0))+'</td><td></td></tr>')
    while len(body)<minimum: body.append('<tr><td>&nbsp;</td><td></td><td></td><td></td></tr>')
    return ''.join(body)


def confirmation_html(company, profile, dispatch, group):
    receivable=[line for line in dispatch['lines'] if line.get('side')=='채권']
    payable=[line for line in dispatch['lines'] if line.get('side')=='채무']
    unresolved=[line for line in dispatch['lines'] if line.get('side') not in ('채권','채무')]
    receivable.extend(unresolved)
    receivable_total=sum(int(line.get('balance',0)) for line in receivable)
    payable_total=sum(int(line.get('balance',0)) for line in payable)
    issued=datetime.now(KST).date()
    base=str(dispatch['base_date']);parts=base.split('-')
    base_text=f'{parts[0]}년 {int(parts[1])}월 {int(parts[2])}일 현재' if len(parts)==3 else base
    auditor=' '.join(x for x in (profile.get('audit_firm',''),profile.get('auditor_name','')) if x).strip()
    inquiry=' / '.join(x for x in (profile.get('auditor_phone',''),profile.get('auditor_email','')) if x)
    seal=''
    if profile.get('seal_data') and profile.get('seal_mime') in ('image/png','image/jpeg'):
        encoded=profile['seal_data'] if isinstance(profile['seal_data'],str) else base64.b64encode(profile['seal_data']).decode('ascii')
        seal=f'<img class="seal" src="data:{profile["seal_mime"]};base64,{encoded}" alt="{escape(company)} 직인">'
    return f'''<!doctype html><html lang="ko"><head><meta charset="utf-8"><title>{escape(dispatch['confirmation_no'])} 채권채무조회서</title>
    <style>@page{{size:A4;margin:12mm 15mm}}*{{box-sizing:border-box}}html,body{{background:#fff!important}}body{{font-family:"Malgun Gothic",sans-serif;color:#000!important;font-size:11px;margin:0;line-height:1.45}}.sheet{{max-width:180mm;margin:0 auto;background:#fff!important;color:#000!important}}.copy{{text-align:right;font-weight:700;margin:0 0 6px}}h1{{font-size:23px;letter-spacing:8px;text-align:center;text-decoration:underline;text-underline-offset:5px;margin:2px 0 13px}}.issued{{text-align:right;margin-bottom:8px}}.to{{font-size:14px;font-weight:700;margin:8px 0 12px}}.intro p{{margin:2px 0}}.signature{{display:flex;justify-content:flex-end;align-items:center;min-height:58px;font-size:14px;font-weight:700;margin:5px 7px 4px}}.seal{{width:58px;height:58px;object-fit:contain;margin-left:-6px}}.section-title{{font-weight:700;border-top:1px solid #000;padding-top:5px;margin:7px 0 3px}}table{{width:100%;border-collapse:collapse;table-layout:fixed;background:#fff!important;color:#000!important}}th,td{{border:1px solid #000!important;padding:4px 6px;height:24px;background:#fff!important;color:#000!important}}th{{text-align:center;font-weight:700}}th:nth-child(1){{width:23%}}th:nth-child(2){{width:33%}}th:nth-child(3){{width:24%}}th:nth-child(4){{width:20%}}.num{{text-align:right;font-variant-numeric:tabular-nums}}tfoot td{{font-weight:700}}.notice-title{{text-align:center;font-size:17px;letter-spacing:8px;font-weight:700;margin:13px 0 8px}}.reply-to{{font-weight:700;margin:5px 0}}.reply-lines p{{margin:2px 0}}.difference{{height:42px;border-bottom:1px solid #000;margin:3px 0 8px}}.reply-fields{{width:55%;margin-left:auto;margin-top:8px}}.reply-fields div{{display:grid;grid-template-columns:75px 1fr;margin:5px 0}}.reply-fields span:last-child{{border-bottom:1px solid #000;min-height:18px}}.contact{{margin-top:10px;border-top:1px solid #000;padding-top:5px;font-size:10px}}.meta{{display:flex;justify-content:space-between;color:#000;font-size:9px;margin-top:6px}}@media print{{html,body,.sheet{{background:#fff!important}}.sheet{{max-width:none}}}}</style></head>
    <body><main class="sheet"><div class="copy">회신용</div><h1>채권채무조회서</h1><div class="issued">{issued.year}년 {issued.month}월 {issued.day}일</div>
    <div class="to">{escape(dispatch['counterparty'])}　귀하</div><section class="intro">
    <p>귀사의 사업이 더욱 번창하시기를 기원하오며, 항상 각별하신 협조에 감사드립니다.</p>
    <p>바쁘실 줄 아오나 당사의 회계감사에 필요하여 <b>{escape(base_text)}</b> 귀사에 대한</p>
    <p>당사의 채권·채무 잔액과 내용을 확인하고자 하오니 귀사의 장부와 대조·확인하시고,</p>
    <p>그 상이 유무를 아래 확인통지란에 금액과 내용을 기입하여 서명·날인 후 보내주시기 바랍니다.</p>
    <p>본 조회내용은 관계 법령에 따라 비밀이 보장되며 회계감사 목적으로만 이용됩니다.</p></section>
    <div class="signature"><span>{escape(company)}　</span>{seal or '<span>(인)</span>'}</div>
    <div class="section-title">1. 당사가 귀사로부터 받아야 할 금액(채권) — 귀사가 당사에 지급해야 할 금액(채무)</div>
    <table><thead><tr><th>계정과목</th><th>적요</th><th>금액</th><th>비고</th></tr></thead><tbody>{_rows(receivable)}</tbody><tfoot><tr><td colspan="2">합　　　　　　계</td><td class="num">{won(receivable_total)}</td><td></td></tr></tfoot></table>
    <div class="section-title">2. 당사가 귀사에 지급해야 할 금액(채무) — 귀사가 당사로부터 받아야 할 금액(채권)</div>
    <table><thead><tr><th>계정과목</th><th>적요</th><th>금액</th><th>비고</th></tr></thead><tbody>{_rows(payable)}</tbody><tfoot><tr><td colspan="2">합　　　　　　계</td><td class="num">{won(payable_total)}</td><td></td></tr></tfoot></table>
    <div class="notice-title">확 인 통 지</div><div class="reply-to">{escape(auditor or profile.get('audit_firm',''))} 귀중</div>
    <section class="reply-lines"><p>1. 위 조회서에 기재된 금액과 내용은 당사 장부와 일치하고 있으므로 이에 서명·날인하여 통지합니다.</p><p>2. 아래와 같은 상이점이 있음을 알려드립니다.</p></section><div class="difference"></div>
    <div class="reply-fields"><div><span>주　　소:</span><span></span></div><div><span>회 사 명:</span><span></span></div><div><span>대 표 자:</span><span>　　　　　　　　　　　　(인)</span></div></div>
    <div class="contact">문의처: 담당공인회계사　{escape(profile.get('auditor_name',''))}　{escape(inquiry)}<br>감사인명: {escape(profile.get('audit_firm',''))}<br>회신주소: {escape(profile.get('auditor_address',''))}</div>
    <div class="meta"><span>확인번호: {escape(dispatch['confirmation_no'])}</span><span>{escape(company)} · 기준일 {escape(base)}</span></div></main></body></html>'''.encode('utf-8')
