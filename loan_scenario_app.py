"""Interactive forecasts, spreadsheet-shaped output and immutable plan confirmation."""
from datetime import date,datetime,timezone,timedelta
import json,hashlib
import pandas as pd
import streamlit as st
import loan_calc as calc
import loan_store as db
import loan_scenario as scenario


def output(result,key,status):
    st.html(scenario.html(result,status=status))
    cols=st.columns(2)
    cols[0].download_button('상환표 인쇄',scenario.html(result,True,status),file_name='월별상환명세.html',mime='text/html',key=key+'print',use_container_width=True)
    cols[1].download_button('엑셀 양식 다운로드',scenario.excel(result,status),file_name='원리금_상환산출서.xlsx',key=key+'xlsx',use_container_width=True)
    st.caption('인쇄 파일을 열고 인쇄 / PDF 저장을 선택하세요. 엑셀은 차용조건·월별상환명세·상환요약 세 시트로 구성됩니다.')


def confirmed_time(record):
    return datetime.fromisoformat(record['created_at']).replace(tzinfo=timezone.utc).astimezone(timezone(timedelta(hours=9))).strftime('%Y-%m-%d %H:%M')


def render(c,item):
    key='scenario_'+str(item['id'])+'_'
    saved=db.confirmed_scenarios(c,item['id'])
    if saved:
        with st.expander('확정된 상환계획 · '+str(len(saved))+'건'):
            lookup={r['id']:r for r in saved}
            selected=st.selectbox('확정 이력',list(lookup),format_func=lambda id:'#'+str(id)+' · '+confirmed_time(lookup[id])+' · '+lookup[id]['data']['options']['mode'],key=key+'saved')
            record=lookup[selected]
            st.caption('확정자 '+record['actor']+' · '+record['memo']+' · 확정 당시 조건과 잔액으로 저장된 계획입니다.')
            output(record['data'],key+'saved_'+str(selected),'확정 상환계획 #'+str(selected)+' · '+confirmed_time(record)+' KST · 확정자 '+record['actor'])
    if item.get('closed'):
        st.info('통합 승계·취소된 건은 확정 이력만 조회합니다. 현재 유효한 계약에서 새 시나리오를 작성하세요.');return
    st.caption('첨부 양식처럼 차용건별 기초원금·월이자·원금상환·기말원금을 표시합니다. 조건을 선택하면 상환표를 계산합니다.')
    candidates=[v for v in db.loans(c) if v['borrower_id']==item['borrower_id'] and v['company']==item['company']]
    lookup={v['id']:v for v in candidates}
    ids=st.multiselect('상환표에 포함할 차용건',list(lookup),default=[item['id']],format_func=lambda id:lookup[id]['number']+' · '+calc.money(db.summary(c,lookup[id],db.today())['balance'])+'원',key=key+'loans')
    if not ids:st.info('상환표에 포함할 차용건을 선택하세요.');return
    now=db.today()
    try:sources=db.scenario_sources(c,ids,now)
    except ValueError as e:st.info(str(e));return
    with st.container(border=True):
        st.markdown('**차용조건 · 상환방식**')
        mode=st.radio('시나리오 상환조건',calc.MODES,index=calc.MODES.index(item['terms']['mode']),key=key+'mode')
        cols=st.columns(2)
        method=cols[0].selectbox('시나리오 원리금 계산',calc.METHODS,index=calc.METHODS.index(item['terms']['method']),key=key+'method',disabled=mode!=calc.MODES[0] or st.session_state.get(key+'manual',bool(item['terms'].get('installment',0))))
        manual=cols[1].checkbox('시나리오 월 원리금 직접 지정',value=bool(item['terms'].get('installment',0)),key=key+'manual',disabled=mode!=calc.MODES[0])
        installment=st.number_input('시나리오 매월 원리금 합계 (원)',min_value=0,value=int(item['terms'].get('installment',0)),key=key+'installment',disabled=not manual or mode!=calc.MODES[0])
        auto=st.checkbox('월 납부액으로 완제일까지 자동 산출',value=True,key=key+'auto',disabled=not manual or mode!=calc.MODES[0])
        st.caption('월정액은 당월이자·과거 미납이자를 먼저 충당하고 나머지를 기초원금 비율로 배분합니다. 자동 산출을 끄면 선택한 만기에 남은 원리금을 정산합니다.')
    with st.container(border=True):
        st.markdown('**차용건별 금액 · 이자**')
        for i,s in enumerate(sources):
            st.markdown('**'+s['number']+'** · 원금 '+calc.money(s['principal'])+'원 · 미회수 이자 '+calc.money(s['carry_interest'])+'원 · 선납이자 '+calc.money(s['interest_credit'])+'원')
            cols=st.columns(2)
            s['rate']=str(cols[0].number_input('변경 연이율 (%)' if len(sources)==1 else s['number']+' 연이율 (%)',0.,100.,float(s['rate']),key=key+'rate' if len(sources)==1 else key+'rate_'+str(s['loan_id']),disabled=s['interest_kind']!=calc.KINDS[0]))
            s['fixed_interest']=cols[1].number_input(s['number']+' 월 약정이자 (원)',min_value=0,value=int(s['fixed_interest']),key=key+'fixed_'+str(s['loan_id']),disabled=s['interest_kind']!=calc.KINDS[1])
        pre=st.number_input('추가 원금상환 가정 (원)',0,sum(s['principal'] for s in sources),0,key=key+'pre')
        basis=st.selectbox('시나리오 이자 계산 기준',scenario.BASIS,key=key+'basis')
        st.caption('월할은 첨부 양식과 같이 매회 연이율÷12를 적용합니다. 부분월을 반영하려면 계약 기준 또는 일할을 선택하세요. 미납이자는 소멸시키지 않고 다음 회차에 이월합니다.')
    with st.container(border=True):
        st.markdown('**상환 일정**');cols=st.columns(3)
        end=cols[0].date_input('예상 만기일',max(calc.add_months(now,1),calc.day(item['terms']['end_date'])),min_value=now,key=key+'end',disabled=manual and auto and mode==calc.MODES[0])
        first=cols[1].date_input('시나리오 첫 상환일',min(calc.add_months(now,1,item['terms']['pay_day']),end),min_value=now,key=key+'first')
        pay_day=cols[2].number_input('시나리오 매월 상환일 (일)',1,31,int(item['terms']['pay_day']),key=key+'payday')
        st.caption('매월 말일 상환은 31일로 선택하세요. 만기 원리금 상환도 매월 발생이자를 보여주고 실제 상환액은 만기에 표시합니다.')
    st.button('시나리오 계산',key=key+'calculate')
    options=dict(as_of=str(now),end_date=str(end),first_due=str(first),pay_day=pay_day,mode=mode,method=method,manual=manual,auto_payoff=auto,installment=installment,basis=basis,prepayment=pre)
    try:result=scenario.forecast(sources,options)
    except ValueError as e:st.info(str(e));return
    cols=st.columns(3)
    for col,label,value in zip(cols,['예상 원금 상환 합계','예상 이자 상환 합계','예상 원리금 상환 합계'],[result['totals']['principal'],result['totals']['interest'],result['totals']['payment']]):col.metric(label,calc.money(value)+'원')
    st.subheader('월별 예상 상환 시나리오')
    output(result,key+'draft_','예상 시나리오')
    with st.expander('월별 합계 확인'):
        st.dataframe(pd.DataFrame([{'회차':r['index'],'예상 상환일':r['due_date'],'월별 발생이자':r['earned_interest'],'원금 상환액':r['principal_paid'],'이자 상환액':r['interest_paid'],'원리금 합계':r['total'],'예상 잔여원금':r['balance'],'이월 미납이자':r['interest_balance']} for r in result['rows']]),hide_index=True,use_container_width=True)
    comparisons=[]
    for alternative in calc.MODES:
        try:
            candidate=scenario.forecast(sources,dict(options,mode=alternative));t=candidate['totals']
            comparisons.append({'상환방식':alternative,'첫 회차 원리금':candidate['rows'][0]['total'],'만기 회차 원리금':candidate['rows'][-1]['total'],'예상 총 이자상환':t['interest'],'예상 총 원리금':t['payment'],'예상 종료일':t['end_date'],'상환 횟수':t['count']})
        except ValueError:comparisons.append({'상환방식':alternative,'첫 회차 원리금':None,'만기 회차 원리금':None,'예상 총 이자상환':None,'예상 총 원리금':None})
    st.subheader('세 가지 상환방식 비교');st.dataframe(pd.DataFrame(comparisons),hide_index=True,use_container_width=True)
    with st.container(border=True):
        st.markdown('**시나리오 확정**')
        st.caption('선택한 조건·기준 잔액·상환표를 확정 이력으로 보존합니다. 법적 계약 변경과 실제 입금 처리는 별도로 진행하세요. 이후 조건을 바꿔 확정해도 이전 확정본은 남습니다.')
        memo=st.text_input('확정 메모',key=key+'memo')
        digest=hashlib.sha256(json.dumps(result,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        approved=st.checkbox('조건·상환표 확인 및 확정 상환계획 저장',key=key+'approve_'+digest[:16])
        if st.button('시나리오 확정 저장',disabled=not approved,key=key+'confirm'):
            try:
                if st.session_state.get(key+'confirmed_digest')==digest:st.info('동일한 상환계획을 이미 확정했습니다.')
                else:
                    id=db.confirm_scenario(c,result,memo);st.session_state[key+'confirmed_digest']=digest;st.session_state[key+'notice']='상환계획 #'+str(id)+'을 확정했습니다.';st.rerun()
            except ValueError as e:st.error(str(e))
        notice=st.session_state.pop(key+'notice',None)
        if notice:st.success(notice)
