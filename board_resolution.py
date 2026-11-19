"""Editable board-resolution templates and A4 print/PDF/DOCX output."""
from datetime import date
from html import escape
from io import BytesIO
from zipfile import ZipFile,ZIP_DEFLATED
from xml.sax.saxutils import escape as xml_escape
from PIL import Image,ImageDraw
import loan_calc as calc
import a4_layout as a4
from loan_report import korean_amount

TOPICS=['금전대차약정·자금대여','전자단기사채·신탁 투자','관계회사 금전소비대차 협정','기타 안건 직접 작성']


def birth(value):
    digits=''.join(c for c in str(value) if c.isdigit())
    if len(digits)==8:return digits[:4]+'.'+digits[4:6]+'.'+digits[6:]
    if len(digits)>=6:return digits[:2]+'.'+digits[2:4]+'.'+digits[4:6]
    return ''


def template(topic,f):
    money=lambda k:'일금 '+korean_amount(f.get(k,0))+'원정 (₩'+calc.money(f.get(k,0))+')'
    if topic==TOPICS[0]:
        lines=['당사의 자금 운영을 위하여 다음 조건으로 금전대차약정(자금대여)을 체결할 것을 결의함.','', '1. 차용인: '+f.get('name',''),'   생년월일 / 법인 식별정보: '+f.get('birth',''),'   주소: '+f.get('address',''),'2. 대여금액: '+money('amount'),'3. 대여일/차용시작일: '+str(f.get('start','')),'4. 상환일자: '+str(f.get('end','')),'5. 이자 적용: '+f.get('interest',''),'6. 상환방법: '+f.get('repayment','')]
        if f.get('collateral'):lines.append('7. 담보·기타 조건: '+f['collateral'])
    elif topic==TOPICS[1]:lines=['당사의 자금 운영을 위하여 다음 조건으로 전자단기사채·신탁 투자를 진행할 것을 결의함.','','1. 상품명: '+f.get('product',''),'2. 종목명: '+f.get('security',''),'3. 투자금액: '+money('amount'),'4. 발행일자: '+str(f.get('start','')),'5. 신탁만기일자: '+str(f.get('end','')),'6. 예상 수익률 및 보수: '+f.get('yield',''),'7. 신용공여·신용보강 사항: '+f.get('credit','')]
    elif topic==TOPICS[2]:lines=['당사의 자금 운영 및 관계회사 간 자금 효율성 제고를 위하여 다음 조건으로 금전소비대차 기본협정을 체결할 것을 결의함.','','1. 거래 상대방: '+f.get('counterparty',''),'2. 최고 거래한도: '+money('amount'),'3. 협정기간: '+f.get('period',''),'4. 자동연장 조건: '+f.get('extension',''),'5. 이자율 기준: '+f.get('interest',''),'6. 이자 지급방식: '+f.get('repayment','')]
    else:return ''
    return '\n'.join(lines)


def validate(data,final=False):
    v=dict(data)
    for key in ['company','title','body','place']:v[key]=str(v.get(key,'')).strip()
    if not v['company']:raise ValueError('회의를 개최하는 회사를 입력하세요.')
    if v.get('topic') not in TOPICS:raise ValueError('안건 유형을 선택하세요.')
    v['meeting_date']=calc.day(v.get('meeting_date')).isoformat()
    v['total_directors']=int(v.get('total_directors',0))
    if not 0<=v['total_directors']<=100:raise ValueError('이사 총수는 0~100명으로 입력하세요.')
    members=[]
    for row in v.get('members',[]):
        name=str(row.get('name','') or '').strip();role=str(row.get('role','') or '').strip();present=bool(row.get('present',False))
        if final and present and (not name or not role):raise ValueError('출석으로 선택한 이사의 직위와 성명을 입력하세요.')
        if name:members.append(dict(name=name,role=role,present=present))
    if len({(m['role'].replace(' ',''),m['name'].replace(' ','')) for m in members})!=len(members):raise ValueError('이사 명단에 같은 직위·성명이 중복되어 있습니다.')
    attendance=sum(m['present'] for m in members)
    if v['total_directors']<len(members):raise ValueError('이사 총수는 입력한 이사 명단 인원 이상이어야 합니다.')
    if final and (not v['title'] or not v['body'] or not v['place'] or attendance==0):raise ValueError('확정하려면 안건 제목·본문·회의 장소와 출석이사를 입력하세요.')
    v.update(members=members,attendance=attendance,status='final' if final else 'draft')
    return v


def lines(v):
    stamp='확정본' if v.get('status')=='final' else '작성중 · 초안'
    if v.get('number'):stamp+=' · '+v['number']+' · v'+str(v.get('version',1))
    result=[('title','이 사 회 결 의 서'),('small',stamp),('body','일자: '+v['meeting_date']),('body','장소: '+v.get('place','')),('body',f"이사 총수: {v['total_directors']}명 중 출석이사 {v['attendance']}명"),('body','안건: '+v.get('title','')),('blank','')]
    result.extend(('body',s) if s else ('blank','') for s in v.get('body','').splitlines())
    result.extend([('blank',''),('body','상기 내용에 대한 결의를 확인하고, 출석이사 서명 날인함.'),('blank',''),('center',v['meeting_date']),('company',v['company'])])
    result.extend(('sign',m['role']+' '+m['name']+'      (인)') for m in v['members'] if m['present'])
    return result


CSS=a4.CSS


def html(v):
    body=a4.html_pages(lines(v),'board')
    return '<!doctype html><html lang="ko"><meta charset="utf-8"><title>이사회 결의서</title><style>'+CSS+'</style><body><div class="tools"><button onclick="window.print()">인쇄 / PDF 저장</button></div>'+body+'</body></html>'


def pdf(v):
    pages=a4.images(lines(v),'board');out=BytesIO()
    pages[0].save(out,format='PDF',save_all=True,append_images=pages[1:],resolution=300)
    return out.getvalue()


def docx(v):
    """Minimal valid OOXML; editable in word processors that open DOCX, including Hangul."""
    paragraphs=[]
    for page_index,page in enumerate(a4.paginate(lines(v),'board')):
        previous=a4.TOP
        for index,b in enumerate(page):
            align=a4.alignment(b['kind'],'board');size=round(b['size']*2);line=b['size']*1.65
            gap=max(0,b['y']-previous);previous=b['y']+line
            props='<w:jc w:val="'+align+'"/><w:spacing w:before="'+str(round(gap*20))+'" w:after="0" w:line="'+str(round(line*20))+'" w:lineRule="exact"/>'
            if page_index and index==0:props+='<w:pageBreakBefore/>'
            if b['footer'] and index<len(page)-1:props+='<w:keepNext/>'
            paragraphs.append('<w:p><w:pPr>'+props+'</w:pPr><w:r><w:rPr><w:rFonts w:ascii="Malgun Gothic" w:eastAsia="맑은 고딕"/><w:sz w:val="'+str(size)+'"/>'+('<w:b/>' if b['bold'] else '')+'</w:rPr><w:t xml:space="preserve">'+xml_escape(b['text'])+'</w:t></w:r></w:p>')
    document='<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'+''.join(paragraphs)+'<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1134" w:bottom="1134" w:left="1134" w:right="1134"/></w:sectPr></w:body></w:document>'
    content='''<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>'''
    rels='''<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>'''
    out=BytesIO()
    with ZipFile(out,'w',ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml',content);z.writestr('_rels/.rels',rels);z.writestr('word/document.xml',document)
    return out.getvalue()
