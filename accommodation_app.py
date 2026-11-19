"""Site accommodation management integrated into the authenticated workspace."""
from pathlib import Path
from datetime import date, timedelta
import base64
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
import accommodation_store as db
import accommodation_report as report
from table_layout import aligned_config

SYSTEM='현장숙소(전·월세)관리'
PAGES=['숙소 총현황','계약 등록·관리','임차료·관리비','보증금 반환','계약 만기']
address_search=components.declare_component('ac_address_search',path=str(Path(__file__).parent/'assets'/'address_search'))
CSS='''<style>
#root .ac-section{display:flex;align-items:center;gap:12px;font-size:21px;font-weight:800;color:#17382d;margin:14px 0 10px;border-bottom:2px solid #198653;padding-bottom:7px}
#root .ac-section b{background:#087b51;color:white;border-radius:18px;padding:2px 12px}
#root .st-key-ac_subnav{background:#e6f6ed;border-radius:10px;padding:4px 12px;margin:0 0 8px}
#root .st-key-ac_subnav button{border:0;background:transparent}
#root .st-key-ac_subnav button[kind="primary"]{background:#b4e7cf;color:#064d35}
#root .st-key-ac_contract_form [data-testid="stVerticalBlock"]{gap:.4rem}
#root .st-key-ac_contract_form input[type="number"]{text-align:right}
#root [data-testid="stMainBlockContainer"]:has(.st-key-ac_subnav){padding-top:3.5rem}
#root .st-key-ac_contract_form [data-testid="stFileUploader"]{padding:8px;border:1px dashed #62b68e;background:#f4fbf7}
</style>'''

def go(page,id=None):
    st.session_state['ac_page']=page
    if id is not None:st.session_state['ac_selected']=id

def table(data):
    if not data:st.info('등록된 내역이 없습니다.');return
    f=pd.DataFrame(data);st.dataframe(f,hide_index=True,use_container_width=True,column_config=aligned_config(f),height=min(680,38+len(f)*36))
def run(fn):
    try:
        fn();st.session_state['ac_notice']='저장했습니다.';st.rerun()
    except ValueError as e:st.error(str(e))
def section(n,title):st.markdown(f'<div class="ac-section"><b>{n:02}</b>{title}</div>',unsafe_allow_html=True)
def address(prefix,title,v,keys):
    postcode,road,detail=keys
    cols=st.columns([.8,.65,2.3,1.5],vertical_alignment='bottom')
    with cols[0]:
        st.markdown('**'+title+'**')
        a=address_search(key=prefix+'search',default=None)
    if isinstance(a,dict) and a.get('nonce')!=st.session_state.get(prefix+'last'):
        st.session_state[prefix+'zip']=str(a.get('zonecode',''))[:10]
        st.session_state[prefix+'road']=str(a.get('address',''))[:300]
        st.session_state[prefix+'last']=a.get('nonce')
    return {postcode:cols[1].text_input(title+' 우편번호',v.get(postcode,''),key=prefix+'zip'),road:cols[2].text_input(title,v.get(road,''),key=prefix+'road'),detail:cols[3].text_input(title+' 상세주소',v.get(detail,''),key=prefix+'detail')}

def attachment_preview(c,id,prefix,editable=False):
    removed=[]
    for f in db.files(c,id):
        cols=st.columns([3,1,1]);cols[0].write(f['name'])
        meta,data=db.file_bytes(c,id,f['id'])
        cols[1].download_button('다운로드',data,file_name=f['name'],mime=f['mime'],key=prefix+'dl'+str(f['id']))
        if editable and cols[2].checkbox('첨부 제외',key=prefix+'rm'+str(f['id'])):removed.append(f['id'])
        with st.expander('미리보기 · '+f['name']):
            if f['mime']=='application/pdf':
                components.html('<iframe title="계약서" style="width:100%;height:560px;border:0" src="data:application/pdf;base64,'+base64.b64encode(data).decode()+'"></iframe>',height=570)
                st.caption('PDF 미리보기를 지원하지 않는 브라우저에서는 다운로드하여 확인하세요.')
            else:st.image(data,use_container_width=True)
    return removed

def compose(c):
    st.subheader('숙소 계약 등록·관리')
    items=db.contracts(c);ids=[None]+[v['id'] for v in items];lookup={v['id']:v for v in items}
    if 'ac_pending' in st.session_state:st.session_state['ac_load']=st.session_state.pop('ac_pending')
    selected=st.selectbox('등록 계약 불러오기',ids,index=ids.index(st.session_state.get('ac_selected')) if st.session_state.get('ac_selected') in ids else 0,format_func=lambda id:'새 계약 등록' if id is None else f"{lookup[id]['site']} / {lookup[id]['name']} · {lookup[id]['start']}",key='ac_load')
    v=lookup.get(selected,{});key=f'ac_edit_{selected}_{v.get("version",0)}_';draft={}
    with st.container(key='ac_contract_form'):
        section(1,'현장·숙소 정보');cols=st.columns(3)
        draft['site']=cols[0].text_input('현장명 *',v.get('site',''),key=key+'site')
        draft['name']=cols[1].text_input('숙소명 *',v.get('name',''),key=key+'name')
        draft['kind']=cols[2].selectbox('계약구분',['월세','전세'],index=0 if v.get('kind','월세')=='월세' else 1,key=key+'kind')
        draft.update(address(key+'site_','현장 주소',v,['site_zip','site_address','site_detail']))
        draft.update(address(key+'home_','숙소 주소',v,['zip','address','detail']))
        st.caption('주소검색 후 상세주소를 입력하세요. 검색 연결이 어려우면 주소를 직접 입력할 수 있습니다.')
        section(2,'계약 당사자·연락처');cols=st.columns(4)
        for col,(field,label) in zip(cols,[('tenant','임차인(계약 명의) *'),('tenant_phone','임차인 연락처 *'),('manager','담당자'),('manager_phone','담당자 연락처')]):draft[field]=col.text_input(label,v.get(field,''),key=key+field)
        cols=st.columns(2)
        for col,(field,label) in zip(cols,[('landlord','임대인 *'),('landlord_phone','임대인 연락처 *')]):draft[field]=col.text_input(label,v.get(field,''),key=key+field)
        section(3,'계약기간·금액');cols=st.columns(3);today=db.today()
        draft['start']=str(cols[0].date_input('계약시작일',date.fromisoformat(v.get('start',str(today))),key=key+'start'))
        draft['end']=str(cols[1].date_input('계약종료일',date.fromisoformat(v.get('end',str(today+timedelta(days=365)))),key=key+'end'))
        draft['alert_days']=cols[2].number_input('만기 알림 (일 전)',1,365,int(v.get('alert_days',30)),key=key+'alert')
        cols=st.columns(4)
        for col,(field,label) in zip(cols[:3],[('deposit','보증금 (원)'),('rent','월 임차료 (원)'),('maintenance','월 관리비 (원)')]):
            draft[field]=col.number_input(label,min_value=0,value=int(v.get(field,0)),step=10000,key=key+field)
        draft['pay_day']=cols[3].number_input('납부일 (매월 일)',1,31,int(v.get('pay_day',5)),key=key+'payday')
        st.caption(f"보증금 {draft['deposit']:,}원 · 월 임차료 {draft['rent']:,}원 · 월 관리비 {draft['maintenance']:,}원")
        st.caption('월별 약정액 기준으로 관리합니다. 입·퇴실월 일할 계산이 필요한 경우 지급 전 계약금액을 확인하세요.')
        st.markdown('**전세권 설정 정보**')
        draft['registration_status']=st.radio('전세권 설정 여부',['미설정','설정 완료'],index=1 if v.get('registration_status')=='설정 완료' else 0,horizontal=True,key=key+'registration_status')
        if draft['registration_status']=='설정 완료':
            cols=st.columns(3)
            draft['registration_date']=str(cols[0].date_input('전세권 설정일 *',date.fromisoformat(v['registration_date']) if v.get('registration_date') else None,key=key+'registration_date'))
            draft['registration_amount']=cols[1].number_input('전세권 설정금액 (원) *',min_value=0,value=int(v.get('registration_amount',0)),step=10000,key=key+'registration_amount')
            draft['registration_number']=cols[2].text_input('등기 접수번호 *',v.get('registration_number',''),key=key+'registration_number')
            st.caption(f"설정금액 {draft['registration_amount']:,}원 · 관련 등기서류는 아래 첨부 영역에 등록하세요.")
        draft['note']=st.text_area('특약·비고',v.get('note',''),key=key+'note',height=80)
        terminated=st.checkbox('계약 조기 종료',bool(v.get('terminated')),key=key+'terminated')
        draft['terminated']=str(st.date_input('실제 종료일',date.fromisoformat(v.get('terminated') or v.get('end',str(today))),key=key+'actualend')) if terminated else ''
        section(4,'계약서·등기서류·첨부자료')
        uploaded=st.file_uploader('계약서·등기서류 업로드 · PDF / JPG / PNG',type=['pdf','jpg','jpeg','png'],accept_multiple_files=True,key=key+'files')
        st.caption('여러 파일을 첨부할 수 있습니다. 파일당 최대 20MB. 기존 첨부자료는 수정 시 유지됩니다.')
        remove=attachment_preview(c,selected,key,True) if selected else []
        cols=st.columns([3,1,1,1])
        if cols[1].button('취소',key=key+'reset'):
            for k in list(st.session_state):
                if k.startswith(key):del st.session_state[k]
            go(PAGES[0]);st.rerun()
        preview=cols[2].button('미리보기',key=key+'preview')
        if preview:
            try:
                cleaned=db.clean(draft)
                table([{'현장':cleaned['site'],'숙소명':cleaned['name'],'현장 주소':cleaned['site_address']+' '+cleaned['site_detail'],'숙소 주소':cleaned['address']+' '+cleaned['detail'],'임차인':cleaned['tenant'],'임차인 연락처':cleaned['tenant_phone'],'임대인':cleaned['landlord'],'보증금':cleaned['deposit'],'월세':cleaned['rent'],'관리비':cleaned['maintenance'],'시작일':cleaned['start'],'종료일':cleaned['end'],'전세권 설정 여부':cleaned['registration_status'],'전세권 설정일':cleaned['registration_date'],'전세권 설정금액':cleaned['registration_amount'],'등기 접수번호':cleaned['registration_number']}])
            except ValueError as e:st.error(str(e))
        if cols[3].button('계약 수정 저장' if selected else '계약 저장',type='primary',key=key+'save'):
            def save():
                id=db.save(c,draft,selected,v.get('version'),[dict(name=f.name,content=f.getvalue()) for f in uploaded or []],remove)
                st.session_state['ac_selected']=id;st.session_state['ac_pending']=id
            run(save)
        if selected:
            with st.expander('계약 변경 이력'):
                history=db.rows(c,'SELECT version,payload,created_at FROM ac_versions WHERE contract_id=? ORDER BY version DESC',(selected,))
                table([{'차수':h['version'],'저장일시':h['created_at']} for h in history])
                import json
                for h in history:
                    with st.expander(str(h['version'])+'차 계약 내용'):st.json(json.loads(h['payload']))

def filters(c):
    items=db.contracts(c);cols=st.columns(4)
    day=cols[0].date_input('기준일',db.today(),key='ac_asof')
    site=cols[1].selectbox('현장',['전체']+sorted({v['site'] for v in items}),key='ac_filter_site')
    kind=cols[2].selectbox('계약구분',['전체','전세','월세'],key='ac_filter_kind')
    status=cols[3].selectbox('계약상태',['전체','사용 중','예정','종료'],key='ac_filter_status')
    return day,[v for v in items if (site=='전체' or v['site']==site) and (kind=='전체' or v['kind']==kind) and (status=='전체' or db.state(v,day)==status)] if status!='예정' else [v for v in items if v['start']>str(day) and (site=='전체' or v['site']==site) and (kind=='전체' or v['kind']==kind)]

def render_alerts(c=None,home=False):
    c=c or db.connect();items=db.alerts(c)
    if not items:return
    st.markdown('**숙소 계약 알림**')
    for v,text in items:st.warning(f"{v['site']} / {v['name']} · {text}")
    if home and st.button('현장숙소 현황 확인',key='ac_home_open'):st.session_state['main_system']=SYSTEM;go(PAGES[0]);st.rerun()

def overview(c):
    st.subheader('현장숙소 총현황');day,items=filters(c);active=[v for v in items if db.state(v,day)=='사용 중'];cols=st.columns(4)
    cols[0].metric('사용 중 숙소',f'{len(active)}개')
    cols[1].metric('미반환 보증금',f"{sum(v['deposit']-db.returned(c,v['id'],day) for v in items):,}원")
    cols[2].metric('월 임차료',f"{sum(v['rent'] for v in active):,}원")
    cols[3].metric('30일 내 만기',f"{sum(0<=(date.fromisoformat(v.get('terminated') or v['end'])-day).days<=30 for v in active)}건")
    notices=[]
    for v,text in db.alerts(c,day):
        if v['id'] in {i['id'] for i in items}:notices.append(f"{v['site']} / {v['name']} · {text}")
    for v in active:
        for row in db.monthly(c,v,day):
            days=(date.fromisoformat(row['납부예정일'])-day).days
            if row['미지급액'] and -31<=days<=7:notices.append(f"{v['site']} / {v['name']} · {row['귀속월']} 임차료·관리비 · 납부일 {row['납부예정일']} · 미지급액 {row['미지급액']:,}원")
    if notices:
        with st.container(border=True):
            st.markdown('**계약·납부 알림**')
            for text in notices:st.markdown('• '+text)
    st.markdown('**현장별 숙소 계약 현황**');data=report.overview(c,items,day);table(data)
    cols=st.columns([1,1,1,3])
    html=report.html(data,day)
    cols[0].download_button('현황표 인쇄 HTML',html,file_name='현장숙소_총현황.html',mime='text/html')
    cols[1].download_button('엑셀 다운로드',report.excel(data),file_name='현장숙소_총현황.xlsx')
    if cols[2].button('＋ 새 계약 등록',type='primary'):
        st.session_state.pop('ac_load',None);st.session_state.pop('ac_selected',None);go(PAGES[1]);st.rerun()
    with st.expander('인쇄 / PDF 미리보기'):components.html(html,height=650,scrolling=True)

def pick(c,key):
    items=db.contracts(c)
    if not items:st.info('먼저 계약을 등록하세요.');return None
    lookup={v['id']:v for v in items}
    id=st.selectbox('현장 / 숙소 계약',list(lookup),format_func=lambda id:f"{lookup[id]['site']} / {lookup[id]['name']} · {lookup[id]['tenant']} ({lookup[id]['start']}~{lookup[id]['end']})",key=key)
    return lookup[id]
def ledger(c,refund=False):
    st.subheader('보증금 반환' if refund else '임차료·관리비');v=pick(c,'ac_return_pick' if refund else 'ac_payment_pick')
    if not v:return
    id=v['id'];prefix=('ac_ref_' if refund else 'ac_pay_')+str(id)
    if refund:
        cols=st.columns(3);returned=db.returned(c,id);cols[0].metric('계약 보증금',f"{v['deposit']:,}원");cols[1].metric('반환받은 금액',f'{returned:,}원');cols[2].metric('미반환 잔액',f"{v['deposit']-returned:,}원")
        table([dict(반환일=r['paid_date'],반환금액=r['amount'],비고=r['note']) for r in db.returns(c,id)])
    else:table(db.monthly(c,v));st.caption('월별 약정액 기준입니다. 지급일이 기준일 이후인 내역은 지급 합계에서 제외됩니다.')
    with st.form(prefix+'form'):
        cols=st.columns(4)
        if not refund:period=cols[0].selectbox('귀속월',list(db.periods(v)))
        paid=cols[1].date_input('반환일' if refund else '지급일',db.today())
        amount=cols[2].number_input('반환금액 (원)' if refund else '지급 임차료 (원)',min_value=0,value=0 if refund else v['rent'],step=10000)
        maintenance=0 if refund else cols[3].number_input('지급 관리비 (원)',min_value=0,value=v['maintenance'],step=10000)
        note=st.text_input('비고');submitted=st.form_submit_button('반환 내역 저장' if refund else '지급 내역 저장',type='primary')
        if submitted:run(lambda:db.add_return(c,id,paid,amount,note) if refund else db.add_payment(c,id,period,paid,amount,maintenance,note))
    entries=db.returns(c,id) if refund else db.payments(c,id)
    with st.expander('저장 내역 확인·잘못된 입력 삭제'):
        table([dict(내역번호=r['id'],일자=r['paid_date'],금액=r['amount'] if refund else r['rent']+r['maintenance'],비고=r['note']) for r in entries])
        if entries:
            rid=st.selectbox('삭제할 내역',[r['id'] for r in entries],key=prefix+'delid');check=st.checkbox('선택한 내역 삭제 확인',key=prefix+'check')
            if st.button('선택 내역 삭제',disabled=not check,key=prefix+'del'):run(lambda:db.remove_entry(c,'ac_returns' if refund else 'ac_payments',rid,id))

def expiry(c):
    st.subheader('계약 만기');render_alerts(c);v=pick(c,'ac_expiry_pick')
    if v:
        st.write(f"계약기간: {v['start']} ~ {v.get('terminated') or v['end']} / {db.state(v)}")
        st.caption('연장 시 기존 계약을 불러와 계약기간·금액·스캔본을 수정하세요. 이전 계약 내용은 변경 이력에 보존됩니다.')
        if st.button('계약 불러오기 · 연장/종료 관리',type='primary'):
            st.session_state['ac_load']=v['id'];go(PAGES[1],v['id']);st.rerun()

def render(user):
    c=db.connect();st.html(CSS)
    page=st.session_state.get('ac_page',PAGES[0]);page=page if page in PAGES else PAGES[0]
    with st.sidebar:
        st.markdown('**현장숙소 관리**')
        for name in PAGES:st.button(name,key='ac_side_'+name,use_container_width=True,type='primary' if page==name else 'secondary',on_click=go,args=(name,))
    with st.container(key='ac_subnav'):
        cols=st.columns(5)
        for col,name in zip(cols,PAGES):col.button(name,key='ac_nav_'+name,use_container_width=True,type='primary' if page==name else 'secondary',on_click=go,args=(name,))
    if st.session_state.get('ac_notice'):st.success(st.session_state.pop('ac_notice'))
    {PAGES[0]:overview,PAGES[1]:compose,PAGES[2]:lambda c:ledger(c),PAGES[3]:lambda c:ledger(c,True),PAGES[4]:expiry}[page](c)
