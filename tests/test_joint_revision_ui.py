from pathlib import Path
import unittest
import test_joint_workflow as fixtures
from streamlit.testing.v1 import AppTest
import joint_store as db

class RevisionUI(unittest.TestCase):
    def setUp(self):
        self.h=fixtures.WorkflowTests('test_project_update_preserves_foreign_keys_and_ids');self.h.setUp();self.addCleanup(self.h.doCleanups)
    def app(self,page):
        at=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'multiuser_app.py'),default_timeout=30)
        at.session_state['_auth_token']=self.h.token;at.session_state['main_system']='공동도급 관리대장';at.session_state['jv_page']=page
        return at
    def test_top_project_choice_filters_member_and_settlement_has_no_period(self):
        h=self.h
        db.company(h.c,'THIRD','다른 회원사',{'회사구분':'외부 회원사'})
        p2=db.project(h.c,'두 번째 공사',1,1100,1000,100,'2026-01-01','2026-12-31',[dict(company_id=1,share=50,fee_enabled=False,fee_rate=0),dict(company_id=3,share=50,fee_enabled=False,fee_rate=0)])
        at=self.app('원가정산서');at.session_state['jv_project']=p2;at.session_state['jv_member']=h.m;at.run()
        self.assertFalse(at.exception,str(at.exception));self.assertFalse(at.error,str(at.error))
        member=next(x for x in at.selectbox if x.label.startswith('대상 회원사'))
        self.assertNotIn('가상 회원사',member.options);self.assertIn('다른 회원사',member.options)
        self.assertFalse(any(x.label.startswith(('시작 연월','종료 연월')) for x in at.text_input))
        at.session_state['jv_page']='기성·하도급·회수';at.run();self.assertFalse(at.exception,str(at.exception))
        for title in ['공사대금 입력','관리비 및 보험료 입력','하도급 청구 및 지급현황 입력','회수내역 입력']:self.assertIn(title,[t.label for t in at.tabs])
    def test_month_close_enables_downloads_and_reopening_disables_them(self):
        h=self.h;h.ledger();db.allocate(h.c,h.p)
        at=self.app('월 마감·보고서 출력');at.run()
        next(x for x in at.text_input if x.label.startswith('배분연월')).set_value('2026-01');at.run()
        self.assertTrue(next(x for x in at.button if x.label=='보고서 출력 묶음').disabled)
        next(x for x in at.button if x.label=='선택 월 마감').click();at.run();self.assertFalse(at.exception,str(at.exception));self.assertFalse(at.error,str(at.error))
        downloads=at.get('download_button')
        self.assertTrue(any('보고서 출력 묶음' in x.proto.label and not x.proto.disabled for x in downloads))
        next(x for x in at.text_input if x.label=='마감 해제 사유').set_value('검증을 위한 해제')
        next(x for x in at.button if x.label=='관리자 마감 해제').click();at.run();self.assertFalse(at.exception,str(at.exception))
        self.assertTrue(next(x for x in at.button if x.label=='보고서 출력 묶음').disabled)
