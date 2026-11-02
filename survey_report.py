"""Original form artwork at 300 dpi, with only variable fields filled locally."""
from pathlib import Path
from io import BytesIO
import os,base64
from html import escape
from PIL import Image,ImageDraw,ImageFont
from survey_store import ITEMS,next_month
ROOT=Path(__file__).resolve().parent
SCALE=300/72

def font(size,bold=False):
 win=Path(os.environ.get('WINDIR','C:/Windows'))/'Fonts'
 names=[win/('malgunbd.ttf' if bold else 'malgun.ttf'),Path('/usr/share/fonts/opentype/noto')/('NotoSerifCJK-Bold.ttc' if bold else 'NotoSerifCJK-Regular.ttc'),Path('/System/Library/Fonts/AppleSDGothicNeo.ttc')]
 for name in names:
  if name.is_file():return ImageFont.truetype(str(name),round(size*SCALE))
 raise ValueError('한글 출력 글꼴을 찾지 못했습니다. Windows 맑은 고딕 글꼴을 확인하세요.')
def image(payload):
 im=Image.open(ROOT/'assets'/'bok_nonmanufacturing_blank.png').convert('RGB');draw=ImageDraw.Draw(im)
 def text(box,value,size=9,bold=False):
  value=str(value or '');x1,y1,x2,y2=[v*SCALE for v in box]
  # Fit to the existing cell without allowing text to cross borders.
  f=font(size,bold)
  while value and draw.textbbox((0,0),value,font=f)[2]>x2-x1 and size>4.5:size-=.25;f=font(size,bold)
  bb=draw.textbbox((0,0),value,font=f)
  if bb[2]>x2-x1:raise ValueError('출력 칸보다 긴 내용이 있습니다. 회사 기본정보를 줄여주세요.')
  draw.text(((x1+x2-bb[2])/2,(y1+y2-(bb[3]-bb[1]))/2-bb[1]),value,font=f,fill='black')
 m=payload['month'];n=next_month(m);p=payload['profile']
 text((167,111,428,125),f'({m[:4]}년 {int(m[5:])}월 동향 및 {n[:4]}년 {int(n[5:])}월 전망)',11,True)
 boxes={'name':(132,127,281,147),'phone':(338,127,416,147),'address':(132,149,416,175),'factory':(465,149,533,175),'product1':(144,177,307,191),'product2':(144,191,307,206),'export_ratio':(362,178,406,206),'employees':(465,178,517,206),'author':(108,210,161,229),'email':(204,210,388,229),'department':(419,210,453,229),'position':(479,210,533,229)}
 for k,box in boxes.items():text(box,p.get(k,''))
 text((518,178,533,206),'명')
 text((465,127,533,147),payload['written'][2:].replace('-','.'))
 for y in [352,440,506,615]:
  text((194,y+1,344,y+18),f'{m[:4]}년 {int(m[5:])}월중',9)
  text((346,y+1,507,y+18),f'{n[:4]}년 {int(n[5:])}월중(전망)',9)
 for (k,_,_,opts),(y1,y2) in zip(ITEMS,[(373,394),(461,482),(526,545),(547,566),(635,659)]):
  for side,x1,x2 in [('now',194,344),('next',346,507)]:
   value=payload.get(side,{}).get(k)
   for i,opt in enumerate(opts):
    left=x1+i*(x2-x1)/3;right=left+(x2-x1)/3
    text((left,y1,right,y2),opt+(' (○)' if value==opt else ' (  )'),9.5,True)
 text((183,690,202,702),payload.get('factor',''),10)
 if payload.get('factor')==13:text((207,776,290,788),payload.get('other',''),8)
 return im

def png(payload):
 stream=BytesIO();image(payload).save(stream,format='PNG');return stream.getvalue()
def pdf(payloads):
 if not payloads:raise ValueError('출력할 조사표가 없습니다.')
 pages=[image(p) for p in payloads];stream=BytesIO();pages[0].save(stream,format='PDF',save_all=True,append_images=pages[1:],resolution=300,quality=95);return stream.getvalue()
def html_preview(payloads):
 pictures=''.join('<img alt="기업경기조사표" src="data:image/png;base64,'+base64.b64encode(png(p)).decode()+'">' for p in payloads)
 return '<!doctype html><html lang="ko"><meta charset="utf-8"><title>기업경기조사표 출력</title><style>body{margin:0;background:#edf0f2;font:16px sans-serif}.tools{padding:16px;text-align:right}button{padding:10px 25px;color:white;background:#009f57;border:0;border-radius:5px}img{display:block;width:210mm;max-width:100%;height:auto;margin:16px auto;background:white}@page{size:A4;margin:0}@media print{body{background:white}.tools{display:none}img{width:210mm;max-width:none;height:297mm;margin:0;break-after:page}img:last-child{break-after:auto}}</style><div class="tools"><button onclick="window.print()">인쇄 / PDF 저장</button></div>'+pictures+'</html>'
