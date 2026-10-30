"""Install public application files in an existing deployment, preserving private files."""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import secrets
import shutil
import sys

ROOT=Path(__file__).resolve().parent
FILES=['joint_workflow.py','joint_app.py','joint_store.py','joint_report.py','joint_import.py','multiuser_app.py','collaboration.py','monthly_app.py','monthly_store.py',
       'monthly_report_preview.py','monthly_preview_template.html','monthly_theme.css','monthly_ledger.py','requirements.lock',
       'requirements.txt','repair_dependencies.bat']


def update(target):
    target=Path(target).expanduser().resolve()
    if target.is_file():target=target.parent
    if target==ROOT:raise ValueError('새 다운로드 폴더가 아니라 기존 start.bat이 있는 폴더를 선택하세요.')
    if not (target/'app.py').is_file() or not (target/'start.bat').is_file() or not (target/'multiuser_app.py').is_file():
        raise ValueError('기존 설치 폴더가 아닙니다. 기존 start.bat이 있는 폴더를 선택하세요.')
    selector='system = st.radio("프로그램 선택", ["자체결산 보고", "엘비데크 월별보고"], key="main_system")'
    if (target/'app.py').read_text(encoding='utf-8').count(selector)!=1:
        raise ValueError('기존 프로그램의 메뉴 형식이 지원 버전과 다릅니다. 원본은 변경하지 않았습니다.')
    for name in FILES:
        if not (ROOT/name).is_file():raise ValueError('업데이트 파일 누락: '+name)
    stamp=datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')+'-'+secrets.token_hex(3)
    backup=target/'private'/'code-updates'/stamp
    backup.mkdir(parents=True)
    manifest={}
    for name in FILES:
        path=target/name
        manifest[name]=hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None
        if path.exists():shutil.copy2(path,backup/name)
    (backup/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    installed=[]
    try:
        for name in FILES:
            path=target/name
            tmp=target/(name+'.update-'+secrets.token_hex(4))
            try:
                tmp.write_bytes((ROOT/name).read_bytes())
                tmp.replace(path);installed.append(name)
            finally:tmp.unlink(missing_ok=True)
    except BaseException:
        for name in reversed(installed):
            if manifest[name] is None:(target/name).unlink(missing_ok=True)
            else:shutil.copy2(backup/name,target/name)
        raise
    print('프로그램 업데이트 완료:',target)
    print('기존 코드 백업:',backup)
    print('계정, 자체결산 app.py, data 폴더는 변경하지 않았습니다.')
    print('기존 start.bat을 실행하고 엘비데크 월별보고 → 원장 업로드를 선택하세요.')
    return backup


def choose_target():
    if len(sys.argv)>1:return sys.argv[1].strip().strip('"')
    window=None
    try:
        import tkinter as tk
        from tkinter import filedialog
        window=tk.Tk();window.withdraw();window.attributes('-topmost',True)
        path=filedialog.askopenfilename(parent=window,title='기존 프로그램의 start.bat을 선택하세요',filetypes=[('start.bat','start.bat')])
        if path:return path
    except Exception as e:print('선택창을 사용할 수 없습니다:',e)
    finally:
        if window:window.destroy()
    return input('기존 start.bat 파일을 이 창에 끌어다 놓고 Enter: ').strip().strip('"')


if __name__=='__main__':
    try:
        value=choose_target()
        if not value:raise ValueError('취소했습니다.')
        update(value)
    except Exception as e:raise SystemExit('업데이트 실패: '+str(e))
