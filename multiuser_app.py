"""Start with: streamlit run multiuser_app.py --server.address 0.0.0.0"""
from pathlib import Path
import sqlite3
import streamlit as st
import collaboration as shared

st.set_page_config(page_title='관계사 통합 수지관리', page_icon='📊', layout='wide')

# The same stylesheet also covers login, administration and the legacy settlement UI.
st.markdown('<style>' + Path(__file__).with_name('monthly_theme.css').read_text(encoding='utf-8') + '</style>', unsafe_allow_html=True)


def refresh():
    token = st.session_state.get('_auth_token')
    st.session_state.clear()
    if token:
        st.session_state['_auth_token'] = token


def login_screen():
    st.title('관계사 통합 수지관리 · 로그인')
    with shared.security_db() as c:
        exists = c.execute('SELECT 1 FROM users LIMIT 1').fetchone()
    if not exists:
        st.info('서버에서 먼저 `python collaboration.py create-admin`을 실행해 최초 관리자 계정을 만드세요.')
        st.stop()
    with st.form('login'):
        username = st.text_input('아이디')
        password = st.text_input('비밀번호', type='password')
        submit = st.form_submit_button('로그인', type='primary')
    if submit:
        token = shared.login(username, password)
        if token:
            st.session_state.clear()
            st.session_state['_auth_token'] = token
            st.rerun()
        st.error('로그인할 수 없습니다. 아이디·비밀번호를 확인하세요. 5회 실패 시 15분간 잠깁니다.')
    st.stop()


def require_admin():
    try:
        return shared.require_admin(st.session_state.get('_auth_token'))
    except PermissionError as e:
        st.error(str(e))
        st.stop()


def account_panel(user):
    with st.sidebar:
        st.caption(f"{user['display_name']} ({user['username']}) · {'관리자' if user['admin'] else '사용자'}")
        with st.expander('계정 · 새로고침'):
            if st.button('로그아웃'):
                shared.logout(st.session_state.get('_auth_token'))
                st.session_state.clear()
                st.rerun()
            st.button('최신 자료 새로고침', on_click=refresh,
                      help='저장하지 않은 입력은 지워집니다.')
            with st.expander('내 비밀번호 변경'):
                with st.form('my_password'):
                    old = st.text_input('현재 비밀번호', type='password')
                    new = st.text_input('새 비밀번호 (12자 이상)', type='password')
                    confirm = st.text_input('새 비밀번호 확인', type='password')
                    submit = st.form_submit_button('비밀번호 변경')
                if submit:
                    try:
                        if new != confirm:
                            raise ValueError('새 비밀번호가 일치하지 않습니다.')
                        shared.change_password(st.session_state['_auth_token'], old, new)
                        st.session_state.clear()
                        st.rerun()
                    except (ValueError, PermissionError) as e:
                        st.error(str(e))
        return st.radio('작업 화면', ['결산 업무', '변경 이력'] + (['사용자 관리'] if user['admin'] else []), key='_workspace')


def user_management():
    require_admin()
    st.title('사용자 관리')
    st.caption('활성 계정은 관리자 포함 최대 10명입니다. 모든 활성 사용자는 전체 업무 자료를 조회·입력·수정할 수 있습니다.')
    with shared.security_db() as c:
        users = c.execute('SELECT username,display_name,admin,active FROM users ORDER BY username').fetchall()
    st.dataframe([dict(zip(['아이디','이름','관리자','활성'], row)) for row in users], hide_index=True)
    with st.form('create_user', clear_on_submit=True):
        st.subheader('계정 추가')
        username = st.text_input('새 아이디')
        name = st.text_input('이름')
        password = st.text_input('초기 비밀번호 (12자 이상)', type='password')
        admin = st.checkbox('관리자 권한 부여')
        submit = st.form_submit_button('계정 생성')
    if submit:
        try:
            shared.create_user(st.session_state['_auth_token'], username, name, password, admin)
            st.success('계정을 생성했습니다.')
        except (ValueError, PermissionError) as e:
            st.error(str(e))
    selected = st.selectbox('변경할 계정', [row[0] for row in users])
    row = next(row for row in users if row[0] == selected)
    with st.form('manage_' + selected, clear_on_submit=True):
        active = st.checkbox('계정 활성', value=bool(row[3]))
        admin = st.checkbox('관리자', value=bool(row[2]))
        password = st.text_input('재설정할 비밀번호 (빈칸이면 유지)', type='password')
        submit = st.form_submit_button('계정 변경 적용')
    if submit:
        try:
            shared.manage_user(st.session_state['_auth_token'], selected, active, admin, password)
            st.success('변경했습니다. 해당 계정의 기존 로그인은 종료됩니다.')
        except (ValueError, PermissionError) as e:
            st.error(str(e))


def history_panel(user):
    st.title('변경 이력')
    files = sorted(list(shared.DATA.glob('finance_*.db')) + list(shared.DATA.glob('lb_monthly_*.db')) + list(shared.DATA.glob('joint_venture.db')))
    if files:
        path = st.selectbox('회계연도 DB', files, format_func=lambda p: p.stem)
        with sqlite3.connect(f'file:{path}?mode=ro', uri=True) as c:
            exists = c.execute("SELECT 1 FROM sqlite_master WHERE name='change_history'").fetchone()
            if exists:
                import pandas as pd
                st.dataframe(pd.read_sql_query('SELECT at AS 시각_UTC,actor AS 사용자,table_name AS 자료,operation AS 작업,before_json AS 변경전,after_json AS 변경후 FROM change_history ORDER BY id DESC LIMIT 500', c), hide_index=True)
                st.caption('가장 최근 500건입니다. 다중 사용자 버전으로 전환한 뒤의 변경부터 기록됩니다.')
            else:
                st.info('이 연도의 결산 업무 화면을 열면 변경 이력 기록이 시작됩니다.')
    if user['admin']:
        with shared.security_db() as c:
            import pandas as pd
            st.subheader('계정·운영 이력')
            st.dataframe(pd.read_sql_query('SELECT at,actor,action,detail FROM events ORDER BY id DESC LIMIT 200', c), hide_index=True)


def backup_panel(c, year):
    require_admin()
    st.subheader('백업 및 복원')
    st.caption('매일 첫 변경 전에 자동 백업합니다. 원장 교체 전에도 별도 백업합니다. 백업은 서버 private/backups에 보관됩니다.')
    if st.button('현재 자료 백업 만들기'):
        saved = shared.backup_database(c.path)
        with shared.security_db() as log:
            shared.event(log, shared.require_admin(st.session_state['_auth_token'])['username'], '수동 백업', saved.name)
        st.success('백업을 생성했습니다.')
    files = sorted((shared.STATE / 'backups').glob(f'finance_{int(year)}-*.sqlite'), reverse=True)
    if files:
        selected = st.selectbox('저장된 백업', files, format_func=lambda p: p.name)
        st.download_button('백업 내려받기', selected.read_bytes(), file_name=selected.name)
    uploaded = st.file_uploader('복원할 동일 버전·동일 연도 백업', type=['sqlite','db'], key='restore_upload')
    confirmed = st.checkbox('현재 연도 자료 전체를 백업 내용으로 되돌립니다. 다른 사용자의 작업도 영향을 받습니다.')
    if st.button('백업 복원 실행', disabled=not uploaded or not confirmed):
        try:
            c.rollback()
            shared.restore_database(st.session_state['_auth_token'], c.path, uploaded.getvalue(), c.expected)
            refresh()
            st.rerun()
        except (ValueError, sqlite3.Error, PermissionError) as e:
            st.error(f'복원하지 못했습니다: {e}')


token = st.session_state.get('_auth_token')
user = shared.validate_session(token)
if not user:
    if token:
        st.session_state.clear()
    login_screen()

with shared.LOCK:
    workspace = account_panel(user)
    if workspace == '사용자 관리':
        user_management()
    elif workspace == '변경 이력':
        history_panel(user)
    else:
        program=st.radio('프로그램 선택',['자체결산 보고','엘비데크 월별보고','공동도급 관리대장'],key='main_system',horizontal=True,label_visibility='collapsed')
        if st.session_state.get('_conflict'):
            st.error(st.session_state['_conflict'])
            st.info('저장되지 않은 입력을 복사해 보관한 뒤 왼쪽의 최신 자료 새로고침을 누르세요.')
            st.stop()
        context = {'token': token, 'user': user,
                   'snapshots': st.session_state.get('_snapshots', {}).copy(), 'connections': []}
        reset = shared.RUN.set(context)
        failed = False
        try:
            from monthly_app import render as render_monthly, legacy_source
            code = Path(__file__).with_name('app.py')
            scope = {'__file__': str(code), '__name__': '__finance_app__',
                     'MULTIUSER_ENTRY': True, 'current_user': user,
                     'require_admin': require_admin, 'backup_panel': backup_panel}
            if program=='공동도급 관리대장':
                from joint_app import render as render_joint
                render_joint(user)
            elif program=='엘비데크 월별보고':
                render_monthly(user)
            else:
                source=legacy_source(code.read_text(encoding='utf-8'))
                exec(compile(source, str(code), 'exec'), scope)
        except shared.StaleData as e:
            failed = True
            st.session_state['_conflict'] = str(e)
            st.error(str(e))
            st.info('저장되지 않은 입력을 보관한 뒤 왼쪽의 최신 자료 새로고침을 누르세요.')
        finally:
            snapshots = context['snapshots']
            for c in context['connections']:
                try:
                    c.rollback()
                    if not failed and c.guarded:
                        snapshots[str(c.path.resolve())] = shared.revision(c)
                    c.close()
                except sqlite3.ProgrammingError:
                    pass
            if not failed:
                st.session_state['_snapshots'] = snapshots
            shared.RUN.reset(reset)
