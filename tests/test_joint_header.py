from pathlib import Path
import unittest
from streamlit.testing.v1 import AppTest
import test_joint_workflow as fixtures
import joint_store as db

class ProjectHeaderTests(unittest.TestCase):
    def setUp(self):
        self.h=fixtures.WorkflowTests('test_project_update_preserves_foreign_keys_and_ids')
        self.h.setUp();self.addCleanup(self.h.doCleanups)
    def app(self,mode='당사주관공사',page='법인·담당자'):
        at=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'multiuser_app.py'),default_timeout=30)
        at.session_state['_auth_token']=self.h.token
        at.session_state['main_system']='공동도급 관리대장'
        at.session_state['jv_mode']=mode;at.session_state['jv_page']=page
        return at
    def check_header(self,at):
        self.assertFalse(at.exception,str(at.exception));self.assertFalse(at.error,str(at.error))
        project=next(x for x in at.selectbox if x.key=='jv_project')
        member=next(x for x in at.selectbox if x.key=='jv_member')
        self.assertTrue(any('jv-context-title' in x.value for x in at.markdown))
        self.assertTrue(any('border-left: 7px solid #009f57' in x.value for x in at.markdown))
        self.assertEqual([x.label for x in at.metric][:2],['지분율','관리비율'])
        return project,member
    def test_lead_context_preserves_selection_across_pages(self):
        h=self.h
        at=self.app();at.session_state['jv_project']=h.p;at.session_state['jv_member']=h.m;at.run()
        project,member=self.check_header(at);self.assertEqual(member.value,h.m)
        for page in ['기성·하도급·회수','원가정산서','원장 등록']:
            next(x for x in at.button if x.key=='jv_nav_'+page).click();at.run()
            project,member=self.check_header(at);self.assertEqual(project.value,h.p);self.assertEqual(member.value,h.m)
    def test_nonlead_context_preserves_project_and_member_filter(self):
        h=self.h
        nonlead=db.project(h.c,'비주관 공사',1,1100,1000,100,'2026-01-01','2026-12-31',h.ms,nonlead=True)
        owner=db.members(h.c,nonlead)[0]['id']
        at=self.app('당사비주관공사');at.run()
        project,member=self.check_header(at)
        self.assertEqual(project.options,['비주관 공사']);self.assertEqual(member.options,['가상 당사'])
        self.assertEqual(member.value,owner);self.assertFalse(db.is_nonlead(h.c,h.p))
        for page in ['원가배분·기성·하도급·지급','원가정산서','당사 투입비']:
            next(x for x in at.button if x.key=='jv_nav_'+page).click();at.run()
            project,member=self.check_header(at);self.assertEqual(project.value,nonlead);self.assertEqual(member.value,owner)
