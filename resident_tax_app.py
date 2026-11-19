"""Resident business tax UI and separate year-end corporate allocation worksheets."""
from datetime import date,timedelta
from io import BytesIO
import json,hashlib,base64
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
import resident_tax_calc as calc
import resident_tax_store as db
import resident_tax_import as imp
import resident_tax_report as report
from accommodation_app import address,section
from table_layout import aligned_config,format_excel

SYSTEM='주민세(사업소분) 관리'
PAGES=['신고대상 총현황','현장·가설건축물','건물사용명세 업로드','면적·세액 검토','신고·납부 관리','법인지방소득세 연계']
CSS='''<style>#root .st-key-rt_subnav{background:#e6f6ed;border-radius:12px;padding:4px 8px;margin-bottom:8px}#root .st-key-rt_subnav button{border:0;background:transparent}#root .st-key-rt_subnav button[kind="primary"]{background:#b7e4cc;color:#064c32}#root .rt-step{background:#edf8f2;color:#15553c;padding:12px;border-radius:8px;font-weight:650}#root .st-key-rt_form input[type="number"]{text-align:right}</style>'''
def table(data):
    if not data:st.info('등록된 내역이 없습니다.');return
    frame=pd.DataFrame(data);config=aligned_config(frame)
    for name in ['총면적','제외면적','과세면적','사용면적','안분면적']:
        if name in frame:config[name]=st.column_config.NumberColumn(name,format='localized',alignment='right')
    st.dataframe(frame,hide_index=True,use_container_width=True,column_config=config,height=min(680,38+len(frame)*36))

def go(page):st.session_state['rt_page']=page

def act(fn):
    try:fn();st.session_state['rt_notice']='저장했습니다.';st.rerun()
    except (ValueError,TypeError) as e:st.error(str(e))
def uploaded(files):return [dict(name=f.name,content=f.getvalue()) for f in files or []]
def pick(c,year,key):
    ss=db.sites(c,year)
    if not ss:st.info('사업장을 먼저 등록하거나 기존 집계표를 가져오세요.');return None
    lookup={s['id']:s for s in ss};id=st.selectbox('법인 / 사업장',list(lookup),format_func=lambda id:f"{lookup[id]['company']} / {lookup[id]['name']} / {lookup[id]['region']}",key=key)
    return lookup[id]
def filters(data,prefix):
    cols=st.columns(3);company=cols[0].selectbox('법인',['전체']+sorted({r['법인'] for r in data}),key=prefix+'company');region=cols[1].selectbox('관할 지자체',['전체']+sorted({r['관할지자체'] for r in data if company=='전체' or r['법인']==company}),key=prefix+'region');state=cols[2].selectbox('검토상태',['전체','확정','확인 필요','확정 가능'],key=prefix+'state')
    return [r for r in data if (company=='전체' or r['법인']==company) and (region=='전체' or r['관할지자체']==region) and (state=='전체' or r.get('검토상태')==state)]
def overview(c,year):
    st.subheader(f'{year}년 주민세(사업소분) 신고 현황');data=filters(report.overview(c,year),'rt_filter_');groups=db.business_groups(c,year);cols=st.columns(4)
    cols[0].metric('등록 사업장',f"{sum(r['사업장수'] for r in data)}개")
    cols[1].metric('검토 필요 신고단위',f"{sum(r['검토상태']=='확인 필요' for r in data)}건")
    cols[2].metric('예상세액 (미확정 포함)',f"{sum(r['합계'] for r in data):,}원")
    cols[3].metric('기본 신고·납부기한',f'{year}.08.31')
    issues=[g['company']+' / '+g['unit']+' · '+', '.join(g['issues']) for g in groups if g['issues']]
    if issues:
        with st.expander(f'확인 필요 {len(issues)}건',expanded=True):
            for text in issues[:10]:st.warning(text)
            if len(issues)>10:st.caption('나머지 항목은 면적·세액 검토 메뉴에서 확인하세요.')
    tabs=st.tabs(['신고단위별 명세','법인별 총괄','법인·지자체별 총괄'])
    with tabs[0]:table(data)
    with tabs[1]:table(report.grouped(data,['법인']))
    with tabs[2]:table(report.grouped(data,['법인','관할지자체']))
    st.caption('330㎡ 이하의 연면적세액은 0원이며 기본세액은 별도입니다. 미확인 자료의 예상세액은 확정 전 금액입니다.')
    cols=st.columns([1,1,1,2]);html=report.html(data,'주민세(사업소분) 집계표',year)
    cols[0].download_button('집계표 인쇄 HTML',html,file_name=f'주민세집계_{year}.html',mime='text/html')
    cols[1].download_button('엑셀 다운로드',report.excel(c,year),file_name=f'주민세집계_{year}.xlsx')
    cols[2].button('건물사용명세 업로드',type='primary',on_click=go,args=(PAGES[2],))
    with st.expander('인쇄 / PDF 미리보기'):components.html(html,height=640,scrolling=True)
    st.markdown('<div class="rt-step">① 현장 명세 업로드　→　② 면적·존치 확인　→　③ 세액 검토 확정　→　④ 신고·납부 기록</div>',unsafe_allow_html=True)

def source_addresses(c):
    out=[]
    for s in db.sites(c):out.append(dict(label=f"주민세 {s['year']} / {s['company']} / {s['name']}",company=s['company'],name=s['name'],address=s['address'],detail=s.get('detail',''),zip=s.get('zip',''),phone=s.get('phone',''),kind=s['kind']))
    if (db.shared.DATA/'accommodations.db').exists():
        import accommodation_store as ac
        for s in ac.contracts(ac.connect()):out.append(dict(label='현장숙소 / '+s['site'],company=s['tenant'],name=s['site'],address=s['site_address'],detail=s.get('site_detail',''),zip=s.get('site_zip',''),phone=s.get('manager_phone',''),kind='현장사무실'))
    return out

def sites_page(c,year):
    st.subheader('사업장·주소·신고단위 관리');ss=db.sites(c,year);lookup={s['id']:s for s in ss};ids=[None]+list(lookup)
    if 'rt_pending_site' in st.session_state:st.session_state['rt_site_load']=st.session_state.pop('rt_pending_site')
    if ss:
        with st.expander(f'등록 사업장 목록 ({len(ss)}건)'):
            table([dict(사업장번호=s['id'],법인=s['company'],사업장=s['name'],주소=s['address'],관할지자체=s['region'],신고단위=s['unit']) for s in ss])
    selected=st.selectbox('사업장 불러오기 · 수정할 사업장 선택',ids,format_func=lambda id:'새 사업장 등록' if id is None else lookup[id]['company']+' / '+lookup[id]['name'],key='rt_site_load')
    v=lookup.get(selected,{})
    locks=db.site_locks(c,selected) if selected else []
    if selected:
        st.info('선택한 사업장을 수정 중입니다. 아래 항목을 변경하고 사업장 수정 저장을 누르세요. 법인명도 정정할 수 있습니다.')
        if locks:
            st.warning('확정된 신고자료에 포함되어 수정·삭제가 제한됩니다: '+', '.join(f['company']+' / '+f['region']+' / '+f['unit'] for f in locks))
            st.caption('신고·납부 기록이 없는 확정 자료만 해제할 수 있습니다. 이미 신고한 자료는 현재 신고 내용을 보존합니다.')
            st.button('신고·납부 관리에서 확정 상태 확인',key='rt_site_open_filing',on_click=go,args=(PAGES[4],))
    if not selected:
        sources=source_addresses(c);index=st.selectbox('기존 주소 불러오기',[None]+list(range(len(sources))),format_func=lambda n:'직접 입력' if n is None else sources[n]['label'],key='rt_address_source')
        if index is not None:v=sources[index]
    else:index=None
    key=f'rt_site_{selected}_{v.get("version",0)}_{index}_';x=dict(year=year)
    with st.container(key='rt_form'):
        section(1,'법인·사업장 정보');cols=st.columns(3)
        x['company']=cols[0].text_input('법인명 *',v.get('company',''),key=key+'company',disabled=bool(locks))
        x['name']=cols[1].text_input('사업장명 *',v.get('name',''),key=key+'name')
        x['kind']=cols[2].selectbox('사업장 구분',calc.KINDS,index=calc.KINDS.index(v.get('kind',calc.KINDS[3])),key=key+'kind')
        x.update(address(key+'addr_','사업장 주소',v,['zip','address','detail']))
        suggest=calc.jurisdiction(x['address']);st.caption('관할 제안: '+(suggest or '주소 입력 후 확인')+' · 행정구와 자치구를 확인하고 실제 과세관청으로 수정하세요.')
        cols=st.columns(3);x['region']=cols[0].text_input('관할 지자체 *',v.get('region') or suggest,key=key+'region_'+x['address']);x['phone']=cols[1].text_input('사업장 연락처',v.get('phone',''),key=key+'phone');x['unit']=cols[2].text_input('신고단위명',v.get('unit',v.get('name','')),key=key+'unit')
        st.caption('같은 법인·지자체에서 같은 신고단위명을 지정한 사업장만 면적을 합산합니다. 기본세액은 신고 단위당 한 번 계산합니다.')
        section(2,'적용 연도 세율·감면');cols=st.columns(4)
        x['capital']=cols[0].number_input('자본금·출자금 (원)',min_value=0,value=int(v.get('capital',0)),step=10000000,key=key+'capital')
        auto=cols[1].checkbox('자본금 기준 기본세액',value=not bool(v.get('base')),key=key+'auto')
        x['base']=calc.basic(x['capital']) if auto else cols[1].number_input('기본세액 (원)',min_value=0,value=int(v.get('base',calc.basic(x['capital']))),step=10000,key=key+'base')
        if auto:cols[1].caption(f"기본세액 {x['base']:,}원")
        x['rate']=cols[2].number_input('연면적 세율 (원/㎡)',min_value=0,value=int(v.get('rate',250)),step=50,key=key+'rate')
        x['education']=cols[3].number_input('지방교육세율 (%)',min_value=0.,max_value=100.,value=float(v.get('education',25 if suggest.startswith('서울') else 10)),step=1.,key=key+'education')
        cols=st.columns(3)
        for col,(k,label) in zip(cols,[('reduce_base','기본세액 감면 (원)'),('reduce_area','연면적세액 감면 (원)'),('reduce_education','지방교육세 감면 (원)')]):x[k]=col.number_input(label,min_value=0,value=int(v.get(k,0)),key=key+k)
        cols=st.columns(2);x['floor_area']=cols[0].checkbox('과세면적 합산 후 1㎡ 미만 버림 (기존 집계표 기준)',value=v.get('floor_area',True),key=key+'floor');x['deadline']=str(cols[1].date_input('신고·납부기한',date.fromisoformat(v.get('deadline',f'{year}-08-31')),key=key+'deadline'))
        x['rule_note']=st.text_input('관할·세율·감면 확인 근거',v.get('rule_note',''),key=key+'rule');x['confirmed']=st.checkbox('해당 연도 관할·세율·감면·기한 확인',value=v.get('confirmed',False),key=key+'confirmed')
        if v.get('legacy'):
            x['legacy']=True;x['legacy_total']=v.get('legacy_total',0);x['legacy_checked']=st.checkbox('기존 집계표 금액·사업장 주소 대조 완료',value=v.get('legacy_checked',False),key=key+'legacy')
        if st.button('사업장 수정 저장' if selected else '사업장 등록',type='primary',key=key+'save',disabled=bool(locks)):
            def save():st.session_state['rt_pending_site']=db.save_site(c,x,selected,lookup.get(selected,{}).get('version'))
            act(save)
    if selected:
        with st.expander('선택 사업장 삭제'):
            st.write(f"삭제 대상: {v['company']} / {v['name']} · 건물 {len(db.buildings(c,selected))}개")
            st.caption('삭제하면 현황과 계산에서 제외합니다. 건물 명세·원본 파일·변경 이력은 보관하며 삭제 목록에서 복구할 수 있습니다.')
            reason=st.text_input('사업장 삭제 사유',key=key+'delete_reason')
            confirmed=st.checkbox('선택한 사업장 삭제 확인',key=key+'delete_confirm')
            if st.button('사업장 삭제',disabled=bool(locks) or not confirmed,key=key+'delete'):
                def remove():
                    db.delete_site(c,selected,v['version'],reason);st.session_state['rt_pending_site']=None
                act(remove)
    deleted=[s for s in db.sites(c,year,include_deleted=True) if s.get('deleted')]
    with st.expander(f'삭제 사업장 목록·복구 ({len(deleted)}건)'):
        if deleted:
            table([dict(사업장번호=s['id'],법인=s['company'],사업장=s['name'],삭제일=s.get('deleted_at',''),삭제사유=s.get('delete_reason','')) for s in deleted])
            removed={s['id']:s for s in deleted}
            restore_id=st.selectbox('복구할 사업장',list(removed),format_func=lambda id:removed[id]['company']+' / '+removed[id]['name'],key='rt_restore_site')
            if st.button('사업장 복구',key='rt_restore_button'):
                def restore():st.session_state['rt_pending_site']=db.restore_site(c,restore_id,removed[restore_id]['version'])
                act(restore)
        else:st.caption('삭제된 사업장이 없습니다.')
    with st.expander('다음 연도 사업장 이월'):
        cols=st.columns(2);source=cols[0].number_input('원본 연도',2000,2100,year,key='rt_carry_source');target=cols[1].number_input('대상 연도',2000,2100,min(year+1,2100),key='rt_carry_target')
        st.caption('주소·건물 명세는 복사하고 존치·세율·면적 검토는 초기화합니다. 신고·납부 기록은 복사하지 않습니다.')
        if st.button('사업장 이월 실행'):act(lambda:db.carry(c,source,target))
    st.divider();st.subheader('건물별 명세 등록·수정');s=lookup[selected] if selected else pick(c,year,'rt_manual_site')
    if s:building_editor(c,s,'rt_manual_')

ROW_LABELS={'floor':'층수','room':'호수','entered':'최초입주일','area':'사용면적','purpose':'사용용도','taxable':'과세면적','reason':'제외 근거·비고'}
def building_editor(c,s,prefix,parsed=None,source=None):
    bs=db.buildings(c,s['id']);lookup={b['id']:b for b in bs}
    bid=st.selectbox('기존 건물 선택',[None]+list(lookup),format_func=lambda id:'새 건물 등록' if id is None else lookup[id]['name'],key=prefix+'bid'+str(s['id']))
    old=lookup.get(bid,{})
    if bid is None and any(b.get('legacy') for b in bs):st.warning('이관한 기존 집계 명세가 있습니다. 기존 건물 선택에서 해당 명세를 선택해 대체해야 면적 중복을 막을 수 있습니다.')
    v=dict(old)
    if parsed:v.update(parsed)
    key=prefix+str(s['id'])+'_'+str(bid)+'_'+(hashlib.sha256(source['content']).hexdigest()[:10] if source else str(old.get('digest',''))[:10])
    cols=st.columns(3);name=cols[0].text_input('건물명·관리번호 *',old.get('name',''),key=key+'name');permit=cols[1].text_input('축조신고번호',v.get('permit',''),key=key+'permit');reported=cols[2].number_input('축조신고·기준 전체면적 (㎡)',min_value=0.,value=float(v.get('reported',0)),format='%.4f',key=key+'reported')
    st.caption('존치 허가기간 종료만으로 철거 처리하지 않습니다. 실제 철거일과 7월 1일 존치 여부를 확인하세요.')
    cols=st.columns(4)
    start=cols[0].text_input('축조·사용시작일 (YYYY-MM-DD)',v.get('start',''),key=key+'start');end=cols[1].text_input('존치 허가만료일 (YYYY-MM-DD)',v.get('permit_end',''),key=key+'end');demolished=cols[2].text_input('실제 철거일 (YYYY-MM-DD)',v.get('demolished',''),key=key+'demolished');presence=cols[3].selectbox(f'{s["year"]}년 7월 1일 존치 여부',['미확인','존치 확인','미존치'],index=['미확인','존치 확인','미존치'].index(v.get('presence','미확인')),key=key+'presence')
    initial=v.get('rows') or [dict(floor='',room='',entered='',area=0.,purpose='',taxable=0.,reason='')]
    frame=pd.DataFrame([{k:r.get(k,'') for k in ROW_LABELS} for r in initial]).rename(columns=ROW_LABELS)
    edited=st.data_editor(frame,num_rows='dynamic',hide_index=True,use_container_width=True,column_config=aligned_config(frame),key=key+'rows')
    records=edited.rename(columns={v:k for k,v in ROW_LABELS.items()}).fillna('').to_dict('records')
    try:
        a=calc.area(records);cols=st.columns(4);cols[0].metric('명세 합계',f"{a['total']:,.2f}㎡");cols[1].metric('제외면적',f"{a['excluded']:,.2f}㎡");cols[2].metric('과세면적',f"{a['taxable']:,.2f}㎡");diff=float(calc.dec(a['total'])-calc.dec(reported));cols[3].metric('기준면적과 차이',f'{diff:,.2f}㎡')
        if abs(diff)>.005:st.warning('기준면적과 명세 합계가 다릅니다. 확인 사유를 기록하세요.')
    except ValueError as e:st.error(str(e))
    reason=st.text_input('면적 차이 확인 사유',v.get('difference_reason',''),key=key+'diff');reviewed=st.checkbox('면적·제외 근거 확인 완료',value=False if parsed else v.get('reviewed',False),key=key+'reviewed')
    if st.button('건물 명세 저장',type='primary',key=key+'save'):
        value=dict(rows=records,reported=reported,permit=permit,start=start,permit_end=end,demolished=demolished,presence=presence,reviewed=reviewed,difference_reason=reason)
        act(lambda:db.save_building(c,s['id'],name,value,source,bid))
    if bid:
        check=st.checkbox('선택한 건물 명세 삭제 확인',key=key+'check')
        if st.button('건물 명세 삭제',disabled=not check,key=key+'delete'):act(lambda:db.remove_building(c,s['id'],bid))
    with st.expander('저장된 원본 명세서 다운로드'):
        for src in db.rows(c,'SELECT id,name,content,digest FROM rt_sources WHERE site_id=? ORDER BY id DESC',(s['id'],)):
            st.download_button(src['name'],base64.b64decode(src['content']),file_name=src['name'],key=key+'src'+str(src['id']))

def upload_page(c,year):
    st.subheader('건물사용명세 엑셀 업로드');tabs=st.tabs(['현장 배포용 명세서','기존 주민세 집계표 이관'])
    with tabs[0]:
        st.download_button('빈 배포 양식 다운로드',imp.blank_statement(year),file_name='건물사용명세서_빈양식.xlsx')
        f=st.file_uploader('현장에서 회신한 건물사용명세서',type=['xlsx'],key='rt_usage_file')
        if f:
            try:
                p=imp.statement(f.getvalue());st.write(f"원본: {p['company']} / {p['site']} · 총면적 {p['total']:,.2f}㎡ / 과세면적 {p['taxable']:,.2f}㎡")
                if p['year'] and p['year']!=year:st.error('원본 기준연도와 선택 연도가 다릅니다. 연도를 변경하세요.')
                else:
                    s=pick(c,year,'rt_upload_site')
                    if s:
                        norm=lambda v:str(v).replace('㈜','').replace('(주)','').replace(' ','')
                        match=norm(p['company'])==norm(s['company']) and norm(p['site'])==norm(s['name'])
                        accepted=match or st.checkbox('원본 법인·현장 표기가 다름을 확인하고 선택한 사업장으로 매핑',key='rt_map_'+hashlib.sha256(f.getvalue()).hexdigest()[:8])
                        if accepted:building_editor(c,s,'rt_upload_',p,dict(name=f.name,content=f.getvalue()))
            except (ValueError,TypeError) as e:st.error(str(e))
    with tabs[1]:
        st.caption('기존 집계표는 미확정 자료로 이관합니다. 원본을 보존하고 주소·관할·존치·면적·세율을 다시 검토합니다. 같은 사업장이 있으면 덮어쓰지 않습니다.')
        f=st.file_uploader('주민세(사업소분) 집계표',type=['xlsx'],key='rt_aggregate_file')
        if f:
            try:
                p=imp.aggregate(f.getvalue());st.write(f"{p['year']}년 · {len(p['sites'])}개 사업장")
                if p.get('skipped'):st.caption(f"금액·면적·현장명이 비어 있는 예비 블록 {p['skipped']}건은 이관에서 제외합니다.")
                table([dict(법인=x['company'],현장=x['site'],주소=x['address'],총면적=x['reported'],과세면적=x['taxable'],기본세액=x['base'],교육세율=x['education'],원본합계=x['legacy_total']) for x in p['sites']])
                yes=st.checkbox('기존 자료와 중복 여부·신고연도 확인',key='rt_aggregate_ok')
                if p['year']!=year:st.error('원본 연도와 조회 연도를 맞추세요.')
                elif st.button('기존 집계표 이관 저장',disabled=not yes,type='primary'):act(lambda:db.import_aggregate(c,p,dict(name=f.name,content=f.getvalue())))
            except (ValueError,TypeError) as e:st.error(str(e))

def review(c,year):
    st.subheader('면적·세액 검토');gs=db.business_groups(c,year)
    if not gs:st.info('사업장과 건물 명세를 먼저 등록하세요.');return
    index=st.selectbox('검토할 신고 단위',list(range(len(gs))),format_func=lambda i:gs[i]['company']+' / '+gs[i]['region']+' / '+gs[i]['unit']);g=gs[index]
    table([dict(사업장=m['site']['name'],총면적=m['total'],제외면적=m['excluded'],과세면적=m['taxable'],검토=', '.join(m['issues']) or '완료') for m in g['members']])
    table([dict(기본세액=g['base'],연면적세액=g['area_tax'],지방교육세=g['education_tax'],합계=g['total'])])
    for text in g['issues']:st.warning(text)
    existing=next((f for f in db.filings(c,year,'business') if (f['company'],f['region'],f['unit'])==(g['company'],g['region'],g['unit'])),None)
    if existing:st.success('검토 확정된 자료입니다. 신고·납부 관리에서 확인하세요.')
    else:
        check=st.checkbox('관할·신고단위·존치·제외면적·세율·감면 및 신고기한 확인',key='rt_review_ok_'+str(index))
        if st.button('검토 결과 확정',disabled=bool(g['issues']) or not check,type='primary'):act(lambda:db.confirm_business(c,g))
    with st.expander('계산 기준·참고 자료'):
        st.write('과세면적 합계가 330㎡를 초과하면 해당 과세면적 전체에 연면적 세율을 적용합니다. 소수점 처리는 사업장에 설정한 합산 후 버림 여부를 적용합니다. 지방교육세는 기본세액을 기준으로 별도 계산하며 감면도 세목별로 반영합니다.')
        for title,url in calc.SOURCES:st.link_button(title,url)


def filing_page(c,year):
    st.subheader('지자체별 신고·납부 관리');data=report.filing_rows(c,year)
    if not data:st.info('면적·세액 검토 또는 법인지방소득세 안분을 먼저 확정하세요.');return
    cols=st.columns(4);kind=cols[0].selectbox('세목',['전체','주민세(사업소분)','법인지방소득세']);company=cols[1].selectbox('조회 법인',['전체']+sorted({x['법인'] for x in data}));region=cols[2].selectbox('조회 지자체',['전체']+sorted({x['관할지자체'] for x in data}));state=cols[3].selectbox('납부상태',['전체','미납','일부 납부','납부 완료','납부대상 없음'])
    shown=[x for x in data if (kind=='전체' or x['세목']==kind) and (company=='전체' or x['법인']==company) and (region=='전체' or x['관할지자체']==region) and (state=='전체' or x['납부상태']==state)];table(shown)
    fs=[f for f in db.filings(c,year) if (kind=='전체' or ('business' if kind=='주민세(사업소분)' else 'corporate')==f['kind']) and (company=='전체' or f['company']==company) and (region=='전체' or f['region']==region)]
    if not fs:return
    lookup={f['id']:f for f in fs};id=st.selectbox('기록할 신고 단위',list(lookup),format_func=lambda id:lookup[id]['company']+' / '+lookup[id]['region']+' / '+lookup[id]['unit']);f=lookup[id];key='rt_filing_'+str(id)+'_'+str(f['version'])
    st.info('이 화면은 신고·납부 기록 관리입니다. 실제 접수·납부는 위택스 또는 관할 지자체에서 진행한 뒤 기록하세요.');st.link_button('위택스 열기','https://www.wetax.go.kr/')
    tabs=st.tabs(['신고 기록','납부 기록','첨부·확정 해제'])
    with tabs[0]:
        with st.form(key+'file'):
            cols=st.columns(2);day=cols[0].date_input('신고일',date.fromisoformat(f['filed_date']) if f['filed_date'] else db.today());receipt=cols[1].text_input('신고 접수번호',f['receipt']);files=st.file_uploader('신고서·접수증',type=['pdf','jpg','jpeg','png'],accept_multiple_files=True)
            if st.form_submit_button('신고 완료 기록',type='primary'):act(lambda:db.record_filing(c,id,day,receipt,uploaded(files),f['version']))
    with tabs[1]:
        cols=st.columns(3);cols[0].metric('확정세액',f"{f['data']['total']:,}원");cols[1].metric('누적 납부액',f"{f['data']['total']-db.balance(c,id):,}원");cols[2].metric('미납잔액',f'{db.balance(c,id):,}원')
        with st.form(key+'pay'):
            cols=st.columns(2);day=cols[0].date_input('납부일',db.today());amount=cols[1].number_input('납부금액 (원)',min_value=0,value=max(0,db.balance(c,id)));note=st.text_input('납부 메모');files=st.file_uploader('납부증',type=['pdf','jpg','jpeg','png'],accept_multiple_files=True)
            if st.form_submit_button('납부 내역 저장',type='primary'):act(lambda:db.pay(c,id,day,amount,note,uploaded(files)))
        ps=db.payments(c,id);table([dict(내역번호=p['id'],납부일=p['paid_date'],납부액=p['amount'],비고=p['note']) for p in ps])
        if ps:
            pid=st.selectbox('잘못된 납부 기록 선택',[p['id'] for p in ps],key=key+'pid');check=st.checkbox('선택한 납부 기록 삭제 확인',key=key+'pcheck')
            if st.button('납부 기록 삭제',disabled=not check,key=key+'pdel'):act(lambda:db.undo_payment(c,id,pid))
    with tabs[2]:
        for e in db.evidence(c,id):st.download_button(e['name'],db.evidence_bytes(c,id,e['id']),file_name=e['name'],mime=e['mime'],key=key+'e'+str(e['id']))
        reason=st.text_input('확정 해제 사유',key=key+'reason');st.caption('신고·납부 기록이 없는 자료만 해제합니다. 법인지방소득세는 같은 법인의 모든 지자체 확정을 함께 해제합니다.')
        if st.button('검토 확정 해제',disabled=bool(f['filed_date'] or db.payments(c,id)),key=key+'release'):act(lambda:db.release(c,id,reason))

def corporate_page(c,year):
    st.subheader('법인지방소득세 안분자료');companies=sorted({s['company'] for s in db.sites(c,year)})
    if not companies:st.info('법인과 사업장을 먼저 등록하세요.');return
    company=st.selectbox('안분 법인',companies,key='rt_corp_company');ss=[s for s in db.sites(c,year) if s['company']==company];v=db.corporate(c,year,company) or {};key=f'rt_corp_{year}_{company}_{v.get("version",0)}_'
    st.info('주민세의 7월 1일 과세면적을 그대로 사용하지 않습니다. 사업연도 종료일의 종업원 수와 직접 사용 건축물 안분면적을 별도로 입력하세요.')
    cols=st.columns(3);end=str(cols[0].date_input('사업연도 종료일',date.fromisoformat(v.get('fiscal_end',f'{year}-12-31')),key=key+'end'));deadline=str(cols[1].date_input('법인지방소득세 신고기한',date.fromisoformat(v.get('deadline',f'{year+1}-04-30')),key=key+'deadline'));total=cols[2].number_input('안분대상 산출세액 (원)',min_value=0,value=int(v.get('total',0)),key=key+'total')
    initial={int(x['site_id']):x for x in v.get('items',[])}
    frame=pd.DataFrame([dict(사업장번호=s['id'],사업장=s['name'],관할지자체=s['region'],연말대상=bool(initial.get(s['id'],{}).get('include',True)),종업원수=float(initial.get(s['id'],{}).get('employees',0)),안분면적=float(initial.get(s['id'],{}).get('area',0))) for s in ss])
    edited=st.data_editor(frame,hide_index=True,use_container_width=True,disabled=['사업장번호','사업장','관할지자체'],column_config=aligned_config(frame),key=key+'rows')
    try:
        items=[dict(site_id=int(r['사업장번호']),include=bool(r['연말대상']),employees=float(r['종업원수']),area=float(r['안분면적']),jurisdiction=r['관할지자체']) for r in edited.to_dict('records')]
    except (TypeError,ValueError):st.error('종업원 수와 안분면적을 숫자로 입력하세요.');return
    allocation=None
    try:
        allocation=calc.allocate([x for x in items if x['include']],total)
        show=[dict(관할지자체=r['jurisdiction'],종업원수=r['employees'],안분면적=r['area'],안분율=f"{r['ratio']*100:.6f}%",안분세액=r['amount'],원단위조정=r['adjustment']) for r in allocation];table(show)
        out=BytesIO()
        with pd.ExcelWriter(out,engine='openpyxl') as w:
            pd.DataFrame(show).to_excel(w,index=False,sheet_name='지자체별안분');pd.DataFrame(edited).to_excel(w,index=False,sheet_name='연말사업장명세')
            for s in w.sheets.values():
                format_excel(s)
                for row in s:
                    for cell in row:
                        if cell.data_type=='f':cell.data_type='s'
        cols=st.columns(2);cols[0].download_button('안분명세 엑셀',out.getvalue(),file_name=f'{company}_{year}_법인지방소득세_안분.xlsx');cols[1].download_button('안분명세 인쇄 HTML',report.html(show,'법인지방소득세 안분 검토명세',year),file_name=f'법인지방소득세_안분_{year}.html',mime='text/html')
    except ValueError as e:st.warning(str(e))
    st.caption('일반 안분율 = (지자체 종업원수 ÷ 법인 전체 종업원수 + 지자체 안분면적 ÷ 법인 전체 안분면적) ÷ 2. 원 단위 차이는 합계가 일치하도록 배분하고 조정액을 표시합니다. 특수 안분·공제·가산세·환급은 별도 검토 대상입니다.')
    note=st.text_input('인원·안분면적·세액·특수 안분 여부 확인 근거',v.get('note',''),key=key+'note');reviewed=st.checkbox('모든 사업장의 연말 대상 여부·관할·안분자료 확인',value=v.get('reviewed',False),key=key+'reviewed')
    if st.button('안분 검토자료 저장',disabled=allocation is None,key=key+'save',type='primary'):act(lambda:db.save_corporate(c,year,company,dict(fiscal_end=end,deadline=deadline,total=total,items=items,note=note,reviewed=reviewed),v.get('version')))
    if v:
        st.caption('확정은 마지막 저장본을 기준으로 합니다. 변경한 입력은 먼저 저장하세요.')
        if st.button('저장한 안분자료 확정·지자체별 신고기록 생성',key=key+'confirm'):act(lambda:db.confirm_corporate(c,year,company))

def render_alerts(c=None,home=False):
    c=c or db.connect();day=db.today();notices=[]
    for f in db.filings(c):
        if f['kind']=='business' and not f['data'].get('target',True):continue
        delta=(date.fromisoformat(f['data']['deadline'])-day).days
        if delta<=30 and (not f['filed_date'] or db.balance(c,f['id'])>0):notices.append(f"{f['company']} / {f['region']} / {f['unit']} · 기한 {f['data']['deadline']} · {'미신고' if not f['filed_date'] else '미납 '+format(db.balance(c,f['id']),',')+'원'}")
    for year in sorted({s['year'] for s in db.sites(c)}):
        for g in db.business_groups(c,year):
            delta=(date.fromisoformat(g['deadline'])-day).days
            if g.get('target',True) and 0<=delta<=30 and not any((f['company'],f['region'],f['unit'])==(g['company'],g['region'],g['unit']) for f in db.filings(c,year,'business')):notices.append(f"{g['company']} / {g['unit']} · {g['deadline']} 신고자료 미확정")
    if notices:
        with st.expander(f'주민세·법인지방소득세 알림 {len(notices)}건',expanded=True):
            for text in notices:st.warning(text)
        if home:st.button('주민세 관리 열기',key='rt_home_open',on_click=lambda:st.session_state.update(main_system=SYSTEM,rt_page=PAGES[0]))

def render(user):
    c=db.connect();st.html(CSS);page=st.session_state.get('rt_page',PAGES[0]);page=page if page in PAGES else PAGES[0]
    with st.sidebar:
        st.markdown('**주민세 관리**')
        for name in PAGES:st.button(name,key='rt_side_'+name,use_container_width=True,type='primary' if page==name else 'secondary',on_click=go,args=(name,))
    with st.container(key='rt_subnav'):
        cols=st.columns(6)
        for col,name in zip(cols,PAGES):col.button(name,key='rt_nav_'+name,use_container_width=True,type='primary' if page==name else 'secondary',on_click=go,args=(name,))
    year=st.number_input('신고·귀속 연도',2000,2100,db.today().year,key='rt_year')
    if st.session_state.get('rt_notice'):st.success(st.session_state.pop('rt_notice'))
    {PAGES[0]:overview,PAGES[1]:sites_page,PAGES[2]:upload_page,PAGES[3]:review,PAGES[4]:filing_page,PAGES[5]:corporate_page}[page](c,year)
