"""Source-backed tax deadlines, displayed without inferring a company's filing status."""
from calendar import Calendar
from datetime import date, datetime, timedelta, timezone
from html import escape
from pathlib import Path
import json
import re
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

ROOT = Path(__file__).resolve().parent / 'assets' / 'tax_calendar'
SOURCE = 'https://www.nts.go.kr/nts/ad/taxSchdul/selectList.do?mi=135747'
CATEGORIES = ['원천세','부가세','법인세','지급명세서']
COLORS = {'원천세':'#087b52','부가세':'#2459a6','법인세':'#8651ae','지급명세서':'#b47014'}


def today():
    return datetime.now(timezone(timedelta(hours=9))).date()


def load_year(year):
    path = ROOT / (str(int(year)) + '.json')
    if not path.is_file():
        return None
    payload = json.loads(path.read_text(encoding='utf-8'))
    if payload['year'] != int(year):
        raise ValueError('일정 자료의 연도를 확인하세요.')
    for item in payload['events']:
        if date.fromisoformat(item['date']).year != int(year):
            raise ValueError('일정 자료의 날짜를 확인하세요.')
    return payload


def filter_events(events, closing_month=12, category='전체'):
    result = []
    for item in events:
        match = re.search(r'(\d+)월말 결산법인', item['title'])
        if match and int(match.group(1)) != closing_month:
            continue
        if category != '전체' and item['category'] != category:
            continue
        result.append(item)
    return sorted(result, key=lambda e:(e['date'],e['title']))


def deadline_label(day, current):
    delta = (day - current).days
    return '오늘 마감' if delta == 0 else 'D-' + str(delta) if delta > 0 else '기한 경과'


def calendar_html(year, month, events, current):
    weeks = Calendar(firstweekday=6).monthdatescalendar(year, month)
    parts = ['<!doctype html><html lang="ko"><meta charset="utf-8"><style>body{margin:0;font-family:"Malgun Gothic",Arial,sans-serif;color:#203c35}*{box-sizing:border-box}.grid{display:grid;grid-template-columns:repeat(7,minmax(0,1fr));border-top:1px solid #dce8e1;border-left:1px solid #dce8e1}.weekday,.day{border-right:1px solid #dce8e1;border-bottom:1px solid #dce8e1}.weekday{text-align:center;padding:12px;background:#f2f8f4;font-size:13px;font-weight:700}.day{min-height:108px;padding:8px;background:#fff;overflow:hidden}.other{background:#f7f9f8;color:#acb8b1}.sun .number{color:#bf5b5b}.sat .number{color:#4d74ab}.number{font-size:13px;display:inline-flex;align-items:center;justify-content:center;min-width:25px;height:25px;font-weight:700}.today .number{border-radius:50%;background:#087b52;color:white}.today{background:#f3fcf7}.event{display:block;padding:5px 6px;margin-top:4px;border-left:3px solid var(--event);border-radius:4px;background:#f0f6f3;font-size:11px;line-height:1.4;overflow-wrap:anywhere}.more{font-size:10px;color:#6c7e75;margin-top:5px}</style><div class="grid">']
    for label in ['일','월','화','수','목','금','토']:
        parts.append('<div class="weekday">'+label+'</div>')
    for week in weeks:
        for index, day in enumerate(week):
            classes='day '+('other ' if day.month!=month else '')+('today ' if day==current else '')+('sun' if index==0 else 'sat' if index==6 else '')
            parts.append('<div class="'+classes+'"><span class="number">'+str(day.day)+'</span>')
            items=[e for e in events if e['date']==day.isoformat()] if day.month==month else []
            for item in items[:3]:
                parts.append('<div class="event" style="--event:'+COLORS[item['category']]+'" title="'+escape(item['title']+' · '+item['note'],quote=True)+'">'+escape(item['title'])+'</div>')
            if len(items)>3:
                parts.append('<div class="more">외 '+str(len(items)-3)+'건 · 아래 목록에서 확인</div>')
            parts.append('</div>')
    parts.append('</div></html>')
    return ''.join(parts), len(weeks)*147+50


def render(user):
    current = today()
    with st.sidebar:
        st.markdown('<div style="padding:22px 16px;background:#075b42;color:white;font-size:25px;font-weight:800;border-radius:8px">회계 업무 일정</div>', unsafe_allow_html=True)
        st.caption('신고·납부 기한을 확인하고 각 업무 메뉴로 이동하세요.')
    from loan_app import render_alerts
    render_alerts(home=True)
    from accommodation_app import render_alerts as accommodation_alerts
    accommodation_alerts(home=True)
    from resident_tax_app import render_alerts as resident_tax_alerts
    resident_tax_alerts(home=True)
    st.header('회계 신고·납부 일정')
    st.caption('국세청 공통 일정입니다. 선택한 결산월과 세목을 기준으로 표시하며, 신고 완료 여부를 의미하지 않습니다.')
    controls = st.columns([1,1,1.4,1.5])
    years = sorted({current.year-1,current.year,current.year+1} | {int(p.stem) for p in ROOT.glob('*.json')})
    year = controls[0].selectbox('조회 연도',years,index=years.index(current.year),key='tax_calendar_year')
    month = controls[1].selectbox('조회 월',list(range(1,13)),index=current.month-1,format_func=lambda n:str(n)+'월',key='tax_calendar_month')
    closing_month = controls[2].selectbox('법인 결산월',list(range(1,13)),index=11,format_func=lambda n:str(n)+'월 결산',key='tax_calendar_closing')
    category = controls[3].selectbox('신고 항목',['전체']+CATEGORIES,key='tax_calendar_category')
    payload = load_year(year)
    if payload is None:
        st.info(str(year)+'년 공식 일정 자료가 아직 등록되지 않았습니다. 아래 국세청 링크에서 해당 연도의 최신 공지를 확인하세요.')
        st.link_button('국세청 공식 일정 확인',SOURCE+'&taxYear='+str(year)+'&taxMonth='+str(month))
        return
    events = filter_events(payload['events'],closing_month,category)
    monthly=[e for e in events if e['date'].startswith(f'{year:04}-{month:02}')]
    upcoming=[e for e in events if 0<=(date.fromisoformat(e['date'])-current).days<=14]
    columns=st.columns(3)
    columns[0].metric('선택 월 주요 일정',str(len(monthly))+'건')
    columns[1].metric('14일 이내 마감',str(len(upcoming))+'건')
    future=[e for e in events if e['date']>=current.isoformat()]
    columns[2].metric('가장 가까운 마감',deadline_label(date.fromisoformat(future[0]['date']),current) if future else '예정 없음')
    left,right=st.columns([3,1])
    with left:
        st.subheader(f'{year}년 {month:02}월')
        html,height=calendar_html(year,month,monthly,current)
        components.html(html,height=height,scrolling=True)
    with right:
        st.subheader('가까운 마감일')
        if not future:
            st.info('조회 연도의 예정 일정이 없습니다.')
        for event in future[:5]:
            with st.container(border=True):
                st.caption(event['date']+' · '+deadline_label(date.fromisoformat(event['date']),current))
                st.markdown('**'+event['title']+'**')
                st.caption(event['note'])
    st.subheader('선택 월 신고·납부 내용')
    if monthly:
        records=[{'기한':e['date'],'항목':e['category'],'신고·납부 내용':e['title'],'대상 기간':e['note'],'기한 안내':deadline_label(date.fromisoformat(e['date']),current)} for e in monthly]
        st.dataframe(pd.DataFrame(records),hide_index=True,use_container_width=True)
        st.download_button('이번 달 일정 CSV',pd.DataFrame(records).to_csv(index=False).encode('utf-8-sig'),file_name=f'회계일정_{year}{month:02}.csv')
    else:
        st.info('선택한 조건에 해당하는 등록 일정이 없습니다.')
    st.caption('출처: 국세청 세무일정 · 자료 확인일 '+payload['checked_on']+' · 국세 주요 일정만 표시합니다. 지방세·4대보험 일정과 회사별 기한 연장 공지는 별도 확인하세요.')
    st.link_button('국세청 공식 일정 확인',SOURCE+'&taxYear='+str(year)+'&taxMonth='+str(month))
