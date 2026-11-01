import json,unittest
from decimal import Decimal
import test_joint_workflow as fixtures
import joint_store as db
import joint_workflow as f
import joint_allocation as matrix
from joint_amounts import formatted,frame
from joint_report import render,monthly_package
from streamlit.testing.v1 import AppTest
from pathlib import Path

class NovemberTests(unittest.TestCase):
    def setUp(self):
        self.h=fixtures.WorkflowTests('test_project_update_preserves_foreign_keys_and_ids');self.h.setUp();self.addCleanup(self.h.doCleanups)
    def test_amount_commas_preserve_fractions_and_totals_do_not_double_count(self):
        self.assertEqual(formatted('1234567.5000'),'1,234,567.5');self.assertEqual(formatted('-0.25'),'-0.25')
        out=frame([{'구분':'A','공급가액':'1,000','VAT':'100'},{'구분':'B','공급가액':'-200','VAT':'-20'}],['공급가액','VAT'],['공급가액','VAT'])
        self.assertEqual(list(out['합계금액']),['1,100','-220','880']);self.assertEqual(out.iloc[-1]['공급가액'],'800')
    def test_receipt_date_controls_closing_without_user_month(self):
        h=self.h;id=db.save_entry(h.c,h.p,h.m,'receipt','2026-04-12','2026-11','2026-11',dict(label='기성1',supply=100,vat=10))
        e=f.source_entries(h.c,h.p,h.m,'receipt')[0];self.assertEqual(e['period_start'],'2026-04')
        h.ledger('2026-04');db.allocate(h.c,h.p);f.close_month(h.c,h.p,'2026-04',h.token)
        with self.assertRaisesRegex(ValueError,'마감'):db.save_entry(h.c,h.p,h.m,'receipt','2026-05-01','2026-05','2026-05',dict(label='기성1',supply=200,vat=20),id)
    def test_subcontract_payment_is_preserved_but_not_used_in_new_settlement(self):
        h=self.h;sid=db.save_entry(h.c,h.p,h.m,'subcontract','2026-02-01','2026-11','2026-11',dict(supply=1000,vat=100,paid_supply=900,paid_vat=90,paid_date='2026-02-02'))
        d=f.selected_settlement(h.c,h.p,h.m,dict(h.selection(),subcontracts=[sid]))
        self.assertEqual(db.num(d['amounts']['recovery']),0);self.assertEqual(db.num(d['amounts']['claim']),1100)
        html=render(d);self.assertIn('하도급 청구내역',html);self.assertNotIn('미지급액',html);self.assertNotIn('지급일자',html)
        db.save_entry(h.c,h.p,h.m,'subcontract','2026-02-01','2026-02','2026-02',dict(supply=1200,vat=120),sid)
        self.assertEqual(json.loads(h.c.execute('SELECT payload FROM jv_entries WHERE id=?',(sid,)).fetchone()[0])['paid_supply'],900)
    def test_preview_accepts_receipts_only_fees_only_and_recoveries_only(self):
        h=self.h;r=h.receipt('기성1',1000);g=f.save_group(h.c,h.p,h.m,'보험료',[r],{'기성1':dict(fee_rate=3,산재보험=10)})
        d=f.selected_settlement(h.c,h.p,h.m,dict(h.selection(),receipts=[r]));self.assertEqual(db.num(d['amounts']['received']),1000);self.assertEqual(db.num(d['amounts']['fee']),0)
        d=f.selected_settlement(h.c,h.p,h.m,dict(h.selection(),fees=[g]));self.assertEqual(db.num(d['amounts']['received']),0);self.assertEqual(db.num(d['amounts']['deductions']),39)
        self.assertEqual(len(d['deduction_entries']),1)
        rec=db.save_entry(h.c,h.p,h.m,'recovery','2026-07-10','2026-07','2026-07',dict(supply=100,vat=10))
        d=f.selected_settlement(h.c,h.p,h.m,dict(h.selection(),recoveries=[rec]));self.assertEqual(db.num(d['amounts']['remaining']),-110)
        self.assertEqual(f.runs(h.c,h.p,h.m),[])
    def test_account_bucket_floor_and_owner_remainder(self):
        h=self.h
        for value in [1,1]:h.ledger(amount=value)
        db.allocate(h.c,h.p)
        al=db.allocations(h.c,h.p,'2026-01','2026-01');mine=[a for a in al if a['member_id']==h.m]
        self.assertEqual(sum(db.num(a['base']) for a in mine),0) # floor(2*49%)
        self.assertEqual(matrix.parts(-1,db.members(h.c,h.p),1)[h.m],-1)
        self.assertEqual(sum(matrix.parts(Decimal('0.91'),db.members(h.c,h.p),1).values()),Decimal('0.91'))
        data=matrix.matrix_data(db.projects(h.c)[0],db.members(h.c,h.p),db.ledger(h.c,h.p),al,stored=matrix.details(h.c,h.p,'2026-01'))
        html=matrix.render_matrix(data,'2026-01')
        for word in ['전월까지','세금계산서','계산서','기타증빙','누계','공제액','기성청구액','합계금액']:self.assertIn(word,html)
    def test_mixed_bucket_adjustment_conserves_each_component(self):
        h=self.h;db.add_ledger(h.c,h.p,1,[dict(posting_date='2026-01-10',allocation_month='2026-01',account='복리후생비',tax_supply=100,invoice=50,receipt=20,vat=10)])
        db.allocate(h.c,h.p);details=matrix.details(h.c,h.p,'2026-01');edits=[dict(d,reason='증빙 수정') for d in details]
        edits[0]['tax_supply']=str(db.num(edits[0]['tax_supply'])+1)
        with self.assertRaises(ValueError):matrix.revise(h.c,h.p,1,edits)
        edits[1]['tax_supply']=str(db.num(edits[1]['tax_supply'])-1);matrix.revise(h.c,h.p,1,edits)
        package=f.close_month(h.c,h.p,'2026-01',h.token);_,_,html=monthly_package(package,h.m,{})
        self.assertIn('allocation-matrix',html);self.assertNotIn('확인 필요</td>',html)
    def test_contact_separator_and_empty_preview_ui(self):
        h=self.h;d=f.month_letter(h.c,h.p,h.m,'2026-01');html=render(d,'공문',dict(contact1='담당 A',contact2='담당 B',contact_separator=' / '))
        self.assertIn('담당자 : 담당 A / 담당 B',html)
        at=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'multiuser_app.py'),default_timeout=30)
        at.session_state['_auth_token']=h.token;at.session_state['main_system']='공동도급 관리대장';at.session_state['jv_page']='원가정산서';at.run()
        self.assertFalse(at.exception,str(at.exception));self.assertFalse(at.error,str(at.error));self.assertTrue(at.get('iframe'))
    def test_money_input_formats_on_blur_and_no_payment_widgets(self):
        h=self.h;at=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'multiuser_app.py'),default_timeout=30)
        at.session_state['_auth_token']=h.token;at.session_state['main_system']='공동도급 관리대장';at.session_state['jv_page']='기성·하도급·회수';at.run()
        self.assertFalse(at.exception,str(at.exception))
        value=next(x for x in at.text_input if x.label=='수령 공급가액');value.set_value('1234567').run()
        self.assertEqual(next(x for x in at.text_input if x.label=='수령 공급가액').value,'1,234,567')
        labels=[x.label for x in at.text_input]
        self.assertNotIn('지급 공급가액',labels);self.assertNotIn('지급 VAT',labels);self.assertNotIn('지급일 (YYYY-MM-DD)',labels)

    def test_selecting_unsaved_receipt_updates_preview_without_a_run(self):
        h=self.h;h.receipt('선택 기성',1234)
        at=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'multiuser_app.py'),default_timeout=30)
        at.session_state['_auth_token']=h.token;at.session_state['main_system']='공동도급 관리대장';at.session_state['jv_page']='원가정산서';at.session_state['jv_member']=h.m;at.run()
        keys=[k for k in at.session_state.keys() if k.startswith('run_receipts_')]
        self.assertEqual(len(keys),1)
        at.session_state[keys[0]]={'edited_rows':{0:{'선택':True}},'added_rows':[],'deleted_rows':[]};at.run()
        self.assertFalse(at.exception,str(at.exception));self.assertFalse(at.error,str(at.error))
        self.assertIn('1,234',at.get('iframe')[0].proto.srcdoc)
        self.assertIn('미선택',at.get('iframe')[0].proto.srcdoc)
        self.assertEqual(f.runs(h.c,h.p,h.m),[])
