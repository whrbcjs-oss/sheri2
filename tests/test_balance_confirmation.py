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

    def test_amaranth_import_infers_side_and_groups_accounts(self):
        frame = pd.DataFrame([
            {'회사명': '대한종합건설', '계정명': '공사미수금', '차변잔액': 1000, '대변잔액': 0, '담당자': '김담당', '이메일': 'a@example.com'},
            {'회사명': '대한종합건설', '계정명': '미수금', '차변잔액': 200, '대변잔액': 0, '담당자': '김담당', '이메일': 'a@example.com'},
            {'회사명': '세림산업', '계정명': '외상매입금', '차변잔액': 0, '대변잔액': 700, '이메일': 'b@example.com'}])
        payload = BytesIO(); frame.to_excel(payload, index=False)
        parsed = store.parse_upload('잔액.xlsx', payload.getvalue())
        self.assertEqual([r['구분'] for r in parsed], ['채권', '채권', '채무'])
        store.save_counterparty_rows(self.c, '다혜건설㈜', 2025, parsed)
        groups = store.group_counterparties(self.c, '다혜건설㈜', 2025)
        first = next(g for g in groups if g['counterparty'] == '대한종합건설')
        self.assertEqual(first['total'], 1200); self.assertEqual(len(first['lines']), 2)

    def test_dispatch_reply_matching_and_print_form(self):
        store.save_counterparty_rows(self.c, '다혜건설㈜', 2025, [{
            '거래처명': '대한종합건설', '계정과목': '공사미수금', '구분': '채권', '채권채무 잔액': 1000,
            '메일주소': 'a@example.com'}])
        group = store.group_counterparties(self.c, '다혜건설㈜', 2025)[0]
        dispatch = store.prepare_dispatch(self.c, '다혜건설㈜', 2025, '2025-12-31', group)
        store.mark_sent(self.c, dispatch['id'], 'job1', '<sent@example.com>', '서버 접수')
        matched = store.match_inbox(self.c, '다혜건설㈜', 2025, [{
            'uid': '19', 'subject': 'Re: 잔액확인 ' + dispatch['confirmation_no'], 'from': 'a@example.com',
            'date_iso': '2026-01-10T09:00:00+09:00', 'in_reply_to': '<sent@example.com>', 'references': ''}])
        self.assertEqual(matched, [dispatch['confirmation_no']])
        saved = store.dispatch(self.c, dispatch['id']); self.assertEqual(saved['status'], '회신 수신')
        html = report.confirmation_html('다혜건설㈜', {'audit_firm':'한길회계법인','auditor_name':'담당자','auditor_email':'audit@example.com','auditor_phone':'02','auditor_address':'서울'}, saved, group)
        self.assertIn('CF-2025-0001'.encode(), html); self.assertIn('1,000'.encode(), html)

    def test_manual_reply_keeps_arrival_separate_from_balance_decision(self):
        store.save_counterparty_rows(self.c, '다혜건설㈜', 2025, [{
            '거래처명': '세림산업', '계정과목': '외상매입금', '구분': '채무', '채권채무 잔액': 700,
            '메일주소': 'b@example.com'}])
        group = store.group_counterparties(self.c, '다혜건설㈜', 2025)[0]
        dispatch = store.prepare_dispatch(self.c, '다혜건설㈜', 2025, '2025-12-31', group)
        store.mark_reply(self.c, dispatch['id'], '작업자 직접 등록', replied_at='2026-01-11', balance_match='차이 있음', note='상대방 잔액 650원')
        saved = store.dispatch(self.c, dispatch['id'])
        self.assertEqual(saved['status'], '차이 검토'); self.assertEqual(saved['balance_match'], '차이 있음')

    def test_amaranth_reimport_updates_only_balance_and_preserves_manual_fields(self):
        row_id = store.save_counterparty_record(self.c, '다혜건설㈜', 2025, {
            'counterparty':'대한종합건설','account':'공사미수금','balance_side':'채권','balance':100,
            'business_no':'123-45-67890','contact_name':'김담당','email':'manual@example.com','phone':'02-1111',
            'address':'서울','note':'직접 확인'})
        frame = pd.DataFrame([{'거래처명':'대한종합건설','계정과목':'공사미수금','채권잔액':999,'담당자명':'덮어쓰면 안 됨','메일주소':'wrong@example.com'}])
        payload = BytesIO(); frame.to_excel(payload,index=False)
        parsed = store.parse_upload('아마란스.xlsx',payload.getvalue())
        self.assertEqual(parsed[0]['구분'],'채권');self.assertEqual(parsed[0]['메일주소'],'')
        store.save_counterparty_rows(self.c,'다혜건설㈜',2025,parsed)
        saved = next(row for row in store.counterparties(self.c,'다혜건설㈜',2025) if row['id']==row_id)
        self.assertEqual(saved['balance'],999);self.assertEqual(saved['contact_name'],'김담당')
        self.assertEqual(saved['email'],'manual@example.com');self.assertEqual(saved['address'],'서울')

    def test_audit_firm_is_shared_and_joint_company_fields_are_reused(self):
        first=store.profile(self.c,'다혜건설㈜')
        values={'business_no':'111','address':'춘천','company_contact':'당사담당','company_phone':'033','company_email':'company@example.com',
          'audit_firm':'한길회계법인','auditor_name':'이회계사','auditor_phone':'02','auditor_email':'audit@example.com','auditor_address':'서울'}
        store.save_profile(self.c,'다혜건설㈜',values,first['version'],first['audit_version'])
        other=store.profile(self.c,'㈜효성')
        self.assertEqual(other['audit_firm'],'한길회계법인');self.assertEqual(other['auditor_email'],'audit@example.com')
        import joint_store
        joint=joint_store.connect();self.addCleanup(joint.close)
        joint_store.company(joint,'OUT1','공동업체',{'사업자등록번호':'222-33-44444','담당자':'박담당','담당자 연락처':'010-1111','전화':'02-2222','주소':'원주'})
        company_id=next(row['id'] for row in joint_store.companies(joint) if row['name']=='공동업체')
        with joint:
            project_id=joint.execute("INSERT INTO jv_projects(name,owner_id,contract,supply,vat,start,end) VALUES('공사',?,'0','0','0','2026-01-01','2026-12-31')",(company_id,)).lastrowid
            member_id=joint.execute("INSERT INTO jv_members(project_id,company_id,share,fee_enabled,fee_rate) VALUES(?,?,'100',0,'0')",(project_id,company_id)).lastrowid
            joint.execute("INSERT INTO jv_member_emails(member_id,project_id,email) VALUES(?,?,?)",(member_id,project_id,'joint@example.com'))
        reused=next(row for row in store.joint_companies() if row['name']=='공동업체')
        self.assertEqual(reused['business_no'],'222-33-44444');self.assertEqual(reused['contact_name'],'박담당')
        self.assertEqual(reused['email'],'joint@example.com');self.assertEqual(reused['phone'],'010-1111');self.assertEqual(reused['address'],'원주')


if __name__ == '__main__':
    unittest.main()
