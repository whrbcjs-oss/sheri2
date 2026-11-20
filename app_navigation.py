"""Shared two-level navigation; existing program routing values stay compatible."""
import streamlit as st

VERSION = '2026.11.20.45'
HOME = '회계 신고 일정'
REPORTS = ['엘비데크 월별보고', '자체결산 보고', '법인결산']
PROGRAMS = [HOME] + REPORTS + ['공동도급 관리대장', '대여금관리', '한국은행 기업경기조사', '현장숙소(전·월세)관리', '주민세(사업소분) 관리']
CSS = '''<style>
#root .app-brand-row {display:flex;align-items:center;justify-content:space-between;gap:20px;margin:0 0 16px;}
#root .app-brand {font-size:25px;font-weight:850;letter-spacing:-.7px;color:#102a35;}
#root .app-brand-version {font-size:12px;color:#7b8b86;white-space:nowrap;}
#root .st-key-app_primary_navigation {background:linear-gradient(180deg,#e7f7f1 0%,#ddf3eb 100%);border:1px solid #b9dfd1;border-radius:22px;padding:4px 8px;box-shadow:0 3px 10px #24566e12;}
#root .st-key-app_primary_navigation [data-testid="stButton"] button {border:1px solid transparent;border-radius:16px;min-height:34px;padding:4px 9px;width:100%;background:transparent;color:#176b55;box-shadow:none;}
#root .st-key-app_primary_navigation [data-testid="stButton"] button p {font-size:15px!important;font-weight:700;color:#176b55!important;white-space:normal;}
#root .st-key-app_primary_navigation [data-testid="stButton"] button:hover {background:#f5fcf9;border-color:#c7e5da;}
#root .st-key-app_primary_navigation [data-testid="stButton"] button[kind="primary"] {background:#ffffff!important;border:1px solid #9fd3c1!important;border-bottom:3px solid #20a574!important;box-shadow:0 2px 7px #176b5515;}
#root .st-key-app_primary_navigation [data-testid="stButton"] button[kind="primary"] p {font-weight:800;}
#root .st-key-app_secondary_navigation {background:linear-gradient(180deg,#f8fcfa,#edf8f4);border:1px solid #d6eae0;border-top:0;border-radius:0 0 18px 18px;padding:4px 24px 0;margin-top:-7px;}
#root .st-key-app_secondary_navigation [data-testid="stButton"] button {background:transparent;border:0;border-radius:0;min-height:32px;padding:4px 12px;color:#233b48;box-shadow:none;}
#root .st-key-app_secondary_navigation [data-testid="stButton"] button p {font-size:17px!important;color:#233b48!important;font-weight:650;white-space:nowrap;}
#root .st-key-app_secondary_navigation [data-testid="stButton"] button[kind="primary"] {background:transparent!important;border-bottom:3px solid #0b8754!important;}
#root .st-key-app_secondary_navigation [data-testid="stButton"] button[kind="primary"] p {color:#086441!important;font-weight:800;}
#root .app-nav-context {font-size:14px;color:#376a54;padding:4px 4px 6px;font-weight:600;}
#root .app-breadcrumb {font-size:13px;color:#74877e;margin:2px 0 4px;}
@media(max-width:800px) {#root .st-key-app_primary_navigation {border-radius:20px;}#root .st-key-app_primary_navigation [data-testid="stButton"] button p {font-size:15px!important;white-space:normal;}}
#root [data-testid="stHeader"]::after {content:"버전 2026.11.20.45";position:absolute;right:144px;top:16px;font-size:11px;color:#7b8b86;pointer-events:none;}
</style>'''


def select_program(program):
    if program not in PROGRAMS:
        return
    st.session_state['main_system'] = program
    if program in REPORTS:
        st.session_state['_last_report_system'] = program


def select_reports():
    select_program(REPORTS[0])


def render():
    program = st.session_state.get('main_system', HOME)
    if program not in PROGRAMS:
        program = HOME
    st.session_state['main_system'] = program
    if program in REPORTS:
        st.session_state['_last_report_system'] = program
    st.html(CSS)
    with st.container(key='app_primary_navigation'):
        columns = st.columns([.55,.8,1.25,.85,1.3,1.4,1.55], gap='small', vertical_alignment='center')
        columns[0].button('홈', icon=':material/home:', key='app_nav_home', use_container_width=True,
            type='primary' if program == HOME else 'secondary', on_click=select_program, args=(HOME,))
        columns[1].button('결산보고서', key='app_nav_reports', use_container_width=True,
            type='primary' if program in REPORTS else 'secondary', on_click=select_reports)
        for column, name, key in [(columns[2], '공동도급 관리대장', 'joint'), (columns[3], '대여금관리', 'loans'), (columns[4], '한국은행 기업경기조사', 'survey'), (columns[5], '현장숙소(전·월세)관리', 'accommodation'), (columns[6], '주민세(사업소분) 관리', 'resident_tax')]:
            column.button(name, key='app_nav_' + key, use_container_width=True,
                type='primary' if program == name else 'secondary', on_click=select_program, args=(name,))
    if program not in REPORTS:return program
    with st.container(key='app_secondary_navigation'):
        if program in REPORTS:
            columns = st.columns([1.5,1.2,1.2,3], gap='small')
            for column, name, key in zip(columns, REPORTS, ['monthly','self','corporate']):
                column.button(name, key='app_report_' + key, use_container_width=True,
                    type='primary' if program == name else 'secondary', on_click=select_program, args=(name,))
        else:
            st.markdown('<div class="app-nav-context">' + ('회계 신고·납부 일정' if program == HOME else program) + '</div>', unsafe_allow_html=True)
    breadcrumb = '결산보고서　›　' + program if program in REPORTS else ('홈　›　회계 신고·납부 일정' if program == HOME else program)
    st.markdown('<div class="app-breadcrumb">' + breadcrumb + '</div>', unsafe_allow_html=True)
    return program
