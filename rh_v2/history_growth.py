"""Bounded history work inside the existing collector; no worker or paid API.

A persisted request reservation precedes network I/O. Recovery after a crash
waits for its lease; repeated failures and empty history have separate TTLs.
"""
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'integration/unified-market'))
import history_coverage as H

DAY = H.DAY
DAILY_BUDGET = 12
TIMEOUT = 8
IDLE_RESERVE = TIMEOUT + 3
SCHEMA = '''
CREATE TABLE IF NOT EXISTS history_finalized_prices(
 chain TEXT,address TEXT,ts INTEGER,first_recorded_at INTEGER,
 PRIMARY KEY(chain,address,ts));
CREATE TABLE IF NOT EXISTS history_growth_state(
 chain TEXT, address TEXT, retry_at INTEGER, failures INTEGER DEFAULT 0,
 outcome TEXT, PRIMARY KEY(chain,address));
CREATE TABLE IF NOT EXISTS history_growth_requests(
 id INTEGER PRIMARY KEY, chain TEXT, address TEXT, start INTEGER, end INTEGER,
 attempted_at INTEGER, outcome TEXT DEFAULT 'pending', inserted INTEGER DEFAULT 0,
 new_returns INTEGER DEFAULT 0, new_any INTEGER DEFAULT 0, new_full INTEGER DEFAULT 0,
 rejected INTEGER DEFAULT 0, error TEXT, weight INTEGER DEFAULT 2,
 response_json TEXT, fetched_at INTEGER);
CREATE TABLE IF NOT EXISTS history_incremental_requests(
 id INTEGER PRIMARY KEY,chain TEXT,address TEXT,start INTEGER,end INTEGER,
 attempted_at INTEGER,outcome TEXT DEFAULT 'pending',inserted INTEGER DEFAULT 0,
 new_returns INTEGER DEFAULT 0,new_any INTEGER DEFAULT 0,new_full INTEGER DEFAULT 0,
 rejected INTEGER DEFAULT 0,error TEXT,weight INTEGER DEFAULT 2,
 response_json TEXT,fetched_at INTEGER);
CREATE TABLE IF NOT EXISTS history_price_provenance(
 chain TEXT,address TEXT,ts INTEGER,source TEXT,task TEXT,request_id INTEGER,
 fetched_at INTEGER,PRIMARY KEY(chain,address,ts));
CREATE TABLE IF NOT EXISTS history_gap_cache(
 chain TEXT,address TEXT,start INTEGER,end INTEGER,retry_at INTEGER,outcome TEXT,
 PRIMARY KEY(chain,address,start,end));
'''


def ensure(con):
    for statement in SCHEMA.split(";"):
        if statement.strip():
            con.execute(statement)
    for table in ('history_growth_requests','history_incremental_requests'):
        columns={r[1] for r in con.execute('PRAGMA table_info('+table+')')}
        for name,kind in [('returned_dates_json','TEXT'),('target_hits','INTEGER DEFAULT 0'),('target_gaps_json','TEXT')]:
            if name not in columns:con.execute('ALTER TABLE '+table+' ADD COLUMN '+name+' '+kind)


def cohort(days, birth, now):
    if birth and birth > now - 7 * DAY:
        return 'E'
    return 'FULL' if days == 7 else 'A' if days == 6 else 'B' if days >= 3 else 'C' if days else 'D'


def idle_allowed(nxt, now, periods):
    # Every established job must remain on time, including the reserved day-K lane.
    return bool(periods) and all(nxt.get(key, 0) - now > IDLE_RESERVE for key in periods)


def plan(con, now, limit=100):
    end = now - now % DAY
    start = end - 8 * DAY
    rows = [dict(r) for r in con.execute('''SELECT r.chain,r.address,r.token_created_at,
      r.first_seen_at,s.liquidity_num,s.price_updated_at,s.volume_24h,
      COALESCE(g.retry_at,0) retry_at,COALESCE(g.failures,0) failures
      FROM token_registry r JOIN token_snapshot s USING(chain,address)
      LEFT JOIN history_growth_state g USING(chain,address)
      WHERE s.liquidity_num>=20000 AND s.price_updated_at>=?
      AND COALESCE(r.kline_retry_after,0)<=? AND COALESCE(g.retry_at,0)<=?''', (now-DAY, now, now))]
    bars = {}
    for r in con.execute('SELECT * FROM daily_kline WHERE ts>=? AND ts<?', (start,end)):
        bars.setdefault((r['chain'],r['address']), []).append(dict(r))
    result = []
    for r in rows:
        key = (r['chain'],r['address'])
        if not H.unified.chain_token(*key):
            continue
        closes = H.valid_closes(bars.get(key, []), now, r['token_created_at'])
        returns = H.return_days(closes,start,end)
        group = cohort(len(returns), r['token_created_at'], now)
        occupied = {b['ts'] for b in bars.get(key, [])}
        missing = H.missing_ranges(dict.fromkeys(occupied),start,end)
        if not missing:
            continue
        # New coins only request days on/after birth, never impossible pre-birth history.
        birth = r['token_created_at']
        if birth:
            missing = [(max(a,birth-birth%DAY),b) for a,b in missing if b>birth-birth%DAY]
        if not missing:
            continue
        left,right = missing[-1] if group == 'E' else missing[0]
        cached=con.execute('SELECT retry_at FROM history_gap_cache WHERE chain=? AND address=? AND start=? AND end=?',(*key,left,right)).fetchone()
        if cached and cached[0]>now:continue
        possible = dict(closes)
        possible.update({d:1 for d in range(left,right,DAY)})
        gain = sum(d in possible and d-DAY in possible and d not in returns for d in range(start+DAY,end,DAY))
        # These are scheduling priors, not measured provider accessibility probabilities.
        availability = {'A':.85,'B':.65,'C':.4,'D':.15,'E':.4,'FULL':0}[group] / (1+r['failures'])
        possible_days=sum(d in possible and d-DAY in possible for d in range(start+DAY,end,DAY))
        probability=availability if possible_days==7 and group!='E' else 0
        activity = math.log1p(H.number(r['volume_24h']) or 0)
        score = (20 * probability + gain * availability) * (1+activity/20) / 2
        proof = birth or r['first_seen_at']
        if group == 'D' and (not proof or proof >= end-7*DAY):
            score *= .1
        recent_single=group=='A' and left==end-DAY and right==end
        result.append({**r,'cohort':group,'start':left,'end':right,'score':score,'recent_single':recent_single,
                       'potential_new_returns':gain,'expected_new_returns':gain*availability,'completion_prior':probability,
                       'valid_days':len(returns)})
    return sorted(result,key=lambda r:(not r['recent_single'],-r['completion_prior'],-r['score'],r['chain'],r['address']))[:limit]


def attempt(con, item, now, fetch):
    """At most one request. INSERT OR IGNORE preserves occupied records."""
    import market_sched as sched
    sched.load_cooldown(con)
    if sched.in_cooldown(now):
        return {'stopped':'shared_cooldown'}
    con.execute('BEGIN IMMEDIATE')
    try:
        used = con.execute('SELECT COUNT(*) FROM history_growth_requests WHERE attempted_at>=?',(now-now%DAY,)).fetchone()[0]
        state = con.execute('SELECT retry_at FROM history_growth_state WHERE chain=? AND address=?',(item['chain'],item['address'])).fetchone()
        if used >= DAILY_BUDGET or (state and state[0]>now):
            con.rollback()
            return {'stopped':'budget_or_cache'}
        before = H.valid_closes(H.read_bars(con,item['chain'],item['address'],now-now%DAY-8*DAY,now-now%DAY),now,item.get('token_created_at'))
        if all(d in before for d in range(item['start'],item['end'],DAY)):
            con.rollback()
            return {'stopped':'already_complete'}
        cur = con.execute('INSERT INTO history_growth_requests(chain,address,start,end,attempted_at) VALUES(?,?,?,?,?)',
          (item['chain'],item['address'],item['start'],item['end'],now))
        request_id = cur.lastrowid
        con.execute("INSERT INTO history_growth_state VALUES(?,?,?,0,'pending') ON CONFLICT(chain,address) DO UPDATE SET retry_at=excluded.retry_at,outcome='pending'",(item['chain'],item['address'],now+3600))
        con.commit()
    except BaseException:
        con.rollback()
        raise
    inserted=[];rejected=0;error=None;outcome='failed';dates=[];hits=0
    try:
        payload,fetched = fetch(item)
        with con:
            con.execute('UPDATE history_growth_requests SET response_json=?,fetched_at=? WHERE id=?',(json.dumps(payload),fetched,request_id))
        rows = payload.get('list')
        if not isinstance(rows,list):
            raise ValueError('malformed_response')
        dates=returned_dates(rows)
        hits=sum(item['start']<=d<item['end'] for d in dates)
        accepted=[b for raw in rows if (b:=H.validate_bar(raw,fetched,item['start'],item['end'],item.get('token_created_at'),(item['chain'],item['address'])))]
        rejected=len(rows)-len(accepted)
        with con:
            inserted=H.insert_missing(con,item['chain'],item['address'],accepted)
            record_prices(con,item['chain'],item['address'],[b['ts'] for b in inserted],fetched)
            record_provenance(con,item['chain'],item['address'],inserted,'backfill',request_id,fetched)
        outcome='success' if inserted else 'no_new_data' if accepted else 'empty' if not rows else 'no_target_history' if all(outside_window(raw,item['start'],item['end']) for raw in rows) else 'invalid'
    except Exception as exc:
        error=type(exc).__name__+': '+str(exc)[:300]
        outcome='rate_limit' if isinstance(exc,sched.RateLimited) else 'failed'
    end=now-now%DAY;start=end-8*DAY
    # Attribution uses only our inserts, excluding concurrent collectors.
    owned={**before,**{b['ts']:float(b['close']) for b in inserted}}
    old=H.return_days(before,start,end);new=H.return_days(owned,start,end)
    state=con.execute('SELECT failures FROM history_growth_state WHERE chain=? AND address=?',(item['chain'],item['address'])).fetchone()
    failures=0 if outcome=='success' else state[0]+1
    delay=DAY if outcome in ('empty','invalid','no_target_history','no_new_data') else min(DAY,300*2**min(failures,8)) if failures else 600
    retry=max(now+delay,sched.cooldown_until()) if outcome=='rate_limit' else now+delay
    with con:
        if not inserted:
            con.execute('INSERT OR REPLACE INTO history_gap_cache VALUES(?,?,?,?,?,?)',(item['chain'],item['address'],item['start'],item['end'],retry,outcome))
        con.execute('UPDATE history_growth_requests SET returned_dates_json=?,target_hits=?,target_gaps_json=? WHERE id=?',(json.dumps(dates),hits,json.dumps([[item['start'],item['end']]]),request_id))
        con.execute('UPDATE history_growth_state SET retry_at=?,failures=?,outcome=? WHERE chain=? AND address=?',(retry,failures,outcome,item['chain'],item['address']))
        con.execute('UPDATE history_growth_requests SET outcome=?,inserted=?,new_returns=?,new_any=?,new_full=?,rejected=?,error=? WHERE id=?',
         (outcome,len(inserted),len(set(new)-set(old)),int(not old and bool(new)),int(len(old)<7 and len(new)==7),rejected,error,request_id))
    return dict(con.execute('SELECT * FROM history_growth_requests WHERE id=?',(request_id,)).fetchone())


def idle_tick(con, now, fetch=None):
    ensure(con)
    last=con.execute('SELECT MAX(attempted_at) FROM history_growth_requests').fetchone()[0]
    if last and now-last<10:
        return {'stopped':'spacing'}
    con.commit()
    replay_saved(con,now)
    replay_incremental(con,now)
    queue=plan(con,now)
    queue=[r for r in queue if trial_worth_continuing(con,now,r['recent_single'])]
    if not queue:
        return {'stopped':'no_worthwhile_candidate'}
    if fetch is None:
        fetch=fetch_standard
    return attempt(con,queue[0],now,fetch)


def fetch_standard(item):
    import market_collect as M
    import time
    chain='robinhood' if item['chain']=='rh' else item['chain']
    payload=M.gmgn(['market','kline','--chain',chain,'--address',item['address'],
              '--resolution','1d','--from',str(item['start']),'--to',str(item['end'])],timeout=TIMEOUT)
    return payload,int(time.time())


def metrics(con, now):
    rows=[dict(r) for r in con.execute('''SELECT outcome,COUNT(*) requests,SUM(weight) weight,
     SUM(inserted) prices,SUM(new_returns) returns,SUM(new_any) any_assets,SUM(new_full) full_assets,
     SUM(rejected) rejected FROM history_growth_requests WHERE attempted_at>=? GROUP BY outcome''',(now-now%DAY,))]
    requests=sum(r['requests'] for r in rows);weight=sum(r['weight'] for r in rows)
    failed=sum(r['requests'] for r in rows if r['outcome'] in ('failed','rate_limit','pending'))
    return {'utc_day':H.dt.datetime.fromtimestamp(now,H.dt.timezone.utc).date().isoformat(),
      'daily_budget':DAILY_BUDGET,'api_requests':requests,'request_weight':weight,'paid_cost':0,
      'failure_rate':failed/requests if requests else 0,
      'unproductive_rate':con.execute('SELECT COUNT(*) FROM history_growth_requests WHERE attempted_at>=? AND inserted=0',(now-now%DAY,)).fetchone()[0]/requests if requests else 0,
      'worth_expanding':requests>=3 and sum(r['full_assets'] or 0 for r in rows)>0,
      'trial_paused':not trial_worth_continuing(con,now),'new_prices':sum(r['prices'] or 0 for r in rows),
      'new_returns':sum(r['returns'] or 0 for r in rows),'new_full_assets':sum(r['full_assets'] or 0 for r in rows),
      'returns_per_weight':sum(r['returns'] or 0 for r in rows)/weight if weight else None,
      'weight_per_new_full_asset':weight/sum(r['full_assets'] or 0 for r in rows) if sum(r['full_assets'] or 0 for r in rows) else None,
      'outcomes':rows,'blocked_assets':[dict(r) for r in con.execute("SELECT outcome,COUNT(*) assets,MIN(retry_at) retry_at FROM history_growth_state WHERE retry_at>? GROUP BY outcome",(now,))]}


_queue = []
_queue_at = 0


def ranked_for_chain(con, chain, now):
    global _queue, _queue_at
    replay_saved(con,now)
    if not trial_worth_continuing(con,now):
        return None
    if now-_queue_at>=600:
        _queue=plan(con,now,100)
        _queue_at=now
    for item in list(_queue):
        if item['chain']==chain and item['cohort'] in ('A','B','C'):
            _queue.remove(item)
            retry=con.execute('SELECT kline_retry_after FROM token_registry WHERE chain=? AND address=?',(chain,item['address'])).fetchone()
            if retry and (not retry[0] or retry[0]<=now):
                return item
    return None



def record_prices(con,chain,address,days,now):
    con.executemany('INSERT OR IGNORE INTO history_finalized_prices VALUES(?,?,?,?)',
                    [(chain,address,day,now) for day in days])



def outside_window(raw,start,end):
    try:
        stamp=float(raw.get('time',raw.get('ts')))
        if stamp>=10**12:stamp/=1000
        return math.isfinite(stamp) and not start<=stamp<end
    except (AttributeError,TypeError,ValueError,OverflowError):return False


def trial_worth_continuing(con,now,recent=False):
    row=con.execute('SELECT COUNT(*),COALESCE(SUM(new_full),0) FROM history_growth_requests WHERE attempted_at>=?',(now-now%DAY,)).fetchone()
    lifetime=con.execute('SELECT COUNT(*),COALESCE(SUM(new_full),0) FROM history_growth_requests').fetchone()
    # Zero completion yield ends old-history optimization across UTC rollover.
    # A bounded recent-close trial can still validate natural accumulation.
    return row[0]<DAILY_BUDGET and (row[0]<3 or row[1]>0) and (recent or lifetime[0]<3 or lifetime[1]>0)


def returned_dates(rows):
    dates=[]
    for raw in rows:
        try:
            stamp=float(raw.get('time',raw.get('ts')))
            if stamp>=10**12:stamp/=1000
            if math.isfinite(stamp) and stamp==int(stamp):dates.append(int(stamp))
        except (AttributeError,TypeError,ValueError,OverflowError):pass
    return sorted(set(dates))


def record_provenance(con,chain,address,bars,task,request_id,fetched):
    con.executemany('INSERT OR IGNORE INTO history_price_provenance VALUES(?,?,?,?,?,?,?)',
      [(chain,address,b['ts'],'gmgn:standard:1d',task,request_id,fetched) for b in bars])


def incremental_metrics(con,now):
    row=con.execute('''SELECT COUNT(*) requests,COALESCE(SUM(weight),0) weight,
      COALESCE(SUM(inserted),0) prices,COALESCE(SUM(new_returns),0) returns,
      COALESCE(SUM(new_full),0) full_assets FROM history_incremental_requests WHERE attempted_at>=?''',(now-now%DAY,)).fetchone()
    result=dict(row);result['paid_cost']=0
    result['weight_per_new_full_asset']=result['weight']/result['full_assets'] if result['full_assets'] else None
    result['since_activation_only']=True
    return result



def replay_saved(con,now):
    """Recover a saved response locally after a crash, never spend another call."""
    for row in con.execute("SELECT * FROM history_growth_requests WHERE outcome='pending' AND response_json IS NOT NULL").fetchall():
        item=dict(row)
        if not item['fetched_at'] or item['fetched_at']>now:
            continue
        born=con.execute('SELECT token_created_at FROM token_registry WHERE chain=? AND address=?',(item['chain'],item['address'])).fetchone()
        birth=born[0] if born else None
        try:payload=json.loads(item['response_json']);raw=payload.get('list')
        except (ValueError,AttributeError):raw=None
        if not isinstance(raw,list):
            with con:con.execute("UPDATE history_growth_requests SET outcome='failed',error='saved_malformed_response' WHERE id=?",(item['id'],))
            continue
        end=now-now%DAY;start=end-8*DAY
        before=H.valid_closes(H.read_bars(con,item['chain'],item['address'],start,end),now,birth)
        bars=[b for r in raw if (b:=H.validate_bar(r,item['fetched_at'],item['start'],item['end'],birth,(item['chain'],item['address'])))]
        with con:
            inserted=H.insert_missing(con,item['chain'],item['address'],bars)
            record_prices(con,item['chain'],item['address'],[b['ts'] for b in inserted],now)
            record_provenance(con,item['chain'],item['address'],inserted,'backfill',item['id'],item['fetched_at'])
            after={**before,**{b['ts']:float(b['close']) for b in inserted}}
            old=H.return_days(before,start,end);new=H.return_days(after,start,end)
            # If inserts preceded the crash, undercount attribution rather than invent it.
            con.execute("UPDATE history_growth_requests SET outcome=?,inserted=inserted+?,new_returns=new_returns+?,new_any=?,new_full=?,rejected=? WHERE id=?",
              ('success' if bars else 'empty',len(inserted),len(set(new)-set(old)),int(not old and bool(new)),int(len(old)<7 and len(new)==7),len(raw)-len(bars),item['id']))
            con.execute('UPDATE history_growth_state SET outcome=?,retry_at=? WHERE chain=? AND address=?',
              ('success' if bars else 'empty',now+(600 if bars else DAY),item['chain'],item['address']))
            dates=returned_dates(raw)
            outcome='success' if inserted else 'no_new_data' if bars else 'no_target_history' if raw and all(outside_window(r,item['start'],item['end']) for r in raw) else 'empty' if not raw else 'invalid'
            con.execute('UPDATE history_growth_requests SET outcome=?,returned_dates_json=?,target_hits=? WHERE id=?',
              (outcome,json.dumps(dates),sum(item['start']<=d<item['end'] for d in dates),item['id']))
            if not inserted:
                con.execute('INSERT OR REPLACE INTO history_gap_cache VALUES(?,?,?,?,?,?)',(item['chain'],item['address'],item['start'],item['end'],now+DAY,outcome))


def validated_incremental(rows,chain,address,created,start,end,fetched):
    accepted=[]
    for row in rows:
        stamps=returned_dates([row])
        if not stamps or stamps[0]%DAY or not H.unified.chain_token(chain,address):continue
        if row.get('address',address)!=address:continue
        if 'chain' in row and H.unified.chain_token(row['chain'],address)!=H.unified.chain_token(chain,address):continue
        if stamps[0]>=end:
            if stamps[0]==end and H.number(row.get('close')):accepted.append(row)
        elif H.validate_bar(row,fetched,start,end,created,(chain,address)):accepted.append(row)
    return accepted


def replay_incremental(con,now):
    """Recover normal-task saved responses locally, without another network call."""
    import market_research as research
    for row in con.execute("SELECT * FROM history_incremental_requests WHERE outcome='pending' AND response_json IS NOT NULL").fetchall():
        item=dict(row);fetched=item['fetched_at']
        if not fetched or fetched>now:continue
        birth=con.execute('SELECT token_created_at FROM token_registry WHERE chain=? AND address=?',(item['chain'],item['address'])).fetchone()
        created=birth[0] if birth else None
        end=item['attempted_at']-item['attempted_at']%DAY
        start=item['attempted_at']-research.KLINE_FETCH_WINDOW_SEC
        try:raw=json.loads(item['response_json'])
        except ValueError:raw=None
        if not isinstance(raw,list):
            with con:con.execute("UPDATE history_incremental_requests SET outcome='failed',error='saved_malformed_response' WHERE id=?",(item['id'],))
            continue
        before=H.valid_closes(H.read_bars(con,item['chain'],item['address'],start,end),now,created)
        accepted=validated_incremental(raw,item['chain'],item['address'],created,start,end,fetched)
        with con:
            research.commit_kline_fetch(con,item['chain'],item['address'],accepted,fetched,True)
            after=H.valid_closes(H.read_bars(con,item['chain'],item['address'],start,end),now,created)
            added=set(after)-set(before)
            record_prices(con,item['chain'],item['address'],added,fetched)
            record_provenance(con,item['chain'],item['address'],[{'ts':d} for d in added],'incremental',item['id'],fetched)
            old=H.return_days(before,end-8*DAY,end);new=H.return_days(after,end-8*DAY,end)
            dates=returned_dates(raw)
            gaps=json.loads(item['target_gaps_json'] or '[]')
            con.execute('UPDATE history_incremental_requests SET outcome=?,inserted=?,new_returns=?,new_any=?,new_full=?,rejected=?,returned_dates_json=?,target_hits=? WHERE id=?',
              ('success' if added else 'no_new_data',len(added),len(set(new)-set(old)),int(not old and bool(new)),int(len(old)<7 and len(new)==7),len(raw)-len(accepted),json.dumps(dates),sum(any(a<=d<b for a,b in gaps) for d in dates),item['id']))
