"""A4 cover and paginated uploaded investment ledger for a continuous print preview."""
from html import escape
import math
import a4_layout
from joint_store import num

def money(v):return f'{num(v):,.0f}'
WIDTHS=[20,24,32,61,27,22,22,22,27]
HEADERS=['기표일/원장번호','계정과목','거래처','적요·비고','세금계산서 공급가액','계산서','영수증','VAT','합계']
def wrapped(text,width):
 f=a4_layout.font(8.5);limit=(width-2)*a4_layout.MM*a4_layout.SCALE;lines=[]
 for paragraph in str(text).split('\n'):
  line=''
  for char in paragraph:
   if line and f.getlength(line+char)>limit:lines.append(line);line=char
   else:line+=char
  lines.append(line)
 return lines or ['']

def legacy_ledger_pages(data):
 rows=data.get('investment_rows',[]);pages=[];current=[];used=0
 for row in rows:
  total=sum((num(row[k]) for k in ['tax_supply','invoice','receipt','vat']),num(0))
  cells=[row['posting_date']+'\n#'+str(row['id']),row['account'],row['vendor'],row['description']+('\n비고: '+row['note'] if row['note'] else '')]+[money(row[k]) for k in ['tax_supply','invoice','receipt','vat']]+[money(total)]
  lines=[wrapped(value,width) for value,width in zip(cells,WIDTHS)];count=max(map(len,lines))
  for offset in range(0,count,24):
   part=[cell[offset:offset+24] if i<4 else cell if offset==0 else [] for i,cell in enumerate(lines)]
   height=max(max(map(len,part)),1)*4.2+2
   if current and used+height>116:pages.append(current);current=[];used=0
   current.append((row['id'],part,height));used+=height
 if current or not pages:pages.append(current)
 sums=[sum((num(row[k]) for row in rows),num(0)) for k in ['tax_supply','invoice','receipt','vat']];sums.append(sum(sums,num(0)))
 result=[]
 for index,page in enumerate(pages):
  body='<section class="a4-ledger-page"><h2>당사 투입비 원장 · '+str(index+1)+' / '+str(len(pages))+'</h2><p>'+escape(data['project']['name'])+' · 통보월 '+escape(data['start'])+' · 단위: 원</p><table class="a4-ledger-table"><colgroup>'+''.join('<col style="width:'+str(w)+'mm">' for w in WIDTHS)+'</colgroup><thead><tr>'+''.join('<th>'+escape(label)+'</th>' for label in HEADERS)+'</tr></thead><tbody>'
  for id,cells,height in page:
   body+='<tr data-ledger-id="'+str(id)+'" style="height:'+str(height)+'mm">'+''.join('<td class="'+('number' if i>=4 else 'text')+'">'+'<br>'.join(escape(line) for line in cell)+'</td>' for i,cell in enumerate(cells))+'</tr>'
  if not page:body+='<tr><td colspan="9">등록된 당사 투입비가 없습니다.</td></tr>'
  if index==len(pages)-1:body+='<tr class="grand-total"><td colspan="4" class="text">전체 합계</td>'+''.join('<td class="number">'+money(v)+'</td>' for v in sums)+'</tr>'
  body+='</tbody></table><div class="ledger-page-note">공문에 연결한 해당 통보월 당사 원장입니다. 발행본은 발행 당시 원장을 보존합니다.</div></section>'
  result.append(body)
 return ''.join(result)

CSS='''
@page{size:A4 portrait;margin:20mm}
@page investment-ledger{size:A4 landscape;margin:20mm}
.document-letter.letter-v2{width:297mm;max-width:297mm;min-width:210mm;padding:0;background:transparent;box-shadow:none}
.letter-v2 .official-letter{background:white;margin:0 auto;width:210mm;min-height:297mm;padding:20mm;display:flex;flex-direction:column;font-size:11pt;line-height:1.65}
.letter-v2 .official-letter>*{flex-shrink:0}.letter-v2 .letter-company{font-size:23pt;margin:0 0 9mm;line-height:1.3}
.letter-v2 .letter-address{font-size:8.5pt}.letter-v2 .letter-top{margin:7mm 0 3mm}.letter-v2 .letter-fields{padding:0;font-size:10pt}
.letter-v2 .letter-fields dt{flex-basis:21mm}.letter-v2 .letter-fields dd{overflow-wrap:anywhere}
.letter-v2 .letter-rule{width:100%;margin:3mm 0}.letter-v2 .letter-paragraphs{margin:4mm 0}.letter-v2 .letter-paragraphs p{margin:3mm 0;overflow-wrap:anywhere}
.letter-v2 .letter-table-wrap{margin:4mm 0 6mm}.letter-v2 table{font-size:9pt}.letter-v2 th,.letter-v2 td{white-space:normal;overflow-wrap:anywhere;padding:2mm 1mm}
.letter-v2 .letter-signature{margin: auto 0 0;min-height:25mm;padding-top:8mm;font-size:16pt;line-height:1.8;break-inside:avoid}
.letter-v2 .letter-signature:has(.seal){padding-right:28mm}.letter-v2 .seal{bottom:0;right:0;width:24mm;height:24mm}
.letter-v2 .a4-ledger-page{page:investment-ledger;width:297mm;min-height:210mm;background:white;padding:20mm;margin-top:12px;break-before:page;page-break-before:always}
.letter-v2 .a4-ledger-page h2{font-size:13pt;margin:0 0 3mm}.letter-v2 .a4-ledger-page>p{font-size:8pt;margin:0 0 4mm;overflow-wrap:anywhere}
.letter-v2 .a4-ledger-table{width:257mm;table-layout:fixed;border-collapse:collapse;font-size:8.5pt;line-height:1.25}
.letter-v2 .a4-ledger-table th,.letter-v2 .a4-ledger-table td{border:1px solid #555;padding:1mm;overflow-wrap:anywhere;vertical-align:middle}
.letter-v2 .a4-ledger-table th{background:#eef5f0}.letter-v2 .a4-ledger-table td.text{text-align:center}.letter-v2 .a4-ledger-table td.number{text-align:right}
.letter-v2 .ledger-page-note{font-size:7pt;margin-top:3mm;color:#666}
.letter-extra-names{font-size:9pt;line-height:1.5;overflow-wrap:anywhere}
.tools .file-links{font-size:12px;display:flex;gap:10px;flex-wrap:wrap}
@media print{
.document-letter.letter-v2{width:170mm;min-width:0;max-width:none;margin:0;padding:0;background:white}
.letter-v2 .official-letter{width:170mm;min-height:257mm;padding:0}
.letter-v2 .a4-ledger-page{width:257mm;min-height:0;padding:0;margin:0}
}
'''

CSS+='''
.letter-v2 .official-letter.letter-flow{display:block;min-height:0}
.letter-v2 .letter-flow .letter-signature{margin-top:12mm}
@media print{.letter-v2 .official-letter.letter-flow{display:block;min-height:0}}
'''
FIT_SCRIPT='''<script>(function(){function fit(){var e=document.querySelector('.letter-v2 .official-letter');if(e&&e.scrollHeight>1125)e.classList.add('letter-flow');}window.addEventListener('beforeprint',fit);if(document.fonts)document.fonts.ready.then(fit);window.addEventListener('load',fit);fit();})();</script>'''


def ledger_pages(data):
 if data.get("letter_layout_version",0)>=3:
  from joint_investment_print import render
  return render(data)
 return legacy_ledger_pages(data)

CSS+="""
.letter-v2 .letter-signature:has(.sender-lines){display:flex;align-items:center;justify-content:flex-end;gap:5mm;min-height:32mm;padding-right:0;letter-spacing:0}
.letter-v2 .sender-lines{width:51mm;max-width:calc(100% - 29mm);flex:0 1 51mm}
.letter-v2 .sender-line{display:flex;justify-content:space-between;width:100%;font-size:16pt;line-height:1.9;gap:0}
.letter-v2 .sender-line span{display:block;flex:0 0 auto}
.letter-v2 .letter-signature:has(.sender-lines) .seal{position:static;flex:0 0 24mm;width:24mm;height:24mm;object-fit:contain;align-self:center}
"""
