"""Compact three-panel nonlead overview followed by payment approval row."""
from html import escape
from joint_store import num

def esc(v):return escape(str(v if v is not None else ''))
def money(v):return '—' if v is None else f'{num(v):,.0f}'
def percent(v):return '—' if v is None else f'{num(v):,.2f}%'
def table(headers,rows,money_cols=()):
 return '<table><thead><tr>'+''.join('<th>'+esc(x)+'</th>' for x in headers)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td'+(' class="number"' if i in money_cols else ' class="text"')+'>'+esc(money(x) if i in money_cols else x)+'</td>' for i,x in enumerate(row))+'</tr>' for row in rows)+'</tbody></table>'
CSS='''<style>.nonlead-status{margin-top:14px;border-top:2px solid #396653;padding-top:10px;break-inside:avoid}.nonlead-status h2{font-size:15px;margin:0 0 5px;color:#133e2b}.nonlead-status .status-panels{display:grid;grid-template-columns:1fr .95fr 1.55fr;gap:16px;align-items:start}.nonlead-status table{width:100%;border-collapse:collapse;font-size:11px;table-layout:fixed}.nonlead-status .status-panels>div{min-width:0}.nonlead-status td,.nonlead-status th{border:1px solid #789185;padding:4px 3px;white-space:normal;overflow-wrap:anywhere}.nonlead-status td.number{text-align:right;white-space:nowrap}.nonlead-status td.text{text-align:center}.nonlead-status th{background:#e8f4ed}.nonlead-status tr:last-child{font-weight:700;background:#f2f7f3}.nonlead-status .status-payment{margin-top:12px}.nonlead-status p{font-size:10px;margin:5px 0;color:#52675a}@media print{.nonlead-status table{font-size:7pt}.nonlead-status th,.nonlead-status td{padding:2px 1px}.nonlead-status h2{font-size:9pt}.nonlead-status p{font-size:6.5pt}.nonlead-status .status-panels{gap:8px}.nonlead-status{margin-top:7px;padding-top:6px}.nonlead-status .status-payment{margin-top:7px}}@media screen and (max-width:1000px){.nonlead-status .status-panels{grid-template-columns:1fr;gap:14px}}</style>'''
def render(s):
 cumulative=s.get('aggregation')=='cumulative'
 scope_label='최초 등록월 ~ '+s['month']+' 누계' if cumulative else '정산 대상월 '+', '.join(s.get('claim_months',[s['month']]))
 costs=[[r['category'],r['target'],r['excluded'],r['total']] for r in s['investment_rows']]
 costs.append(['합계']+[sum((num(r[k]) for r in s['investment_rows']),num(0)) for k in ['target','excluded','total']])
 cash=s['cash'];flow=[['수입',cash['income'],cash['earned']],['지출(전회까지)',cash['previous'],cash['previous']],['지출(금회예정)',cash['current'],cash['current']],['보험료·안분제외',cash['extra'],cash['extra']],['지출총계',cash['spending'],cash['spending']],['수입−지출',cash['cash_balance'],cash['earned_balance']]]
 contract=[[r['name'],str(r['share'])+'%',r['contract'],r['previous'],r['current'],r['cumulative'],percent(r['rate'])] for r in s['contracts']]
 totals={k:sum((num(r[k]) for r in s['contracts']),num(0)) for k in ['contract','previous','current','cumulative']}
 total_rate=str(totals['cumulative']/totals['contract']*100) if totals['contract'] else None
 contract.append(['전체분','100%',totals['contract'],totals['previous'],totals['current'],totals['cumulative'],percent(total_rate)])
 b=s['payment'];body=CSS+'<section class="nonlead-status"><div class="status-panels"><div><h2>■ 당사 투입비 내역</h2>'+table(['구분','안분대상액','안분제외액','계'],costs,[1,2,3])+'<p>'+(esc(scope_label) if s.get('schema_version',0)>=10 else '기준월 '+esc(s['month']))+' · '+esc(s['source_label'])+'</p></div>'
 body+='<div><h2>■ 수입·지출 현황 (공급가액)</h2>'+table(['구분','입금 기준','기성 기준'],flow,[1,2])
 if s.get('schema_version',0)<10:body+=table(['대비율',percent(cash['cash_ratio']),percent(cash['earned_ratio'])],[])+'<p>기성 집계: '+esc(s['income_scope'])+' / 대비율: '+esc(s['ratio'])+'</p>'
 body+='</div>'
 body+='<div><h2>● 계약·실기성 현황</h2><p>기준일: '+esc(s['as_of'])+'</p>'+table(['법인','지분율','계약금액(공급가액)','전회까지','금회','합계','기성률'],contract,[2,3,4,5])+'</div></div>'
 if s.get('schema_version',0)>=8:
  payment=[[b['claim'],b['paid'],b['prior_balance'],b['offset'],b['planned'],None]]
  body+='<p>'+('집계 범위: ' if cumulative else '정산 대상월: ')+esc(scope_label)+' · 정산 건: '+esc(s['run_name'])+' · 계산 기준: '+esc(s.get('source_mode','현황 저장값'))+'</p><div class="status-payment">'+table(['① 청구금액(공급가액+부가세)','② 기지급액','③ 전회미지급/유보액','④ 당사투입비/선금반제','⑤ 지급예정액','⑥ 승인액'],payment,[0,1,2,3,4])+'</div><p>⑤ = ① − ② − ③ − ④. '+('④의 당사투입비는 안분제외액을 제외합니다. 금회예정 = ⑤ − 선택 원가배분 VAT. ' if s.get('schema_version',0)>=11 else '')+'승인액은 대표이사 수기 작성란입니다. '+('모든 금액은 기준월까지 누계입니다.' if cumulative else '수금·지급은 기준일까지 누계, 당사투입비는 정산 대상월 공급가액입니다.')+'</p>'
 else:
  payment=[[s['month']+' 원가배분',b['claim'],b['paid'],b['prior_balance'],num(b['investment_offset'])+num(b['advance']),b['planned'],b['approved']]]
  body+='<p>'+('집계 범위: ' if cumulative else '정산 대상월: ')+esc(scope_label)+' · 정산 건: '+esc(s['run_name'])+' · 계산 기준: '+esc(s.get('source_mode','현황 저장값'))+'</p><div class="status-payment">'+table(['구분','청구금액(부가세 포함)','기지급액','전회미지급·유보액','추가 당사투입비·선금반제','지급 예정액','승인액'],payment,[1,2,3,4,5,6])+'</div>'
 body+='</section>'

 return body

def excel(s):
 from io import BytesIO
 import pandas as pd
 from table_layout import format_excel
 def number(v):return None if v is None else int(num(v)) if num(v)==int(num(v)) else float(num(v))
 costs=[{'구분':r['category'],'안분대상액':number(r['target']),'안분제외액':number(r['excluded']),'계':number(r['total'])} for r in s['investment_rows']]
 contracts=[{'법인':r['name'],'지분율(%)':number(r['share']),'계약금액':number(r['contract']),'전회까지':number(r['previous']),'금회':number(r['current']),'합계':number(r['cumulative']),'기성률(%)':number(r['rate'])} for r in s['contracts']]
 cash=s['cash'];cash_rows=[{'구분':label,'입금 기준':number(cash[a]),'기성 기준':number(cash[b])} for label,a,b in [('수입','income','earned'),('지출(전회까지)','previous','previous'),('지출(금회예정)','current','current'),('보험료·안분제외','extra','extra'),('지출총계','spending','spending'),('수입−지출','cash_balance','earned_balance')]]
 costs.append({'구분':'합계',**{k:sum(row[k] for row in costs) for k in ['안분대상액','안분제외액','계']}})
 totals={k:sum(row[k] for row in contracts) for k in ['계약금액','전회까지','금회','합계']}
 contracts.append({'법인':'전체 합계','지분율(%)':100,**totals,'기성률(%)':totals['합계']/totals['계약금액']*100 if totals['계약금액'] else None})
 p=s['payment'];payment=[{'구분':s['month']+' 원가배분','청구금액':number(p['claim']),'기지급액':number(p['paid']),'전회미지급·유보액':number(p['prior_balance']),'추가 당사투입비':number(p['investment_offset']),'추가 선금반제':number(p['advance']),'지급예정액':number(p['planned']),'승인액':number(p['approved'])}]
 if s.get('schema_version',0)>=8:
  payment=[{'① 청구금액':number(p['claim']),'② 기지급액':number(p['paid']),'③ 전회미지급/유보액':number(p['prior_balance']),'④ 당사투입비/선금반제':number(p['offset']),'⑤ 지급예정액':number(p['planned']),'⑥ 승인액':None}]
 out=BytesIO()
 with pd.ExcelWriter(out,engine='openpyxl') as writer:
  for title,rows in [('당사투입비',costs),('계약실기성',contracts),('수입지출',cash_rows),('지급예정',payment)]:
   pd.DataFrame(rows).to_excel(writer,index=False,sheet_name=title);sheet=writer.sheets[title];format_excel(sheet);sheet.freeze_panes='B2'
   for col in sheet.columns:
    sheet.column_dimensions[col[0].column_letter].width=23
    for cell in col[1:]:
     if '(%)' in str(col[0].value):cell.number_format='0.00"%"'
     if cell.data_type=='f':cell.data_type='s'
  if s.get('aggregation')=='cumulative':
   pd.DataFrame([{'집계방식':'기준월까지 누계','기준월':s['month'],'기준일':s['as_of'],'집계범위':'최초 등록월 ~ '+s['month']}]).to_excel(writer,index=False,sheet_name='집계기준');format_excel(writer.sheets['집계기준'])
 return out.getvalue()
