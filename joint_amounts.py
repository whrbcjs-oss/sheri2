"""Currency presentation without changing Decimal storage or summing derived values twice."""
from decimal import Decimal
import pandas as pd
import streamlit as st
from joint_store import num

def formatted(value):
    d=num(value)
    if not d:return '0'
    text=format(d,'f');whole,_,fraction=text.partition('.')
    result=format(int(whole),',')
    if whole.startswith('-') and int(whole)==0:result='-'+result
    fraction=fraction.rstrip('0')
    return result+('.'+fraction if fraction else '')

def _format_input(key):
    try:st.session_state[key]=formatted(st.session_state[key])
    except ValueError:pass  # Keep invalid text visible; the save validator explains it.

def money_input(label,value='0',key=None,where=None):
    if key is None:raise ValueError('금액 입력 키가 필요합니다.')
    return (where or st).text_input(label,formatted(value),key=key,on_change=_format_input,args=(key,))

def frame(records,currency,row_sum=(),footer=True):
    data=records.to_dict('records') if isinstance(records,pd.DataFrame) else [dict(x) for x in records]
    if not data:return pd.DataFrame()
    columns=list(data[0]);currency=[k for k in currency if k in columns]
    if row_sum:
        for r in data:r['합계금액']=str(sum((num(r.get(k,0)) for k in row_sum),Decimal(0)))
        if '합계금액' in columns:columns.remove('합계금액')
        columns.insert(max(columns.index(k) for k in currency)+1,'합계금액');currency=list(dict.fromkeys(currency+['합계금액']))
    if footer:
        totals={k:'' for k in columns};first=next((k for k in columns if k not in currency),'구분');totals[first]='합계'
        for k in currency:totals[k]=str(sum((num(r.get(k,0)) for r in data),Decimal(0)))
        data.append(totals)
    for r in data:
        for k in currency:r[k]=formatted(r.get(k,0))
    result=pd.DataFrame(data,columns=columns)
    if footer:
        for k in columns:
            if k not in currency and any(isinstance(x,str) for x in result[k]) and any(isinstance(x,(int,float)) for x in result[k]):result[k]=result[k].map(str)
    return result

def show(records,currency,row_sum=(),footer=True):
    result=frame(records,currency,row_sum,footer)
    styled=result.style.set_properties(**{'text-align':'center'}).set_properties(subset=[k for k in list(currency)+['합계금액'] if k in result],**{'text-align':'right'})
    if footer and len(result):styled=styled.set_properties(subset=pd.IndexSlice[[result.index[-1]],:],**{'font-weight':'bold','background-color':'#e8edf0','border-top':'2px solid #66737d'})
    st.dataframe(styled,hide_index=True,use_container_width=True)
    return result
