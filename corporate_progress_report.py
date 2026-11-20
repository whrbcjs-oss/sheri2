"""A4 landscape and numeric Excel outputs for construction progress review."""
from html import escape
from io import BytesIO
import openpyxl
from openpyxl.styles import Font,PatternFill,Alignment
import corporate_progress as calc
from table_layout import format_excel

def n(v):return f'{int(v or 0):,}'
def html(company,year,rows,flow_revenue,extra=None):
    data=[calc.recalculate(r) for r in rows if not r.get('deleted')];s=calc.summary(data,extra);body=''
    for r in data:
        body+=f'''<tr><td>{escape(r['client'])}</td><td>{escape(r['project'])}</td><td>{escape(r['start'])}<br>{escape(r['end'])}</td><td class="m">{n(r['contract'])}</td><td>{escape(r['trade'])}</td><td class="m blue">{n(r['prior_revenue'])}</td><td class="m blue">{n(r['current_revenue'])}</td><td class="m">{n(r['total_revenue'])}</td><td class="m blue">{n(r['prior_cost'])}</td><td class="m blue">{n(r['current_cost'])}</td><td class="m">{n(r['total_cost'])}</td><td>{r['expected_cost_rate']*100:.3f}%</td><td class="m">{n(r['expected_revenue'])}</td><td class="m red">{n(calc.final_adjustment(r))}</td><td>{escape(r['status'])}</td></tr>'''
    css='''*{box-sizing:border-box}body{font:8pt "Malgun Gothic",sans-serif;margin:0;color:#111}h1{text-align:center;color:#078653;font-size:18pt;margin:0 0 3mm}.meta{display:flex;justify-content:space-between;margin-bottom:2mm;font-weight:bold}.summary{display:grid;grid-template-columns:repeat(5,1fr);gap:2mm;margin:2mm 0}.card{border:1px solid #9dbfaf;padding:2mm}.card b{display:block;text-align:right;font-size:11pt;margin-top:1mm}table{width:100%;border-collapse:collapse}th,td{border:1px solid #789487;padding:1mm;text-align:center}th{background:#dcece4}.m{text-align:right}.blue{color:#1674cf}.red{color:#df2424;font-weight:bold}.total{background:#fff36d;font-weight:bold}.break{break-before:page}@page{size:A4 landscape;margin:8mm}@media print{.no-print{display:none}}'''
    diff=int(flow_revenue or 0)-s['table_revenue']
    return f'''<!doctype html><html lang="ko"><head><meta charset="utf-8"><style>{css}</style></head><body><button class="no-print" onclick="print()">인쇄 / PDF 저장</button><h1>{year}년 공사수입·원가대비 및 진행률 검산</h1><div class="meta"><span>{escape(company)}</span><span>단위: 원</span></div><div class="summary"><div class="card">흐름표 공사수입<b>{n(flow_revenue)}</b></div><div class="card">현장표 당기 공사수입<b>{n(s['table_revenue'])}</b></div><div class="card">공사수입 검산차이<b class="red">{n(diff)}</b></div><div class="card">당기진행율 배분합계<b>{n(s['current_adjustment'])}</b></div><div class="card">예상원가율 미입력<b>{s['missing_rates']}건</b></div></div><table><thead><tr><th>발주처</th><th>공사명</th><th>착공·준공</th><th>계약공급가액</th><th>공종</th><th>전기수입</th><th>당기수입</th><th>누계수입</th><th>전기원가</th><th>당기원가</th><th>누계원가</th><th>예상원가율</th><th>예상누적수입</th><th>최종 당기진행율</th><th>상태</th></tr></thead><tbody>{body}</tbody></table><table class="break"><tr><th colspan="3">법인세 계산 흐름표 연동·검산</th></tr><tr><td>전기 진행률 조정 환입</td><td class="m">-{n(s['prior_adjustment'])}</td><td>자동집계</td></tr><tr><td>당기 진행률 조정</td><td class="m">{n(s['current_adjustment'])}</td><td>자동집계</td></tr><tr><td>전기 미완성 환입</td><td class="m">{n(s['prior_unfinished'])}</td><td>자동집계</td></tr><tr><td>당기 미완성 차감</td><td class="m">-{n(s['current_unfinished'])}</td><td>자동집계</td></tr><tr><td>VAT 신고 조정</td><td class="m">{n(s['vat_adjustment'])}</td><td>작업자 입력</td></tr><tr><td>기타 수동 조정</td><td class="m">{n(s['manual_adjustment'])}</td><td>작업자 입력</td></tr><tr class="total"><td>법인세 조정 순액</td><td class="m">{n(s['tax_flow_adjustment'])}</td><td>별도 검산값</td></tr></table></body></html>'''

def workbook(company,year,rows,flow_revenue,extra=None):
    data=[calc.recalculate(r) for r in rows if not r.get('deleted')];s=calc.summary(data,extra);w=openpyxl.Workbook();sh=w.active;sh.title=f'{year} 진행률관리'
    headers=['발주처','공사명','공사관리번호','착공일','준공일','계약공급가액','공종','전기수입','당기수입','전기원가','당기원가','예상원가율','예상누적수입','적정조정액','전기진행률조정','가져온당기조정','배분방식','최종당기진행율','상태','차기이월','이월메모','전기미완성','당기미완성','비고']
    sh.append([f'{year}년 공사수입·원가대비',company]);sh.append(headers)
    for r in data:sh.append([r['client'],r['project'],calc.project_key(r),r['start'],r['end'],r['contract'],r['trade'],r['prior_revenue'],r['current_revenue'],r['prior_cost'],r['current_cost'],r['expected_cost_rate'],r['expected_revenue'],r['calculated_adjustment'],r['prior_adjustment'],r['current_adjustment'],r.get('allocation_mode','auto'),calc.final_adjustment(r),r['status'],'Y' if r.get('carryover_eligible',1) else 'N',r.get('carryover_note',''),r['prior_unfinished'],r['current_unfinished'],r['note']])
    sh.freeze_panes='A3';sh.auto_filter.ref=f'A2:X{sh.max_row}';format_excel(sh)
    for cell in sh[2]:cell.fill=PatternFill('solid',fgColor='DCECE4');cell.font=Font(bold=True)
    for row in sh.iter_rows(min_row=3):row[11].number_format='0.000%'
    carry=w.create_sheet(f'{year+1} 차기이월');carry.append([f'{year+1}년 차기이월 공사',company]);carry.append(headers)
    for r in data:
        if not r.get('carryover_eligible',1) or calc.completed(r.get('status')):continue
        carry.append([r['client'],r['project'],calc.project_key(r),r['start'],r['end'],r['contract'],r['trade'],r['total_revenue'],0,r['total_cost'],0,r['expected_cost_rate'],r['total_revenue'],0,calc.final_adjustment(r),0,'auto',None,'진행중','Y',r.get('carryover_note',''),0,0,r['note']])
    carry.freeze_panes='A3';carry.auto_filter.ref=f'A2:X{carry.max_row}';format_excel(carry)
    for cell in carry[2]:cell.fill=PatternFill('solid',fgColor='DCECE4');cell.font=Font(bold=True)
    for row in carry.iter_rows(min_row=3):row[11].number_format='0.000%'
    x=w.create_sheet('흐름표 연동');x.append(['항목','금액','구분']);items=[('흐름표 공사수입',flow_revenue,'검산'),('현장표 당기 공사수입',s['table_revenue'],'검산'),('공사수입 차이',int(flow_revenue or 0)-s['table_revenue'],'자동'),('전기 진행률 조정 환입',-s['prior_adjustment'],'자동'),('당기 진행률 조정',s['current_adjustment'],'현장별 최종합계'),('전기 미완성 환입',s['prior_unfinished'],'자동'),('당기 미완성 차감',-s['current_unfinished'],'자동'),('VAT 신고 조정',s['vat_adjustment'],'입력'),('기타 수동 조정',s['manual_adjustment'],'입력'),('법인세 조정 순액',s['tax_flow_adjustment'],'별도 검산')]
    for row in items:x.append(row)
    format_excel(x);x.column_dimensions['A'].width=28;x.column_dimensions['B'].width=20
    for cell in x[1]:cell.fill=PatternFill('solid',fgColor='DCECE4');cell.font=Font(bold=True)
    out=BytesIO();w.save(out);return out.getvalue()
