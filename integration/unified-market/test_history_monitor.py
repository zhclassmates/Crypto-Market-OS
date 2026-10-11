import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import history_monitor as m
import history_api_audit as api


class MonitorTests(unittest.TestCase):
    def test_api_receipts_count_started_not_double_completions(self):
        with tempfile.TemporaryDirectory() as folder,patch.object(api,'PATH',Path(folder)/'events'),patch.object(api.time,'time',return_value=1791676800):
            ident,route=api.start(['market','kline','--address','secret-free'])
            api.event(ident,route,'success');api.event(ident,route,'success')
            other,route=api.start(['market','trending']);api.event(other,route,'provider_error')
            result=api.metrics(1791676800)
            self.assertEqual(result['requests'],2)
            self.assertEqual(result['routes']['market kline']['failure_rate'],0)
            self.assertEqual(result['routes']['market trending']['failure_rate'],1)
            self.assertNotIn('secret-free',api.PATH.read_text())
    def test_pending_receipt_is_unknown_not_success(self):
        with tempfile.TemporaryDirectory() as folder,patch.object(api,'PATH',Path(folder)/'events'),patch.object(api.time,'time',return_value=1791676800):
            api.start(['market','kline'])
            result=api.metrics(1791676800)
            self.assertEqual(result['routes']['market kline']['pending'],1)
    def test_explain_intraday_and_young(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'db';con=sqlite3.connect(path)
            con.execute('CREATE TABLE wm_unified_current(canonical_asset_id,symbol,token_created_at)')
            con.execute('CREATE TABLE wm_unified_sources(provider,canonical_asset_id)')
            con.execute('CREATE TABLE wm_unified_daily(canonical_asset_id,date_utc,provider,time_basis,return_quality)')
            con.execute("INSERT INTO wm_unified_current VALUES('one','ONE','2026-10-10T00:00:00Z')")
            con.execute("INSERT INTO wm_unified_sources VALUES('dex','one')")
            con.execute("INSERT INTO wm_unified_daily VALUES('one','2026-10-10','dex','intraday','INTRADAY')")
            con.commit();con.close()
            r=m.explain(path,'one',1791676800)
            self.assertEqual((r['cohort'],r['valid_days']),('E',0))
            self.assertEqual(len(r['missing_return_days']),7)
            self.assertIn('intraday_or_unverified_close_excluded',r['reasons'])
            self.assertEqual(r['worth_continuing'],'incremental_only_until_old_enough')
    def test_unknown_asset(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'db';con=sqlite3.connect(path);con.execute('CREATE TABLE wm_unified_current(canonical_asset_id)');con.close()
            self.assertEqual(m.explain(path,'unknown',1791676800)['reason'],'unknown_asset')
