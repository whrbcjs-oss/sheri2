"""Display the approved logo image without modifying its source artwork."""
from base64 import b64encode
from functools import lru_cache
from pathlib import Path
from PIL import Image
import streamlit as st

LOGO = Path(__file__).resolve().parent / 'assets' / 'hs_logo.png'


@lru_cache(maxsize=1)
def logo_markup():
    with Image.open(LOGO) as image:
        width, height = image.size
        box = image.getchannel('A').getbbox() if image.mode == 'RGBA' else (0,0,width,height)
    if not box:
        raise ValueError('로고 이미지가 비어 있습니다.')
    left, top, right, bottom = box
    visible_width, visible_height = right-left, bottom-top
    content = b64encode(LOGO.read_bytes()).decode('ascii')
    # Use a CSS viewport to omit transparent canvas padding; keep the PNG intact.
    style = f'width:{width/visible_width*100:.6f}%;left:{-left/visible_width*100:.6f}%;top:{-top/visible_height*100:.6f}%;'
    return f'<div class="hs-sidebar-logo" style="aspect-ratio:{visible_width}/{visible_height}"><img alt="HS 경리Job\'s" src="data:image/png;base64,{content}" style="{style}"></div>'


def render_sidebar_logo():
    with st.sidebar:
        with st.container(key='hs_sidebar_brand'):
            st.markdown(logo_markup(),unsafe_allow_html=True)


def without_sidebar_program_titles(source):
    """Hide redundant legacy app/sidebar headings while preserving page and report titles."""
    import ast,re
    titles={'자체결산보고','자체결산','엘비데크월별보고','공동도급관리대장','한국은행기업경기조사','수지보고서'}
    tree=ast.parse(source)
    lines=source.encode('utf-8').splitlines(keepends=True)
    offsets=[0]
    for line in lines:offsets.append(offsets[-1]+len(line))
    edits=[]
    def path(node):
        if isinstance(node,ast.Name):return node.id
        if isinstance(node,ast.Attribute):return path(node.value)+'.'+node.attr
        return ''
    def visit(node,sidebar=False):
        if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef,ast.Lambda)):sidebar=False
        if isinstance(node,(ast.With,ast.AsyncWith)):
            sidebar=sidebar or any(path(item.context_expr)=='st.sidebar' for item in node.items)
        if isinstance(node,ast.Expr) and isinstance(node.value,ast.Call):
            call=node.value;target=path(call.func)
            heading_calls={'st.header','st.subheader','st.title','st.sidebar.header','st.sidebar.subheader','st.sidebar.title','st.markdown','st.sidebar.markdown'}
            if target in heading_calls:
                label=call.args[0].value if call.args and isinstance(call.args[0],ast.Constant) else None
                if isinstance(label,str):
                    label=re.sub(r'^(?:#{1,6}\s*|[▥▤▦▣■□]+\s*)+','',label.strip())
                    label=''.join(label.split())
                    in_sidebar=sidebar or target.startswith('st.sidebar.')
                    remove=(in_sidebar and label in titles) or (not in_sidebar and label=='관계사통합수지관리')
                    if remove:
                        start=offsets[node.lineno-1]+node.col_offset;end=offsets[node.end_lineno-1]+node.end_col_offset
                        edits.append((start,end));return
        for child in ast.iter_child_nodes(node):visit(child,sidebar)
    visit(tree)
    raw=source.encode('utf-8')
    for start,end in sorted(edits,reverse=True):raw=raw[:start]+b'pass'+b'\n'*raw[start:end].count(b'\n')+raw[end:]
    return raw.decode('utf-8')
