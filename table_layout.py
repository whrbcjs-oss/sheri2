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
        values=frame[name].dropna();values=values[values.map(lambda v:bool(str(v).strip()))];label=str(name)
        numeric=bool(len(values)) and all(isinstance(v,Number) and not isinstance(v,bool) or isinstance(v,str) and bool(re.fullmatch(r'-?[\d,]+(?:\.\d+)?%?',v.strip())) for v in values if str(v).strip())
        alignment='right' if numeric else 'center'
        # Date strings and identifiers are descriptive fields, even if stored as digits.
        if any(x in label for x in ['일자','일시','연월','날짜','코드','아이디','번호','회차','차수','순번','생년월일','전화','연락처','주민등록']):alignment='center'
        old=result.get(name)
        if isinstance(old,dict):result[name]={**old,'alignment':alignment}
        elif old is None:result[name]={'alignment':alignment}
        elif isinstance(old,str):result[name]={'label':old,'alignment':alignment}
        # Display formatting only: retain numeric values for sorting, editing and totals.
        actual_numeric=bool(len(values)) and all(isinstance(v,Number) and not isinstance(v,bool) for v in values)
        current=result.get(name)
        if alignment=='right' and actual_numeric and isinstance(current,dict):
            type_config=dict(current.get('type_config') or {})
            if type_config.get('type','number')=='number':
                type_config.setdefault('type','number')
                if type_config.get('format') is None:type_config['format']='localized'
                result[name]={**current,'type_config':type_config}
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


def format_excel(sheet,min_row=1):
    """Apply the same display convention to Excel exports without changing values."""
    from openpyxl.styles import Alignment
    for row in sheet.iter_rows(min_row=min_row):
        for cell in row:
            numeric=isinstance(cell.value,Number) and not isinstance(cell.value,bool)
            cell.alignment=Alignment(horizontal='right' if numeric else 'center',vertical='center',wrap_text=True)
            if numeric and cell.number_format=='General':cell.number_format='#,##0' if float(cell.value).is_integer() else '#,##0.########'
