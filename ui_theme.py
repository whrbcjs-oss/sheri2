"""Per-user visual themes; no accounting data or calculations are changed."""
from html import escape

import collaboration as shared

THEMES={
    'mint':('현재 밝은 민트','기존 밝은 민트·하늘색 업무 화면'),
    'medlink':('Medlink 청록 카드','흰색 카드와 청록색 강조의 넓고 밝은 화면'),
    'contrast':('고대비 업무용','표와 숫자의 구분을 강화한 남색 업무 화면'),
}
SCALES={'90%':90,'100% (기본)':100,'110%':110}
ROW_HEIGHTS={'촘촘하게 (34px)':34,'보통 (42px)':42,'넓게 (50px)':50}
DEFAULT={'theme':'mint','scale':100,'row_height':42,'rounded':True}

def _ensure(c):
    c.execute('''CREATE TABLE IF NOT EXISTS user_ui_preferences(
      username TEXT PRIMARY KEY REFERENCES users(username) ON DELETE CASCADE,
      theme TEXT NOT NULL DEFAULT 'mint',scale INTEGER NOT NULL DEFAULT 100,
      row_height INTEGER NOT NULL DEFAULT 42,rounded INTEGER NOT NULL DEFAULT 1,
      updated_at TEXT DEFAULT CURRENT_TIMESTAMP)''')

def validate(settings):
    result=dict(settings)
    if result.get('theme') not in THEMES:raise ValueError('화면 테마를 확인하세요.')
    result['scale']=int(result.get('scale',100));result['row_height']=int(result.get('row_height',42))
    if result['scale'] not in SCALES.values():raise ValueError('화면 배율을 확인하세요.')
    if result['row_height'] not in ROW_HEIGHTS.values():raise ValueError('표 행 높이를 확인하세요.')
    result['rounded']=bool(result.get('rounded',True))
    return result

def load(username):
    with shared.security_db() as c:
        _ensure(c)
        row=c.execute('SELECT theme,scale,row_height,rounded FROM user_ui_preferences WHERE username=?',(username,)).fetchone()
    return dict(DEFAULT) if not row else validate(dict(zip(['theme','scale','row_height','rounded'],row)))

def save(token,settings):
    user=shared.validate_session(token)
    if not user:raise PermissionError('로그인 세션이 만료되었습니다. 다시 로그인하세요.')
    values=validate(settings)
    with shared.security_db() as c:
        _ensure(c)
        c.execute('''INSERT INTO user_ui_preferences(username,theme,scale,row_height,rounded,updated_at)
          VALUES(?,?,?,?,?,CURRENT_TIMESTAMP) ON CONFLICT(username) DO UPDATE SET
          theme=excluded.theme,scale=excluded.scale,row_height=excluded.row_height,
          rounded=excluded.rounded,updated_at=CURRENT_TIMESTAMP''',
          (user['username'],values['theme'],values['scale'],values['row_height'],int(values['rounded'])))
        shared.event(c,user['username'],'화면 테마 저장',values['theme'])
    return values

def css(settings):
    settings=validate(settings);radius='14px' if settings['rounded'] else '2px'
    common=f'''
<style id="sheri2-user-theme">
:root{{--s2-radius:{radius};--s2-row:{settings['row_height']}px;--s2-scale:{settings['scale']}%;}}
#root{{font-size:var(--s2-scale);}}
#root [data-testid="stDataFrame"] [role="row"],#root [data-testid="stDataEditor"] [role="row"]{{min-height:var(--s2-row)!important;}}
#root [data-testid="stMetric"],#root [data-testid="stExpander"],#root [data-testid="stVerticalBlockBorderWrapper"],
#root [data-testid="stDataFrame"],#root [data-testid="stTable"],#root .stButton button,#root .stDownloadButton button,
#root [data-baseweb="select"]>div,#root [data-testid="stTextInput"] input,#root [data-testid="stNumberInput"] input{{border-radius:var(--s2-radius)!important;}}
</style>'''
    if settings['theme']=='mint':return common
    if settings['theme']=='medlink':
        return common+'''
<style id="sheri2-medlink-theme">
#root .stApp,#root [data-testid="stAppViewContainer"]{background:#f4f5f7!important;color:#173d45!important;}
#root [data-testid="stHeader"],#root [data-testid="stSidebar"]{background:#ffffff!important;}
#root [data-testid="stSidebar"]{border-right:1px solid #e8ecee!important;}
#root .block-container{padding-top:1.2rem!important;}
#root h1,#root h2,#root h3{color:#173d45!important;letter-spacing:-.03em;}
#root [data-testid="stMetric"],#root [data-testid="stExpander"],#root [data-testid="stVerticalBlockBorderWrapper"]{background:#fff!important;border:1px solid #edf0f1!important;box-shadow:0 6px 20px rgba(31,72,80,.06)!important;}
#root [data-testid="stMetricValue"]{color:#204e56!important;}
#root .stButton button[kind="primary"],#root button[data-testid="baseButton-primary"]{background:#45a3b4!important;border-color:#45a3b4!important;color:#fff!important;}
#root .stButton button[kind="secondary"],#root .stDownloadButton button{border-color:#a9d5dd!important;color:#287b89!important;background:#fff!important;}
#root .st-key-app_primary_navigation{background:#fff!important;border:1px solid #edf0f1!important;box-shadow:0 5px 18px rgba(31,72,80,.05)!important;}
#root .st-key-app_primary_navigation [data-testid="stButton"] button{color:#52666b!important;}
#root .st-key-app_primary_navigation [data-testid="stButton"] button p{color:#52666b!important;}
#root .st-key-app_primary_navigation [data-testid="stButton"] button[kind="primary"]{background:#45a3b4!important;border-color:#45a3b4!important;border-bottom:1px solid #45a3b4!important;}
#root .st-key-app_primary_navigation [data-testid="stButton"] button[kind="primary"] p{color:#fff!important;}
#root .st-key-app_secondary_navigation{background:#fff!important;border-color:#edf0f1!important;}
#root .st-key-app_secondary_navigation [data-testid="stButton"] button[kind="primary"]{border-bottom-color:#45a3b4!important;}
#root .st-key-app_secondary_navigation [data-testid="stButton"] button[kind="primary"] p{color:#287b89!important;}
#root [data-testid="stDataFrame"],#root [data-testid="stTable"]{background:#fff!important;border-color:#e5ecee!important;box-shadow:0 4px 14px rgba(31,72,80,.04)!important;}
#root [data-testid="stAlert"]{border-radius:var(--s2-radius)!important;}
#root [data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked){background:#dff5f4!important;color:#257f8d!important;}
#root [data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) p{color:#257f8d!important;}
</style>'''
    return common+'''
<style id="sheri2-contrast-theme">
#root .stApp,#root [data-testid="stAppViewContainer"]{background:#eef2f6!important;color:#132b45!important;}
#root [data-testid="stHeader"],#root [data-testid="stSidebar"]{background:#fff!important;}
#root [data-testid="stSidebar"]{border-right:2px solid #ccd7e2!important;}
#root h1,#root h2,#root h3{color:#0e3156!important;}
#root [data-testid="stMetric"],#root [data-testid="stExpander"],#root [data-testid="stVerticalBlockBorderWrapper"]{background:#fff!important;border:1px solid #b9c9d8!important;box-shadow:none!important;}
#root [data-testid="stMetricValue"]{color:#0b376e!important;}
#root .stButton button[kind="primary"],#root button[data-testid="baseButton-primary"]{background:#0b376e!important;border-color:#0b376e!important;color:#fff!important;}
#root .st-key-app_primary_navigation{background:#0b376e!important;border-color:#0b376e!important;box-shadow:none!important;}
#root .st-key-app_primary_navigation [data-testid="stButton"] button p{color:#fff!important;}
#root .st-key-app_primary_navigation [data-testid="stButton"] button[kind="primary"]{background:#fff!important;border-color:#fff!important;border-bottom:1px solid #fff!important;}
#root .st-key-app_primary_navigation [data-testid="stButton"] button[kind="primary"] p{color:#0b376e!important;}
#root .st-key-app_secondary_navigation{background:#fff!important;border:1px solid #b9c9d8!important;}
#root [data-testid="stDataFrame"],#root [data-testid="stTable"]{border:1px solid #9fb2c5!important;background:#fff!important;}
#root [data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked){background:#dbe8f5!important;color:#0b376e!important;}
</style>'''

def active(user):
    import streamlit as st
    preview=st.session_state.get('_theme_preview')
    if isinstance(preview,dict) and preview.get('username')==user['username']:
        return validate(preview['settings'])
    return load(user['username'])

def apply(user):
    import streamlit as st
    st.html(css(active(user)))

def render_settings(user):
    import streamlit as st
    current=active(user)
    theme_ids=list(THEMES);scale_labels=list(SCALES);row_labels=list(ROW_HEIGHTS)
    with st.popover('⚙ 화면 테마 설정'):
        st.markdown('#### 화면 테마 설정')
        st.caption('계정별로 저장되며 계산식과 업무자료에는 영향을 주지 않습니다.')
        with st.form('ui_theme_settings_'+user['username']):
            theme=st.radio('테마',theme_ids,index=theme_ids.index(current['theme']),format_func=lambda key:THEMES[key][0])
            st.caption(escape(THEMES[theme][1]))
            scale_label=st.selectbox('화면 배율',scale_labels,index=list(SCALES.values()).index(current['scale']))
            row_label=st.selectbox('표 행 높이',row_labels,index=list(ROW_HEIGHTS.values()).index(current['row_height']))
            rounded=st.toggle('둥근 모서리 사용',value=current['rounded'])
            left,right=st.columns(2)
            preview=left.form_submit_button('미리보기',use_container_width=True)
            stored=right.form_submit_button('저장',type='primary',use_container_width=True)
        settings={'theme':theme,'scale':SCALES[scale_label],'row_height':ROW_HEIGHTS[row_label],'rounded':rounded}
        if preview:
            st.session_state['_theme_preview']={'username':user['username'],'settings':validate(settings)};st.rerun()
        if stored:
            save(st.session_state.get('_auth_token'),settings)
            st.session_state.pop('_theme_preview',None);st.session_state['_theme_saved']=True;st.rerun()
        if st.session_state.pop('_theme_saved',False):st.success('화면 테마를 저장했습니다.')
