"""Original-style A4 agreements and bilateral board resolutions; shared measured output."""
from html import escape
from io import BytesIO
from pathlib import Path
from datetime import timedelta
from zipfile import ZipFile,ZIP_DEFLATED
import base64,json,re
from PIL import Image,ImageDraw,ImageFont
from functools import lru_cache
import os
import a4_layout as a4
import related_loan_calc as calc
from loan_report import korean_amount

MM=72/25.4;LEFT=20*MM;TOP=20*MM;RIGHT=190*MM;BOTTOM=277*MM

@lru_cache(maxsize=32)
def font(size,bold=False):
 win=Path(os.environ.get('WINDIR','C:/Windows'))/'Fonts'
 names=[win/'gulim.ttc',Path('/usr/share/fonts/opentype/noto')/('NotoSansCJK-Bold.ttc' if bold else 'NotoSansCJK-Regular.ttc')]
 for name in names:
  if name.is_file():return ImageFont.truetype(str(name),round(size*a4.SCALE))
 return a4.font(size,bold)

def krdate(v):
 d=calc.day(v);return f'{d.year}년 {d.month}월 {d.day}일'
def money(v):return f'{calc.D(v):,.0f}'
def split_text(text,width,size):
 f=font(size);limit=width*a4.SCALE;out=[]
 for paragraph in str(text).replace('\t','    ').split('\n'):
  line=''
  for ch in paragraph:
   if line and f.getlength(line+ch)>limit:out.append(line);line=ch
   else:line+=ch
  out.append(line)
 return out

def block(kind,text='',columns=None):return dict(kind=kind,text=text,columns=columns)
def company_part(c,label):return [label,'회   사   명: '+c['name'],'법인등록번호: '+c.get('registration',''),'대 표  이 사: '+c.get('representative','')]
def interest_clause(t,rates,until):
 calc.rate_at(t,rates,until)
 points={calc.day(t['interest_start'])}
 points.update(calc.day(r['effective_date']) for r in rates if t['interest_start']<r['effective_date']<=until)
 seq=sorted(points);out=[]
 for i,d in enumerate(seq):
  rate,kb=calc.rate_at(t,rates,d)
  end=seq[i+1]-timedelta(days=1) if i+1<len(seq) else calc.day(until)
  if end<d:continue
  out.append((('차입일로부터 ' if i==0 and t['interest_start']==t['start'] else krdate(d)+'부터 ')+krdate(end)+'까지는 년이율 '+f'{rate:.2f}'+'%를 적용한다.'))
 return '\n'.join(out)
def agreement(t,lender,borrower,issued,until,rates):
 amount='일금 '+korean_amount(t['principal'])+'원 정 (₩ '+money(t['principal'])+')'
 maturity=t.get('agreement_maturity') or ('(을)의 차입일 '+krdate(t['start'])+'로부터 '+('1년 이내에' if calc.day(t['maturity'])==__import__('loan_calc').add_months(calc.day(t['start']),12) else krdate(t['maturity'])+'까지')+' 상환하여야 한다.')
 extension='단, (을)의 자금운영과 관련하여 부득이한 경우에는 상호협의하에 상환기간을 연장할 수 있다.'
 clauses=[('(제1조) (대여 및 차입금액)','(을)은 (갑)에게 '+amount+'을 차입한다.'),('(제2조) (상환기일)',maturity+'\n'+extension),('(제3조) (이자율)',t.get('agreement_interest') or interest_clause(t,rates,until)+'\n단, 시중은행의 여신금리변동에 따라 상호협의하에 이자율을 조정할 수 있다.'),('(제4조) (계산방법)',t.get('agreement_calculation') or '매월말일 기준으로 제3조에 대한 이자율을 적용 계산한다.'),('(제5조) (이자수수방법)',t.get('agreement_interest_payment') or '제3조와 제4조의에 따라 적용한 이자를 이자발생일로부터 1년이내에 상환하여야 한다.\n'+extension)]
 body=[block('title','금 전 거 래 약 정 서'),block('blank'),block('columns',columns=[company_part(lender,'■대 여 인(갑)'),company_part(borrower,'■차 입 인(을)')]),block('blank'),block('text','(갑)과 (을)의 자금의 대여 및 차용에 관한 금액에 대하여 다음과 같이 약정한다'),block('blank')]
 for heading,text in clauses:body.extend([block('bold',heading),block('indent',text),block('blank')])
 footer=[block('date',krdate(issued)),block('blank'),block('columns_sign',columns=[['(갑) '+lender['name'],'대표이사 '+lender.get('representative','')+'     (인)'],['(을) '+borrower['name'],'대표이사 '+borrower.get('representative','')+'     (인)']])]
 return dict(title='금전거래약정서',body=body,footer=footer,seals=[lender.get('seal',''),borrower.get('seal','')])
def board(t,company,counterparty,lending,meeting,until,rates):
 word='대여' if lending else '차입';directors=[r for r in company.get('directors',[]) if r.get('present')]
 intro=company.get('lending_intro' if lending else 'borrowing_intro') or ('당 사가 시행사인 {상대회사}의 아파트 신축분양과 관련한 아파트 시공권을 보장받기 위하여, 금전대차약정(자금대여)에 있어 하기의 조건으로 자금대여할 것을 결의함.' if lending else '당사의 아파트 신축분양 및 운영자금 조달을 위하여, 금전대차약정(자금차입)에 있어 하기의 조건으로 자금차입할 것을 결의함.')
 intro=intro.replace('{상대회사}',counterparty['name'])
 body=[block('title','이 사 회 결 의 서'),block('text','일     자 : '+krdate(meeting)),block('text','장     소 : '+company.get('place','본사 회의실')),block('text','이사 총수 : '+str(company.get('total_directors',0))+'명 중 출석이사 '+str(len(directors))+'명'),block('blank'),block('bold','안     건 : 금전대차약정(자금'+word+')'),block('blank'),block('text',intro),block('blank')]
 counterpart='회   사   명 : '+counterparty['name']+'\n              대 표  이 사 : '+counterparty.get('representative','')+'\n              법인등록번호 : '+counterparty.get('registration','')+'\n              주        소 : '+counterparty.get('address','')
 items=[('1. '+('대 여 처' if lending else '차 입 처')+' : ',counterpart),('2. '+word+'용도 : ',t.get('purpose','')),('3. 담보조건 : ',t.get('collateral','') if lending else re.sub(r'(?<![가-힣])당\s*사(?=[의\s])',lambda match:counterparty['name'],t.get('collateral',''))),('4. 대금금액 : ','일금 '+korean_amount(t['principal'])+'원정(₩'+money(t['principal'])+')'),('5. '+word+'일자 : ',krdate(t['start'])),('6. 상환일자 : ',t.get('board_maturity') or krdate(t['maturity'])+'\n(단, '+('대여처' if lending else '당사')+'의 자금운영과 관련하여 부득이한 경우 상호협의 하에 상환기간을 연장할수 있다.)'),('7. 이자적용 : ',t.get('board_interest') or interest_clause(t,rates,until).replace('차입일','대여일' if lending else '차입일')+'\n(단, 시중은행의 여신금융변동에 따라 상호협의 하에 이자율을 조정할 수 있다.)'),('8. 상환방법 : ',t.get('repayment','원리금 일시상환'))]
 body += [block('item',value,columns=label) for label,value in items]
 body += [block('blank'),block('bold','상기 내용에 대한 결의를 확인하고, 출석이사 서명 날인함.')]
 if t.get('collateral_list'):body.append(block('text','※첨부: 담보 물건 목록'))
 footer=[block('date',krdate(meeting)),block('company',company['name'])]+[block('sign',r['role']+' '+r['name']+'      (인)') for r in directors]
 return dict(title='이사회결의서',body=body,footer=footer,seals=[company.get('seal','')],directors=directors)

def measured(blocks):
 out=[]
 for b in blocks:
  kind=b['kind'];size=20 if kind=='title' else 11
  if kind=='blank':out.append(dict(kind=kind,height=8,elements=[]));continue
  if kind.startswith('columns'):
   els=[];height=0;width=(RIGHT-LEFT-6*MM)/2
   for col,lines in enumerate(b['columns']):
    y=0
    for index,line in enumerate(lines):
     wrapped=split_text(line,width,size)
     for part,text in enumerate(wrapped):
      els.append(dict(x=LEFT+col*(width+6*MM),dy=y,width=width,text=text,size=size,bold=index==0,align='left',seal_slot=col if kind=='columns_sign' and index==1 and part==len(wrapped)-1 else None));y+=17.6 if kind=='columns' or index==0 else 12*MM
    height=max(height,y)
   out.append(dict(kind=kind,height=height,elements=els));continue
  if kind=='item':
   width=RIGHT-LEFT-24*MM;lines=split_text('\n'.join(line.lstrip() for line in b['text'].split('\n')),width,size);els=[dict(x=LEFT,dy=0,width=24*MM,text=b['columns'],size=size,bold=False,align='left',seal_slot=None)]
   for index,text in enumerate(lines):els.append(dict(x=LEFT+24*MM,dy=index*17.6,width=width,text=text,size=size,bold=False,align='left',seal_slot=None))
   out.append(dict(kind=kind,height=len(lines)*17.6,elements=els));continue
  width=RIGHT-LEFT-(12*MM if kind=='indent' else 0);lines=split_text(b['text'],width,size);height=0;els=[]
  for text in lines:
   pitch=12*MM if kind=='sign' else 28 if kind=='title' else 17.6
   align='center' if kind in ['title','company','date'] else 'right' if kind=='sign' else 'left'
   els.append(dict(x=LEFT+(12*MM if kind=='indent' else 0),dy=height,width=width,text=text,size=size,bold=kind in ['bold','company'],align=align,seal_slot=0 if kind=='sign' and '대표' in b['text'] and text==lines[-1] else None));height+=pitch
  if kind=='title':height+=12
  out.append(dict(kind=kind,height=height,elements=els))
 return out

def paginate(doc):
 from itertools import groupby
 def rows(blocks):
  result=[]
  for b in measured(blocks):
   if not b['elements']:result.append(dict(elements=[],height=b['height']));continue
   groups=[(y,list(es)) for y,es in groupby(sorted(b['elements'],key=lambda e:e['dy']),key=lambda e:e['dy'])]
   for index,(y,es) in enumerate(groups):result.append(dict(elements=es,height=(groups[index+1][0] if index+1<len(groups) else b['height'])-y))
  return result
 pages=[[]];y=TOP
 issuer=next((b['text'] for b in doc['footer'] if b['kind']=='company'),'')
 def next_page():
  nonlocal y
  texts=split_text(doc['title']+' (계속)'+(' · '+issuer if issuer else ''),RIGHT-LEFT,11)
  pages.append([dict(x=LEFT,y=TOP+i*17.6,width=RIGHT-LEFT,text=text,size=11,bold=True,align='center',seal_slot=None) for i,text in enumerate(texts)]);y=TOP+len(texts)*17.6+8
 def put(row):
  nonlocal y
  if y+row['height']>BOTTOM:
   if not row['elements']:return
   next_page()
  for e in row['elements']:pages[-1].append(dict(e,y=y))
  y+=row['height']
 for row in rows(doc['body']):put(row)
 footer=rows(doc['footer']);height=sum(r['height'] for r in footer)
 if y+10+height<=BOTTOM:y=BOTTOM-height
 else:
  next_page()
  if y+height<=BOTTOM:y=BOTTOM-height
 for row in footer:put(row)
 return [p for p in pages if p]
CSS='''*{box-sizing:border-box}body{margin:0;background:#edf2ef;color:#111;font-family:Gulim,"굴림","Noto Sans CJK KR",sans-serif}.tools{padding:10px;text-align:right}.tools button{padding:9px 18px;background:#087b52;color:white;border:0}.a4{position:relative;width:210mm;height:297mm;margin:12px auto;background:white;box-shadow:0 2px 8px #0001}.line{position:absolute;margin:0;white-space:pre;line-height:1.5}.seal{position:absolute;width:12mm;height:12mm;object-fit:contain}@page{size:A4;margin:0}@media print{body{background:white}.tools{display:none}.a4{margin:0;box-shadow:none;break-after:page}.a4:last-child{break-after:auto}}'''

def seal_position(e):
 f=font(e['size'],e['bold']);width=f.getlength(e['text'])/a4.SCALE;x=e['x']
 if e['align']=='right':x+=e['width']-width
 if e['align']=='center':x+=(e['width']-width)/2
 marker=e['text'].rfind('(인)')
 center=x+(f.getlength(e['text'][:marker])+f.getlength('(인)')/2)/a4.SCALE if marker>=0 else x+width
 return max(e['x'],min(e['x']+e['width']-12*MM,center-6*MM))

def html(documents):
 pages=[]
 for doc in documents:
  for page in paginate(doc):
   parts=[]
   for e in page:
    parts.append('<p class="line" style="left:'+str(e['x'])+'pt;top:'+str(e['y'])+'pt;width:'+str(e['width'])+'pt;font-size:'+str(e['size'])+'pt;font-weight:'+('700' if e['bold'] else '400')+';text-align:'+e['align']+'">'+escape(e['text'])+'</p>')
    slot=e.get('seal_slot');seal=doc.get('seals',[])[slot] if slot is not None and slot<len(doc.get('seals',[])) else ''
    if seal.startswith(('data:image/png;base64,','data:image/jpeg;base64,')):parts.append('<img class="seal" style="left:'+str(seal_position(e)/MM)+'mm;top:'+str(e['y']/MM-2)+'mm" src="'+escape(seal)+'">')
   pages.append('<article class="a4">'+''.join(parts)+'</article>')
 return '<!doctype html><html lang="ko"><meta charset="utf-8"><style>'+CSS+'</style><div class="tools"><button onclick="window.print()">일괄 인쇄 / PDF 저장</button></div>'+''.join(pages)+'</html>'

def pdf(documents):
 out=BytesIO();out.write(b'%PDF-1.4\n%\xe2\xe3\xcf\xd3\n');offsets={};refs=[];count=0
 def obj(n,body):
  offsets[n]=out.tell();out.write(str(n).encode()+b' 0 obj\n'+body+b'\nendobj\n')
 for doc in documents:
  for page in paginate(doc):
   im=Image.new('RGB',(2480,3508),'white');draw=ImageDraw.Draw(im)
   for e in page:
    f=font(e['size'],e['bold']);length=draw.textlength(e['text'],font=f);x=e['x']*a4.SCALE
    if e['align']=='center':x+=(e['width']*a4.SCALE-length)/2
    if e['align']=='right':x+=e['width']*a4.SCALE-length
    draw.text((x,e['y']*a4.SCALE),e['text'],font=f,fill='#111',stroke_width=1 if e['bold'] and os.name=='nt' else 0,stroke_fill='#111')
    slot=e.get('seal_slot');seal=doc.get('seals',[])[slot] if slot is not None and slot<len(doc.get('seals',[])) else ''
    if seal:
     stamp=Image.open(BytesIO(base64.b64decode(seal.split(',',1)[1]))).convert('RGBA');stamp.thumbnail((int(12*MM*a4.SCALE),int(12*MM*a4.SCALE)))
     im.paste(stamp,(int(seal_position(e)*a4.SCALE),int((e['y']-2*MM)*a4.SCALE)),stamp)
   jpeg=BytesIO();im.save(jpeg,'JPEG',quality=90);blob=jpeg.getvalue();im.close();n=3+count*3;count+=1;refs.append(n)
   obj(n,f'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595.276 841.890] /Resources << /XObject << /I {n+1} 0 R >> >> /Contents {n+2} 0 R >>'.encode())
   obj(n+1,f'<< /Type /XObject /Subtype /Image /Width 2480 /Height 3508 /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode /Length {len(blob)} >>\nstream\n'.encode()+blob+b'\nendstream')
   content=b'q 595.276 0 0 841.890 0 0 cm /I Do Q';obj(n+2,f'<< /Length {len(content)} >>\nstream\n'.encode()+content+b'\nendstream')
 if not count:raise ValueError('출력할 문서를 선택하세요.')
 obj(1,b'<< /Type /Catalog /Pages 2 0 R >>');obj(2,('<< /Type /Pages /Count '+str(count)+' /Kids ['+' '.join(str(n)+' 0 R' for n in refs)+'] >>').encode());xref=out.tell();maximum=max(offsets)
 out.write(f'xref\n0 {maximum+1}\n0000000000 65535 f \n'.encode())
 for n in range(1,maximum+1):out.write(f'{offsets[n]:010} 00000 n \n'.encode())
 out.write(f'trailer\n<< /Size {maximum+1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF'.encode());return out.getvalue()


def bundle(data):
 from joint_letter_files import unpack
 out=BytesIO()
 with ZipFile(out,'w',ZIP_DEFLATED) as z:
  all_documents=[]
  for index,item in enumerate(data['items'],1):
   all_documents+=item['documents']
   folder=f'{index:03}'
   for i,doc in enumerate(item['documents'],1):
    name=folder+'/'+str(i)+'_'+doc['title']
    z.writestr(name+'.html',html([doc]).encode());z.writestr(name+'.pdf',pdf([doc]))
   for i,f in enumerate(item.get('files',[]),1):z.writestr(folder+'/첨부/'+str(i)+'_'+f['name'],unpack(f))
  z.writestr('전체_일괄인쇄.html',html(all_documents).encode())
 return out.getvalue()
