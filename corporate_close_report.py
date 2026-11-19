"""Excel-shaped corporate-close preview and numeric workbook export."""
from html import escape
from io import BytesIO
import openpyxl
from openpyxl.styles import Font,PatternFill,Border,Side,Alignment
from openpyxl.utils import get_column_letter
import corporate_close_calc as calc
try:
    from table_layout import format_excel
except (ImportError, ModuleNotFoundError):
    # Older Sheri2 installations only provide the on-screen table helpers.
    # Keep the corporate-close workbook export self-contained on those builds.
    def format_excel(sheet):
        thin=Side(style='thin',color='B7C8BF')
        for row in sheet.iter_rows():
            for cell in row:
                cell.border=Border(left=thin,right=thin,top=thin,bottom=thin)
                cell.alignment=Alignment(horizontal='right' if isinstance(cell.value,(int,float)) else 'center',vertical='center')
        for column in range(1,sheet.max_column+1):
            letter=get_column_letter(column)
            width=max((len(str(sheet.cell(row,column).value or '')) for row in range(1,sheet.max_row+1)),default=8)
            sheet.column_dimensions[letter].width=min(max(width+3,10),32)

def n(v):return f'{int(v):,}'
def td(label,value=None,kind='',span=1):
    cls=(' '+kind) if kind else ''
    if value is None:return f'<td colspan="{span}" class="text{cls}">{escape(str(label))}</td>'
    return f'<td class="text{cls}">{escape(str(label))}</td><td class="money{cls}">{n(value)}</td>'
def html(company,year,payload,adjustments,income,tax,reserves=()):
    f=calc.flow(payload.get('values',{}),adjustments);a=calc.adjustment_totals(adjustments)
    review=payload.get('review',{});rt=calc.research_totals(review);required=['donation_excess','donation_carry_deduction','carry_loss','rd_prior','rd_current','undocumented_base','land_gain','prepaid_local','accrued_tax'];tax_ready=all(k in payload.get('tax',{}) for k in required)
    def adj(side):
        rs=[r for r in adjustments if r['side']==side and not r.get('deleted')];body=''
        for r in rs:
            operating=(r.get('account_group') or '원가')=='원가';cost=r['amount'] if r['target']=='원가' else r.get('cost_amount',0) if r['target']=='공통' else 0;sga=r['amount']-cost
            body+=f'<tr><td>{escape(r["name"])}</td><td class="money input">{n(r["amount"])}</td><td class="money calc">{n(cost) if operating else ""}</td><td class="money calc">{n(sga) if operating else ""}</td></tr>'
        amount=sum(r['amount'] for r in rs);cost=a[side+'_cost'];sga=a[side+'_sga']
        return body+f'<tr class="auto"><th>계</th><th class="money calc">{n(amount)}</th><th class="money calc">{n(cost)}</th><th class="money calc">{n(sga)}</th></tr>'
    metrics=[('매출액','revenue',''),('매출원가','cost',''),('판매관리비','sga',''),('영업외수익','nonop_income',''),('영업외비용','nonop_expense',''),('각사업연도소득','current_income','auto'),('이월결손금','loss','input'),('과세표준','taxable','auto')]
    division_head='<th>구분</th><th>전체 합계</th>'+''.join(f'<th>{escape(r["name"])}</th>' for r in income['rows']);division=''
    for label,key,kind in metrics:
        vals=[r[key] for r in income['rows']];cls=(' class="'+kind+'"') if kind else '';total_key={'revenue':'sales'}.get(key,key);total=income.get('totals',{}).get(total_key,sum(vals)) if key not in ['current_income','loss','taxable'] else sum(vals)
        division+=f'<tr{cls}><td>{label}</td><td class="money">{n(total)}</td>'+''.join(f'<td class="money">{n(v)}</td>' for v in vals)+'</tr>'
    left=[('공사수입',f['construction_revenue'],'input'),('용역수입',f['service_revenue'],'input'),('진행률조정수입',f['progress_adjustment'],'estimate'),('매출계',f['sales'],'auto'),('매출총이익',f['gross_profit'],'auto'),('판매관리비',f['sga'],'input'),('영업이익',f['operating_profit'],'auto'),('영업외수익',f['nonop_income'],'input'),('영업외비용',f['nonop_expense'],'input'),('법인세차감전순이익',f['pre_tax'],'auto'),('법인세등',n(tax['tax_expense']) if tax_ready else '계산 대기','estimate raw'),('당기순이익',tax['net_income'],'auto')]
    middle=[('전기매출',f['prior_sales'],'input'),('당기매출',f['sales'],'auto'),('증감률',f'{f["sales_growth"]:.2f}%','raw'),('매출원가',f['cost'],'input'),('전기 진행률조정',f['prior_progress'],''),('당기 진행률조정',f['progress_adjustment'],'estimate'),('진행률조정 계',f['prior_progress']+f['progress_adjustment'],'auto'),('전기 미완성공사',f['prior_unfinished'],''),('당기 미완성공사',f['current_unfinished'],'estimate'),('세전이익률 전기','-','raw'),('세전이익률 당기',f'{f["pre_tax_rate"]:.2f}%','raw'),('순이익률 전기','-','raw'),('순이익률 당기',f'{(tax["net_income"]/f["sales"]*100 if f["sales"] else 0):.2f}%','raw'),('원가율 전기','-','raw'),('원가율 당기',f'{f["cost_rate"]:.2f}%','raw')]
    adjustment=[('접대비','경비',review.get('entertainment_cost',0),'input'),('접대비','판관비',review.get('entertainment_sga',0),'input'),('세금과공과','경비',review.get('tax_cost',0),'input'),('세금과공과','판관비',review.get('tax_sga',0),'input'),('접대비·세금과공과 계','',sum(review.get(k,0) for k in ['entertainment_cost','entertainment_sga','tax_cost','tax_sga']),'auto'),('이자비용','',review.get('interest',0),'input'),('기부금','',review.get('donation',0),'input'),('경상연구개발비 계','',rt['current_total'],'auto'),('인력개발비 계','',rt['personnel_total'],'auto'),('기술개발투자비','',rt['tech_total'],'auto')]
    prepaid=[('법인세 중간예납',tax.get('prepaid_corp_interim',0),'input'),('법인세 원천납부',tax.get('prepaid_corp_withholding',0),'input'),('지방소득세 기납부',tax.get('prepaid_local',0),'input'),('선납세금 합계',tax.get('prepaid_total',tax.get('prepaid_corp',0)+tax.get('prepaid_local',0)),'auto')]
    def pair(item,end=False):
        if not item:return '<td></td><td class="block-end"></td>' if end else '<td></td><td></td>'
        label,value,kind=item;raw='raw' in kind;classes=' '.join(x for x in kind.split() if x!='raw');value=value if raw else n(value)
        endclass=' block-end' if end else ''
        rendered=escape(str(value))
        if '율' in str(label) and str(value).rstrip().endswith('%'):
            try:width=max(0,min(100,float(str(value).rstrip().rstrip('%'))));rendered=f'<div class="ratio"><span>{rendered}</span><i style="width:{width}%"></i></div>'
            except ValueError:pass
        return f'<td class="{classes}">{escape(str(label))}</td><td class="money {classes}{endclass}">{rendered}</td>'
    def quad(item):
        if not item:return '<td></td><td></td><td></td><td class="block-end"></td>'
        group,detail,value,kind=item;value=n(value)
        if detail:return f'<td>{escape(str(group))}</td><td>{escape(str(detail))}</td><td class="money {kind}">{value}</td><td class="block-end"></td>'
        return f'<td colspan="2" class="{kind}">{escape(str(group))}</td><td class="money {kind}">{value}</td><td class="block-end"></td>'
    flow_rows=''
    for i in range(max(len(left),len(middle),len(adjustment),len(prepaid))):flow_rows+='<tr>'+pair(left[i] if i<len(left) else None,True)+pair(middle[i] if i<len(middle) else None,True)+quad(adjustment[i] if i<len(adjustment) else None)+pair(prepaid[i] if i<len(prepaid) else None)+'</tr>'
    css='''*{box-sizing:border-box}body{font:12px "Malgun Gothic","Noto Sans KR",sans-serif;color:#17231d;margin:0;padding:18px;background:#f2f6f4}.title{text-align:left;color:#075c40;font-size:25px;letter-spacing:-.8px;margin:6px 0 10px;padding-left:12px;border-left:6px solid #0a8a5c}.meta{display:flex;justify-content:space-between;align-items:center;font-weight:bold;font-size:14px;margin:8px 0 12px;padding:8px 12px;background:#fff;border:1px solid #c8d8d0;border-radius:7px}.legend{color:#60776c;font-size:10px;margin:0 0 7px;text-align:right}table{border-collapse:separate;border-spacing:0;width:100%;margin-bottom:14px;background:#fff;border:1px solid #aebfb6;border-radius:7px;overflow:hidden;box-shadow:0 2px 7px rgba(31,74,55,.08)}th,td{border-right:1px solid #cad6d0;border-bottom:1px solid #cad6d0;padding:5.5px;text-align:center}tr:last-child>td,tr:last-child>th{border-bottom:0}tr>*:last-child{border-right:0}th{font-weight:700;background:#edf5f1}.money{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}.input{color:#176fc1;background:#eef6ff}.calc{color:#e32929}.estimate{color:#e32929}.auto{background:#fff3a6!important;font-weight:800;color:#15251d}.section{background:linear-gradient(180deg,#0b8057,#086947)!important;color:#fff!important;font-size:13px;letter-spacing:-.2px}.flow{border:1px solid #7f9e8f;table-layout:fixed}.flow th{border-color:#a8bdb2}.flow .block-end{border-right:2px solid #708f80}.pair{display:grid;grid-template-columns:1fr 1fr;gap:12px}.pair table:first-child{border-right:1px solid #aebfb6}.green{background:#e4f3ea;font-weight:bold}.note{font-size:10px;color:#60776c}.ratio{position:relative;min-height:17px;overflow:hidden}.ratio i{position:absolute;left:0;bottom:0;height:5px;border-radius:4px;background:#78c69f;opacity:.7}.ratio span{position:relative;z-index:1}.no-print{border:1px solid #0a7952;background:#087a4f;color:#fff;border-radius:6px;padding:7px 14px;font-weight:700;cursor:pointer;margin-bottom:5px}.break{break-before:page}@page{size:A4 landscape;margin:8mm}@media print{body{margin:0;padding:0;background:#fff;font-size:6.5pt}.title{font-size:18pt;margin:0 0 3mm}.meta{font-size:9pt;margin:2mm 0;box-shadow:none}table{margin-bottom:2.5mm;box-shadow:none}th,td{padding:1.05mm}.section{font-size:8pt}.no-print{display:none}.break{page-break-before:always}}'''
    return f'''<!doctype html><html lang="ko"><head><meta charset="utf-8"><style>{css}</style></head><body><button class="no-print" onclick="print()">인쇄 / PDF 저장</button><h1 class="title">{year}년도 법인세 계산 흐름표</h1><div class="meta"><span>{escape(company)}</span><span>처분확정일 {escape(payload.get('disposal_date',''))}</span></div><p class="legend">파란색은 원장·작업자 입력, 빨간색은 예상금액, 노란색은 주요 자동계산 결과입니다.</p>
    <table class="flow"><colgroup><col style="width:13%"><col style="width:9%"><col style="width:12%"><col style="width:9%"><col style="width:8%"><col style="width:8%"><col style="width:10%"><col style="width:4%"><col style="width:11%"><col style="width:8%"></colgroup><tr><th class="section" colspan="2">손익계산서 점검</th><th class="section" colspan="2">전기·예상 지표</th><th class="section" colspan="4">조정 전 검토사항</th><th class="section" colspan="2">기납부세액</th></tr>{flow_rows}</table>
    <div class="pair"><table><tr><th class="section" colspan="4">익금산입 및 손금불산입</th></tr><tr><th>과목</th><th>금액</th><th>원가부인</th><th>판관비부인</th></tr>{adj('add')}</table><table><tr><th class="section" colspan="4">손금산입 및 익금불산입</th></tr><tr><th>과목</th><th>금액</th><th>원가추인</th><th>판관비추인</th></tr>{adj('deduct')}</table></div>
    <table><tr><th class="section" colspan="{2+len(income['rows'])}">소득구분계산서</th></tr><tr>{division_head}</tr>{division}</table>
    <table><tr><th class="section" colspan="8">세액 계산</th></tr><tr><td>차가감소득금액</td><td class="money calc">{n(tax['current_income'])}</td><td class="auto">산출세액</td><td class="money auto calc">{n(tax['output_tax'])}</td><td>중소기업 특별세액감면</td><td class="money calc">{n(tax['special_reduction'])}</td><td>공제·감면 계</td><td class="money calc">{n(tax['credits'])}</td></tr><tr><td>기부금한도초과</td><td class="money input">{n(tax['donation_excess'])}</td><td>R&D 전기이월</td><td class="money input">{n(tax['rd_prior'])}</td><td>R&D 당기</td><td class="money input">{n(tax['rd_current'])}</td><td>증빙미수취 가산세</td><td class="money calc">{n(tax['penalty'])}</td></tr><tr><td>기부금이월손금</td><td class="money input">{n(tax['donation_carry_deduction'])}</td><td>토지 등 양도소득 법인세</td><td class="money calc">{n(tax['land_tax'])}</td><td>법인세 총부담</td><td class="money calc">{n(tax['corp_total'])}</td><td>법인세 납부·환급</td><td class="money auto calc">{n(tax['corp_payable'])}</td></tr><tr><td>전기이월결손금</td><td class="money input">{n(tax['carry_loss'])}</td><td>법인세 중간예납</td><td class="money input">{n(tax['prepaid_corp_interim'])}</td><td>법인세 원천납부</td><td class="money input">{n(tax['prepaid_corp_withholding'])}</td><td>지방세 기납부</td><td class="money input">{n(tax['prepaid_local'])}</td></tr><tr><td class="auto">과세표준</td><td class="money auto calc">{n(tax['taxable'])}</td><td>지방소득세 총부담</td><td class="money calc">{n(tax['local_total'])}</td><td>지방소득세 납부·환급</td><td class="money calc">{n(tax['local_payable'])}</td><td class="auto">확정 법인세등</td><td class="money auto calc">{n(tax['confirmed_tax'])}</td></tr></table>
    <p class="note">파란색은 원장·전기이월·작업자 입력, 빨간색은 예상금액, 노란색은 주요 자동계산 결과입니다.</p></body></html>'''
def workbook(company,year,payload,adjustments,income,tax,reserves=()):
    w=openpyxl.Workbook();s=w.active;s.title='법인세 계산'
    rows=[['법인세 계산 흐름표',company,year],['항목','금액'],['차가감소득금액',tax['current_income']],['기부금한도초과',tax['donation_excess']],['기부금이월손금',tax['donation_carry_deduction']],['전기이월결손금',tax['carry_loss']],['과세표준',tax['taxable']],['산출세액',tax['output_tax']],['중소기업 특별세액감면',tax['special_reduction']],['R&D 전기이월',tax['rd_prior']],['R&D 당기',tax['rd_current']],['공제·감면',tax['credits']],['증빙미수취 가산세',tax['penalty']],['토지 등 양도소득 법인세',tax['land_tax']],['법인세 총부담',tax['corp_total']],['법인세 중간예납',tax.get('prepaid_corp_interim',0)],['법인세 원천납부',tax.get('prepaid_corp_withholding',0)],['법인세 기납부 합계',tax['prepaid_corp']],['법인세 납부·환급',tax['corp_payable']],['지방소득세 총부담',tax['local_total']],['지방소득세 기납부',tax['prepaid_local']],['지방소득세 납부·환급',tax['local_payable']],['확정 법인세등',tax['confirmed_tax']]]
    for r in rows:s.append(r)
    for name,data,headers in [('세무조정',adjustments,['구분','과목','금액','반영구분','원가배분액','비고']),('소득구분',income['rows'],['구분','매출액','매출원가','판매관리비','영업외수익','영업외비용','각사업연도소득','이월결손금','과세표준'])]:
        sh=w.create_sheet(name);sh.append(headers)
        for r in data:
            if name=='세무조정':
                operating=(r.get('account_group') or '원가')=='원가';sh.append([r['side'],r['name'],r['amount'],r['target'] if operating else '',r.get('cost_amount',0) if operating else '',r.get('note','')])
            elif name=='소득구분':pass
        if name=='소득구분':
            sh.delete_rows(1,sh.max_row);sh.append(['구분','전체 합계']+[r['name'] for r in data])
            for label,key in [('매출액','revenue'),('매출원가','cost'),('판매관리비','sga'),('영업외수익','nonop_income'),('영업외비용','nonop_expense'),('각사업연도소득','current_income'),('이월결손금','loss'),('과세표준','taxable')]:
                vals=[r[key] for r in data];total_key={'revenue':'sales'}.get(key,key);total=income.get('totals',{}).get(total_key,sum(vals)) if key not in ['current_income','loss','taxable'] else sum(vals);sh.append([label,total]+vals)
        format_excel(sh);sh.freeze_panes='A2';sh.auto_filter.ref=sh.dimensions
        for cell in sh[1]:cell.fill=PatternFill('solid',fgColor='DCECE2');cell.font=Font(bold=True)
    format_excel(s);s.column_dimensions['A'].width=28;s.column_dimensions['B'].width=22
    out=BytesIO();w.save(out);return out.getvalue()
