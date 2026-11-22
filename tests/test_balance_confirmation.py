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


if __name__ == '__main__':
    unittest.main()
