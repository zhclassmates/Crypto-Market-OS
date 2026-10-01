const ROWS = [
  ["Heat", "6h/18h 量比 35、笔数比 20、买家加速 15、6h 涨幅 15、持币 6h 增长 15", "加速度用非重叠窗：(近 6h 小时均量) / (再往前 18h 小时均量)。DexScreener 的 h6、h24 第一小时就能算。"],
  ["Quality", "池深 25、Vol/LP 减分 20、独立买家/买单笔数 20、持币数 15、Top10 减分 10、币龄 10", "独立买家除以买单笔数越低，越像少数地址来回刷。Vol/LP 高是减分，不是热闹。"],
  ["Entry", "100 减去：距 7 日低点的倍数、24h 涨幅、Vol/LP、1h 卖压、72h 高点腰斩", "用来挡「路径更像能上所，但价格已经走完」。"],
  ["ListingP", "频率表，不是回归", "已上币安永续就直接写。已在 Alpha，按格子查 30 天内上永续的比例。纯链上要等自己的观察池满 30 天。格子样本 < 20 写「不确定」。"],
];

export function MethodView() {
  return (
    <div id="sec-method" className="mx-auto flex max-w-3xl flex-col gap-6 px-4 py-6">
      <p className="text-sm text-pretty text-muted">
        阶梯回答「走到了哪一级」。四列回答「这一小时的量和筹码像不像还早、还干净」。两套数字不要加成一个总分。
      </p>
      <section className="flex flex-col gap-3">
        {ROWS.map(([name, mix, note]) => (
          <article key={name} className="rounded-xl border border-line bg-surface p-4">
            <h2 className="text-sm font-medium">{name}</h2>
            <p className="mt-1 text-sm text-pretty">{mix}</p>
            <p className="mt-2 text-xs text-pretty text-muted">{note}</p>
          </article>
        ))}
      </section>
      <section className="rounded-xl border border-line p-4">
        <h2 className="text-sm font-medium">READY 要七条一起满足</h2>
        <ol className="mt-2 list-decimal space-y-1 pl-5 text-sm">
          <li>Heat ≥ 55</li>
          <li>Quality ≥ 60</li>
          <li>Entry ≥ 60</li>
          <li>自己的小时快照至少 6 根</li>
          <li>连续 3 小时 Heat 达标</li>
          <li>持币地址 6 小时不下降（没有这项数据时不卡）</li>
          <li>6 小时买单笔数不少于卖单</li>
        </ol>
        <p className="mt-3 text-xs text-pretty text-muted">
          缺数据的分项跳过，权重按剩下的重新归一，所以第一小时也有分，历史攒够了才准进 READY。升级马上生效。往下降要连续 2 小时还是一样，避免来回跳。池子浅于 $10k 直接 INVALID。24h 涨幅超过 500%，或者超过 300% 且 Vol/LP 大于 10，或者 Entry 低于 25，立刻 OVERHEATED。
        </p>
      </section>
      <section className="rounded-xl border border-line p-4">
        <h2 className="text-sm font-medium">ListingP 省掉的那块脏活</h2>
        <p className="mt-2 text-sm text-pretty text-muted">
          不用对公告。币安 Alpha 列表自带 listingTime、chainId 和合约地址；币安永续的 exchangeInfo 自带 onboardDate；现货没有上线日，用第一根日 K 的开盘时间。全链 Alpha 币 7 / 30 / 90 天内有没有上永续，一次请求就能成表。
        </p>
        <p className="mt-2 text-sm text-pretty text-muted">
          两个坑已经处理：删失 —— 上 Alpha 不满 30 天的不进 30 天分母，不能当成没上。撞名 —— 永续比 Alpha 早一天以上，当作不是同一个币，或早就上过，剔出分母。格子先看 RH 链、2026-09-08 币安 Alpha 2.0 接入之后，再看全链近 180 天，最后才是全链全时段。
        </p>
      </section>
      <section className="rounded-xl border border-line p-4">
        <h2 className="text-sm font-medium">这页现在做不到的</h2>
        <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-pretty text-muted">
          <li>点「四列」会当场请求 GeckoTerminal、DexScreener 和币安 Alpha。某一步 429 或被地区拦住，日志里写失败原因，不用假币顶上。</li>
          <li>自有小时库存在这台浏览器里。不满 6 次不同小时的快照，规则不允许进 READY。</li>
          <li>币安永续的 onboardDate 这一轮经常被地区拦，所以已在 Alpha 的只写「已在 Alpha」，不编一个百分比。</li>
          <li>Aster、Hyperliquid、韩所、Robinhood App 没有链上合约可对。手递手洗量还没做，换手超过 20 倍的在阶梯页单独标出。</li>
        </ul>
      </section>
    </div>
  );
}
