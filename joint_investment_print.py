"""Approved investment print design shared by standalone and letter appendix output."""
from html import escape
from decimal import ROUND_HALF_UP
import a4_layout
from joint_store import num

WIDTHS=[30,26,52,50,31,20,31,17]
HEADERS=['과목','일자','적요','거래처','공급가액','VAT','합계금액','비고']
BUDGET=106

def money(v):return f'{num(v).quantize(num(1),rounding=ROUND_HALF_UP):,}'
def wrap(value,width,size=8.5):
 font=a4_layout.font(size);limit=(width-2)*a4_layout.MM*a4_layout.SCALE;lines=[]
 for paragraph in str(value).split('\n'):
  line=''
  for char in paragraph:
   if line and font.getlength(line+char)>limit:lines.append(line);line=char
   else:line+=char
  lines.append(line)
 return lines or ['']
def cells(values,numeric):
 return ''.join('<td class="'+('number' if i in numeric else 'text')+'">'+('<br>'.join(escape(v) for v in value) if isinstance(value,list) else escape(str(value)))+'</td>' for i,value in enumerate(values))

def render(data):
 portrait=data.get('letter_layout_version',4)>=4
 widths=[20,21,25,24,25,18,26,11] if portrait else WIDTHS
 summary_widths=[26,22,15,22] if portrait else [38,29,17,26]
 budget=184 if portrait else BUDGET
 rows=data.get('investment_rows',[]);parts=[];accounts={};supply=vat=num(0)
 for row in rows:
  amount=sum((num(row[k]) for k in ['tax_supply','invoice','receipt']),num(0));tax=num(row['vat']);supply+=amount;vat+=tax
  bucket=accounts.setdefault(row['account'],[num(0),num(0)]);bucket[0]+=amount;bucket[1]+=tax
  values=[row['account'],row['posting_date'],row['description'],row['vendor'],money(amount),money(tax),money(amount+tax),row['note']]
  lines=[wrap(value,width) for value,width in zip(values,widths)]
  for offset in range(0,max(map(len,lines)),40 if portrait else 22):
   chunk=[line[offset:offset+(40 if portrait else 22)] if i not in [4,5,6] else line if offset==0 else [] for i,line in enumerate(lines)]
   parts.append(dict(id=row['id'],cells=chunk,height=max(7,max(max(map(len,chunk)),1)*4+2.4)))
 summary=[]
 for account,values in accounts.items():
  wrapped=[wrap(account,summary_widths[0],7.8)]+[wrap(money(value),width,7.8) for value,width in zip([*values,sum(values,num(0))],summary_widths[1:])]
  summary.append(dict(cells=wrapped,height=max(map(len,wrapped))*3.6+2.4))
 chunks=[];chunk=[];height=21
 for row in summary:
  if chunk and height+row['height']>(166 if portrait else 96):chunks.append(chunk);chunk=[];height=21
  chunk.append(row);height+=row['height']
 chunks.append(chunk)
 pages=[];front=list(parts);tail=[]
 if len(chunks)==1:
  room=max(0,budget-36-sum(row['height'] for row in chunks[0]));used=0
  while front and used+front[-1]['height']<=room:
   row=front.pop();tail.insert(0,row);used+=row['height']
 current=[];used=0
 for row in front:
  if current and used+row['height']>budget:pages.append(dict(rows=current));current=[];used=0
  current.append(row);used+=row['height']
 if current:pages.append(dict(rows=current))
 if len(chunks)==1:pages.append(dict(rows=tail,summary=chunks[0],final=True))
 else:
  if pages and sum(row['height'] for row in pages[-1]['rows'])+8<=budget:pages[-1]['total']=True
  else:pages.append(dict(rows=[],total=True))
  pages += [dict(rows=[],summary=chunk,final=index==len(chunks)-1) for index,chunk in enumerate(chunks)]
 result=[]
 for index,page in enumerate(pages):
  body='<section class="a4-ledger-page investment-page'+(' investment-portrait' if portrait else '')+'"><div class="investment-accent"></div><div class="investment-eyebrow">공동도급 공사 · 원가 증빙</div><div class="investment-heading"><h1>공동원가 투입내역</h1><span>금액 단위 : 원</span></div><div class="investment-project">'+escape(data['project']['name'])+'</div>'
  show_detail=bool(page['rows']) or (not rows and index==0) or page.get('total') or (page.get('final') and len(chunks)==1)
  if show_detail:
   body+='<div class="investment-section"><strong>■ 상세 투입내역</strong><span>'+str(len(rows))+'건</span></div><table class="investment-detail"><colgroup>'+''.join('<col style="width:'+str(width)+'mm">' for width in widths)+'</colgroup><thead><tr>'+''.join('<th>'+label+'</th>' for label in HEADERS)+'</tr></thead><tbody>'
   for row in page['rows']:body+='<tr data-ledger-id="'+str(row['id'])+'" style="height:'+str(row['height'])+'mm">'+cells(row['cells'],[4,5,6])+'</tr>'
   if not rows:body+='<tr><td colspan="8">등록된 당사 투입비가 없습니다.</td></tr>'
   if page.get('total') or (len(chunks)==1 and page.get('final')):body+='<tr class="investment-total"><td colspan="4">총 합 계</td>'+cells([money(supply),money(vat),money(supply+vat),''],[0,1,2])+'</tr>'
   body+='</tbody></table>'
  if 'summary' in page:
   body+='<div class="investment-summary"><h2>계정과목별 집계'+(' · 계속' if len(chunks)>1 and index<len(pages)-1 else '')+'</h2><table><colgroup>'+''.join('<col style="width:'+str(width)+'mm">' for width in summary_widths)+'</colgroup><thead><tr><th>계정과목</th><th>공급가액</th><th>VAT</th><th>합계금액</th></tr></thead><tbody>'
   for row in page['summary']:body+='<tr>'+cells(row['cells'],[1,2,3])+'</tr>'
   if page.get('final'):body+='<tr class="investment-total">'+cells(['총 합 계',money(supply),money(vat),money(supply+vat)],[1,2,3])+'</tr>'
   body+='</tbody></table></div>'
  body+='<div class="investment-footer"><span>HS 경리Job’s · 공동원가 투입내역</span><span>'+str(index+1)+' / '+str(len(pages))+'</span></div></section>'
  result.append(body)
 return ''.join(result)

CSS='''
.letter-v2 .investment-page{position:relative;color:#202e28;font-family:"Malgun Gothic","Noto Sans CJK KR",sans-serif}
.investment-page .investment-accent{height:1.2mm;width:11mm;background:#17674f;margin-bottom:3mm}
.investment-page .investment-eyebrow{font-size:7pt;letter-spacing:1.5px;color:#61776b;font-weight:700}
.investment-page .investment-heading{display:flex;justify-content:space-between;align-items:end;border-bottom:1.5px solid #24523e;padding-bottom:4mm;margin:1mm 0 4mm}
.letter-v2 .investment-page h1{font-size:20pt;letter-spacing:1px;color:#214c38;line-height:1.25;margin:0}
.investment-heading span,.investment-section span{font-size:7pt;color:#74867b}
.investment-page .investment-project{font-size:10pt;font-weight:700;margin-bottom:5mm}
.investment-page .investment-section{display:flex;justify-content:space-between;align-items:center;margin-bottom:2mm;font-size:8.5pt}
.letter-v2 .investment-page table{width:257mm;border-collapse:collapse;table-layout:fixed;font-size:8.5pt;line-height:1.3;font-variant-numeric:tabular-nums}
.letter-v2 .investment-page th{background:#edf3ef;color:#214b3a;border:0;border-top:1px solid #9db1a4;border-bottom:1px solid #b1bfb7;font-weight:700;padding:1.8mm 1mm;text-align:center;overflow-wrap:anywhere}
.letter-v2 .investment-page td{border:0;border-bottom:1px solid #dfe7e2;padding:1mm;white-space:normal;overflow-wrap:anywhere;vertical-align:middle}
.letter-v2 .investment-page tbody tr:nth-child(even){background:#fafcfb}
.letter-v2 .investment-page td.text{text-align:center}.letter-v2 .investment-page td.number{text-align:right}
.letter-v2 .investment-page tr.investment-total td{font-weight:800!important;background:#e5efe9!important;border-top:1.5px solid #527863!important;border-bottom:1.5px solid #527863!important;font-size:9pt;padding:2mm 1mm;text-align:right}
.letter-v2 .investment-page tr.investment-total td:first-child{text-align:center}
.letter-v2 .investment-page .investment-summary{width:110mm;margin:6mm 0 0 auto;break-inside:avoid}
.letter-v2 .investment-summary h2{font-size:9pt;margin:0 0 2mm;color:#253b2e}
.letter-v2 .investment-summary table{width:110mm;font-size:7.8pt}
.letter-v2 .investment-summary td,.letter-v2 .investment-summary th{padding:1mm}
.letter-v2 .investment-summary tr.investment-total td{font-size:8pt;padding:1.5mm 1mm}
.investment-footer{display:flex;justify-content:space-between;border-top:1px solid #dfe7e2;padding-top:2mm;margin-top:5mm;font-size:7pt;color:#7e8e83}
@media print{.investment-page,.investment-page th,.investment-page td{print-color-adjust:exact;-webkit-print-color-adjust:exact}}
'''

def document(data):
 from joint_letter_pages import CSS as common_css
 return '<!doctype html><html lang="ko"><meta charset="utf-8"><title>공동원가 투입내역</title><style>*{box-sizing:border-box}body{margin:0;background:#edf0ee}.tools{padding:10px;text-align:right}.tools button{padding:8px 16px;cursor:pointer}@media print{.tools{display:none}}'+common_css+CSS+'</style><body><div class="tools"><button onclick="window.print()">인쇄 / PDF 저장</button></div><main class="document-letter letter-v2'+(' investment-document-portrait' if data.get('letter_layout_version',4)>=4 else '')+'">'+render(data)+'</main></body></html>'

CSS+='''
@page investment-portrait{size:A4 portrait;margin:20mm}
.document-letter.letter-v2.investment-document-portrait{width:210mm;max-width:210mm}
.letter-v2 .investment-portrait{page:investment-portrait;width:210mm;min-height:297mm;margin-left:auto;margin-right:auto}
.letter-v2 .investment-portrait table{width:170mm;font-size:8pt}
.letter-v2 .investment-portrait td.number{white-space:nowrap;overflow-wrap:normal;font-size:7.5pt}
.letter-v2 .investment-portrait tr.investment-total td.number{font-size:8pt}
.letter-v2 .investment-portrait h1{font-size:18pt}
.letter-v2 .investment-portrait .investment-summary{width:85mm}
.letter-v2 .investment-portrait .investment-summary table{width:85mm;font-size:7.5pt}
@media print{.document-letter.letter-v2.investment-document-portrait{width:170mm;max-width:none}.letter-v2 .investment-portrait{width:170mm;min-height:0;padding:0;margin:0}}
'''
