import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import sys

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('upgrade',ROOT/'upgrade.py')
u=importlib.util.module_from_spec(spec)
spec.loader.exec_module(u)

class UpgradeSelectionTests(unittest.TestCase):
    def test_dragged_quoted_path(self):
        self.assertEqual(u.choose_archive(['"C:\\내 문서\\통합결산 (3).zip"']), 'C:\\내 문서\\통합결산 (3).zip')

    def test_local_original_needs_no_gui(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(u,'ROOT',Path(folder)):
            target=Path(folder)/'통합결산 (3).zip'
            target.touch()
            with patch.dict(sys.modules,{'tkinter':None}):
                self.assertEqual(u.choose_archive([]),str(target))

    def test_missing_gui_uses_console_path(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(u,'ROOT',Path(folder)):
            with patch.dict(sys.modules,{'tkinter':None}):
                self.assertEqual(u.choose_archive([],lambda message:'"C:\\원본 (3).zip"'),'C:\\원본 (3).zip')

    def test_console_cancel(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(u,'ROOT',Path(folder)):
            with patch.dict(sys.modules,{'tkinter':None}):
                self.assertEqual(u.choose_archive([],lambda message:''),'')

if __name__=='__main__':unittest.main()
