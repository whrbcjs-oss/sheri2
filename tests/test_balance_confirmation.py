from io import BytesIO
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

import collaboration as shared
import balance_confirmation_store as store
import balance_confirmation_report as report


class BalanceConfirmationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.patcher = patch.multiple(shared, DATA=root/'data', STATE=root/'private')
        self.patcher.start(); self.addCleanup(self.patcher.stop)
        shared.create_user(None, 'admin', '관리자', 'test-password-long-2026', bootstrap=True)
        token = shared.login('admin', 'test-password-long-2026')
        self.context = {'token': token, 'user': shared.validate_session(token), 'snapshots': {}, 'connections': []}
        reset = shared.RUN.set(self.context); self.addCleanup(shared.RUN.reset, reset)
        self.c = store.connect(); self.addCleanup(self.c.close)

    def test_amaranth_import_applies_selected_receivable_account(self):
        frame = pd.DataFrame([
            {'거래처명': '대한종합건설', '채권잔액': 1000},
            {'거래처명': '세림산업', '채권잔액': 700}])
        payload = BytesIO(); frame.to_excel(payload, index=False)
        parsed = store.parse_upload('잔액.xlsx', payload.getvalue(), '공사미수금')
        self.assertEqual([r['계정과목'] for r in parsed], ['공사미수금', '공사미수금'])
        self.assertEqual([r['구분'] for r in parsed], ['채권', '채권'])
        store.save_counterparty_rows(self.c, '다혜건설㈱', 2025, parsed)
        group = next(g for g in store.group_counterparties(self.c, '다혜건설㈱', 2025) if g['counterparty'] == '대한종합건설')
        self.assertEqual(group['total'], 1000); self.assertEqual(group['side'], '채권')

    def test_dispatch_reply_matching_and_print_form(self):
        store.save_counterparty_rows(self.c, '다혜건설㈱', 2025, [{'거래처명': '대한종합건설', '계정과목': '공사미수금', '채권채무 잔액': 1000, '메일주소': 'a@example.com'}])
        group = store.group_counterparties(self.c, '다혜건설㈱', 2025)[0]
        dispatch = store.prepare_dispatch(self.c, '다혜건설㈱', 2025, '2025-12-31', group)
        store.mark_sent(self.c, dispatch['id'], 'job1', '<sent@example.com>', '서버 접수')
        matched = store.match_inbox(self.c, '다혜건설㈱', 2025, [{'uid': '19', 'subject': 'Re: 잔액확인 ' + dispatch['confirmation_no'], 'from': 'a@example.com', 'date_iso': '2026-01-10T09:00:00+09:00', 'in_reply_to': '<sent@example.com>', 'references': ''}])
        self.assertEqual(matched, [dispatch['confirmation_no']])
        saved = store.dispatch(self.c, dispatch['id']); self.assertEqual(saved['status'], '회신 수신')
        html = report.confirmation_html('다혜건설㈱', {'audit_firm':'한길회계법인','auditor_name':'담당자','auditor_email':'audit@example.com','auditor_phone':'02','auditor_address':'서울'}, saved, group)
        self.assertIn('CF-2025-0001'.encode(), html); self.assertIn('1,000'.encode(), html)
        self.assertIn('채권채무조회서'.encode(), html); self.assertIn('확 인 통 지'.encode(), html)

    def test_manual_reply_keeps_arrival_separate_from_balance_decision(self):
        store.save_counterparty_rows(self.c, '다혜건설㈱', 2025, [{'거래처명': '세림산업', '계정과목': '미수금', '채권채무 잔액': 700, '메일주소': 'b@example.com'}])
        group = store.group_counterparties(self.c, '다혜건설㈱', 2025)[0]
        dispatch = store.prepare_dispatch(self.c, '다혜건설㈱', 2025, '2025-12-31', group)
        store.mark_reply(self.c, dispatch['id'], '작업자 직접 등록', replied_at='2026-01-11', balance_match='차이 있음', note='상대방 잔액 650원')
        saved = store.dispatch(self.c, dispatch['id'])
        self.assertEqual(saved['status'], '차이 검토'); self.assertEqual(saved['balance_match'], '차이 있음')

    def test_reimport_preserves_manual_fields(self):
        row_id = store.save_counterparty_record(self.c, '다혜건설㈱', 2025, {'counterparty':'대한종합건설','account':'공사미수금','balance':100,'business_no':'123-45-67890','contact_name':'김담당','email':'manual@example.com','phone':'02-1111','address':'서울','note':'직접 확인'})
        payload = BytesIO(); pd.DataFrame([{'거래처명':'대한종합건설','채권잔액':999}]).to_excel(payload,index=False)
        parsed = store.parse_upload('아마란스.xlsx', payload.getvalue(), '공사미수금')
        self.assertEqual(parsed[0]['구분'],'채권'); self.assertEqual(parsed[0]['메일주소'],'')
        store.save_counterparty_rows(self.c,'다혜건설㈱',2025,parsed)
        saved = next(row for row in store.counterparties(self.c,'다혜건설㈱',2025) if row['id']==row_id)
        self.assertEqual(saved['balance'],999); self.assertEqual(saved['contact_name'],'김담당'); self.assertEqual(saved['email'],'manual@example.com')

    def test_audit_profile_and_own_company_reuse(self):
        first=store.profile(self.c,'다혜건설㈱')
        values={'business_no':'111','representative':'홍길동','address':'춘천','company_contact':'당사담당','company_phone':'033','fax':'033-1','company_email':'company@example.com','audit_firm':'한길회계법인','auditor_name':'이회계사','auditor_phone':'02','auditor_email':'audit@example.com','auditor_address':'서울'}
        store.save_profile(self.c,'다혜건설㈱',values,first['version'],first['audit_version'])
        saved = store.profile(self.c,'다혜건설㈱')
        self.assertEqual(saved['representative'], '홍길동'); self.assertEqual(saved['fax'], '033-1')
        self.assertEqual(store.profile(self.c,'㈱효성')['audit_firm'],'한길회계법인')
        import joint_store
        joint=joint_store.connect(); self.addCleanup(joint.close)
        joint_store.company(joint,'REL1','㈱효성',{'회사구분':'관계사','사업자등록번호':'222-33-44444','대표자':'박대표','담당자':'박담당','담당자 연락처':'010-1111','전화':'02-2222','팩스':'02-3333','주소':'원주'})
        company_id=next(row['id'] for row in joint_store.companies(joint) if row['name']=='㈱효성')
        with joint:
            project_id=joint.execute("INSERT INTO jv_projects(name,owner_id,contract,supply,vat,start,end) VALUES('공사',?,'0','0','0','2026-01-01','2026-12-31')",(company_id,)).lastrowid
            member_id=joint.execute("INSERT INTO jv_members(project_id,company_id,share,fee_enabled,fee_rate) VALUES(?,?,'100',0,'0')",(project_id,company_id)).lastrowid
            joint.execute("INSERT INTO jv_member_emails(member_id,project_id,email) VALUES(?,?,?)",(member_id,project_id,'joint@example.com'))
        reused=next(row for row in store.joint_company_profiles() if row['name']=='㈱효성')
        self.assertEqual(reused['business_no'],'222-33-44444'); self.assertEqual(reused['company_contact'],'박담당')
        self.assertEqual(reused['company_email'],'joint@example.com'); self.assertEqual(reused['representative'],'박대표'); self.assertEqual(reused['fax'],'02-3333')

    def test_company_and_audit_firm_are_saved_independently(self):
        initial = store.profile(self.c, '㈱효성')
        store.save_company_profile(self.c, '㈱효성', {
            'business_no':'123','representative':'김대표','address':'서울','company_contact':'이담당',
            'company_phone':'02-1','fax':'02-2','company_email':'company@example.com'}, initial['version'])
        company_saved = store.profile(self.c, '㈱효성')
        self.assertEqual(company_saved['representative'], '김대표')
        store.save_audit_profile(self.c, {'audit_firm':'새로운회계법인','auditor_name':'박회계사',
            'auditor_phone':'02-3','auditor_email':'audit@example.com','auditor_address':'서울'}, company_saved['audit_version'])
        after = store.profile(self.c, '㈱효성')
        self.assertEqual(after['audit_firm'], '새로운회계법인')
        self.assertEqual(after['representative'], '김대표')

    def test_default_and_custom_account_types(self):
        self.assertEqual([row['name'] for row in store.account_types(self.c)], ['공사미수금', '미수금'])
        store.save_account_type(self.c, '받을어음')
        self.assertIn('받을어음', [row['name'] for row in store.account_types(self.c)])

    def test_reconnect_can_seed_through_existing_audit_trigger(self):
        # Reproduces an upgraded database: triggers already exist, while a
        # newly introduced default row must be inserted before protect().
        with self.c:
            self.c.execute("DELETE FROM bc_account_types WHERE name='공사미수금'")
        self.c.close()
        self.c = store.connect()
        self.assertIn('공사미수금', [row['name'] for row in store.account_types(self.c)])


if __name__ == '__main__':
    unittest.main()
