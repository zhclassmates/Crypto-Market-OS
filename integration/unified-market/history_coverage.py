"""Bounded, resumable UTC history recovery. Never replaces an existing candle.

Uses the established GMGN free standard 1d CLI route, at most one request per
missing contiguous interval. No CMC paid history or synthetic daily prices.
"""
import argparse
import datetime as dt
import hashlib
import fcntl
import json
import math
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
CORE=Path(json.loads((Path(__file__).parent/'install-manifest.json').read_text())['target'])
sys.path.insert(0,str(Path(__file__).parent))
import unified_market as unified
from unified_onchain import final_bar
DAY=86400


def number(value):
 try:
  value=float(value)
  return value if math.isfinite(value) and value>0 else None
 except (ValueError,TypeError,OverflowError):return None


def validate_bar(raw, fetched, start, end, created=None, identity=None):
 """Exact UTC aligned source time. Never floor an arbitrary intraday stamp."""
 if not isinstance(raw,dict):return None
 if identity and (('address' in raw and raw['address']!=identity[1]) or ('chain' in raw and unified.chain_token(raw['chain'],identity[1])!=unified.chain_token(*identity))):return None
 try:
  opened=float(raw.get('time',raw.get('ts')))
  if opened>=10**12:opened/=1000
  if not math.isfinite(opened) or opened!=int(opened):return None
  opened=int(opened)
 except (TypeError,ValueError,OverflowError):return None
 close=number(raw.get('close'))
 if not close or not start<=opened<end:return None
 if not final_bar({'ts':opened,'fetched_at':fetched},created,fetched):return None
 low,high=number(raw.get('low')),number(raw.get('high'))
 if low is not None and close<low:return None
 if high is not None and close>high:return None
 return {'ts':opened,'close':str(raw['close']),'open':raw.get('open'),'high':raw.get('high'),'low':raw.get('low'),
         'volume':raw.get('volume'),'amount':raw.get('amount'),'fetched_at':fetched,'finalized_at':fetched}


def valid_closes(rows, now, created=None):
 return {int(r['ts']):float(r['close']) for r in rows if number(r.get('close')) and final_bar(r,created,now)}


def return_days(closes,start,end):
 out={}
 for day in range(start+DAY,end,DAY):
  old,new=closes.get(day-DAY),closes.get(day)
  if old is not None and new is not None and old>=1e-8:
   ratio=new/old-1
   if math.isfinite(ratio) and abs(ratio)<=50:out[day]=ratio*100
 return out


def missing_ranges(closes,start,end):
 ranges=[]
 for day in range(start,end,DAY):
  if day in closes:continue
  if ranges and ranges[-1][1]==day:ranges[-1]=(ranges[-1][0],day+DAY)
  else:ranges.append((day,day+DAY))
 return ranges


def read_bars(db,chain,address,start,end):
 return [dict(r) for r in db.execute('SELECT * FROM daily_kline WHERE chain=? AND address=? AND ts>=? AND ts<?',(chain,address,start,end))]


def insert_missing(db,chain,address,bars):
 inserted=[]
 for r in bars:
  changed=db.execute('INSERT OR IGNORE INTO daily_kline(chain,address,ts,open,high,low,close,volume,amount,fetched_at,finalized_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
   (chain,address,r['ts'],r['open'],r['high'],r['low'],r['close'],r['volume'],r['amount'],r['fetched_at'],r['finalized_at'])).rowcount
  if changed:inserted.append(r)
 return inserted


def connect(path, readonly=False):
 c=sqlite3.connect(Path(path).resolve().as_uri()+('?mode=ro' if readonly else ''),uri=True,timeout=30)
 c.row_factory=sqlite3.Row
 return c


def audit(core, source, now):
 end=now-now%DAY;start=end-8*DAY;cutoff=start+DAY
 current={r['canonical_asset_id']:dict(r) for r in core.execute('SELECT canonical_asset_id,token_created_at,first_seen_utc FROM wm_unified_current')}
 mapping={(r['chain_id'],r['contract_address']):r['canonical_asset_id'] for r in core.execute('SELECT * FROM wm_unified_chain_tokens')}
 registry=[dict(r) for r in source.execute('SELECT chain,address,first_seen_at,token_created_at FROM token_registry')]
 old=set();young=set();unknown=set()
 for r in registry:
  ident=unified.chain_token(r['chain'],r['address'])
  asset=mapping.get(ident)
  if not asset:continue
  created=r['token_created_at'];proof=created or r['first_seen_at']
  if created and created>=cutoff:young.add(asset)
  elif proof and proof<cutoff:old.add(asset)
  else:unknown.add(asset)
 old-=young;unknown-=old|young
 bars=[dict(r) for r in source.execute('SELECT chain,address,ts,close,fetched_at,finalized_at FROM daily_kline WHERE ts>=? AND ts<?',(start,end))]
 births={(r['chain'],r['address']):r['token_created_at'] for r in registry}
 bytoken={}
 for row in bars:bytoken.setdefault((row['chain'],row['address']),[]).append(row)
 recovered=set();local_closes=set();local_pairs=set()
 for token,rows in bytoken.items():
  asset=mapping.get(unified.chain_token(*token))
  if not asset:continue
  closes=valid_closes(rows,now,births.get(token))
  if closes:local_closes.add(asset)
  if return_days(closes,start,end):local_pairs.add(asset)
  if any(day<cutoff for day in closes):recovered.add(asset)
 old|=recovered-young;unknown=set(current)-old-young
 rows=core.execute("SELECT canonical_asset_id,date_utc,provider FROM wm_unified_daily WHERE time_basis='utc_finalized' AND return_quality='VALID' AND daily_return IS NOT NULL AND date_utc>=? AND date_utc<?",(dt.datetime.fromtimestamp(cutoff,dt.timezone.utc).date().isoformat(),dt.datetime.fromtimestamp(end,dt.timezone.utc).date().isoformat())).fetchall()
 days={};byprovider={}
 for r in rows:
  days.setdefault(r['canonical_asset_id'],set()).add(r['date_utc']);byprovider.setdefault(r['provider'],set()).add(r['canonical_asset_id'])
 valid=set(days);full={asset for asset,dd in days.items() if len(dd)==7}
 observed=local_closes|set(r['canonical_asset_id'] for r in core.execute("SELECT DISTINCT canonical_asset_id FROM wm_unified_daily WHERE time_basis='utc_finalized' AND date_utc>=? AND date_utc<?",(dt.datetime.fromtimestamp(start,dt.timezone.utc).date().isoformat(),dt.datetime.fromtimestamp(end,dt.timezone.utc).date().isoformat())))
 def cohort(ids):return {'assets':len(ids),'any_valid_return':len(ids&valid),'seven_valid_returns':len(ids&full),'any_rate':len(ids&valid)/len(ids) if ids else None,'seven_rate':len(ids&full)/len(ids) if ids else None}
 return {'window_start':dt.datetime.fromtimestamp(cutoff,dt.timezone.utc).date().isoformat(),'window_end':dt.datetime.fromtimestamp(end-DAY,dt.timezone.utc).date().isoformat(),
  'baseline_day':dt.datetime.fromtimestamp(start,dt.timezone.utc).date().isoformat(),'all':cohort(set(current)),
  'age_sufficient':cohort(old),'age_sufficient_with_local_history':cohort(old&observed),'confirmed_young':len(young),'age_unknown':len(unknown),'locally_accessible_history':cohort(observed),
  'source_valid_assets':{p:len(ids) for p,ids in byprovider.items()},'source_observations':[dict(r) for r in core.execute('SELECT provider,time_basis,COUNT(*) records,COUNT(DISTINCT provider_id) assets,MIN(date_utc) first_date,MAX(date_utc) last_date FROM wm_market_observations GROUP BY provider,time_basis')],
  'gmgn_local_finalized_price_assets':len(local_closes),'gmgn_local_pair_assets':len(local_pairs),'raw_bar_rows_window':len(bars)}


def candidates(source,now,limit):
 end=now-now%DAY;start=end-8*DAY;cutoff=start+DAY
 rows=source.execute('''SELECT r.chain,r.address,r.token_created_at,r.first_seen_at,s.liquidity_num,s.price_updated_at
 FROM token_registry r JOIN token_snapshot s USING(chain,address)
 WHERE (r.token_created_at<? OR r.first_seen_at<?) AND (r.token_created_at IS NULL OR r.token_created_at<?)
 AND s.liquidity_num>=20000 AND NOT EXISTS(SELECT 1 FROM daily_kline d WHERE d.chain=r.chain AND d.address=r.address AND d.ts>=? AND d.ts<?)
 ORDER BY (s.price_updated_at>=?) DESC,s.liquidity_num DESC,r.chain,r.address''',(cutoff,cutoff,cutoff,start,end,now-DAY)).fetchall()
 queues={}
 for r in rows:
  if unified.chain_token(r['chain'],r['address']):queues.setdefault(r['chain'],[]).append(dict(r))
 chosen=[]
 while len(chosen)<limit and any(queues.values()):
  for chain in sorted(queues):
   if queues[chain] and len(chosen)<limit:chosen.append(queues[chain].pop(0))
 return chosen


def manifest_candidates(source,path,limit):
 """Target only previously confirmed identities, using authoritative registry birth data."""
 entries=json.loads(Path(path).read_text())
 if not isinstance(entries,list):raise ValueError('Asset manifest must be a list')
 selected=[];seen=set()
 for entry in entries:
  key=(entry['chain'],entry['address'])
  if key in seen:continue
  seen.add(key)
  if not unified.chain_token(*key):raise ValueError('Unrecognizable asset identity')
  row=source.execute('SELECT chain,address,token_created_at,first_seen_at FROM token_registry WHERE chain=? AND address=?',key).fetchone()
  if not row:raise ValueError('Asset is absent from the existing registry')
  selected.append(dict(row))
  if len(selected)>=limit:break
 return selected


def recover_archive(core, row,start,end,now):
 chain,address=unified.chain_token(row['chain'],row['address']);sid=chain+':'+address
 recovered={}
 for archived in core.execute("SELECT payload_json FROM wm_unified_raw_versions WHERE provider='gmgn' AND provider_id=? AND date_utc>=? AND date_utc<?",(sid,dt.datetime.fromtimestamp(start,dt.timezone.utc).date().isoformat(),dt.datetime.fromtimestamp(end,dt.timezone.utc).date().isoformat())):
  payload=json.loads(archived[0]);raw=payload.get('raw_bar')
  if payload.get('raw_chain')!=row['chain'] or payload.get('raw_address')!=row['address'] or payload.get('time_basis')!='utc_finalized' or not raw:continue
  fetched=max(raw.get('fetched_at') or 0,raw.get('finalized_at') or 0)
  bar=validate_bar(raw,fetched,start,end,row.get('token_created_at')) if fetched<=now else None
  if bar and (bar['ts'] not in recovered or fetched>recovered[bar['ts']]['fetched_at']):recovered[bar['ts']]=bar
 return list(recovered.values())


def _sample(reportdir,limit,max_requests,network,delay=10,assets_file=None):
 reportdir.mkdir(exist_ok=True,parents=True);now=int(time.time());source=connect(ROOT/'rh_v2/market.sqlite');core=connect(CORE/'data/world_model_market.sqlite',True)
 planfile=reportdir/'plan.json'
 if planfile.exists():plan=json.loads(planfile.read_text());now=plan['now']
 else:
  core.execute('BEGIN');source.execute('BEGIN')
  assets=manifest_candidates(source,assets_file,limit) if assets_file else candidates(source,now,limit)
  plan={'now':now,'assets':assets,'baseline':{'targeted_assets':len(assets)} if assets_file else audit(core,source,now)}
  (reportdir/'before.json').write_text(json.dumps(plan['baseline'],indent=2));planfile.write_text(json.dumps(plan,indent=2))
  core.rollback();source.rollback()
 end=now-now%DAY;start=end-8*DAY
 existing={}
 events=reportdir/'events.jsonl'
 if events.exists():
  for line in events.read_text().splitlines():
   r=json.loads(line);existing[(r['chain'],r['address'])]=r
 receipts=reportdir/'requests.jsonl'
 requests=len(receipts.read_text().splitlines()) if receipts.exists() else 0
 started=time.monotonic();stopped=None
 for row in plan['assets']:
  key=(row['chain'],row['address'])
  if key in existing:
   # An offline audit is resumable with networking; issued requests are never repeated.
   if not network or existing[key]['requests']>0:continue
   if not missing_ranges({r['ts']:True for r in read_bars(source,*key,start,end)},start,end):continue
   existing.pop(key)
  checkpoint=reportdir/(hashlib.sha256(str(key).encode()).hexdigest()+'.checkpoint.json')
  if checkpoint.exists():event=json.loads(checkpoint.read_text())
  else:
   event={**row,'before':read_bars(source,*key,start,end),'archive_candidates':0,'requests':0,'inserted':0,'accepted':0,'errors':[],'invalid_rows':0,'raw_files':[],'owned_bars':[]}
   checkpoint.write_text(json.dumps(event,indent=2))
  before=valid_closes(event['before'],now,row['token_created_at'])
  archived=recover_archive(core,row,start,end,now)
  event['archive_candidates']=len(archived)
  with source:inserted=insert_missing(source,*key,archived)
  event['owned_bars'].extend(inserted);event['inserted']+=len(inserted)
  checkpoint.write_text(json.dumps(event,indent=2))
  live=read_bars(source,*key,start,end)
  # Occupied invalid records require a separate review; do not fetch and overwrite.
  occupied={r['ts']:True for r in live}
  for left,right in missing_ranges(occupied,start,end):
   if not network:continue
   rawname=hashlib.sha256(f'{key}:{left}:{right}'.encode()).hexdigest()+'.json'
   rawfile=reportdir/rawname
   receipt_id=rawname
   prior_receipts=[json.loads(line) for line in receipts.read_text().splitlines()] if receipts.exists() else []
   already_requested=any(r['id']==receipt_id for r in prior_receipts)
   if rawfile.exists():
    saved=json.loads(rawfile.read_text());payload=saved['response'];fetched=saved['fetched_at']
   else:
    if already_requested:continue  # uncertain/failed requests never automatically repeat
    if requests>=max_requests:stopped='request_budget';break
    sys.path.insert(0,str(ROOT/'rh_v2'));import market_sched
    market_sched.load_cooldown(source)
    if market_sched.in_cooldown(time.time()):stopped='shared_rate_limit_cooldown';break
    cli_chain='robinhood' if row['chain']=='rh' else row['chain']
    cmd=['gmgn-cli','market','kline','--chain',cli_chain,'--address',row['address'],'--resolution','1d','--from',str(left),'--to',str(right),'--raw']
    with receipts.open('a') as output:output.write(json.dumps({'id':receipt_id,'chain':row['chain'],'address':row['address'],'from':left,'to':right,'started_at':int(time.time())})+'\n')
    event['requests']+=1;requests+=1
    checkpoint.write_text(json.dumps(event,indent=2))
    try:
     response=subprocess.run(cmd,capture_output=True,text=True,timeout=35)
     if response.returncode:
      message=response.stderr or response.stdout
      category='rate_limit' if ('429' in message or 'RATE_LIMIT' in message) else 'authentication' if ('401' in message or '403' in message) else 'provider_error'
      event['errors'].append(category)
      if category=='rate_limit':market_sched.observe_error(message);stopped=category
      if category=='authentication':stopped=category
      checkpoint.write_text(json.dumps(event,indent=2))
      if stopped:break
      time.sleep(delay);continue
     payload=json.loads(response.stdout);fetched=int(time.time())
     with rawfile.open('x') as output:json.dump({'provider':'gmgn','chain':row['chain'],'address':row['address'],'resolution':'1d','from':left,'to':right,'fetched_at':fetched,'response':payload},output)
    except subprocess.TimeoutExpired:event['errors'].append('timeout');checkpoint.write_text(json.dumps(event,indent=2));continue
    except (ValueError,TypeError):event['errors'].append('malformed_response');checkpoint.write_text(json.dumps(event,indent=2));continue
   rawrows=payload.get('list')
   if not isinstance(rawrows,list):event['errors'].append('malformed_response');continue
   event['raw_files'].append(rawname)
   bars=[bar for raw in rawrows if (bar:=validate_bar(raw,fetched,left,right,row['token_created_at'],key))]
   event['invalid_rows']+=len(rawrows)-len(bars);event['accepted']+=len(bars)
   with source:inserted=insert_missing(source,*key,bars)
   event['owned_bars'].extend(inserted);event['inserted']+=len(inserted)
   checkpoint.write_text(json.dumps(event,indent=2));time.sleep(delay)
  # Attribute only this run's successful inserts, excluding concurrent collectors.
  after=valid_closes(event['before']+event['owned_bars'],int(time.time()),row['token_created_at'])
  before_returns=return_days(before,start,end);after_returns=return_days(after,start,end)
  event.update(before_valid_days=len(before_returns),after_valid_days=len(after_returns),new_return_days=len(set(after_returns)-set(before_returns)),new_any_asset=int(not before_returns and bool(after_returns)),new_full_asset=int(len(before_returns)<7 and len(after_returns)==7),elapsed_seconds=round(time.monotonic()-started,3))
  with events.open('a') as output:output.write(json.dumps(event)+'\n')
  existing[key]=event
  print(json.dumps({'done':len(existing),'requests':requests,'inserted':event['inserted'],'new_return_days':event['new_return_days'],'errors':event['errors']}),flush=True)
  if stopped:break
 totals={'selected_assets':len(plan['assets']),'tested_assets':len(existing),'api_requests':requests,'inserted_bars':sum(r['inserted'] for r in existing.values()),'archive_candidates':sum(r['archive_candidates'] for r in existing.values()),'new_any_assets':sum(r['new_any_asset'] for r in existing.values()),'new_full_assets':sum(r['new_full_asset'] for r in existing.values()),'new_return_days':sum(r['new_return_days'] for r in existing.values()),'error_requests':sum(len(r['errors']) for r in existing.values()),'stopped':stopped,'elapsed_seconds':round(time.monotonic()-started,3),'paid_requests':0,'request_spacing_seconds':delay,'assets_returning_verified_history':sum(r['accepted']>0 for r in existing.values()),'assets_with_empty_response':sum(bool(r['raw_files']) and r['accepted']==0 and not r['errors'] for r in existing.values()),'invalid_response_bars':sum(r['invalid_rows'] for r in existing.values())}
 totals['error_rate']=totals['error_requests']/totals['api_requests'] if totals['api_requests'] else 0
 runsfile=reportdir/'runs.jsonl'
 with runsfile.open('a') as output:output.write(json.dumps({'elapsed_seconds':totals['elapsed_seconds'],'requests_so_far':requests,'stopped':stopped})+'\n')
 totals['total_elapsed_seconds']=round(sum(json.loads(line)['elapsed_seconds'] for line in runsfile.read_text().splitlines()),3)
 (reportdir/'sample.json').write_text(json.dumps(totals,indent=2));print(json.dumps(totals),flush=True)
 source.close();core.close();return totals

def sample(reportdir,limit,max_requests,network,delay=10,assets_file=None):
 """One recovery process per persisted plan; concurrent launches cannot duplicate requests."""
 reportdir.mkdir(exist_ok=True,parents=True)
 with (reportdir/'run.lock').open('a') as lock:
  try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  except BlockingIOError:raise RuntimeError('This history recovery checkpoint is already running')
  return _sample(reportdir,limit,max_requests,network,delay,assets_file)

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--report-dir',type=Path,required=True);p.add_argument('--limit',type=int,default=100);p.add_argument('--max-requests',type=int,default=100);p.add_argument('--network',action='store_true');p.add_argument('--delay',type=float,default=10);p.add_argument('--assets-file',type=Path);a=p.parse_args()
 if not 100<=a.limit<=500:raise SystemExit('sample limit must be 100..500')
 if a.delay<5:raise SystemExit('minimum request spacing is 5 seconds')
 if not 0<=a.max_requests<=500:raise SystemExit('request budget must be 0..500')
 sample(a.report_dir,a.limit,a.max_requests,a.network,a.delay,a.assets_file)
