"""Joint venture management integrated into the authenticated Streamlit application."""
from datetime import date
from io import BytesIO
import json
import sqlite3
from zipfile import BadZipFile
import pandas as pd
import openpyxl
import streamlit as st
import streamlit.components.v1 as components
import collaboration as shared
import joint_store as db
from joint_report import render as report_html,money
from joint_import import read as import_rows,LABELS

VERSION='2026.10.30.1'

def saved():
    st.session_state['_jv_success']='저장했습니다.';st.rerun()

def month_fields(default=None):
    default=default or date.today().strftime('%Y-%m')
    a,b=st.columns(2)
    return a.text_input('시작 연월 (YYYY-MM)',default),b.text_input('종료 연월 (YYYY-MM)',default)

def company_page(c):
    st.header('법인·담당자 등록')
    cos=db.companies(c);selected=st.selectbox('수정할 법인',['새 법인']+[x['code'] for x in cos])
    old=next((x for x in cos if x['code']==selected),{});info=json.loads(old.get('info','{}'))
    with st.form('jv_company_'+str(old.get('id','new'))):
        code=st.text_input('법인코드',old.get('code',''));name=st.text_input('법인명',old.get('name',''))
        vals={k:st.text_input(k,info.get(k,'')) for k in ['사업자등록번호','대표자','주소','전화','팩스','담당자','직급','담당자 연락처','담당자2','직급2','입금계좌']}
        if st.form_submit_button('법인 저장',type='primary'):db.company(c,code,name,vals,old.get('id'));saved()
    st.dataframe(pd.DataFrame(cos).drop(columns=['info'],errors='ignore'),hide_index=True,use_container_width=True)

def project_page(c):
    st.header('프로젝트·회원사 등록')
    cos=db.companies(c)
    if not cos:st.info('먼저 당사와 회원사를 법인·담당자 등록에서 등록하세요.');return
    labels={x['id']:f"{x['name']} [{x['code']}]" for x in cos};reverse={v:k for k,v in labels.items()}
    ps=db.projects(c);selected=st.selectbox('프로젝트 등록·수정',[None]+[x['id'] for x in ps],format_func=lambda x:'새 프로젝트' if x is None else next(p['name'] for p in ps if p['id']==x))
    old=next((x for x in ps if x['id']==selected),{});ms=db.members(c,selected) if selected else []
    if selected and db.ledger(c,selected):st.info('이 프로젝트는 원장이 등록되어 지분 변경을 잠갔습니다. 아래 양식은 조회용입니다.')
    with st.form('jv_project_'+str(selected)):
        name=st.text_input('공사명',old.get('name',''));owner=st.selectbox('당사(관리법인)',list(labels),format_func=labels.get,index=list(labels).index(old.get('owner_id',list(labels)[0])))
        contract=st.text_input('계약금액 전체',old.get('contract','0'));supply=st.text_input('공급가액 전체',old.get('supply','0'));vat=st.text_input('계약 부가세액',old.get('vat','0'))
        start=st.date_input('공사 시작',date.fromisoformat(old.get('start',date.today().isoformat())));end=st.date_input('공사 종료',date.fromisoformat(old.get('end',date.today().isoformat())))
        initial=[{'법인':labels[m['company_id']],'지분율(%)':m['share'],'관리비 적용':bool(m['fee_enabled']),'관리비율(%)':m['fee_rate']} for m in ms] or [{'법인':labels[owner],'지분율(%)':'100','관리비 적용':False,'관리비율(%)':'0'}]
        st.caption('당사를 포함한 전체 지분율 합계는 100%입니다. 행을 추가해 회원사 수만큼 등록하세요.')
        frame=st.data_editor(pd.DataFrame(initial),num_rows='dynamic',hide_index=True,use_container_width=True,column_config={'법인':st.column_config.SelectboxColumn(options=list(reverse),required=True)})
        if st.form_submit_button('프로젝트 저장',type='primary'):
            entries=[{'company_id':reverse[x['법인']],'share':x['지분율(%)'],'fee_enabled':x['관리비 적용'],'fee_rate':x['관리비율(%)']} for x in frame.to_dict('records') if x.get('법인') in reverse]
            db.project(c,name,owner,contract,supply,vat,start,end,entries,selected);saved()

def ledger_page(c,p,ms):
    st.header('원장 업로드·수기입력')
    tab1,tab2,tab3=st.tabs(['회원사 원가 수기입력','엑셀 업로드','원장 조회'])
    with tab1:
        with st.form('jv_manual_'+str(p)):
            who=st.selectbox('원가투입 법인',[m['company_id'] for m in ms],format_func=lambda x:next(m['name'] for m in ms if m['company_id']==x))
            dt=st.date_input('기표일자');month=st.text_input('배분월 (YYYY-MM)',date.today().strftime('%Y-%m'))
            rec=dict(posting_date=dt,allocation_month=month,account=st.text_input('계정과목'),vendor=st.text_input('거래처'),description=st.text_input('적요'))
            for key,label in [('tax_supply','세금계산서 공급가액 (VAT 제외)'),('vat','부가세'),('invoice','계산서 금액'),('receipt','기타영수증 금액')]:rec[key]=st.text_input(label,'0')
            rec['note']=st.text_input('비고·정정 사유')
            st.caption('취소·정정은 원거래를 지우지 않고 음수 원가와 정정 사유로 기록할 수 있습니다.')
            if st.form_submit_button('원가 저장',type='primary'):db.add_ledger(c,p,who,[rec]);saved()
    with tab2:
        st.info('아마란스 실제 양식 확인 전에는 열을 직접 지정합니다. 전표번호와 전표행 식별값으로 중복을 차단하며, 중복이 있으면 파일 전체를 저장하지 않습니다.')
        wb=openpyxl.Workbook();ws=wb.active;ws.title='원장';ws.append(list(LABELS.values()))
        stream=BytesIO();wb.save(stream)
        st.download_button('입력용 빈 엑셀 양식',stream.getvalue(),file_name='공동도급_원장입력양식.xlsx')
        up=st.file_uploader('원장 엑셀 선택',type=['xlsx'],key='jv_upload')
        if up:
            blob=up.getvalue();book=openpyxl.load_workbook(BytesIO(blob),read_only=True,data_only=True)
            try:
                sheet=st.selectbox('시트',book.sheetnames);header=st.number_input('제목 행 번호',min_value=1,value=1,step=1)
                last=st.number_input('마지막 자료 행 (0이면 끝까지)',min_value=0,value=0,step=1)
                if last and last<=header:raise ValueError('마지막 자료 행은 제목 행 다음이어야 합니다.')
                cells=next(book[sheet].iter_rows(min_row=int(header),max_row=int(header)),[])
                options={i+1:f'{openpyxl.utils.get_column_letter(i+1)} · {cell.value or "빈 제목"}' for i,cell in enumerate(cells)}
                if not options:st.warning('해당 행에 열이 없습니다.');return
                who=st.selectbox('업로드 원가투입 법인',[m['company_id'] for m in ms],format_func=lambda x:next(m['name'] for m in ms if m['company_id']==x),key='jv_import_company')
                mapping={}
                with st.expander('엑셀 열 연결',expanded=True):
                    for key,label in LABELS.items():
                        match=next((col for col,text in options.items() if text.split(' · ',1)[1]==label),None)
                        choices=[None]+list(options);mapping[key]=st.selectbox(label,choices,index=choices.index(match),format_func=lambda x:'사용 안 함' if x is None else options[x],key='jv_map_'+key)
                if st.button('분석 미리보기'):
                    records=import_rows(blob,sheet,header,mapping,int(last) or None);st.dataframe(records[:100],hide_index=True);st.success(f'{len(records):,}행 분석 완료. 저장하려면 아래 버튼을 누르세요.')
                if st.button('검증 후 원장 전체 저장',type='primary'):
                    records=import_rows(blob,sheet,header,mapping,int(last) or None);db.add_ledger(c,p,who,records,blob,up.name);saved()
            finally:book.close()
    with tab3:
        frame=pd.DataFrame(db.ledger(c,p));st.dataframe(frame,hide_index=True,use_container_width=True)
        st.download_button('원장 CSV 내려받기',safe_csv(frame),file_name='공동도급_원장.csv')

def csv_cell(value):
    if isinstance(value,str) and value.lstrip().startswith(('=','+','-','@')):
        try:db.num(value)
        except ValueError:return "'"+value
    return value


def safe_csv(frame):
    # Prevent spreadsheet formula execution from text fields in exported CSV.
    frame=frame.copy()
    for col in frame.columns:
        frame[col]=frame[col].map(csv_cell)
    return frame.to_csv(index=False).encode('utf-8-sig')

def allocation_page(c,p,start,end):
    st.header('원가배분내역서')
    st.caption('원장별 공급가액·VAT를 지분 배분합니다. 원 단위 반올림 후 잔여액은 지분이 가장 큰 회사에 반영하며 총액은 보존합니다.')
    if st.button('미배분 원장 자동 배분',type='primary'):
        count=db.allocate(c,p);st.success(f'{count}개 원장을 배분했습니다. 기존 배분·수정액은 유지했습니다.')
    al=db.allocations(c,p,start,end);frame=pd.DataFrame(al);st.dataframe(frame,hide_index=True,use_container_width=True)
    st.download_button('원가배분 CSV',safe_csv(frame),file_name='원가배분내역서.csv')
    if al:
        line=st.selectbox('수정할 원장ID',list(dict.fromkeys(a['ledger_id'] for a in al)))
        subset=[{'id':a['id'],'회원사':a['name'],'base':a['base'],'vat':a['vat'],'reason':a['reason']} for a in al if a['ledger_id']==line]
        with st.form('jv_alloc_edit_'+str(line)):
            st.caption('base는 VAT 제외 원가입니다. 모든 회원사 합계가 원장과 각각 일치해야 합니다. 수정할 회원사뿐 아니라 전체 행의 사유를 입력하세요.')
            edits=st.data_editor(pd.DataFrame(subset),disabled=['id','회원사'],hide_index=True,use_container_width=True)
            if st.form_submit_button('배분 수정 저장'):db.revise(c,p,line,edits.to_dict('records'));saved()

def entry_page(c,p,m,start,end):
    st.header('기성·공제·하도급·회수 입력')
    kind=st.selectbox('입력 구분',['progress','subcontract','recovery','opening'],format_func={'progress':'기성·관리비·보험료','subcontract':'하도급 청구·지급','recovery':'회수내역','opening':'공문 전월 미수·지연이자'}.get)
    es=db.entries(c,p,m['id'],kind)
    selected=st.selectbox('등록·수정할 자료',[None]+[e['id'] for e in es],format_func=lambda x:'새 자료' if x is None else str(x)+' · '+next(e['entry_date'] for e in es if e['id']==x))
    old=next((x for x in es if x['id']==selected),{});data=json.loads(old.get('payload','{}'))
    with st.form('jv_entry_'+kind+'_'+str(m['id'])+'_'+str(selected)):
        dt=st.date_input('기성 수령일 / 청구일 / 회수일',date.fromisoformat(old.get('entry_date',date.today().isoformat())))
        a,b=st.columns(2);ps=a.text_input('해당 시작월',old.get('period_start',start));pe=b.text_input('해당 종료월',old.get('period_end',end))
        payload={}
        if kind=='progress':
            payload['label']=st.text_input('기성명',data.get('label',''))
            st.caption('모든 보험료·제외금액은 해당 회원사분으로 입력하세요. 전체금액을 받았다면 지분율을 적용한 금액을 입력하며, 프로그램이 지분을 다시 곱하지 않습니다.')
            payload['supply']=st.text_input('기성 수령 공급가액',data.get('supply','0'));payload['vat']=st.text_input('기성 수령 VAT',data.get('vat','0'))
            payload['fee_rate']=st.text_input('이 기성의 관리비율 (%)',data.get('fee_rate',m['fee_rate']))
            for k in db.EXCLUSIONS:payload[k]=st.text_input(k,data.get(k,'0'))
            st.caption('같은 기성의 여러 수령분은 합산해 한 건으로 입력하세요. 관리비 = (기성 공급가액 − 위 제외항목 합계) × 관리비율, 기성별 원 미만 버림. 관리비 미적용 회원사는 정산서에 관리비 0원을 반영합니다.')
        elif kind=='subcontract':
            payload['vendor']=st.text_input('하도급 업체',data.get('vendor',''))
            for k,label in [('supply','청구 공급가액'),('vat','청구 VAT'),('paid_supply','지급 공급가액'),('paid_vat','지급 VAT')]:payload[k]=st.text_input(label,data.get(k,'0'))
            payload['paid_date']=st.text_input('지급일 (YYYY-MM-DD, 미지급은 빈칸)',data.get('paid_date',''));payload['method']=st.text_input('공종·지급방식',data.get('method',''))
            if payload['paid_date']:db.day(payload['paid_date'])
            st.caption('분할지급을 별도 행으로 입력할 때는 청구 공급가액·VAT를 0으로 두어 청구액이 중복되지 않게 하세요. 별도 지급분이 선택 기간 밖이면 기간을 넓혀 누적 조회하세요.')
        elif kind=='recovery':
            payload['supply']=st.text_input('회수 공급가액',data.get('supply','0'));payload['vat']=st.text_input('회수 VAT',data.get('vat','0'))
            st.caption('하도급 지급은 자동으로 회수 합계에 포함되므로 여기에서 중복 입력하지 마세요.')
        else:
            payload['arrears']=st.text_input('전월 미수액',data.get('arrears','0'));payload['interest']=st.text_input('지연이자',data.get('interest','0'))
            st.caption('공문 청구용 입력입니다. 이전 미회수액을 자동으로 재가산하지 않습니다.')
        payload['note']=st.text_area('비고·수정 사유',data.get('note',''))
        if st.form_submit_button('입력 저장',type='primary'):db.save_entry(c,p,m['id'],kind,dt,ps,pe,payload,selected);saved()
    st.dataframe([dict(id=e['id'],일자=e['entry_date'],시작월=e['period_start'],종료월=e['period_end'],**json.loads(e['payload'])) for e in es],hide_index=True,use_container_width=True)
    if selected:
        confirmed=st.checkbox('선택한 수기 자료를 삭제합니다. 확정된 발행본은 유지됩니다.')
        if st.button('선택 자료 삭제',disabled=not confirmed):
            with c:c.execute('DELETE FROM jv_entries WHERE id=? AND project_id=? AND member_id=?',(selected,p,m['id']))
            saved()

def report_page(c,p,m,start,end,kind):
    st.header(kind+' 작성·발행')
    data=db.settlement(c,p,m['id'],start,end)
    if data['unallocated']:st.warning(f"미배분 원장 {data['unallocated']}건이 있습니다. 미리보기에는 아직 반영되지 않으며 발행할 수 없습니다.")
    a=data['amounts'];cols=st.columns(3)
    for col,key,label in zip(cols,['claim','recovery','remaining'] if kind=='정산서' else ['base','invested','letter_claim'],['청구 합계','회수 합계','미회수액'] if kind=='정산서' else ['배분 공급가액','회원사투입 공제','금월청구액']):col.metric(label,money(a[key])+'원')
    st.caption('정산은 선택 기간에 완전히 포함되는 자료로 계산합니다. 공사 전체 누적 정산은 시작월을 공사 시작월로 선택하세요. 회수일과 대상 배분월은 별도로 저장합니다.')
    owner=next(x for x in data['companies'] if x['id']==data['project']['owner_id']);info=json.loads(owner['info'])
    number=st.text_input('문서번호 (전체 문서 중 중복 불가)',key='jv_docnumber_'+kind)
    issued=st.date_input('발행일',key='jv_issue_'+kind)
    meta=dict(number=number,issued=issued.isoformat())
    if kind=='공문':
        st.info('공문 공제액은 회원사투입액입니다. 관리비·산재·고용 공제와 혼합하지 않습니다.')
        meta.update(title=st.text_input('제목',f'{start} ~ {end} 공동원가 안분정산 및 자금청구의 건',key='jv_title_'+str(p)+'_'+start+'_'+end),reference=st.text_input('참조','공동도급 담당자'),body=st.text_area('본문 추가 문구'),due=st.text_input('입금 요청기한'),bank=st.text_input('입금계좌',info.get('입금계좌','')),attachments=st.text_input('첨부목록','공동원가 투입 및 배분내역서 1부, 현장별 원장 1부'))
    html=report_html(data,kind,meta)
    st.download_button('미확정 '+kind+' HTML 내려받기',html.encode('utf-8'),file_name='미확정_'+kind+'.html',mime='text/html')
    if st.button('현재 내용 확정·발행',type='primary',disabled=bool(data['unallocated'])):
        db.snapshot(c,data,kind,number,issued,meta);saved()
    components.html(html,height=1000,scrolling=True)

def archive_page(c,p):
    st.header('발행본·백업·변경 이력')
    docs=db.rows(c,'SELECT id,kind,number,issued FROM jv_documents WHERE project_id=? ORDER BY id DESC',(p,));st.dataframe(docs,hide_index=True)
    if docs:
        id=st.selectbox('확정 발행본',[x['id'] for x in docs],format_func=lambda id:next(x['number']+' · '+x['kind'] for x in docs if x['id']==id))
        d=json.loads(c.execute('SELECT snapshot FROM jv_documents WHERE id=?',(id,)).fetchone()[0]);d['snapshot_id']=id
        html=report_html(d,d['kind']);st.download_button('확정본 내려받기',html.encode('utf-8'),file_name=d['kind']+'_'+str(id)+'.html',mime='text/html');components.html(html,height=800,scrolling=True)
    st.download_button('변경 이력 CSV',safe_csv(pd.DataFrame(db.rows(c,'SELECT at,actor,table_name,operation,before_json,after_json FROM change_history ORDER BY id DESC LIMIT 1000'))),file_name='공동도급_변경이력.csv')
    if st.button('현재 DB 백업 생성'):
        path=shared.backup_database(c.path);st.download_button('생성한 백업 내려받기',path.read_bytes(),file_name=path.name)
    st.caption('매일 첫 변경 전 자동 백업합니다. 복원은 관리자만 실행할 수 있습니다.')
    if shared.validate_session(st.session_state['_auth_token'])['admin']:
        up=st.file_uploader('공동도급 DB 백업 복원',type=['sqlite','db'],key='jv_restore')
        confirm=st.checkbox('공동도급 자료 전체를 선택한 백업으로 되돌립니다.')
        if st.button('공동도급 백업 복원 실행',disabled=not(up and confirm)):
            db.restore(c,up.getvalue(),st.session_state['_auth_token']);st.session_state.pop('_snapshots',None);saved()

def render(user):
    st.caption('공동도급 관리대장 · 버전 '+VERSION)
    c=db.connect()
    with st.sidebar:
        st.subheader('공동도급 관리대장')
        page=st.radio('공동도급 업무',['법인·담당자','프로젝트·회원사','원장 등록','원가배분내역서','기성·하도급·회수','원가정산서','공문 작성','발행본·백업'],key='jv_page')
    try:
        if '_jv_success' in st.session_state:st.success(st.session_state.pop('_jv_success'))
        if page=='법인·담당자':company_page(c);return
        if page=='프로젝트·회원사':project_page(c);return
        ps=db.projects(c)
        if not ps:st.info('법인 등록 후 프로젝트·회원사를 등록하세요.');return
        with st.sidebar:
            p=st.selectbox('공동도급 프로젝트',[x['id'] for x in ps],format_func=lambda id:next(x['name'] for x in ps if x['id']==id),key='jv_project');ms=db.members(c,p)
            selected=st.selectbox('대상 회원사',[x['id'] for x in ms],format_func=lambda id:next(x['name'] for x in ms if x['id']==id),key='jv_member');m=next(x for x in ms if x['id']==selected)
            st.caption('지분 '+m['share']+'% · 관리비 '+(m['fee_rate']+'%' if m['fee_enabled'] else '미적용'))
        if page=='원장 등록':ledger_page(c,p,ms);return
        if page=='발행본·백업':archive_page(c,p);return
        start,end=month_fields()
        db.period(start);db.period(end)
        if start>end:raise ValueError('시작월은 종료월보다 늦을 수 없습니다.')
        if page=='원가배분내역서':allocation_page(c,p,start,end)
        elif page=='기성·하도급·회수':entry_page(c,p,m,start,end)
        elif page in ['원가정산서','공문 작성']:report_page(c,p,m,start,end,'정산서' if page=='원가정산서' else '공문')
    except (ValueError,sqlite3.Error,BadZipFile) as e:st.error(str(e))
