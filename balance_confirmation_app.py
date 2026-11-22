"""PC-first receivable/payable confirmation workflow."""
import hashlib
from datetime import date

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

import balance_confirmation_store as db
import balance_confirmation_report as report
import collaboration as shared
import mail_service as mail


CSS = '''<style>
.bc-hero{background:linear-gradient(125deg,#edf8f5,#e6f3fa);border:1px solid #bcdad2;border-left:6px solid #2d95aa;border-radius:9px;padding:13px 16px;margin:4px 0 12px;color:#244955}.bc-hero small{display:block;color:#4b8782;font-weight:700;letter-spacing:.05em}.bc-hero strong{display:block;font-size:23px;margin-top:2px}.bc-title{background:#eaf5fb;color:#24566e;border-left:6px solid #4b9ac8;border-bottom:2px solid #afd3e5;border-radius:6px 6px 0 0;padding:8px 11px;font-size:18px;font-weight:800;margin:12px 0 8px}.bc-note{background:#eef8f4;border:1px solid #c4e2d6;border-radius:7px;padding:9px 11px;color:#315c50}.bc-warning{background:#fff8df;border:1px solid #e3cc73;border-radius:7px;padding:9px 11px;color:#765b00}.st-key-bc_context{background:#fff;border:1px solid #cfe0dc;border-radius:8px;padding:10px 13px}.st-key-bc_metrics [data-testid="stMetric"]{background:#fff;border:1px solid #d5e3df;border-top:4px solid #4b9ac8;border-radius:8px;padding:9px 11px}.st-key-bc_metrics [data-testid="stMetricValue"]{color:#176b55;font-size:21px}.st-key-bc_editor [data-testid="stDataFrame"]{border:1px solid #bed6cf;border-radius:8px}.st-key-bc_editor input{color:#176ba0!important;font-weight:700!important}.bc-status-ok{color:#087a4f;font-weight:800}.bc-status-warn{color:#8a6900;font-weight:800}.bc-status-bad{color:#c33d40;font-weight:800}</style>'''


def token():
    ctx = shared.RUN.get()
    return st.session_state.get('_auth_token') or (ctx and ctx['token'])


def money(value):
    return f'{int(value or 0):,}원'


def flash():
    item = st.session_state.pop('_bc_notice', None)
    if item:
        getattr(st, item[0])(item[1])


def context_header(companies):
    st.html(CSS)
    st.html('<div class="bc-hero"><small>EXTERNAL AUDIT · BALANCE CONFIRMATION</small><strong>채권채무확인서</strong>회사별 거래처 잔액 등록부터 확인서 발송·회신까지 관리합니다.</div>')
    with st.container(key='bc_context'):
        a, b, c = st.columns([1.4, .55, .7])
        company = a.selectbox('대상 법인', companies, key='bc_company')
        year = b.number_input('결산연도', 2000, 2100, date.today().year - 1, key='bc_year')
        base_date = c.date_input('확인 기준일', date(int(year), 12, 31), key='bc_base_date')
    return company, int(year), base_date


def summary_panel(c, company, year):
    values = db.summary(c, company, year)
    with st.container(key='bc_metrics'):
        cols = st.columns(4)
        cols[0].metric('대상 거래처', f"{values['parties']:,}개", f"메일 누락 {values['missing_email']:,}개")
        cols[1].metric('채권 잔액', money(values['receivable']))
        cols[2].metric('채무 잔액', money(values['payable']))
        rate = round(values['replied'] / values['sent'] * 100) if values['sent'] else 0
        cols[3].metric('발송 / 회신', f"{values['sent']:,} / {values['replied']:,}건", f'회신율 {rate}%')


def counterparties_tab(c, company, year):
    st.html('<div class="bc-title">① 거래처·채권채무 잔액</div>')
    st.caption('아마란스 자료의 거래처명·계정과목·잔액을 읽습니다. 같은 거래처의 여러 계정은 확인서 한 통에 묶지만 계정별 금액은 합치지 않고 각각 표시합니다.')
    uploaded = st.file_uploader('아마란스 거래처별 잔액 XLSX 또는 CSV', type=['xlsx', 'xlsm', 'csv'], key=f'bc_upload_{company}_{year}')
    if uploaded:
        digest = hashlib.sha256(uploaded.getvalue()).hexdigest()
        cache_key = f'_bc_import_{company}_{year}'
        cached = st.session_state.get(cache_key)
        if not cached or cached['digest'] != digest:
            try:
                parsed = db.parse_upload(uploaded.name, uploaded.getvalue())
                st.session_state[cache_key] = {'digest': digest, 'name': uploaded.name, 'rows': parsed}
            except ValueError as exc:
                st.error(str(exc)); parsed = []
        else:
            parsed = cached['rows']
        if parsed:
            st.success(f'{uploaded.name}에서 {len(parsed):,}개 계정 행을 찾았습니다.')
            st.dataframe(pd.DataFrame(parsed).drop(columns=['source'], errors='ignore'), hide_index=True, use_container_width=True, height=220)
            if st.button('가져온 자료 등록·갱신', type='primary', key='bc_import_save'):
                try:
                    db.save_counterparty_rows(c, company, year, parsed)
                    st.session_state['_bc_notice'] = ('success', f'{len(parsed):,}개 계정 행을 등록·갱신했습니다.')
                    st.session_state.pop(cache_key, None); st.rerun()
                except (ValueError, PermissionError) as exc: st.error(str(exc))
    records = db.counterparties(c, company, year)
    frame = pd.DataFrame([{'id': row['id'], '거래처명': row['counterparty'], '사업자번호': row['business_no'], '구분': row['balance_side'],
        '계정과목': row['account'], '채권채무 잔액': row['balance'], '담당자명': row['contact_name'], '메일주소': row['email'],
        '연락처': row['phone'], '주소': row['address'], '비고': row['note']} for row in records],
        columns=['id', '거래처명', '사업자번호', '구분', '계정과목', '채권채무 잔액', '담당자명', '메일주소', '연락처', '주소', '비고'])
    with st.container(key='bc_editor'):
        edited = st.data_editor(frame, num_rows='dynamic', hide_index=True, use_container_width=True, height=420,
          column_config={'id': None, '구분': st.column_config.SelectboxColumn(options=list(db.SIDES), required=True),
            '채권채무 잔액': st.column_config.NumberColumn(format='%,d', min_value=0, required=True),
            '거래처명': st.column_config.TextColumn(required=True), '계정과목': st.column_config.TextColumn(required=True)})
    if st.button('거래처·잔액 수정사항 저장', type='primary', key='bc_grid_save'):
        try:
            prepared = []
            for row in edited.to_dict('records'):
                if not str(row.get('거래처명', '') or '').strip() and not str(row.get('계정과목', '') or '').strip(): continue
                prepared.append(row)
            current_ids = {int(row['id']) for row in prepared if pd.notna(row.get('id')) and str(row.get('id')).strip()}
            remove = {row['id'] for row in records} - current_ids
            db.save_counterparty_rows(c, company, year, prepared, remove)
            st.session_state['_bc_notice'] = ('success', '거래처·잔액 수정사항을 저장했습니다.'); st.rerun()
        except (ValueError, PermissionError) as exc: st.error(str(exc))


def profile_tab(c, company):
    st.html('<div class="bc-title">② 공인회계법인·회신처 설정</div>')
    st.caption('확인서에 표시될 회사 정보와 거래처가 직접 회신할 담당 공인회계법인 정보를 등록합니다.')
    row = db.profile(c, company)
    with st.form(f'bc_profile_{company}_{row["version"]}'):
        a, b = st.columns(2)
        business_no = a.text_input('당사 사업자등록번호', row['business_no']); address = b.text_input('당사 주소', row['address'])
        a, b, d = st.columns(3)
        company_contact = a.text_input('당사 담당자', row['company_contact']); company_phone = b.text_input('당사 연락처', row['company_phone']); company_email = d.text_input('당사 이메일', row['company_email'])
        st.markdown('**담당 공인회계법인**')
        a, b = st.columns(2)
        audit_firm = a.text_input('공인회계법인명', row['audit_firm']); auditor_name = b.text_input('담당 공인회계사·직원', row['auditor_name'])
        a, b = st.columns(2)
        auditor_phone = a.text_input('회계법인 연락처', row['auditor_phone']); auditor_email = b.text_input('회신 이메일', row['auditor_email'])
        auditor_address = st.text_input('회신 주소', row['auditor_address'])
        submitted = st.form_submit_button('회계법인·회신처 정보 저장', type='primary')
    if submitted:
        try:
            db.save_profile(c, company, locals(), row['version'])
            st.session_state['_bc_notice'] = ('success', '회계법인·회신처 정보를 저장했습니다.'); st.rerun()
        except (ValueError, PermissionError) as exc: st.error(str(exc))
    st.html('<div class="bc-note">회신은 감사의 독립성을 위해 당사가 아니라 담당 공인회계법인으로 직접 받도록 확인서에 표시합니다.</div>')


def prepare_all(c, company, year, base_date):
    made = 0; skipped = []
    for group in db.group_counterparties(c, company, year):
        if group['needs_review'] or not group['email']:
            skipped.append(group['counterparty']); continue
        db.prepare_dispatch(c, company, year, base_date, group); made += 1
    return made, skipped


def letters_tab(c, company, year, base_date):
    st.html('<div class="bc-title">③ 확인서 작성·미리보기</div>')
    profile = db.profile(c, company); groups = db.group_counterparties(c, company, year)
    if not profile['audit_firm'] or not profile['auditor_email']:
        st.warning('먼저 ② 회계법인 정보에서 공인회계법인명과 회신 이메일을 등록하세요.')
    if not groups:
        st.info('① 거래처·잔액에서 확인 대상 자료를 등록하세요.'); return
    a, b = st.columns([1, 3])
    if a.button('발송 대상 일괄 준비', type='primary', disabled=not profile['audit_firm'] or not profile['auditor_email']):
        made, skipped = prepare_all(c, company, year, base_date)
        st.session_state['_bc_notice'] = ('success', f'확인서 {made:,}건을 준비했습니다.' + (f' 검토·메일 누락 {len(skipped):,}건은 제외했습니다.' if skipped else '')); st.rerun()
    group = b.selectbox('미리볼 거래처', groups, format_func=lambda x: f"{x['counterparty']} · {x['side']} · {x['total']:,}원", key='bc_group_preview')
    if group['needs_review']: st.warning('채권·채무 구분이 혼합되거나 미분류된 계정이 있습니다. 잔액표에서 먼저 확인하세요.')
    dispatch = next((row for row in db.dispatches(c, company, year) if row['counterparty'] == group['counterparty']), None)
    if st.button('선택 거래처 확인서 준비·갱신', disabled=group['needs_review'] or not profile['audit_firm'] or not profile['auditor_email']):
        db.prepare_dispatch(c, company, year, base_date, group)
        st.session_state['_bc_notice'] = ('success', '선택 거래처 확인서를 준비했습니다.'); st.rerun()
    if not dispatch:
        st.info('선택 거래처 확인서를 준비하면 확인번호가 발급되고 미리보기가 표시됩니다.'); return
    content = report.confirmation_html(company, profile, dispatch, group)
    st.download_button('확인서 인쇄 HTML 내려받기', content, file_name=f"{dispatch['confirmation_no']}_{group['counterparty']}_채권채무확인서.html", mime='text/html')
    components.html(content.decode('utf-8'), height=650, scrolling=True)


def sending_tab(c, company, year):
    st.html('<div class="bc-title">④ 메일 발송</div>')
    dispatches = db.dispatches(c, company, year)
    if not dispatches:
        st.info('③ 확인서 작성에서 발송 대상 확인서를 먼저 준비하세요.'); return
    current = st.selectbox('발송할 확인서', dispatches, format_func=lambda x: f"{x['confirmation_no']} · {x['counterparty']} · {x['status']}", key='bc_send_pick')
    group = next((g for g in db.group_counterparties(c, company, year) if g['counterparty'] == current['counterparty']), None)
    if not group: st.error('거래처 원자료를 찾을 수 없습니다.'); return
    profile = db.profile(c, company); content = report.confirmation_html(company, profile, current, group)
    settings = mail.settings(token())
    if not settings['has_secret']:
        st.info('관리자가 작업 화면 → 사용자 관리 → 메일서버 설정을 먼저 저장하세요.'); return
    st.caption(f"발신: {settings['name']} <{settings['sender']}> · 수신: {current['recipient_email'] or '메일주소 없음'}")
    key = f"bc_mail_{current['id']}_{current['version']}_"
    to = st.text_input('받는 사람', current['recipient_email'], key=key+'to')
    cc = st.text_input('참조', profile['auditor_email'], key=key+'cc')
    subject = st.text_input('제목', f"[{current['confirmation_no']}] {company} {group['side']} 잔액 확인 요청", key=key+'subject')
    body = st.text_area('본문', f"안녕하세요.\n외부감사와 관련하여 {current['base_date']} 기준 {group['side']} 잔액 확인을 요청드립니다.\n첨부 확인서를 검토한 뒤 담당 공인회계법인으로 직접 회신해 주시기 바랍니다.\n감사합니다.", height=140, key=key+'body')
    attachment = {'name': f"{current['confirmation_no']}_{current['counterparty']}_채권채무확인서.html", 'content': content, 'mime': 'text/html'}
    source = f"balance-confirmation:{current['id']}:{current['version']}"
    if st.button('메일 미리보기 만들기', type='primary', disabled=not to, key=key+'preview'):
        try:
            job_id = mail.prepare(token(), f'bc:{company}:{year}', source, to, cc, subject, body, [attachment])
            st.session_state['_bc_pending_mail'] = (current['id'], job_id, source); st.rerun()
        except (ValueError, PermissionError) as exc: st.error(str(exc))
    pending = st.session_state.get('_bc_pending_mail')
    if pending and pending[0] == current['id']:
        try:
            job = mail.job(token(), pending[1]); payload = job['payload']
            st.markdown('**발송 전 최종 확인**')
            st.write('받는 사람: ' + ', '.join(payload['to'])); st.write('참조: ' + (', '.join(payload['cc']) or '없음'))
            st.write('제목: ' + payload['subject']); st.write('첨부: ' + ', '.join(x['name'] for x in payload['files']))
            st.download_button('메일 EML 미리보기', job['eml'], file_name=f"{current['confirmation_no']}_메일미리보기.eml", mime='message/rfc822')
            confirmed = st.checkbox('받는 사람·제목·본문·첨부를 확인했으며 실제 발송에 동의합니다.', key=key+'confirm')
            if st.button('확인한 메일 발송', disabled=not confirmed or job['status'] != '발송대기', key=key+'send'):
                with st.spinner('메일 서버에 발송 중입니다…'):
                    status, detail = mail.send(token(), job['id'], pending[2])
                db.mark_sent(c, current['id'], job['id'], payload.get('message_id', ''), status)
                st.session_state.pop('_bc_pending_mail', None)
                st.session_state['_bc_notice'] = ('success' if status == '서버 접수' else 'warning', status + ' · ' + detail); st.rerun()
        except (ValueError, PermissionError) as exc: st.error(str(exc))
    history = mail.history(token(), f'bc:{company}:{year}')
    if history:
        with st.expander('확인서 메일 발송 이력'):
            st.dataframe([{'일시': r['created_at'], '받는 사람': ', '.join(r['payload']['to']), '제목': r['payload']['subject'], '상태': r['status'], '안내': r['detail']} for r in history], hide_index=True, use_container_width=True)


def replies_tab(c, company, year):
    st.html('<div class="bc-title">⑤ 회신 수신·완료 현황</div>')
    st.caption('네이트 받은메일함은 읽음 상태를 바꾸지 않고 최근 메일의 제목·발신자·회신 연결정보만 확인합니다.')
    st.link_button('네이트 공식 IMAP 설정 안내', 'https://mail3.nate.com/outmail/imap_guide04.html')
    allowed = st.checkbox('네이트 받은메일함을 조회하여 확인번호와 회신 연결정보를 확인합니다.', key='bc_imap_consent')
    if st.button('네이트 회신 메일 새로고침', type='primary', disabled=not allowed):
        try:
            with st.spinner('네이트 받은메일함을 확인 중입니다…'):
                messages = mail.inbox_headers(token(), 300)
                matched = db.match_inbox(c, company, year, messages)
            st.session_state['_bc_notice'] = ('success', f'회신 {len(matched):,}건을 자동 연결했습니다.' if matched else '새로 연결된 회신이 없습니다.'); st.rerun()
        except (ValueError, PermissionError) as exc: st.error(str(exc))
    records = db.dispatches(c, company, year)
    if not records:
        st.info('작성된 확인서가 없습니다.'); return
    st.dataframe([{'확인번호': r['confirmation_no'], '거래처명': r['counterparty'], '확인금액': r['total_balance'], '발송일': r['sent_at'],
        '회신일': r['replied_at'], '회신경로': r['reply_source'], '잔액판정': r['balance_match'], '상태': r['status']} for r in records],
        hide_index=True, use_container_width=True, column_config={'확인금액': st.column_config.NumberColumn(format='%,d')})
    with st.expander('수동 회신 등록·판정'):
        selected = st.selectbox('확인서', records, format_func=lambda x: f"{x['confirmation_no']} · {x['counterparty']}", key='bc_reply_pick')
        a, b = st.columns(2)
        reply_date = a.date_input('회신 수신일', date.today()); match = b.selectbox('잔액 확인 결과', ['미판정', '일치', '차이 있음'])
        note = st.text_area('회신 메모·차이 내용', selected['reply_note'])
        if st.button('회신 수신·판정 저장', type='primary'):
            try:
                db.mark_reply(c, selected['id'], '작업자 직접 등록', replied_at=str(reply_date), balance_match=match, note=note)
                st.session_state['_bc_notice'] = ('success', '회신 수신·판정을 저장했습니다.'); st.rerun()
            except (ValueError, PermissionError) as exc: st.error(str(exc))
    st.html('<div class="bc-warning">회신 메일 도착은 잔액 일치 판정과 다릅니다. 첨부 확인서와 차이 내용을 검토한 뒤 작업자가 최종 판정하세요.</div>')


def render(user=None):
    mail.actor(token())
    c = db.connect()
    companies = db.company_names()
    company, year, base_date = context_header(companies)
    flash(); summary_panel(c, company, year)
    tabs = st.tabs(['① 거래처·잔액', '② 회계법인 정보', '③ 확인서 작성', '④ 메일 발송', '⑤ 회신 현황'])
    with tabs[0]: counterparties_tab(c, company, year)
    with tabs[1]: profile_tab(c, company)
    with tabs[2]: letters_tab(c, company, year, base_date)
    with tabs[3]: sending_tab(c, company, year)
    with tabs[4]: replies_tab(c, company, year)
