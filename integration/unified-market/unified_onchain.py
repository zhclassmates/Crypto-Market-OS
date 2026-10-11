"""Read-only adapter for the EXISTING onchain SQLite. Never calls an API."""
import datetime as dt
import hashlib
import json
import sqlite3
from pathlib import Path
UTC=dt.timezone.utc
CHAINS={'eth':'ethereum','sol':'solana','rh':'robinhood'}
GMGN_VARIANTS={'hot','trending','trenches','signal'}

def iso(ts):
 try:
  if ts is None or float(ts)<=0:return None
  return dt.datetime.fromtimestamp(int(ts),UTC).isoformat()
 except (ValueError,TypeError,OverflowError,OSError):return None

def final_bar(r,created_at,now):
 ts=r['ts']
 if not isinstance(ts,int) or ts%86400 or ts+86400>now:return False
 if created_at and ts<int(created_at)//86400*86400:return False
 return any(isinstance(r.get(k),int) and ts+86400<=r[k]<=ts+100*86400 for k in ('fetched_at','finalized_at'))

def read_inputs(sources,health,path,number,digest,chain_token,now=None):
 now=int(now or dt.datetime.now(UTC).timestamp())
 c=sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True,timeout=30);c.row_factory=sqlite3.Row
 c.execute('PRAGMA query_only=ON');c.execute('BEGIN')
 audit=hashlib.sha256();count={'gmgn_tokens':0,'gmgn_snapshots':0,'dex_auxiliary_records':0,'gmgn_bars':0,'gmgn_finalized_bars':0,'gmgn_invalid_bars':0}
 try:
  tokens={}
  registry_columns={r[1] for r in c.execute('PRAGMA table_info(token_registry)')}
  registry={}
  if {'chain','address'}.issubset(registry_columns):
   registry={(r['chain'],r['address']):dict(r) for r in c.execute('SELECT * FROM token_registry')}
  records={(r['chain'],r['address']):dict(r) for r in c.execute('SELECT t.*,s.* FROM tokens t LEFT JOIN token_snapshot s USING(chain,address) ORDER BY t.chain,t.address')}
  token_ids=set(records)
  for ident,r in registry.items():
   if ident not in records:
    snapshot=c.execute('SELECT * FROM token_snapshot WHERE chain=? AND address=?',ident).fetchone()
    records[ident]={**r,**(dict(snapshot) if snapshot else {})}
  for ident in sorted(records):
   rr=records[ident]
   r=dict(rr);audit.update(json.dumps(r,sort_keys=True).encode());rawchain=r['chain'];chain=CHAINS.get(rawchain,rawchain);address=r['address']
   ident=chain_token(chain,address);sid=chain+':'+(ident[1] if ident else str(address));key=('gmgn',sid)
   reg=registry.get((rawchain,address),{})
   liquidity=number(r.get('liquidity_num'))
   if liquidity is None:liquidity=number(r.get('liquidity'))
   main=reg.get('first_liquidity_50k_at') is not None or reg.get('kline_backfilled_at') is not None or (liquidity is not None and liquidity>=50000)
   tier='MAIN' if main else ('EARLY' if liquidity is not None and liquidity>=20000 else ('OBSERVE' if liquidity is not None else 'UNKNOWN'))
   asset={'asset_key':'gmgn:'+sid,'chain':chain,'address':address,'symbol':r.get('symbol'),'name':r.get('name'),
     'first_seen_utc':iso(r.get('first_seen_at') or reg.get('first_seen_at')),'last_seen_utc':iso(r.get('ts')),'token_created_at':iso(r.get('token_created_at') or reg.get('token_created_at')),
     'browse_tier':tier,'tier_basis':'existing registry first_liquidity_50k_at / kline_backfilled_at; current snapshot liquidity 20k / 50k',
     'creation_basis':'tokens.token_created_at; never pair_created_at or first_seen_at','raw_table':'tokens' if (rawchain,address) in token_ids else 'token_registry','raw_database':str(Path(path).resolve())}
   src=sources.setdefault(key,{'assets':[],'observations':[]});src['assets'].append(asset);tokens[(rawchain,address)]=(key,asset)
   count['gmgn_tokens']+=1
   if r.get('ts') is None:continue
   count['gmgn_snapshots']+=1
   time=iso(r['ts']);field_times={};field_quality={};values={}
   for field,col in [('price_usd','price'),('market_cap_usd','market_cap'),('volume_usd','volume_24h'),('liquidity_usd','liquidity'),('price_change_24h','pc_24h')]:
    variant=r.get(col+'_source');known=variant in GMGN_VARIANTS
    # Oracle/anchor/Dex fields do not become GMGN quotes. Legacy values stay UNKNOWN.
    values[field]=number(r.get(col),field=='price_change_24h') if known or variant is None else None
    if field=='price_change_24h' and values[field] is not None:values[field]*=100
    stamp=iso(r.get(col+'_updated_at')) if known else None
    field_times[field]=stamp or time
    field_quality[field]='trusted' if known and stamp else 'unknown'
   o={'provider':'gmgn','provider_id':sid,'asset_key':asset['asset_key'],'date_utc':time[:10] if time else 'unknown',
      'collected_at_utc':time,'time_basis':'intraday','market_scope':'chain_token_reported', 'volume_basis':'chain_token_rolling_24h',
      'fdv_usd':None,**values,'field_timestamps':field_times,'field_quality':field_quality,'source_quality':'unknown',
      'raw_table':'token_snapshot','raw_chain':rawchain,'raw_address':address,'raw_snapshot_ts':r['ts'],
      'field_sources':{col:r.get(col+'_source') for col in ('price','volume_24h','liquidity','market_cap','pc_24h')}}
   o['version_id']=digest(o);src['observations'].append(o)
   if any(r.get(col) is not None for col in ('price_ds','volume_ds','liquidity_ds')):
    # Snapshot.ts is GMGN refresh time, NOT the timestamp of the DS auxiliary fields.
    dsid='rh:'+sid;ds=sources.setdefault(('dex',dsid),{'assets':[],'observations':[]});ds['assets'].append(asset)
    d={'provider':'dex','provider_id':dsid,'asset_key':asset['asset_key'],'date_utc':'unknown','collected_at_utc':None,
      'time_basis':'unknown','market_scope':'onchain_returned_pool','volume_basis':'returned_pool_rolling_24h',
      'price_usd':number(r.get('price_ds')),'volume_usd':number(r.get('volume_ds')),'liquidity_usd':number(r.get('liquidity_ds')),
      'market_cap_usd':None,'fdv_usd':None,'source_quality':'unknown','timestamp_missing':True,'raw_table':'token_snapshot',
      'raw_chain':rawchain,'raw_address':address,'scope_note':'DEX auxiliary values have no per-record time; never current trusted price or finalized history'}
    d['version_id']=digest(d);ds['observations'].append(d);count['dex_auxiliary_records']+=1
  for rr in c.execute('SELECT * FROM daily_kline ORDER BY chain,address,ts'):
   r=dict(rr);audit.update(json.dumps(r,sort_keys=True).encode());count['gmgn_bars']+=1
   info=tokens.get((r['chain'],r['address']))
   if not info:continue
   key,asset=info;closed=final_bar(r,asset.get('token_created_at') and int(dt.datetime.fromisoformat(asset['token_created_at']).timestamp()),now)
   count['gmgn_finalized_bars']+=int(closed);count['gmgn_invalid_bars']+=int(not closed)
   bar_time=iso(r['ts']);observed=iso(r.get('finalized_at')) or iso(r.get('fetched_at'))
   o={'provider':'gmgn','provider_id':key[1],'asset_key':asset['asset_key'],'date_utc':bar_time[:10] if bar_time else 'unknown',
      'collected_at_utc':observed,'time_basis':'utc_finalized' if closed else 'provisional',
      'price_usd':number(r.get('close')),'volume_usd':None,'market_cap_usd':None,'fdv_usd':None,'liquidity_usd':None,
      'volume_basis':'not_available','market_scope':'chain_token_daily_close','source_quality':'trusted' if closed else 'unknown',
      'raw_table':'daily_kline','raw_chain':r['chain'],'raw_address':r['address'],'raw_bar':r,'bar_open_ts':r['ts'],
      'history_eligible':closed,'quote_timestamp':(bar_time if not closed else None)}
   o['version_id']=digest(o);sources[key]['observations'].append(o)
  health['gmgn']='local_observed' # Collection health is not a blanket TRUSTED asset label.
  return {**count,'read_only':True,'input_sha256':audit.hexdigest(),'source_database':str(Path(path).resolve())}
 finally:c.rollback();c.close()
