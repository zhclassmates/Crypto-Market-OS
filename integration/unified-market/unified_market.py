#!/usr/bin/env python3
"""Local-only, additive unified market layer. No networking or ingestion imports.

Raw tables are never updated. BEGIN IMMEDIATE publishes identity, current fields,
UTC snapshots and checkpoints together. A failed transaction preserves last good view.
"""
import argparse
import datetime as dt
import hashlib
import json
import math
import os
import re
import sqlite3
from collections import defaultdict
from pathlib import Path

UTC = dt.timezone.utc
VERSION = 'unified-v1.8'
FIELDS = {'price_usd':'price_usd', 'market_cap':'market_cap_usd', 'fdv':'fdv_usd',
          'volume_24h':'volume_usd', 'liquidity_usd':'liquidity_usd',
          'market_cap_rank':'market_cap_rank', 'price_change_24h':'price_change_24h'}
THRESHOLDS = {'price_usd':.05, 'market_cap':.10, 'fdv':.10, 'volume_24h':.25, 'market_cap_rank':.10, 'price_change_24h':.25}
SCHEMA = '''
CREATE TABLE IF NOT EXISTS wm_unified_assets (
 canonical_asset_id TEXT PRIMARY KEY, name TEXT, symbol TEXT, identity_confidence TEXT NOT NULL,
 first_seen_utc TEXT, active INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS wm_unified_sources (
 provider TEXT, provider_id TEXT, canonical_asset_id TEXT NOT NULL, evidence_json TEXT NOT NULL,
 fingerprint TEXT NOT NULL, PRIMARY KEY(provider,provider_id));
CREATE INDEX IF NOT EXISTS idx_unified_sources_asset ON wm_unified_sources(canonical_asset_id);
CREATE TABLE IF NOT EXISTS wm_unified_chain_tokens (
 chain_id TEXT, contract_address TEXT, canonical_asset_id TEXT NOT NULL, evidence_json TEXT NOT NULL,
 PRIMARY KEY(chain_id,contract_address));
CREATE INDEX IF NOT EXISTS idx_unified_tokens_asset ON wm_unified_chain_tokens(canonical_asset_id);
CREATE TABLE IF NOT EXISTS wm_unified_identity_links (
 provider_a TEXT, id_a TEXT, provider_b TEXT, id_b TEXT, evidence TEXT NOT NULL,
 verified INTEGER NOT NULL CHECK(verified IN (0,1)),
 PRIMARY KEY(provider_a,id_a,provider_b,id_b));
CREATE TABLE IF NOT EXISTS wm_unified_redirects (old_id TEXT PRIMARY KEY, canonical_asset_id TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS wm_unified_raw_versions (
 version_id TEXT PRIMARY KEY, provider TEXT NOT NULL, provider_id TEXT NOT NULL,
 date_utc TEXT NOT NULL, collected_at_utc TEXT NOT NULL, payload_json TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_unified_raw_source ON wm_unified_raw_versions(provider,provider_id,date_utc);
CREATE TABLE IF NOT EXISTS wm_unified_current (
 canonical_asset_id TEXT PRIMARY KEY, name TEXT, symbol TEXT, chains TEXT NOT NULL,
 contracts TEXT NOT NULL, cg_id TEXT, cmc_id TEXT, dex_token_id TEXT, source_list TEXT NOT NULL,
 source_count INTEGER NOT NULL, primary_source TEXT, identity_confidence TEXT NOT NULL,
 price_usd REAL, market_cap REAL, fdv REAL, volume_24h REAL, liquidity_usd REAL,
 market_cap_rank REAL, price_change_24h REAL, first_seen_utc TEXT, latest_data_time TEXT,
 quality_status TEXT NOT NULL, data_timestamp TEXT, source_conflict INTEGER NOT NULL,
 missing_fields TEXT NOT NULL, selection_json TEXT NOT NULL, pool_data_json TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_unified_cap ON wm_unified_current(market_cap DESC,canonical_asset_id);
CREATE INDEX IF NOT EXISTS idx_unified_volume ON wm_unified_current(volume_24h DESC,canonical_asset_id);
CREATE INDEX IF NOT EXISTS idx_unified_quality ON wm_unified_current(quality_status,market_cap DESC);
CREATE TABLE IF NOT EXISTS wm_unified_daily (
 canonical_asset_id TEXT, date_utc TEXT, price_usd REAL, daily_return REAL,
 provider TEXT, provider_id TEXT, time_basis TEXT, data_timestamp TEXT,
 raw_version_id TEXT, selection_json TEXT NOT NULL, PRIMARY KEY(canonical_asset_id,date_utc));
CREATE INDEX IF NOT EXISTS idx_unified_daily_date ON wm_unified_daily(date_utc,daily_return,canonical_asset_id);
CREATE TABLE IF NOT EXISTS wm_unified_conflicts (
 canonical_asset_id TEXT, field TEXT, source_a TEXT, source_b TEXT,
 value_a REAL, value_b REAL, difference_ratio REAL, timestamp_a TEXT, timestamp_b TEXT,
 comparison_status TEXT NOT NULL, chosen_source TEXT, reason TEXT NOT NULL,
 PRIMARY KEY(canonical_asset_id,field,source_a,source_b));
CREATE TABLE IF NOT EXISTS wm_unified_meta (key TEXT PRIMARY KEY,value TEXT NOT NULL);
CREATE VIEW IF NOT EXISTS wm_unified_market_view AS SELECT * FROM wm_unified_current;
CREATE VIEW IF NOT EXISTS wm_unified_research_view AS
 SELECT * FROM wm_unified_current WHERE quality_status='VALID' AND identity_confidence!='UNRESOLVED';
'''

def js(v):
    return json.dumps(v, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False)

def digest(v):
    return hashlib.sha256(js(v).encode()).hexdigest()

def timestamp(v):
    try:
        return dt.datetime.fromisoformat(v.replace('Z','+00:00')).astimezone(UTC).timestamp()
    except (ValueError, TypeError, AttributeError):
        return None

def chain_token(chain, address):
    chain = {'1':'ethereum','56':'bsc','8453':'base','eth':'ethereum','sol':'solana','binance-smart-chain':'bsc','base':'base'}.get(chain,chain)
    address = str(address or '').strip()
    if address.startswith('0X'):address='0x'+address[2:]
    if chain == 'solana' and re.fullmatch(r'[1-9A-HJ-NP-Za-km-z]{32,44}', address):
        return chain,address
    if chain in ('ethereum','bsc','base','robinhood') and re.fullmatch(r'0x[0-9a-fA-F]{40}',address):
        return chain,address.lower()
    return None

def number(v, signed=False):
    try:
        n = float(v)
        return n if math.isfinite(n) and (signed or n >= 0) else None
    except (TypeError,ValueError,OverflowError):
        return None

def field_time(o,field):
    return o.get('field_timestamps',{}).get(FIELDS[field]) or data_time(o)

def source_quality(o,field,health):
    return o.get('field_quality',{}).get(FIELDS[field]) or o.get('source_quality') or health.get(o['provider'],'unknown')

def data_time(o):
    # CMC collection time is NOT the historical quote time.
    if o['time_basis'] == 'utc_finalized':
        return o['date_utc']+'T23:59:59+00:00'
    return o.get('quote_timestamp') or o['collected_at_utc']

def source_key(o):
    return o['provider']+':'+o['provider_id']

def field_candidates(obs, field, health):
    candidates=[]
    for o in obs:
        if field == 'liquidity_usd':
            if o['provider'] not in ('dex','gmgn'): continue
        elif o['provider'] == 'dex':
            # Pool price is a fallback only; pool volumes/caps never impersonate asset totals.
            if field != 'price_usd': continue
        v = number(o.get(FIELDS[field]), field=='price_change_24h')
        if v is None or timestamp(field_time(o,field)) is None or o.get('time_basis')=='provisional': continue
        if field=='price_usd' and v<=0:continue
        # Old raw ranks / changes have not been retained by CMC ingestion.
        candidates.append((o,v))
    def score(x):
        o,_=x
        scope = (2 if o['provider'] in ('cg','cmc') else 1 if o['provider']=='gmgn' else 0) if field != 'liquidity_usd' else 1
        fresh=timestamp(field_time(o,field))
        # Price is a quote: among trustworthy prices prefer the latest actual observation.
        return (source_quality(o,field,health)=='trusted', fresh if field=='price_usd' else scope, scope if field=='price_usd' else fresh,
                o['time_basis']=='utc_finalized', source_key(o))
    return sorted(candidates,key=score,reverse=True)

def select_fields(obs, health):
    values={}; selections={}; conflicts=[]
    for field in FIELDS:
        candidates=field_candidates(obs,field,health)
        if not candidates:
            values[field]=None;selections[field]={'reason':'missing: no valid retained observation'};continue
        chosen,value=candidates[0];values[field]=value
        reason='validity → source quality → field scope → quote freshness → deterministic tie-break'
        selections[field]={'source':source_key(chosen),'provider':chosen['provider'],
            'value':value,'timestamp':field_time(chosen,field),'collected_at_utc':chosen['collected_at_utc'],
            'time_basis':chosen['time_basis'],'market_scope':chosen['market_scope'],
            'volume_basis':chosen['volume_basis'],'raw_version_id':chosen['version_id'], 'reason':reason,
            'source_quality':source_quality(chosen,field,health), 'timestamp_basis':('normalized_utc_eod' if chosen['time_basis']=='utc_finalized' else ('provider_quote' if chosen.get('quote_timestamp') else 'collection_proxy'))}
        # Compare CG/CMC only, with aligned UTC-finalized or synchronized intraday windows.
        a=next((x for x in candidates if x[0]['provider']=='cg'),None)
        b=next((x for x in candidates if x[0]['provider']=='cmc'),None)
        if not a or not b: continue
        ao,av=a;bo,bv=b
        synchronized = ((ao['time_basis']==bo['time_basis']=='utc_finalized' and ao['date_utc']==bo['date_utc']) or
          (ao['time_basis']==bo['time_basis']=='intraday' and abs(timestamp(data_time(ao))-timestamp(data_time(bo)))<=900))
        if field=='volume_24h' and ao['volume_basis']!=bo['volume_basis']: synchronized=False
        gap=abs(av-bv)/max(abs(av),abs(bv)) if av or bv else 0
        status='CONFLICT' if synchronized and gap>THRESHOLDS.get(field,.1) else ('ALIGNED' if synchronized else 'NOT_COMPARABLE')
        conflicts.append({'field':field,'source_a':source_key(ao),'source_b':source_key(bo),
            'value_a':av,'value_b':bv,'difference_ratio':gap if synchronized else None,
            'timestamp_a':data_time(ao),'timestamp_b':data_time(bo),'comparison_status':status,
            'chosen_source':source_key(chosen),'reason':reason if synchronized else '不同时间窗口或成交量口径；不计算同步价差'})
    return values,selections,conflicts

def schema(c):
    c.executescript(SCHEMA)
    for table,cols in {'wm_unified_current':{'token_created_at':'TEXT','gmgn_id':"TEXT DEFAULT '[]'",'market_tier':"TEXT DEFAULT 'UNKNOWN'"},'wm_unified_daily':{'return_quality':'TEXT'}}.items():
        present={r[1] for r in c.execute('PRAGMA table_info('+table+')')}
        for col,decl in cols.items():
            if col not in present:c.execute('ALTER TABLE '+table+' ADD COLUMN '+col+' '+decl)
    for name,sql in {
        'idx_unified_tier_cap':'wm_unified_current(market_tier,market_cap DESC,canonical_asset_id)',
        'idx_unified_liquidity':'wm_unified_current(liquidity_usd,canonical_asset_id)',
        'idx_unified_first_seen':'wm_unified_current(first_seen_utc,canonical_asset_id)',
        'idx_unified_tokens_address':'wm_unified_chain_tokens(contract_address,canonical_asset_id)',
        'idx_unified_finalized_date':'wm_unified_daily(time_basis,date_utc DESC)',
    }.items():c.execute('CREATE INDEX IF NOT EXISTS '+name+' ON '+sql)
    c.commit()

def upsert(c,table,row,keys):
    cols=list(row); values=list(row.values())
    updates=[x for x in cols if x not in keys]
    c.execute(f"INSERT INTO {table} ({','.join(cols)}) VALUES ({','.join('?' for _ in cols)}) ON CONFLICT({','.join(keys)}) DO UPDATE SET "+','.join(f'{x}=excluded.{x}' for x in updates)+
        ' WHERE '+ ' OR '.join(f'{table}.{x} IS NOT excluded.{x}' for x in updates),values)

def read_inputs(c):
    c.row_factory=sqlite3.Row
    assets={r['asset_key']:dict(r) for r in c.execute('SELECT * FROM wm_market_assets')}
    sources={}
    for r in c.execute('SELECT * FROM wm_market_aliases'):
        key=(r['provider'],r['provider_id']); a=assets.get(r['asset_key'],{})
        sources[key]={'assets':[a], 'observations':[]}
    payloads={}
    for r in c.execute('''SELECT s.provider_id,s.payload,t.date_utc FROM wm_cg_staged s
      JOIN wm_cg_snapshots t USING(snapshot_id) WHERE t.status='complete' ORDER BY t.date_utc'''):
        try: payloads[(r['provider_id'],r['date_utc'])]=json.loads(r['payload'])
        except ValueError: pass
    for r in c.execute('SELECT * FROM wm_market_observations ORDER BY provider,provider_id,date_utc,time_basis'):
        o=dict(r);key=(o['provider'],o['provider_id'])
        src=sources.setdefault(key,{'assets':[],'observations':[]})
        a=assets.get(o['asset_key'],{})
        if a and a not in src['assets']:src['assets'].append(a)
        o['version_id']=digest(o)
        if o['provider']=='cg':
            p=payloads.get((o['provider_id'],o['date_utc']),{})
            o['market_cap_rank']=p.get('market_cap_rank');o['price_change_24h']=p.get('price_change_percentage_24h')
            o['quote_timestamp']=p.get('last_updated')
        o['version_id']=digest({k:v for k,v in o.items() if k!='version_id'})
        src['observations'].append(o)
    health={r['provider']:r['status'] for r in c.execute('SELECT provider,status FROM wm_quality_reports ORDER BY checked_at_utc')}
    return sources,health

def sync(c, full=False, fail_before_commit=False, rh_db=None):
    schema(c)
    c.execute('BEGIN IMMEDIATE')
    try:
        sources,health=read_inputs(c)
        checkpoints={r['key']:r['value'] for r in c.execute('SELECT * FROM wm_unified_meta')}
        rh_path=rh_db if rh_db is not None else os.environ.get('RH_MARKET_DB',checkpoints.get('onchain_db'))
        if rh_path:
            import unified_onchain
            audit=unified_onchain.read_inputs(sources,health,rh_path,number,digest,chain_token)
            upsert(c,'wm_unified_meta',{'key':'onchain_audit','value':js(audit)},['key'])
            upsert(c,'wm_unified_meta',{'key':'onchain_db','value':str(Path(rh_path).resolve())},['key'])
        repair_days=full or checkpoints.get('version')!=VERSION or checkpoints.get('health')!=js(health)
        recomputed_dates=0
        latest_date=max((o['date_utc'] for src in sources.values() for o in src['observations'] if re.fullmatch(r'\d{4}-\d{2}-\d{2}',o['date_utc'])),default=None)
        old={(r['provider'],r['provider_id']):dict(r) for r in c.execute('SELECT * FROM wm_unified_sources')}
        old_groups=defaultdict(set)
        for k,v in old.items():old_groups[v['canonical_asset_id']].add(k)
        links=[dict(r) for r in c.execute('SELECT * FROM wm_unified_identity_links WHERE verified=1 AND length(trim(evidence))>0')]
        # Reviewed native links carry chain identity without inventing a contract.
        native_pairs={('bitcoin','1'):'bitcoin',('ethereum','1027'):'ethereum',('solana','5426'):'solana'}
        for link in links:
            pair=(link['id_a'],link['id_b'])
            if link['provider_a']=='cg' and link['provider_b']=='cmc' and pair in native_pairs:
                try: proof=json.loads(link['evidence'])
                except ValueError:continue
                if proof.get('kind')=='verified_native_ids' and proof.get('native_chain')==native_pairs[pair]:
                    for key in [('cg',pair[0]),('cmc',pair[1])]:
                        for asset in sources.get(key,{}).get('assets',[]):
                            if not asset.get('address'):asset['native_chain']=native_pairs[pair]
        parent={k:k for k in sources};evidence=defaultdict(list); tokens=defaultdict(list)
        def find(k):
            while parent[k]!=k:parent[k]=parent[parent[k]];k=parent[k]
            return k
        def union(a,b):
            a,b=find(a),find(b)
            if a!=b:parent[max(a,b)]=min(a,b)
        for k,s in sources.items():
            for a in s['assets']:
                t=chain_token(a.get('chain'),a.get('address'))
                if t:
                    if k not in tokens[t]:tokens[t].append(k)
                    evidence[k].append({'basis':'source_contract_mapping','provider':k[0], 'provider_id':k[1],
                      'raw_asset_key':a['asset_key'],'chain_id':t[0],'contract_address':t[1]})
        for t,keys in tokens.items():
            for k in keys[1:]:union(keys[0],k)
        for l in links:
            a=(l['provider_a'],l['id_a']);b=(l['provider_b'],l['id_b'])
            if a in sources and b in sources:
                union(a,b)
                for k in (a,b):evidence[k].append({'basis':'verified_official_id_link','evidence':l['evidence'], 'link':l})
        groups=defaultdict(list)
        for k in sources:groups[find(k)].append(k)
        group_tokens=defaultdict(list)
        for t,ks in tokens.items():group_tokens[find(ks[0])].append(t)
        assigned={};used=set();affected=set();mapping={};cid_tokens={}
        for root,keys in sorted(groups.items()):
            previous=sorted({old[k]['canonical_asset_id'] for k in keys if k in old})
            anchor=next((p for p in previous if p not in used),None)
            cid=anchor or 'asset:'+digest(root)[:24]
            if cid in used:cid='asset:'+digest(keys)[:24]
            used.add(cid);assigned[cid]=keys;cid_tokens[cid]=sorted(group_tokens[root])
            for k in keys:
                mapping[k]=cid
                fp=digest({'version':VERSION,'source':sources[k],'health':health.get(k[0]),'evidence':evidence[k]})
                prior=old.get(k)
                if full or not prior or prior['fingerprint']!=fp or prior['canonical_asset_id']!=cid:
                    affected.add(cid)
                    if prior:affected.add(prior['canonical_asset_id'])
                upsert(c,'wm_unified_sources',{'provider':k[0],'provider_id':k[1],'canonical_asset_id':cid,
                    'evidence_json':js(evidence[k] or [{'basis':'unresolved_source_id','provider':k[0],'provider_id':k[1]}]),'fingerprint':fp},['provider','provider_id'])
            for p in previous:
                if p!=cid and p not in used and all(mapping.get(k,cid)==cid for k in keys if old.get(k,{}).get('canonical_asset_id')==p):
                    upsert(c,'wm_unified_redirects',{'old_id':p,'canonical_asset_id':cid},['old_id'])
        previous_window=c.execute("SELECT value FROM wm_unified_meta WHERE key='window_end'").fetchone()
        if previous_window and previous_window[0]!=latest_date:
            affected.update(r[0] for r in c.execute("SELECT canonical_asset_id FROM wm_unified_current WHERE missing_fields NOT LIKE '%price_history_7d%' OR missing_fields NOT LIKE '%daily_return%'"))
        if latest_date:upsert(c,'wm_unified_meta',{'key':'window_end','value':latest_date},['key'])
        # Removed raw aliases are not silently deleted; original observations keep identity alive.
        for cid in affected:
            if cid not in assigned:
                c.execute('UPDATE wm_unified_assets SET active=0 WHERE canonical_asset_id=?',(cid,))
                for t in ['wm_unified_current','wm_unified_daily','wm_unified_conflicts','wm_unified_chain_tokens']:
                    c.execute(f'DELETE FROM {t} WHERE canonical_asset_id=?',(cid,))
                continue
            keys=assigned[cid]; obs=[o for k in keys for o in sources[k]['observations']]
            aa=[a for k in keys for a in sources[k]['assets'] if a]
            aa.sort(key=lambda a:((a.get('last_seen_utc') or ''),a.get('asset_key','')),reverse=True)
            name=next((a.get('name') for a in aa if a.get('name')),None)
            symbol=next((a.get('symbol') for a in aa if a.get('symbol')),None)
            tt=cid_tokens[cid]
            confidence='VERIFIED_MAPPING' if any(e.get('basis')=='verified_official_id_link' for k in keys for e in evidence[k]) else ('CONTRACT_MATCH' if len(set(k[0] for k in keys))>1 and tt else ('VERIFIED_CONTRACT' if tt else 'UNRESOLVED'))
            first=min((a['first_seen_utc'] for a in aa if a.get('first_seen_utc')),default=None)
            created=min((a['token_created_at'] for a in aa if a.get('token_created_at')),default=None)
            upsert(c,'wm_unified_assets',{'canonical_asset_id':cid,'name':name,'symbol':symbol,'identity_confidence':confidence,'first_seen_utc':first,'active':1},['canonical_asset_id'])
            c.execute('DELETE FROM wm_unified_chain_tokens WHERE canonical_asset_id=?',(cid,))
            for t in tt:
                upsert(c,'wm_unified_chain_tokens',{'chain_id':t[0],'contract_address':t[1],'canonical_asset_id':cid,
                    'evidence_json':js([e for k in keys for e in evidence[k] if e.get('chain_id')==t[0] and e.get('contract_address')==t[1]])},['chain_id','contract_address'])
            for o in obs:
                c.execute('INSERT OR IGNORE INTO wm_unified_raw_versions VALUES(?,?,?,?,?,?)',
                    (o['version_id'],o['provider'],o['provider_id'],o['date_utc'],o['collected_at_utc'] or 'UNKNOWN',js(o)))
            # Latest snapshot per source, never sum across sources/chains.
            latest={}
            for o in obs:
                k=(o['provider'],o['provider_id'])
                if k not in latest or (timestamp(data_time(o)) or 0)>(timestamp(data_time(latest[k])) or 0):latest[k]=o
            values,selections,conflicts=select_fields(list(latest.values()),health)
            byday=defaultdict(list)
            for o in obs:
                if re.fullmatch(r'\d{4}-\d{2}-\d{2}',o['date_utc']):byday[o['date_utc']].append(o)
            # Date fingerprints isolate daily corrections from changes to current fields.
            date_key='daily_fingerprints:'+cid
            prior_dates=json.loads(checkpoints.get(date_key,'{}'))
            date_fps={day:digest(sorted(o['version_id'] for o in oo)) for day,oo in byday.items()}
            identity_changed=old_groups[cid]!=set(keys)
            changed_days=set(byday)|set(prior_dates) if repair_days or identity_changed else {d for d in set(byday)|set(prior_dates) if date_fps.get(d)!=prior_dates.get(d)}
            # A corrected close also changes the immediately following day's return.
            changed_days|={(dt.date.fromisoformat(d)+dt.timedelta(days=1)).isoformat() for d in list(changed_days)}
            days={r['date_utc']:dict(r) for r in c.execute('SELECT * FROM wm_unified_daily WHERE canonical_asset_id=?',(cid,))}
            for day in sorted(changed_days):
                if day not in byday and day not in days:continue
                recomputed_dates+=1
                days.pop(day,None)
                oo=byday.get(day,[])

                # A stale quote from a previous UTC date cannot fill this date.
                oo=[o for o in oo if (data_time(o) or '')[:10]==day and o['time_basis'] in ('utc_finalized','intraday') and o.get('history_eligible',True)]
                # UTC close is a distinct canonical time grid; intraday is display-only.
                eligible=[o for o in oo if o['time_basis']=='utc_finalized' and o['provider']!='dex']
                candidates=field_candidates(eligible,'price_usd',health) or field_candidates(oo,'price_usd',health)
                if not candidates:continue
                previous_day=(dt.date.fromisoformat(day)-dt.timedelta(days=1)).isoformat()
                # Return pairs are constructed within each source, independent of the
                # selected previous day's display price. Never splice CMC and GMGN.
                pairs={}
                for cand,v in candidates:
                    prevs=[p for p in byday.get(previous_day,[]) if p['provider']==cand['provider'] and p['provider_id']==cand['provider_id'] and p['time_basis']==cand['time_basis']=='utc_finalized' and p.get('history_eligible',True)]
                    prev_candidates=field_candidates(prevs,'price_usd',health)
                    if prev_candidates:pairs[cand['version_id']]=prev_candidates[0]
                ranked=sorted(candidates,key=lambda x: x[0]['version_id'] in pairs,reverse=True)
                o,v=ranked[0];ret=None;rq='MISSING_PREVIOUS_CLOSE';prev_pair=pairs.get(o['version_id'])
                if o['time_basis']!='utc_finalized':rq='INTRADAY'
                elif prev_pair:
                    prev_o,pv=prev_pair;ratio=v/pv-1
                    rq='LOW_BASE_PRICE' if pv<1e-8 else ('EXTREME_RETURN' if abs(ratio)>50 else 'VALID')
                    if rq=='VALID':ret=ratio*100
                dr={'canonical_asset_id':cid,'date_utc':day,'price_usd':v,'daily_return':ret,'provider':o['provider'],'provider_id':o['provider_id'],
                    'time_basis':o['time_basis'],'data_timestamp':data_time(o),'raw_version_id':o['version_id'],'return_quality':rq,
                    'selection_json':js({'previous_raw_version_id':prev_pair[0]['version_id'] if prev_pair else None,'return_quality':rq,'reason':'same-source adjacent validated UTC closes; low-base/extreme pairs excluded from ranking','timestamp_basis':('normalized_utc_eod' if o['time_basis']=='utc_finalized' else ('provider_quote' if o.get('quote_timestamp') else 'collection_proxy')),'source_quality':source_quality(o,'price_usd',health)})}
                days[day]=dr;upsert(c,'wm_unified_daily',dr,['canonical_asset_id','date_utc'])
            if days:
                c.execute('DELETE FROM wm_unified_daily WHERE canonical_asset_id=? AND date_utc NOT IN ('+','.join('?' for _ in days)+')',(cid,*days))
            else:c.execute('DELETE FROM wm_unified_daily WHERE canonical_asset_id=?',(cid,))
            upsert(c,'wm_unified_meta',{'key':date_key,'value':js(date_fps)},['key'])
            collision=any(len({k[1] for k in tokens[t] if k[0]==p})>1 for t in tt for p in ('cg','cmc'))
            conflict=any(x['comparison_status']=='CONFLICT' for x in conflicts) or collision
            missing=[f for f,v in values.items() if v is None]
            window_end=latest_date
            available_dates=set(days)
            window_dates={(dt.date.fromisoformat(window_end)-dt.timedelta(days=i)).isoformat() for i in range(7)} if window_end else set()
            if len(available_dates & window_dates)<7:missing.append('price_history_7d')
            if not any(d['daily_return'] is not None and day in window_dates for day,d in days.items()):missing.append('daily_return')
            providers=sorted({k[0] for k in keys}); ps=selections['price_usd']
            # Decision gate for the CURRENT quote only: trusted providers, resolved
            # identity and the core valuation fields. fdv/rank are provider-specific by
            # design; pool liquidity is required only for on-chain-pool assets; 7d history
            # gaps stay visible in missing_fields but never veto the current quote.
            provider_set=set(providers)
            blocking_missing=[f for f in ('price_usd','market_cap','volume_24h','price_change_24h') if values.get(f) is None]
            if provider_set & {'dex','gmgn'} and values.get('liquidity_usd') is None:blocking_missing.append('liquidity_usd')
            # Provider health is the trust ceiling: a stamped GMGN quote proves provenance
            # (field-level) but local-only observation is not cross-verified for decisions.
            untrusted=any(health.get(s.get('provider'),'unknown')!='trusted' for s in selections.values() if s.get('source'))
            blocked=any(s.get('source_quality')=='blocked' for s in selections.values())
            quality='CONFLICT' if conflict else ('BLOCKED' if blocked else ('PARTIAL' if blocking_missing or confidence=='UNRESOLVED' or untrusted else 'VALID'))
            pools=[{**o,'scope_note':o.get('scope_note','返回池成交量之和；流动性来自最大池；未保留池地址，禁止当作全资产总量或跨链相加')} for o in latest.values() if o['provider']=='dex']
            tier=next((tier for tier in ('MAIN','EARLY','OBSERVE') if any(a.get('browse_tier')==tier for a in aa)),'UNKNOWN')
            row={'market_tier':tier,'canonical_asset_id':cid,'name':name,'symbol':symbol,'chains':js(sorted({t[0] for t in tt}|{a['native_chain'] for a in aa if a.get('native_chain')})), 'contracts':js([{'chain_id':t[0],'contract_address':t[1]} for t in tt]),
                'cg_id':js([k[1] for k in keys if k[0]=='cg']), 'cmc_id':js([k[1] for k in keys if k[0]=='cmc']), 'dex_token_id':js([k[1] for k in keys if k[0]=='dex']),
                'source_list':js(providers),'source_count':len(providers),'primary_source':ps.get('provider'), 'identity_confidence':confidence, **values,
                'token_created_at':created,'gmgn_id':js([k[1] for k in keys if k[0]=='gmgn']),'first_seen_utc':first,'latest_data_time':max((data_time(o) for o in obs),key=lambda v:timestamp(v) or 0,default=None),
                'quality_status':quality,'data_timestamp':ps.get('timestamp'),'source_conflict':int(conflict),'missing_fields':js(missing),'selection_json':js(selections),'pool_data_json':js(pools)}
            upsert(c,'wm_unified_current',row,['canonical_asset_id'])
            c.execute('DELETE FROM wm_unified_conflicts WHERE canonical_asset_id=?',(cid,))
            for cf in conflicts:
                upsert(c,'wm_unified_conflicts',{'canonical_asset_id':cid,**cf},['canonical_asset_id','field','source_a','source_b'])
            if collision:
                upsert(c,'wm_unified_conflicts',{'canonical_asset_id':cid,'field':'identity','source_a':'contract','source_b':'multiple_official_ids',
                    'value_a':None,'value_b':None,'difference_ratio':None,'timestamp_a':None,'timestamp_b':None,'comparison_status':'CONFLICT',
                    'chosen_source':None,'reason':'同链同合约指向多个同源官方 ID；保留全部 ID 和映射依据'},['canonical_asset_id','field','source_a','source_b'])
        now=dt.datetime.now(UTC).isoformat()
        if affected:
            upsert(c,'wm_unified_meta',{'key':'synced_at','value':now},['key'])
        upsert(c,'wm_unified_meta',{'key':'health','value':js(health)},['key'])
        upsert(c,'wm_unified_meta',{'key':'version','value':VERSION},['key'])
        if fail_before_commit:raise RuntimeError('injected publish failure')
        c.commit()
        return {**stats(c),'recomputed_assets':len(affected),'recomputed_dates':recomputed_dates,'external_api_calls':0}
    except BaseException:
        c.rollback();raise

def stats(c):
    result={}
    for p in ('cg','cmc','dex'):
        result[p]=c.execute('SELECT COUNT(DISTINCT provider_id) FROM wm_market_observations WHERE provider=? AND date_utc=(SELECT MAX(date_utc) FROM wm_market_observations WHERE provider=?)',(p,p)).fetchone()[0]
    for key,sql in {
      'unique_assets':'SELECT COUNT(*) FROM wm_unified_current',
      'chain_tokens':'SELECT COUNT(*) FROM wm_unified_chain_tokens',
      'multi_source_matches':'SELECT COUNT(*) FROM wm_unified_current WHERE source_count>1',
      'unresolved':'SELECT COUNT(*) FROM wm_unified_current WHERE identity_confidence="UNRESOLVED"',
      'gmgn':'SELECT COUNT(*) FROM wm_unified_sources WHERE provider="gmgn"',
      'field_conflicts':'SELECT COUNT(*) FROM wm_unified_conflicts WHERE comparison_status="CONFLICT" AND field!="identity"',
      'identity_conflicts':'SELECT COUNT(*) FROM wm_unified_conflicts WHERE field="identity"',
      'history_assets':'SELECT COUNT(DISTINCT canonical_asset_id) FROM wm_unified_daily WHERE date_utc>=date((SELECT MAX(date_utc) FROM wm_unified_daily),"-6 days")',
      'full_seven_day_assets':'SELECT COUNT(*) FROM (SELECT canonical_asset_id FROM wm_unified_daily WHERE date_utc>=date((SELECT MAX(date_utc) FROM wm_unified_daily),"-6 days") GROUP BY canonical_asset_id HAVING COUNT(*)=7)',
      'daily_return_assets':'SELECT COUNT(DISTINCT canonical_asset_id) FROM wm_unified_daily WHERE daily_return IS NOT NULL'
    }.items():result[key]=c.execute(sql).fetchone()[0]
    sync_row=c.execute("SELECT value FROM wm_unified_meta WHERE key='synced_at'").fetchone()
    result['synced_at']=sync_row[0] if sync_row else None
    return result

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--db',default=str(Path(__file__).parent/'data/world_model_market.sqlite'));p.add_argument('--full',action='store_true');p.add_argument('--stats',action='store_true');p.add_argument('--rh-db',help='Existing onchain DB; opened read-only, remembered for daily sync')
    a=p.parse_args()
    c=sqlite3.connect(a.db,timeout=30)
    try:print(json.dumps(stats(c) if a.stats else sync(c,a.full,rh_db=a.rh_db),ensure_ascii=False,indent=2))
    finally:c.close()

if __name__=='__main__':main()
