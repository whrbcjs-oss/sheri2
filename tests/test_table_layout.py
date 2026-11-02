import unittest
from joint_amounts import frame
from table_layout import aligned_config

class TableLayoutTests(unittest.TestCase):
    def test_total_is_adjacent_to_money_and_footer_aligned(self):
        result=frame([{'청구일':'2026-11-01','업체':'예시','공급가액':'1000','VAT':'100','공종':'철근','비고':'메모'}],['공급가액','VAT'],['공급가액','VAT'])
        self.assertEqual(list(result.columns),['청구일','업체','공급가액','VAT','합계금액','공종','비고'])
        self.assertEqual(result.iloc[-1]['공급가액'],'1,000')
        self.assertEqual(result.iloc[-1]['합계금액'],'1,100')
        config=aligned_config(result)
        for name in ['청구일','업체','공종','비고']:self.assertEqual(config[name]['alignment'],'center')
        for name in ['공급가액','VAT','합계금액']:self.assertEqual(config[name]['alignment'],'right')
    def test_edit_configuration_preserved(self):
        result=aligned_config([{'법인':'예시','지분':49}],{'법인':{'type_config':{'options':['예시']}}})
        self.assertEqual(result['법인']['alignment'],'center')
        self.assertEqual(result['법인']['type_config']['options'],['예시'])
        self.assertEqual(result['지분']['alignment'],'right')
