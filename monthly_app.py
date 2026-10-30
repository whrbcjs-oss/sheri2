"""LB monthly upload/report menus inside the existing authenticated Streamlit app."""
import hashlib
from pathlib import Path
import tempfile
from zoneinfo import ZoneInfo
from datetime import datetime
import json
import sqlite3
import zipfile

import streamlit as st
import streamlit.components.v1 as components
import collaboration as shared
import monthly_store as store
from monthly_report_preview import render_html
from monthly_ledger import read_ledger


def legacy_source(source):
    """Keep the generated private app.py unchanged; use the shared program selector."""
    selector='system = st.radio("프로그램 선택", ["자체결산 보고", "엘비데크 월별보고"], key="main_system")'
    if source.count(selector)!=1:
        raise ValueError('기존 프로그램의 메뉴 형식이 지원 버전과 다릅니다. app.py 원본을 보존하고 확인이 필요합니다.')
    return source.replace(selector,'system = st.session_state.get("main_system", "자체결산 보고")',1)


def analyze_upload(blob,name,year=None):
    with tempfile.TemporaryDirectory() as temp:
        path=Path(temp)/'uploaded.xlsx';path.write_bytes(blob)
        result=read_ledger(path)
    result['source']=str(name).replace('\\','/').rsplit('/',1)[-1]
    return result


def report_view(report,embedded=True):
    html=render_html(report,embedded=embedded)
    components.html(html,height=1450,scrolling=True)


def upload_page(c,year,user):
    st.subheader(f'{year}년 월별 원장 업로드')
    st.caption('원장 읽기·화면 버전: 2026.10.30.1')
    existing=store.imports(c)
    counts=c.execute("SELECT COUNT(*),COALESCE(SUM(CASE WHEN department='데크거더' THEN 1 ELSE 0 END),0) FROM monthly_ledger").fetchone()
    cards=st.columns(4)
    cards[0].metric('회계연도',str(year))
    cards[1].metric('저장된 월',f'{len(existing)}개월')
    cards[2].metric('저장된 원장',f'{counts[0]:,}건')
    cards[3].metric('데크거더 집계 대상',f'{counts[1]:,}건')
    st.markdown('<div class="lb-flow"><div class="lb-flow-step active"><strong>1</strong>월별 원장 선택</div><span>→</span><div class="lb-flow-step"><strong>2</strong>연도·월 확인 후 저장</div><span>→</span><div class="lb-flow-step"><strong>3</strong>통장기준 보고서 확인</div></div>',unsafe_allow_html=True)
    if existing:
        with st.expander('저장된 월별 원장 내역'):
            st.dataframe(existing,hide_index=True,use_container_width=True)
    if not user['admin']:
        st.info('원장 파일 교체 업로드는 관리자만 실행합니다. 보고서·원장 조회와 이월액·보험료 조정은 모든 사용자가 사용할 수 있습니다.')
        return
    st.info('보통예금_원장 시트만 있는 엑셀을 업로드하세요. 보고서 시트는 필요하지 않습니다.')
    st.markdown('<div class="lb-upload-tip">해당 월의 보통예금 원장을 선택하면 자동으로 읽습니다. 선택한 월만 저장·교체하며, 다른 달과 이월액·조정액은 유지합니다.</div>',unsafe_allow_html=True)
    uploaded=st.file_uploader('월별 보통예금 원장 엑셀',type=['xlsx'],key='lb_upload_file')
    if uploaded:
        blob=uploaded.getvalue();digest=hashlib.sha256(blob).hexdigest()
        cached=st.session_state.get('_lb_upload')
        if not cached or cached['digest']!=digest:
            try:
                with st.spinner('월별 원장을 읽고 있습니다.'):
                    data=analyze_upload(blob,uploaded.name)
                st.session_state['_lb_upload']={'digest':digest,'payload':data,'blob':blob}
            except (ValueError,KeyError,TypeError,ArithmeticError,OSError,zipfile.BadZipFile) as e:
                st.session_state.pop('_lb_upload',None)
                st.error('원장을 읽지 못했습니다: '+str(e));return
    upload=st.session_state.get('_lb_upload')
    if not upload:return
    data=upload['payload']
    if data.get('native_formula_count'):
        st.caption(f"SEARCH·IF 등 문자 분류 수식 {data['native_formula_count']:,}개 셀을 직접 계산했습니다.")
    if data.get('cached_formula_count'):
        st.caption(f"엑셀에 저장된 수식 계산 결과 {data['cached_formula_count']:,}개 셀을 사용했습니다. 원본 수식을 바꾼 경우 Excel에서 전체 계산 후 저장한 파일을 올려 주세요.")
    months=sorted({r['month'] for r in data['records'] if r['year']==year},reverse=True)
    if not months:
        st.warning(f'파일에 {year}년 거래가 없습니다. 왼쪽 월별보고 회계연도를 변경하세요.');return
    month=st.selectbox('저장할 월',months,format_func=lambda m:f'{year}년 {m}월',key='lb_import_month_'+upload['digest'])
    selected=[r for r in data['records'] if r['year']==year and r['month']==month]
    deck=[r for r in selected if r['department']=='데크거더']
    a,b=st.columns(2);a.metric('선택 월 전체 원장',f'{len(selected):,}건');b.metric('데크거더 집계 대상',f'{len(deck):,}건')
    st.caption(f"{data['source']} · {min(r['date'] for r in selected)} ~ {max(r['date'] for r in selected)}")
    if not deck:st.warning('이 달에는 대분류가 데크거더인 거래가 없습니다. 분류가 입력된 원장인지 확인하세요.')
    st.dataframe(selected[:30],hide_index=True,use_container_width=True)
    current=next((i for i in existing if i['month']==month),None)
    if current and current['sha256']==data['sha256']:
        st.info('이 달은 이미 같은 파일로 저장되어 있습니다. 다른 월을 선택하거나 새 파일을 업로드하세요.');return
    confirmed=st.checkbox(f'{year}년 {month}월 원장만 저장·교체합니다. 다른 달은 유지합니다.',key=f'lb_confirm_{year}_{month}_{upload["digest"]}')
    if st.button('선택 월 원장 저장',type='primary',disabled=not confirmed):
        try:
            store.save_month(c,year,month,data,upload['blob'],st.session_state['_auth_token'])
            st.session_state.pop('_lb_upload',None)
            st.session_state['_lb_next_page']='통장입출금기준 현황'
            st.session_state['_lb_success']=f'{year}년 {month}월 원장을 저장했습니다. 다른 달은 유지했습니다.'
            st.rerun()
        except (ValueError,PermissionError,sqlite3.Error,OSError) as e:st.error('저장하지 못했습니다: '+str(e))


def settings_page(c,year):
    st.subheader('이월액·원장외 보험료 조정')
    st.caption('원장에 없는 값만 별도로 입력합니다. 변경한 계정과 금액은 수정 이력에 기록됩니다.')
    current=store.settings(c)
    with st.form('lb_settings'):
        opening=st.text_input('전년 이월 정산액(원) · 미확인이면 빈칸',value=current['opening_amount'] if current['opening_confirmed'] else '')
        rate=st.text_input('관리비율(%)',value=current['management_rate'])
        submit=st.form_submit_button('이월액·관리비율 저장')
    if submit:
        try:store.save_settings(c,year,opening,rate);st.success('저장했습니다.')
        except (ValueError,PermissionError,sqlite3.Error) as e:st.error(str(e))
    months=[i['month'] for i in store.imports(c)]
    if not months:
        st.info('보험료 조정은 해당 월 원장을 저장한 뒤 입력합니다.');return
    month=st.selectbox('보험료 조정 월',months,format_func=lambda m:f'{m}월')
    previous=c.execute('SELECT amount,reason FROM monthly_adjustments WHERE month=? AND report_row=8',(month,)).fetchone()
    with st.form('lb_insurance_'+str(month)):
        st.write('원청 공제 고용·산재 보전액: 공사수입과 고용·산재 지출에 같은 금액을 가산합니다.')
        amount=st.text_input('원장외 보험료 보전액(원)',value=previous[0] if previous else '0')
        reason=st.text_input('조정 사유·근거',value=previous[1] if previous else '')
        submit=st.form_submit_button('보험료 조정 저장')
    if submit:
        try:store.save_insurance(c,year,month,amount,reason);st.success('조정을 저장했습니다.')
        except (ValueError,PermissionError,sqlite3.Error) as e:st.error(str(e))


def annotations_page(c,year):
    from monthly_ledger import LABELS
    st.subheader('보고서 메모·결재란')
    st.caption('모든 사용자가 작성할 수 있습니다. 연도별로 함께 저장되며, 원장 재업로드 후에도 유지됩니다. 메모 금액은 계산값을 변경하지 않습니다.')
    tabs=st.tabs(['노임·미불 월별 메모','셀 포스트잇','결재란'])
    entries=store.annotations(c)
    with tabs[0]:
        month=st.selectbox('메모 월',list(range(1,13)),format_func=lambda m:f'{m}월',key='lb_memo_month')
        row=st.selectbox('메모 항목',[13,17],format_func=lambda r:LABELS[r],key='lb_memo_row')
        existing=next((a for a in entries if a['kind']=='row_memo' and a['month']==month and a['report_row']==row),None)
        with st.form(f'lb_row_memo_{year}_{month}_{row}'):
            text=st.text_area('금액 아래에 표시할 메모',value=existing['body'] if existing else '',placeholder='예: 전월 노임 / 전전월 미불',max_chars=1000)
            submit=st.form_submit_button('월별 메모 저장',type='primary')
        if submit:
            try:store.save_annotation(c,year,month,row,'row_memo',text);st.success('월별 메모를 저장했습니다. 빈칸으로 저장하면 삭제됩니다.')
            except (ValueError,PermissionError,sqlite3.Error) as e:st.error(str(e))
    with tabs[1]:
        month=st.selectbox('포스트잇 월',[0]+list(range(1,13)),format_func=lambda m:'누계' if m==0 else f'{m}월',key='lb_sticky_month')
        row=st.selectbox('포스트잇 항목',list(LABELS),format_func=lambda r:LABELS[r],key='lb_sticky_row')
        existing=next((a for a in entries if a['kind']=='sticky' and a['month']==month and a['report_row']==row),None)
        with st.form(f'lb_sticky_{year}_{month}_{row}'):
            title=st.text_input('포스트잇 제목',value=existing['title'] if existing else '',placeholder='예: 일용부 고용보험료 내역',max_chars=120)
            body=st.text_area('포스트잇 내용',value=existing['body'] if existing else '',placeholder='공제·환수 금액과 근거를 자유롭게 적으세요.',max_chars=5000,height=150)
            submit=st.form_submit_button('포스트잇 저장',type='primary')
        if submit:
            try:store.save_annotation(c,year,month,row,'sticky',body,title);st.success('포스트잇을 저장했습니다. 제목·내용을 모두 비우고 저장하면 삭제됩니다.')
            except (ValueError,PermissionError,sqlite3.Error) as e:st.error(str(e))
    with tabs[2]:
        groups=store.approvals(c)
        with st.form(f'lb_approvals_{year}'):
            people=[]
            for g,group in enumerate(groups):
                st.write(group['title']);columns=st.columns(3)
                people.append([columns[r].text_input(item['role'],value=item['person'],key=f'lb_approver_{year}_{g}_{r}',max_chars=100) for r,item in enumerate(group['roles'])])
            st.caption('기입한 성명을 출력하며, 비워 두면 인쇄 후 수기로 서명할 수 있습니다.')
            submit=st.form_submit_button('결재란 저장',type='primary')
        if submit:
            try:store.save_approvals(c,year,people);st.success('결재란을 저장했습니다.')
            except (ValueError,PermissionError,sqlite3.Error) as e:st.error(str(e))


def backup_page(c,year,user):
    if not user['admin']:
        st.info('백업·복원은 관리자만 실행할 수 있습니다.');return
    st.subheader(f'{year}년 월별 자료 백업·복원')
    st.caption('매일 첫 변경 전과 원장 교체 전에 자동 백업합니다. 월별 DB는 자체결산 DB와 별개입니다. 메모 기능 추가 전 백업을 복원할 때는 현재 메모·결재란을 유지합니다.')
    if st.button('월별 DB 백업 만들기'):
        shared.require_admin(st.session_state['_auth_token'])
        shared.backup_database(c.path);st.success('백업을 만들었습니다.')
    files=sorted((shared.STATE/'backups').glob(f'lb_monthly_{year}-*.sqlite'),reverse=True)
    if files:
        path=st.selectbox('월별 백업 선택',files,format_func=lambda p:p.name)
        st.download_button('월별 백업 다운로드',path.read_bytes(),file_name=path.name)
    restore=st.file_uploader('복원할 동일 연도 월별 DB 백업',type=['sqlite'],key='lb_restore_file')
    confirm=st.checkbox('선택 연도 월별 자료를 백업 내용으로 교체하는 것을 확인했습니다.')
    if st.button('월별 백업 복원',disabled=not restore or not confirm):
        try:
            c.rollback()
            shared.restore_database(st.session_state['_auth_token'],c.path,restore.getvalue(),c.expected)
            st.session_state.pop('_lb_upload',None)
            st.session_state['_lb_next_page']='통장입출금기준 현황'
            st.session_state['_lb_success']='월별 자료를 복원했습니다.'
            st.rerun()
        except (ValueError,PermissionError,sqlite3.Error,OSError) as e:st.error(str(e))


def render(user):
    css=Path(__file__).with_name('monthly_theme.css').read_text(encoding='utf-8')
    st.markdown('<style>'+css+'</style>',unsafe_allow_html=True)
    with st.sidebar:
        st.subheader('엘비데크 월별보고')
        this_year=datetime.now(ZoneInfo('Asia/Seoul')).year
        years=sorted(set(store.available_years()+[this_year]),reverse=True)
        year=st.number_input('월별보고 회계연도',min_value=2000,max_value=2100,
                             value=years[0],step=1,key='lb_year')
        if '_lb_next_page' in st.session_state:
            st.session_state['lb_monthly_page']=st.session_state.pop('_lb_next_page')
        page=st.radio('월별보고 메뉴',['원장 업로드','통장입출금기준 현황','원장 조회','보고서 메모·결재','이월액·조정','백업 관리'],key='lb_monthly_page')
    st.markdown('<div class="lb-breadcrumb"><span>엘비데크 월별보고 / '+page+'</span><span class="lb-badge">공급가액 기준 · 부가세 제외</span></div>',unsafe_allow_html=True)
    st.title('엘비데크 월별보고')
    st.caption('원장 업로드 → 월별 집계 → 부가세 제외 보고서 · 자체결산 자료와 분리 저장')
    if '_lb_success' in st.session_state:st.success(st.session_state.pop('_lb_success'))
    c=store.connect(int(year))
    if page=='원장 업로드':upload_page(c,int(year),user);return
    if page=='백업 관리':backup_page(c,int(year),user);return
    if page=='보고서 메모·결재':annotations_page(c,int(year));return
    if page=='이월액·조정':settings_page(c,int(year));return
    data=store.report(c,int(year))
    if not data:
        st.info('저장된 월별 자료가 없습니다. 원장 업로드에서 해당 월 보통예금 원장을 저장하세요.');return
    st.caption(f"{year}년 · 저장된 월: {', '.join(str(m)+'월' for m in data['months'])}")
    if page=='통장입출금기준 현황':
        st.caption('결재란과 노임·미불 메모, 셀 포스트잇은 왼쪽 보고서 메모·결재 메뉴에서 입력합니다.')
        if not data['opening_confirmed']:st.info('이월 정산액이 아직 입력되지 않았습니다. 월별 수입·지출은 계산되며 최종 정산잔액은 미확인으로 표시합니다.')
        st.download_button('보고서 HTML 다운로드 · 열어서 인쇄/PDF 저장',render_html(data).encode('utf-8'),
                           file_name=f'엘비데크_월별보고_{year}.html',mime='text/html')
        report_view(data)
    elif page=='원장 조회':
        frame=store.ledger(c)
        only_deck=st.checkbox('데크거더 집계 대상만 보기',value=True)
        if only_deck:frame=frame[frame['대분류']=='데크거더']
        query=st.text_input('프로젝트·거래처·적요 검색')
        if query:
            mask=frame[['프로젝트','거래처','적요']].astype(str).apply(lambda col:col.str.contains(query,regex=False,case=False)).any(axis=1)
            frame=frame[mask]
        st.write(f'{len(frame):,}건')
        st.dataframe(frame,hide_index=True,use_container_width=True)
        st.download_button('조회 원장 CSV 다운로드',frame.to_csv(index=False).encode('utf-8-sig'),file_name=f'월별원장_{year}.csv',mime='text/csv')
