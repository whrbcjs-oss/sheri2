from pathlib import Path
from io import BytesIO
import json
import tempfile
import unittest
from unittest.mock import patch
import openpyxl
import collaboration as shared
import joint_store as j
from joint_report import render
from joint_import import read,LABELS

class JointTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);root=Path(self.tmp.name)
        self.patcher=patch.multiple(shared,DATA=root/'data',STATE=root/'private');self.patcher.start();self.addCleanup(self.patcher.stop)
        shared.create_user(None,'testadmin','검증관리자','test-password-long-2026',bootstrap=True)
        token=shared.login('testadmin','test-password-long-2026');user=shared.validate_session(token)
        self.ctx=dict(token=token,user=user,snapshots={},connections=[])
        reset=shared.RUN.set(self.ctx);self.addCleanup(shared.RUN.reset,reset)
        self.c=j.connect();self.addCleanup(self.c.close)
        j.company(self.c,'OWNER','당사',{'대표자':'대표','주소':'주소'});j.company(self.c,'MEM','회원사',{})
        self.p=j.project(self.c,'테스트공사',1,1100,1000,100,'2026-01-01','2026-12-31',[dict(company_id=1,share=51,fee_enabled=False,fee_rate=0),dict(company_id=2,share=49,fee_enabled=True,fee_rate=3)])
        self.m=j.members(self.c,self.p)[1]
    def rec(self,**kw):
        x=dict(posting_date='2026-01-10',allocation_month='2026-01',account='재료비',tax_supply='101',vat='10',invoice='0',receipt='0',vendor='업체',description='원가',note='',voucher='2026-1',line='1');x.update(kw);return x
    def test_upload_duplicates_and_atomicity(self):
        j.add_ledger(self.c,self.p,1,[self.rec()],b'file','sample.xlsx')
        with self.assertRaisesRegex(ValueError,'중복'):j.add_ledger(self.c,self.p,1,[self.rec(voucher='new'),self.rec()],b'other')
        self.assertEqual(len(j.ledger(self.c,self.p)),1)
        with self.assertRaises(ValueError):j.add_ledger(self.c,self.p,1,[self.rec(voucher='')],b'bad')
        j.add_ledger(self.c,self.p,2,[self.rec()],b'file')
        self.assertEqual(len(j.ledger(self.c,self.p)),2)
    def test_allocations_conserve_negative_and_fractional_amounts(self):
        for amt in ['101','-101','0.91','-0.91']:
            j.add_ledger(self.c,self.p,1,[self.rec(tax_supply=amt,vat='-1.5')])
        self.assertEqual(j.allocate(self.c,self.p),4);self.assertEqual(j.allocate(self.c,self.p),0)
        al=j.allocations(self.c,self.p,'2026-01','2026-01')
        for ledger in j.ledger(self.c,self.p):
            subset=[x for x in al if x['ledger_id']==ledger['id']]
            self.assertEqual(sum(j.num(x['base']) for x in subset),j.num(ledger['tax_supply']))
            self.assertEqual(sum(j.num(x['vat']) for x in subset),j.num(ledger['vat']))
    def test_adjustment_requires_balanced_totals_and_reason(self):
        j.add_ledger(self.c,self.p,1,[self.rec()]);j.allocate(self.c,self.p)
        al=j.allocations(self.c,self.p,'2026-01','2026-01');changes=[dict(id=x['id'],base=x['base'],vat=x['vat'],reason='조정') for x in al]
        changes[0]['base']=str(j.num(changes[0]['base'])+1)
        with self.assertRaises(ValueError):j.revise(self.c,self.p,1,changes)
        changes[1]['base']=str(j.num(changes[1]['base'])-1);j.revise(self.c,self.p,1,changes)
        self.assertTrue(all(x['reason']=='조정' for x in j.allocations(self.c,self.p,'2026-01','2026-01')))
    def test_fee_truncation_and_settlement_formulas(self):
        j.add_ledger(self.c,self.p,1,[self.rec(tax_supply='1000',vat='100')]);j.add_ledger(self.c,self.p,2,[self.rec(tax_supply='200',vat='20')]);j.allocate(self.c,self.p)
        j.save_entry(self.c,self.p,self.m['id'],'progress','2026-01-20','2026-01','2026-01',dict(supply='1001',vat='100',fee_rate='3',산재보험='10',고용보험='5'))
        j.save_entry(self.c,self.p,self.m['id'],'subcontract','2026-01-20','2026-01','2026-01',dict(supply='300',vat='30',paid_supply='100',paid_vat='10'))
        j.save_entry(self.c,self.p,self.m['id'],'recovery','2026-01-20','2026-01','2026-01',dict(supply='50',vat='5'))
        d=j.settlement(self.c,self.p,self.m['id'],'2026-01','2026-01');a={k:j.num(v) for k,v in d['amounts'].items()}
        self.assertEqual(a['fee'],29);self.assertEqual(a['invested'],200)
        self.assertEqual(a['remaining'],1001-(29+10+5)+(59+30)-165-200)
        with self.c:self.c.execute('UPDATE jv_members SET fee_enabled=0 WHERE id=?',(self.m['id'],))
        d=j.settlement(self.c,self.p,self.m['id'],'2026-01','2026-01');a={k:j.num(v) for k,v in d['amounts'].items()}
        self.assertEqual(a['fee'],0);self.assertEqual(a['remaining'],a['claim']-a['recovery'])
    def test_snapshots_remain_immutable_and_html_escaped(self):
        j.add_ledger(self.c,self.p,1,[self.rec()]);d=j.settlement(self.c,self.p,self.m['id'],'2026-01','2026-01')
        with self.assertRaises(ValueError):j.snapshot(self.c,d,'공문','N1','2026-01-31',{})
        j.allocate(self.c,self.p);d=j.settlement(self.c,self.p,self.m['id'],'2026-01','2026-01')
        snap=j.snapshot(self.c,d,'공문','N1','2026-01-31',{'body':'<script>alert(1)</script>'})
        html=render(snap,'공문');self.assertNotIn('<script>',html);self.assertIn('&lt;script&gt;',html)
        before=self.c.execute('SELECT snapshot FROM jv_documents').fetchone()[0]
        j.save_entry(self.c,self.p,self.m['id'],'recovery','2026-01-31','2026-01','2026-01',{'supply':1,'vat':0})
        self.assertEqual(before,self.c.execute('SELECT snapshot FROM jv_documents').fetchone()[0])
        with self.assertRaises(Exception):j.snapshot(self.c,d,'공문','N1','2026-01-31',{})
    def test_period_boundary_is_not_silently_prorated(self):
        j.save_entry(self.c,self.p,self.m['id'],'recovery','2026-02-01','2026-01','2026-02',dict(supply=100,vat=10))
        with self.assertRaisesRegex(ValueError,'일부만'):j.settlement(self.c,self.p,self.m['id'],'2026-02','2026-02')
    def test_import_mapping_and_missing_formula_cache(self):
        w=openpyxl.Workbook();s=w.active;s.append(list(LABELS.values()));s.append(['V1',1,'2026-01-01','2026-01','원가','거래처','적요',100,10,0,0,''])
        b=BytesIO();w.save(b);mapping={k:i+1 for i,k in enumerate(LABELS)}
        parsed=read(b.getvalue(),s.title,1,mapping);self.assertEqual(parsed[0]['vat'],'10')
        s['H2']='=50+50';b=BytesIO();w.save(b)
        with self.assertRaisesRegex(ValueError,'계산값'):read(b.getvalue(),s.title,1,mapping)
    def test_audit_session_and_stale_write_guard(self):
        self.assertGreater(self.c.execute('SELECT count(*) FROM change_history').fetchone()[0],0)
        other=j.connect()
        try:
            with self.c:self.c.execute('UPDATE jv_companies SET name=? WHERE id=1',('다른 이름',))
            with self.assertRaises(shared.StaleData):j.company(other,'OTHER','다른법인',{})
        finally:other.close()
        token=shared.RUN.set(None)
        try:
            with self.assertRaises(PermissionError):j.company(self.c,'BAD','실패',{})
        finally:shared.RUN.reset(token)

    def test_backup_restore_keeps_referential_integrity_and_audit(self):
        j.add_ledger(self.c,self.p,1,[self.rec()]);j.allocate(self.c,self.p)
        backup=shared.backup_database(self.c.path);payload=backup.read_bytes()
        before=len(j.ledger(self.c,self.p))
        j.add_ledger(self.c,self.p,1,[self.rec(tax_supply=200)])
        j.restore(self.c,payload,self.ctx['token'])
        self.assertEqual(len(j.ledger(self.c,self.p)),before)
        self.assertIsNone(self.c.execute('PRAGMA foreign_key_check').fetchone())
        self.assertGreater(self.c.execute('SELECT count(*) FROM change_history').fetchone()[0],0)
