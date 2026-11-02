import base64,json,unittest
from pathlib import Path
import test_joint_workflow as fixtures
import survey_store as db
import survey_report as report
from streamlit.testing.v1 import AppTest

class SurveyTests(unittest.TestCase):
 def setUp(self):
  self.h=fixtures.WorkflowTests('test_project_update_preserves_foreign_keys_and_ids');self.h.setUp();self.addCleanup(self.h.doCleanups)
  self.c=db.connect();self.addCleanup(self.c.close)
  self.profile=dict(name='가상 법인 A',phone='033-000-0000',author='예시 담당',product1='건설공사',fax='033-000-0001')
  db.profile(self.c,1,self.profile)
 def payload(self,month='2026-12'):
  return dict(month=month,written='2026-11-02',profile=self.profile,now={k:o[1] for k,_,_,o in db.ITEMS},next={k:o[0] for k,_,_,o in db.ITEMS},factor=2,other='')
 def test_company_month_isolation_and_rename_does_not_reseed(self):
  db.save(self.c,1,'2026-12',self.payload())
  self.assertIsNone(db.draft(self.c,2,'2026-12')[0]);self.assertIsNone(db.draft(self.c,1,'2026-11')[0])
  c2=db.connect();self.addCleanup(c2.close);self.assertEqual(len(db.companies(c2)),2)
  self.assertEqual(db.company(c2,1)['name'],'가상 법인 A')
 def test_incomplete_draft_allowed_final_output_requires_answers(self):
  p=self.payload();p['now']['staff']=None
  sid=db.save(self.c,1,p['month'],p)
  with self.assertRaisesRegex(ValueError,'모든 항목'):db.issue(self.c,sid)
  self.assertFalse(db.rows(self.c,'SELECT id FROM bs_documents'))
  p=self.payload();p['factor']=13;p['other']=''
  with self.assertRaisesRegex(ValueError,'기타'):db.validate(p,True)
 def test_issue_freezes_profile_answers_and_pdf(self):
  sid=db.save(self.c,1,'2026-12',self.payload());doc=db.issue(self.c,sid);original=db.document_pdf(self.c,doc)
  self.assertTrue(original.startswith(b'%PDF'));self.assertGreater(len(original),100000)
  changed=dict(self.profile,name='수정한 법인');db.profile(self.c,1,changed)
  p=self.payload();p['now']['staff']='부족';db.save(self.c,1,'2026-12',p)
  stored=json.loads(db.document(self.c,doc)['snapshot'])
  self.assertEqual(stored['profile']['name'],'가상 법인 A');self.assertEqual(stored['now']['staff'],'적정')
  self.assertEqual(db.document_pdf(self.c,doc),original)
  self.assertEqual(db.status(self.c,sid),'수정 후 재출력 필요')
  self.assertTrue(db.rows(self.c,"SELECT id FROM change_history WHERE table_name='bs_surveys'"))
 def test_fax_requires_actual_recipient_and_is_linked_to_edition(self):
  sid=db.save(self.c,1,'2026-12',self.payload());doc=db.issue(self.c,sid)
  with self.assertRaisesRegex(ValueError,'수신'):db.record_fax(self.c,doc,'2026-11-02','','')
  db.record_fax(self.c,doc,'2026-11-02','033-000-0001','직접 전송 확인')
  self.assertEqual(db.rows(self.c,'SELECT document_id FROM bs_faxes')[0]['document_id'],doc)
  self.assertEqual(db.status(self.c,sid),'발송 기록 있음')
 def test_original_form_pdf_and_december_forecast(self):
  self.assertEqual(db.next_month('2026-12'),'2027-01')
  for bad in ['2026-1','2026-13','2026-12-01']:
   with self.assertRaises(ValueError):db.month(bad)
  im=report.image(self.payload());self.assertEqual(im.size,(2480,3508))
  # Static logo and instruction areas remain exactly equal to the original artwork.
  from PIL import Image,ImageChops
  with Image.open(report.ROOT/'assets'/'bok_nonmanufacturing_blank.png') as bg:
   for box in [(300,100,600,380),(300,1250,2150,1380),(300,3300,2150,3440)]:self.assertIsNone(ImageChops.difference(im.crop(box),bg.crop(box).convert('RGB')).getbbox())
  content=report.pdf([self.payload(),self.payload('2027-01')]);self.assertEqual(content.count(b'/Type /Page\n'),2)
 def test_ui_navigation_and_unsaved_default_answers(self):
  at=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'multiuser_app.py'),default_timeout=30)
  at.session_state['_auth_token']=self.h.token;at.session_state['main_system']='한국은행 기업경기조사';at.run()
  self.assertFalse(at.exception,str(at.exception))
  self.assertEqual([x.label for x in at.sidebar.radio][-1],'작업 화면')
  choices=[x for x in at.radio if x.label.endswith((' 동향',' 전망'))]
  self.assertEqual(len(choices),10);self.assertTrue(all(x.value is None for x in choices))
  for x in choices:x.set_value(x.options[1])
  next(x for x in at.selectbox if x.label=='경영애로요인').set_value(2)
  next(x for x in at.button if x.label=='검토 완료·저장하고 출력본 만들기').click();at.run()
  self.assertFalse(at.exception,str(at.exception));self.assertFalse(at.error,str(at.error))
  self.assertTrue(at.get('download_button'))
  next(x for x in at.sidebar.radio if x.label=='기업경기조사 업무').set_value('작성 내역·출력');at.run()
  self.assertFalse(at.exception,str(at.exception));self.assertTrue(any(x.label=='실제 수신 팩스번호' for x in at.text_input))
