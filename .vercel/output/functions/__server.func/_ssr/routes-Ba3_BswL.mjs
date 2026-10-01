import { i as __toESM } from "../_runtime.mjs";
import { b as require_jsx_runtime, q as require_react } from "../_libs/@tanstack/react-router+[...].mjs";
import { n as TSS_SERVER_FUNCTION, r as getServerFnById, t as createServerFn } from "./ssr.mjs";
import { a as ExternalLink, i as Pause, n as RefreshCw, r as Play } from "../_libs/lucide-react.mjs";
//#region node_modules/.nitro/vite/services/ssr/assets/routes-Ba3_BswL.js
var import_react = /* @__PURE__ */ __toESM(require_react());
var import_jsx_runtime = require_jsx_runtime();
var LADDER = {
	"ts": 1790772486799,
	"coverage": {
		"active": 461,
		"universe": 819,
		"volKnown": 451,
		"liqKnown": 242
	},
	"kinds": {
		"stock": 146,
		"paired": 11,
		"meme": 303,
		"eco": 1,
		"mirror": 0
	},
	"rungs": [
		{
			"key": "onchain",
			"track": "base",
			"prev": null,
			"label": "Robinhood 链上",
			"count": 461,
			"source": "近 24h 有成交/流动性或已核实到某个场所"
		},
		{
			"key": "aster",
			"track": "cex",
			"prev": "onchain",
			"label": "Aster",
			"count": 10,
			"source": "链上价与 Aster 永续报价比对"
		},
		{
			"key": "hl",
			"track": "cex",
			"prev": "onchain",
			"label": "Hyperliquid",
			"count": 3,
			"source": "链上价与 HL 永续中间价比对"
		},
		{
			"key": "bnAlpha",
			"track": "cex",
			"prev": "aster",
			"label": "币安 Alpha",
			"count": 4,
			"source": "按合约地址核实"
		},
		{
			"key": "bnPerp",
			"track": "cex",
			"prev": "bnAlpha",
			"label": "币安永续",
			"count": 3,
			"source": "按合约地址或报价核实"
		},
		{
			"key": "bnSpot",
			"track": "cex",
			"prev": "bnPerp",
			"label": "币安现货",
			"count": 0,
			"source": "按合约地址核实"
		},
		{
			"key": "kr",
			"track": "cex",
			"prev": "bnSpot",
			"label": "韩所",
			"count": 3,
			"source": "Upbit / Bithumb 的韩元价按 BTC 汇率折成美元后与链上价比对"
		},
		{
			"key": "rhQuoted",
			"track": "rh",
			"prev": "onchain",
			"label": "RH 有行情页",
			"count": 7,
			"source": "链上价与 App 报价比对"
		},
		{
			"key": "rhSpot",
			"track": "rh",
			"prev": "rhQuoted",
			"label": "RH 可交易",
			"count": 2,
			"source": "App 里能真正买入"
		}
	],
	"funnel": [
		{
			"key": "onchain",
			"track": "base",
			"prev": null,
			"count": 461,
			"fromPrev": 461,
			"conversionFromPrevPct": 100,
			"dropFromPrev": 0,
			"skippedPrev": 0
		},
		{
			"key": "aster",
			"track": "cex",
			"prev": "onchain",
			"count": 10,
			"fromPrev": 10,
			"conversionFromPrevPct": 2.17,
			"dropFromPrev": 451,
			"skippedPrev": 0
		},
		{
			"key": "hl",
			"track": "cex",
			"prev": "onchain",
			"count": 3,
			"fromPrev": 3,
			"conversionFromPrevPct": .65,
			"dropFromPrev": 458,
			"skippedPrev": 0
		},
		{
			"key": "bnAlpha",
			"track": "cex",
			"prev": "aster",
			"count": 4,
			"fromPrev": 3,
			"conversionFromPrevPct": 30,
			"dropFromPrev": 7,
			"skippedPrev": 1
		},
		{
			"key": "bnPerp",
			"track": "cex",
			"prev": "bnAlpha",
			"count": 3,
			"fromPrev": 1,
			"conversionFromPrevPct": 25,
			"dropFromPrev": 3,
			"skippedPrev": 2
		},
		{
			"key": "bnSpot",
			"track": "cex",
			"prev": "bnPerp",
			"count": 0,
			"fromPrev": 0,
			"conversionFromPrevPct": 0,
			"dropFromPrev": 3,
			"skippedPrev": 0
		},
		{
			"key": "kr",
			"track": "cex",
			"prev": "bnSpot",
			"count": 3,
			"fromPrev": 0,
			"conversionFromPrevPct": null,
			"dropFromPrev": 0,
			"skippedPrev": 3
		},
		{
			"key": "rhQuoted",
			"track": "rh",
			"prev": "onchain",
			"count": 7,
			"fromPrev": 7,
			"conversionFromPrevPct": 1.52,
			"dropFromPrev": 454,
			"skippedPrev": 0
		},
		{
			"key": "rhSpot",
			"track": "rh",
			"prev": "rhQuoted",
			"count": 2,
			"fromPrev": 2,
			"conversionFromPrevPct": 28.57,
			"dropFromPrev": 5,
			"skippedPrev": 0
		}
	],
	"gates": {
		"first": {
			"label": "上第一个交易所",
			"base": 5.7,
			"note": "干净样本 n=9，本链毕业生",
			"bars": {
				"holders": {
					"bar": 9600,
					"w": 35,
					"label": "持币地址",
					"lift": 9.5,
					"note": "唯一没有反向因果的指标"
				},
				"mcap": {
					"bar": 83e5,
					"w": 20,
					"label": "市值",
					"lift": 7
				},
				"liq": {
					"bar": 44e4,
					"w": 15,
					"label": "池深",
					"lift": 5.1,
					"note": "有一半是上市后长出来的，已调低权重"
				},
				"ageD": {
					"bar": 11,
					"w": 10,
					"label": "币龄(天)",
					"lift": null
				},
				"ct": {
					"bar": 2,
					"w": 20,
					"label": "CT 热度",
					"lift": null,
					"note": "链上看不到的独立信号"
				}
			}
		},
		"cex": {
			"label": "从 Alpha 进币安 CEX",
			"base": 17.6,
			"note": "外部样本 n=676，币安 Alpha 全体在架币",
			"bars": {
				"mcap": {
					"bar": 165e5,
					"w": 45,
					"label": "市值",
					"lift": 2.33,
					"note": "这道门几乎只看体量"
				},
				"vol24h": {
					"bar": 9500,
					"w": 15,
					"label": "24h 成交",
					"lift": 1.28
				},
				"liq": {
					"bar": 53700,
					"w": 15,
					"label": "流动性",
					"lift": 1.2
				},
				"holders": {
					"bar": 8300,
					"w": 15,
					"label": "持币地址",
					"lift": 1.15,
					"note": "到这一级已经不太重要"
				},
				"ct": {
					"bar": 2,
					"w": 10,
					"label": "CT 热度",
					"lift": null
				}
			}
		}
	},
	"venueRules": {
		"aster": {
			"venue": "Aster",
			"kind": "published",
			"src": "AOS-2 / AOS-1（docs.asterdex.com）",
			"must": [
				{
					"k": "mcapMin",
					"v": 1e7,
					"text": "流通市值 ≥ $1,000 万（申请时）"
				},
				{
					"k": "prereq",
					"text": "代币须已在币安 Alpha 或 Tier 2 交易所上市"
				},
				{
					"k": "stake",
					"text": "质押 100 万 ASTER，锁 4 年，不可提前赎回（投票被否则全额退还）"
				}
			],
			"note": "Aster 的资格线直接引用币安地位，现货上币费也按「是否已在币安 Alpha」分档（2 万 / 5 万 USDT）。所以它是币安 Alpha 的下游，不是平行选项。上线走验证人投票，T+1。"
		},
		"hl": {
			"venue": "Hyperliquid",
			"kind": "published-vague",
			"src": "官方 FAQ",
			"must": [{
				"k": "demand",
				"text": "官方原话只有一句：“Perps listings are based on community request and organic demand”"
			}],
			"note": "没有申请表、没有费用、没有评分标准。新标的一律 3 倍杠杆、仅逐仓，站稳了再逐级提杠杆 —— 杠杆档位就是事实上的公开评分卡。对这道门，CT 讨论热度不是辅助信号，它就是机制本身。"
		},
		"bnAlpha": {
			"venue": "币安 Alpha",
			"kind": "discretionary",
			"src": "官方 FAQ / 2025-04 上币信息公告",
			"must": [{
				"k": "none",
				"text": "无任何公开定量门槛。官方明示「目前我们不接受用户的代币推荐」"
			}],
			"note": "只给了质性维度：项目基本面与表现、代币经济、技术风险、团队背景与合规审查。所以这道门只能用统计反推 —— 本页拿它自己公布的 676 个在架币做参照系。另注：常被引用的「17% 毕业到现货」是在拿过空投的子集上算的，全样本约 8~10%。"
		},
		"kr": {
			"venue": "韩所（Upbit / Bithumb）",
			"kind": "published",
			"src": "DAXA《가상자산 거래지원 모범사례》2024-07 施行、2025-06 大修",
			"must": [
				{
					"k": "community",
					"v": 1e5,
					"text": "meme 类：在线社区成员 < 10 万 → 形式不合格"
				},
				{
					"k": "txs",
					"v": 1e6,
					"text": "meme 类：主网交易/合约数 < 100 万 → 形式不合格"
				},
				{
					"k": "young",
					"v": 5e4,
					"text": "发行未满一年的改测：前 30 天累计交易 < 5 万 → 形式不合格"
				}
			],
			"note": "唯一的现实路径是豁免条款：在 2 个「合格海外市场」交易满 6 个月，可整体绕过 meme 社区规模测试。但 DAXA 承诺过的合格市场名单至今没公布。另有僵尸币季度复查：市值低于 40 亿韩元连续两季即进下架流程。"
		},
		"rhSpot": {
			"venue": "Robinhood App",
			"kind": "none",
			"src": "FY2025 10-K",
			"must": [{
				"k": "committee",
				"text": "没有公开框架、没有申请表。10-K 里只说 Crypto Listing Frameworks 是「内部政策」，由上币委员会自由裁量"
			}],
			"note": "成文的唯一红线是证券属性，且会连坐「具有类似特征的其他资产」。纽约另受 NYDFS 约束：流通量低于总量 35%、交易所自发币、桥接币不得自认证。CASHCAT 走通过一次，路径是深度原生流动性 + 成为该链旗舰文化资产 + 先上 Bitstamp（Robinhood 旗下）—— 只有一个样本，别过拟合。"
		}
	},
	"listingHistory": {
		"note": "「发射台出身」指在 bonding curve 上发出来的币，不含发射台自己的平台币（PUMP/VIRTUAL/PONS）。",
		"bnSpot": {
			"n": 11,
			"since": "全部历史",
			"detail": "pump.fun 2 个（ACT、PNUT，同在 2024-11-11，此后 23 个月再没有）· four.meme 6 个 · Flap 2 个 · Virtuals 1 个"
		},
		"bnPerp": {
			"n": 18,
			"since": "全部历史",
			"detail": "仅 pump.fun 一家就有约 18 个 —— 永续的可及性大约是现货的 9 倍"
		},
		"kr": {
			"n": 2,
			"since": "全部历史",
			"detail": "Upbit 只上过 MOODENG（2025-07-03，KRW）和 USELESS（2026-09-08，仅 BTC/USDT）"
		},
		"coinbase": {
			"n": 5,
			"since": "全部历史",
			"detail": "MOODENG、PNUT、FARTCOIN、TROLL、USELESS"
		},
		"insight": "BNB 链系发射台（four.meme + Flap）拿走了 11 个币安现货名额里的 8 个 —— 决定能不能上的是发射台在不在交易所自己的漏斗里，不是代币质量。Robinhood 链 2026-09-08 起已接入币安 Alpha 2.0（可充提），这是本链最有价值的一个位置变化。",
		"pons": "PONS 作为本链发射台的平台币，2026-09-06 已上币安永续，峰值市值约 $6.91 亿 —— 平台币比它发出来的任何币都更容易到 CEX。"
	},
	"alphaRef": {
		"n": 682,
		"ageConversion": {
			"d30": {
				"n": 17,
				"cex": 0
			},
			"d90": {
				"n": 9,
				"cex": 2
			},
			"d180": {
				"n": 83,
				"cex": 6
			},
			"older": {
				"n": 573,
				"cex": 110
			}
		},
		"rhOnAlpha": [
			{
				"symbol": "MEME",
				"at": 1788949303152,
				"score": 100,
				"cex": false,
				"liq": 4238211.411204098,
				"holders": 30085,
				"mcap": 23751026.65197476
			},
			{
				"symbol": "AI",
				"at": 1788513371688,
				"score": 100,
				"cex": false,
				"liq": 7171811.570638808,
				"holders": 54023,
				"mcap": 179299457.50031307
			},
			{
				"symbol": "UP",
				"at": 1788510649951,
				"score": 110,
				"cex": false,
				"liq": 2781168.1080661668,
				"holders": 15180,
				"mcap": 8286568.15157033
			},
			{
				"symbol": "CASHCAT",
				"at": 1788510620856,
				"score": 100,
				"cex": false,
				"liq": 14247137.531102465,
				"holders": 113733,
				"mcap": 175706551.65044266
			},
			{
				"symbol": "PONS",
				"at": 1788356024965,
				"score": 110,
				"cex": false,
				"liq": 27569391.291514114,
				"holders": 101784,
				"mcap": 386947547.98745954
			}
		]
	},
	"advancedFeed": [
		{
			"symbol": "AVA",
			"kind": "meme",
			"vol24h": .03,
			"stage": 5,
			"stageLabel": "韩所",
			"at": 17897682e5
		},
		{
			"symbol": "BONER",
			"kind": "meme",
			"vol24h": 2009892,
			"stage": 1,
			"stageLabel": "永续 DEX",
			"at": 17887857e5
		},
		{
			"symbol": "PONS",
			"kind": "eco",
			"vol24h": 1465394.19,
			"stage": 3,
			"stageLabel": "币安永续",
			"at": 17886771e5
		},
		{
			"symbol": "PAIR",
			"kind": "paired",
			"vol24h": 191336.25,
			"stage": 1,
			"stageLabel": "永续 DEX",
			"at": 17886696e5
		},
		{
			"symbol": "SHROOM",
			"kind": "meme",
			"vol24h": 2254425,
			"stage": 1,
			"stageLabel": "永续 DEX",
			"at": 17886123e5
		}
	],
	"ruledOut": [
		{
			"symbol": "VRAX",
			"vol24h": 23546398.68081081,
			"liq": 357308.85459999996,
			"why": "换手 66 倍（成交÷池深）。毕业生的中位数是 1.1，没毕业的 75 分位是 18.7 —— 这是刷量不是热度",
			"all": ["wash", "young"]
		},
		{
			"symbol": "LIQCAT",
			"vol24h": 18167160.9815472,
			"liq": 184236.3988,
			"why": "换手 99 倍（成交÷池深）。毕业生的中位数是 1.1，没毕业的 75 分位是 18.7 —— 这是刷量不是热度",
			"all": ["wash", "young"]
		},
		{
			"symbol": "STKDOG",
			"vol24h": 17406272.2529231,
			"liq": 61082.5441,
			"why": "换手 285 倍（成交÷池深）。毕业生的中位数是 1.1，没毕业的 75 分位是 18.7 —— 这是刷量不是热度",
			"all": ["wash", "young"]
		},
		{
			"symbol": "VRAX",
			"vol24h": 16103977.0883031,
			"liq": 248183.2838,
			"why": "换手 65 倍（成交÷池深）。毕业生的中位数是 1.1，没毕业的 75 分位是 18.7 —— 这是刷量不是热度",
			"all": ["wash", "young"]
		},
		{
			"symbol": "NFLOAT",
			"vol24h": 13308798.2662903,
			"liq": 146540.6202,
			"why": "换手 91 倍（成交÷池深）。毕业生的中位数是 1.1，没毕业的 75 分位是 18.7 —— 这是刷量不是热度",
			"all": ["wash", "young"]
		},
		{
			"symbol": "OFY",
			"vol24h": 9055561.71468987,
			"liq": 3384.5554,
			"why": "换手 2676 倍（成交÷池深）。毕业生的中位数是 1.1，没毕业的 75 分位是 18.7 —— 这是刷量不是热度",
			"all": [
				"wash",
				"thin",
				"young"
			]
		},
		{
			"symbol": "OCTCAT",
			"vol24h": 8768167.27468071,
			"liq": 254917.4357,
			"why": "换手 34 倍（成交÷池深）。毕业生的中位数是 1.1，没毕业的 75 分位是 18.7 —— 这是刷量不是热度",
			"all": ["wash", "young"]
		},
		{
			"symbol": "SI",
			"vol24h": 8578559.86693491,
			"liq": 219932.5605,
			"why": "换手 39 倍（成交÷池深）。毕业生的中位数是 1.1，没毕业的 75 分位是 18.7 —— 这是刷量不是热度",
			"all": ["wash"]
		}
	],
	"candidates": [
		{
			"symbol": "AI",
			"address": "0x2e8c31162b855a2ffa90f6f8634643ad6f111e18",
			"kind": "paired",
			"gate": "cex",
			"next": "币安永续",
			"vol24h": 12517799.29,
			"liq": 1761347.81,
			"turn": 7.106943454853473,
			"raw": {
				"liq": 1761347.81,
				"vol24h": 12517799.29,
				"mcap": 179624790.211728,
				"ageD": 11.691814780092592,
				"holders": null,
				"ct": null
			},
			"alphaPct": {
				"liq": 87,
				"mcap": 95,
				"vol": 98
			},
			"asterRule": {
				"mcapOk": true,
				"prereqOk": true
			},
			"already": ["aster", "bnAlpha"]
		},
		{
			"symbol": "GOOSE",
			"address": "0x348cc963411fb82cd6e0b64345714fec94f242cb",
			"kind": "meme",
			"gate": "first",
			"next": "永续 DEX（Aster / Hyperliquid）",
			"vol24h": 20076166,
			"liq": 11754249.06,
			"turn": 1.7079922245581547,
			"raw": {
				"liq": 11754249.06,
				"vol24h": 20076166,
				"mcap": 116368151.1,
				"ageD": null,
				"holders": null,
				"ct": null
			},
			"alphaPct": {
				"liq": 99,
				"mcap": 93,
				"vol": 98
			},
			"asterRule": {
				"mcapOk": true,
				"prereqOk": false
			},
			"already": []
		},
		{
			"symbol": "ORBIO",
			"address": "0xaa07a0e9209e16ac99708c3ec70159c6ef3128a3",
			"kind": "meme",
			"gate": "first",
			"next": "永续 DEX（Aster / Hyperliquid）",
			"vol24h": 2953398,
			"liq": 1021033.06,
			"turn": 2.8925586405595913,
			"raw": {
				"liq": 1021033.06,
				"vol24h": 2953398,
				"mcap": 58142785,
				"ageD": null,
				"holders": null,
				"ct": null
			},
			"alphaPct": {
				"liq": 76,
				"mcap": 86,
				"vol": 94
			},
			"asterRule": {
				"mcapOk": true,
				"prereqOk": false
			},
			"already": []
		},
		{
			"symbol": "BONER",
			"address": "0x98096d17e191b3da1d5f99a6d7b3584351b11e18",
			"kind": "meme",
			"gate": "first",
			"next": "币安 Alpha",
			"vol24h": 2009892,
			"liq": 397794.72,
			"turn": 5.052585916675818,
			"raw": {
				"liq": 397794.72,
				"vol24h": 2009892,
				"mcap": 48558048,
				"ageD": null,
				"holders": null,
				"ct": null
			},
			"alphaPct": {
				"liq": 59,
				"mcap": 84,
				"vol": 93
			},
			"asterRule": {
				"mcapOk": true,
				"prereqOk": false
			},
			"already": ["aster"]
		},
		{
			"symbol": "INDEX",
			"address": "0x56910d4409f3a0c78c64dd8d0545ff0705389870",
			"kind": "meme",
			"gate": "first",
			"next": "永续 DEX（Aster / Hyperliquid）",
			"vol24h": 110992.58,
			"liq": 781541.6,
			"turn": .14201749465415534,
			"raw": {
				"liq": 781541.6,
				"vol24h": 110992.58,
				"mcap": 23656841.6074674,
				"ageD": null,
				"holders": null,
				"ct": null
			},
			"alphaPct": {
				"liq": 70,
				"mcap": 72,
				"vol": 64
			},
			"asterRule": {
				"mcapOk": true,
				"prereqOk": false
			},
			"already": []
		},
		{
			"symbol": "CHUMP",
			"address": "0x0e0d2c89a5a019fe1cf762e5e33187631dacc21b",
			"kind": "meme",
			"gate": "first",
			"next": "永续 DEX（Aster / Hyperliquid）",
			"vol24h": 1944381,
			"liq": 867320.6,
			"turn": 2.2418249952785625,
			"raw": {
				"liq": 867320.6,
				"vol24h": 1944381,
				"mcap": 23171879,
				"ageD": null,
				"holders": null,
				"ct": null
			},
			"alphaPct": {
				"liq": 72,
				"mcap": 72,
				"vol": 93
			},
			"asterRule": {
				"mcapOk": true,
				"prereqOk": false
			},
			"already": []
		},
		{
			"symbol": "PIPEDOG",
			"address": "0x5cb6f181081301b44905f3ae15419112ecabd8a6",
			"kind": "meme",
			"gate": "first",
			"next": "永续 DEX（Aster / Hyperliquid）",
			"vol24h": 145221.81,
			"liq": 7964137.18,
			"turn": .01823446868352411,
			"raw": {
				"liq": 7964137.18,
				"vol24h": 145221.81,
				"mcap": 21548272,
				"ageD": null,
				"holders": null,
				"ct": null
			},
			"alphaPct": {
				"liq": 98,
				"mcap": 70,
				"vol": 67
			},
			"asterRule": {
				"mcapOk": true,
				"prereqOk": false
			},
			"already": []
		},
		{
			"symbol": "DELTA",
			"address": "0xe8ffd7e24187f72afb08d75b1bb13088a989a791",
			"kind": "meme",
			"gate": "first",
			"next": "币安 Alpha",
			"vol24h": 1306468,
			"liq": 1270631.32,
			"turn": 1.028203838073187,
			"raw": {
				"liq": 1270631.32,
				"vol24h": 1306468,
				"mcap": 19922912,
				"ageD": null,
				"holders": null,
				"ct": null
			},
			"alphaPct": {
				"liq": 82,
				"mcap": 69,
				"vol": 91
			},
			"asterRule": {
				"mcapOk": true,
				"prereqOk": false
			},
			"already": ["aster"]
		},
		{
			"symbol": "BUN",
			"address": "0x07ebb29a38fbcb41563817e5e19f2cec619c90d2",
			"kind": "meme",
			"gate": "first",
			"next": "永续 DEX（Aster / Hyperliquid）",
			"vol24h": 2929367,
			"liq": 930965.4,
			"turn": 3.1465906251725357,
			"raw": {
				"liq": 930965.4,
				"vol24h": 2929367,
				"mcap": 19217801,
				"ageD": null,
				"holders": null,
				"ct": null
			},
			"alphaPct": {
				"liq": 74,
				"mcap": 68,
				"vol": 94
			},
			"asterRule": {
				"mcapOk": true,
				"prereqOk": false
			},
			"already": []
		},
		{
			"symbol": "HOOKR",
			"address": "0x18e674231a58c239dc7daedcffe15ec3a24cff5c",
			"kind": "meme",
			"gate": "first",
			"next": "永续 DEX（Aster / Hyperliquid）",
			"vol24h": 4221523,
			"liq": 969354.08,
			"turn": 4.35498553841131,
			"raw": {
				"liq": 969354.08,
				"vol24h": 4221523,
				"mcap": 15823009.5,
				"ageD": null,
				"holders": null,
				"ct": null
			},
			"alphaPct": {
				"liq": 75,
				"mcap": 64,
				"vol": 96
			},
			"asterRule": {
				"mcapOk": true,
				"prereqOk": false
			},
			"already": []
		},
		{
			"symbol": "ZZZ",
			"address": "0x7dbf38976f6d3b9c529e7d9484a71898b409ee6a",
			"kind": "meme",
			"gate": "first",
			"next": "永续 DEX（Aster / Hyperliquid）",
			"vol24h": 438829.53,
			"liq": 415872.47,
			"turn": 1.0552021632978015,
			"raw": {
				"liq": 415872.47,
				"vol24h": 438829.53,
				"mcap": 15370576,
				"ageD": null,
				"holders": null,
				"ct": null
			},
			"alphaPct": {
				"liq": 60,
				"mcap": 64,
				"vol": 81
			},
			"asterRule": {
				"mcapOk": true,
				"prereqOk": false
			},
			"already": []
		},
		{
			"symbol": "SHROOM",
			"address": "0xab093def657f15df31b33922a95e047add645b29",
			"kind": "meme",
			"gate": "first",
			"next": "币安 Alpha",
			"vol24h": 2254425,
			"liq": 471810.38,
			"turn": 4.778243751229042,
			"raw": {
				"liq": 471810.38,
				"vol24h": 2254425,
				"mcap": 14641153,
				"ageD": null,
				"holders": null,
				"ct": null
			},
			"alphaPct": {
				"liq": 63,
				"mcap": 64,
				"vol": 93
			},
			"asterRule": {
				"mcapOk": true,
				"prereqOk": false
			},
			"already": ["aster"]
		},
		{
			"symbol": "UP",
			"address": "0x57c0e45cb534413d1c20a4240955d6bb250bb4f1",
			"kind": "meme",
			"gate": "cex",
			"next": "币安永续",
			"vol24h": 1957286.72,
			"liq": 1813206.98,
			"turn": 1.0794612758439746,
			"raw": {
				"liq": 1813206.98,
				"vol24h": 1957286.72,
				"mcap": 9264094.08384416,
				"ageD": null,
				"holders": null,
				"ct": null
			},
			"alphaPct": {
				"liq": 87,
				"mcap": 56,
				"vol": 93
			},
			"asterRule": {
				"mcapOk": false,
				"prereqOk": true
			},
			"already": ["bnAlpha"]
		},
		{
			"symbol": "PROLOGUE",
			"address": "0xb9972ca7188e511174947e3936a5315ac7073277",
			"kind": "meme",
			"gate": "first",
			"next": "永续 DEX（Aster / Hyperliquid）",
			"vol24h": 455240.11,
			"liq": 683911.84,
			"turn": .665641510168913,
			"raw": {
				"liq": 683911.84,
				"vol24h": 455240.11,
				"mcap": 8655635,
				"ageD": null,
				"holders": null,
				"ct": null
			},
			"alphaPct": {
				"liq": 69,
				"mcap": 55,
				"vol": 81
			},
			"asterRule": {
				"mcapOk": false,
				"prereqOk": false
			},
			"already": []
		},
		{
			"symbol": "MOO",
			"address": "0xd9db30bb0d2b8d2eae3826a1372117e058791e18",
			"kind": "meme",
			"gate": "first",
			"next": "永续 DEX（Aster / Hyperliquid）",
			"vol24h": 2252983,
			"liq": 918840.38,
			"turn": 2.4519851859362123,
			"raw": {
				"liq": 918840.38,
				"vol24h": 2252983,
				"mcap": 8216544,
				"ageD": null,
				"holders": null,
				"ct": null
			},
			"alphaPct": {
				"liq": 74,
				"mcap": 54,
				"vol": 93
			},
			"asterRule": {
				"mcapOk": false,
				"prereqOk": false
			},
			"already": []
		},
		{
			"symbol": "RAXOL",
			"address": "0xf44702b17d9abd53815f703e772f35e9c71a53af",
			"kind": "meme",
			"gate": "first",
			"next": "永续 DEX（Aster / Hyperliquid）",
			"vol24h": 166399.24,
			"liq": 423659.22,
			"turn": .3927667147194389,
			"raw": {
				"liq": 423659.22,
				"vol24h": 166399.24,
				"mcap": 6683800,
				"ageD": null,
				"holders": null,
				"ct": null
			},
			"alphaPct": {
				"liq": 61,
				"mcap": 50,
				"vol": 68
			},
			"asterRule": {
				"mcapOk": false,
				"prereqOk": false
			},
			"already": []
		},
		{
			"symbol": "FRONG",
			"address": "0x6245e67affa44a23077f0ea7f981a8dc743a0c47",
			"kind": "meme",
			"gate": "first",
			"next": "永续 DEX（Aster / Hyperliquid）",
			"vol24h": 748193,
			"liq": 725785.79,
			"turn": 1.030873034866114,
			"raw": {
				"liq": 725785.79,
				"vol24h": 748193,
				"mcap": 5680677,
				"ageD": null,
				"holders": null,
				"ct": null
			},
			"alphaPct": {
				"liq": 69,
				"mcap": 48,
				"vol": 86
			},
			"asterRule": {
				"mcapOk": false,
				"prereqOk": false
			},
			"already": []
		},
		{
			"symbol": "ARROW",
			"address": "0xf2915d1e3c1b0c769d0c756ec43f1c1f6c99cd03",
			"kind": "meme",
			"gate": "first",
			"next": "永续 DEX（Aster / Hyperliquid）",
			"vol24h": 69256,
			"liq": 240385.07,
			"turn": .2881044151369301,
			"raw": {
				"liq": 240385.07,
				"vol24h": 69256,
				"mcap": 3726459,
				"ageD": null,
				"holders": null,
				"ct": null
			},
			"alphaPct": {
				"liq": 49,
				"mcap": 44,
				"vol": 60
			},
			"asterRule": {
				"mcapOk": false,
				"prereqOk": false
			},
			"already": []
		},
		{
			"symbol": "BUCKET",
			"address": "0xbc9e7b1c5c0081f4ae85e71ec95703d3dec9ffad",
			"kind": "meme",
			"gate": "first",
			"next": "永续 DEX（Aster / Hyperliquid）",
			"vol24h": 230555,
			"liq": 158660.1,
			"turn": 1.4531378714623273,
			"raw": {
				"liq": 158660.1,
				"vol24h": 230555,
				"mcap": 3550354,
				"ageD": null,
				"holders": null,
				"ct": null
			},
			"alphaPct": {
				"liq": 42,
				"mcap": 43,
				"vol": 73
			},
			"asterRule": {
				"mcapOk": false,
				"prereqOk": false
			},
			"already": []
		},
		{
			"symbol": "HARMONIC",
			"address": "0xdee52f2ab639b6942b0d0f0565400b93b7a0fbe5",
			"kind": "meme",
			"gate": "first",
			"next": "永续 DEX（Aster / Hyperliquid）",
			"vol24h": 1053323,
			"liq": 178031.39,
			"turn": 5.916501578738446,
			"raw": {
				"liq": 178031.39,
				"vol24h": 1053323,
				"mcap": 3076994,
				"ageD": null,
				"holders": null,
				"ct": null
			},
			"alphaPct": {
				"liq": 44,
				"mcap": 41,
				"vol": 88
			},
			"asterRule": {
				"mcapOk": false,
				"prereqOk": false
			},
			"already": []
		},
		{
			"symbol": "VEX",
			"address": "0x8ff92566f2e81bdd68edfaa8cde73942a723796b",
			"kind": "meme",
			"gate": "first",
			"next": "永续 DEX（Aster / Hyperliquid）",
			"vol24h": 334047.42,
			"liq": 329095.76,
			"turn": 1.0150462588761398,
			"raw": {
				"liq": 329095.76,
				"vol24h": 334047.42,
				"mcap": 2880384,
				"ageD": null,
				"holders": null,
				"ct": null
			},
			"alphaPct": {
				"liq": 56,
				"mcap": 41,
				"vol": 78
			},
			"asterRule": {
				"mcapOk": false,
				"prereqOk": false
			},
			"already": []
		},
		{
			"symbol": "PARE",
			"address": "0x15d36b6a28d8327abc7afabf0f106ae2c9af5c4d",
			"kind": "meme",
			"gate": "first",
			"next": "永续 DEX（Aster / Hyperliquid）",
			"vol24h": 455201,
			"liq": 158094.91,
			"turn": 2.8792894091277197,
			"raw": {
				"liq": 158094.91,
				"vol24h": 455201,
				"mcap": 2676378,
				"ageD": null,
				"holders": null,
				"ct": null
			},
			"alphaPct": {
				"liq": 42,
				"mcap": 41,
				"vol": 81
			},
			"asterRule": {
				"mcapOk": false,
				"prereqOk": false
			},
			"already": []
		},
		{
			"symbol": "ASTEROID",
			"address": "0xfd82d8db539b6ace0d50815845133767e24f1e18",
			"kind": "meme",
			"gate": "first",
			"next": "永续 DEX（Aster / Hyperliquid）",
			"vol24h": 31158,
			"liq": 464040.74,
			"turn": .06714496662512864,
			"raw": {
				"liq": 464040.74,
				"vol24h": 31158,
				"mcap": 2641660,
				"ageD": null,
				"holders": null,
				"ct": null
			},
			"alphaPct": {
				"liq": 63,
				"mcap": 40,
				"vol": 51
			},
			"asterRule": {
				"mcapOk": false,
				"prereqOk": false
			},
			"already": []
		},
		{
			"symbol": "MICRODUCK",
			"address": "0xd5f1afea47b1a9eab414d2ee740cf1d6d039e725",
			"kind": "meme",
			"gate": "first",
			"next": "永续 DEX（Aster / Hyperliquid）",
			"vol24h": 598444,
			"liq": 134882.82,
			"turn": 4.436769634561317,
			"raw": {
				"liq": 134882.82,
				"vol24h": 598444,
				"mcap": 2354322,
				"ageD": null,
				"holders": null,
				"ct": null
			},
			"alphaPct": {
				"liq": 39,
				"mcap": 39,
				"vol": 84
			},
			"asterRule": {
				"mcapOk": false,
				"prereqOk": false
			},
			"already": []
		},
		{
			"symbol": "MANCER",
			"address": "0xc72f232a6869e6cf34dc06129affd07f8a2a246a",
			"kind": "meme",
			"gate": "first",
			"next": "永续 DEX（Aster / Hyperliquid）",
			"vol24h": 156039,
			"liq": 485614.69,
			"turn": .3213226519156577,
			"raw": {
				"liq": 485614.69,
				"vol24h": 156039,
				"mcap": 2094828,
				"ageD": null,
				"holders": null,
				"ct": null
			},
			"alphaPct": {
				"liq": 63,
				"mcap": 38,
				"vol": 68
			},
			"asterRule": {
				"mcapOk": false,
				"prereqOk": false
			},
			"already": []
		},
		{
			"symbol": "ROBIN",
			"address": "0x11b70d0243baf75e85ce03201a92b5b7c33beb59",
			"kind": "meme",
			"gate": "first",
			"next": "永续 DEX（Aster / Hyperliquid）",
			"vol24h": 495149.43,
			"liq": 93401.66,
			"turn": 5.301291540214596,
			"raw": {
				"liq": 93401.66,
				"vol24h": 495149.43,
				"mcap": 1394188.096,
				"ageD": null,
				"holders": null,
				"ct": null
			},
			"alphaPct": {
				"liq": 35,
				"mcap": 36,
				"vol": 82
			},
			"asterRule": {
				"mcapOk": false,
				"prereqOk": false
			},
			"already": []
		},
		{
			"symbol": "ICOIN",
			"address": "0x5d6ef090a1461b11c9427ac319260122d1c61e18",
			"kind": "meme",
			"gate": "first",
			"next": "永续 DEX（Aster / Hyperliquid）",
			"vol24h": 167715,
			"liq": 243327.55,
			"turn": .6892561076622848,
			"raw": {
				"liq": 243327.55,
				"vol24h": 167715,
				"mcap": 831875,
				"ageD": null,
				"holders": null,
				"ct": null
			},
			"alphaPct": {
				"liq": 50,
				"mcap": 31,
				"vol": 69
			},
			"asterRule": {
				"mcapOk": false,
				"prereqOk": false
			},
			"already": []
		},
		{
			"symbol": "FATCOIN",
			"address": "0x12d5ee7917ca430073c3a638ee1e6f0648a98a01",
			"kind": "meme",
			"gate": "first",
			"next": "永续 DEX（Aster / Hyperliquid）",
			"vol24h": 224785,
			"liq": 89168.21,
			"turn": 2.5209096380873857,
			"raw": {
				"liq": 89168.21,
				"vol24h": 224785,
				"mcap": 548149,
				"ageD": null,
				"holders": null,
				"ct": null
			},
			"alphaPct": {
				"liq": 35,
				"mcap": 27,
				"vol": 73
			},
			"asterRule": {
				"mcapOk": false,
				"prereqOk": false
			},
			"already": []
		},
		{
			"symbol": "PERPSHOOD",
			"address": "0x7ba36be14dd06ba492f08be6c1b2979c1d0b652c",
			"kind": "meme",
			"gate": "first",
			"next": "永续 DEX（Aster / Hyperliquid）",
			"vol24h": 98167.01,
			"liq": 73384.84,
			"turn": 1.337701492569855,
			"raw": {
				"liq": 73384.84,
				"vol24h": 98167.01,
				"mcap": 527169,
				"ageD": null,
				"holders": null,
				"ct": null
			},
			"alphaPct": {
				"liq": 33,
				"mcap": 26,
				"vol": 63
			},
			"asterRule": {
				"mcapOk": false,
				"prereqOk": false
			},
			"already": []
		},
		{
			"symbol": "0XZAPS",
			"address": "0xdd90bfa4adc7f4401e611abac692d939f9f4cb07",
			"kind": "meme",
			"gate": "first",
			"next": "永续 DEX（Aster / Hyperliquid）",
			"vol24h": 86852,
			"liq": 189344.73,
			"turn": .458697741415882,
			"raw": {
				"liq": 189344.73,
				"vol24h": 86852,
				"mcap": 438784,
				"ageD": null,
				"holders": null,
				"ct": null
			},
			"alphaPct": {
				"liq": 45,
				"mcap": 24,
				"vol": 62
			},
			"asterRule": {
				"mcapOk": false,
				"prereqOk": false
			},
			"already": []
		},
		{
			"symbol": "AA",
			"address": "0xe2dae1c072b9f66bed999873b94798b2152af7e1",
			"kind": "meme",
			"gate": "first",
			"next": "永续 DEX（Aster / Hyperliquid）",
			"vol24h": 102248,
			"liq": 50202.97,
			"turn": 2.036692251474365,
			"raw": {
				"liq": 50202.97,
				"vol24h": 102248,
				"mcap": 367717,
				"ageD": null,
				"holders": null,
				"ct": null
			},
			"alphaPct": {
				"liq": 30,
				"mcap": 22,
				"vol": 63
			},
			"asterRule": {
				"mcapOk": false,
				"prereqOk": false
			},
			"already": []
		},
		{
			"symbol": "MERRYMEN",
			"address": "0xa15cd06dd305269a0f48bebeb30aa3588fba7b32",
			"kind": "meme",
			"gate": "first",
			"next": "永续 DEX（Aster / Hyperliquid）",
			"vol24h": 42638,
			"liq": 97373.99,
			"turn": .43787873948679723,
			"raw": {
				"liq": 97373.99,
				"vol24h": 42638,
				"mcap": 329637,
				"ageD": null,
				"holders": null,
				"ct": null
			},
			"alphaPct": {
				"liq": 36,
				"mcap": 21,
				"vol": 55
			},
			"asterRule": {
				"mcapOk": false,
				"prereqOk": false
			},
			"already": []
		},
		{
			"symbol": "CINEMA",
			"address": "0x9936403a9cc72cf306063e3496ea387428a3aecd",
			"kind": "meme",
			"gate": "first",
			"next": "永续 DEX（Aster / Hyperliquid）",
			"vol24h": 421071,
			"liq": 58135.05,
			"turn": 7.242979923471296,
			"raw": {
				"liq": 58135.05,
				"vol24h": 421071,
				"mcap": 235863,
				"ageD": null,
				"holders": null,
				"ct": null
			},
			"alphaPct": {
				"liq": 30,
				"mcap": 19,
				"vol": 80
			},
			"asterRule": {
				"mcapOk": false,
				"prereqOk": false
			},
			"already": []
		},
		{
			"symbol": "DOGGIE",
			"address": "0xa9efe2fc94de79734c03051515f48f254ce61e18",
			"kind": "meme",
			"gate": "first",
			"next": "永续 DEX（Aster / Hyperliquid）",
			"vol24h": 18696.62,
			"liq": 116488.7,
			"turn": .16050157654776814,
			"raw": {
				"liq": 116488.7,
				"vol24h": 18696.62,
				"mcap": 201061,
				"ageD": null,
				"holders": null,
				"ct": null
			},
			"alphaPct": {
				"liq": 37,
				"mcap": 18,
				"vol": 46
			},
			"asterRule": {
				"mcapOk": false,
				"prereqOk": false
			},
			"already": []
		},
		{
			"symbol": "BLINK",
			"address": "0x7b630f080807df83908b4ade46ba6396ee66b098",
			"kind": "meme",
			"gate": "first",
			"next": "永续 DEX（Aster / Hyperliquid）",
			"vol24h": 1014733,
			"liq": 159278.65,
			"turn": 6.370803619945297,
			"raw": {
				"liq": 159278.65,
				"vol24h": 1014733,
				"mcap": null,
				"ageD": null,
				"holders": null,
				"ct": null
			},
			"alphaPct": {
				"liq": 42,
				"mcap": null,
				"vol": 88
			},
			"asterRule": {
				"mcapOk": null,
				"prereqOk": false
			},
			"already": []
		},
		{
			"symbol": "STONKBROKER",
			"address": "0xe934e36a439c94017b64a3fece66af12099abf50",
			"kind": "meme",
			"gate": "first",
			"next": "币安 Alpha",
			"vol24h": 378464.28,
			"liq": 2503594.2,
			"turn": .15116838024309212,
			"raw": {
				"liq": 2503594.2,
				"vol24h": 378464.28,
				"mcap": null,
				"ageD": null,
				"holders": null,
				"ct": null
			},
			"alphaPct": {
				"liq": 90,
				"mcap": null,
				"vol": 79
			},
			"asterRule": {
				"mcapOk": null,
				"prereqOk": false
			},
			"already": ["aster"]
		},
		{
			"symbol": "MANY",
			"address": "0xa26992c4268a8a78a4d872fe4bdad2ed03ac287d",
			"kind": "meme",
			"gate": "first",
			"next": "永续 DEX（Aster / Hyperliquid）",
			"vol24h": 279554,
			"liq": 116381.86,
			"turn": 2.4020410053594263,
			"raw": {
				"liq": 116381.86,
				"vol24h": 279554,
				"mcap": null,
				"ageD": null,
				"holders": null,
				"ct": null
			},
			"alphaPct": {
				"liq": 37,
				"mcap": null,
				"vol": 76
			},
			"asterRule": {
				"mcapOk": null,
				"prereqOk": false
			},
			"already": []
		},
		{
			"symbol": "PAIR",
			"address": "0x6b1d42927b1a84ec28fa88d4fc6fa7af404966be",
			"kind": "paired",
			"gate": "first",
			"next": "币安 Alpha",
			"vol24h": 191336.25,
			"liq": 187456.61,
			"turn": 1.02069620271059,
			"raw": {
				"liq": 187456.61,
				"vol24h": 191336.25,
				"mcap": null,
				"ageD": null,
				"holders": null,
				"ct": null
			},
			"alphaPct": {
				"liq": 45,
				"mcap": null,
				"vol": 71
			},
			"asterRule": {
				"mcapOk": null,
				"prereqOk": false
			},
			"already": ["aster"]
		},
		{
			"symbol": "JUGGERNAUT",
			"address": "0xd7321801caae694090694ff55a9323139f043b88",
			"kind": "meme",
			"gate": "first",
			"next": "永续 DEX（Aster / Hyperliquid）",
			"vol24h": 176695.18,
			"liq": 489322.72,
			"turn": .36110152416384833,
			"raw": {
				"liq": 489322.72,
				"vol24h": 176695.18,
				"mcap": null,
				"ageD": null,
				"holders": null,
				"ct": null
			},
			"alphaPct": {
				"liq": 63,
				"mcap": null,
				"vol": 69
			},
			"asterRule": {
				"mcapOk": null,
				"prereqOk": false
			},
			"already": []
		},
		{
			"symbol": "TA",
			"address": "0x9ca1cc0c90d97b4f36c5e2232d4fbd705a73c65d",
			"kind": "meme",
			"gate": "first",
			"next": "永续 DEX（Aster / Hyperliquid）",
			"vol24h": 152719.77,
			"liq": 89376.29,
			"turn": 1.7087280082894467,
			"raw": {
				"liq": 89376.29,
				"vol24h": 152719.77,
				"mcap": null,
				"ageD": null,
				"holders": null,
				"ct": null
			},
			"alphaPct": {
				"liq": 35,
				"mcap": null,
				"vol": 67
			},
			"asterRule": {
				"mcapOk": null,
				"prereqOk": false
			},
			"already": []
		},
		{
			"symbol": "EARN",
			"address": "0xa3b6aee90017b72c0812dc1e013de70eb2917ba3",
			"kind": "meme",
			"gate": "first",
			"next": "永续 DEX（Aster / Hyperliquid）",
			"vol24h": 123073,
			"liq": 267157.96,
			"turn": .46067502536701505,
			"raw": {
				"liq": 267157.96,
				"vol24h": 123073,
				"mcap": null,
				"ageD": null,
				"holders": null,
				"ct": null
			},
			"alphaPct": {
				"liq": 52,
				"mcap": null,
				"vol": 65
			},
			"asterRule": {
				"mcapOk": null,
				"prereqOk": false
			},
			"already": []
		},
		{
			"symbol": "GOOD",
			"address": "0x5f62c57e5c537887117eef828b7e3ad41c009feb",
			"kind": "meme",
			"gate": "first",
			"next": "永续 DEX（Aster / Hyperliquid）",
			"vol24h": 113782,
			"liq": 344850.46,
			"turn": .3299459133677826,
			"raw": {
				"liq": 344850.46,
				"vol24h": 113782,
				"mcap": null,
				"ageD": null,
				"holders": null,
				"ct": null
			},
			"alphaPct": {
				"liq": 57,
				"mcap": null,
				"vol": 64
			},
			"asterRule": {
				"mcapOk": null,
				"prereqOk": false
			},
			"already": []
		},
		{
			"symbol": "NASDANQ",
			"address": "0x51fb76be80ab6daaa345d818f4e06441816b4fea",
			"kind": "meme",
			"gate": "first",
			"next": "永续 DEX（Aster / Hyperliquid）",
			"vol24h": 103871,
			"liq": 147371.32,
			"turn": .7048250636555334,
			"raw": {
				"liq": 147371.32,
				"vol24h": 103871,
				"mcap": null,
				"ageD": null,
				"holders": null,
				"ct": null
			},
			"alphaPct": {
				"liq": 41,
				"mcap": null,
				"vol": 63
			},
			"asterRule": {
				"mcapOk": null,
				"prereqOk": false
			},
			"already": []
		},
		{
			"symbol": "WOJAK",
			"address": "0xace55fe98bab14366dd49ab5aa5df76aa11a3c6f",
			"kind": "meme",
			"gate": "first",
			"next": "永续 DEX（Aster / Hyperliquid）",
			"vol24h": 96905.78,
			"liq": 195246.46,
			"turn": .49632541353118514,
			"raw": {
				"liq": 195246.46,
				"vol24h": 96905.78,
				"mcap": null,
				"ageD": null,
				"holders": null,
				"ct": null
			},
			"alphaPct": {
				"liq": 46,
				"mcap": null,
				"vol": 63
			},
			"asterRule": {
				"mcapOk": null,
				"prereqOk": false
			},
			"already": []
		},
		{
			"symbol": "LILUNI",
			"address": "0x4a6eec8a30b49d289b9fc865fd374b4d61eab8fb",
			"kind": "meme",
			"gate": "first",
			"next": "永续 DEX（Aster / Hyperliquid）",
			"vol24h": 95617,
			"liq": 82889.16,
			"turn": 1.1535525272544684,
			"raw": {
				"liq": 82889.16,
				"vol24h": 95617,
				"mcap": null,
				"ageD": null,
				"holders": null,
				"ct": null
			},
			"alphaPct": {
				"liq": 34,
				"mcap": null,
				"vol": 63
			},
			"asterRule": {
				"mcapOk": null,
				"prereqOk": false
			},
			"already": []
		},
		{
			"symbol": "PEPONS",
			"address": "0xfde368debe9e80f80785064a65719cec1f809dec",
			"kind": "meme",
			"gate": "first",
			"next": "永续 DEX（Aster / Hyperliquid）",
			"vol24h": 95587.1411586603,
			"liq": 149242.3601,
			"turn": .6404826424254618,
			"raw": {
				"liq": 149242.3601,
				"vol24h": 95587.1411586603,
				"mcap": null,
				"ageD": 12.039662002314815,
				"holders": null,
				"ct": null
			},
			"alphaPct": {
				"liq": 41,
				"mcap": null,
				"vol": 63
			},
			"asterRule": {
				"mcapOk": null,
				"prereqOk": false
			},
			"already": []
		},
		{
			"symbol": "PONGO",
			"address": "0xedaee44320107caa714baaec486261a87f27022d",
			"kind": "meme",
			"gate": "first",
			"next": "永续 DEX（Aster / Hyperliquid）",
			"vol24h": 61664.74,
			"liq": 131943.78,
			"turn": .4673561724546621,
			"raw": {
				"liq": 131943.78,
				"vol24h": 61664.74,
				"mcap": null,
				"ageD": null,
				"holders": null,
				"ct": null
			},
			"alphaPct": {
				"liq": 39,
				"mcap": null,
				"vol": 59
			},
			"asterRule": {
				"mcapOk": null,
				"prereqOk": false
			},
			"already": []
		},
		{
			"symbol": "WORTH",
			"address": "0xfb1bcb6817f7b8fa86896d3253b16aeb7bd6a5a8",
			"kind": "meme",
			"gate": "first",
			"next": "永续 DEX（Aster / Hyperliquid）",
			"vol24h": 59773,
			"liq": 137147.59,
			"turn": .4358297510003639,
			"raw": {
				"liq": 137147.59,
				"vol24h": 59773,
				"mcap": null,
				"ageD": null,
				"holders": null,
				"ct": null
			},
			"alphaPct": {
				"liq": 40,
				"mcap": null,
				"vol": 59
			},
			"asterRule": {
				"mcapOk": null,
				"prereqOk": false
			},
			"already": []
		},
		{
			"symbol": "POOLS",
			"address": "0x385b36ff682ab4c76e7c37a66b96aabc466471d5",
			"kind": "meme",
			"gate": "first",
			"next": "永续 DEX（Aster / Hyperliquid）",
			"vol24h": 46260.42,
			"liq": 204417.19,
			"turn": .22630396201023992,
			"raw": {
				"liq": 204417.19,
				"vol24h": 46260.42,
				"mcap": null,
				"ageD": null,
				"holders": null,
				"ct": null
			},
			"alphaPct": {
				"liq": 47,
				"mcap": null,
				"vol": 56
			},
			"asterRule": {
				"mcapOk": null,
				"prereqOk": false
			},
			"already": []
		},
		{
			"symbol": "GRASS",
			"address": "0x16391c40e85fb2246a2c8c17bfa2594c5d3ef84b",
			"kind": "meme",
			"gate": "first",
			"next": "永续 DEX（Aster / Hyperliquid）",
			"vol24h": 39302.93,
			"liq": 100695.38,
			"turn": .3903151266721472,
			"raw": {
				"liq": 100695.38,
				"vol24h": 39302.93,
				"mcap": null,
				"ageD": null,
				"holders": null,
				"ct": null
			},
			"alphaPct": {
				"liq": 36,
				"mcap": null,
				"vol": 54
			},
			"asterRule": {
				"mcapOk": null,
				"prereqOk": false
			},
			"already": []
		}
	],
	"tokens": [
		{
			"symbol": "CASHCAT",
			"address": "0x020bfc650a365f8bb26819deaabf3e21291018b4",
			"kind": "meme",
			"name": "Cash Cat",
			"vol24h": 25002015,
			"liq": 2457993.4238,
			"mcap": null,
			"poolSeenAt": "2026-07-01T19:38:42.000Z",
			"krVenue": "Upbit",
			"reached": {
				"aster": true,
				"hl": true,
				"bnAlpha": true,
				"bnPerp": false,
				"bnSpot": false,
				"kr": true,
				"rhQuoted": true,
				"rhSpot": true
			}
		},
		{
			"symbol": "VRAX",
			"address": "0x94641b97010608c3827fb058074889f19868ff33",
			"kind": "meme",
			"name": "Commander Vrax",
			"vol24h": 23546398.68081081,
			"liq": 357308.85459999996,
			"mcap": null,
			"poolSeenAt": "2026-09-29T23:56:29.000Z",
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "NVDA",
			"address": "0xd0601ce157db5bdc3162bbac2a2c8af5320d9eec",
			"kind": "stock",
			"name": "NVIDIA • Robinhood Token",
			"vol24h": 23377310.19,
			"liq": 7072222.2383,
			"mcap": null,
			"poolSeenAt": "2026-08-06T06:27:27.000Z",
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "GOOSE",
			"address": "0x348cc963411fb82cd6e0b64345714fec94f242cb",
			"kind": "meme",
			"name": "Goose Token",
			"vol24h": 20076166,
			"liq": 11754249.06,
			"mcap": 116368151.1,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "LIQCAT",
			"address": "0x360a4b70230ce96bc5105bee83112ce6270b06a9",
			"kind": "meme",
			"name": "Liquid Cat",
			"vol24h": 18167160.9815472,
			"liq": 184236.3988,
			"mcap": null,
			"poolSeenAt": "2026-09-29T21:54:57.000Z",
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "STKDOG",
			"address": "0x37844c70e005a02824f1bf612fffa064f96a3033",
			"kind": "meme",
			"name": "StockTokenDog",
			"vol24h": 17406272.2529231,
			"liq": 61082.5441,
			"mcap": null,
			"poolSeenAt": "2026-09-29T15:00:56.000Z",
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "VRAX",
			"address": "0x257723230c9cccf6a2df1e7cf67cffcfcf01eeb8",
			"kind": "meme",
			"name": "Commander Vrax",
			"vol24h": 16103977.0883031,
			"liq": 248183.2838,
			"mcap": null,
			"poolSeenAt": "2026-09-30T01:26:26.000Z",
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "NFLOAT",
			"address": "0x21d43454696693beec4d84847c1410f1da9a2d1f",
			"kind": "meme",
			"name": "NightFloat",
			"vol24h": 13308798.2662903,
			"liq": 146540.6202,
			"mcap": null,
			"poolSeenAt": "2026-09-30T05:22:34.000Z",
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "AI",
			"address": "0x2e8c31162b855a2ffa90f6f8634643ad6f111e18",
			"kind": "paired",
			"name": "Artificial Inu",
			"vol24h": 12517799.29,
			"liq": 1761347.81,
			"mcap": 179624790.211728,
			"poolSeenAt": "2026-09-18T20:11:54.000Z",
			"krVenue": "Upbit+Bithumb",
			"reached": {
				"aster": true,
				"hl": false,
				"bnAlpha": true,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "SPCX",
			"address": "0x4a0e65a3eccec6dbe60ae065f2e7bb85fae35eea",
			"kind": "stock",
			"name": "SpaceX • Robinhood Token",
			"vol24h": 11796505.25,
			"liq": 2994144.7065999997,
			"mcap": null,
			"poolSeenAt": "2026-09-19T14:57:57.000Z",
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "OFY",
			"address": "0x77b88d2ddae155cccec58f2750d53da9355b7e40",
			"kind": "meme",
			"name": "OffYield Neobank",
			"vol24h": 9055561.71468987,
			"liq": 3384.5554,
			"mcap": null,
			"poolSeenAt": "2026-09-29T19:19:00.000Z",
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "OCTCAT",
			"address": "0x0fe2650ebedb62ae2b209fc43e45862af73e5e58",
			"kind": "meme",
			"name": "October Kitty",
			"vol24h": 8768167.27468071,
			"liq": 254917.4357,
			"mcap": null,
			"poolSeenAt": "2026-09-30T04:58:41.000Z",
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "SI",
			"address": "0x3fcd140c68d067c6a71ca328a90fe8d688b81e18",
			"kind": "meme",
			"name": "Shiba Inu",
			"vol24h": 8578559.86693491,
			"liq": 219932.5605,
			"mcap": null,
			"poolSeenAt": "2026-08-29T18:27:03.000Z",
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "DEADBEEF",
			"address": "0xb64fd97d3ce8c487bd3613fcda691eb874f37ace",
			"kind": "meme",
			"name": "Deadbeef coin",
			"vol24h": 6813386.19704704,
			"liq": 1.6166,
			"mcap": null,
			"poolSeenAt": "2026-09-29T12:13:56.000Z",
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "HOOD",
			"address": "0x32ac8c1d7672667d5ebdea22935f7b06fc8d496f",
			"kind": "stock",
			"name": "HOOD",
			"vol24h": 6393187.38574317,
			"liq": 336720.1336,
			"mcap": null,
			"poolSeenAt": "2026-09-03T05:36:21.000Z",
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "VRAX",
			"address": "0xc6080ea62997b33c8e46360850cb4473913b61f0",
			"kind": "meme",
			"name": "Commander Vrax",
			"vol24h": 4939382.77129186,
			"liq": 59457.8782,
			"mcap": null,
			"poolSeenAt": "2026-09-29T23:30:32.000Z",
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "OFY",
			"address": "0xfd1a35778d9798f13c6fb97d29c07a5ce3f7fb5e",
			"kind": "meme",
			"name": "OffYield Neobank",
			"vol24h": 4737655.913580556,
			"liq": 66.542,
			"mcap": null,
			"poolSeenAt": "2026-09-29T18:39:11.000Z",
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "SPY",
			"address": "0x117cc2133c37b721f49de2a7a74833232b3b4c0c",
			"kind": "stock",
			"name": "SPDR S&P 500 ETF Trust • Robinhood Token",
			"vol24h": 4446794.37,
			"liq": 1721041.2853,
			"mcap": null,
			"poolSeenAt": "2026-08-03T13:56:47.000Z",
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "HOOKR",
			"address": "0x18e674231a58c239dc7daedcffe15ec3a24cff5c",
			"kind": "meme",
			"name": "Hookr.fun",
			"vol24h": 4221523,
			"liq": 969354.08,
			"mcap": 15823009.5,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "DUCAT",
			"address": "0x35f3033bb46c97f55762f53adb1b7c5c004f4dbf",
			"kind": "meme",
			"name": "Ducat",
			"vol24h": 4142851.00640844,
			"liq": 1520.9944,
			"mcap": null,
			"poolSeenAt": "2026-09-29T13:30:31.000Z",
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "ROBINPEPE",
			"address": "0xa241395adcdf456f6dc04d1bc02b18e6f4c4052c",
			"kind": "meme",
			"name": "Robin Pepe",
			"vol24h": 3848882.69599858,
			"liq": 78922.883,
			"mcap": null,
			"poolSeenAt": "2026-09-25T16:33:59.000Z",
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "NEPTUNE",
			"address": "0x5024307aa5b0f2dbae7caf04d4645830c8f24ba8",
			"kind": "meme",
			"name": "neptune",
			"vol24h": 3827996.07753066,
			"liq": 11105.54,
			"mcap": null,
			"poolSeenAt": "2026-09-29T23:25:35.000Z",
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "FLING",
			"address": "0x27e1ce669d481827096ab2e45d1b80f34fb41137",
			"kind": "meme",
			"name": "FLING",
			"vol24h": 3813497.66482564,
			"liq": 8.6221,
			"mcap": null,
			"poolSeenAt": "2026-09-29T09:31:03.000Z",
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "NUTFLEX",
			"address": "0xf595166f1bed0fea3941d9a423d4eb7575dfc1e5",
			"kind": "meme",
			"name": "NUTFLEX",
			"vol24h": 3542434.85420874,
			"liq": 18113.5,
			"mcap": null,
			"poolSeenAt": "2026-09-30T00:30:57.000Z",
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "ORBIO",
			"address": "0xaa07a0e9209e16ac99708c3ec70159c6ef3128a3",
			"kind": "meme",
			"name": "Orbio.so",
			"vol24h": 2953398,
			"liq": 1021033.06,
			"mcap": 58142785,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "GLD",
			"address": "0xc9a981fee1f9dec688bb123ccdecc63d0debfc4e",
			"kind": "stock",
			"name": "SPDR Gold Shares • Robinhood Token",
			"vol24h": 2937862.98,
			"liq": 1430991.2,
			"mcap": null,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "BUN",
			"address": "0x07ebb29a38fbcb41563817e5e19f2cec619c90d2",
			"kind": "meme",
			"name": "Bundle Cat",
			"vol24h": 2929367,
			"liq": 930965.4,
			"mcap": 19217801,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "ASI",
			"address": "0xd932750cbe79c5bcafee5e41b2ca87b4c16b1e90",
			"kind": "meme",
			"name": "American Super Intelligence",
			"vol24h": 2841946.68085397,
			"liq": 54733.32,
			"mcap": null,
			"poolSeenAt": "2026-09-29T21:35:04.000Z",
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "HAPPY",
			"address": "0x1ce54db9067c0ee04b6c2c24c9d6b139573a2257",
			"kind": "meme",
			"name": "Happiness",
			"vol24h": 2758744.49210796,
			"liq": 2690.3684,
			"mcap": null,
			"poolSeenAt": "2026-09-29T19:07:20.000Z",
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "AMC",
			"address": "0x05a3d1cd21d0c88145e82600e62e7e496e0f222b",
			"kind": "stock",
			"name": "AMC Entertainment Holdings, Inc. • Robinhood Token",
			"vol24h": 2516417.53,
			"liq": 246711.77,
			"mcap": null,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "GME",
			"address": "0x1b0e319c6a659f002271b69db8a7df2f911c153e",
			"kind": "stock",
			"name": "GameStop • Robinhood Token",
			"vol24h": 2501631.75,
			"liq": 195680.83349999998,
			"mcap": null,
			"poolSeenAt": "2026-09-29T23:35:01.000Z",
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "SHRUB",
			"address": "0x5d9144d2d017386519a7134fcc7f1e4ba22f920c",
			"kind": "meme",
			"name": "Lil' Shrub",
			"vol24h": 2407442,
			"liq": 43583.27,
			"mcap": null,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "BOTBOOK",
			"address": "0x00a6075b0487877eb83687c90d7643c3524a8601",
			"kind": "paired",
			"name": "Botbook",
			"vol24h": 2399155.26401279,
			"liq": 58612.8415,
			"mcap": null,
			"poolSeenAt": "2026-09-30T00:54:23.000Z",
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "ROBINHOOD",
			"address": "0xeec414174f7dcba9e3aa1672a1cf57078e65ae28",
			"kind": "meme",
			"name": "Gta6HaalandRizzler42069",
			"vol24h": 2270009.05548768,
			"liq": 21299.9762,
			"mcap": null,
			"poolSeenAt": "2026-09-29T22:56:59.000Z",
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "SHROOM",
			"address": "0xab093def657f15df31b33922a95e047add645b29",
			"kind": "meme",
			"name": "MUSHROOM",
			"vol24h": 2254425,
			"liq": 471810.38,
			"mcap": 14641153,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": true,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "MOO",
			"address": "0xd9db30bb0d2b8d2eae3826a1372117e058791e18",
			"kind": "meme",
			"name": "Memory cow Moo",
			"vol24h": 2252983,
			"liq": 918840.38,
			"mcap": 8216544,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "DOTS",
			"address": "0xe52c003f1a3abe8839447b1674d7bda62047a8b4",
			"kind": "meme",
			"name": "Dotsbook",
			"vol24h": 2135993.46380673,
			"liq": 48231.53,
			"mcap": null,
			"poolSeenAt": "2026-09-29T17:25:48.000Z",
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "SUITED",
			"address": "0x448168b7c3736fb55c552dce72d5f1f5b30d77cb",
			"kind": "meme",
			"name": "Suited",
			"vol24h": 2082363.00989296,
			"liq": 96562.7645,
			"mcap": null,
			"poolSeenAt": "2026-09-29T22:49:33.000Z",
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "BONER",
			"address": "0x98096d17e191b3da1d5f99a6d7b3584351b11e18",
			"kind": "meme",
			"name": "Boner Coin",
			"vol24h": 2009892,
			"liq": 397794.72,
			"mcap": 48558048,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": true,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "NEPTUNE",
			"address": "0x82f80846196f6067570588877d97dd6d06494ba8",
			"kind": "meme",
			"name": "neptune",
			"vol24h": 1988222.86211492,
			"liq": 22699.1796,
			"mcap": null,
			"poolSeenAt": "2026-09-29T23:15:46.000Z",
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "UP",
			"address": "0x57c0e45cb534413d1c20a4240955d6bb250bb4f1",
			"kind": "meme",
			"name": "up",
			"vol24h": 1957286.72,
			"liq": 1813206.98,
			"mcap": 9264094.08384416,
			"poolSeenAt": null,
			"krVenue": "Bithumb",
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": true,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "CHUMP",
			"address": "0x0e0d2c89a5a019fe1cf762e5e33187631dacc21b",
			"kind": "meme",
			"name": "Chump Coin",
			"vol24h": 1944381,
			"liq": 867320.6,
			"mcap": 23171879,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "GOOGL",
			"address": "0x2e0847e8910a9732eb3fb1bb4b70a580adad4fe3",
			"kind": "stock",
			"name": "Alphabet Class A • Robinhood Token",
			"vol24h": 1859135.13,
			"liq": 844117.67,
			"mcap": null,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "META",
			"address": "0xc0d6457c16cc70d6790dd43521c899c87ce02f35",
			"kind": "stock",
			"name": "Meta Platforms • Robinhood Token",
			"vol24h": 1859067.1,
			"liq": 183214.8658,
			"mcap": null,
			"poolSeenAt": "2026-08-11T03:15:51.000Z",
			"krVenue": "Upbit+Bithumb",
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "HIMS",
			"address": "0xccee82fe024c36fa15e1005ede3e9e4787e23d09",
			"kind": "stock",
			"name": "Hims & Hers Health, Inc. • Robinhood Token",
			"vol24h": 1558877.48,
			"liq": 346935.41,
			"mcap": null,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "PONS",
			"address": "0x39dbed3a2bd333467115de45665cc57f813c4571",
			"kind": "eco",
			"name": "Pons",
			"vol24h": 1465394.19,
			"liq": 15472356.6911,
			"mcap": null,
			"poolSeenAt": "2026-09-08T13:29:28.000Z",
			"krVenue": null,
			"reached": {
				"aster": true,
				"hl": true,
				"bnAlpha": true,
				"bnPerp": true,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": true,
				"rhSpot": false
			}
		},
		{
			"symbol": "DUCAT",
			"address": "0xd0ca71118ca21d674f9018a53026a38a0ab54dbf",
			"kind": "meme",
			"name": "Ducat",
			"vol24h": 1451460.84518928,
			"liq": 236437.2223,
			"mcap": null,
			"poolSeenAt": "2026-09-29T13:08:53.000Z",
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "OPENAIX1L",
			"address": "0xfe09fb328be1c286b4f597ed34764b7472ae72c5",
			"kind": "meme",
			"name": "OPENAI 1x Long",
			"vol24h": 1440391.12244505,
			"liq": 53388.7686,
			"mcap": null,
			"poolSeenAt": "2026-09-21T14:56:47.000Z",
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "TAOLAUNCH",
			"address": "0x0441a16767215fe33056a0fb9ce2e4dee842fa8f",
			"kind": "meme",
			"name": "TAOLaunch",
			"vol24h": 1429329.64082209,
			"liq": 43474.122,
			"mcap": null,
			"poolSeenAt": "2026-09-29T15:27:41.000Z",
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "QQQ",
			"address": "0xd5f3879160bc7c32ebb4dc785f8a4f505888de68",
			"kind": "stock",
			"name": "Invesco QQQ • Robinhood Token",
			"vol24h": 1409134.84,
			"liq": 1302949.09,
			"mcap": null,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "SI",
			"address": "0x280f96be1ab107e95692c31171ceaae53433e5d8",
			"kind": "paired",
			"name": "Super Inu",
			"vol24h": 1395229.60755885,
			"liq": 7661.3032,
			"mcap": null,
			"poolSeenAt": "2026-09-29T20:03:37.000Z",
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "PAIR",
			"address": "0xbe71cd8b74f4b988e36c08c41347ad6c827f986f",
			"kind": "meme",
			"name": "Pair",
			"vol24h": 1381630.70745682,
			"liq": 75013.8013,
			"mcap": null,
			"poolSeenAt": "2026-09-30T04:32:40.000Z",
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "VLADBOT",
			"address": "0x0d8d80ab88cc80e1ed025d1f7cc1f7e08d6eacfe",
			"kind": "meme",
			"name": "VladBot",
			"vol24h": 1320920.28606691,
			"liq": 12309.062,
			"mcap": null,
			"poolSeenAt": "2026-09-29T23:27:11.000Z",
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "DELTA",
			"address": "0xe8ffd7e24187f72afb08d75b1bb13088a989a791",
			"kind": "meme",
			"name": "Delta",
			"vol24h": 1306468,
			"liq": 1270631.32,
			"mcap": 19922912,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": true,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "DJT",
			"address": "0x1d11f0496982706c5e14a514d4e79f2e6bde4516",
			"kind": "stock",
			"name": "Trump Media & Technology Group Corp. • Robinhood Token",
			"vol24h": 1249862.26,
			"liq": 255793.12,
			"mcap": null,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "HOODIE",
			"address": "0x8f23191a2a697df832acb9fe9fcb7a23e75ca184",
			"kind": "meme",
			"name": "Hoodie",
			"vol24h": 1160300.4176485,
			"liq": 35917.393,
			"mcap": null,
			"poolSeenAt": "2026-09-27T18:34:55.000Z",
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "HARMONIC",
			"address": "0xdee52f2ab639b6942b0d0f0565400b93b7a0fbe5",
			"kind": "meme",
			"name": "Harmonic Agent",
			"vol24h": 1053323,
			"liq": 178031.39,
			"mcap": 3076994,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "BLINK",
			"address": "0x7b630f080807df83908b4ade46ba6396ee66b098",
			"kind": "meme",
			"name": "dont blink",
			"vol24h": 1014733,
			"liq": 159278.65,
			"mcap": null,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "USO",
			"address": "0xa30fa36db767ad9ed3f7a60fc79526fb4d56d344",
			"kind": "stock",
			"name": "United States Oil Fund • Robinhood Token",
			"vol24h": 995408.35,
			"liq": 197512.94,
			"mcap": null,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "AAPL",
			"address": "0xaf3d76f1834a1d425780943c99ea8a608f8a93f9",
			"kind": "stock",
			"name": "Apple • Robinhood Token",
			"vol24h": 942333.25,
			"liq": 244696.71,
			"mcap": null,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "INTC",
			"address": "0xc72b96e0e48ecd4dc75e1e45396e26300bc39681",
			"kind": "stock",
			"name": "Intel • Robinhood Token",
			"vol24h": 850356.22,
			"liq": 390401.13,
			"mcap": null,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "ROO",
			"address": "0x3458e003f6ed93df0f537b8acac6fbe08e41247f",
			"kind": "meme",
			"name": "Roo",
			"vol24h": 788981.042434246,
			"liq": 24018.1066,
			"mcap": null,
			"poolSeenAt": "2026-09-23T04:00:40.000Z",
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "LIT",
			"address": "0xeeca2e7dc194a320d349122d88259bb9595a4cb0",
			"kind": "meme",
			"name": "Lighter",
			"vol24h": 771559.79,
			"liq": 571918.03,
			"mcap": null,
			"poolSeenAt": null,
			"krVenue": "Upbit+Bithumb",
			"reached": {
				"aster": true,
				"hl": true,
				"bnAlpha": false,
				"bnPerp": true,
				"bnSpot": false,
				"kr": true,
				"rhQuoted": true,
				"rhSpot": true
			}
		},
		{
			"symbol": "LLY",
			"address": "0x8005d266423c7ea827372c9c864491e5786600ea",
			"kind": "stock",
			"name": "Eli Lilly • Robinhood Token",
			"vol24h": 767202.26,
			"liq": 307597.36,
			"mcap": null,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "FRONG",
			"address": "0x6245e67affa44a23077f0ea7f981a8dc743a0c47",
			"kind": "meme",
			"name": "frong",
			"vol24h": 748193,
			"liq": 725785.79,
			"mcap": 5680677,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": true,
				"rhSpot": false
			}
		},
		{
			"symbol": "RBD",
			"address": "0xb41c7ac9d46a980f8bdf1894b392a2a07ec9992a",
			"kind": "meme",
			"name": "RobinDog",
			"vol24h": 736208.578395203,
			"liq": 33747.7646,
			"mcap": null,
			"poolSeenAt": "2026-09-24T12:49:41.000Z",
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "MSTR",
			"address": "0xec262a75e413fafd0df80480274532c79d42da09",
			"kind": "stock",
			"name": "Strategy Inc. • Robinhood Token",
			"vol24h": 717719.66,
			"liq": 1264195.97,
			"mcap": null,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "NFLX",
			"address": "0xe0444ef8bf4ed74f74fd73686e2ddf4c1c5591e8",
			"kind": "stock",
			"name": "Netflix • Robinhood Token",
			"vol24h": 691463.86,
			"liq": 192082.82,
			"mcap": null,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "PLTR",
			"address": "0x894e1ec2d74ffe5aef8dc8a9e84686accb964f2a",
			"kind": "stock",
			"name": "Palantir Technologies • Robinhood Token",
			"vol24h": 686886.71,
			"liq": 371427.51,
			"mcap": null,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "MICRODUCK",
			"address": "0xd5f1afea47b1a9eab414d2ee740cf1d6d039e725",
			"kind": "meme",
			"name": "microduck",
			"vol24h": 598444,
			"liq": 134882.82,
			"mcap": 2354322,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "MSFT",
			"address": "0xe93237c50d904957cf27e7b1133b510c669c2e74",
			"kind": "stock",
			"name": "Microsoft • Robinhood Token",
			"vol24h": 534649.52,
			"liq": 564815.9,
			"mcap": null,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "ROBIN",
			"address": "0x11b70d0243baf75e85ce03201a92b5b7c33beb59",
			"kind": "meme",
			"name": "Robin the Frog",
			"vol24h": 495149.43,
			"liq": 93401.66,
			"mcap": 1394188.096,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "MU",
			"address": "0xff080c8ce2e5feadaca0da81314ae59d232d4afd",
			"kind": "stock",
			"name": "Micron Technology • Robinhood Token",
			"vol24h": 492393.67,
			"liq": 477165.95,
			"mcap": null,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "AMZN",
			"address": "0x12f190a9f9d7d37a250758b26824b97ce941bf54",
			"kind": "stock",
			"name": "Amazon • Robinhood Token",
			"vol24h": 471267.16,
			"liq": 841517.31,
			"mcap": null,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "TSLA",
			"address": "0x322f0929c4625ed5bad873c95208d54e1c003b2d",
			"kind": "stock",
			"name": "Tesla • Robinhood Token",
			"vol24h": 461197.34,
			"liq": 865292.28,
			"mcap": null,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "PROLOGUE",
			"address": "0xb9972ca7188e511174947e3936a5315ac7073277",
			"kind": "meme",
			"name": "Prologue",
			"vol24h": 455240.11,
			"liq": 683911.84,
			"mcap": 8655635,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "PARE",
			"address": "0x15d36b6a28d8327abc7afabf0f106ae2c9af5c4d",
			"kind": "meme",
			"name": "Pare",
			"vol24h": 455201,
			"liq": 158094.91,
			"mcap": 2676378,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "ZZZ",
			"address": "0x7dbf38976f6d3b9c529e7d9484a71898b409ee6a",
			"kind": "meme",
			"name": "ZZZ",
			"vol24h": 438829.53,
			"liq": 415872.47,
			"mcap": 15370576,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "SGOV",
			"address": "0x92fd66527192e3e61d4ddd13322aa222de86f9b5",
			"kind": "stock",
			"name": "iShares 0-3 Month Treasury Bond ETF • Robinhood Token",
			"vol24h": 423630.57,
			"liq": 2165770.81,
			"mcap": null,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "CINEMA",
			"address": "0x9936403a9cc72cf306063e3496ea387428a3aecd",
			"kind": "meme",
			"name": "ABSOLUTE CINEMA",
			"vol24h": 421071,
			"liq": 58135.05,
			"mcap": 235863,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "TSM",
			"address": "0x58ffe4a942d3885baa22d7520691f611ef09e7aa",
			"kind": "stock",
			"name": "Taiwan Semiconductor Manufacturing • Robinhood Token",
			"vol24h": 414950.83,
			"liq": 551121.06,
			"mcap": null,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "ASI",
			"address": "0x07e3cbe641daa04a4dadfcae995c63856ae21e18",
			"kind": "paired",
			"name": "American Super Inutelligence",
			"vol24h": 382413.092075577,
			"liq": 39293.5366,
			"mcap": null,
			"poolSeenAt": "2026-09-29T13:54:44.000Z",
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "STONKBROKER",
			"address": "0xe934e36a439c94017b64a3fece66af12099abf50",
			"kind": "meme",
			"name": "StonkBroker",
			"vol24h": 378464.28,
			"liq": 2503594.2,
			"mcap": null,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": true,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "HOODCATS",
			"address": "0xd17c81cb01d44cc6e822936e8f098960001b47d2",
			"kind": "meme",
			"name": "Hood Cats",
			"vol24h": 354555.417917064,
			"liq": 33420.0547,
			"mcap": null,
			"poolSeenAt": "2026-09-19T03:23:52.000Z",
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "VEX",
			"address": "0x8ff92566f2e81bdd68edfaa8cde73942a723796b",
			"kind": "meme",
			"name": "ProjectVex",
			"vol24h": 334047.42,
			"liq": 329095.76,
			"mcap": 2880384,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "SNAP",
			"address": "0xf6589f11bc40b669e584073f428b05562f568733",
			"kind": "stock",
			"name": "Snap Inc. • Robinhood Token",
			"vol24h": 317720.73,
			"liq": 114102.55,
			"mcap": null,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "AMD",
			"address": "0x86923f96303d656e4aa86d9d42d1e57ad2023fdc",
			"kind": "stock",
			"name": "AMD • Robinhood Token",
			"vol24h": 292826.38,
			"liq": 337849.93,
			"mcap": null,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "MANY",
			"address": "0xa26992c4268a8a78a4d872fe4bdad2ed03ac287d",
			"kind": "meme",
			"name": "Manyways Inference",
			"vol24h": 279554,
			"liq": 116381.86,
			"mcap": null,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "BUCKET",
			"address": "0xbc9e7b1c5c0081f4ae85e71ec95703d3dec9ffad",
			"kind": "meme",
			"name": "Bucket Shop",
			"vol24h": 230555,
			"liq": 158660.1,
			"mcap": 3550354,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "FATCOIN",
			"address": "0x12d5ee7917ca430073c3a638ee1e6f0648a98a01",
			"kind": "meme",
			"name": "FATCOIN",
			"vol24h": 224785,
			"liq": 89168.21,
			"mcap": 548149,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "GLXY",
			"address": "0x2d427692e928fa156ec22acfabafa0447c5805b7",
			"kind": "stock",
			"name": "Galaxy Digital Inc. • Robinhood Token",
			"vol24h": 200779.12,
			"liq": 180307.61,
			"mcap": null,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "RDDT",
			"address": "0x05b37fb53a299a1b874a619e1c4c404d52c36f4c",
			"kind": "stock",
			"name": "Reddit • Robinhood Token",
			"vol24h": 197173.74,
			"liq": 1016915.23,
			"mcap": null,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "PAIR",
			"address": "0x6b1d42927b1a84ec28fa88d4fc6fa7af404966be",
			"kind": "paired",
			"name": "PAIR",
			"vol24h": 191336.25,
			"liq": 187456.61,
			"mcap": null,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": true,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "HOTDOG",
			"address": "0x1c1daef0300551adbfbe403e7d567b6c5aff566f",
			"kind": "meme",
			"name": "hotdog",
			"vol24h": 181313,
			"liq": 47923.83,
			"mcap": null,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "JUGGERNAUT",
			"address": "0xd7321801caae694090694ff55a9323139f043b88",
			"kind": "meme",
			"name": "The Juggernaut",
			"vol24h": 176695.18,
			"liq": 489322.72,
			"mcap": null,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": true,
				"rhSpot": false
			}
		},
		{
			"symbol": "SLV",
			"address": "0x411efb0e7f985935daec3d4c3ebaea0d0ad7d89f",
			"kind": "stock",
			"name": "iShares Silver Trust • Robinhood Token",
			"vol24h": 172561.1,
			"liq": 129798.52,
			"mcap": null,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "BE",
			"address": "0x822cc93ffd030293e9842c30bbd678f530701867",
			"kind": "stock",
			"name": "Bloom Energy • Robinhood Token",
			"vol24h": 172009.64,
			"liq": 108929.82,
			"mcap": null,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "ICOIN",
			"address": "0x5d6ef090a1461b11c9427ac319260122d1c61e18",
			"kind": "meme",
			"name": "iCoin",
			"vol24h": 167715,
			"liq": 243327.55,
			"mcap": 831875,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "RAXOL",
			"address": "0xf44702b17d9abd53815f703e772f35e9c71a53af",
			"kind": "meme",
			"name": "RAXOL",
			"vol24h": 166399.24,
			"liq": 423659.22,
			"mcap": 6683800,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "MANCER",
			"address": "0xc72f232a6869e6cf34dc06129affd07f8a2a246a",
			"kind": "meme",
			"name": "Mancer",
			"vol24h": 156039,
			"liq": 485614.69,
			"mcap": 2094828,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "TA",
			"address": "0x9ca1cc0c90d97b4f36c5e2232d4fbd705a73c65d",
			"kind": "meme",
			"name": "TA FUND",
			"vol24h": 152719.77,
			"liq": 89376.29,
			"mcap": null,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "COST",
			"address": "0x4ea005168d7f09a7a0ba9d1def21a479950e44c2",
			"kind": "stock",
			"name": "Costco • Robinhood Token",
			"vol24h": 150923.15,
			"liq": 92852.23,
			"mcap": null,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "PIPEDOG",
			"address": "0x5cb6f181081301b44905f3ae15419112ecabd8a6",
			"kind": "meme",
			"name": "pipedog",
			"vol24h": 145221.81,
			"liq": 7964137.18,
			"mcap": 21548272,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "BA",
			"address": "0x4d21483a44bf67a86b77e3da301411880797d452",
			"kind": "stock",
			"name": "Boeing • Robinhood Token",
			"vol24h": 133718.04,
			"liq": 111212.58,
			"mcap": null,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "EARN",
			"address": "0xa3b6aee90017b72c0812dc1e013de70eb2917ba3",
			"kind": "meme",
			"name": "EARN",
			"vol24h": 123073,
			"liq": 267157.96,
			"mcap": null,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "GOOD",
			"address": "0x5f62c57e5c537887117eef828b7e3ad41c009feb",
			"kind": "meme",
			"name": "Good In The Hood",
			"vol24h": 113782,
			"liq": 344850.46,
			"mcap": null,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "INDEX",
			"address": "0x56910d4409f3a0c78c64dd8d0545ff0705389870",
			"kind": "meme",
			"name": "The Index",
			"vol24h": 110992.58,
			"liq": 781541.6,
			"mcap": 23656841.6074674,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": true,
				"rhSpot": false
			}
		},
		{
			"symbol": "NASDANQ",
			"address": "0x51fb76be80ab6daaa345d818f4e06441816b4fea",
			"kind": "meme",
			"name": "NASDANQ",
			"vol24h": 103871,
			"liq": 147371.32,
			"mcap": null,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "NET",
			"address": "0x116f00968269b7bfbad4109ce591d6e74c0601d4",
			"kind": "stock",
			"name": "Cloudflare, Inc. • Robinhood Token",
			"vol24h": 103006.22,
			"liq": 96843.32,
			"mcap": null,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "AA",
			"address": "0xe2dae1c072b9f66bed999873b94798b2152af7e1",
			"kind": "meme",
			"name": "Arbitrage Ape",
			"vol24h": 102248,
			"liq": 50202.97,
			"mcap": 367717,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "PERPSHOOD",
			"address": "0x7ba36be14dd06ba492f08be6c1b2979c1d0b652c",
			"kind": "meme",
			"name": "PerpsHood",
			"vol24h": 98167.01,
			"liq": 73384.84,
			"mcap": 527169,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "WOJAK",
			"address": "0xace55fe98bab14366dd49ab5aa5df76aa11a3c6f",
			"kind": "meme",
			"name": "Wojak",
			"vol24h": 96905.78,
			"liq": 195246.46,
			"mcap": null,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "LILUNI",
			"address": "0x4a6eec8a30b49d289b9fc865fd374b4d61eab8fb",
			"kind": "meme",
			"name": "Liluni",
			"vol24h": 95617,
			"liq": 82889.16,
			"mcap": null,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "PEPONS",
			"address": "0xfde368debe9e80f80785064a65719cec1f809dec",
			"kind": "meme",
			"name": "Pepons",
			"vol24h": 95587.1411586603,
			"liq": 149242.3601,
			"mcap": null,
			"poolSeenAt": "2026-09-18T11:51:00.000Z",
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "RBLX",
			"address": "0xf0c4bf4c582cb3836e98394b1d4e7b7281101be8",
			"kind": "stock",
			"name": "Roblox • Robinhood Token",
			"vol24h": 92910.55,
			"liq": 208503.92,
			"mcap": null,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "0XZAPS",
			"address": "0xdd90bfa4adc7f4401e611abac692d939f9f4cb07",
			"kind": "meme",
			"name": "OpenZaps",
			"vol24h": 86852,
			"liq": 189344.73,
			"mcap": 438784,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "QUBT",
			"address": "0x59818904ab4ce163b3ce4ffb64f2d6ca02c434b4",
			"kind": "stock",
			"name": "Quantum Computing • Robinhood Token",
			"vol24h": 82306.21,
			"liq": 127336.63,
			"mcap": null,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "BABA",
			"address": "0xad25ac6c84d497db898fa1e8387bf6af3532a1c4",
			"kind": "stock",
			"name": "Alibaba • Robinhood Token",
			"vol24h": 79863.67,
			"liq": 52378.85,
			"mcap": null,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "FIG",
			"address": "0x41f4267525a8aff329540ef24fd83d9044758b33",
			"kind": "stock",
			"name": "Figma, Inc. • Robinhood Token",
			"vol24h": 78818.66,
			"liq": 152248.81,
			"mcap": null,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "MRNA",
			"address": "0x43b07d15ce533bec5476d70c22a78a1b2b662155",
			"kind": "stock",
			"name": "Moderna, Inc. • Robinhood Token",
			"vol24h": 75273.27,
			"liq": 78189.33,
			"mcap": null,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "MARTIANS",
			"address": "0xac77646bcff9d52e99800534192e0290933f4094",
			"kind": "meme",
			"name": "Martians",
			"vol24h": 71777,
			"liq": 46359.56,
			"mcap": null,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "ARROW",
			"address": "0xf2915d1e3c1b0c769d0c756ec43f1c1f6c99cd03",
			"kind": "meme",
			"name": "Arrow",
			"vol24h": 69256,
			"liq": 240385.07,
			"mcap": 3726459,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "IBM",
			"address": "0x980dcf6766fa79f5cf0c4aadb3ab477ff15a9619",
			"kind": "stock",
			"name": "International Business Machines Corporation • Robinhood Token",
			"vol24h": 65296.28,
			"liq": 243091.98,
			"mcap": null,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "TTWO",
			"address": "0x5e81213613b6b86eab4c6c50d718d34359459786",
			"kind": "stock",
			"name": "Take-Two Interactive Software • Robinhood Token",
			"vol24h": 65081.54,
			"liq": 185155.5,
			"mcap": null,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "PONGO",
			"address": "0xedaee44320107caa714baaec486261a87f27022d",
			"kind": "meme",
			"name": "PONGO",
			"vol24h": 61664.74,
			"liq": 131943.78,
			"mcap": null,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "LULU",
			"address": "0x4e62068525ab11fe768e29dfd00ef909b9803016",
			"kind": "stock",
			"name": "Lululemon • Robinhood Token",
			"vol24h": 59953.74,
			"liq": 120602.95,
			"mcap": null,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "WORTH",
			"address": "0xfb1bcb6817f7b8fa86896d3253b16aeb7bd6a5a8",
			"kind": "meme",
			"name": "one life, its worth an attempt",
			"vol24h": 59773,
			"liq": 137147.59,
			"mcap": null,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "JNJ",
			"address": "0x03dfbbe0ac4e7bcdafd08ed41a400326b77d8c80",
			"kind": "stock",
			"name": "Johnson & Johnson • Robinhood Token",
			"vol24h": 56262.87,
			"liq": 48847.47,
			"mcap": null,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "DELL",
			"address": "0x941ae714ec6d8130c7b75d67160ca08f1e7d11dd",
			"kind": "stock",
			"name": "Dell • Robinhood Token",
			"vol24h": 54402.57,
			"liq": 116500.63,
			"mcap": null,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "RCAT",
			"address": "0xfde6b5d9bb419b10c23268c74e369abff39c0460",
			"kind": "stock",
			"name": "Red Cat Holdings, Inc. • Robinhood Token",
			"vol24h": 46554.54,
			"liq": 51645.23,
			"mcap": null,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "POOLS",
			"address": "0x385b36ff682ab4c76e7c37a66b96aabc466471d5",
			"kind": "meme",
			"name": "pools.trade",
			"vol24h": 46260.42,
			"liq": 204417.19,
			"mcap": null,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "ORCL",
			"address": "0xb0992820e760d836549ba69bc7598b4af75dee03",
			"kind": "stock",
			"name": "Oracle • Robinhood Token",
			"vol24h": 46072.63,
			"liq": 132824.95,
			"mcap": null,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "CRUDECAT",
			"address": "0xbd957cc9f1e94617792f37bc40f2f299e78acf3e",
			"kind": "meme",
			"name": "Crude Cat",
			"vol24h": 42682,
			"liq": 6026.34,
			"mcap": null,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "MERRYMEN",
			"address": "0xa15cd06dd305269a0f48bebeb30aa3588fba7b32",
			"kind": "meme",
			"name": "Merrymen by Virtuals",
			"vol24h": 42638,
			"liq": 97373.99,
			"mcap": 329637,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "DENAR",
			"address": "0x3786728a2c49c4617bf4fe5bd82b90b6b0df5508",
			"kind": "meme",
			"name": "Denar Markets",
			"vol24h": 42632,
			"liq": 48421.88,
			"mcap": null,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "BB",
			"address": "0x48e39e56acdba37b09020c0b734a613c9a2f100a",
			"kind": "stock",
			"name": "BlackBerry Limited • Robinhood Token",
			"vol24h": 41163.22,
			"liq": 56970.8,
			"mcap": null,
			"poolSeenAt": null,
			"krVenue": "Bithumb",
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "LMT",
			"address": "0x329fcaceb9ad6f9580dd5f643fed0646900d043c",
			"kind": "stock",
			"name": "Lockheed Martin Corp. • Robinhood Token",
			"vol24h": 41024.34,
			"liq": 167220.66,
			"mcap": null,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "PFE",
			"address": "0x7066a64c24e4206cd62e83bf198c1e7eb361f51e",
			"kind": "stock",
			"name": "Pfizer Inc. • Robinhood Token",
			"vol24h": 40700.07,
			"liq": 78423.56,
			"mcap": null,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "GRASS",
			"address": "0x16391c40e85fb2246a2c8c17bfa2594c5d3ef84b",
			"kind": "meme",
			"name": "Touch Grass",
			"vol24h": 39302.93,
			"liq": 100695.38,
			"mcap": null,
			"poolSeenAt": null,
			"krVenue": "Bithumb",
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "LEMON",
			"address": "0xf0e17e54239cd945cd7bea471a3a2ca6a8c7f7a3",
			"kind": "meme",
			"name": "Lemon.fun",
			"vol24h": 38946,
			"liq": 50776.33,
			"mcap": null,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "DTF",
			"address": "0x5edb417509a869b1d8222dea05257b8c8ba00361",
			"kind": "meme",
			"name": "DeFi Traded Fund",
			"vol24h": 38012,
			"liq": 88244.26,
			"mcap": null,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "KITSU",
			"address": "0x8d4dfaaa4198b6486e0293fec914c2b6a821d4dc",
			"kind": "meme",
			"name": "Kitsu",
			"vol24h": 34410,
			"liq": 117331.85,
			"mcap": null,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "MESH",
			"address": "0x14641000a501bdc736116abf84e6fcea9b90a713",
			"kind": "meme",
			"name": "MESH Gateway",
			"vol24h": 33556,
			"liq": 62138.65,
			"mcap": null,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "SHOP",
			"address": "0xf53f66751b1eff985311b693531e3290f600c410",
			"kind": "stock",
			"name": "Shopify • Robinhood Token",
			"vol24h": 33009.97,
			"liq": 33649.38,
			"mcap": null,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "NUKE",
			"address": "0x0000000005aca17e8bd5779fc87e13cb433aed24",
			"kind": "meme",
			"name": "NUKE",
			"vol24h": 31813,
			"liq": 181935.91,
			"mcap": null,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "ASTEROID",
			"address": "0xfd82d8db539b6ace0d50815845133767e24f1e18",
			"kind": "meme",
			"name": "ASTEROID",
			"vol24h": 31158,
			"liq": 464040.74,
			"mcap": 2641660,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "MUMU",
			"address": "0x8ec17c059f250a5c19566c3fc56ee13a343dd283",
			"kind": "meme",
			"name": "Mumu The Bull",
			"vol24h": 30871,
			"liq": 28970.57,
			"mcap": null,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "CNPY",
			"address": "0x532c5583671870723ceef573600208af49c87c54",
			"kind": "meme",
			"name": "Canopy Finance",
			"vol24h": 30286,
			"liq": 100765.96,
			"mcap": null,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "LUTE",
			"address": "0xd1e861cc5eee7ea88649206b74504d78ccd7aeea",
			"kind": "meme",
			"name": "Alandale",
			"vol24h": 30211,
			"liq": 145251.9,
			"mcap": null,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "MLY",
			"address": "0x84b7515081a7ac5adc26179b77a8b18a8c6725c0",
			"kind": "meme",
			"name": "Mintly",
			"vol24h": 30097,
			"liq": 78510.67,
			"mcap": null,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "ORDO",
			"address": "0xfe2f0fb0c00d19786a8abf98d4b1f1ac8763b167",
			"kind": "meme",
			"name": "OrdoFi",
			"vol24h": 29942,
			"liq": 49459.22,
			"mcap": null,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "GG",
			"address": "0xcacb0e9caccee63ec4d82952e561a291c68bcb68",
			"kind": "meme",
			"name": "Golden Goose",
			"vol24h": 29649,
			"liq": 54363.36,
			"mcap": null,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "SNDK",
			"address": "0xb90a19ff0af67f7779aff50a882a9cff42446400",
			"kind": "stock",
			"name": "Sandisk Corporation • Robinhood Token",
			"vol24h": 29570.82,
			"liq": 237039.1,
			"mcap": null,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "🅿️",
			"address": "0xe1e5f00a9b0255ca4df85b3130ee0f77d15acc2d",
			"kind": "meme",
			"name": "Pushin' 🅿️",
			"vol24h": 27491.37,
			"liq": 37828.57,
			"mcap": null,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "F",
			"address": "0x25c288e6d899b9bc30160965ad9644c67e73be0c",
			"kind": "stock",
			"name": "Ford Motor • Robinhood Token",
			"vol24h": 26343.46,
			"liq": 113961.64,
			"mcap": null,
			"poolSeenAt": null,
			"krVenue": "Upbit+Bithumb",
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "BACKED",
			"address": "0x7168563b0e70124f0c7c0cf2f13a8d1861baf4a5",
			"kind": "meme",
			"name": "Backed",
			"vol24h": 26015,
			"liq": 93355.08,
			"mcap": null,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "MARIAN",
			"address": "0x01637b14b7378b99de75a64d50656d98488d9a4d",
			"kind": "meme",
			"name": "Lady Marian",
			"vol24h": 25249,
			"liq": 103052.75,
			"mcap": null,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "CRWV",
			"address": "0x5f10a1c971b69e47e059e1dc91901b59b3fb49c3",
			"kind": "stock",
			"name": "CoreWeave • Robinhood Token",
			"vol24h": 24744.1,
			"liq": 46031.31,
			"mcap": null,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "USAR",
			"address": "0xd917b029c761d264c6a312bbbcda868658ef86a6",
			"kind": "stock",
			"name": "USA Rare Earth • Robinhood Token",
			"vol24h": 24180.41,
			"liq": 67082.46,
			"mcap": null,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "HH",
			"address": "0x6835dbf2d7d5852f84bf0a80de00cab3864f44b1",
			"kind": "meme",
			"name": "HyperHood",
			"vol24h": 23584,
			"liq": 123759.91,
			"mcap": null,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "DDOG",
			"address": "0x27c99fbde9d0d2aa4f4bfb4943f237843ddf6958",
			"kind": "stock",
			"name": "Datadog • Robinhood Token",
			"vol24h": 23281.15,
			"liq": 43865.98,
			"mcap": null,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "AU",
			"address": "0xd4aae326ddd1a2537a92c00e6576e4605e5d1e18",
			"kind": "meme",
			"name": "AUTSM",
			"vol24h": 21347,
			"liq": 170259.34,
			"mcap": null,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "NU",
			"address": "0x408c14038a04f7bd235329e26d2bf569ee20e250",
			"kind": "stock",
			"name": "Nu • Robinhood Token",
			"vol24h": 20366.81,
			"liq": 49016.65,
			"mcap": null,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "CLOCKIN",
			"address": "0xa5be0eeb82a013dc7867b9e020c36a69da666666",
			"kind": "meme",
			"name": "CLOCK IN",
			"vol24h": 19642.07,
			"liq": 92897.54,
			"mcap": null,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "DOGGIE",
			"address": "0xa9efe2fc94de79734c03051515f48f254ce61e18",
			"kind": "meme",
			"name": "Doggie Mode",
			"vol24h": 18696.62,
			"liq": 116488.7,
			"mcap": 201061,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "RIVN",
			"address": "0xb1bf26c1d20ff267a4f93550d1e0d06ac40a114b",
			"kind": "stock",
			"name": "Rivian Automotive • Robinhood Token",
			"vol24h": 18583.19,
			"liq": 77637.18,
			"mcap": null,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "QCOM",
			"address": "0x0f17206447090e464c277571124dd2688e48aea9",
			"kind": "stock",
			"name": "Qualcomm • Robinhood Token",
			"vol24h": 18570.72,
			"liq": 61155.27,
			"mcap": null,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "AVGO",
			"address": "0x156e175dd063a8ce274c50654ef40e0032b3fbcf",
			"kind": "stock",
			"name": "Broadcom • Robinhood Token",
			"vol24h": 17950.4,
			"liq": 157438.53,
			"mcap": null,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "MOON",
			"address": "0x862cdccb67c8a22fdb247d09a08b1dad09447777",
			"kind": "meme",
			"name": "mooncat",
			"vol24h": 17827.06,
			"liq": 172851.56,
			"mcap": null,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "NINJACAT",
			"address": "0x4a88cf518ea6b7d1184184d6eab78df7252a74f1",
			"kind": "meme",
			"name": "NinjaCat",
			"vol24h": 16808.16,
			"liq": 84437.2,
			"mcap": null,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "POKEMON",
			"address": "0xc8f15d4378e2df49befc148262ad20466c8489cc",
			"kind": "meme",
			"name": "Pokemon",
			"vol24h": 16384.9366043117,
			"liq": 3778.1017,
			"mcap": null,
			"poolSeenAt": "2026-09-29T16:33:31.000Z",
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "AUREON",
			"address": "0xd293291060334d42e5dbea6fb854c231af527777",
			"kind": "meme",
			"name": "AUREON",
			"vol24h": 16118.96,
			"liq": 52768.38,
			"mcap": null,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "NBIS",
			"address": "0x9d9c6684f596f66a64c030b93a886d51fd4d7931",
			"kind": "stock",
			"name": "Nebius Group • Robinhood Token",
			"vol24h": 15776.73,
			"liq": 125043.07,
			"mcap": null,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "BISCOTTI",
			"address": "0x7cd7073a71eaf5f6e4febfa98460ee66cd97deb1",
			"kind": "meme",
			"name": "Biscotti",
			"vol24h": 15300.39,
			"liq": 115135.27,
			"mcap": null,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "LIGER",
			"address": "0x6102d8109bd980ab0d528f56c92b7b87effd1e18",
			"kind": "meme",
			"name": "Liger",
			"vol24h": 14821.34,
			"liq": 38102.79,
			"mcap": null,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "LOCK",
			"address": "0xd5bf43f29bf7aa5bb42ae9e217b84b86eb7a4b94",
			"kind": "meme",
			"name": "HoodLock",
			"vol24h": 14694.72,
			"liq": 63967.34,
			"mcap": null,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "PFWA",
			"address": "0xa934ba4f59070149d37a93f8a002af79bae35563",
			"kind": "meme",
			"name": "predict FWA",
			"vol24h": 14215.28,
			"liq": 65865.57,
			"mcap": null,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "CRCL",
			"address": "0xdf0992e440dd0be65bd8439b609d6d4366bf1cb5",
			"kind": "stock",
			"name": "Circle Internet Group • Robinhood Token",
			"vol24h": 13440.13,
			"liq": 39488.36,
			"mcap": null,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "GAZZ",
			"address": "0x08a5d78a4bc7754e8aff87b4509e007baeb685f3",
			"kind": "meme",
			"name": "Gazz",
			"vol24h": 12830.35,
			"liq": 79839.1,
			"mcap": null,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "RVH",
			"address": "0x96765066f6a040a21eb027167d2315b707c82633",
			"kind": "meme",
			"name": "Ravenhood",
			"vol24h": 12333.7,
			"liq": 84202.41,
			"mcap": null,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "UPS",
			"address": "0xf23250dac154d05bb671cb0d0ebef3c635c79ce2",
			"kind": "stock",
			"name": "UPS • Robinhood Token",
			"vol24h": 12283.24,
			"liq": 74127.74,
			"mcap": null,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "PRINTER",
			"address": "0x85a574f2ff0795685f58d1d7b0d4b51f148ac489",
			"kind": "meme",
			"name": "PRINTER",
			"vol24h": 12236.27,
			"liq": 234642.31,
			"mcap": null,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "HODL",
			"address": "0xf4c450c1570c2dbda91de1ed2e39995a15028c97",
			"kind": "meme",
			"name": "Diamond Hands",
			"vol24h": 12101.29,
			"liq": 40612.37,
			"mcap": null,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "NAVEN",
			"address": "0xeafa804083a4886a9460b5b19557334a652beba8",
			"kind": "meme",
			"name": "Naven Network",
			"vol24h": 11387.85,
			"liq": 52608.61,
			"mcap": null,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "SOXX",
			"address": "0x75742c18bc1f1c5c5f448f4c9d9c6f66dafaaa38",
			"kind": "stock",
			"name": "iShares Semiconductor ETF • Robinhood Token",
			"vol24h": 11328,
			"liq": 41967.74,
			"mcap": null,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "BOURSE",
			"address": "0x60edd303679c3923b628c8f02ce0be69e96deb1d",
			"kind": "meme",
			"name": "BOURSE",
			"vol24h": 11248.4,
			"liq": 67353.39,
			"mcap": null,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "SNOW",
			"address": "0xba0cab75495255d0cb58e22b648bfed4ecd1f47e",
			"kind": "stock",
			"name": "Snowflake Inc. • Robinhood Token",
			"vol24h": 11232.52,
			"liq": 61841.63,
			"mcap": null,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "VLAD",
			"address": "0xdbe9a8897f73ee91fc2e1e27f9b50a72f9fe5a43",
			"kind": "meme",
			"name": "CAPTAIN ROBINHOOD",
			"vol24h": 10756.69,
			"liq": null,
			"mcap": null,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "OURO",
			"address": "0x8ea0eb3505f5b3bd2bbea0febae0ce850cc73ecc",
			"kind": "meme",
			"name": "OuroLayer",
			"vol24h": 10100.35,
			"liq": null,
			"mcap": null,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "DICE",
			"address": "0x3f9f0b6073ee8c495aed96869af31850fed40feb",
			"kind": "meme",
			"name": "Dice Protocol",
			"vol24h": 9978.23,
			"liq": null,
			"mcap": null,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "PONSAN",
			"address": "0x97216593d3b2769da6f0adeee6fb8e36da4e319f",
			"kind": "meme",
			"name": "Ponsancoin",
			"vol24h": 9927.15,
			"liq": null,
			"mcap": null,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "SKHY",
			"address": "0x84cab63bc87912e71ad199ff14a0ba45de68fef8",
			"kind": "stock",
			"name": "SK Hynix • Robinhood Token",
			"vol24h": 9757.25,
			"liq": 90657.85,
			"mcap": null,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "FIRE",
			"address": "0x43eea882b845a8493152ebc55cf30ae9281b02d5",
			"kind": "meme",
			"name": "FIRE",
			"vol24h": 9126.74,
			"liq": null,
			"mcap": null,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "222",
			"address": "0x21ed792de0ebfa85c2f55ff45b2241c576727f7b",
			"kind": "meme",
			"name": "divinely protected",
			"vol24h": 8643.61,
			"liq": null,
			"mcap": null,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "MEOW",
			"address": "0x75c8258eaa6d0f94b82951194191ca3efb0bcbe2",
			"kind": "meme",
			"name": "meow",
			"vol24h": 8209.11,
			"liq": 30151.67,
			"mcap": null,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "GWOOD",
			"address": "0x24d8657e10af588b12de3e102a116f77b9e35ee8",
			"kind": "meme",
			"name": "Greenwood",
			"vol24h": 8190.5,
			"liq": null,
			"mcap": null,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "CRM",
			"address": "0xd95b44124e475743a7589e68f3d74008a5536d44",
			"kind": "stock",
			"name": "Salesforce, Inc. • Robinhood Token",
			"vol24h": 7741.74,
			"liq": 29277.22,
			"mcap": null,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "MRVL",
			"address": "0x62fd0668e10d8b72339be2dcf7643001688ff13b",
			"kind": "stock",
			"name": "Marvell Technology • Robinhood Token",
			"vol24h": 6733.75,
			"liq": 20486.26,
			"mcap": null,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "ON",
			"address": "0xbbd09f72b025360fee5c928053dca6248d35be54",
			"kind": "stock",
			"name": "ON Semiconductor Corporation • Robinhood Token",
			"vol24h": 4798.78,
			"liq": 27228.51,
			"mcap": null,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "GIGA",
			"address": "0x5baaec1b70864f01dbdb747358ff59f2e2ccf7d5",
			"kind": "meme",
			"name": "GIGA",
			"vol24h": 3781.65,
			"liq": 169742.64,
			"mcap": null,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "LITE",
			"address": "0x8ef20885f94e3d9bc7eb3080279188bd5ed7c08c",
			"kind": "stock",
			"name": "Lumentum • Robinhood Token",
			"vol24h": 2831.75,
			"liq": 31053.33,
			"mcap": null,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "STONKS",
			"address": "0xbf72347bacefe747eaf48b8a66e38babad3020a0",
			"kind": "meme",
			"name": "Stonks",
			"vol24h": 2129.95,
			"liq": 28476.47,
			"mcap": null,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "ASML",
			"address": "0x47f93d52cbec7c6d2cfc080e154002370a60daea",
			"kind": "stock",
			"name": "ASML Holding NV • Robinhood Token",
			"vol24h": 1930.27,
			"liq": 29887.52,
			"mcap": null,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "WIF",
			"address": "0xe49a1c3033ecc6b804bc423021d3f71f1a3e0f9b",
			"kind": "meme",
			"name": "RobinWifHat",
			"vol24h": 820.95,
			"liq": 44976.52,
			"mcap": null,
			"poolSeenAt": null,
			"krVenue": "Upbit+Bithumb",
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "FLOW",
			"address": "0xe59eccb15ea07a755eb9587eefda7929559e1fa6",
			"kind": "meme",
			"name": "RobinFlow",
			"vol24h": 418.51,
			"liq": 48366.78,
			"mcap": null,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "MEMESTOCK",
			"address": "0x10dc3d3719b507e6bf3fc90c3d327d8590827777",
			"kind": "meme",
			"name": "MEMESTOCK",
			"vol24h": 214.65,
			"liq": 20047.24,
			"mcap": null,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "STAR",
			"address": "0x0172fd20b8e89cb577a6edd3b800ee7b2a5b00c1",
			"kind": "meme",
			"name": "Stargazer AI",
			"vol24h": 101.9,
			"liq": 40030.69,
			"mcap": null,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "GOAT",
			"address": "0x6e9acbfbdd8b57649ffeacea4d26a81ae1395367",
			"kind": "meme",
			"name": "Absolute Goat",
			"vol24h": 1.0893594624,
			"liq": 155272.11723994985,
			"mcap": null,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "DRV",
			"address": "0x82b152f345cd4f554d90768e975bebcca3409754",
			"kind": "meme",
			"name": "Derive",
			"vol24h": .03,
			"liq": 9007319.02,
			"mcap": null,
			"poolSeenAt": null,
			"krVenue": "Upbit+Bithumb",
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		},
		{
			"symbol": "AVA",
			"address": "0xa4821316e7833c52275ad810e2049acc5a0823b2",
			"kind": "meme",
			"name": "AVA",
			"vol24h": .03,
			"liq": 1438377.33,
			"mcap": null,
			"poolSeenAt": null,
			"krVenue": "Bithumb",
			"reached": {
				"aster": true,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": true,
				"bnSpot": false,
				"kr": true,
				"rhQuoted": true,
				"rhSpot": false
			}
		},
		{
			"symbol": "FUTU",
			"address": "0xeb30663bdff0622ef4e4e5cbb4e975f19f33f51d",
			"kind": "stock",
			"name": "Futu Holdings • Robinhood Token",
			"vol24h": null,
			"liq": 27544.589981096124,
			"mcap": null,
			"poolSeenAt": null,
			"krVenue": null,
			"reached": {
				"aster": false,
				"hl": false,
				"bnAlpha": false,
				"bnPerp": false,
				"bnSpot": false,
				"kr": false,
				"rhQuoted": false,
				"rhSpot": false
			}
		}
	]
};
function usd(v) {
	if (v == null || !Number.isFinite(v)) return "–";
	const sign = v < 0 ? "−" : "";
	const n = Math.abs(v);
	if (n >= 1e9) return `${sign}$${(n / 1e9).toFixed(2)}B`;
	if (n >= 1e6) return `${sign}$${(n / 1e6).toFixed(2)}M`;
	if (n >= 1e3) return `${sign}$${(n / 1e3).toFixed(n >= 1e4 ? 0 : 1)}k`;
	return `${sign}$${n.toFixed(0)}`;
}
function pct(v, digits = 0) {
	if (v == null || !Number.isFinite(v)) return "–";
	const n = v.toFixed(digits);
	return `${v > 0 ? "+" : ""}${n}%`;
}
function num(v, digits = 0) {
	if (v == null || !Number.isFinite(v)) return "–";
	return v.toFixed(digits);
}
function stamp(ms) {
	const d = new Date(ms);
	const p = (n) => String(n).padStart(2, "0");
	return `${d.getUTCFullYear()}-${p(d.getUTCMonth() + 1)}-${p(d.getUTCDate())} ${p(d.getUTCHours())}:${p(d.getUTCMinutes())} UTC`;
}
function shortAddr(a) {
	if (!a) return "–";
	return `${a.slice(0, 6)}…${a.slice(-4)}`;
}
function turn(vol, liq) {
	if (!vol || !liq) return null;
	return vol / liq;
}
var KIND = {
	stock: "链上美股",
	paired: "与股票配对",
	meme: "纯 Meme",
	eco: "生态币",
	mirror: "仿股票"
};
function kindLabel(k) {
	return KIND[k] ?? k;
}
var createSsrRpc = (functionId) => {
	const url = "/_serverFn/" + functionId;
	const serverFnMeta = { id: functionId };
	const fn = async (...args) => {
		return (await getServerFnById(functionId, { origin: "server" }))(...args);
	};
	return Object.assign(fn, {
		url,
		serverFnMeta,
		[TSS_SERVER_FUNCTION]: true
	});
};
/** 币安 Alpha 公开列表里 chainId = 4663（Robinhood 链）的合约。只读，不写库。 */
var fetchRhAlpha = createServerFn({ method: "GET" }).handler(createSsrRpc("bc3f91d7c0778e85c67439c36f78c8c78f9ab59bea52d7ae0e460d42cbf63b75"));
var STEPS = [
	{
		key: "aster",
		label: "Aster"
	},
	{
		key: "hl",
		label: "Hyperliquid"
	},
	{
		key: "bnAlpha",
		label: "币安 Alpha"
	},
	{
		key: "bnPerp",
		label: "币安永续"
	},
	{
		key: "bnSpot",
		label: "币安现货"
	},
	{
		key: "kr",
		label: "韩所"
	}
];
var APP_STEPS = [{
	key: "rhQuoted",
	label: "有行情页"
}, {
	key: "rhSpot",
	label: "可交易"
}];
var KINDS = [
	{
		id: "all",
		label: "全部"
	},
	{
		id: "stock",
		label: "链上美股"
	},
	{
		id: "paired",
		label: "与股票配对"
	},
	{
		id: "meme",
		label: "纯 Meme"
	},
	{
		id: "eco",
		label: "生态币"
	}
];
var RULE_KIND = {
	published: "已公布硬性门槛",
	"published-vague": "只公布了原则",
	discretionary: "明示自由裁量、不接受申请",
	none: "无公开框架"
};
function rungCount(key) {
	return LADDER.rungs.find((r) => r.key === key)?.count ?? 0;
}
function verified(t) {
	return STEPS.concat(APP_STEPS).some((s) => t.reached[s.key]);
}
function recent(t) {
	if (!t.poolSeenAt) return false;
	return Date.now() - Date.parse(t.poolSeenAt) <= 2592e5;
}
function withAlpha(base, hits) {
	if (!hits?.length) return base;
	const next = base.map((t) => ({
		...t,
		reached: { ...t.reached }
	}));
	const byAddr = new Map(next.filter((t) => t.address).map((t) => [t.address, t]));
	for (const h of hits) {
		const cur = byAddr.get(h.address);
		if (cur) {
			cur.reached.bnAlpha = true;
			continue;
		}
		const row = {
			symbol: h.symbol,
			address: h.address,
			kind: "meme",
			name: h.symbol,
			vol24h: null,
			liq: null,
			mcap: null,
			poolSeenAt: null,
			reached: {
				aster: false,
				hl: false,
				bnAlpha: true,
				bnPerp: false,
				bnSpot: false,
				kr: false,
				rhQuoted: false,
				rhSpot: false
			}
		};
		next.push(row);
		byAddr.set(h.address, row);
	}
	return next;
}
function scoreCandidate(c, gates) {
	const g = gates[c.gate] ?? gates.first;
	if (!g) return {
		score: null,
		checks: []
	};
	const vals = {
		liq: c.raw?.liq ?? null,
		holders: c.raw?.holders ?? null,
		mcap: c.raw?.mcap ?? null,
		ageD: c.raw?.ageD ?? null,
		ct: c.raw?.ct ?? null,
		vol24h: c.raw?.vol24h ?? null
	};
	let got = 0;
	let known = 0;
	const checks = [];
	for (const [k, cfg] of Object.entries(g.bars)) {
		const v = vals[k] ?? null;
		if (v == null) {
			checks.push({
				label: cfg.label,
				ok: null,
				title: `${cfg.label} 这一项快照里没有，不进权重`
			});
			continue;
		}
		known += cfg.w;
		const ok = v >= cfg.bar;
		if (ok) got += cfg.w;
		const lift = cfg.lift ? ` · 毕业生相对没毕业的提升 ${cfg.lift} 倍` : "";
		checks.push({
			label: cfg.label,
			ok,
			title: `门槛 ${cfg.bar}，它是 ${v}，权重 ${cfg.w}${lift}${cfg.note ? ` · ${cfg.note}` : ""}`
		});
	}
	return {
		score: known ? Math.round(got / known * 100) : null,
		checks
	};
}
function Chip({ on, children, onClick }) {
	return /* @__PURE__ */ (0, import_jsx_runtime.jsx)("button", {
		type: "button",
		onClick,
		className: "min-h-11 rounded-full border px-3 text-sm " + (on ? "border-brass text-brass" : "border-line text-muted hover:text-fg"),
		children
	});
}
function LadderView() {
	const [kind, setKind] = (0, import_react.useState)("all");
	const [quick, setQuick] = (0, import_react.useState)("liq");
	const [query, setQuery] = (0, import_react.useState)("");
	const [rung, setRung] = (0, import_react.useState)(null);
	const [sortKey, setSortKey] = (0, import_react.useState)("vol");
	const [sortDir, setSortDir] = (0, import_react.useState)(-1);
	const [pick, setPick] = (0, import_react.useState)(null);
	const [hits, setHits] = (0, import_react.useState)(null);
	const [alphaNote, setAlphaNote] = (0, import_react.useState)("台阶数字来自公开列表快照。可以再对一次币安 Alpha。");
	const [busy, setBusy] = (0, import_react.useState)(false);
	const tokens = (0, import_react.useMemo)(() => withAlpha(LADDER.tokens, hits), [hits]);
	const rows = (0, import_react.useMemo)(() => {
		const q = query.trim().toLowerCase();
		let list = tokens.filter((t) => kind === "all" || t.kind === kind);
		if (quick === "verifiable") list = list.filter(verified);
		else if (quick === "liq") list = list.filter((t) => (t.liq || 0) >= 1e5);
		else if (quick === "recent") list = list.filter(recent);
		if (rung) list = list.filter((t) => t.reached[rung]);
		if (q) list = list.filter((t) => t.symbol.toLowerCase().includes(q) || (t.name || "").toLowerCase().includes(q));
		const val = (t) => sortKey === "vol" ? t.vol24h || 0 : sortKey === "liq" ? t.liq || 0 : t.symbol;
		return [...list].sort((a, b) => {
			const x = val(a);
			const y = val(b);
			if (typeof x === "string" && typeof y === "string") return x.localeCompare(y) * sortDir;
			return (x - y) * sortDir;
		});
	}, [
		tokens,
		kind,
		quick,
		query,
		rung,
		sortKey,
		sortDir
	]);
	const selected = tokens.find((t) => t.address === pick) ?? null;
	async function refreshAlpha() {
		setBusy(true);
		const res = await fetchRhAlpha();
		setBusy(false);
		if (!res.ok) {
			setAlphaNote(res.error);
			return;
		}
		setHits(res.tokens);
		const snap = rungCount("bnAlpha");
		setAlphaNote(res.n === snap ? `币安 Alpha 现有 ${res.n} 个 RH 链合约，与台阶计数一致。核对于 ${stamp(res.fetchedAt)}。` : `币安 Alpha 现有 ${res.n} 个 RH 链合约，快照台阶记的是 ${snap}。表里的点已按合约地址改过来。核对于 ${stamp(res.fetchedAt)}。`);
	}
	function toggleSort(key) {
		if (sortKey === key) setSortDir((d) => d === 1 ? -1 : 1);
		else {
			setSortKey(key);
			setSortDir(key === "symbol" ? 1 : -1);
		}
	}
	const first = LADDER.candidates.filter((c) => c.gate === "first").map((c) => ({
		c,
		s: scoreCandidate(c, LADDER.gates)
	})).filter((x) => x.s.score != null).sort((a, b) => (b.s.score ?? 0) - (a.s.score ?? 0)).slice(0, 6);
	const cex = LADDER.candidates.filter((c) => c.gate === "cex").map((c) => ({
		c,
		s: scoreCandidate(c, LADDER.gates)
	})).filter((x) => x.s.score != null).sort((a, b) => (b.s.score ?? 0) - (a.s.score ?? 0)).slice(0, 4);
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
		id: "sec-ladder",
		className: "mx-auto flex max-w-7xl flex-col gap-6 px-4 py-6",
		children: [
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", {
				className: "max-w-3xl text-sm text-pretty text-muted",
				children: "只统计 Robinhood 链上的币。每一格是这些币里有多少个走到了那一级 —— 链上谁都能发，能在 App 里真正买到的是个位数。 交易所那一路和 Robinhood App 那一路从链上分出去，互不为前提。身份按合约地址或报价偏离 8% 以内核对，只对上符号不算。"
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
				className: "flex flex-col gap-3 rounded-xl border border-line bg-surface p-4",
				children: [
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)(Track, {
						label: "基线",
						steps: [{
							key: "onchain",
							label: "链上有量的币",
							count: rungCount("onchain")
						}],
						rung,
						onPick: setRung
					}),
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)(Track, {
						label: "交易所",
						steps: STEPS.map((s) => ({
							...s,
							count: rungCount(s.key)
						})),
						rung,
						onPick: setRung,
						joiner: [
							"dot",
							"dot",
							"arrow",
							"arrow",
							"arrow",
							"arrow"
						]
					}),
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)(Track, {
						label: "Robinhood App",
						steps: APP_STEPS.map((s) => ({
							...s,
							count: rungCount(s.key)
						})),
						rung,
						onPick: setRung,
						joiner: ["arrow", "arrow"]
					}),
					/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
						className: "flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between",
						children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", {
							className: "text-xs text-pretty text-muted",
							children: alphaNote
						}), /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("button", {
							type: "button",
							onClick: refreshAlpha,
							disabled: busy,
							className: "inline-flex min-h-11 shrink-0 items-center justify-center gap-2 rounded-full border border-line px-4 text-sm text-fg hover:border-brass disabled:opacity-60",
							children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)(RefreshCw, { className: "size-4 " + (busy ? "animate-spin" : "") }), busy ? "正在对币安" : "对一次币安 Alpha"]
						})]
					})
				]
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
				className: "grid gap-3 lg:grid-cols-2",
				children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)(GateCard, {
					title: "离「上第一个交易所」最近",
					gate: LADDER.gates.first,
					rows: first,
					onPick: setPick
				}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)(GateCard, {
					title: "离「从 Alpha 进币安 CEX」最近",
					gate: LADDER.gates.cex,
					rows: cex,
					onPick: setPick
				})]
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("section", {
				className: "grid gap-3 lg:grid-cols-2",
				children: [/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
					className: "rounded-xl border border-line bg-surface p-4",
					children: [
						/* @__PURE__ */ (0, import_jsx_runtime.jsx)("h2", {
							className: "text-sm font-medium text-clay",
							children: "别被成交额骗了"
						}),
						/* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", {
							className: "mt-1 text-xs text-muted",
							children: "成交额排在前面，但换手、池深或币龄过不了硬门槛。"
						}),
						/* @__PURE__ */ (0, import_jsx_runtime.jsx)("ul", {
							className: "mt-3 flex flex-col gap-2",
							children: LADDER.ruledOut.map((r, i) => /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("li", {
								className: "text-sm",
								children: [
									/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
										className: "font-mono text-fg",
										children: r.symbol
									}),
									/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", {
										className: "ml-2 font-mono text-xs text-muted",
										children: [
											"24h ",
											usd(r.vol24h),
											" · 池深 ",
											usd(r.liq)
										]
									}),
									/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
										className: "mt-0.5 block text-xs text-pretty text-muted",
										children: r.why
									})
								]
							}, r.symbol + i))
						})
					]
				}), /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
					className: "rounded-xl border border-line bg-surface p-4",
					children: [
						/* @__PURE__ */ (0, import_jsx_runtime.jsx)("h2", {
							className: "text-sm font-medium",
							children: "现实里，发射台出身的币上过几家"
						}),
						/* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", {
							className: "mt-1 text-xs text-pretty text-muted",
							children: LADDER.listingHistory.note
						}),
						/* @__PURE__ */ (0, import_jsx_runtime.jsx)("ul", {
							className: "mt-3 flex flex-col gap-2 text-sm",
							children: [
								["币安现货", LADDER.listingHistory.bnSpot],
								["币安永续", LADDER.listingHistory.bnPerp],
								["韩所", LADDER.listingHistory.kr],
								["Coinbase", LADDER.listingHistory.coinbase]
							].map(([name, x]) => /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("li", { children: [
								/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
									className: "text-fg",
									children: name
								}),
								/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
									className: "ml-2 font-mono text-brass",
									children: x.n
								}),
								/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
									className: "mt-0.5 block text-xs text-pretty text-muted",
									children: x.detail
								})
							] }, name))
						}),
						/* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", {
							className: "mt-3 text-xs text-pretty text-muted",
							children: LADDER.listingHistory.insight
						}),
						/* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", {
							className: "mt-2 text-xs text-pretty text-muted",
							children: LADDER.listingHistory.pons
						})
					]
				})]
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("section", { children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("h2", {
				className: "text-sm font-medium",
				children: "各场所自己写了什么"
			}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
				className: "mt-3 grid gap-3 md:grid-cols-2",
				children: Object.values(LADDER.venueRules).map((v) => /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("article", {
					className: "rounded-xl border border-line bg-surface p-4",
					children: [
						/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
							className: "flex flex-wrap items-baseline gap-2",
							children: [
								/* @__PURE__ */ (0, import_jsx_runtime.jsx)("h3", {
									className: "text-sm font-medium",
									children: v.venue
								}),
								/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
									className: "text-xs text-brass",
									children: RULE_KIND[v.kind] ?? v.kind
								}),
								/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
									className: "text-xs text-muted",
									children: v.src
								})
							]
						}),
						/* @__PURE__ */ (0, import_jsx_runtime.jsx)("ul", {
							className: "mt-2 list-disc pl-4 text-sm text-fg",
							children: v.must.map((m) => /* @__PURE__ */ (0, import_jsx_runtime.jsx)("li", {
								className: "text-pretty",
								children: m.text
							}, m.text))
						}),
						v.note ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", {
							className: "mt-2 text-xs text-pretty text-muted",
							children: v.note
						}) : null
					]
				}, v.venue))
			})] }),
			/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("section", {
				className: "rounded-xl border border-line bg-surface",
				children: [
					/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
						className: "flex flex-col gap-3 border-b border-line p-4",
						children: [
							/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
								className: "flex flex-wrap items-center justify-between gap-2",
								children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("h2", {
									className: "text-sm font-medium",
									children: "台阶名册"
								}), /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("p", {
									className: "font-mono text-xs text-muted",
									children: [
										rows.length,
										" 行 · 快照 ",
										stamp(LADDER.ts),
										" · 样本 ",
										LADDER.coverage.active,
										"/",
										LADDER.coverage.universe
									]
								})]
							}),
							/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
								className: "flex flex-wrap gap-2",
								children: KINDS.map((k) => /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(Chip, {
									on: kind === k.id,
									onClick: () => setKind(k.id),
									children: [k.label, /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
										className: "ml-1 font-mono text-xs",
										children: k.id === "all" ? LADDER.coverage.active : LADDER.kinds[k.id] ?? 0
									})]
								}, k.id))
							}),
							/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
								className: "flex flex-wrap gap-2",
								children: [
									/* @__PURE__ */ (0, import_jsx_runtime.jsx)(Chip, {
										on: quick === "liq",
										onClick: () => setQuick("liq"),
										children: "池深 ≥ $100k"
									}),
									/* @__PURE__ */ (0, import_jsx_runtime.jsx)(Chip, {
										on: quick === "verifiable",
										onClick: () => setQuick("verifiable"),
										children: "已核实到某一级"
									}),
									/* @__PURE__ */ (0, import_jsx_runtime.jsx)(Chip, {
										on: quick === "recent",
										onClick: () => setQuick("recent"),
										children: "72h 内新池"
									}),
									/* @__PURE__ */ (0, import_jsx_runtime.jsx)(Chip, {
										on: quick === "all",
										onClick: () => setQuick("all"),
										children: "名册全部"
									}),
									rung ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Chip, {
										on: true,
										onClick: () => setRung(null),
										children: "清除台阶筛选"
									}) : null,
									/* @__PURE__ */ (0, import_jsx_runtime.jsx)("input", {
										value: query,
										onChange: (e) => setQuery(e.target.value),
										placeholder: "搜符号或名字",
										className: "min-h-11 min-w-40 flex-1 rounded-full border border-line bg-bg px-4 text-sm text-fg outline-none placeholder:text-muted focus:border-brass"
									})
								]
							})
						]
					}),
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
						className: "max-w-full overflow-x-auto",
						children: /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("table", {
							className: "w-full min-w-max border-collapse text-sm",
							children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("thead", { children: /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("tr", {
								className: "text-left text-xs text-muted",
								children: [
									/* @__PURE__ */ (0, import_jsx_runtime.jsx)("th", {
										className: "px-4 py-2 font-medium",
										children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)("button", {
											type: "button",
											className: "min-h-11",
											onClick: () => toggleSort("symbol"),
											children: "代币"
										})
									}),
									/* @__PURE__ */ (0, import_jsx_runtime.jsx)("th", {
										className: "px-2 py-2 font-medium",
										children: "类型"
									}),
									/* @__PURE__ */ (0, import_jsx_runtime.jsx)("th", {
										className: "px-2 py-2 text-right font-medium",
										children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)("button", {
											type: "button",
											className: "min-h-11",
											onClick: () => toggleSort("vol"),
											children: "24h 成交"
										})
									}),
									/* @__PURE__ */ (0, import_jsx_runtime.jsx)("th", {
										className: "px-2 py-2 text-right font-medium",
										children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)("button", {
											type: "button",
											className: "min-h-11",
											onClick: () => toggleSort("liq"),
											children: "池深"
										})
									}),
									/* @__PURE__ */ (0, import_jsx_runtime.jsx)("th", {
										className: "px-2 py-2 text-right font-medium",
										children: "换手"
									}),
									STEPS.concat(APP_STEPS).map((s) => /* @__PURE__ */ (0, import_jsx_runtime.jsx)("th", {
										className: "px-2 py-2 text-center font-medium",
										children: s.label
									}, s.key))
								]
							}) }), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("tbody", { children: rows.slice(0, 80).map((t) => {
								const on = t.address === pick;
								const tv = turn(t.vol24h, t.liq);
								return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("tr", {
									onClick: () => setPick(t.address),
									className: "cursor-pointer border-t border-line " + (on ? "bg-surface-2" : "hover:bg-bg"),
									children: [
										/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("td", {
											className: "px-4 py-2",
											children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
												className: "font-mono text-fg",
												children: t.symbol
											}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
												className: "max-w-48 truncate text-xs text-muted",
												children: (t.name || "").replace(/\s*•\s*Robinhood Token$/i, "")
											})]
										}),
										/* @__PURE__ */ (0, import_jsx_runtime.jsx)("td", {
											className: "px-2 py-2 text-xs text-muted",
											children: kindLabel(t.kind)
										}),
										/* @__PURE__ */ (0, import_jsx_runtime.jsx)("td", {
											className: "px-2 py-2 text-right font-mono tabular-nums",
											children: usd(t.vol24h)
										}),
										/* @__PURE__ */ (0, import_jsx_runtime.jsx)("td", {
											className: "px-2 py-2 text-right font-mono tabular-nums",
											children: usd(t.liq)
										}),
										/* @__PURE__ */ (0, import_jsx_runtime.jsx)("td", {
											className: "px-2 py-2 text-right font-mono tabular-nums " + ((tv ?? 0) > 20 ? "text-clay" : ""),
											children: tv == null ? "–" : `${tv.toFixed(1)}x`
										}),
										STEPS.concat(APP_STEPS).map((s) => /* @__PURE__ */ (0, import_jsx_runtime.jsx)("td", {
											className: "px-2 py-2 text-center",
											children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
												className: t.reached[s.key] ? "text-moss" : "text-line",
												children: t.reached[s.key] ? "●" : "·"
											})
										}, s.key))
									]
								}, (t.address || t.symbol) + (t.vol24h || 0));
							}) })]
						})
					}),
					rows.length > 80 ? /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("p", {
						className: "px-4 py-3 text-xs text-muted",
						children: [
							"只展开成交靠前的 80 行，共 ",
							rows.length,
							" 行。用筛选或搜索收窄。"
						]
					}) : null,
					!rows.length ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", {
						className: "px-4 py-6 text-sm text-muted",
						children: "这个筛选下没有币。"
					}) : null
				]
			}),
			selected ? /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("aside", {
				className: "rounded-xl border border-brass/40 bg-surface p-4",
				children: [
					/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
						className: "flex flex-wrap items-baseline justify-between gap-2",
						children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("h2", {
							className: "font-mono text-lg",
							children: selected.symbol
						}), /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
							className: "flex flex-wrap gap-3 text-sm",
							children: [selected.address ? /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("a", {
								className: "inline-flex min-h-11 items-center gap-1 text-brass",
								href: `https://dexscreener.com/robinhood/${selected.address}`,
								target: "_blank",
								rel: "noreferrer",
								children: ["DexScreener ", /* @__PURE__ */ (0, import_jsx_runtime.jsx)(ExternalLink, { className: "size-3.5" })]
							}) : null, selected.address ? /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("a", {
								className: "inline-flex min-h-11 items-center gap-1 text-brass",
								href: `https://robinscan.io/token/${selected.address}`,
								target: "_blank",
								rel: "noreferrer",
								children: [
									shortAddr(selected.address),
									" ",
									/* @__PURE__ */ (0, import_jsx_runtime.jsx)(ExternalLink, { className: "size-3.5" })
								]
							}) : null]
						})]
					}),
					/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("p", {
						className: "text-sm text-muted",
						children: [
							kindLabel(selected.kind),
							" · ",
							(selected.name || "").replace(/\s*•\s*Robinhood Token$/i, "")
						]
					}),
					/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("dl", {
						className: "mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4",
						children: [
							/* @__PURE__ */ (0, import_jsx_runtime.jsx)(Stat, {
								k: "24h 成交",
								v: usd(selected.vol24h)
							}),
							/* @__PURE__ */ (0, import_jsx_runtime.jsx)(Stat, {
								k: "池深",
								v: usd(selected.liq)
							}),
							/* @__PURE__ */ (0, import_jsx_runtime.jsx)(Stat, {
								k: "换手",
								v: turn(selected.vol24h, selected.liq) == null ? "–" : `${turn(selected.vol24h, selected.liq).toFixed(1)}x`
							}),
							/* @__PURE__ */ (0, import_jsx_runtime.jsx)(Stat, {
								k: "市值",
								v: usd(selected.mcap)
							})
						]
					}),
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
						className: "mt-3 flex flex-wrap gap-2",
						children: STEPS.concat(APP_STEPS).map((s) => /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", {
							className: "rounded-full border px-3 py-1 text-xs " + (selected.reached[s.key] ? "border-moss text-moss" : "border-line text-muted"),
							children: [s.label, s.key === "kr" && selected.krVenue && selected.reached.kr ? ` · ${selected.krVenue}` : ""]
						}, s.key))
					})
				]
			}) : /* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", {
				className: "text-xs text-muted",
				children: "点名册里的一行，看它走到了哪一级。"
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("details", {
				className: "text-sm text-muted",
				children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("summary", {
					className: "min-h-11 cursor-pointer text-fg",
					children: "口径"
				}), /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
					className: "mt-2 max-w-3xl space-y-2 text-xs text-pretty leading-relaxed",
					children: [
						/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("p", { children: [
							"台阶计数是快照时刻的全样本（",
							LADDER.coverage.active,
							" / 宇宙 ",
							LADDER.coverage.universe,
							"），不是下面这张表的行数。名册为了能点开，只留下池深 ≥ $20k、或 24h 成交 ≥ $8k、或已经核实到某一级的币。"
						] }),
						/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("p", { children: [
							"两道门用两套标准，权重来自已上币的实证，不是一把尺子量所有人。第一道门（上第一个交易所）基线 ",
							LADDER.gates.first?.base,
							"% ，",
							LADDER.gates.first?.note,
							"：持币地址是唯一没有明显反向因果的领先指标。第二道门（Alpha → 币安 CEX）基线 ",
							LADDER.gates.cex?.base,
							"% ，",
							LADDER.gates.cex?.note,
							"，几乎只看体量。"
						] }),
						/* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", { children: "硬性排除：换手（成交 ÷ 池深）超过 20 倍、池深低于 $5 万、开池不足 3 天。Aster 的公开规则要求先有币安 Alpha 或 Tier 2，所以图上它和 Hyperliquid 并排，并不表示它是 Alpha 的上游。" }),
						/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("p", { children: [
							"币安 Alpha 进 CEX 的年龄切片（样本 n=",
							LADDER.alphaRef.n,
							"）：",
							Object.entries(LADDER.alphaRef.ageConversion).map(([k, v]) => ` ${k} ${v.cex}/${v.n}`).join(" ·"),
							"。近 30 天新上的还没有一个进 CEX。"
						] })
					]
				})]
			})
		]
	});
}
function Stat({ k, v }) {
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("dt", {
		className: "text-xs text-muted",
		children: k
	}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("dd", {
		className: "font-mono tabular-nums",
		children: v
	})] });
}
function Track({ label, steps, rung, onPick, joiner }) {
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
		className: "flex flex-col gap-2 sm:flex-row sm:items-center",
		children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
			className: "w-28 shrink-0 font-mono text-xs text-muted",
			children: label
		}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
			className: "flex flex-wrap items-center gap-1",
			children: steps.map((s, i) => {
				const join = joiner?.[i] ?? (i === 0 ? "none" : "arrow");
				const on = rung === s.key;
				return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", {
					className: "inline-flex items-center gap-1",
					children: [
						i > 0 && join === "arrow" ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
							className: "px-0.5 text-muted",
							children: "→"
						}) : null,
						i > 0 && join === "dot" ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
							className: "px-0.5 text-muted",
							children: "·"
						}) : null,
						/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("button", {
							type: "button",
							onClick: () => onPick(on ? null : s.key),
							className: "flex min-h-11 min-w-16 flex-col items-start rounded-lg border px-3 py-1 " + (on ? "border-brass bg-bg" : "border-line hover:border-brass"),
							children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
								className: "font-mono text-xl leading-none tabular-nums text-fg",
								children: s.count
							}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
								className: "text-xs text-muted",
								children: s.label
							})]
						})
					]
				}, s.key);
			})
		})]
	});
}
function GateCard({ title, gate, rows, onPick }) {
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("section", {
		className: "rounded-xl border border-line bg-surface p-4",
		children: [
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)("h2", {
				className: "text-sm font-medium",
				children: title
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", {
				className: "mt-1 text-xs text-pretty text-muted",
				children: gate ? `基线 ${gate.base}% · ${gate.note}。悬停标签看门槛。缺数据的项不进分。` : "没有这道门的参数。"
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)("ul", {
				className: "mt-3 flex flex-col gap-3",
				children: rows.map(({ c, s }) => /* @__PURE__ */ (0, import_jsx_runtime.jsx)("li", { children: /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("button", {
					type: "button",
					onClick: () => onPick(c.address),
					className: "w-full text-left",
					children: [/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
						className: "flex flex-wrap items-baseline gap-2",
						children: [
							/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
								className: "font-mono",
								children: c.symbol
							}),
							/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
								className: "font-mono tabular-nums " + ((s.score ?? 0) >= 70 ? "text-moss" : (s.score ?? 0) >= 40 ? "text-brass" : "text-muted"),
								children: s.score
							}),
							/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", {
								className: "text-xs text-muted",
								children: ["下一级 ", c.next]
							}),
							c.already?.length ? /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", {
								className: "text-xs text-muted",
								children: ["已在 ", c.already.join(" + ")]
							}) : null
						]
					}), /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
						className: "mt-1 flex flex-wrap gap-1",
						children: [s.checks.map((ch) => /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
							title: ch.title,
							className: "rounded-full border px-2 py-0.5 text-xs " + (ch.ok ? "border-moss text-moss" : ch.ok === false ? "border-clay text-clay" : "border-line text-muted"),
							children: ch.label
						}, ch.label)), c.alphaPct?.mcap != null ? /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", {
							className: "rounded-full border border-line px-2 py-0.5 text-xs text-muted",
							title: "在币安 Alpha 在架币里的市值分位",
							children: [
								"Alpha 分位 ",
								c.alphaPct.mcap,
								"%"
							]
						}) : null]
					})]
				}) }, c.address + c.gate))
			})
		]
	});
}
var ROWS = [
	[
		"Heat",
		"6h/18h 量比 35、笔数比 20、买家加速 15、6h 涨幅 15、持币 6h 增长 15",
		"加速度用非重叠窗：(近 6h 小时均量) / (再往前 18h 小时均量)。DexScreener 的 h6、h24 第一小时就能算。"
	],
	[
		"Quality",
		"池深 25、Vol/LP 减分 20、独立买家/买单笔数 20、持币数 15、Top10 减分 10、币龄 10",
		"独立买家除以买单笔数越低，越像少数地址来回刷。Vol/LP 高是减分，不是热闹。"
	],
	[
		"Entry",
		"100 减去：距 7 日低点的倍数、24h 涨幅、Vol/LP、1h 卖压、72h 高点腰斩",
		"用来挡「路径更像能上所，但价格已经走完」。"
	],
	[
		"ListingP",
		"频率表，不是回归",
		"已上币安永续就直接写。已在 Alpha，按格子查 30 天内上永续的比例。纯链上要等自己的观察池满 30 天。格子样本 < 20 写「不确定」。"
	]
];
function MethodView() {
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
		id: "sec-method",
		className: "mx-auto flex max-w-3xl flex-col gap-6 px-4 py-6",
		children: [
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", {
				className: "text-sm text-pretty text-muted",
				children: "阶梯回答「走到了哪一级」。四列回答「这一小时的量和筹码像不像还早、还干净」。两套数字不要加成一个总分。"
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)("section", {
				className: "flex flex-col gap-3",
				children: ROWS.map(([name, mix, note]) => /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("article", {
					className: "rounded-xl border border-line bg-surface p-4",
					children: [
						/* @__PURE__ */ (0, import_jsx_runtime.jsx)("h2", {
							className: "text-sm font-medium",
							children: name
						}),
						/* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", {
							className: "mt-1 text-sm text-pretty",
							children: mix
						}),
						/* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", {
							className: "mt-2 text-xs text-pretty text-muted",
							children: note
						})
					]
				}, name))
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("section", {
				className: "rounded-xl border border-line p-4",
				children: [
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)("h2", {
						className: "text-sm font-medium",
						children: "READY 要七条一起满足"
					}),
					/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("ol", {
						className: "mt-2 list-decimal space-y-1 pl-5 text-sm",
						children: [
							/* @__PURE__ */ (0, import_jsx_runtime.jsx)("li", { children: "Heat ≥ 55" }),
							/* @__PURE__ */ (0, import_jsx_runtime.jsx)("li", { children: "Quality ≥ 60" }),
							/* @__PURE__ */ (0, import_jsx_runtime.jsx)("li", { children: "Entry ≥ 60" }),
							/* @__PURE__ */ (0, import_jsx_runtime.jsx)("li", { children: "自己的小时快照至少 6 根" }),
							/* @__PURE__ */ (0, import_jsx_runtime.jsx)("li", { children: "连续 3 小时 Heat 达标" }),
							/* @__PURE__ */ (0, import_jsx_runtime.jsx)("li", { children: "持币地址 6 小时不下降（没有这项数据时不卡）" }),
							/* @__PURE__ */ (0, import_jsx_runtime.jsx)("li", { children: "6 小时买单笔数不少于卖单" })
						]
					}),
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", {
						className: "mt-3 text-xs text-pretty text-muted",
						children: "缺数据的分项跳过，权重按剩下的重新归一，所以第一小时也有分，历史攒够了才准进 READY。升级马上生效。往下降要连续 2 小时还是一样，避免来回跳。池子浅于 $10k 直接 INVALID。24h 涨幅超过 500%，或者超过 300% 且 Vol/LP 大于 10，或者 Entry 低于 25，立刻 OVERHEATED。"
					})
				]
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("section", {
				className: "rounded-xl border border-line p-4",
				children: [
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)("h2", {
						className: "text-sm font-medium",
						children: "ListingP 省掉的那块脏活"
					}),
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", {
						className: "mt-2 text-sm text-pretty text-muted",
						children: "不用对公告。币安 Alpha 列表自带 listingTime、chainId 和合约地址；币安永续的 exchangeInfo 自带 onboardDate；现货没有上线日，用第一根日 K 的开盘时间。全链 Alpha 币 7 / 30 / 90 天内有没有上永续，一次请求就能成表。"
					}),
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", {
						className: "mt-2 text-sm text-pretty text-muted",
						children: "两个坑已经处理：删失 —— 上 Alpha 不满 30 天的不进 30 天分母，不能当成没上。撞名 —— 永续比 Alpha 早一天以上，当作不是同一个币，或早就上过，剔出分母。格子先看 RH 链、2026-09-08 币安 Alpha 2.0 接入之后，再看全链近 180 天，最后才是全链全时段。"
					})
				]
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("section", {
				className: "rounded-xl border border-line p-4",
				children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("h2", {
					className: "text-sm font-medium",
					children: "这页现在做不到的"
				}), /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("ul", {
					className: "mt-2 list-disc space-y-1 pl-5 text-sm text-pretty text-muted",
					children: [
						/* @__PURE__ */ (0, import_jsx_runtime.jsx)("li", { children: "小时快照库还没在这台预览里常驻。阶梯用的是一份已核对过的公开列表快照，币安 Alpha 可以现对。" }),
						/* @__PURE__ */ (0, import_jsx_runtime.jsx)("li", { children: "GeckoTerminal 和 DexScreener 的公开层容易 429，所以四列沙盘用成型行情把规则跑通，而不是假装每一行都有 6 小时加速度。" }),
						/* @__PURE__ */ (0, import_jsx_runtime.jsx)("li", { children: "Aster、Hyperliquid、韩所、Robinhood App 没有链上合约可对，只能比报价。对不上的同名币不进台阶。" }),
						/* @__PURE__ */ (0, import_jsx_runtime.jsx)("li", { children: "手递手对倒的洗量检测还没做。Quality 里的独立买家比和 Vol/LP 只能挡住一部分。换手超过 20 倍的，阶梯页直接标出来。" })
					]
				})]
			})
		]
	});
}
var T0 = 179e7 - 800;
var DAY_MS = 864e5;
var OBS_MIN_LIQ = 25e3;
var OBS_MIN_VOL24 = 2e4;
var INVALID_LIQ = 1e4;
var READY_MIN_SNAPSHOTS = 6;
var DOWNGRADE_CONFIRM_HOURS = 2;
var OVERHEAT_PC24 = 300;
var OVERHEAT_VOL_LIQ = 10;
var OVERHEAT_PC24_HARD = 500;
var LISTING_MIN_N = 20;
var REGIME_CUTOFF_MS = 17888256e5;
var CHAIN_ID = "4663";
var RANK = {
	INVALID: 0,
	WATCH: 1,
	ACCELERATING: 2,
	RESEARCH: 3,
	READY: 4,
	OVERHEATED: 5
};
var CAST = [
	{
		address: "0x" + "a".repeat(40),
		symbol: "RISER",
		kind: "accel"
	},
	{
		address: "0x" + "b".repeat(40),
		symbol: "PUMP",
		kind: "pump"
	},
	{
		address: "0x" + "c".repeat(40),
		symbol: "FLAT",
		kind: "flat"
	},
	{
		address: "0x" + "d".repeat(40),
		symbol: "DUST",
		kind: "dust"
	},
	{
		address: "0x" + "e".repeat(40),
		symbol: "ALPHA1",
		kind: "flat"
	}
];
function lin(x, lo, hi) {
	if (x == null || Number.isNaN(x)) return null;
	if (hi === lo) return x >= hi ? 1 : 0;
	return Math.max(0, Math.min(1, (x - lo) / (hi - lo)));
}
function wavg(parts) {
	const got = parts.filter((p) => p.v != null);
	if (!got.length) return null;
	const s = got.reduce((a, p) => a + p.w * p.v, 0);
	const w = got.reduce((a, p) => a + p.w, 0);
	return Math.round(100 * s / w * 10) / 10;
}
function ratio(a, b, floor) {
	if (a == null || b == null) return null;
	return a / Math.max(b, floor);
}
function share(b, s) {
	if (b == null || s == null || b + s === 0) return null;
	return Math.round(b / (b + s) * 1e3) / 1e3;
}
function snapAt(h, c) {
	let v24, v6, v1, liq, pc24, pc6, price;
	if (c.kind === "accel") {
		v24 = 4e5 + 6e4 * h;
		v6 = 25e4 + 4e4 * h;
		v1 = 7e4 + 8e3 * h;
		liq = 3e5;
		pc24 = 60;
		pc6 = 25;
		price = 1 + .03 * h;
	} else if (c.kind === "pump") {
		v24 = 5e6;
		v6 = 3e6;
		v1 = 8e5;
		liq = 6e4;
		pc24 = 800;
		pc6 = 300;
		price = 9;
	} else if (c.kind === "dust") {
		v24 = 5e3;
		v6 = 1e3;
		v1 = 100;
		liq = 3e3;
		pc24 = 5;
		pc6 = 1;
		price = .1;
	} else {
		v24 = 1e5;
		v6 = 25e3;
		v1 = 4e3;
		liq = 2e5;
		pc24 = 2;
		pc6 = 0;
		price = 1;
	}
	const b6 = Math.trunc(v6 / 300);
	return {
		ts: T0 + h * 3600,
		address: c.address,
		symbol: c.symbol,
		price,
		mcap: price * 1e7,
		liq,
		vol_h1: v1,
		vol_h6: v6,
		vol_h24: v24,
		buys_h1: Math.trunc(v1 / 250),
		sells_h1: Math.trunc(v1 / 400),
		buys_h6: b6,
		sells_h6: Math.trunc(b6 * .7),
		buys_h24: Math.trunc(v24 / 300),
		sells_h24: Math.trunc(v24 / 400),
		pc_h6: pc6,
		pc_h24: pc24,
		holders: c.kind === "accel" ? 1500 + 60 * h : 900,
		top10_pct: 22,
		buyers_h1: 40 + 5 * h,
		buyers_h24: 400,
		pair_created: 1788271200
	};
}
function inObs(s) {
	return s.liq >= OBS_MIN_LIQ && s.vol_h24 >= OBS_MIN_VOL24;
}
function features(s, hist, nHist) {
	s.vol_h1;
	const v6 = s.vol_h6 || 0;
	const v24 = s.vol_h24 || 0;
	const t6 = (s.buys_h6 || 0) + (s.sells_h6 || 0);
	const t24 = (s.buys_h24 || 0) + (s.sells_h24 || 0);
	const f = {
		vol_accel_6v18: v24 ? ratio(v6 / 6, Math.max(v24 - v6, 0) / 18, 100) : null,
		tx_accel_6v18: t24 ? ratio(t6 / 6, Math.max(t24 - t6, 0) / 18, 1) : null,
		buy_ratio_h1: share(s.buys_h1, s.sells_h1),
		buy_ratio_h6: share(s.buys_h6, s.sells_h6),
		vol_liq: s.liq ? v24 / s.liq : null,
		buyer_accel: s.buyers_h1 != null && s.buyers_h24 ? ratio(s.buyers_h1, s.buyers_h24 / 24, 1) : null,
		holder_g6: null,
		holder_g24: null,
		runup_from_low: null,
		dd_from_high: null,
		n_hist: nHist
	};
	if (s.holders) for (const [key, hrs] of [["holder_g6", 6], ["holder_g24", 24]]) {
		const old = hist.filter((r) => r.holders && Math.abs(r.ts - (s.ts - hrs * 3600)) <= 1800);
		if (old.length) f[key] = Math.round(100 * (s.holders / old[old.length - 1].holders - 1) * 100) / 100;
	}
	const lows = [...hist.map((r) => r.price).filter((p) => p)];
	const highs = hist.filter((r) => r.price && r.ts >= s.ts - 259200).map((r) => r.price);
	if (s.price && s.pc_h24 > -99) lows.push(s.price / (1 + s.pc_h24 / 100));
	f.runup_from_low = s.price && lows.length ? Math.round(s.price / Math.min(...lows) * 100) / 100 : null;
	const highPool = highs.length ? highs : [];
	f.dd_from_high = s.price && (highPool.length || s.price) ? Math.round(100 * (1 - s.price / Math.max(...highPool, s.price)) * 10) / 10 : null;
	return f;
}
function part(label, weight, raw, mapped) {
	return {
		label,
		weight,
		raw,
		mapped
	};
}
function heatBundle(s, f) {
	const parts = [
		part("6h/18h 量比", 35, f.vol_accel_6v18 == null ? "缺" : `${f.vol_accel_6v18.toFixed(2)}x`, lin(f.vol_accel_6v18, 1, 3)),
		part("6h/18h 笔数比", 20, f.tx_accel_6v18 == null ? "缺" : `${f.tx_accel_6v18.toFixed(2)}x`, lin(f.tx_accel_6v18, 1, 3)),
		part("买家加速", 15, f.buyer_accel == null ? "缺" : `${f.buyer_accel.toFixed(2)}x`, lin(f.buyer_accel, 1, 3)),
		part("6h 涨幅", 15, s.pc_h6 == null ? "缺" : `${s.pc_h6.toFixed(0)}%`, lin(s.pc_h6, 0, 100)),
		part("持币 6h", 15, f.holder_g6 == null ? "缺" : `${f.holder_g6.toFixed(1)}%`, lin(f.holder_g6, 0, 5))
	];
	return {
		score: wavg(parts.map((p) => ({
			w: p.weight,
			v: p.mapped
		}))),
		parts
	};
}
function qualityBundle(s, f, ageDays) {
	const uniq = s.buyers_h24 && s.buys_h24 ? s.buyers_h24 / s.buys_h24 : null;
	const liq = s.liq || 0;
	const parts = [
		part("池深", 25, liq ? `$${(liq / 1e3).toFixed(0)}k` : "缺", liq > 0 ? lin(Math.log10(liq), Math.log10(25e3), 6) : null),
		part("Vol/LP（减分）", 20, f.vol_liq == null ? "缺" : f.vol_liq.toFixed(1), f.vol_liq == null ? null : 1 - (lin(f.vol_liq, 3, 15) ?? 0)),
		part("独立买家/笔数", 20, uniq == null ? "缺" : uniq.toFixed(2), lin(uniq, .15, .6)),
		part("持币数", 15, s.holders ? s.holders.toLocaleString("en-US") : "缺", s.holders ? lin(Math.log10(s.holders), 2.5, 4) : null),
		part("Top10（减分）", 10, s.top10_pct == null ? "缺" : `${s.top10_pct.toFixed(0)}%`, s.top10_pct == null ? null : 1 - (lin(s.top10_pct, 20, 60) ?? 0)),
		part("币龄", 10, ageDays == null ? "缺" : `${ageDays.toFixed(0)}天`, lin(ageDays, .5, 14))
	];
	return {
		score: wavg(parts.map((p) => ({
			w: p.weight,
			v: p.mapped
		}))),
		parts
	};
}
function entryBundle(s, f) {
	const notes = [];
	let pen = 0;
	if (f.runup_from_low != null) {
		const x = 40 * (lin(f.runup_from_low, 2, 10) ?? 0);
		pen += x;
		notes.push(`距 7 日低点 ${f.runup_from_low.toFixed(2)}x → −${x.toFixed(0)}`);
	} else notes.push("距低点：缺历史");
	const p24 = 25 * (lin(s.pc_h24, 100, 500) ?? 0);
	pen += p24;
	notes.push(`24h ${s.pc_h24.toFixed(0)}% → −${p24.toFixed(0)}`);
	const pv = 15 * (lin(f.vol_liq, 5, 15) ?? 0);
	pen += pv;
	notes.push(`Vol/LP ${f.vol_liq == null ? "缺" : f.vol_liq.toFixed(1)} → −${pv.toFixed(0)}`);
	if (f.buy_ratio_h1 != null && f.buy_ratio_h1 < .45) {
		pen += 10;
		notes.push("1h 买单占比 < 45% → −10");
	}
	if (f.dd_from_high != null && f.dd_from_high > 50) {
		pen += 15;
		notes.push(`自 72h 高点回撤 ${f.dd_from_high.toFixed(0)}% → −15`);
	}
	return {
		score: Math.round(Math.max(0, 100 - pen) * 10) / 10,
		notes
	};
}
function scenarioEvents() {
	const rows = [{
		chain_id: CHAIN_ID,
		alpha_ms: 178974e7,
		perp_ms: null
	}];
	for (let i = 0; i < 60; i++) {
		const alpha_ms = 17727192e5;
		rows.push({
			chain_id: "56",
			alpha_ms,
			perp_ms: alpha_ms + (i < 21 ? 10 : 60) * DAY_MS
		});
	}
	return rows;
}
function baseRates(now, firstObs, alphaSince) {
	const nowMs = now * 1e3;
	const windows = [
		["7", 7],
		["30", 30],
		["90", 90]
	];
	const cells = /* @__PURE__ */ new Map();
	for (const e of scenarioEvents()) {
		if (e.perp_ms === -1) continue;
		const eras = ["all"];
		if (e.alpha_ms >= REGIME_CUTOFF_MS) eras.push("post");
		if (e.alpha_ms >= nowMs - 180 * DAY_MS) eras.push("recent");
		const chains = ["*", ...e.chain_id === CHAIN_ID ? [CHAIN_ID] : []];
		for (const ch of chains) for (const era of eras) {
			const k = `${ch}|${era}`;
			let c = cells.get(k);
			if (!c) {
				c = {};
				for (const [w] of windows) {
					c["n" + w] = 0;
					c["h" + w] = 0;
				}
				cells.set(k, c);
			}
			for (const [w, d] of windows) {
				if (e.alpha_ms + d * DAY_MS > nowMs) continue;
				c["n" + w] = (c["n" + w] ?? 0) + 1;
				if (e.perp_ms && e.perp_ms - e.alpha_ms <= d * DAY_MS) c["h" + w] = (c["h" + w] ?? 0) + 1;
			}
		}
	}
	const out = /* @__PURE__ */ new Map();
	for (const [k, c] of cells) {
		const row = {};
		for (const [w] of windows) {
			const n = c["n" + w] ?? 0;
			const h = c["h" + w] ?? 0;
			row["n" + w] = n;
			row["p" + w] = n ? 100 * h / n : 0;
		}
		out.set(k, row);
	}
	let n = 0;
	let h = 0;
	for (const r of firstObs) {
		const t0 = r.t0 * 1e3;
		const since = alphaSince.get(r.address);
		if (t0 + 30 * DAY_MS > nowMs || since != null && since <= t0) continue;
		n += 1;
		if (since != null && since <= t0 + 30 * DAY_MS) h += 1;
	}
	out.set("own|post", {
		n30: n,
		p30: n ? 100 * h / n : 0
	});
	return out;
}
function listingP(venues, rates) {
	const tags = [...venues].sort().join(",") || "无";
	if ([...venues].some((v) => v.startsWith("binance_perp"))) return {
		p: "已上币安永续",
		basis: tags
	};
	if ([...venues].some((v) => v.startsWith("binance_alpha"))) {
		const order = [
			[CHAIN_ID, "post"],
			["*", "recent"],
			["*", "all"]
		];
		for (const [ch, era] of order) {
			const r = rates.get(`${ch}|${era}`);
			if (r && (r.n30 ?? 0) >= LISTING_MIN_N) {
				const label = ch === CHAIN_ID ? "RH链" : "全链";
				const eraLabel = era === "post" ? "9/8后" : era === "recent" ? "近180天" : "全时段";
				return {
					p: `${Math.round(r.p30 ?? 0)}%`,
					basis: `Alpha→永续30天 ${label}${eraLabel} n=${r.n30} | ${tags}`
				};
			}
		}
		return {
			p: "不确定",
			basis: `Alpha→永续样本不足 | ${tags}`
		};
	}
	const own = rates.get("own|post");
	if (own && (own.n30 ?? 0) >= LISTING_MIN_N) return {
		p: `${Math.round(own.p30 ?? 0)}%`,
		basis: `RH观察池→Alpha30天 n=${own.n30} | ${tags}`
	};
	return {
		p: "不确定",
		basis: `纯链上，自有样本不足 | ${tags}`
	};
}
function targetState(s, f, heat, quality, entry, persist) {
	const liq = s.liq || 0;
	if (liq < INVALID_LIQ) return {
		state: "INVALID",
		why: [`池深 $${Math.round(liq).toLocaleString("en-US")} < $${INVALID_LIQ.toLocaleString("en-US")}`]
	};
	const pc24 = s.pc_h24 || 0;
	const vl = f.vol_liq || 0;
	if (pc24 > OVERHEAT_PC24 && vl > OVERHEAT_VOL_LIQ || pc24 > OVERHEAT_PC24_HARD || entry != null && entry < 25) return {
		state: "OVERHEATED",
		why: [
			`24h ${pc24 >= 0 ? "+" : ""}${pc24.toFixed(0)}%`,
			`Vol/LP ${vl.toFixed(1)}`,
			`Entry ${entry ?? "–"}`
		]
	};
	const H = heat ?? 0;
	const Q = quality ?? 0;
	const E = entry ?? 0;
	const checks = [
		[`Heat≥55(${H.toFixed(0)})`, H >= 55],
		[`Quality≥60(${Q.toFixed(0)})`, Q >= 60],
		[`Entry≥60(${E.toFixed(0)})`, E >= 60],
		[`自有快照≥${READY_MIN_SNAPSHOTS}h(${f.n_hist})`, f.n_hist >= READY_MIN_SNAPSHOTS],
		[`连续3h热(${persist})`, persist >= 3],
		["持币不降", f.holder_g6 == null || f.holder_g6 >= 0],
		["6h买单占优", (f.buy_ratio_h6 ?? 0) >= .5]
	];
	if (checks.every(([, ok]) => ok)) return {
		state: "READY",
		why: checks.map(([k]) => k)
	};
	if (H >= 55 && Q >= 50) return {
		state: "RESEARCH",
		why: ["未满足: " + checks.filter(([, ok]) => !ok).map(([k]) => k).join("、")]
	};
	if ((f.vol_accel_6v18 ?? 0) >= 2 && (f.buy_ratio_h1 ?? 0) >= .5) return {
		state: "ACCELERATING",
		why: [`6h/18h 量比 ${(f.vol_accel_6v18 ?? 0).toFixed(1)}x`]
	};
	return {
		state: "WATCH",
		why: ["量能或买盘还没形成连续加速"]
	};
}
function step(cur, target, now) {
	if (!cur) return {
		state: target,
		since: now,
		pending: null,
		pendingCount: 0
	};
	if (target === cur.state) return {
		...cur,
		pending: null,
		pendingCount: 0
	};
	if (target === "INVALID" || target === "OVERHEATED" || (RANK[target] ?? 0) > (RANK[cur.state] ?? 0) || cur.state === "INVALID" || cur.state === "OVERHEATED") return {
		state: target,
		since: now,
		pending: null,
		pendingCount: 0
	};
	const cnt = cur.pending === target ? cur.pendingCount + 1 : 1;
	if (cnt >= DOWNGRADE_CONFIRM_HOURS) return {
		state: target,
		since: now,
		pending: null,
		pendingCount: 0
	};
	return {
		...cur,
		pending: target,
		pendingCount: cnt
	};
}
function rateRows(rates) {
	const names = {
		"*": "全链",
		[CHAIN_ID]: "RH链"
	};
	const eras = {
		all: "全时段",
		post: "9/8 后",
		recent: "近 180 天"
	};
	const keys = [...rates.keys()].filter((k) => k !== "own|post").sort((a, b) => {
		const [ca, ea] = a.split("|");
		const [cb, eb] = b.split("|");
		if (ca === "*" !== (cb === "*")) return ca === "*" ? -1 : 1;
		return ea.localeCompare(eb);
	});
	const pack = (n, p) => ({
		n: n ?? null,
		p: n != null && n >= LISTING_MIN_N ? p ?? null : null
	});
	const rows = keys.map((k) => {
		const [ch, era] = k.split("|");
		const r = rates.get(k);
		return {
			id: k,
			label: `Alpha→永续 · ${names[ch] ?? ch} · ${eras[era] ?? era}`,
			cells: [
				pack(r.n7, r.p7),
				pack(r.n30, r.p30),
				pack(r.n90, r.p90)
			]
		};
	});
	const own = rates.get("own|post");
	rows.push({
		id: "own",
		label: "RH 观察池 → Alpha（自有样本）",
		cells: [
			{
				n: null,
				p: null
			},
			{
				n: own?.n30 ?? 0,
				p: (own?.n30 ?? 0) >= LISTING_MIN_N ? own?.p30 ?? 0 : null
			},
			{
				n: null,
				p: null
			}
		]
	});
	return rows;
}
/** 从第 0 小时重放到 lastHour（含）。状态机每小时递推，不跳步。 */
function replay(lastHour) {
	const hour = Math.max(0, Math.min(9, lastHour));
	const historySnaps = /* @__PURE__ */ new Map();
	const states = /* @__PURE__ */ new Map();
	const heats = /* @__PURE__ */ new Map();
	const history = {};
	const firstObs = [];
	const alphaSince = /* @__PURE__ */ new Map([["0x" + "e".repeat(40), 178974e7]]);
	let rows = [];
	let rates = [];
	let alerts = [];
	let now = T0;
	for (let h = 0; h <= hour; h++) {
		now = T0 + h * 3600;
		const snaps = CAST.map((c) => snapAt(h, c));
		const obs = snaps.filter(inObs);
		const prevStates = new Map([...states.entries()].map(([a, s]) => [a, s.state]));
		alerts = [];
		const ratesMap = baseRates(now, firstObs, alphaSince);
		rates = rateRows(ratesMap);
		rows = [];
		for (const s of obs) {
			if (!firstObs.some((f) => f.address === s.address)) firstObs.push({
				address: s.address,
				t0: s.ts
			});
			const hist = historySnaps.get(s.address) ?? [];
			const nHist = hist.length + 1;
			const f = features(s, hist, nHist);
			const age = (now - s.pair_created) / 86400;
			const hb = heatBundle(s, f);
			const qb = qualityBundle(s, f, age);
			const eb = entryBundle(s, f);
			const prev = (heats.get(s.address) ?? []).slice(-2).reverse();
			let persist = (hb.score ?? 0) >= 55 ? 1 : 0;
			if (persist) for (const p of prev) if (p >= 55) persist += 1;
			else break;
			const venues = /* @__PURE__ */ new Set();
			if (s.symbol === "ALPHA1") venues.add("binance_alpha");
			if (s.symbol === "RISER" && s.mcap >= 1e6) venues.add("aster_perp?");
			const lp = listingP(venues, ratesMap);
			const tgt = targetState(s, f, hb.score, qb.score, eb.score, persist);
			const next = step(states.get(s.address), tgt.state, now);
			states.set(s.address, next);
			const why = next.state === tgt.state ? tgt.why : [...tgt.why, `目标 ${tgt.state}，降级待确认`];
			const series = heats.get(s.address) ?? [];
			series.push(hb.score ?? 0);
			heats.set(s.address, series);
			const stHist = history[s.symbol] ?? [];
			stHist.push(next.state);
			history[s.symbol] = stHist;
			if ((next.state === "READY" || next.state === "RESEARCH") && prevStates.get(s.address) !== next.state) alerts.push(`${next.state} ${s.symbol}`);
			rows.push({
				address: s.address,
				symbol: s.symbol,
				state: next.state,
				target: tgt.state,
				heat: hb.score,
				quality: qb.score,
				entry: eb.score,
				listingP: lp.p,
				listingBasis: lp.basis,
				venues: [...venues].sort().join(" ") || "无",
				why,
				liq: s.liq,
				vol24: s.vol_h24,
				pc24: s.pc_h24,
				pc6: s.pc_h6,
				price: s.price,
				holders: s.holders,
				volAccel: f.vol_accel_6v18,
				volLiq: f.vol_liq,
				holderG6: f.holder_g6,
				runup: f.runup_from_low,
				nHist,
				heatParts: hb.parts,
				qualityParts: qb.parts,
				entryNotes: eb.notes
			});
		}
		for (const s of snaps) {
			const arr = historySnaps.get(s.address) ?? [];
			arr.push(s);
			historySnaps.set(s.address, arr);
		}
	}
	const order = [
		"READY",
		"RESEARCH",
		"ACCELERATING",
		"WATCH",
		"OVERHEATED",
		"INVALID"
	];
	rows.sort((a, b) => order.indexOf(a.state) - order.indexOf(b.state) || (b.heat ?? 0) - (a.heat ?? 0));
	return {
		hour,
		now,
		rows,
		rates,
		history,
		alerts
	};
}
function finalChecks(frame) {
	const by = Object.fromEntries(frame.rows.map((r) => [r.symbol, r]));
	const risen = by.RISER?.state;
	const alpha = by.ALPHA1;
	return [
		{
			ok: by.PUMP?.state === "OVERHEATED",
			label: "PUMP 为 OVERHEATED（24h 硬顶）"
		},
		{
			ok: risen === "READY" || risen === "RESEARCH",
			label: `RISER 为 ${risen ?? "—"}（READY 或 RESEARCH）`
		},
		{
			ok: !by.DUST,
			label: "DUST 池深不够，不进观察池"
		},
		{
			ok: alpha?.listingP === "35%",
			label: `ALPHA1 的 ListingP 为 ${alpha?.listingP ?? "—"}（全链 30 天 21/60）`
		}
	];
}
var STATE_CLASS = {
	READY: "text-moss",
	RESEARCH: "text-brass",
	ACCELERATING: "text-fg",
	WATCH: "text-muted",
	OVERHEATED: "text-clay",
	INVALID: "text-muted"
};
var DOT = {
	READY: "bg-moss",
	RESEARCH: "bg-brass",
	ACCELERATING: "bg-fg",
	WATCH: "bg-line",
	OVERHEATED: "bg-clay",
	INVALID: "bg-line"
};
function ScoreView() {
	const full = (0, import_react.useMemo)(() => replay(9), []);
	const checks = (0, import_react.useMemo)(() => finalChecks(full), [full]);
	const [hour, setHour] = (0, import_react.useState)(9);
	const [play, setPlay] = (0, import_react.useState)(false);
	const [symbol, setSymbol] = (0, import_react.useState)("RISER");
	const frame = (0, import_react.useMemo)(() => replay(hour), [hour]);
	const row = frame.rows.find((r) => r.symbol === symbol) ?? frame.rows[0];
	(0, import_react.useEffect)(() => {
		if (!play) return;
		const id = window.setInterval(() => {
			setHour((h) => {
				if (h >= 9) {
					setPlay(false);
					return 9;
				}
				return h + 1;
			});
		}, 800);
		return () => window.clearInterval(id);
	}, [play]);
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
		id: "sec-score",
		className: "mx-auto flex max-w-7xl flex-col gap-6 px-4 py-6",
		children: [
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
				className: "max-w-3xl text-sm text-pretty text-muted",
				children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", { children: "四列分开看，没有综合分。Heat 看加速度，Quality 看池子干不干净，ListingP 是频率不是回归，Entry 防止「更可能上、但已经涨完」。 下面用五条成型行情把同一套规则逐小时跑完。数字是现算的，把滑杆拉回第 1 小时，RISER 还进不了 READY。" })
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
				className: "flex flex-col gap-3 rounded-xl border border-line bg-surface p-4",
				children: [
					/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
						className: "flex flex-wrap items-center gap-3",
						children: [
							/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("button", {
								type: "button",
								onClick: () => {
									if (hour >= 9) setHour(0);
									setPlay((p) => !p);
								},
								className: "inline-flex min-h-11 items-center gap-2 rounded-full border border-line px-4 text-sm",
								children: [play ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Pause, { className: "size-4" }) : /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Play, { className: "size-4" }), play ? "暂停" : hour >= 9 ? "从头播放" : "播放"]
							}),
							/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("label", {
								className: "flex min-w-48 flex-1 items-center gap-3 text-sm",
								children: [/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", {
									className: "font-mono text-xs text-muted",
									children: [
										"第 ",
										hour + 1,
										"/10 小时"
									]
								}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("input", {
									type: "range",
									min: 0,
									max: 9,
									value: hour,
									onChange: (e) => {
										setPlay(false);
										setHour(Number(e.target.value));
									},
									className: "w-full accent-brass"
								})]
							}),
							/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
								className: "font-mono text-xs text-muted",
								children: stamp(frame.now * 1e3)
							})
						]
					}),
					/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("p", {
						className: "text-xs text-muted",
						children: [
							"剧本时钟从 ",
							stamp(T0 * 1e3),
							" 起。观察池门槛：池深 ≥ $25k 且 24h 成交 ≥ $20k。升级立刻生效，降级要连续 2 小时，过热和失效立刻生效。"
						]
					}),
					frame.alerts.length ? /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("p", {
						className: "text-sm text-moss",
						children: ["本小时新进入：", frame.alerts.join(" · ")]
					}) : /* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", {
						className: "text-xs text-muted",
						children: "本小时没有新的 READY / RESEARCH。"
					})
				]
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
				className: "grid gap-4 lg:grid-cols-[minmax(0,1fr)_20rem]",
				children: [/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
					className: "max-w-full overflow-x-auto rounded-xl border border-line bg-surface",
					children: [/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("table", {
						className: "w-full min-w-max border-collapse text-sm",
						children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("thead", { children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)("tr", {
							className: "text-left text-xs text-muted",
							children: [
								"状态",
								"币",
								"Heat",
								"Quality",
								"ListingP",
								"Entry",
								"池深",
								"24h",
								"24h%",
								"量比 6/18"
							].map((h) => /* @__PURE__ */ (0, import_jsx_runtime.jsx)("th", {
								className: "px-3 py-2 font-medium",
								children: h
							}, h))
						}) }), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("tbody", { children: frame.rows.map((r) => /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("tr", {
							onClick: () => setSymbol(r.symbol),
							className: "cursor-pointer border-t border-line " + (row?.symbol === r.symbol ? "bg-surface-2" : "hover:bg-bg"),
							children: [
								/* @__PURE__ */ (0, import_jsx_runtime.jsx)("td", {
									className: "px-3 py-2 font-medium " + (STATE_CLASS[r.state] ?? ""),
									children: r.state
								}),
								/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("td", {
									className: "px-3 py-2",
									children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
										className: "font-mono",
										children: r.symbol
									}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Trail, {
										states: full.history[r.symbol] ?? [],
										hour
									})]
								}),
								/* @__PURE__ */ (0, import_jsx_runtime.jsx)("td", {
									className: "px-3 py-2 font-mono tabular-nums",
									children: num(r.heat, 0)
								}),
								/* @__PURE__ */ (0, import_jsx_runtime.jsx)("td", {
									className: "px-3 py-2 font-mono tabular-nums",
									children: num(r.quality, 0)
								}),
								/* @__PURE__ */ (0, import_jsx_runtime.jsx)("td", {
									className: "px-3 py-2 font-mono",
									children: r.listingP
								}),
								/* @__PURE__ */ (0, import_jsx_runtime.jsx)("td", {
									className: "px-3 py-2 font-mono tabular-nums",
									children: num(r.entry, 0)
								}),
								/* @__PURE__ */ (0, import_jsx_runtime.jsx)("td", {
									className: "px-3 py-2 font-mono tabular-nums",
									children: usd(r.liq)
								}),
								/* @__PURE__ */ (0, import_jsx_runtime.jsx)("td", {
									className: "px-3 py-2 font-mono tabular-nums",
									children: usd(r.vol24)
								}),
								/* @__PURE__ */ (0, import_jsx_runtime.jsx)("td", {
									className: "px-3 py-2 font-mono tabular-nums",
									children: pct(r.pc24)
								}),
								/* @__PURE__ */ (0, import_jsx_runtime.jsx)("td", {
									className: "px-3 py-2 font-mono tabular-nums",
									children: r.volAccel == null ? "–" : `${r.volAccel.toFixed(1)}x`
								})
							]
						}, r.address)) })]
					}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", {
						className: "px-3 py-2 text-xs text-muted",
						children: "DUST 池深 $3k，这一小时不在表里。色点是 10 小时的状态，亮的是当前小时。"
					})]
				}), row ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Inspector, { row }) : null]
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("section", {
				className: "rounded-xl border border-line bg-surface p-4",
				children: [
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)("h2", {
						className: "text-sm font-medium",
						children: "ListingP 频率表"
					}),
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", {
						className: "mt-1 text-xs text-pretty text-muted",
						children: "样本不到 20 的格子写「不定」，不给一个看起来很精确的百分比。上 Alpha 还不满窗口的币不进分母。永续比 Alpha 早一天以上的，当撞名剔掉。"
					}),
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
						className: "mt-3 max-w-full overflow-x-auto",
						children: /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("table", {
							className: "w-full min-w-max border-collapse text-sm",
							children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("thead", { children: /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("tr", {
								className: "text-left text-xs text-muted",
								children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("th", {
									className: "py-1 pr-3 font-medium",
									children: "格子"
								}), [
									"7 天",
									"30 天",
									"90 天"
								].map((h) => /* @__PURE__ */ (0, import_jsx_runtime.jsx)("th", {
									className: "px-3 py-1 font-medium",
									children: h
								}, h))]
							}) }), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("tbody", { children: frame.rates.map((r) => /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("tr", {
								className: "border-t border-line",
								children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("td", {
									className: "py-2 pr-3",
									children: r.label
								}), r.cells.map((c, i) => /* @__PURE__ */ (0, import_jsx_runtime.jsx)("td", {
									className: "px-3 py-2 font-mono tabular-nums",
									children: c.n == null ? "–" : c.p == null ? `${c.n} 不定` : `${c.n} · ${c.p.toFixed(0)}%`
								}, i))]
							}, r.id)) })]
						})
					})
				]
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("section", {
				className: "rounded-xl border border-line p-4",
				children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("h2", {
					className: "text-sm font-medium",
					children: "跑满 10 小时后的自检"
				}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("ul", {
					className: "mt-3 grid gap-2 sm:grid-cols-2",
					children: checks.map((c) => /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("li", {
						className: "flex items-start gap-2 text-sm",
						children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { className: "mt-1 size-2 shrink-0 rounded-full " + (c.ok ? "bg-moss" : "bg-clay") }), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
							className: c.ok ? "text-fg" : "text-clay",
							children: c.label
						})]
					}, c.label))
				})]
			})
		]
	});
}
function Trail({ states, hour }) {
	return /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
		className: "mt-1 flex gap-0.5",
		"aria-hidden": true,
		children: Array.from({ length: 10 }, (_, i) => /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { className: "h-1.5 w-2 rounded-sm " + (i < states.length ? DOT[states[i]] ?? "bg-line" : "bg-line") + (i === hour ? " ring-1 ring-fg" : "") }, i))
	});
}
function Inspector({ row }) {
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("aside", {
		className: "rounded-xl border border-line bg-surface p-4",
		children: [
			/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
				className: "flex items-baseline justify-between gap-2",
				children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("h2", {
					className: "font-mono text-lg",
					children: row.symbol
				}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
					className: "text-sm font-medium " + (STATE_CLASS[row.state] ?? ""),
					children: row.state
				})]
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", {
				className: "mt-1 text-xs text-pretty text-muted",
				children: row.why.join(" · ")
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("p", {
				className: "mt-2 text-xs text-pretty text-muted",
				children: [
					"上所 ",
					row.venues,
					" · 自有快照 ",
					row.nHist,
					"h · 持币 ",
					row.holders?.toLocaleString("en-US") ?? "–"
				]
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", {
				className: "mt-1 text-xs text-pretty text-brass",
				children: row.listingBasis
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)(Block, {
				title: "Heat",
				score: row.heat,
				parts: row.heatParts
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)(Block, {
				title: "Quality",
				score: row.quality,
				parts: row.qualityParts
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
				className: "mt-4",
				children: [/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
					className: "flex items-baseline justify-between",
					children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("h3", {
						className: "text-xs text-muted",
						children: "Entry"
					}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
						className: "font-mono tabular-nums",
						children: num(row.entry, 1)
					})]
				}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("ul", {
					className: "mt-2 space-y-1 text-xs text-muted",
					children: row.entryNotes.map((n) => /* @__PURE__ */ (0, import_jsx_runtime.jsx)("li", { children: n }, n))
				})]
			})
		]
	});
}
function Block({ title, score, parts }) {
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
		className: "mt-4",
		children: [/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
			className: "flex items-baseline justify-between",
			children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("h3", {
				className: "text-xs text-muted",
				children: title
			}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
				className: "font-mono tabular-nums",
				children: num(score, 1)
			})]
		}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("ul", {
			className: "mt-2 flex flex-col gap-2",
			children: parts.map((p) => /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("li", { children: [/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
				className: "flex items-baseline justify-between gap-2 text-xs",
				children: [/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", { children: [p.label, /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", {
					className: "text-muted",
					children: [" · ", p.weight]
				})] }), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
					className: "font-mono text-muted",
					children: p.raw
				})]
			}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
				className: "mt-1 h-1.5 overflow-hidden rounded-full bg-bg",
				children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
					className: "h-full rounded-full bg-brass",
					style: { width: `${(p.mapped ?? 0) * 100}%` }
				})
			})] }, p.label))
		})]
	});
}
var TABS = [
	{
		id: "ladder",
		label: "上币阶梯",
		hint: "走到了哪一级"
	},
	{
		id: "score",
		label: "四列",
		hint: "状态机逐小时"
	},
	{
		id: "method",
		label: "口径",
		hint: "规则写在明处"
	}
];
function tabFromHash(hash) {
	const h = hash.replace("#", "");
	if (h === "score" || h === "sec-score") return "score";
	if (h === "method" || h === "sec-method") return "method";
	if (h === "ladder" || h === "sec-ladder") return "ladder";
	return null;
}
function Desk() {
	const [tab, setTab] = (0, import_react.useState)("ladder");
	(0, import_react.useEffect)(() => {
		const next = tabFromHash(window.location.hash);
		if (next) setTab(next);
		const onHash = () => {
			const t = tabFromHash(window.location.hash);
			if (t) setTab(t);
		};
		window.addEventListener("hashchange", onHash);
		return () => window.removeEventListener("hashchange", onHash);
	}, []);
	function go(id) {
		setTab(id);
		const hash = id === "ladder" ? "#sec-ladder" : id === "score" ? "#sec-score" : "#sec-method";
		window.history.replaceState(null, "", hash);
	}
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
		className: "min-h-screen bg-bg text-fg",
		children: [
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)("header", {
				className: "border-b border-line",
				children: /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
					className: "mx-auto flex max-w-7xl flex-col gap-4 px-4 py-5 md:flex-row md:items-end md:justify-between",
					children: [/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { children: [
						/* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", {
							className: "font-mono text-xs tracking-widest text-brass",
							children: "ROBINHOOD CHAIN"
						}),
						/* @__PURE__ */ (0, import_jsx_runtime.jsx)("h1", {
							className: "mt-1 text-3xl font-medium tracking-tight text-balance",
							children: "阶梯"
						}),
						/* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", {
							className: "mt-1 max-w-xl text-sm text-pretty text-muted",
							children: "链上谁都能发。能在 Robinhood App 里买到的，和能走到币安的，是两条分开数的路。"
						})
					] }), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("nav", {
						className: "flex flex-wrap gap-2",
						"aria-label": "视图",
						children: TABS.map((t) => /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("button", {
							type: "button",
							onClick: () => go(t.id),
							className: "min-h-11 rounded-full border px-4 text-left " + (tab === t.id ? "border-brass text-fg" : "border-line text-muted"),
							children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
								className: "block text-sm",
								children: t.label
							}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
								className: "block text-xs text-muted",
								children: t.hint
							})]
						}, t.id))
					})]
				})
			}),
			tab === "ladder" ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)(LadderView, {}) : null,
			tab === "score" ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)(ScoreView, {}) : null,
			tab === "method" ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)(MethodView, {}) : null
		]
	});
}
function Home() {
	return /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Desk, {});
}
//#endregion
export { Home as component };
