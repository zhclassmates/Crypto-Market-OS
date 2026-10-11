import sqlite3
import unittest
from unittest.mock import patch
import history_growth as g


class GrowthTests(unittest.TestCase):
    def setUp(self):
        self.now=1791676800
        self.start=self.now-8*g.DAY
        self.con=sqlite3.connect(':memory:');self.con.row_factory=sqlite3.Row
        self.con.execute('CREATE TABLE daily_kline(chain,address,ts,open,high,low,close,volume,amount,fetched_at,finalized_at,PRIMARY KEY(chain,address,ts))')
        self.con.execute('CREATE TABLE market_meta(k PRIMARY KEY,v)')
        g.ensure(self.con);self.con.commit()
        self.item={'chain':'eth','address':'0x'+'a'*40,'start':self.start,'end':self.now,'token_created_at':None}
        self.guard=patch.object(g.H.sys.modules.get('market_sched') or __import__('market_sched'),'in_cooldown',return_value=False)
        self.guard.start()
    def tearDown(self):
        self.guard.stop();self.con.close()
    def fetch(self,item):
        return {'list':[{'time':self.start+i*g.DAY,'close':'2'} for i in range(8)]},self.now
    def test_classification(self):
        for n,label in [(0,'D'),(1,'C'),(2,'C'),(3,'B'),(5,'B'),(6,'A'),(7,'FULL')]:
            self.assertEqual(g.cohort(n,None,self.now),label)
        self.assertEqual(g.cohort(6,self.now-g.DAY,self.now),'E')
    def test_idle_never_displaces_due_or_soon_task(self):
        periods={('gmgn','eth'):300,('gmgn_kline','eth'):60}
        for due in (self.now-1,self.now,self.now+g.IDLE_RESERVE):
            self.assertFalse(g.idle_allowed(dict.fromkeys(periods,due),self.now,periods))
        self.assertTrue(g.idle_allowed(dict.fromkeys(periods,self.now+40),self.now,periods))
    def test_success_and_repeat_are_idempotent(self):
        result=g.attempt(self.con,self.item,self.now,self.fetch)
        self.assertEqual((result['inserted'],result['new_returns'],result['new_full']),(8,7,1))
        self.assertIn('response_json',result)
        with patch.object(self,'fetch') as fetch:
            g.attempt(self.con,self.item,self.now+3601,fetch)
            fetch.assert_not_called()
        self.assertEqual(self.con.execute('SELECT COUNT(*) FROM history_growth_requests').fetchone()[0],1)
    def test_budget_is_persistent(self):
        for i in range(g.DAILY_BUDGET):
            self.con.execute('INSERT INTO history_growth_requests(attempted_at) VALUES(?)',(self.now,))
        self.con.commit()
        with patch.object(self,'fetch') as fetch:
            self.assertEqual(g.attempt(self.con,self.item,self.now,fetch)['stopped'],'budget_or_cache')
            fetch.assert_not_called()
    def test_empty_history_cached_24_hours(self):
        g.attempt(self.con,self.item,self.now,lambda _:({'list':[]},self.now))
        self.assertEqual(self.con.execute('SELECT retry_at FROM history_growth_state').fetchone()[0],self.now+g.DAY)
        with patch.object(self,'fetch') as fetch:
            g.attempt(self.con,self.item,self.now+3600,fetch);fetch.assert_not_called()
    def test_failure_retry_bounded_and_persisted(self):
        def fail(_):raise TimeoutError('network')
        result=g.attempt(self.con,self.item,self.now,fail)
        self.assertEqual(result['outcome'],'failed')
        with patch.object(self,'fetch') as fetch:
            g.attempt(self.con,self.item,self.now+1,fetch);fetch.assert_not_called()
        g.attempt(self.con,self.item,self.now+601,self.fetch)
        self.assertEqual(g.metrics(self.con,self.now+601)['api_requests'],2)
    def test_pending_crash_lease_prevents_repeat(self):
        self.con.execute("INSERT INTO history_growth_state VALUES(?,?,?,0,'pending')",(self.item['chain'],self.item['address'],self.now+3600));self.con.commit()
        with patch.object(self,'fetch') as fetch:
            g.attempt(self.con,self.item,self.now,fetch);fetch.assert_not_called()
    def test_intraday_birth_and_wrong_identity_rejected(self):
        rows=[{'time':self.now,'close':'2'},{'time':self.start+1,'close':'2'},{'time':self.start,'close':'2','address':'wrong'}]
        result=g.attempt(self.con,self.item,self.now,lambda _:({'list':rows},self.now))
        self.assertEqual((result['inserted'],result['rejected']),(0,3))
    def test_occupied_invalid_bar_never_overwritten(self):
        self.con.execute('INSERT INTO daily_kline(chain,address,ts,close) VALUES(?,?,?,?)',(self.item['chain'],self.item['address'],self.start,'0'));self.con.commit()
        result=g.attempt(self.con,self.item,self.now,self.fetch)
        self.assertEqual(result['inserted'],7)
        self.assertEqual(self.con.execute('SELECT close FROM daily_kline WHERE ts=?',(self.start,)).fetchone()[0],'0')
    def test_cooldown_zero_requests(self):
        with patch('market_sched.in_cooldown',return_value=True),patch.object(self,'fetch') as fetch:
            self.assertEqual(g.attempt(self.con,self.item,self.now,fetch)['stopped'],'shared_cooldown');fetch.assert_not_called()
    def test_new_day_budget_resets(self):
        for i in range(g.DAILY_BUDGET):self.con.execute('INSERT INTO history_growth_requests(attempted_at) VALUES(?)',(self.now-g.DAY,))
        self.con.commit()
        self.assertEqual(g.attempt(self.con,self.item,self.now,self.fetch)['inserted'],8)
    def test_plan_gains_uses_gaps_not_price_guess(self):
        self.con.execute('CREATE TABLE token_registry(chain,address,token_created_at,first_seen_at,kline_retry_after)')
        self.con.execute('CREATE TABLE token_snapshot(chain,address,liquidity_num,price_updated_at,volume_24h)')
        self.con.execute('INSERT INTO token_registry VALUES(?,?,?,?,NULL)',('eth',self.item['address'],self.start-10*g.DAY,self.start))
        self.con.execute('INSERT INTO token_snapshot VALUES(?,?,?,?,?)',('eth',self.item['address'],30000,self.now,'100'))
        for i in range(1,8):
            b=g.H.validate_bar({'time':self.start+i*g.DAY,'close':'0.00002'},self.now,self.start,self.now)
            g.H.insert_missing(self.con,'eth',self.item['address'],[b])
        queue=g.plan(self.con,self.now)
        self.assertEqual((queue[0]['cohort'],queue[0]['potential_new_returns']),('A',1))
    def test_next_day_accumulates_without_current_day(self):
        g.attempt(self.con,self.item,self.now,self.fetch)
        tomorrow=self.now+g.DAY
        item={**self.item,'start':self.now,'end':tomorrow}
        result=g.attempt(self.con,item,tomorrow,lambda _:({'list':[{'time':self.now,'close':'3'},{'time':tomorrow,'close':'4'}]},tomorrow))
        self.assertEqual((result['inserted'],result['new_returns'],result['rejected']),(1,1,1))
    def test_metrics_zero_cost_and_efficiency(self):
        g.attempt(self.con,self.item,self.now,self.fetch)
        m=g.metrics(self.con,self.now)
        self.assertEqual((m['paid_cost'],m['request_weight'],m['returns_per_weight']),(0,2,3.5))

class TrialTests(unittest.TestCase):
    setUp=GrowthTests.setUp
    tearDown=GrowthTests.tearDown
    def test_zero_completion_old_history_stays_paused_across_day(self):
        for i in range(3):self.con.execute("INSERT INTO history_growth_requests(attempted_at,outcome) VALUES(?,'empty')",(self.now,))
        self.con.commit()
        self.assertFalse(g.trial_worth_continuing(self.con,self.now))
        self.assertFalse(g.trial_worth_continuing(self.con,self.now+g.DAY))
        self.assertTrue(g.trial_worth_continuing(self.con,self.now+g.DAY,recent=True))
    def test_boundary_only_response_is_not_invented_history(self):
        result=g.attempt(self.con,self.item,self.now,lambda _:({'list':[{'time':self.now,'close':'2'}]},self.now))
        self.assertEqual((result['outcome'],result['inserted']),('no_target_history',0))
    def test_completion_yield_allows_remaining_bounded_budget(self):
        for i in range(3):self.con.execute("INSERT INTO history_growth_requests(attempted_at,new_returns,new_full) VALUES(?,1,1)",(self.now,))
        self.con.commit()
        self.assertTrue(g.trial_worth_continuing(self.con,self.now))
    def test_finalized_receipts_unique_across_replays(self):
        g.record_prices(self.con,'eth','a',[self.start],self.now)
        g.record_prices(self.con,'eth','a',[self.start],self.now+g.DAY)
        self.assertEqual(self.con.execute('SELECT first_recorded_at FROM history_finalized_prices').fetchone()[0],self.now)


class ReplayTests(unittest.TestCase):
    setUp=GrowthTests.setUp
    tearDown=GrowthTests.tearDown
    def test_saved_pending_replays_without_network(self):
        self.con.execute('CREATE TABLE token_registry(chain,address,token_created_at)')
        payload=GrowthTests.fetch(self,self.item)[0]
        import json
        self.con.execute('INSERT INTO history_growth_requests(chain,address,start,end,attempted_at,response_json,fetched_at) VALUES(?,?,?,?,?,?,?)',
          (self.item['chain'],self.item['address'],self.start,self.now,self.now,json.dumps(payload),self.now))
        self.con.commit()
        g.replay_saved(self.con,self.now)
        g.replay_saved(self.con,self.now)
        self.assertEqual(self.con.execute('SELECT COUNT(*) FROM daily_kline').fetchone()[0],8)
        row=self.con.execute('SELECT outcome,inserted,new_returns FROM history_growth_requests').fetchone()
        self.assertEqual(tuple(row),('success',8,7))
