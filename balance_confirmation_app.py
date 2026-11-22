"""PC-first receivable/payable confirmation workflow."""
import hashlib
from datetime import date
from html import escape

import streamlit as st
import streamlit.components.v1 as components

import balance_confirmation_store as db
import balance_confirmation_report as report
import collaboration as shared
import mail_service as mail


CSS = '''<style>
.bc-hero{background:linear-gradient(125deg,#edf8f5,#e6f3fa);border:1px solid #bcdad2;border-left:6px solid #2d95aa;border-radius:9px;padding:13px 16px;margin:4px 0 12px;color:#244955}.bc-hero small{display:block;color:#4b8782;font-weight:700;letter-spacing:.05em}.bc-hero strong{display:block;font-size:23px;margin-top:2px}.bc-title{background:#eaf5fb;color:#24566e;border-left:6px solid #4b9ac8;border-bottom:2px solid #afd3e5;border-radius:6px 6px 0 0;padding:8px 11px;font-size:18px;font-weight:800;margin:12px 0 8px}.bc-note{background:#eef8f4;border:1px solid #c4e2d6;border-radius:7px;padding:9px 11px;color:#315c50}.bc-warning{background:#fff8df;border:1px solid #e3cc73;border-radius:7px;padding:9px 11px;color:#765b00}.st-key-bc_context{background:#fff;border:1px solid #cfe0dc;border-radius:8px;padding:10px 13px}.st-key-bc_metrics [data-testid="stMetric"]{background:#fff;border:1px solid #d5e3df;border-top:4px solid #4b9ac8;border-radius:8px;padding:9px 11px}.st-key-bc_metrics [data-testid="stMetricValue"]{color:#176b55;font-size:21px}.bc-status-ok{color:#087a4f;font-weight:800}.bc-status-warn{color:#8a6900;font-weight:800}.bc-status-bad{color:#c33d40;font-weight:800}.st-key-bc_account_head{background:#eaf2ef;border-top:1px solid #c8dcd5;border-bottom:1px solid #c8dcd5;padding:7px 9px}.bc-account-head{text-align:center;color:#60776c;font-size:12px;font-weight:800}[class*="st-key-bc_account_row_"]{border-bottom:1px solid #dce8e3;padding:7px 9px;background:#fff}[class*="st-key-bc_account_row_selected_"]{background:#e8f4fa;border-left:5px solid #4b9ac8}[class*="st-key-bc_account_row_"] [data-testid="column"]{display:flex;align-items:center;justify-content:flex-end;min-width:0}[class*="st-key-bc_account_row_"] [data-testid="column"]:first-child{justify-content:flex-start}[class*="st-key-bc_account_row_"] button{background:transparent!important;border:0!important;box-shadow:none!important;color:#173f59!important;text-align:left!important;padding:2px 0!important;font-weight:800!important}.bc-account-cell{width:100%;text-align:right;font-size:12px;color:#314b43;font-variant-numeric:tabular-nums;white-space:nowrap}.bc-account-cell.center{text-align:center}.bc-account-cell small{display:block;color:#80918b;font-size:10px}.bc-account-badge{display:inline-block;border-radius:999px;padding:3px 8px;background:#e7f2fb;color:#176ba0;font-weight:800}.bc-account-badge.debt{background:#eee9fb;color:#6247a6}.bc-account-badge.review{background:#fff0a8;color:#725a00}.st-key-bc_account_detail{background:#fff;border:1px solid #cbded7;border-radius:9px;padding:13px 14px;margin-top:12px}.st-key-bc_account_detail input,.st-key-bc_account_detail textarea{color:#176ba0!important;font-weight:700!important}.bc-detail-head{display:flex;justify-content:space-between;align-items:center;background:#edf6fc;border-left:6px solid #4b9ac8;padding:9px 12px;margin-bottom:9px}.bc-detail-head strong{font-size:18px;color:#173f59}.bc-detail-head span{color:#687d77;font-size:12px}@media(max-width:900px){.bc-account-cell,.bc-account-head{font-size:10px}}</style>'''


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
        cols[1].metric('공사미수금 등 채권 잔액', money(values['receivable']))
        cols[2].metric('등록 계정과목', f"{len(db.account_types(c)):,}개")
        rate = round(values['replied'] / values['sent'] * 100) if values['sent'] else 0
        cols[3].metric('발송 / 회신', f"{values['sent']:,} / {values['replied']:,}건", f'회신율 {rate}%')


def counterparties_tab(c, company, year):
    st.html('<div class="bc-title">① 거래처·채권 잔액</div>')
    st.caption('모든 자료는 채권으로 관리합니다. 아마란스 파일에서는 거래처명·채권잔액만 읽고, 담당자·메일·연락처·주소는 등록 후 직접 입력합니다.')
    accounts = db.account_types(c)
    account_names = [row['name'] for row in accounts]
    with st.expander('계정과목 관리', expanded=not account_names):
        st.caption('기본 계정은 공사미수금·미수금입니다. 필요한 채권 계정을 추가할 수 있습니다.')
        selected_type = st.selectbox('등록된 계정과목', [None] + accounts,
            format_func=lambda x: '새 계정과목 추가' if x is None else x['name'], key='bc_account_type_pick')
        a, b, d = st.columns([2.4, .8, .8])
        type_name = a.text_input('계정과목명', selected_type['name'] if selected_type else '', key=f"bc_account_type_name_{selected_type['id'] if selected_type else 0}")
        if b.button('저장', type='primary', use_container_width=True, key='bc_account_type_save'):
            try:
                db.save_account_type(c, type_name, selected_type['id'] if selected_type else None, selected_type['version'] if selected_type else None)
                st.session_state['_bc_notice'] = ('success', '계정과목을 저장했습니다.'); st.rerun()
            except (ValueError, PermissionError) as exc: st.error(str(exc))
        if d.button('삭제', disabled=selected_type is None, use_container_width=True, key='bc_account_type_delete'):
            try:
                db.delete_account_type(c, selected_type['id'], selected_type['version'])
                st.session_state['_bc_notice'] = ('success', '계정과목을 삭제했습니다.'); st.rerun()
            except (ValueError, PermissionError) as exc: st.error(str(exc))
    if not account_names:
        st.warning('업로드 전에 계정과목을 등록하세요.'); return
    upload_account = st.selectbox('업로드 자료에 적용할 계정과목', account_names, key=f'bc_upload_account_{company}_{year}')
    uploaded = st.file_uploader('아마란스 거래처별 잔액 XLSX 또는 CSV', type=['xlsx', 'xlsm', 'csv'], key=f'bc_upload_{company}_{year}')
    if uploaded:
        digest = hashlib.sha256(uploaded.getvalue()).hexdigest()
        cache_key = f'_bc_import_{company}_{year}'
        cached = st.session_state.get(cache_key)
        if not cached or cached['digest'] != digest or cached.get('account') != upload_account:
            try:
                parsed = db.parse_upload(uploaded.name, uploaded.getvalue(), upload_account)
                st.session_state[cache_key] = {'digest': digest, 'account': upload_account, 'name': uploaded.name, 'rows': parsed}
            except ValueError as exc:
                st.error(str(exc)); parsed = []
        else:
            parsed = cached['rows']
        if parsed:
            st.success(f'{uploaded.name}에서 {len(parsed):,}개 계정 행을 찾았습니다.')
            with st.expander('가져올 계정 미리보기', expanded=True):
                widths=[2.1,1.6,1.25]
                with st.container(key='bc_import_head'):
                    cols=st.columns(widths);labels=['거래처명','계정과목','채권잔액']
                    for col,label in zip(cols,labels):col.html(f'<div class="bc-account-head">{label}</div>')
                for index,row in enumerate(parsed[:20]):
                    cols=st.columns(widths);cols[0].write(row['거래처명']);cols[1].write(row['계정과목']);cols[2].write(f"{row['채권채무 잔액']:,}원")
                if len(parsed)>20:st.caption(f'나머지 {len(parsed)-20:,}개 행은 등록 후 아래 목록에서 검색할 수 있습니다.')
            if st.button('가져온 자료 등록·갱신', type='primary', key='bc_import_save'):
                try:
                    db.save_counterparty_rows(c, company, year, parsed)
                    st.session_state['_bc_notice'] = ('success', f'{len(parsed):,}개 계정 행을 등록·갱신했습니다.')
                    st.session_state.pop(cache_key, None); st.rerun()
                except (ValueError, PermissionError) as exc: st.error(str(exc))
    records = db.counterparties(c, company, year)
    controls=st.columns([1.8,.8,.7])
    query=controls[0].text_input('업체명·계정과목 검색',key=f'bc_account_search_{company}_{year}')
    filter_=controls[1].selectbox('조회 상태',['전체','입력 확인 필요','메일 누락'],key=f'bc_account_filter_{company}_{year}')
    if controls[2].button('새 항목 추가',type='primary',use_container_width=True,key='bc_account_new'):
        st.session_state['bc_account_selected_id']=0;st.rerun()
    visible=[]
    for row in records:
        searchable=(row['counterparty']+' '+row['account']).casefold()
        needs=not row['business_no'] or not row['contact_name'] or not row['email']
        if query.strip().casefold() not in searchable:continue
        if filter_=='입력 확인 필요' and not needs:continue
        if filter_=='메일 누락' and row['email']:continue
        visible.append(row)
    selected_id=st.session_state.get('bc_account_selected_id')
    if selected_id not in [row['id'] for row in records]+[0]:selected_id=records[0]['id'] if records else 0
    st.session_state['bc_account_selected_id']=selected_id
    widths=[2.2,1.45,1.2,1.4,.8]
    with st.container(key='bc_account_head'):
        cols=st.columns(widths,gap='small')
        for col,label in zip(cols,['거래처명','계정과목','채권잔액','담당자·메일','상태']):col.html(f'<div class="bc-account-head">{label}</div>')
    if not visible:st.info('선택한 조건에 해당하는 계정이 없습니다.')
    for row in visible:
        style='selected' if row['id']==selected_id else 'normal';needs=not row['business_no'] or not row['contact_name'] or not row['email']
        with st.container(key=f'bc_account_row_{style}_{row["id"]}'):
            cols=st.columns(widths,gap='small')
            if cols[0].button(row['counterparty'],key=f'bc_pick_{row["id"]}',use_container_width=True):
                st.session_state['bc_account_selected_id']=row['id'];st.rerun()
            cols[0].html(f'<div class="bc-account-cell" style="text-align:left"><small>{escape(row["business_no"] or "사업자번호 미입력")}</small></div>')
            cols[1].html(f'<div class="bc-account-cell center">{escape(row["account"])}</div>')
            cols[2].html(f'<div class="bc-account-cell">{row["balance"]:,}</div>')
            cols[3].html(f'<div class="bc-account-cell center">{escape(row["contact_name"] or "-")}<small>{escape(row["email"] or "메일 미입력")}</small></div>')
            cols[4].html(f'<div class="bc-account-cell center"><span class="bc-account-badge {"review" if needs else ""}">{"확인 필요" if needs else "입력 완료"}</span></div>')
    selected=next((row for row in records if row['id']==selected_id),None)
    old=selected or {'counterparty':'','business_no':'','balance_side':'채권','account':account_names[0],'balance':0,'contact_name':'','email':'','phone':'','address':'','note':'','version':0,'source':'직접 입력'}
    with st.container(key='bc_account_detail'):
        st.html(f'<div class="bc-detail-head"><div><span>{"선택 계정 수정" if selected else "새 계정 등록"}</span><strong>{escape(old["counterparty"] or "거래처를 선택하거나 직접 입력하세요")}</strong></div><span>{escape(old.get("source", ""))}</span></div>')
        values=dict(old)
        form_epoch=hashlib.sha256(repr(sorted(values.items())).encode()).hexdigest()[:10]
        with st.form(f'bc_account_form_{company}_{year}_{selected_id}_{form_epoch}'):
            a,b=st.columns([2,1]);counterparty=a.text_input('거래처명',values.get('counterparty',''));business_no=b.text_input('사업자등록번호',values.get('business_no',''))
            a,b=st.columns([2,1.2]);account=a.selectbox('계정과목',account_names,index=account_names.index(values['account']) if values.get('account') in account_names else 0);balance=b.number_input('채권잔액',min_value=0,value=int(values.get('balance',0)),step=1)
            a,b,d=st.columns(3);contact_name=a.text_input('담당자명',values.get('contact_name',''));email=b.text_input('메일주소',values.get('email',''));phone=d.text_input('연락처',values.get('phone',''))
            address=st.text_input('주소',values.get('address',''));note=st.text_area('비고',values.get('note',''),height=80)
            submitted=st.form_submit_button('계정 정보 저장',type='primary')
        if submitted:
            try:
                payload=locals()
                saved_id=db.save_counterparty_record(c,company,year,payload,selected_id or None,old.get('version'))
                st.session_state['bc_account_selected_id']=saved_id
                st.session_state['_bc_notice']=('success','거래처·계정 정보를 저장했습니다.');st.rerun()
            except (ValueError,PermissionError) as exc:st.error(str(exc))
        if selected:
            with st.expander('선택 계정 삭제'):
                reason=st.text_input('삭제 사유',key=f'bc_delete_reason_{selected_id}');confirm=st.checkbox('선택한 계정을 삭제합니다.',key=f'bc_delete_confirm_{selected_id}')
                if st.button('선택 계정 삭제',disabled=not confirm,key=f'bc_delete_{selected_id}'):
                    try:
                        db.delete_counterparty(c,company,year,selected_id,selected['version'],reason);st.session_state['bc_account_selected_id']=0
                        st.session_state['_bc_notice']=('success','선택 계정을 삭제했습니다.');st.rerun()
                    except (ValueError,PermissionError) as exc:st.error(str(exc))


def profile_tab(c, company):
    st.html('<div class="bc-title">② 공인회계법인·회신처 설정</div>')
    st.caption('회사 기본정보는 법인별로 저장합니다. 공인회계법인과 회신처는 공통정보로 한 번만 등록하며 5개 법인이 함께 사용합니다.')
    row = db.profile(c, company)
    joint = db.joint_company_profiles()
    labels = {f"{item['name']} [{item['code']}]": item for item in joint}
    matched = next((label for label,item in labels.items() if db.normalized(item['name']) == db.normalized(company)), None)
    picked = st.selectbox('공동도급 당사·관계사 정보', [None] + list(labels),
        index=([None] + list(labels)).index(matched) if matched in labels else 0,
        format_func=lambda x: '불러올 회사를 선택하세요' if x is None else x, key=f'bc_profile_joint_{company}')
    if st.button('선택 회사 정보 불러오기', disabled=picked is None, key=f'bc_profile_joint_load_{company}'):
        values = dict(row); incoming = labels[picked]
        for field in ('business_no','representative','address','company_contact','company_email','company_phone','fax'):
            if incoming.get(field): values[field] = incoming[field]
        if not values.get('company_phone') and incoming.get('contact_phone'): values['company_phone'] = incoming['contact_phone']
        st.session_state[f'_bc_profile_prefill_{company}'] = values; st.rerun()
    row = st.session_state.get(f'_bc_profile_prefill_{company}', row)
    with st.form(f'bc_profile_{company}_{row["version"]}'):
        a, b = st.columns(2)
        business_no = a.text_input('당사 사업자등록번호', row['business_no']); representative = b.text_input('대표자', row['representative'])
        address = st.text_input('당사 주소', row['address'])
        a, b, d = st.columns(3)
        company_contact = a.text_input('당사 담당자', row['company_contact']); company_phone = b.text_input('당사 연락처', row['company_phone']); fax = d.text_input('팩스', row['fax'])
        company_email = st.text_input('당사 이메일', row['company_email'])
        st.markdown('**5개 법인 공통 공인회계법인·회신처**')
        a, b = st.columns(2)
        audit_firm = a.text_input('공인회계법인명', row['audit_firm']); auditor_name = b.text_input('담당 공인회계사·직원', row['auditor_name'])
        a, b = st.columns(2)
        auditor_phone = a.text_input('회계법인 연락처', row['auditor_phone']); auditor_email = b.text_input('회신 이메일', row['auditor_email'])
        auditor_address = st.text_input('회신 주소', row['auditor_address'])
        submitted = st.form_submit_button('회계법인·회신처 정보 저장', type='primary')
    if submitted:
        try:
            db.save_profile(c, company, locals(), row['version'], row['audit_version'])
            st.session_state.pop(f'_bc_profile_prefill_{company}', None)
            st.session_state['_bc_notice'] = ('success', '회사 기본정보와 5개 법인 공통 회계법인·회신처를 저장했습니다.'); st.rerun()
        except (ValueError, PermissionError) as exc: st.error(str(exc))
    st.html('<div class="bc-note">공통 공인회계법인 정보는 어느 법인에서 수정해도 5개 법인 전체에 즉시 적용됩니다. 회신은 감사의 독립성을 위해 담당 공인회계법인으로 직접 받도록 확인서에 표시합니다.</div>')


def prepare_all(c, company, year, base_date):
    made = 0; skipped = []
    for group in db.group_counterparties(c, company, year):
        if not group['email']:
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
    dispatch = next((row for row in db.dispatches(c, company, year) if row['counterparty'] == group['counterparty']), None)
    if st.button('선택 거래처 확인서 준비·갱신', disabled=not profile['audit_firm'] or not profile['auditor_email']):
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
