from io import BytesIO
import importlib
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import openpyxl

import corporate_progress as progress


def project(row_id, name, natural_rate=.8, status='진행중', mode='auto', allocated=None):
    return {
        'id': row_id, 'client': '발주처', 'project': name, 'start': '2026-01-01',
        'end': '2027-12-31', 'contract': 5000, 'prior_revenue': 0,
        'current_revenue': 1000, 'prior_cost': 0, 'current_cost': 1600,
        'expected_cost_rate': natural_rate, 'trade': '건축', 'status': status,
        'prior_adjustment': 0, 'current_adjustment': 0, 'prior_unfinished': 0,
        'current_unfinished': 0, 'note': '', 'allocation_mode': mode,
        'allocated_adjustment': allocated, 'carryover_eligible': 1, 'deleted': 0,
    }


class ProgressAllocationTests(unittest.TestCase):
    def test_target_is_distributed_inside_natural_limits(self):
        rows = [project(1, 'A'), project(2, 'B')]
        plan = progress.allocate(rows, 1500, 'rate')
        self.assertEqual(plan['allocated'], 1500)
        self.assertEqual(plan['residual'], 0)
        self.assertEqual(sum(plan['allocations'].values()), 1500)
        self.assertTrue(all(0 <= value <= 1000 for value in plan['allocations'].values()))

    def test_completed_and_missing_rate_are_not_allocated(self):
        rows = [project(1, '준공공사', status='준공'), project(2, '미입력', natural_rate=0)]
        plan = progress.allocate(rows, 100, 'rate')
        self.assertEqual(plan['allocated'], 0)
        self.assertEqual(plan['residual'], 100)
        self.assertIn('준공 현장', plan['rows'][0]['allocation_reason'])
        self.assertFalse(plan['rows'][1]['rate_ready'])

    def test_fixed_amount_is_preserved_and_summary_uses_final_amount(self):
        rows = [project(1, '고정', mode='fixed', allocated=300), project(2, '자동')]
        plan = progress.allocate(rows, 800, 'rate')
        self.assertEqual(plan['allocations'][1], 300)
        self.assertEqual(plan['allocations'][2], 500)
        for row in rows:
            row['allocated_adjustment'] = plan['allocations'][row['id']]
        summary = progress.summary(rows)
        self.assertEqual(summary['current_adjustment'], 800)
        self.assertEqual(summary['expected_adjustment'], 800)

    def test_excel_is_default_and_cost_method_spreads_only_difference(self):
        rows = [project(1, 'A'), project(2, 'B')]
        rows[0]['current_adjustment']=100;rows[1]['current_adjustment']=200
        unchanged=progress.allocate(rows,600)
        self.assertEqual(unchanged['allocated'],300);self.assertEqual(unchanged['residual'],300)
        adjusted=progress.allocate(rows,600,'cost')
        self.assertEqual(adjusted['excel_total'],300);self.assertEqual(adjusted['allocated'],600)
        self.assertEqual(adjusted['residual'],0)

    def test_cost_difference_does_not_require_expected_rate(self):
        row=project(1,'원가배분',natural_rate=0);row['current_adjustment']=50
        plan=progress.allocate([row],200,'cost')
        self.assertEqual(plan['allocated'],200);self.assertEqual(plan['residual'],0)

    def test_vat_progress_difference_is_prior_plus_current_adjustment(self):
        row=project(1,'자동계산');row['prior_adjustment']=505524750;row['allocated_adjustment']=283877540
        summary=progress.summary([row],{'ledger_construction_revenue':999999999,'vat_adjustment':999999})
        self.assertEqual(summary['vat_progress_difference'],-789402290)
        self.assertNotIn('vat_adjustment',summary)
        row['prior_adjustment']=194635430;row['allocated_adjustment']=5564137100
        self.assertEqual(progress.summary([row])['vat_progress_difference'],-5758772530)

    def test_export_contains_reimportable_next_year_sheet(self):
        rows = [project(1, '이월공사')]
        with patch.dict(sys.modules, {'streamlit': SimpleNamespace()}):
            report = importlib.import_module('corporate_progress_report')
        blob = report.workbook('테스트건설', 2026, rows, 1000, {'ledger_construction_revenue':1500})
        book = openpyxl.load_workbook(BytesIO(blob), data_only=True)
        self.assertIn('2027 차기이월', book.sheetnames)
        linked={row[0]:row[1] for row in book['흐름표 연동'].iter_rows(min_row=2,values_only=True)}
        self.assertEqual(linked['전기진행율 합계'],0)
        self.assertEqual(linked['당기진행율 합계'],1000)
        self.assertEqual(linked['VAT 신고 작업진행률 수입차액 조정 후 차액'],-1000)
        sheet, parsed = progress.parse(blob, 2027, '테스트건설', '2027 차기이월')
        self.assertEqual(sheet, '2027 차기이월')
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0]['prior_revenue'], 1000)
        self.assertEqual(parsed[0]['prior_adjustment'], 1000)


if __name__ == '__main__':
    unittest.main()
