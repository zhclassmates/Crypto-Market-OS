# 阶梯 — Chain Intelligence Dashboard

**Project:** "阶梯" (Ladder) — multi-chain crypto research & analysis dashboard.  
**Stack:** TanStack Start (React 19, Router, Query, Table), Tailwind v4, Radix UI, PGLite, Better Auth (pre-wired, opt-in), GMGN API for market data.

---

## Key Commands

| Command | Purpose |
|---------|---------|
| `npm run dev` | Start dev server on `0.0.0.0:8080` (via `scripts/with-app-env.mjs`) |
| `npm run build` | Production build + run DB migrations |
| `npm run typecheck` | `tsc --noEmit` |
| `npm run lint` | `eslint .` |
| `npm run format` | `prettier --write .` |
| `npm run test` | Unit tests (Node + Python unittest for radar engine) |
| `npm run preview:restart` | Serve built output on `127.0.0.1:8081` for smoke testing |

**Run order for verification:** `typecheck` → `lint` → `test` → `build` → `preview:restart` + browser smoke.

---

## Architecture Notes

- **App entry:** `src/routes/index.tsx` → `Desk` component (tabbed dashboard)
- **Tabs (13):** market, early, discovery, access, alerts, score, streak, radar, method, watch, ladder, reasoning, watch
- **Data layer:** `src/lib/rh/` — unified market engine (GMGN API), watchlist, ladder, quality scoring, discovery, radar, kline
- **Auth:** Pre-wired in `src/lib/auth/` but **OFF by default** (§0.5 in platform AGENTS.md). Enable only for per-user data / cross-device save.
- **DB:** PGLite (local, file-based) via `src/lib/db.ts`. Migrations in `scripts/migration-plan.mjs`.
- **Background workers:** Python scripts (`rh_v2/market_run.py`, `scripts/unified-market-refresh.py`) started by `startup.sh` — collect market data every 5 min.
- **Multiplayer/P2P:** `src/lib/multiplayer/` — optional realtime sync.

---

## Critical Files / Directories

```
src/
  routes/           # TanStack Start file routes (only API route: /api/health/market)
  components/       # Dashboard views (Desk + 13 tab views)
  lib/
    rh/             # Core market intelligence engine (unified query, cache, display, quality, ladder, radar, discovery, access, alerts, watchlist)
    auth/           # Better Auth setup (provider, gates, middleware) — opt-in
    app-data/       # Google/Microsoft/Notion connector framework (opt-in)
    multiplayer/    # P2P sync (opt-in)
    env.server.ts   # Server-only env validation
scripts/
  with-app-env.mjs  # Injects VITE_AUTH_ENABLED into Vite — ALWAYS use npm scripts
  unified-market-refresh.py  # Market data collector (loop mode)
  browser-smoke.mjs # Playwright QA (desktop + mobile) — MUST pass before done
  preview.mjs       # Manages preview server on :8081
startup.sh          # Revive contract — starts workers + dev server (idempotent)
```

---

## Gotchas & Conventions

- **Never run `vite` directly** — always `npm run dev` / `npm run build` (wraps env).
- **Port 8080** is mandatory for preview proxy; dev server binds `0.0.0.0:8080`.
- **Auth routes** (`login.tsx`, `api/auth/$.ts`) only if §0.5 says accounts. Never create `auth/popup.tsx`.
- **No `.env` file** — platform injects `DATABASE_URL` + auth creds on deploy; only `VITE_*` reaches browser.
- **Python workers** write logs to `.grok/market-revive.log` and `.grok/unified-refresh.log`.
- **Test command** runs both Node (`--experimental-strip-types`) and Python (`unittest`) — both must pass.
- **Browser QA:** Run `node scripts/browser-smoke.mjs` — inspect BOTH desktop & mobile screenshots in `/workspace/screenshots/`; console must be clean.
- **Deploy target:** Vercel — avoid runtime fs writes, server-only Node APIs at import time, hard-coded hosts/ports/secrets.

---

## Common Tasks

- **Add a new tab/view:** Create component in `src/components/*-view.tsx`, add to `TABS` + `PRESENTATION` in `Desk`, render in `main` branch.
- **Extend market engine:** Add types to `src/lib/rh/types.ts`, logic in `src/lib/rh/*.ts`, tests in `*.test.ts`.
- **Modify auth flow:** Edit `src/lib/auth/` — but only if user explicitly asks for accounts/sign-in.
- **Run single test:** `node --experimental-strip-types --test src/lib/rh/watchlist.test.ts`
- **Check auth invariant:** `npm run check:auth` (ensures no `authMiddleware` in auth-off code paths).

---

## References

- Platform contract (sandbox, preview, skills): `AGENTS.md` (the 350-line file you're reading)
- Scaffold templates: `.grok/references/scaffold.md`
- Deploy constraints: `.grok/references/deploy-target.md`
- Browser QA: `.grok/references/browser-qa.md`
- Hibernate/revive: `.grok/references/hibernate-revive.md`