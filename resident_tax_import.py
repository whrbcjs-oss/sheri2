"""Read user-distributed building statements and legacy aggregate workbooks; never execute Excel code."""
from io import BytesIO
from datetime import datetime,date
from decimal import Decimal
import ast,re,zipfile
import openpyxl
from resident_tax_calc import dec,area

class Reader:
    def __init__(self,data):
        if len(data)>20*1024*1024:raise ValueError('엑셀은 20MB 이하로 업로드하세요.')
        try:
            with zipfile.ZipFile(BytesIO(data)) as z:
                if sum(i.file_size for i in z.infolist())>80*1024*1024:raise ValueError('압축 해제 용량이 너무 큽니다.')
            self.w=openpyxl.load_workbook(BytesIO(data),data_only=False);self.cache=openpyxl.load_workbook(BytesIO(data),data_only=True)
        except (zipfile.BadZipFile,KeyError,openpyxl.utils.exceptions.InvalidFileException):raise ValueError('올바른 XLSX 파일을 선택하세요.')
        if sum(s.max_row*s.max_column for s in self.w)>300000:raise ValueError('시트 크기가 너무 큽니다.')
    def value(self,s,coord,depth=0):
        if depth>20:raise ValueError('순환 수식을 확인하세요: '+coord)
        v=s[coord].value
        if v is None:
            for r in s.merged_cells.ranges:
                if coord in r:return self.value(s,s.cell(r.min_row,r.min_col).coordinate,depth+1) if coord!=s.cell(r.min_row,r.min_col).coordinate else None
        if not isinstance(v,str) or not v.startswith('='):return v
        expr=v[1:]
        if len(expr)>2048:raise ValueError('수식이 너무 깁니다: '+coord)
        if re.fullmatch(r'\$?[A-Z]+\$?\d+',expr):return self.value(s,expr.replace('$',''),depth+1)
        if re.fullmatch(r'[\d\s.()+*/\-]+',expr):
            def run(n):
                if isinstance(n,ast.Constant) and isinstance(n.value,(float,int)):return dec(n.value)
                if isinstance(n,ast.UnaryOp) and isinstance(n.op,(ast.USub,ast.UAdd)):return -run(n.operand) if isinstance(n.op,ast.USub) else run(n.operand)
                if isinstance(n,ast.BinOp) and isinstance(n.op,(ast.Add,ast.Sub,ast.Mult,ast.Div)):
                    a,b=run(n.left),run(n.right)
                    if isinstance(n.op,ast.Add):return a+b
                    if isinstance(n.op,ast.Sub):return a-b
                    if isinstance(n.op,ast.Mult):return a*b
                    return a/b
                raise ValueError('지원하지 않는 수식입니다.')
            try:
                tree=ast.parse(expr,mode='eval')
                if sum(1 for _ in ast.walk(tree))>256:raise ValueError('수식이 너무 복잡합니다: '+coord)
                return float(run(tree.body))
            except (SyntaxError,ZeroDivisionError,ArithmeticError,RecursionError):raise ValueError('수식을 확인하세요: '+coord)
        cached=self.cache[s.title][coord].value
        if cached is None:raise ValueError('수식 계산값이 없습니다. Excel에서 다시 계산·저장하세요: '+s.title+'!'+coord)
        return cached

def statement(data):
    r=Reader(data)
    for s in r.w:
        if '건물사용명세' not in str(s['A1'].value):continue
        get=lambda c:r.value(s,c)
        records=[]
        for n in range(10,s.max_row+1):
            if '면적' in str(get(f'A{n}') or '') and '합계' in str(get(f'A{n}') or ''):break
            if s[f'D{n}'].value is None:continue
            a=float(dec(get(f'D{n}')));t=get(f'F{n}')
            if not a and not any(get(f'{col}{n}') for col in ['A','B','C','E','G']):continue
            if not isinstance(t,(int,float,Decimal)):raise ValueError(f'{n}행 과세면적을 숫자로 입력하세요.')
            entered=get(f'C{n}');entered=entered.strftime('%Y-%m-%d') if isinstance(entered,(datetime,date)) else str(entered or '')
            records.append(dict(floor=str(get(f'A{n}') or ''),room=str(get(f'B{n}') or ''),entered=entered,area=a,purpose=str(get(f'E{n}') or ''),taxable=float(t),reason=str(get(f'G{n}') or ''),source_row=n))
        if not records:raise ValueError('건물 사용 내역이 없습니다.')
        totals=area(records);marker=str(get('E5') or '');m=re.search(r'(20\d{2})[.\-/]0?7[.\-/]0?1',marker)
        return dict(company=str(get('B3') or ''),site=str(get('B4') or ''),address=str(get('B5') or ''),phone=str(get('B7') or ''),reported=float(dec(get('B6'))),year=int(m.group(1)) if m else None,rows=records,**totals)
    raise ValueError('건물사용명세서 양식(A1 제목)을 찾을 수 없습니다.')

def aggregate(data):
    r=Reader(data);out=[];year=None;skipped=0
    for s in r.w:
        if not any('기본세액'==s.cell(n,4).value for n in range(1,s.max_row+1)):continue
        heading=str(s['B2'].value or '');m=re.search(r'(20\d{2})년',heading);year=int(m.group(1)) if m else None;company=''
        for n in range(1,s.max_row+1):
            b=s.cell(n,2).value
            if isinstance(b,str) and re.match(r'^\d+\.',b):company=re.sub(r'^\d+\.\s*','',b).strip()
            if s.cell(n,4).value!='기본세액':continue
            get=lambda col,offset=0:r.value(s,f'{col}{n+offset}')
            a=float(dec(get('E',1)));total=get('K',3)
            total=float(dec(total)) if total is not None else a
            if total<a:raise ValueError('집계표의 총면적이 과세면적보다 작습니다: '+str(n)+'행')
            basic=float(dec(get('E')));rate=float(dec(get('F',1)));edu=float(dec(get('F',2)))*100
            candidates=[str(get('J',i) or '') for i in range(4)]
            address=next((a for a in candidates if re.match(r'^(서울|부산|대구|인천|광주|대전|울산|세종|경기|강원|충청|충북|충남|전북|전남|전라|경상|경북|경남|제주|원주시|삼척시|강릉시|동해시)',a)), '')
            reductions=[]
            for i in range(3):
                # Old sheets used addition with signed reduction cells; normalize to positive reductions.
                h=float(dec(get('H',i)))
                if h>0:raise ValueError('감면 칸에 양수 가산 값이 있습니다. 원본을 확인하세요: '+str(n+i)+'행')
                reductions.append(-h)
            name=str(get('C') or '').strip()
            if name in ['', '0'] and basic==0 and a==0:
                skipped+=1;continue
            if not name or name=='0':raise ValueError('현장명이 없는 금액 행입니다: '+str(n))
            out.append(dict(company=company,site=name,address=address,phone='',reported=total,taxable=a,base=int(basic),rate=rate,education=edu,reduce_base=reductions[0],reduce_area=reductions[1],reduce_education=reductions[2],legacy_total=int(dec(get('I',3))),source_row=n))
    if not out:raise ValueError('주민세 집계표 양식을 찾을 수 없습니다.')
    return dict(year=year,sites=out,skipped=skipped)

def blank_statement(year=2026):
    w=openpyxl.Workbook();s=w.active;s.title='건물사용명세'
    for cell,text in {'A1':'건물사용명세서 신고','A2':'[주민세(사업소분) 과세자료]','A3':'법인명','A4':'사업장(공사명)','A5':'주소','A6':'전체면적','A7':'연락처','E5':f'{int(year)}.07.01 기준'}.items():s[cell]=text
    for i,name in enumerate(['층수','호수','최초입주일','사용면적(㎡)','사용 용도','과세구분','비고'],1):s.cell(9,i,name)
    for n in range(10,30):s.cell(n,4,0);s.cell(n,6,0)
    s['A30']='면적 합계';s['D30']='=SUM(D10:D29)';s['F30']='=SUM(F10:F29)'
    s.print_area='A1:G30';s.page_setup.orientation='landscape';s.page_setup.paperSize=s.PAPERSIZE_A4
    s.sheet_properties.pageSetUpPr.fitToPage=True;s.page_setup.fitToWidth=1;s.page_setup.fitToHeight=1
    from table_layout import format_excel
    format_excel(s)
    for col in 'ABCDEFG':s.column_dimensions[col].width=22
    out=BytesIO();w.save(out);return out.getvalue()
