"""Apply the collaboration upgrade locally, without uploading original company data."""
import hashlib
import json
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parent


def upgrade(archive):
    spec = json.loads((ROOT / 'app_upgrade.json').read_text(encoding='utf-8'))
    with zipfile.ZipFile(archive) as z:
        original = z.read('app.py').decode('utf-8')
        if hashlib.sha256(original.encode()).hexdigest() != spec['original_sha256']:
            raise ValueError('지원하는 원본 버전이 아닙니다. 처음 전달하신 통합결산 (3).zip을 선택하세요.')
        result = original
        for patch in reversed(spec['patches']):
            result = result[:patch['start']] + patch['replacement'] + result[patch['end']:]
        if hashlib.sha256(result.encode()).hexdigest() != spec['result_sha256']:
            raise ValueError('변환 검증에 실패했습니다. 원본은 변경하지 않았습니다.')
        outputs = {'app.py': result.encode('utf-8')}
        for name in ['joint_cost.py', 'report_templates.json', 'data/finance_2024.db', 'data/finance_2025.db']:
            outputs[name] = z.read(name)
        for name, content in outputs.items():
            target = ROOT / name
            if target.exists():
                raise ValueError(f'기존 파일을 덮어쓰지 않습니다: {name}. 새 폴더에 다운로드하여 설치하세요.')
        for name, content in outputs.items():
            target = ROOT / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
    print('공동 사용 버전 변환 완료. 원본 ZIP은 변경하지 않았습니다.')
    print('다음 단계: setup.bat 실행 → 최초 관리자 생성 → start.bat 실행')


def choose_archive(arguments=None, prompt=None):
    """Support drag/drop, a ZIP beside this script, GUI, then a console path."""
    arguments = sys.argv[1:] if arguments is None else arguments
    prompt = input if prompt is None else prompt
    if arguments:
        return arguments[0].strip().strip('"')
    local = ROOT / '통합결산 (3).zip'
    if local.is_file():
        print('같은 폴더의 원본 ZIP을 사용합니다: ' + local.name)
        return str(local)
    print('원본 ZIP 선택창을 엽니다. 다른 창 뒤에 있으면 Alt+Tab으로 확인하세요.')
    window = None
    try:
        import tkinter as tk
        from tkinter import filedialog
        window = tk.Tk()
        window.withdraw()
        window.attributes('-topmost', True)
        archive = filedialog.askopenfilename(
            parent=window, title='기존 통합결산 (3).zip을 선택하세요',
            filetypes=[('ZIP 파일', '*.zip')])
        if archive:
            return archive
    except (ImportError, RuntimeError) as e:
        print('파일 선택창을 사용할 수 없습니다: ' + str(e))
    except Exception as e:
        # TclError is unavailable when tkinter itself cannot be imported.
        if type(e).__name__ != 'TclError':
            raise
        print('파일 선택창을 사용할 수 없습니다: ' + str(e))
    finally:
        if window is not None:
            window.destroy()
    print('원본 ZIP 파일을 이 검은 창에 끌어다 놓고 Enter를 누르세요.')
    print('또는 원본 ZIP의 전체 경로를 입력하세요. 빈칸으로 Enter를 누르면 취소합니다.')
    return prompt('원본 ZIP 경로: ').strip().strip('"')


if __name__ == '__main__':
    try:
        archive = choose_archive()
        if not archive:
            raise SystemExit('파일 선택을 취소했습니다.')
        upgrade(archive)
    except (OSError, ValueError, KeyError, zipfile.BadZipFile, EOFError) as e:
        raise SystemExit('변환 실패: ' + str(e))
