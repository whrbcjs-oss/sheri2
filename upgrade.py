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


if __name__ == '__main__':
    try:
        if len(sys.argv) > 1:
            archive = sys.argv[1]
        else:
            import tkinter as tk
            from tkinter import filedialog
            window = tk.Tk()
            window.withdraw()
            archive = filedialog.askopenfilename(title='기존 통합결산 (3).zip을 선택하세요', filetypes=[('ZIP 파일', '*.zip')])
            window.destroy()
        if not archive:
            raise SystemExit('파일 선택을 취소했습니다.')
        upgrade(archive)
    except (OSError, ValueError, KeyError, zipfile.BadZipFile) as e:
        raise SystemExit('변환 실패: ' + str(e))
