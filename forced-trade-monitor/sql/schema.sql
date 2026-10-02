PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS raw_klines_1h (
  symbol TEXT NOT NULL,
  bar_open_ts INTEGER NOT NULL,
  open REAL,
  high REAL,
  low REAL,
  close REAL,
  volume REAL,
  quote_volume REAL,
  taker_buy_volume REAL,
  taker_buy_quote_volume REAL,
  source_close_ts INTEGER,
  payload_hash TEXT NOT NULL,
  ingested_at INTEGER NOT NULL,
  PRIMARY KEY (symbol, bar_open_ts)
);

CREATE TABLE IF NOT EXISTS raw_oi_1h (
  symbol TEXT NOT NULL,
  bar_open_ts INTEGER NOT NULL,
  api_ts INTEGER NOT NULL,
  oi_qty REAL,
  oi_value_usdt REAL,
  payload_hash TEXT NOT NULL,
  ingested_at INTEGER NOT NULL,
  PRIMARY KEY (symbol, bar_open_ts)
);

CREATE TABLE IF NOT EXISTS raw_taker_1h (
  symbol TEXT NOT NULL,
  bar_open_ts INTEGER NOT NULL,
  api_ts INTEGER NOT NULL,
  buy_sell_ratio REAL,
  buy_vol REAL,
  sell_vol REAL,
  payload_hash TEXT NOT NULL,
  ingested_at INTEGER NOT NULL,
  PRIMARY KEY (symbol, bar_open_ts)
);

CREATE TABLE IF NOT EXISTS raw_basis_1h (
  symbol TEXT NOT NULL,
  pair TEXT NOT NULL,
  contract_type TEXT NOT NULL,
  bar_open_ts INTEGER NOT NULL,
  api_ts INTEGER NOT NULL,
  index_price REAL,
  futures_price REAL,
  basis_rate REAL,
  basis REAL,
  payload_hash TEXT NOT NULL,
  ingested_at INTEGER NOT NULL,
  PRIMARY KEY (symbol, bar_open_ts)
);

CREATE TABLE IF NOT EXISTS raw_funding (
  symbol TEXT NOT NULL,
  funding_time INTEGER NOT NULL,
  funding_rate REAL NOT NULL,
  mark_price REAL,
  rate_type TEXT,
  payload_hash TEXT NOT NULL,
  ingested_at INTEGER NOT NULL,
  PRIMARY KEY (symbol, funding_time)
);

CREATE TABLE IF NOT EXISTS raw_mark (
  symbol TEXT NOT NULL,
  observed_at INTEGER NOT NULL,
  mark_price REAL,
  index_price REAL,
  last_funding_rate REAL,
  next_funding_time INTEGER,
  payload_hash TEXT NOT NULL,
  ingested_at INTEGER NOT NULL,
  PRIMARY KEY (symbol, observed_at)
);

CREATE TABLE IF NOT EXISTS funding_info_snapshot (
  symbol TEXT NOT NULL,
  observed_at INTEGER NOT NULL,
  funding_interval_hours REAL,
  cap REAL,
  floor REAL,
  present_in_payload INTEGER NOT NULL,
  payload_hash TEXT NOT NULL,
  PRIMARY KEY (symbol, observed_at)
);

CREATE TABLE IF NOT EXISTS universe_snapshot (
  ts INTEGER NOT NULL,
  symbol TEXT NOT NULL,
  rank INTEGER NOT NULL,
  quote_volume REAL,
  listing_days REAL,
  contract_type TEXT,
  status TEXT,
  quote_asset TEXT,
  PRIMARY KEY (ts, symbol)
);

CREATE TABLE IF NOT EXISTS features_1h (
  symbol TEXT NOT NULL,
  bar_open_ts INTEGER NOT NULL,
  ret_1h REAL,
  ret_4h REAL,
  ret_24h REAL,
  oi_qty_chg_1h REAL,
  oi_qty_chg_4h REAL,
  oi_qty_chg_24h REAL,
  oi_z_7d REAL,
  oi_chg_1h_z REAL,
  abs_ret_1h_z REAL,
  funding_8h_equiv REAL,
  funding_pct_30d REAL,
  funding_interval_hours REAL,
  interval_source TEXT,
  funding_rate_type TEXT,
  taker_imbalance_1h REAL,
  taker_imbalance_4h REAL,
  kline_taker_imbalance_1h REAL,
  basis_bps REAL,
  mark_index_basis_bps REAL,
  basis_divergence_bps REAL,
  basis_z_7d REAL,
  btc_ret_1h REAL,
  btc_ret_4h REAL,
  ret_1h_vs_btc REAL,
  ret_4h_vs_btc REAL,
  volume_pct_30d REAL,
  flow_aligned_with_price INTEGER,
  data_quality_flag TEXT,
  PRIMARY KEY (symbol, bar_open_ts)
);

CREATE TABLE IF NOT EXISTS states_1h (
  symbol TEXT NOT NULL,
  bar_open_ts INTEGER NOT NULL,
  state TEXT NOT NULL,
  hit INTEGER NOT NULL,
  reason TEXT,
  PRIMARY KEY (symbol, bar_open_ts, state)
);

CREATE TABLE IF NOT EXISTS alerts (
  alert_id INTEGER PRIMARY KEY AUTOINCREMENT,
  symbol TEXT NOT NULL,
  bar_open_ts INTEGER NOT NULL,
  state TEXT NOT NULL,
  cooldown_suppressed INTEGER NOT NULL DEFAULT 0,
  created_at INTEGER NOT NULL,
  UNIQUE (symbol, bar_open_ts, state)
);

CREATE TABLE IF NOT EXISTS outcomes (
  symbol TEXT NOT NULL,
  bar_open_ts INTEGER NOT NULL,
  ret_fwd_1h REAL,
  ret_fwd_4h REAL,
  ret_fwd_24h REAL,
  ret_fwd_72h REAL,
  ret_fwd_4h_vs_btc REAL,
  ret_fwd_24h_vs_btc REAL,
  ret_fwd_72h_vs_btc REAL,
  in_universe INTEGER NOT NULL,
  price_def TEXT NOT NULL DEFAULT 'kline_close',
  updated_at INTEGER NOT NULL,
  PRIMARY KEY (symbol, bar_open_ts)
);

CREATE TABLE IF NOT EXISTS data_health (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts INTEGER NOT NULL,
  source TEXT NOT NULL,
  symbol TEXT,
  expected_ts INTEGER,
  actual_ts INTEGER,
  age_sec REAL,
  success INTEGER NOT NULL,
  http_status INTEGER,
  latency_ms REAL,
  rows_expected INTEGER,
  rows_got INTEGER,
  null_rate REAL,
  ts_semantics TEXT,
  error TEXT
);

CREATE TABLE IF NOT EXISTS raw_revisions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  table_name TEXT NOT NULL,
  symbol TEXT NOT NULL,
  bar_open_ts INTEGER,
  event_ts INTEGER,
  old_hash TEXT,
  new_hash TEXT,
  old_payload TEXT,
  new_payload TEXT,
  revised_at INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_funding_symbol_time ON raw_funding(symbol, funding_time);
CREATE INDEX IF NOT EXISTS idx_funding_info_symbol_time ON funding_info_snapshot(symbol, observed_at);
CREATE INDEX IF NOT EXISTS idx_health_source_ts ON data_health(source, ts);
