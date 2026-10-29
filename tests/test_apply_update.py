from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import apply_update as updater

SELECTOR='system = st.radio("프로그램 선택", ["자체결산 보고", "엘비데크 월별보고"], key="main_system")'

class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.target=Path(self.tmp.name)/'installed';self.target.mkdir()
        (self.target/'app.py').write_text('import streamlit as st\n'+SELECTOR+'\n',encoding='utf-8')
        (self.target/'multiuser_app.py').write_text('previous wrapper')
        (self.target/'start.bat').write_text('previous launcher')
        (self.target/'data').mkdir();(self.target/'data'/'finance_2026.db').write_bytes(b'financial bytes')
        (self.target/'private').mkdir();(self.target/'private'/'accounts.db').write_bytes(b'account bytes')

    def test_update_preserves_private_data_and_source(self):
        original=(self.target/'app.py').read_bytes()
        backup=updater.update(self.target/'start.bat')
        self.assertEqual((self.target/'app.py').read_bytes(),original)
        self.assertEqual((self.target/'data'/'finance_2026.db').read_bytes(),b'financial bytes')
        self.assertEqual((self.target/'private'/'accounts.db').read_bytes(),b'account bytes')
        self.assertTrue((self.target/'monthly_ledger.py').is_file())
        self.assertEqual((backup/'multiuser_app.py').read_text(),'previous wrapper')

    def test_failed_copy_rolls_back(self):
        replace=Path.replace
        def fail_monthly(path,target):
            if path.name.startswith('monthly_store.py.update-'):raise OSError('simulated failure')
            return replace(path,target)
        with patch.object(Path,'replace',fail_monthly):
            with self.assertRaises(OSError):updater.update(self.target)
        self.assertEqual((self.target/'multiuser_app.py').read_text(),'previous wrapper')
        self.assertFalse((self.target/'monthly_app.py').exists())
        self.assertFalse((self.target/'collaboration.py').exists())
        self.assertEqual((self.target/'private'/'accounts.db').read_bytes(),b'account bytes')

    def test_incompatible_source_is_not_overwritten(self):
        (self.target/'app.py').write_text('custom user source')
        with self.assertRaises(ValueError):updater.update(self.target)
        self.assertEqual((self.target/'app.py').read_text(),'custom user source')

if __name__=='__main__':unittest.main()
