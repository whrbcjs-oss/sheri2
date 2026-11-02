"""Consistent table alignment for every integrated application route."""
import re
from numbers import Number
from functools import wraps
import pandas as pd
import streamlit as st

def aligned_config(data,config=None):
    try:
        frame=data.data if hasattr(data,'data') and isinstance(data.data,pd.DataFrame) else pd.DataFrame(data)
    except (ValueError,TypeError):return config or {}
    result=dict(config or {})
    for name in frame:
        values=frame[name].dropna();label=str(name)
        numeric=bool(len(values)) and all(isinstance(v,Number) and not isinstance(v,bool) or isinstance(v,str) and bool(re.fullmatch(r'-?[\d,]+(?:\.\d+)?%?',v.strip())) for v in values if str(v).strip())
        alignment='right' if numeric else 'center'
        # Date strings and identifiers are descriptive fields, even if stored as digits.
        if any(x in label for x in ['일자','일시','연월','날짜','코드','아이디','번호']):alignment='center'
        old=result.get(name)
        if isinstance(old,dict):result[name]={**old,'alignment':alignment}
        elif old is None:result[name]={'alignment':alignment}
        elif isinstance(old,str):result[name]={'label':old,'alignment':alignment}
    return result

def install():
    for name in ['dataframe','data_editor']:
        original=getattr(st,name)
        if getattr(original,'_aligned_tables',False):continue
        @wraps(original)
        def display(data=None,*args,_original=original,**kwargs):
            kwargs['column_config']=aligned_config(data,kwargs.get('column_config'))
            return _original(data,*args,**kwargs)
        display._aligned_tables=True
        setattr(st,name,display)
