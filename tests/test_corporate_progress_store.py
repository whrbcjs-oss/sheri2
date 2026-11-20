from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import collaboration as shared
import corporate_close_store as store


class ProgressStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.patcher = patch.multiple(shared, DATA=root/'data', STATE=root/'private')
        self.patcher.start(); self.addCleanup(self.patcher.stop)
        shared.create_user(None,'admin','관리자','test-password-long-2026',bootstrap=True)
        token=shared.login('admin','test-password-long-2026');self.context={'token':token,'user':shared.validate_session(token),'snapshots':{},'connections':[]}
        reset=shared.RUN.set(self.context);self.addCleanup(shared.RUN.reset,reset)
        self.c = store.connect(); self.addCleanup(self.c.close)
        company = store.companies(self.c)[0]
        self.case = store.case(self.c, company['id'], 2026)

    def test_import_updates_matching_project_without_deleting_manual_project(self):
        manual = {'client':'수동','project':'직접추가','start':'2026-01-01','contract':1000,
                  'expected_cost_rate':.8,'status':'진행중','allocation_mode':'auto','carryover_eligible':1}
        store.add_progress_project(self.c, self.case, manual)
        uploaded = {'project_key':'발주처|업로드|20260101','source_row':4,'client':'발주처','project':'업로드',
                    'start':'2026-01-01','end':'2027-01-01','contract':2000,'prior_revenue':0,
                    'current_revenue':500,'prior_cost':0,'current_cost':400,'expected_cost_rate':.8,
                    'trade':'건축','status':'진행중','prior_adjustment':0,'current_adjustment':0,
                    'prior_unfinished':0,'current_unfinished':0,'note':'','carryover_eligible':1}
        store.save_progress_import(self.c, self.case, 'a.xlsx', '2026', b'first', [uploaded])
        uploaded['current_revenue'] = 700
        store.save_progress_import(self.c, self.case, 'b.xlsx', '2026', b'second', [uploaded])
        rows = store.progress_projects(self.c, self.case['id'])
        self.assertEqual(len(rows), 2)
        self.assertEqual(next(r for r in rows if r['project']=='업로드')['current_revenue'], 700)
        self.assertIn('직접추가', [r['project'] for r in rows])

    def test_confirmed_open_project_rolls_forward_and_completed_is_excluded(self):
        common={'client':'발주처','start':'2026-01-01','contract':3000,'prior_revenue':100,
                'current_revenue':900,'prior_cost':80,'current_cost':720,'expected_cost_rate':.8,
                'allocation_mode':'fixed','allocated_adjustment':200,'carryover_eligible':1}
        store.add_progress_project(self.c,self.case,{**common,'project':'진행공사','status':'진행중'})
        store.add_progress_project(self.c,self.case,{**common,'project':'준공공사','status':'준공'})
        store.confirm(self.c,self.case);current=store.case(self.c,self.case['company_id'],2026,create=False)
        next_case=store.case(self.c,self.case['company_id'],2027);result=store.carryover_progress_projects(self.c,current,next_case)
        self.assertEqual(result,{'carried':1,'excluded':1})
        rows=store.progress_projects(self.c,next_case['id'])
        self.assertEqual(len(rows),1);self.assertEqual(rows[0]['project'],'진행공사')
        self.assertEqual(rows[0]['prior_revenue'],1000);self.assertEqual(rows[0]['prior_adjustment'],200)


if __name__ == '__main__':
    unittest.main()
