"""Accommodation register exports with common numeric/text alignment."""
from html import escape
from io import BytesIO
import pandas as pd
from table_layout import format_excel

MONEY=['보증금','월 임차료','월 관리비','반환액','미반환 보증금','전세권 설정금액']
def overview(c,items,as_of):
    import accommodation_store as db
    return [{'현장':v['site'],'숙소명':v['name'],'구분':v['kind'],'숙소 주소':' '.join([v['address'],v['detail']]).strip(),'임차인':v['tenant'],'연락처':v['tenant_phone'],'계약시작일':v['start'],'계약종료일':v.get('terminated') or v['end'],'보증금':v['deposit'],'월 임차료':v['rent'],'월 관리비':v['maintenance'],'반환액':db.returned(c,v['id'],as_of),'미반환 보증금':v['deposit']-db.returned(c,v['id'],as_of),'상태':db.state(v,as_of),'전세권 설정 여부':v.get('registration_status','미설정'),'전세권 설정일':v.get('registration_date',''),'전세권 설정금액':v.get('registration_amount',0),'등기 접수번호':v.get('registration_number','')} for v in items]
def excel(rows):
    out=BytesIO()
    with pd.ExcelWriter(out,engine='openpyxl') as w:
        frame=pd.DataFrame(rows)
        frame.to_excel(w,index=False,sheet_name='숙소 현황')
        s=w.sheets['숙소 현황'];format_excel(s);s.freeze_panes='C2';s.auto_filter.ref=s.dimensions
        for col in s.columns:s.column_dimensions[col[0].column_letter].width=38 if col[0].value=='숙소 주소' else 20
    return out.getvalue()
def html(rows,as_of):
    headers=list(rows[0]) if rows else ['현장','숙소명','계약기간','보증금','월 임차료','상태']
    head=''.join('<th>'+escape(k)+'</th>' for k in headers)
    body=''.join('<tr>'+''.join('<td'+(' class="money"' if k in MONEY else '')+'>'+escape(f'{r[k]:,}' if k in MONEY else str(r[k]))+'</td>' for k in headers)+'</tr>' for r in rows)
    totals='<tr>'+''.join('<td'+(' class="money"' if k in MONEY else '')+'>'+ (f'{sum(r[k] for r in rows):,}' if k in MONEY else '합계' if i==0 else '')+'</td>' for i,k in enumerate(headers))+'</tr>'
    return '<!doctype html><html lang="ko"><meta charset="utf-8"><title>현장숙소 총현황</title><style>@page{size:A4 landscape;margin:15mm}body{font:10px sans-serif;color:#163c30}h1{text-align:center}table{border-collapse:collapse;width:100%;table-layout:fixed}td,th{border:1px solid #9aafa3;padding:7px 3px;text-align:center;overflow-wrap:anywhere}th{background:#e4f4eb}.money{text-align:right;white-space:nowrap}thead{display:table-header-group}tr{break-inside:avoid}@media print{button{display:none}}</style><button onclick="window.print()">인쇄 / PDF 저장</button><h1>현장숙소 총현황</h1><p>기준일: '+escape(str(as_of))+'</p><table><thead><tr>'+head+'</tr></thead><tbody>'+body+totals+'</tbody></table></html>'
