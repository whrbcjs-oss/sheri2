"""Manual director entry and editable board-resolution drafting."""
import json,hashlib
import streamlit as st
import streamlit.components.v1 as components
import board_resolution as board
import loan_calc as calc
import loan_store as db
from loan_report import interest_label


def start(loan_id=None):
    st.session_state['loan_page']='이사회 결의서'
    st.session_state['_board_loaded']=None;st.session_state['_board_link_loan']=loan_id
    st.session_state['_board_generation']=st.session_state.get('_board_generation',0)+1


def exports(v,key):
    filename='이사회결의서_'+v.get('number','미저장')+'_v'+str(v.get('version',1))
    cols=st.columns(3)
    cols[0].download_button('결의서 인쇄',board.html(v),file_name=filename+'.html',mime='text/html',key=key+'html',use_container_width=True)
    cols[1].download_button('DOCX 다운로드',board.docx(v),file_name=filename+'.docx',mime='application/vnd.openxmlformats-officedocument.wordprocessingml.document',key=key+'docx',use_container_width=True)
    if cols[2].button('PDF 만들기',key=key+'pdfmake',use_container_width=True):
        st.download_button('결의서 PDF 다운로드',board.pdf(v),file_name=filename+'.pdf',mime='application/pdf',key=key+'pdf')
    st.caption('인쇄 파일을 열어 인쇄/PDF 저장을 선택할 수 있습니다. DOCX는 한글 등 지원 문서 편집기에서 열어 수정할 수 있습니다.')


def render(c):
    st.header('이사회 결의서')
    records=db.board_resolutions(c);lookup={r['id']:r for r in records};latest={}
    for r in records:latest.setdefault(r['doc_root'],r)
    with st.expander('저장된 결의서 불러오기·출력',expanded=bool(records)):
        if records:
            selected=st.selectbox('저장된 결의서',list(latest.values()),format_func=lambda r:r['number']+' · '+r['company']+' · '+r['data']['title']+' · '+('확정' if r['status']=='final' else '작성중'),key='board_select')
            versions=[r for r in records if r['doc_root']==selected['doc_root']]
            chosen_id=st.selectbox('저장 버전',list(r['id'] for r in versions),format_func=lambda id:'v'+str(lookup[id]['version'])+' · '+('확정' if lookup[id]['status']=='final' else '작성중')+' · '+lookup[id]['data']['meeting_date'],key='board_version')
            if st.button('선택 버전 불러오기',key='board_load'):
                st.session_state['_board_loaded']=chosen_id;st.session_state['_board_link_loan']=lookup[chosen_id]['loan_id'];st.session_state['_board_generation']=st.session_state.get('_board_generation',0)+1;st.rerun()
            exports(lookup[chosen_id]['data'],'board_saved_'+str(chosen_id)+'_')
        else:st.caption('저장된 결의서가 없습니다.')
    if st.button('새 결의서 작성',key='board_new'):start();st.rerun()
    loaded=lookup.get(st.session_state.get('_board_loaded'));initial=loaded['data'] if loaded else {}
    key='board_'+str(st.session_state.get('_board_generation',0))+'_'
    items=db.loans(c,include_closed=True);sources={v['id']:v for v in items}
    default=st.session_state.get('_board_link_loan')
    options=[None]+list(sources)
    linked=st.selectbox('차용증 연결 (선택)',options,index=options.index(default) if default in options else 0,format_func=lambda id:'연결 없이 직접 작성' if id is None else sources[id]['number']+' · '+sources[id]['company']+' · '+sources[id]['borrower']['name'],key=key+'loan')
    source=None;contract_id=None;digest=None
    if linked:
        versions=sources[linked]['versions'];ids=[x['id'] for x in reversed(versions)]
        old=initial.get('contract_id')
        contract_id=st.selectbox('연결 차용증 버전',ids,index=ids.index(old) if old in ids else 0,format_func=lambda id:next(v['number'] for v in versions if v['id']==id),key=key+'contract_'+str(linked))
        source=next(v['data'] for v in versions if v['id']==contract_id);digest=db.board_source_digest(source)
    context=key+str(contract_id or 0)+'_'
    with st.container(border=True):
        st.markdown('**회사 · 회의 정보**');cols=st.columns(2)
        company=cols[0].text_input('회의 개최회사 / 차용금 지급회사',source['company'] if source else initial.get('company',''),disabled=bool(source),key=context+'company')
        meeting=cols[1].date_input('회의일자',calc.day(initial.get('meeting_date',db.today())),key=key+'date')
        cols=st.columns(2);place=cols[0].text_input('회의 장소',initial.get('place','본사 회의실'),key=key+'place')
        total=cols[1].number_input('이사 총수',0,100,int(initial.get('total_directors',0)),key=key+'total')
    with st.container(border=True):
        st.markdown('**대표이사 · 이사 수동 입력**')
        st.caption('직위와 성명을 직접 입력하고 출석 여부를 선택하세요. 행 추가·삭제가 가능하며 출석으로 선택한 이사만 서명란에 표시합니다.')
        defaults=initial.get('members') or [dict(role='대표이사',name='',present=False),dict(role='이사',name='',present=False)]
        rowkey=key+'member_rows'
        if rowkey not in st.session_state:st.session_state[rowkey]=list(range(len(defaults)))
        members=[]
        for index in list(st.session_state[rowkey]):
            base=defaults[index] if index<len(defaults) else dict(role='이사',name='',present=False)
            cols=st.columns([2,3,1.4,1],vertical_alignment='bottom')
            role=cols[0].text_input('직위 '+str(index+1),base['role'],key=key+'role_'+str(index))
            name=cols[1].text_input('성명 '+str(index+1),base['name'],key=key+'name_'+str(index))
            present=cols[2].checkbox('출석 '+str(index+1),value=base['present'],key=key+'present_'+str(index))
            if cols[3].button('삭제',key=key+'remove_'+str(index),use_container_width=True):
                st.session_state[rowkey].remove(index);st.rerun()
            members.append(dict(role=role,name=name,present=present))
        if st.button('이사 행 추가',key=key+'add_member'):
            next_id=st.session_state.get(key+'next_member',len(defaults))
            st.session_state[rowkey].append(next_id);st.session_state[key+'next_member']=next_id+1;st.rerun()
        st.caption('출석이사 '+str(sum(r['present'] and bool(r['name'].strip()) for r in members))+'명 · 입력한 이사 총수 '+str(total)+'명')
    with st.container(border=True):
        st.markdown('**안건 유형 · 작성 조건**')
        topic=st.selectbox('안건 유형',board.TOPICS,index=board.TOPICS.index(initial.get('topic',board.TOPICS[0])),key=key+'topic')
        tkey=context+str(board.TOPICS.index(topic))+'_'
        title=st.text_input('안건 제목',initial.get('title',topic if topic!=board.TOPICS[3] else '') if initial.get('topic',topic)==topic else topic,key=tkey+'title')
        same=initial.get('topic')==topic and initial.get('contract_id')==contract_id
        f=dict(initial.get('topic_fields',{})) if same else {}
        if source and not same and topic==board.TOPICS[0]:
            person=source.get('borrower',{})
            f.update(name=person.get('name',''),birth=person.get('national_id','') if person.get('kind')=='법인' else board.birth(person.get('national_id','')),address=person.get('address',''),amount=source['principal'],start=source['start_date'],end=source['end_date'],interest=interest_label(source),repayment=source['mode'],collateral=source.get('collateral',''))
        def text(label,name,default=''):
            return st.text_input(label,str(f.get(name,default)),key=tkey+name)
        def amount(label):return st.number_input(label,min_value=0,max_value=10**15,value=int(f.get('amount',0)),step=100000,key=tkey+'amount')
        def dates():
            cols=st.columns(2)
            start=cols[0].date_input('대여일 / 발행일',calc.day(f.get('start') or db.today()),key=tkey+'start')
            end=cols[1].date_input('상환일 / 만기일',calc.day(f.get('end') or calc.add_months(db.today(),12)),key=tkey+'end')
            return str(start),str(end)
        if topic==board.TOPICS[0]:
            f=dict(name=text('차용인 / 법인명','name'),birth=text('생년월일 / 법인 식별정보','birth'),address=text('차용인 주소','address'),amount=amount('대여금액 (원)'),start=f.get('start'),end=f.get('end'),interest=text('이자 적용','interest'),repayment=text('상환방법','repayment'),collateral=text('담보·기타 조건','collateral'))
            f['start'],f['end']=dates()
        elif topic==board.TOPICS[1]:
            product=text('상품명','product');security=text('종목명','security');value=amount('투자금액 (원)');start,end=dates()
            yield_=text('예상 수익률·신탁보수','yield');credit=text('신용공여·신용보강 사항','credit')
            f=dict(product=product,security=security,amount=value,start=start,end=end,credit=credit);f['yield']=yield_
        elif topic==board.TOPICS[2]:
            counterparty=text('거래 상대방','counterparty');value=amount('최고 거래한도 (원)');period=text('협정기간','period');extension=text('자동연장 조건','extension');interest=text('이자율 기준','interest');repayment=text('이자 지급방식','repayment')
            f=dict(counterparty=counterparty,amount=value,period=period,extension=extension,interest=interest,repayment=repayment)
        else:f={}
    bodykey=tkey+'body'
    generated=board.template(topic,f);autokey=tkey+'last_generated'
    if bodykey not in st.session_state:
        st.session_state[bodykey]=initial.get('body','') if same else generated
        st.session_state[autokey]=None if same else generated
    elif st.session_state.get(autokey) is not None and st.session_state[bodykey]==st.session_state[autokey]:
        st.session_state[bodykey]=generated;st.session_state[autokey]=generated
    if topic!=board.TOPICS[3] and st.button('입력 조건으로 본문 다시 생성',key=tkey+'generate'):
        st.session_state[bodykey]=generated;st.session_state[autokey]=generated
    st.caption('직접 수정하기 전에는 입력 조건에 맞춰 본문을 갱신합니다. 직접 수정한 본문과 불러온 저장본은 그대로 유지하며, 다시 생성 버튼을 누르면 현재 조건으로 교체합니다.')
    body=st.text_area('결의 본문 (직접 수정)',height=340,key=bodykey)
    data=dict(company=company,meeting_date=str(meeting),place=place,total_directors=total,members=members,topic=topic,title=title,body=body,topic_fields=f,loan_id=linked,contract_id=contract_id,source_digest=digest)
    try:
        preview=board.validate(data)
        st.subheader('이사회 결의서 미리보기');components.html(board.html(preview),height=820,scrolling=True)
        exports(preview,tkey+'preview_')
    except ValueError as e:st.info(str(e))
    fingerprint=hashlib.sha256(json.dumps(data,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    confirmed=st.checkbox('회의 정보·최종 본문·출석 명단 확인',key=tkey+'confirm_'+fingerprint[:16])
    cols=st.columns(2)
    def save(final):
        try:
            id=db.save_board_resolution(c,data,final,loaded['doc_root'] if loaded else None)
            st.session_state['_board_loaded']=id;st.session_state['_board_link_loan']=linked;st.session_state['_board_generation']=st.session_state.get('_board_generation',0)+1;st.rerun()
        except ValueError as e:st.error(str(e))
    if cols[0].button('결의서 초안 저장',key=tkey+'save',use_container_width=True):save(False)
    if cols[1].button('결의서 확정 저장',type='primary',disabled=not confirmed,key=tkey+'final',use_container_width=True):save(True)
