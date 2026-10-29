import unittest
from pathlib import Path
from decimal import Decimal
import sqlite3
import tempfile
from unittest.mock import patch
import secrets
import hashlib
import collaboration as s
import monthly_store as store

class MonthlyAnnotationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        root=Path(self.tmp.name)
        for field,path in [('DATA',root/'data'),('STATE',root/'private')]:
            handle=patch.object(s,field,path);handle.start();self.addCleanup(handle.stop)
        password=secrets.token_urlsafe(24)
        s.create_user(None,'admin','검증관리자',password,bootstrap=True);self.admin=s.login('admin',password)
        s.create_user(self.admin,'staff','검증사용자',password);token=s.login('staff',password)
        self.ctx={'token':token,'user':s.validate_session(token),'snapshots':{},'connections':[]}
        reset=s.RUN.set(self.ctx);self.addCleanup(s.RUN.reset,reset)
        self.addCleanup(self.close)
        self.c=store.connect(2026)
        with self.c:
            self.c.execute('INSERT INTO monthly_imports(fiscal_year,month,source_name,source_sha256,imported_by) VALUES(2026,1,\'fixture\',\'hash\',\'admin\')')
            self.c.execute('INSERT INTO monthly_ledger(fiscal_year,month,source_row,posting_date,department,category,inflow,outflow,vat) VALUES(2026,1,4,\'2026-01-10\',\'데크거더\',\'공사수입\',\'1100\',\'0\',\'100\')')

    def close(self):
        for c in self.ctx['connections']:
            try:c.rollback();c.close()
            except sqlite3.Error:pass

    def test_memo_sticky_approvals_preserve_all_calculated_amounts(self):
        before=store.report(self.c,2026)
        store.save_annotation(self.c,2026,1,13,'row_memo','전월 노임')
        store.save_annotation(self.c,2026,1,17,'row_memo','전전월 미불\n추가 메모')
        store.save_annotation(self.c,2026,1,16,'sticky','보험료 예시 12,300\n근거 설명','일용부 보험료')
        store.save_approvals(self.c,2026,[['작성자','검토자',''],['본사 작성자','','']])
        after=store.report(self.c,2026)
        self.assertEqual([r['values'] for r in before['rows']],[r['values'] for r in after['rows']])
        self.assertEqual(next(r for r in after['rows'] if r['row']==13)['subnotes'][0],'전월 노임')
        self.assertEqual(next(r for r in after['rows'] if r['row']==17)['subnotes'][0],'전전월 미불\n추가 메모')
        self.assertEqual(after['approval_groups'][0]['roles'][1]['person'],'검토자')
        self.assertEqual(self.c.execute("SELECT actor FROM change_history WHERE table_name='monthly_annotations' ORDER BY id DESC LIMIT 1").fetchone()[0],'staff')
        self.assertEqual(len(after['annotations']),3)

    def test_blank_save_removes_annotation_and_restores_blank_signatures(self):
        store.save_annotation(self.c,2026,1,13,'row_memo','memo')
        store.save_annotation(self.c,2026,1,13,'row_memo','')
        store.save_annotation(self.c,2026,0,8,'sticky','title only','')
        store.save_annotation(self.c,2026,0,8,'sticky','','')
        self.assertEqual(store.annotations(self.c),[])
        store.save_approvals(self.c,2026,[['','',''],['','','']])
        self.assertTrue(all(not p['person'] for g in store.approvals(self.c) for p in g['roles']))

    def test_notes_survive_month_replacement(self):
        store.save_annotation(self.c,2026,1,13,'row_memo','keep')
        blob=b'synthetic replacement workbook'
        record={'year':2026,'month':1,'row':5,'date':'2026-01-11','corporation':'','project':'','vendor':'','description':'','note':'','department':'데크거더','category':'공사수입','inflow':'2200','outflow':'0','vat':'200'}
        payload={'source':'replacement fixture','sha256':hashlib.sha256(blob).hexdigest(),'records':[record]}
        context={'token':self.admin,'user':s.validate_session(self.admin),'snapshots':{},'connections':[]}
        reset=s.RUN.set(context)
        try:
            current=store.connect(2026)
            store.save_month(current,2026,1,payload,blob,self.admin)
        finally:
            for db in context['connections']:db.close()
            s.RUN.reset(reset)
        self.assertEqual(store.annotations(self.c)[0]['body'],'keep')
        self.assertEqual(store.report(self.c,2026)['rows'][0]['values'][0],2000)

    def test_notes_and_approvals_are_in_backup_and_old_backups_preserve_current(self):
        store.save_annotation(self.c,2026,1,17,'row_memo','initial')
        store.save_approvals(self.c,2026,[['initial','',''],['','','']])
        backup=s.backup_database(self.c.path)
        store.save_annotation(self.c,2026,1,17,'row_memo','changed')
        s.restore_database(self.admin,self.c.path,backup.read_bytes(),s.revision(self.c))
        self.assertEqual(store.annotations(self.c)[0]['body'],'initial')
        # Simulate a backup made before the annotation feature existed.
        with sqlite3.connect(backup) as old:
            old.execute('DROP TABLE monthly_annotations');old.execute('DROP TABLE monthly_approvals')
        s.restore_database(self.admin,self.c.path,backup.read_bytes(),s.revision(self.c))
        self.assertEqual(store.annotations(self.c)[0]['body'],'initial')
        self.assertEqual(store.approvals(self.c)[0]['roles'][0]['person'],'initial')

    def test_outdated_notes_writer_is_rejected(self):
        other=store.connect(2026)
        store.save_annotation(self.c,2026,1,13,'row_memo','first')
        with self.assertRaises(s.StaleData):store.save_annotation(other,2026,1,13,'row_memo','stale')
        self.assertEqual(store.annotations(self.c)[0]['body'],'first')

    def test_invalid_locations_and_untrusted_html_are_handled(self):
        with self.assertRaises(ValueError):store.save_annotation(self.c,2026,1,8,'row_memo','wrong location')
        with self.assertRaises(ValueError):store.save_annotation(self.c,2026,13,16,'sticky','wrong month')
        with self.assertRaises(ValueError):store.save_annotation(self.c,2025,1,13,'row_memo','wrong year')
        store.save_annotation(self.c,2026,1,16,'sticky','</script><script>alert(1)</script>','<img src=x>')
        from monthly_report_preview import render_html
        html=render_html(store.report(self.c,2026))
        self.assertNotIn('"body": "</script>',html)

    def test_ui_regular_user_can_save_all_annotation_types(self):
        from streamlit.testing.v1 import AppTest
        root=Path(__file__).resolve().parents[1]
        at=AppTest.from_file(str(root/'multiuser_app.py'),default_timeout=30)
        at.session_state['_auth_token']=self.ctx['token']
        at.session_state['main_system']='엘비데크 월별보고'
        at.session_state['lb_monthly_page']='보고서 메모·결재'
        at.run();self.assertFalse(at.exception,str(at.exception))
        next(w for w in at.text_area if w.label=='금액 아래에 표시할 메모').set_value('전월 노임')
        next(w for w in at.button if w.label=='월별 메모 저장').click().run()
        self.assertFalse(at.exception,str(at.exception))
        self.assertEqual(store.annotations(self.c)[0]['body'],'전월 노임')
        next(w for w in at.selectbox if w.label=='포스트잇 월').set_value(1).run()
        next(w for w in at.selectbox if w.label=='포스트잇 항목').set_value(16).run()
        next(w for w in at.text_input if w.label=='포스트잇 제목').set_value('보험료 메모')
        next(w for w in at.text_area if w.label=='포스트잇 내용').set_value('설명 예시 12,300')
        next(w for w in at.button if w.label=='포스트잇 저장').click().run()
        self.assertFalse(at.exception,str(at.exception))
        self.assertTrue(any(a['kind']=='sticky' and a['body']=='설명 예시 12,300' for a in store.annotations(self.c)))
        next(w for w in at.text_input if w.key=='lb_approver_2026_0_0').set_value('작성자')
        next(w for w in at.button if w.label=='결재란 저장').click().run()
        self.assertFalse(at.exception,str(at.exception))
        self.assertEqual(store.approvals(self.c)[0]['roles'][0]['person'],'작성자')

if __name__=='__main__':unittest.main()
