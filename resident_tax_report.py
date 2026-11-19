"""Review-oriented registers and exports, separated by company and jurisdiction."""
from io import BytesIO
from html import escape
from collections import defaultdict
import pandas as pd
import resident_tax_store as db
from table_layout import format_excel

MONEY=['기본세액','연면적세액','지방교육세','합계','납부액','미납잔액','산출세액','감면세액','안분세액','원단위조정']
def status(c,f):
    if f['kind']=='business' and not f['data'].get('target',True):return '대상 제외','납부대상 없음',0
    paid=sum(x['amount'] for x in db.payments(c,f['id']))
    return '미신고' if not f['filed_date'] else '신고 완료', '납부대상 없음' if f['data']['total']==0 else '납부 완료' if paid>=f['data']['total'] else '일부 납부' if paid else '미납',paid

def overview(c,year):
    out=[];fixed={(f['company'],f['region'],f['unit']):f for f in db.filings(c,year,'business')}
    for g in db.business_groups(c,year):
        f=fixed.get((g['company'],g['region'],g['unit']));value=f['data'] if f else g
        filed,paid,pay=(('검토 중','미확정',0) if value.get('target',True) else ('대상 제외','납부대상 없음',0)) if not f else status(c,f)
        out.append(dict(법인=g['company'],관할지자체=g['region'],신고단위=g['unit'],신고대상='대상' if value.get('target',True) else '7월1일 미존치 제외',사업장수=len(g['site_ids']),총면적=value['total_area'],제외면적=value['excluded'],과세면적=value['taxable'],기본세액=value['base'],연면적세액=value['area_tax'],지방교육세=value['education_tax'],합계=value['total'],검토상태='확정' if f else '확인 필요' if g['issues'] else '확정 가능',신고상태=filed,납부상태=paid,납부액=pay,미납잔액=max(0,value['total']-pay),기한=value['deadline']))
    return out

def grouped(data,keys):
    out={}
    for r in data:
        key=tuple(r[k] for k in keys)
        item=out.setdefault(key,dict(dict(zip(keys,key)),신고단위수=0,기본세액=0,연면적세액=0,지방교육세=0,합계=0,납부액=0,미납잔액=0,미신고건수=0,미확정건수=0))
        item['신고단위수']+=1
        for k in ['기본세액','연면적세액','지방교육세','합계','납부액','미납잔액']:item[k]+=r[k]
        item['미신고건수']+=r['신고상태'] not in ['신고 완료','대상 제외'];item['미확정건수']+=r['검토상태']!='확정'
    return list(out.values())

def filing_rows(c,year):
    out=[]
    for f in db.filings(c,year):
        filed,paid,amount=status(c,f)
        out.append(dict(세목='주민세(사업소분)' if f['kind']=='business' else '법인지방소득세',법인=f['company'],관할지자체=f['region'],신고단위=f['unit'],합계=f['data']['total'],신고상태=filed,신고일=f['filed_date'],접수번호=f['receipt'],납부상태=paid,납부액=amount,미납잔액=max(0,f['data']['total']-amount),기한=f['data']['deadline']))
    return out

def excel(c,year):
    out=BytesIO();data=overview(c,year)
    sheets={'법인총괄':grouped(data,['법인']),'지자체총괄':grouped(data,['법인','관할지자체']),'신고단위명세':data,'신고납부':filing_rows(c,year)}
    detail=[]
    for g in db.business_groups(c,year):
        config=g['members'][0]['site']
        for label,base,rate,tax,discount in [('기본세액',config['base'],'',g['raw_base'] if 'raw_base' in g else g['base'],config['reduce_base']),('연면적세액',g['taxable'],config['rate'],g.get('raw_area',g['area_tax']),config['reduce_area']),('지방교육세',config['base'],str(config['education'])+'%',g.get('raw_education',g['education_tax']),config['reduce_education'])]:
            detail.append(dict(법인=g['company'],지자체=g['region'],현장명=g['unit'],세목=label,과세표준=base,세율=rate,산출세액=tax,감면세액=discount,합계=tax-discount))
        detail.append(dict(법인=g['company'],지자체=g['region'],현장명=g['unit'],세목='현장 계',합계=g['total']))
    sheets['주민세집계']=detail
    with pd.ExcelWriter(out,engine='openpyxl') as w:
        for name,rows in sheets.items():
            pd.DataFrame(rows).to_excel(w,index=False,sheet_name=name);s=w.sheets[name];format_excel(s);s.freeze_panes='D2';s.auto_filter.ref=s.dimensions
            s.page_setup.orientation='landscape';s.page_setup.paperSize=s.PAPERSIZE_A4;s.print_title_rows='1:1';s.sheet_properties.pageSetUpPr.fitToPage=True;s.page_setup.fitToWidth=1;s.page_setup.fitToHeight=0
            for col in s.columns:s.column_dimensions[col[0].column_letter].width=25 if col[0].value in ['법인','관할지자체','현장명','신고단위'] else 18
            for row in s:
                for cell in row:
                    if cell.data_type=='f':cell.data_type='s'
                    if s.cell(1,cell.column).value in ['총면적','제외면적','과세면적']:cell.number_format='#,##0.00'
    return out.getvalue()

def html(data,title,year):
    columns=list(data[0]) if data else ['법인','관할지자체','신고단위','합계']
    heads=''.join('<th>'+escape(str(c))+'</th>' for c in columns)
    body=''
    for r in data:
        body+='<tr>'
        for c in columns:
            v=r.get(c,'');money=c in MONEY;area=c in ['총면적','제외면적','과세면적','안분면적']
            label=f'{v:,.0f}' if money and isinstance(v,(float,int)) else f'{v:,.2f}' if area and isinstance(v,(float,int)) else str(v)
            body+='<td'+(' class="money"' if money or area else '')+'>'+escape(label)+'</td>'
        body+='</tr>'
    return '<!doctype html><html lang="ko"><meta charset="utf-8"><title>'+escape(title)+'</title><style>@page{size:A4 landscape;margin:15mm}body{font:10px sans-serif;color:#16382b}h1{text-align:center;font-size:22px}table{width:100%;border-collapse:collapse;table-layout:fixed}th,td{border:1px solid #9eafa5;padding:6px 3px;text-align:center;overflow-wrap:anywhere}th{background:#e6f5ed}.money{text-align:right}thead{display:table-header-group}tr{break-inside:avoid}@media print{button{display:none}}</style><button onclick="window.print()">인쇄 / PDF 저장</button><h1>'+escape(title)+'</h1><p>'+str(year)+'년 · 검토용 자료 / 실제 신고·납부는 관할 지자체·위택스에서 진행</p><table><thead><tr>'+heads+'</tr></thead><tbody>'+body+'</tbody></table></html>'
