from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import collaboration as shared
import ui_theme

class ThemePreferenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        state=Path(self.tmp.name)/'private'
        p=patch.object(shared,'STATE',state);p.start();self.addCleanup(p.stop)
        shared.create_user(None,'admin','관리자','test-password-2026',bootstrap=True)
        self.token=shared.login('admin','test-password-2026')

    def test_default_save_and_reload_per_user(self):
        self.assertEqual(ui_theme.load('admin'),ui_theme.DEFAULT)
        saved=ui_theme.save(self.token,{'theme':'medlink','scale':110,'row_height':50,'rounded':False})
        self.assertEqual(saved,ui_theme.load('admin'))
        self.assertEqual(saved['theme'],'medlink');self.assertFalse(saved['rounded'])

    def test_invalid_values_are_rejected(self):
        with self.assertRaises(ValueError):ui_theme.validate({'theme':'unknown','scale':100,'row_height':42,'rounded':True})
        with self.assertRaises(ValueError):ui_theme.validate({'theme':'mint','scale':125,'row_height':42,'rounded':True})

    def test_theme_css_is_scoped_and_contains_selected_style(self):
        text=ui_theme.css({'theme':'medlink','scale':90,'row_height':34,'rounded':True})
        self.assertIn('sheri2-medlink-theme',text);self.assertIn('--s2-scale:90%',text)
        self.assertIn('#root',text);self.assertNotIn('<script',text)

if __name__=='__main__':unittest.main()
