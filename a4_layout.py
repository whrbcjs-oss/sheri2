"""Measured A4 pagination shared by HTML, PDF and editable document output."""
from functools import lru_cache
from html import escape
from PIL import Image,ImageDraw
MM=72/25.4
WIDTH=210*MM;HEIGHT=297*MM;TOP=20*MM;BOTTOM=HEIGHT-20*MM;LEFT=20*MM;RIGHT=WIDTH-20*MM
SCALE=300/72

@lru_cache(maxsize=24)
def font(size,bold=False):
    from survey_report import font as load
    return load(size,bold)


def spec(kind):
    size=23 if kind=='title' else 16 if kind=='company' else 8.5 if kind=='small' else 11.5
    bold=kind in ['title','company','bold']
    return size,bold


def wrap(text,kind):
    size,bold=spec(kind);f=font(size,bold);width=(RIGHT-LEFT-2*MM)*SCALE
    result=[]
    for paragraph in str(text).replace('\t','    ').split('\n'):
        line=''
        for char in paragraph:
            if f.getlength(line+char)>width and line:result.append(line);line=char
            else:line+=char
        result.append(line)
    return result


def blocks(lines):
    result=[]
    for group,(kind,text) in enumerate(lines):
        if kind=='blank':result.append(dict(kind=kind,text='',height=3*MM,group=group));continue
        size,bold=spec(kind)
        for line in wrap(text,kind):result.append(dict(kind=kind,text=line,height=size*1.65,group=group,size=size,bold=bold))
        if kind=='title':result.append(dict(kind='blank',text='',height=7*MM,group=group))
    return result


def split(lines,style):
    index=next((i for i,(k,t) in enumerate(lines) if k=='center'),len(lines))
    if style=='board':return lines[:max(0,index-3)],lines[max(0,index-2):]
    footer=[]
    for k,t in lines[index:]:
        if k=='center' and t.startswith('위 차용인:'):k='sign_center'
        elif k=='center' and t.startswith('(연락처:'):k='contact'
        footer.append((k,t))
    return lines[:index],footer


def footer_blocks(lines,pitch,style):
    result=blocks(lines)
    for i,b in enumerate(result):
        k=b['kind']
        if k in ['sign','sign_center']:b['height']=pitch
        if k=='center':b['height']+=8*MM
        if k=='company' and style=='board':b['height']+=8*MM
    return result


def paginate(lines,style='board'):
    main,footer=split(lines,style);body=blocks(main);pages=[[]];y=TOP
    for b in body:
        if y+b['height']>BOTTOM and pages[-1]:pages.append([]);y=TOP
        if b['kind']!='blank':pages[-1].append(dict(b,y=y,footer=False))
        y+=b['height']
    while pages[-1] and pages[-1][-1]['kind']=='blank':pages[-1].pop()
    footer_base=footer_blocks(footer,12*MM,style)
    minimum=sum(b['height'] for b in footer_base)
    # Keep very large signature lists printable by continuing them on additional pages.
    if minimum>BOTTOM-TOP:
        sign_at=next((i for i,(k,t) in enumerate(footer) if k in ['sign','sign_center']),len(footer))
        prefix=footer[:sign_at];signs=footer[sign_at:]
        if len(signs)>1:
            mid=(len(signs)+1)//2
            return paginate(main+[('blank','')]+prefix+signs[:mid],style)+paginate(prefix+signs[mid:],style)
        pages=[[]];y=TOP
        for b in blocks(main)+footer_base:
            if y+b['height']>BOTTOM and pages[-1]:pages.append([]);y=TOP
            if b['kind']!='blank':pages[-1].append(dict(b,y=y,footer=True))
            y+=b['height']
        return [p for p in pages if p]
    y=max((b['y']+b['height'] for b in pages[-1]),default=TOP)
    if y+10*MM+minimum>BOTTOM:
        last=pages[-1];group=last[-1]['group'] if last else None
        moved=[]
        while last and last[-1]['group']==group:moved.insert(0,last.pop())
        if not last and len(pages)>1:pages.pop()
        pages.append([]);y=TOP
        for b in moved:
            if y+b['height']+minimum+10*MM>BOTTOM and pages[-1]:pages.append([]);y=TOP
            pages[-1].append(dict(b,y=y));y+=b['height']
        if y+minimum+10*MM>BOTTOM:pages.append([]);y=TOP
    room=BOTTOM-y-10*MM
    count=sum(1 for b in footer_base if b['kind'] in ['sign','sign_center'])
    pitch=min(20*MM,max(12*MM,12*MM+(room-minimum)/max(count,1)))
    tail=footer_blocks(footer,pitch,style);height=sum(b['height'] for b in tail)
    y=max(y+10*MM,BOTTOM-height)
    for b in tail:
        if b['kind']!='blank':pages[-1].append(dict(b,y=y,footer=True))
        y+=b['height']
    return [p for p in pages if p]


def alignment(kind,style):
    if kind=='sign':return 'right'
    if kind in ['title','center','contact','sign_center'] or kind=='company' and style=='board':return 'center'
    return 'left'


CSS='''*{box-sizing:border-box}body{margin:0;background:#edf2ef;color:#111;font-family:"Malgun Gothic","Noto Serif CJK KR",serif}.tools{text-align:right;padding:10px}.tools button{border:0;border-radius:5px;padding:9px 18px;background:#087b52;color:white;cursor:pointer}.a4-page{position:relative;width:210mm;height:297mm;margin:12px auto;background:white;box-shadow:0 2px 8px #0001}.a4-line{position:absolute;margin:0;white-space:pre;line-height:1.65}.a4-page-number{position:absolute;bottom:7mm;width:100%;text-align:center;font-size:8pt;color:#777}@page{size:A4;margin:0}@media print{body{background:white}.tools{display:none}.a4-page{margin:0;box-shadow:none;break-after:page;page-break-after:always}.a4-page:last-child{break-after:auto;page-break-after:auto}}'''


def html_pages(lines,style='board'):
    pages=paginate(lines,style);html=[]
    for index,page in enumerate(pages):
        items=[]
        for b in page:
            css=f"top:{b['y']:.3f}pt;left:{LEFT:.3f}pt;width:{RIGHT-LEFT:.3f}pt;font-size:{b['size']}pt;font-weight:{700 if b['bold'] else 400};text-align:{alignment(b['kind'],style)}"
            items.append('<p class="a4-line '+b['kind']+'" style="'+css+'">'+escape(b['text'])+'</p>')
        html.append('<article class="a4-page">'+''.join(items)+'<div class="a4-page-number">'+str(index+1)+' / '+str(len(pages))+'</div></article>')
    return ''.join(html)


def images(lines,style='board'):
    result=[]
    for page in paginate(lines,style):
        im=Image.new('RGB',(2480,3508),'white');draw=ImageDraw.Draw(im)
        for b in page:
            f=font(b['size'],b['bold']);width=draw.textlength(b['text'],font=f);align=alignment(b['kind'],style)
            x=(2480-width)/2 if align=='center' else RIGHT*SCALE-width if align=='right' else LEFT*SCALE
            draw.text((x,b['y']*SCALE),b['text'],font=f,fill='#111111')
        result.append(im)
    return result
