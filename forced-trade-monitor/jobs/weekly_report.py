"""Incremental-information question. Empty until 30 complete days exist."""

SQL = """
-- Control: ret_4h_vs_btc < 0, same universe hour.
-- Treatment: crowded_long_under_pressure hit = 1.
-- Compare mean ret_fwd_24h. Not a trading rule.
SELECT
  CASE WHEN s.hit = 1 THEN 's1' ELSE 'weak_vs_btc' END AS bucket,
  AVG(o.ret_fwd_24h) AS mean_fwd_24h,
  COUNT(*) AS n
FROM features_1h f
JOIN outcomes o USING (symbol, bar_open_ts)
LEFT JOIN states_1h s
  ON s.symbol = f.symbol
 AND s.bar_open_ts = f.bar_open_ts
 AND s.state = 'crowded_long_under_pressure'
WHERE o.in_universe = 1
  AND o.ret_fwd_24h IS NOT NULL
  AND f.ret_4h_vs_btc < 0
GROUP BY 1;
"""


def main() -> None:
    print(SQL)


if __name__ == "__main__":
    main()
