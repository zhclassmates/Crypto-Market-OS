# forced-trade-monitor v1.1

研究雷达，不是执行系统。规格见 `SPEC.md`。

路径只有两条：`features → states → alerts`，以及 `features → outcomes`。S4 关闭。告警不回写研究表。

```bash
python scripts/init_db.py
PYTHONPATH=src pytest
```

30 天问题从本库攒满 30 个完整日开始算。OI 与 taker 官方历史大约只有 30 天，不回补更早。
