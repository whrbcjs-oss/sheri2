"""Escaped A4 loan certificates, PDF files and Excel-style loan-register printouts."""
from html import escape
from io import BytesIO
from PIL import Image,ImageDraw
import loan_calc as calc
import a4_layout as a4


def esc(value):return escape(str(value if value is not None else ''),quote=True)
def korean_amount(value):
    value=calc.won(value)
    if not value:return '영'
    digits='영일이삼사오육칠팔구';groups=[];units=['','만','억','조']
    for unit in units:
        group=value%10000;value//=10000
        if group:
            text=''
            for divisor,suffix in [(1000,'천'),(100,'백'),(10,'십'),(1,'')]:
                n,group=divmod(group,divisor)
                if n:text+=digits[n]+suffix
            groups.insert(0,text+unit)
    return ''.join(groups)


def interest_label(v):
    if v['interest_kind']==calc.KINDS[2]:return '무이자'
    if v['interest_kind']==calc.KINDS[1]:return '월정액 '+calc.money(v['fixed_interest'])+'원'
    return '연이율 '+str(v['rate'])+'%'


def certificate_lines(v,show_id=False):
    person=v.get('borrower',{});id_=person.get('national_id','')
    digits=''.join(c for c in str(id_) if c.isdigit())
    id_label='생년월일' if len(digits) in [6,8] else '주민등록번호'
    if len(digits)==8:id_=digits[:4]+'.'+digits[4:6]+'.'+digits[6:]
    elif len(digits)==6:id_=digits[:2]+'.'+digits[2:4]+'.'+digits[4:]
    if not show_id and len(digits) not in [6,8]:
        from loan_store import mask_id
        id_=mask_id(id_)
    if v['mode']==calc.MODES[2]:condition=f"이자는 매월 {v['pay_day']}일, 원금은 {v['end_date']}까지 상환할 것을 약속드립니다."
    elif v['mode']==calc.MODES[1]:condition=f"원리금은 {v['end_date']}까지 상환할 것을 약속드립니다."
    else:
        plan=calc.schedule(v);amount=calc.money(plan[0]['total'])
        condition=f"{v['method']} 방식으로 매월 {v['pay_day']}일 원리금을 상환하며, 최초 예정액은 {amount}원입니다. 최종 회차의 잔액은 만료일까지 정산할 것을 약속드립니다."
    combined=v.get('consolidation')
    title=('통합 갱신 차용증' if len(combined['rows'])>1 else '갱신 차용증') if combined else '차  용  증'
    if v.get('document_kind')=='amendment':title='변경 차용증'
    result=[('title',title),('small','관리번호: '+v.get('number','미저장')),('blank',''),('bold','■ 차용인'),('body','성명: '+person.get('name','')),('body','연락처: '+person.get('phone','')),('body',id_label+': '+id_),('body','주소: '+person.get('address','')),('blank',''),('bold','■ 차용금액: 일금 '+korean_amount(v['principal'])+'원정 (₩'+calc.money(v['principal'])+')'),('body','■ 대여일/차용시작일: '+v['start_date'].replace('-','.')),('body','■ 차용 종료일: '+v['end_date'].replace('-','.')),('body','■ 차용이자: '+interest_label(v)),('blank',''),('body','상기 본인은 '+v.get('company','')+'로부터 위 금액을 차용하며, '+condition)]
    if v['interest_kind']==calc.KINDS[0]:result.append(('small','이자 계산 기준: '+v['basis']))
    if v['mode']!=calc.MODES[1]:result.append(('small','최초 상환일: '+v['first_due']))
    if combined:
        result=[(k,('■ 갱신 원금잔액: 일금 '+korean_amount(v['principal'])+'원정 (₩'+calc.money(v['principal'])+')') if t.startswith('■ 차용금액:') else ('상기 본인은 별첨 기존 차용건의 잔액을 확인하고 다음 조건으로 갱신하며, '+condition) if t.startswith('상기 본인은 ') else t) for k,t in result]
        pos=next(i for i,(k,t) in enumerate(result) if t.startswith('■ 갱신 원금잔액:'))+1
        result[pos:pos]=[('body','■ 기존 미회수 이자: '+calc.money(combined['unpaid_interest'])+'원 (원금과 별도)'),('bold','■ 갱신 대상 총액: 일금 '+korean_amount(combined['total'])+'원정 (₩'+calc.money(combined['total'])+')'),('small','잔액 산정 기준일: '+combined['as_of']+' · 기존 차용건 '+str(len(combined['rows']))+'건')]
        result.append(('body','세부 내역은 마지막 장의 별첨 명세와 같으며, 본 차용증의 일부로 합니다.'))
    if v.get('carry_interest'):
        policy=v.get('carry_policy','첫 상환일 정산')
        result.append(('body','이전 계약의 미회수 이자 '+calc.money(v['carry_interest'])+'원은 원금과 별도로 이월하며 '+policy+'합니다. 기존 이자에 새 이자를 부과하지 않습니다.'))
    if v.get('interest_credit'):result.append(('body','이전 계약에서 선납한 이자 '+calc.money(v['interest_credit'])+'원은 이자 상환액에서 차감합니다.'))
    if v.get('previous_number'):result.append(('small','갱신 전 관리번호: '+v['previous_number']))
    result.extend([('blank',''),('body','# 담보물의 명칭 및 기타 조건: '+(v.get('collateral') or '별도 약정 없음'))])
    if v.get('note'):result.append(('body','# 추가 약정: '+v['note']))
    result.extend([('body','# 첨부서류: '+(', '.join(v.get('attachments',[])) or '별도 첨부 없음')+'. 끝.'),('blank',''),('center',v['issued_date'].replace('-','.')),('blank',''),('center','위 차용인: '+person.get('name','')+'                 (인)'),('center','(연락처: '+person.get('phone','')+')'),('blank',''),('company',v.get('company','')+' 귀중')])
    return result


DOC_CSS='''*{box-sizing:border-box}body{margin:0;background:#edf2ef;color:#111;font-family:"Malgun Gothic","Noto Serif CJK KR",serif}.tools{padding:10px;text-align:right}.tools button{border:0;border-radius:5px;padding:9px 18px;background:#087b52;color:#fff;cursor:pointer}.paper{background:#fff;max-width:210mm;min-height:270mm;margin:12px auto;padding:20mm 18mm;box-shadow:0 2px 8px #0001;font-size:14px;line-height:1.65;overflow-wrap:anywhere}.paper p{margin:3px 0;white-space:pre-wrap}.paper .title{text-align:center;font-size:27px;letter-spacing:9px;text-decoration:underline;text-underline-offset:8px;margin-bottom:24px}.paper .small{font-size:11px;color:#555}.paper .bold{font-weight:700}.paper .blank{height:17px}.paper .center{text-align:center;margin-top:8px}.paper .company{font-size:20px;margin-top:20px}.muted{color:#617569}.annex h2{font-size:20px;text-align:center}.annex table{border-collapse:collapse;width:100%;table-layout:fixed;font:10px 'Malgun Gothic',sans-serif}.annex th,.annex td{border:1px solid #879d91;padding:6px 3px;text-align:center;overflow-wrap:anywhere}.annex th{background:#e4f3e9}.annex td.money{text-align:right}.annex .detail{font-size:10px;line-height:1.6;text-align:left}.annex .total{font-weight:bold;background:#e4f3e9}.annex .sign{margin-top:25px;text-align:center}.annex{break-before:page;page-break-before:always}@page{size:A4;margin:0}@media print{body{background:white}.tools{display:none}.paper{max-width:none;margin:0;box-shadow:none;min-height:0}p{break-inside:avoid}}'''


def certificate_html(v,show_id=False):
    body=a4.html_pages(certificate_lines(v,show_id),'loan')
    return '<!doctype html><html lang="ko"><meta charset="utf-8"><title>차용증 '+esc(v.get('number',''))+'</title><style>'+DOC_CSS+a4.CSS+'</style><body><div class="tools"><button onclick="window.print()">인쇄 / PDF 저장</button></div>'+body+annex_html(v)+'</body></html>'


def certificate_pdf(v,show_id=False):
    from survey_report import font
    pages=a4.images(certificate_lines(v,show_id),'loan');pages.extend(annex_images(v))
    footer_font=font(8)
    for i,page in enumerate(pages):
        d=ImageDraw.Draw(page);text=f'{i+1} / {len(pages)}';d.text(((2480-d.textlength(text,font=footer_font))/2,3380),text,font=footer_font,fill='#555555')
    stream=BytesIO();pages[0].save(stream,format='PDF',save_all=True,append_images=pages[1:],resolution=300,quality=95)
    return stream.getvalue()


def register_html(summaries,as_of):
    headers=['관리번호','구분','차용인','지급회사','대여일','적요','채권금액','상환금액','잔액','상환일','이자','증빙','비고']
    groups={}
    for s in summaries:groups.setdefault(s['loan']['borrower_id'],[]).append(s)
    rows=[]
    for group in groups.values():
        for s in group:
            loan=s['loan'];v=loan['terms'];person=loan['borrower']
            data=[loan['number'],person['kind'],person['name'],loan['company'],loan['start_date'],'일시 대여금',calc.money(s['principal']),calc.money(s['paid_principal']),calc.money(s['balance']),v['end_date'],interest_label(v),'차용증',v.get('note','')]
            rows.append('<tr>'+''.join('<td class="'+('number' if i in [6,7,8] else '')+'">'+esc(t)+'</td>' for i,t in enumerate(data))+'</tr>')
        if len(group)>1:
            sums=[sum(s[k] for s in group) for k in ['principal','paid_principal','balance']]
            rows.append('<tr class="subtotal"><td colspan="6">'+esc(group[0]['loan']['borrower']['name'])+' 소계</td>'+''.join('<td class="number">'+calc.money(n)+'</td>' for n in sums)+'<td colspan="4"></td></tr>')
    sums=[sum(s[k] for s in summaries) for k in ['principal','paid_principal','balance']]
    rows.append('<tr class="total"><td colspan="6">전체 합계</td>'+''.join('<td class="number">'+calc.money(n)+'</td>' for n in sums)+'<td colspan="4"></td></tr>')
    approvals='<table class="approval"><tr>'+''.join('<th>'+name+'</th>' for name in ['담당','부장','상무','사장'])+'</tr><tr>'+'<td></td>'*4+'</tr></table>'
    css='''body{font:12px "Malgun Gothic",sans-serif;color:#162d29;margin:20px}h1{text-align:center;font-size:24px}.tools{text-align:right}button{padding:8px 18px;background:#087b52;color:white;border:0;border-radius:5px}table{width:100%;border-collapse:collapse}th,td{border:1px solid #778d81;padding:7px 5px;text-align:center;overflow-wrap:anywhere}th{background:#e4f3e9}.number,.amount{text-align:right;white-space:nowrap}.grand-total{background:#dff3e7;font-weight:bold}.borrower-summary{margin-bottom:18px}h2{font-size:16px;margin:14px 0 8px}.subtotal{background:#fff7df;font-weight:bold}.total{background:#dff3e7;font-weight:bold}.register-head{display:flex;align-items:center;gap:20px}.register-head h1{flex:1}.approval{width:280px;margin-left:auto}.approval td{height:50px}.meta{text-align:right;margin:10px 0}.register{table-layout:fixed}.register th{font-size:11px}@page{size:A3 landscape;margin:10mm}@media print{.tools{display:none}body{margin:0}tr{break-inside:avoid}}'''
    return '<!doctype html><html lang="ko"><meta charset="utf-8"><title>임직원 차용현황표</title><style>'+css+'</style><div class="tools"><button onclick="window.print()">인쇄 / PDF 저장</button></div>'+'<div class="register-head"><h1>임직원 차용현황표</h1>'+approvals+'</div><div class="meta">기준일자: '+esc(as_of)+'</div><h2>차용인별 요약</h2>'+borrower_table(summaries)+'<h2>건별 상세현황</h2><table class="register"><thead><tr>'+''.join('<th>'+h+'</th>' for h in headers)+'</tr></thead><tbody>'+''.join(rows)+'</tbody></table><p>상환일은 현재 약정의 만료일입니다. 상환금액과 잔액은 기준일 실제 회수 원금을 반영합니다.</p></html>'


ANNEX_HEADERS=['기존 관리번호','대여일','최초 차용원금','회수원금','원금잔액','미회수 이자','갱신 대상 합계']


def annex_groups(v):
    rows=v.get('consolidation',{}).get('rows',[])
    return [rows[i:i+3] for i in range(0,len(rows),3)]


def annex_values(row):
    return [row['number'],row['start_date']]+[calc.money(row[k]) for k in ['original_principal','paid_principal','balance','unpaid_interest','total']]


def annex_detail(row):
    return [
        '이자 산정기간: '+row['interest_start']+' ~ '+row['interest_end']+' · '+interest_label(row)+' · '+row['basis'],
        '금회 발생이자 '+calc.money(row['earned_interest'])+'원 + 이전 이월이자 '+calc.money(row['opening_carry'])+'원 − 금회 회수이자 '+calc.money(row['paid_interest'])+'원 − 이전 선납공제 '+calc.money(row['opening_credit'])+'원',
        '미회수 이자 '+calc.money(row['unpaid_interest'])+'원 · 선납이자 잔액 '+calc.money(row['interest_credit'])+'원 (원금과 구분 승계)'
    ]


def annex_totals(v):
    data=v['consolidation']
    return ['합계','']+[calc.money(sum(r[k] for r in data['rows'])) for k in ['original_principal','paid_principal','balance','unpaid_interest','total']]


def annex_html(v):
    groups=annex_groups(v)
    if not groups:return ''
    result=[];data=v['consolidation']
    for index,group in enumerate(groups):
        final=index==len(groups)-1
        html='<article class="paper annex"><h2>별첨 — 기존 차용건별 잔액 명세</h2><p class="small">갱신 관리번호: '+esc(v['number'])+' · 기준일: '+esc(data['as_of'])+' · 별첨 '+str(index+1)+' / '+str(len(groups))+'</p><p class="small">차용인: '+esc(v['borrower']['name'])+' · 지급회사: '+esc(v['company'])+' · 금액 단위: 원</p><table><thead><tr>'+''.join('<th>'+esc(h)+'</th>' for h in ANNEX_HEADERS)+'</tr></thead><tbody>'
        for row in group:
            html+='<tr>'+''.join('<td class="'+('money' if i>=2 else '')+'">'+esc(value)+'</td>' for i,value in enumerate(annex_values(row)))+'</tr><tr><td colspan="7" class="detail">'+'<br>'.join(esc(t) for t in annex_detail(row))+'</td></tr>'
        if final:
            html+='<tr class="total">'+''.join('<td class="'+('money' if i>=2 else '')+'">'+esc(value)+'</td>' for i,value in enumerate(annex_totals(v)))+'</tr>'
        html+='</tbody></table>'
        if final:
            html+='<p class="bold">갱신 대상 총액: '+esc(calc.money(data['total']))+'원</p><p class="small">원금 '+esc(calc.money(data['principal']))+'원 + 미회수 이자 '+esc(calc.money(data['unpaid_interest']))+'원. 선납이자 '+esc(calc.money(data['interest_credit']))+'원은 약정 이자에서 별도 공제합니다.</p><p class="small">기존 계약·회수·첨부 이력을 보존하며 통합 승계된 원금은 중복 집계하지 않습니다.</p><p class="sign">위 잔액 명세를 확인합니다. '+esc(v['borrower']['name'])+'　서명 또는 날인: __________</p>'
        else:html+='<p class="small">다음 별첨 페이지에 계속됩니다.</p>'
        result.append(html+'</article>')
    return ''.join(result)


def annex_images(v):
    from survey_report import font
    result=[];groups=annex_groups(v)
    def wrap(draw,text,f,width):
        lines=[];line=''
        for char in text:
            if char=='\n' or draw.textlength(line+char,font=f)>width:
                lines.append(line);line='' if char=='\n' else char
            else:line+=char
        return lines+[line] if line else lines
    for index,group in enumerate(groups):
        im=Image.new('RGB',(2480,3508),'white');d=ImageDraw.Draw(im);y=160
        f=font(17,True);title='별첨 — 기존 차용건별 잔액 명세';d.text(((2480-d.textlength(title,font=f))/2,y),title,font=f,fill='black');y+=125
        f=font(9)
        info=['갱신 관리번호: '+v['number']+' · 기준일: '+v['consolidation']['as_of']+' · 별첨 '+str(index+1)+' / '+str(len(groups)), '차용인: '+v['borrower']['name']+' · 지급회사: '+v['company']+' · 금액 단위: 원']
        for text in info:
            for line in wrap(d,text,f,2200):d.text((140,y),line,font=f,fill='black');y+=60
        y+=30
        widths=[340,210,330,330,330,330,330]
        def cells(values,header=False,total=False):
            nonlocal y
            f=font(8,header or total);wrapped=[wrap(d,t,f,w-20) for t,w in zip(values,widths)];height=max(85,max(len(w) for w in wrapped)*48+20);x=140
            for i,(lines,width) in enumerate(zip(wrapped,widths)):
                d.rectangle((x,y,x+width,y+height),fill='#e4f3e9' if header or total else 'white',outline='#879d91',width=2)
                for j,line in enumerate(lines):
                    tw=d.textlength(line,font=f);tx=x+width-12-tw if i>=2 and not header else x+(width-tw)/2
                    d.text((tx,y+10+j*48),line,font=f,fill='black')
                x+=width
            y+=height
        cells(ANNEX_HEADERS,header=True)
        for row in group:
            cells(annex_values(row))
            f=font(8)
            for text in annex_detail(row):
                for line in wrap(d,text,f,2160):d.text((160,y+10),line,font=f,fill='black');y+=55
            y+=30
        if index==len(groups)-1:
            cells(annex_totals(v),total=True);y+=50
            f=font(11,True);d.text((140,y),'갱신 대상 총액: '+calc.money(v['consolidation']['total'])+'원',font=f,fill='black');y+=85
            f=font(9)
            for text in ['원금과 미회수 이자는 구분 승계하며, 기존 이자에 새 이자를 부과하지 않습니다.','선납이자 '+calc.money(v['consolidation']['interest_credit'])+'원은 약정 이자에서 별도 공제합니다.','기존 계약·회수·첨부 이력을 보존하며 통합 승계된 원금은 중복 집계하지 않습니다.','위 잔액 명세를 확인합니다. '+v['borrower']['name']+'　서명 또는 날인: __________']:
                for line in wrap(d,text,f,2200):d.text((140,y),line,font=f,fill='black');y+=70
        result.append(im)
    return result


def borrower_totals(summaries):
    """Aggregate registered borrowers, keeping different people with the same name separate."""
    groups={}
    for s in summaries:
        item=s['loan'];id=item['borrower_id']
        group=groups.setdefault(id,dict(borrower_id=id,name=item['borrower']['name'],companies=set(),count=0,principal=0,paid_principal=0,balance=0,unpaid_interest=0))
        group['companies'].add(item['company']);group['count']+=1
        for key in ['principal','paid_principal','balance','unpaid_interest']:group[key]+=s[key]
    return [dict(g,companies=' · '.join(sorted(g['companies']))) for g in sorted(groups.values(),key=lambda g:(g['name'],g['borrower_id']))]


def borrower_records(summaries):
    result=[{'차용인':g['name'],'지급회사':g['companies'],'차용건수':g['count'],'전체 대여원금':g['principal'],'전체 상환원금':g['paid_principal'],'전체 잔액':g['balance'],'미회수 이자':g['unpaid_interest']} for g in borrower_totals(summaries)]
    result.append({'차용인':'전체 합계','지급회사':'','차용건수':len(summaries),'전체 대여원금':sum(s['principal'] for s in summaries),'전체 상환원금':sum(s['paid_principal'] for s in summaries),'전체 잔액':sum(s['balance'] for s in summaries),'미회수 이자':sum(s['unpaid_interest'] for s in summaries)})
    return result


def borrower_table(summaries):
    records=borrower_records(summaries);headers=list(records[0]);rows=[]
    for index,r in enumerate(records):
        cells=''.join('<td class="'+('amount' if i>=3 else '')+'">'+esc(calc.money(r[h]) if i>=3 else r[h])+'</td>' for i,h in enumerate(headers))
        rows.append('<tr'+(' class="grand-total"' if index==len(records)-1 else '')+'>'+cells+'</tr>')
    return '<table class="borrower-summary"><thead><tr>'+''.join('<th>'+esc(h)+'</th>' for h in headers)+'</tr></thead><tbody>'+''.join(rows)+'</tbody></table>'


OVERVIEW_CSS='''<style>
#loan-overview-panel{width:100%;color:#193b30;font-family:"Malgun Gothic",sans-serif}
#loan-overview-panel h3{font-size:20px;font-weight:750;margin:12px 0 10px}
#loan-overview-panel .table-wrap{width:100%;overflow-x:auto}
#loan-overview-panel table{width:100%;border-collapse:collapse;font-size:14px;line-height:1.5}
#loan-overview-panel th,#loan-overview-panel td{border:1px solid #cfddd5;padding:10px 8px;text-align:center;overflow-wrap:anywhere;vertical-align:middle}
#loan-overview-panel th{background:#e9f4ed;color:#174a37;font-weight:750}
#loan-overview-panel td.amount{text-align:right;white-space:nowrap;font-variant-numeric:tabular-nums}
#loan-overview-panel .grand-total{background:#dcefe2;font-weight:800}
#loan-overview-panel .subtotal{background:#fff7df;font-weight:700}
#loan-overview-panel .detail-table{table-layout:fixed;min-width:1150px}
#loan-overview-panel .borrower-summary{min-width:780px}
#loan-overview-panel .note{font-size:13px;color:#65796f;margin:8px 0 14px}
#loan-overview-panel details{margin-top:14px}
#loan-overview-panel summary{cursor:pointer;font-size:18px;font-weight:750;padding:8px 0}
</style>'''


def overview_html(summaries,as_of):
    headers=['관리번호','구분','차용인','지급회사','대여일','적요','채권금액','상환원금','잔액','상환일','이자','증빙','비고'];rows=[]
    groups={}
    for s in summaries:groups.setdefault(s['loan']['borrower_id'],[]).append(s)
    for group in sorted(groups.values(),key=lambda g:(g[0]['loan']['borrower']['name'],g[0]['loan']['borrower_id'])):
        for s in group:
            item=s['loan'];v=item['terms'];person=item['borrower']
            values=[item['number'],person['kind'],person['name'],item['company'],item['start_date'],'일시 대여금',calc.money(s['principal']),calc.money(s['paid_principal']),calc.money(s['balance']),v['end_date'],interest_label(v),'차용증',v.get('note','')]
            rows.append('<tr>'+''.join('<td class="'+('amount' if i in [6,7,8] else '')+'">'+esc(value)+'</td>' for i,value in enumerate(values))+'</tr>')
        if len(group)>1:
            rows.append('<tr class="subtotal"><td colspan="6">'+esc(group[0]['loan']['borrower']['name'])+' 소계 · '+str(len(group))+'건</td>'+''.join('<td class="amount">'+calc.money(sum(s[k] for s in group))+'</td>' for k in ['principal','paid_principal','balance'])+'<td colspan="4"></td></tr>')
    if not summaries:rows.append('<tr><td colspan="13">조회 조건에 해당하는 차용건이 없습니다.</td></tr>')
    rows.append('<tr class="grand-total"><td colspan="6">전체 합계</td>'+''.join('<td class="amount">'+calc.money(sum(s[k] for s in summaries))+'</td>' for k in ['principal','paid_principal','balance'])+'<td colspan="4"></td></tr>')
    widths=[10,4,6,8,7,7,10,10,10,7,8,5,8]
    detail='<table class="detail-table"><colgroup>'+''.join('<col style="width:'+str(w)+'%">' for w in widths)+'</colgroup><thead><tr>'+''.join('<th>'+h+'</th>' for h in headers)+'</tr></thead><tbody>'+''.join(rows)+'</tbody></table>'
    return OVERVIEW_CSS+'<section id="loan-overview-panel"><h3>차용인별 요약</h3><div class="table-wrap">'+borrower_table(summaries)+'</div><p class="note">기준일 '+esc(as_of)+' · 상환금액은 실제 회수한 원금입니다. 미회수 이자는 잔액과 구분해 표시합니다.</p><details open><summary>건별 상세현황 · '+str(len(summaries))+'건</summary><div class="table-wrap">'+detail+'</div></details></section>'
