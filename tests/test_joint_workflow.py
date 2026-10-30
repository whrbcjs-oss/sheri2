from pathlib import Path
from io import BytesIO
import json,zipfile,tempfile,unittest
from unittest.mock import patch
import collaboration as shared
import joint_store as db
import joint_workflow as f
from joint_report import render,monthly_package

class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);root=Path(self.tmp.name)
        p=patch.multiple(shared,DATA=root/'data',STATE=root/'private');p.start();self.addCleanup(p.stop)
        shared.create_user(None,'admin','관리자','test-password-long-2026',bootstrap=True)
        self.token=shared.login('admin','test-password-long-2026');self.ctx=dict(token=self.token,user=shared.validate_session(self.token),snapshots={},connections=[])
        reset=shared.RUN.set(self.ctx);self.addCleanup(shared.RUN.reset,reset)
        self.c=db.connect();self.addCleanup(self.c.close)
        db.company(self.c,'O','가상 당사',{'회사구분':'당사'});db.company(self.c,'M','가상 회원사',{'회사구분':'외부 회원사'})
        self.ms=[dict(company_id=1,share=51,fee_enabled=False,fee_rate=0),dict(company_id=2,share=49,fee_enabled=True,fee_rate=3)]
        self.p=db.project(self.c,'가상 프로젝트',1,1100,1000,100,'2026-01-01','2026-12-31',self.ms);self.m=db.members(self.c,self.p)[1]['id']
    def ledger(self,month='2026-01',amount=101,company=1,blob=None):
        db.add_ledger(self.c,self.p,company,[dict(posting_date=month+'-10',allocation_month=month,account='재료비',tax_supply=amount,vat=10,invoice=0,receipt=0,voucher='V1',line='1')],blob=blob)
        return db.ledger(self.c,self.p)[-1]['id']
    def receipt(self,label,supply,month='2026-07'):
        return db.save_entry(self.c,self.p,self.m,'receipt',month+'-10',month,month,dict(label=label,supply=supply,vat=0))
    def selection(self):return {k:[] for k in f.SELECTIONS}
    def test_project_update_preserves_foreign_keys_and_ids(self):
        mid=self.m;db.save_entry(self.c,self.p,mid,'opening','2026-01-10','2026-01','2026-01',dict(arrears=1,interest=0))
        db.project(self.c,'수정 공사명',1,2200,2000,200,'2026-01-01','2026-12-31',self.ms,self.p)
        self.assertEqual(db.members(self.c,self.p)[1]['id'],mid)
        self.ledger();db.allocate(self.c,self.p)
        db.project(self.c,'원장 연결 후 공사명 수정',1,2200,2000,200,'2026-01-01','2026-12-31',self.ms,self.p)
        self.assertIsNone(self.c.execute('PRAGMA foreign_key_check').fetchone())
        with self.assertRaisesRegex(ValueError,'지분율'):db.project(self.c,'오류',1,1100,1000,100,'2026-01-01','2026-12-31',[dict(self.ms[0],share=50),dict(self.ms[1],share=50)],self.p)
    def test_fee_group_aggregates_split_receipts_and_truncates_per_stage(self):
        a=self.receipt('기성1회',126);b=self.receipt('기성2회',60);c=self.receipt('기성2회',65,'2026-12')
        gid=f.save_group(self.c,self.p,self.m,'1~2회 정산',[a,b,c],{'기성1회':{'fee_rate':3,'산재보험':1},'기성2회':{'fee_rate':3}})
        data=json.loads(f.groups(self.c,self.p,self.m)[0]['calculations'])
        self.assertEqual([db.num(x['supply']) for x in data],[126,125]);self.assertEqual(sum(db.num(x['fee']) for x in data),6)
        with self.assertRaisesRegex(ValueError,'중복'):f.save_group(self.c,self.p,self.m,'중복',[a],{})
        lid=self.ledger('2026-01');db.allocate(self.c,self.p)
        s=dict(self.selection(),receipts=[a,b,c],fees=[gid],claims=[lid]);d=f.selected_settlement(self.c,self.p,self.m,s)
        self.assertEqual(db.num(d['amounts']['received']),251);self.assertEqual(db.num(d['amounts']['fee']),6)
        self.assertEqual(len(d['receipt_entries']),3);self.assertEqual(len(d['management_entries']),2)
        self.assertNotIn('대상 기간:',render(d));self.assertIn('letter-rule',render(d,'공문'))
    def test_selection_rejects_partial_groups_cross_member_and_duplicate_runs(self):
        a=self.receipt('기성',100);g=f.save_group(self.c,self.p,self.m,'그룹',[a],{'기성':{'fee_rate':3}})
        with self.assertRaisesRegex(ValueError,'모두'):f.selected_settlement(self.c,self.p,self.m,dict(self.selection(),fees=[g]))
        s=dict(self.selection(),receipts=[a],fees=[g]);id=f.save_run(self.c,self.p,self.m,'첫 정산',s)
        f.save_run(self.c,self.p,self.m,'수정 정산명',s,id)
        with self.assertRaisesRegex(ValueError,'중복 정산'):f.save_run(self.c,self.p,self.m,'두 번째',s)
        with self.assertRaises(ValueError):f.selected_settlement(self.c,self.p,1,s)
        with self.assertRaisesRegex(ValueError,'정산 건'):f.delete_group(self.c,self.p,self.m,g)
        with self.assertRaisesRegex(ValueError,'정산 건'):db.save_entry(self.c,self.p,self.m,'receipt','2026-07-10','2026-07','2026-07',dict(label='기성',supply=200,vat=0),a)
    def test_month_close_locks_writes_and_reopen_requires_admin(self):
        lid=self.ledger()
        with self.assertRaisesRegex(ValueError,'마감해야'):f.closed_package(self.c,self.p,'2026-01')
        with self.assertRaisesRegex(ValueError,'미배분'):f.close_month(self.c,self.p,'2026-01',self.token)
        db.allocate(self.c,self.p);package=f.close_month(self.c,self.p,'2026-01',self.token)
        for action in [lambda:self.ledger(),lambda:db.revise(self.c,self.p,lid,[]),lambda:self.receipt('신규',100,'2026-01'),lambda:db.save_entry(self.c,self.p,self.m,'recovery','2026-01-10','2026-01','2026-01',dict(supply=1,vat=0))]:
            with self.assertRaisesRegex(ValueError,'마감'):action()
        shared.create_user(self.token,'user','일반 사용자','regular-password-2026');ordinary=shared.login('user','regular-password-2026')
        with self.assertRaises(PermissionError):f.reopen(self.c,self.p,'2026-01',ordinary,'사유')
        with self.assertRaises(ValueError):f.reopen(self.c,self.p,'2026-01',self.token,'')
        f.reopen(self.c,self.p,'2026-01',self.token,'입력 수정');self.assertFalse(f.is_closed(self.c,self.p,'2026-01'))
        with self.assertRaises(ValueError):f.closed_package(self.c,self.p,'2026-01')
        self.ledger(amount=200);db.allocate(self.c,self.p);new=f.close_month(self.c,self.p,'2026-01',self.token)
        self.assertEqual(len(package['ledger']),1);self.assertEqual(len(new['ledger']),2)
        self.assertEqual(self.c.execute('SELECT count(*) FROM jv_close_history').fetchone()[0],3)
    def test_closed_bundle_has_original_month_ledger_allocation_and_letter(self):
        self.ledger(blob=b'original-excel-test-bytes');db.allocate(self.c,self.p);package=f.close_month(self.c,self.p,'2026-01',self.token)
        bundle,ledger,alloc=monthly_package(package,self.m,dict(number='수동문서-1'))
        with zipfile.ZipFile(BytesIO(bundle)) as z:
            self.assertTrue({'공문.html','해당월_원장.html','원가배분내역서.html'}<=set(z.namelist()))
            self.assertEqual(z.read('업로드원본/원본_1.xlsx'),b'original-excel-test-bytes')
        self.assertIn('2026-01',ledger);self.assertIn('가상 회원사',alloc)
        frozen=json.dumps(f.closed_package(self.c,self.p,'2026-01'),sort_keys=True)
        db.company(self.c,'O','수정된 회사명',{'회사구분':'당사'},1)
        self.assertEqual(frozen,json.dumps(f.closed_package(self.c,self.p,'2026-01'),sort_keys=True))
        preview=render(package['letters'][str(self.m)],'공문',printable=False)
        self.assertNotIn('onclick="window.print()"',preview)
    def test_legacy_migration_is_idempotent_and_keeps_old_documents(self):
        old=db.save_entry(self.c,self.p,self.m,'progress','2026-01-10','2026-01','2026-01',dict(label='이전 기성',supply=1000,vat=100,fee_rate=3))
        f.migrate(self.c);f.migrate(self.c)
        self.assertEqual(len(f.source_entries(self.c,self.p,self.m,'receipt')),1);self.assertEqual(len(f.groups(self.c,self.p,self.m)),1)
        self.assertIsNotNone(self.c.execute('SELECT 1 FROM jv_entries WHERE id=?',(old,)).fetchone())
        g=f.groups(self.c,self.p,self.m)[0];f.delete_group(self.c,self.p,self.m,g['id']);f.migrate(self.c)
        self.assertEqual(len(f.source_entries(self.c,self.p,self.m,'receipt')),1);self.assertEqual(f.groups(self.c,self.p,self.m),[])

    def test_releasing_a_run_allows_correction_without_deleting_source(self):
        a=self.receipt('기성',125);g=f.save_group(self.c,self.p,self.m,'관리비',[a],{'기성':{'fee_rate':3}})
        r=f.save_run(self.c,self.p,self.m,'초안',dict(self.selection(),receipts=[a],fees=[g]))
        f.delete_run(self.c,self.p,self.m,r)
        f.save_group(self.c,self.p,self.m,'수정 관리비',[a],{'기성':{'fee_rate':4}},g)
        self.assertEqual(len(f.source_entries(self.c,self.p,self.m,'receipt')),1)
        self.assertEqual(db.num(json.loads(f.groups(self.c,self.p,self.m)[0]['calculations'])[0]['fee']),5)

    def test_legacy_multi_month_arrears_are_not_silently_omitted(self):
        db.save_entry(self.c,self.p,self.m,'opening','2026-02-10','2026-01','2026-02',dict(arrears=100,interest=1))
        with self.assertRaisesRegex(ValueError,'배분연월 하나'):f.month_letter(self.c,self.p,self.m,'2026-02')
