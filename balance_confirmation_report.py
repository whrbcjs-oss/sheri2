"""Printable standard confirmation form used until a user template is supplied."""
from html import escape


def won(value):
    return f'{int(value or 0):,}'


def confirmation_html(company, profile, dispatch, group):
    lines = ''.join(
        '<tr><td>' + escape(dispatch['base_date']) + '</td><td>' + escape(line['account']) + '</td>'
        '<td>' + escape(line['side']) + '</td><td class="num">' + won(line['balance']) + '</td><td>' + escape(line.get('note', '')) + '</td></tr>'
        for line in dispatch['lines'])
    side = group.get('side', '')
    return f'''<!doctype html><html lang="ko"><head><meta charset="utf-8"><title>{escape(dispatch['confirmation_no'])} 채권채무확인서</title>
    <style>@page{{size:A4;margin:16mm}}*{{box-sizing:border-box}}body{{font-family:"Malgun Gothic",sans-serif;color:#111;font-size:12px;margin:0}}
    h1{{text-align:center;font-size:24px;letter-spacing:6px;margin:18px 0 34px}}.meta{{display:flex;justify-content:space-between;border-bottom:2px solid #222;padding-bottom:8px;margin-bottom:26px}}
    p{{line-height:1.8}}.to{{font-size:15px;font-weight:700;margin:20px 0}}table{{border-collapse:collapse;width:100%;margin:22px 0}}th,td{{border:1px solid #222;padding:8px}}th{{background:#eef3f1;text-align:center}}.num{{text-align:right;font-variant-numeric:tabular-nums}}tfoot td{{font-weight:700;background:#f4f6f5}}
    .reply{{border:2px solid #333;padding:12px 14px;margin-top:24px;line-height:1.7}}.sign{{text-align:right;margin-top:40px;font-size:15px;font-weight:700}}.notice{{font-size:10px;color:#555;margin-top:18px}}@media print{{button{{display:none}}}}</style></head>
    <body><div class="meta"><span>확인번호: <b>{escape(dispatch['confirmation_no'])}</b></span><span>기준일: {escape(dispatch['base_date'])}</span></div>
    <h1>채권·채무 잔액 확인서</h1><p class="to">{escape(dispatch['counterparty'])} 귀중</p>
    <p>외부감사와 관련하여 당사 장부에 기록된 귀사와의 <b>{escape(side)}</b> 잔액은 아래와 같습니다. 내용의 일치 여부를 확인하시어 담당 공인회계법인으로 직접 회신하여 주시기 바랍니다.</p>
    <table><thead><tr><th>기준일</th><th>계정과목</th><th>구분</th><th>당사 장부잔액(원)</th><th>비고</th></tr></thead><tbody>{lines}</tbody>
    <tfoot><tr><td colspan="3">합계</td><td class="num">{won(dispatch['total_balance'])}</td><td></td></tr></tfoot></table>
    <div class="reply"><b>회신처</b><br>{escape(profile.get('audit_firm',''))} {escape(profile.get('auditor_name',''))}<br>
    이메일: {escape(profile.get('auditor_email',''))}　연락처: {escape(profile.get('auditor_phone',''))}<br>{escape(profile.get('auditor_address',''))}</div>
    <div class="sign">{escape(company)}<br>대표이사　(직인)</div>
    <p class="notice">본 확인서는 잔액 확인을 위한 문서이며 회신은 위 공인회계법인으로 직접 보내주시기 바랍니다.</p></body></html>'''.encode('utf-8')
