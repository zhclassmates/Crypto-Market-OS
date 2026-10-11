"""Read-only coverage audit, published by the established projection worker."""
import collections
import datetime as dt
import json
import sqlite3
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'rh_v2'))
import history_growth as growth
import history_api_audit


def snapshot(core_path,source_path,now):
    core=sqlite3.connect(Path(core_path).resolve().as_uri()+'?mode=ro',uri=True,timeout=30)
    core.row_factory=sqlite3.Row
    source=growth.H.connect(source_path,True)
    try:
        core.execute('BEGIN');source.execute('BEGIN')
        end=now-now%growth.DAY;start=end-7*growth.DAY
        day=lambda ts:dt.datetime.fromtimestamp(ts,dt.timezone.utc).date().isoformat()
        days=collections.defaultdict(set);source_days=collections.defaultdict(lambda:collections.defaultdict(set))
        for r in core.execute("SELECT canonical_asset_id,provider,date_utc FROM wm_unified_daily WHERE time_basis='utc_finalized' AND return_quality='VALID' AND daily_return IS NOT NULL AND date_utc>=? AND date_utc<?",(day(start),day(end))):
            days[r['canonical_asset_id']].add(r['date_utc']);source_days[r['provider']][r['canonical_asset_id']].add(r['date_utc'])
        groups=collections.Counter();unknown=0
        for r in core.execute('SELECT canonical_asset_id,token_created_at FROM wm_unified_current'):
            # Current canonical birth field is Unix seconds (no collection time substitution).
            birth=growth.H.unified.timestamp(r['token_created_at'])
            if birth is not None and not isinstance(birth,(int,float)):
                birth=int(dt.datetime.fromisoformat(str(birth).replace('Z','+00:00')).timestamp())
            groups[growth.cohort(len(days[r['canonical_asset_id']]),birth,now)]+=1
            unknown+=int(birth is None)
        denominators=collections.defaultdict(set)
        for r in core.execute('SELECT provider,canonical_asset_id FROM wm_unified_sources'):
            denominators[r['provider']].add(r['canonical_asset_id'])
        providers={}
        for p,assets in denominators.items():
            valid=source_days[p];full=sum(len(ds)==7 for ds in valid.values())
            providers[p]={'assets':len(assets),'valid_assets':len(valid),'full_assets':full,
                          'valid_coverage':len(valid)/len(assets) if assets else None,
                          'full_coverage':full/len(assets) if assets else None}
        exists=source.execute("SELECT 1 FROM sqlite_master WHERE name='history_growth_requests'").fetchone()
        costs=growth.metrics(source,now) if exists else {'api_requests':0,'paid_cost':0}
        health=[dict(r) for r in source.execute("SELECT source,SUM(attempts) attempts,SUM(successes) successes FROM source_health GROUP BY source")]
        # Count persisted, individually verified closes by UTC fetch date, not quote-day snapshots.
        prices=collections.Counter()
        for r in source.execute('SELECT d.chain,d.address,d.ts,d.close,d.fetched_at,d.finalized_at,r.token_created_at FROM daily_kline d LEFT JOIN token_registry r USING(chain,address) WHERE d.fetched_at>=?',(end,)):
            if growth.H.number(r['close']) and growth.H.final_bar(dict(r),r['token_created_at'],now):prices[day(r['fetched_at'])]+=1
        newly=collections.Counter()
        if source.execute("SELECT 1 FROM sqlite_master WHERE name='history_finalized_prices'").fetchone():
            for r in source.execute('SELECT first_recorded_at,COUNT(*) n FROM history_finalized_prices WHERE first_recorded_at>=? GROUP BY first_recorded_at',(end,)):
                newly[day(r['first_recorded_at'])]+=r['n']
        return {'checked_at':now,'window':[day(start),day(end-growth.DAY)],'cohorts':dict(groups),
          'age_unknown':unknown,'valid_assets':sum(bool(x) for x in days.values()),
          'full_assets':sum(len(x)==7 for x in days.values()),'providers':providers,
          'reliable_prices_observed_by_fetch_day':dict(prices),'new_reliable_prices_since_activation':dict(newly),'history_cost':costs,'incremental_cost':growth.incremental_metrics(source,now) if source.execute("SELECT 1 FROM sqlite_master WHERE name='history_incremental_requests'").fetchone() else {'since_activation_only':True},'gmgn_transport':history_api_audit.metrics(now),
          'collector_lifetime_task_attempts':health,
          'source_constraints':{'cg':'Reuse complete staged snapshots; intraday/near_utc_close cannot become finalized history.',
          'cmc':'Historical listings exists, plan-gated. No verified free historical entitlement; disabled, no calls.',
          'dex':'Without independent timestamp/close evidence no daily return.',
          'gmgn':'Free standard 1d only; daily idle budget 12, timeout 8s; shared cooldown; empty TTL 24h.'}}
    finally:core.close();source.close()


def publish(core,source,state,now):
    report=snapshot(core/'data/world_model_market.sqlite',source,now)
    target=state/'history-coverage.json'
    temp=target.with_suffix('.tmp');temp.write_text(json.dumps(report,indent=2));temp.replace(target)
    archive=state/'history-coverage-daily';archive.mkdir(exist_ok=True)
    daily=archive/(dt.datetime.fromtimestamp(now,dt.timezone.utc).date().isoformat()+'.json')
    temp=daily.with_suffix('.tmp');temp.write_text(json.dumps(report,indent=2));temp.replace(daily)
    return {'valid_assets':report['valid_assets'],'full_assets':report['full_assets'],'history_cost':report['history_cost']}


def explain(core_path,asset_id,now):
    """Explain a canonical asset without guessing history or source availability."""
    con=growth.H.connect(core_path,True)
    try:
        row=con.execute('SELECT * FROM wm_unified_current WHERE canonical_asset_id=?',(asset_id,)).fetchone()
        if not row:return {'asset_id':asset_id,'reason':'unknown_asset'}
        row=dict(row);end=now-now%growth.DAY
        expected=[dt.datetime.fromtimestamp(end-i*growth.DAY,dt.timezone.utc).date().isoformat() for i in range(7,0,-1)]
        observations=[dict(r) for r in con.execute('SELECT date_utc,provider,time_basis,return_quality FROM wm_unified_daily WHERE canonical_asset_id=? AND date_utc>=? AND date_utc<=?',(asset_id,expected[0],expected[-1]))]
        valid={r['date_utc'] for r in observations if r['time_basis']=='utc_finalized' and r['return_quality']=='VALID'}
        birth=growth.H.unified.timestamp(row['token_created_at'])
        group=growth.cohort(len(valid),birth,now)
        providers=[r[0] for r in con.execute('SELECT provider FROM wm_unified_sources WHERE canonical_asset_id=?',(asset_id,))]
        reasons=[]
        if group=='E':reasons.append('age_under_seven_days: pre-birth history is impossible; accumulate completed days')
        if birth is None:reasons.append('birth_unknown: first-seen is minimum age evidence only')
        if any(r['time_basis']!='utc_finalized' for r in observations):reasons.append('intraday_or_unverified_close_excluded')
        if 'gmgn' in providers:reasons.append('gmgn: only verified same-source adjacent closes count; empty/failure cache and daily budget apply')
        if 'cg' in providers:reasons.append('cg: existing staged snapshot reused, cannot synthesize a UTC close')
        if 'cmc' in providers:reasons.append('cmc: history endpoint exists; free entitlement unverified, no historical API calls')
        if 'dex' in providers:reasons.append('dex: independent timestamp and close evidence required; not a return baseline')
        return {'asset_id':asset_id,'symbol':row['symbol'],'cohort':group,'valid_days':len(valid),'missing_return_days':sorted(set(expected)-valid),
                'providers':providers,'reasons':reasons,'worth_continuing':'incremental_only_until_old_enough' if group=='E' else 'bounded_trial_if_active_and_gmgn' if 'gmgn' in providers and len(valid)<7 else 'already_complete' if len(valid)==7 else 'no_verified_free_history_path'}
    finally:con.close()
