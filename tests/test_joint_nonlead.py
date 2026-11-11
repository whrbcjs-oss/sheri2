from pathlib import Path
import json
import unittest
from streamlit.testing.v1 import AppTest
import test_joint_workflow as fixtures
import joint_store as db
import joint_workflow as flow
from joint_report import render
from joint_nonlead import investment_data, investment_attachment

class NonleadTests(unittest.TestCase):
    def setUp(self):
        self.h=fixtures.WorkflowTests('test_project_update_preserves_foreign_keys_and_ids')
        self.h.setUp();self.addCleanup(self.h.doCleanups)
        self.c=self.h.c;self.p=self.h.p;self.m=db.members(self.c,self.p)[0]['id']
        db.set_project_mode(self.c,self.p,True)
    def allocation(self,**values):
        return db.save_entry(self.c,self.p,self.m,'allocation_receipt','2026-09-30','2026-09','2026-09',dict(supply='249,619,159',vat='21,056,276',asset=100,sub_input=200,own_input=300,label='원가대체',**values))
    def test_allocation_totals_and_settlement_link_lock(self):
        i=self.allocation();e=flow.source_entries(self.c,self.p,self.m,'allocation_receipt')[0]
        self.assertEqual(e['data']['total'],'270674835')
        sel=dict(claims=[-i]);data=flow.selected_settlement(self.c,self.p,self.m,sel)
        self.assertEqual(data['amounts']['invested'],'600');self.assertEqual(data['amounts']['claim'],'270674835')
        html=render(data);self.assertIn('원가배분 접수내역',html);self.assertIn('249,619,159',html)
        run=flow.save_run(self.c,self.p,self.m,'9월',sel)
        with self.assertRaisesRegex(ValueError,'정산 건'):flow.delete_entry(self.c,self.p,self.m,i)
        with self.assertRaisesRegex(ValueError,'중복 정산'):flow.save_run(self.c,self.p,self.m,'중복',sel)
        flow.delete_run(self.c,self.p,self.m,run);flow.delete_entry(self.c,self.p,self.m,i)
        self.assertEqual(flow.claim_rows(self.c,self.p,self.m),[])
    def test_investment_letter_uses_only_own_company_and_month(self):
        for company,month in [(1,'2026-09'),(2,'2026-09'),(1,'2026-08')]:
            db.add_ledger(self.c,self.p,company,[dict(posting_date=month+'-10',allocation_month=month,account='급여',description='<script>x</script>',tax_supply=100,vat=10,invoice=20,receipt=30)])
        recipient=db.members(self.c,self.p)[1]
        data=investment_data(self.c,self.p,recipient,'2026-09')
        self.assertEqual(data['investment_totals']['total'],'160');self.assertEqual(data['investment_totals']['invoice'],'120')
        html=render(data,'공문',{'title':'공동원가 투입내역 통보'})
        self.assertIn('공동원가 배분시 반영',html);self.assertIn('계산서',html);self.assertNotIn('기성시',html)
        self.assertNotIn('입금계좌 :',html);self.assertIn('가상 회원사',html)
        attachment=investment_attachment(data);self.assertIn('&lt;script&gt;',attachment);self.assertNotIn('<script>x',attachment)
    def test_nonlead_ui_tabs_and_letter_submenu(self):
        at=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'multiuser_app.py'),default_timeout=30)
        at.session_state['main_system']='공동도급 관리대장'
        at.session_state['_auth_token']=self.h.token
        at.session_state['jv_mode']='당사비주관공사'
        at.session_state['jv_page']='원가배분·기성·하도급·지급'
        at.run();self.assertFalse(at.exception,str(at.exception));self.assertFalse(at.error,str(at.error))
        self.assertEqual([t.label for t in at.tabs],['원가배분 접수','기성금 수금','관리비·보험료 정산','하도급 청구내역','지급내역 입력'])
        next(x for x in at.text_input if x.label=='공급가액').set_value('1,000')
        next(x for x in at.text_input if x.label=='부가세').set_value('100')
        next(x for x in at.button if x.key.startswith('alloc_') and x.label=='입력 저장').click()
        at.run();self.assertFalse(at.exception,str(at.exception));self.assertFalse(at.error,str(at.error))
        self.assertEqual(flow.source_entries(self.c,self.p,self.m,'allocation_receipt')[0]['data']['total'],'1100')
        next(x for x in at.button if x.key=='jv_nav_공문 작성').click();at.run()
        self.assertFalse(at.exception,str(at.exception));self.assertFalse(at.error,str(at.error))
        self.assertIn('공문 HTML 내려받기',[x.proto.label for x in at.get('download_button')])
        next(x for x in at.button if x.key=='jv_nav_당사 투입비').click();at.run()
        self.assertFalse(at.exception,str(at.exception))
        self.assertEqual([t.label for t in at.tabs],['원장 엑셀 등록','원가 수기입력'])
        self.assertFalse(any(x.label=='당사 투입비 하위 메뉴' for x in at.radio))
        self.assertTrue(at.get('file_uploader'))
        self.assertTrue(any(x.label=='원가 저장' for x in at.button))
        nav=[x.label for x in at.sidebar.button if x.key and x.key.startswith('jv_nav_')]
        self.assertEqual(nav,['법인·담당자','프로젝트·회원사','당사 투입비','공문 작성','원가배분·기성·하도급·지급','원가정산서','발행본·백업'])
