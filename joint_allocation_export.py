"""Numeric Excel and individual HTML bundles sharing the matrix's exact projection."""
from io import BytesIO
from zipfile import ZipFile,ZIP_DEFLATED
from decimal import Decimal
import re
import openpyxl
from openpyxl.styles import Font,PatternFill,Border,Side,Alignment
from openpyxl.utils import get_column_letter
import joint_allocation as matrix
from table_layout import format_excel

def workbook(data,month,member_ids=None,separate=False):
 members=matrix.selected_members(data,member_ids);member_total=separate or member_ids is not None;span=6 if member_total else 5;book=openpyxl.Workbook();book.remove(book.active)
 targets=[([m],m['name']) for m in members] if separate else [(members,'전체' if member_ids is None else '회원사')]
 for number,(ms,title) in enumerate(targets,1):
  title='전체 원가배분' if title=='전체' else title
  safe=re.sub(r'[\\/*?:\[\]]','_',title).strip() or '회원사';safe=safe[:25]+'_'+str(number);sheet=book.create_sheet(safe)
  cols=9+span*len(ms);sheet.merge_cells(start_row=1,start_column=1,end_row=1,end_column=cols);sheet.cell(1,1,'원가배분내역서 · '+data['project']['name']+' · '+month)
  sheet.merge_cells(start_row=2,start_column=1,end_row=4,end_column=1);sheet.cell(2,1,'과목');sheet.merge_cells(start_row=2,start_column=2,end_row=2,end_column=8);sheet.cell(2,2,'전체 공사원가')
  sheet.merge_cells(start_row=3,start_column=2,end_row=4,end_column=2);sheet.cell(3,2,'전월 공급가액 누계');sheet.merge_cells(start_row=3,start_column=3,end_row=3,end_column=6);sheet.cell(3,3,'당월 원가')
  for c,name in [(7,'VAT'),(8,'공급가액 누계')]:sheet.merge_cells(start_row=3,start_column=c,end_row=4,end_column=c);sheet.cell(3,c,name)
  for c,name in enumerate(['세금계산서','계산서','기타증빙','공급가액'],3):sheet.cell(4,c,name)
  for i,m in enumerate(ms):
   col=9+span*i;sheet.merge_cells(start_row=2,start_column=col,end_row=2,end_column=col+span-1);sheet.cell(2,col,m['name']);sheet.merge_cells(start_row=3,start_column=col,end_row=3,end_column=col+span-1);sheet.cell(3,col,str(m['share'])+'%'+(' (계약 '+str(m['contract_share'])+'%)' if m.get('contract_share') and str(m['share'])!=str(m['contract_share']) else ''))
   for c,name in enumerate(['세금계산서','계산서','기타','공급가액 계','VAT']+(['합계금액'] if member_total else []),col):sheet.cell(4,c,name)
  sheet.merge_cells(start_row=2,start_column=cols,end_row=4,end_column=cols);sheet.cell(2,cols,'비고')
  section_rows=[];sum_rows=[];highlights=[]
  for i,line in enumerate(data['lines'],5):
   if 'section' in line:sheet.cell(i,1,line['section']);section_rows.append(i)
   else:
    for c,value in enumerate(matrix.line_values(data,line,ms,member_total),1):
     cell=sheet.cell(i,c,int(value) if isinstance(value,Decimal) and value==value.to_integral_value() else float(value) if isinstance(value,Decimal) else value)
     if cell.data_type=='f':cell.data_type='s'
    if line.get('subtotal') or line.get('total'):sum_rows.append(i)
    if line.get('total') or line['label']=='공사원가 계':highlights.append(i)
  format_excel(sheet)
  thin=Side(style='thin',color='BACBC1');strong=Side(style='medium',color='176B44');boundaries=[2]+[9+span*i for i in range(len(ms))]+[cols]
  for row in sheet:
   for cell in row:
    cell.border=Border(left=strong if cell.column in boundaries else thin,right=thin,top=thin,bottom=thin)
    if cell.row<=4:cell.fill=PatternFill('solid',fgColor='EDF5EF');cell.font=Font(bold=True);cell.alignment=Alignment(horizontal='center',vertical='center',wrap_text=True)
    if cell.row in section_rows:cell.fill=PatternFill('solid',fgColor='E4F1E8');cell.font=Font(bold=True);cell.alignment=Alignment(horizontal='left' if cell.column==1 else 'center',vertical='center')
    if cell.row in sum_rows:cell.fill=PatternFill('solid',fgColor='DCECDF');cell.font=Font(bold=True)
    if cell.row in highlights:cell.fill=PatternFill('solid',fgColor='0A7048');cell.font=Font(bold=True,color='FFFFFF')
    if cell.data_type=='f':cell.data_type='s'
  for c in range(1,cols+1):sheet.column_dimensions[get_column_letter(c)].width=22 if c==1 else 17
  sheet.freeze_panes='C5';sheet.print_title_rows='1:4';sheet.sheet_properties.pageSetUpPr.fitToPage=True;sheet.page_setup.orientation='landscape';sheet.page_setup.paperSize=sheet.PAPERSIZE_A3;sheet.page_setup.fitToWidth=1;sheet.page_setup.fitToHeight=0
  sheet.print_area='A1:'+get_column_letter(cols)+str(sheet.max_row)
 out=BytesIO();book.save(out);return out.getvalue()

def bundle(data,month,member_ids,printable=True):
 members=matrix.selected_members(data,member_ids);out=BytesIO()
 with ZipFile(out,'w',ZIP_DEFLATED) as z:
  for i,m in enumerate(members,1):
   safe=re.sub(r'[\\/:*?"<>|]','_',m['name']).strip('. ') or '회원사'
   z.writestr(f'{i:02}_{safe}_원가배분내역서.html',matrix.render_matrix(data,month,printable,[m['id']]))
  z.writestr('회원사별_원가배분내역서.xlsx',workbook(data,month,[m['id'] for m in members],True))
 return out.getvalue()
