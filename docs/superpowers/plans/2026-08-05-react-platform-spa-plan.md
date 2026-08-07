# React Platform SPA Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the React SPA (`web/`) described in `docs/superpowers/specs/2026-08-05-react-platform-scout-hq-design.md` — a dark, bold-accent platform with Dashboard, Scout HQ (chat + mission board), Leads, Runs, and Agents pages that consumes the completed `/api/*` backend.

**Architecture:** A new `web/` folder holds a Vite + React 18 + TypeScript SPA using React Router for pages and TanStack Query for server state. Plain CSS with CSS-variable design tokens (no UI framework). Dev runs Vite with a proxy to the running backend (`localhost:8000`); prod is a separate `web` nginx container that serves the built assets and proxies `/api` → `app:8000`. SSE chat is consumed via `fetch` + stream reader (backend emits `start` → `delta*` → `done`; tool-activity cards render from persisted `role="tool"` messages refetched after `done`).

**Tech Stack:** React 18.3, Vite 5, TypeScript 5.6, React Router 6.28, TanStack Query 5.59, Vitest 2 + Testing Library (jsdom), plain CSS. Node 22.14 / npm 10.9 are installed on the host.

## Global Constraints

- All API calls hit `/api/*` on the same origin (Vite proxy in dev, nginx proxy in prod). Never hardcode `localhost:8000` in app code.
- Python is 3.9 on host — this plan touches **no Python files** except `docker-compose.yml` (add `web` service) and docs. Do not modify `api/`, `crm/`, `agents/`, `db/`, `migrations/`, `tests/`.
- The backend is already running/verified; SSE chat emits `event: start`, `event: delta` (`{"delta","index"}`), `event: done` (`{"thread_id","assistant","tool_calls"}`), `event: error` (`{"detail"}`). Tool activity is NOT streamed live — render tool cards from refetched messages after `done`.
- Design tokens (verbatim from spec §7): bg `#0B0F17`, surface `#131926`, border `#1E2735`, text `#E6EDF7`, muted `#8B98AD`; accent gradient `#7C3AED → #D946EF`; secondary cyan `#22D3EE`; success `#22C55E`, warning `#F59E0B`, danger `#EF4444`.
- Layout (spec §7): fixed left sidebar (Dashboard, Scout HQ, Leads, Runs, Agents) + topbar (page title, live "Scout active" badge, API status dot).
- Pages (spec §7): `/` Dashboard, `/scout-hq`, `/leads`, `/leads/:id`, `/runs`, `/runs/:id`, `/agents`, `/agents/:name`.
- Scout HQ layout (spec §7): split view — left mission board (missions list + start/finish Scout), right persisted chat with SSE streaming + tool-activity cards.
- Every task ends with a commit. Tests are Vitest (frontend). `npm run build` must pass after every task.
- `web/Dockerfile` builds with `npm ci` + `npm run build`, serves with `nginx:alpine`, proxies `/api` → `app:8000` with `proxy_buffering off` (required for SSE).

---

### Task 1: Scaffold `web/` — Vite + React + TS + tooling

**Files:**
- Create: `web/package.json`
- Create: `web/vite.config.ts`
- Create: `web/tsconfig.json`
- Create: `web/tsconfig.node.json`
- Create: `web/index.html`
- Create: `web/src/main.tsx`
- Create: `web/src/App.tsx`
- Create: `web/src/test/setup.ts`
- Create: `web/.gitignore`

**Interfaces:**
- Produces: a runnable Vite app at `web/` with scripts `dev`, `build`, `test`. `src/App.tsx` renders a placeholder heading that later tasks replace with the router shell.

- [ ] **Step 1: Create the scaffold files**

`web/package.json`:

```json
{
  "name": "nextlevel-platform-web",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc --noEmit && vite build",
    "preview": "vite preview",
    "test": "vitest run"
  },
  "dependencies": {
    "@tanstack/react-query": "^5.59.0",
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "react-router-dom": "^6.28.0"
  },
  "devDependencies": {
    "@testing-library/jest-dom": "^6.5.0",
    "@testing-library/react": "^16.0.1",
    "@testing-library/user-event": "^14.5.2",
    "@types/react": "^18.3.10",
    "@types/react-dom": "^18.3.0",
    "@vitejs/plugin-react": "^4.3.2",
    "jsdom": "^25.0.1",
    "typescript": "~5.6.3",
    "vite": "^5.4.9",
    "vitest": "^2.1.2"
  }
}
```

`web/vite.config.ts`:

```ts
/// <reference types="vitest" />
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": "http://localhost:8000",
      "/health": "http://localhost:8000",
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
  },
});
```

`web/tsconfig.json`:

```json
{
  "compilerOptions": {
    "target": "ES2020",
    "useDefineForClassFields": true,
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true
  },
  "include": ["src"]
}
```

`web/tsconfig.node.json`:

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["ES2023"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowSyntheticDefaultImports": true,
    "strict": true,
    "noEmit": true
  },
  "include": ["vite.config.ts"]
}
```

`web/index.html`:

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>NextLevel Marketing Dept</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

`web/src/main.tsx`:

```tsx
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import App from "./App";

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } },
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </StrictMode>,
);
```

`web/src/App.tsx`:

```tsx
export default function App() {
  return <h1>NextLevel Platform</h1>;
}
```

`web/src/test/setup.ts`:

```ts
import "@testing-library/jest-dom/vitest";
```

`web/.gitignore`:

```
node_modules
dist
```

- [ ] **Step 2: Install dependencies**

Run (workdir `web`): `npm install`
Expected: `npm install` completes; `web/package-lock.json` created.

- [ ] **Step 3: Verify build passes**

Run (workdir `web`): `npm run build`
Expected: TypeScript check passes and Vite emits `dist/` with no errors.

- [ ] **Step 4: Verify dev server proxies the API**

Run (workdir `web`): `npm run dev` (background), then `Invoke-RestMethod http://localhost:5173/api/health`
Expected: `{"status":"ok"}` — proves the `/api` proxy to `:8000` works. Stop the dev server.

- [ ] **Step 5: Commit**

```bash
git add web
git commit -m "feat: scaffold React SPA (Vite + React + TS + tooling)"
```

---

### Task 2: Design tokens, API client, types, SSE parser

**Files:**
- Create: `web/src/styles/tokens.css`
- Create: `web/src/styles/global.css`
- Create: `web/src/api/types.ts`
- Create: `web/src/api/client.ts`
- Create: `web/src/api/sse.ts`
- Test: `web/src/api/sse.test.ts`
- Test: `web/src/api/client.test.ts`

**Interfaces:**
- Consumes: nothing.
- Produces (later tasks import these):
  - `src/api/client.ts`: `apiGet<T>(path)`, `apiSend<T>(path, method, body)`, `ApiError(status, message)`.
  - `src/api/types.ts`: interfaces `Lead`, `LeadEvent`, `LeadDetail`, `AgentRun`, `PipelineRun`, `ToolInfo`, `AgentProfile`, `Stats`, `ScoutStatus`, `ScoutThread`, `ScoutMessage`, `DiscoveryStartOut`.
  - `src/api/sse.ts`: `SseFrame { event: string; data: string }`, `parseSseFrames(buffer: string): SseFrame[]`, `takeFrames(buffer: string): { frames: SseFrame[]; rest: string }`.
  - `web/src/styles/tokens.css`: CSS variables `--bg`, `--surface`, `--border`, `--text`, `--muted`, `--accent`, `--accent-2`, `--cyan`, `--success`, `--warning`, `--danger`, `--radius`, `--sidebar-w`.

- [ ] **Step 1: Write the failing tests**

`web/src/api/sse.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { parseSseFrames, takeFrames } from "./sse";

describe("parseSseFrames", () => {
  it("parses event + data frames", () => {
    const raw = "event: start\ndata: {}\n\nevent: delta\ndata: {\"delta\":\"hi\"}\n\n";
    const frames = parseSseFrames(raw);
    expect(frames).toEqual([
      { event: "start", data: "{}" },
      { event: "delta", data: "{\"delta\":\"hi\"}" },
    ]);
  });
});

describe("takeFrames", () => {
  it("returns complete frames and keeps the partial tail", () => {
    const { frames, rest } = takeFrames("event: start\ndata: {}\n\nevent: delta\ndata: {\"d");
    expect(frames).toEqual([{ event: "start", data: "{}" }]);
    expect(rest).toBe("event: delta\ndata: {\"d");
  });
});
```

`web/src/api/client.test.ts`:

```ts
import { afterEach, describe, expect, it, vi } from "vitest";
import { apiGet, ApiError } from "./client";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("apiGet", () => {
  it("returns parsed json on 200", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ status: "ok" }),
    }));
    const out = await apiGet<{ status: string }>("/api/health");
    expect(out.status).toBe("ok");
  });

  it("throws ApiError with detail on non-ok", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: false,
      status: 404,
      json: async () => ({ detail: "not found" }),
      statusText: "Not Found",
    }));
    await expect(apiGet("/api/leads/x")).rejects.toMatchObject({
      status: 404,
      message: "not found",
    });
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run (workdir `web`): `npm test`
Expected: FAIL — `Cannot find module './sse'` / `'./client'`.

- [ ] **Step 3: Create the files**

`web/src/styles/tokens.css`:

```css
:root {
  --bg: #0b0f17;
  --surface: #131926;
  --border: #1e2735;
  --text: #e6edf7;
  --muted: #8b98ad;
  --accent: #7c3aed;
  --accent-2: #d946ef;
  --cyan: #22d3ee;
  --success: #22c55e;
  --warning: #f59e0b;
  --danger: #ef4444;
  --radius: 8px;
  --sidebar-w: 220px;
  --gradient: linear-gradient(135deg, #7c3aed, #d946ef);
}
```

`web/src/styles/global.css`:

```css
@import "./tokens.css";

* {
  box-sizing: border-box;
}

html,
body,
#root {
  margin: 0;
  height: 100%;
}

body {
  background: var(--bg);
  color: var(--text);
  font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
  font-size: 15px;
  line-height: 1.5;
}

a {
  color: var(--cyan);
  text-decoration: none;
}

a:hover {
  text-decoration: underline;
}

code,
pre {
  font-family: ui-monospace, Consolas, monospace;
}

.muted {
  color: var(--muted);
}
```

`web/src/api/types.ts`:

```ts
export interface Lead {
  id: string;
  name: string | null;
  url: string | null;
  country: string | null;
  industry: string | null;
  business_type: string | null;
  email: string | null;
  phone: string | null;
  seo_score: number | null;
  lead_score: number | null;
  status: string | null;
  status_notes: string | null;
  source: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface LeadEvent {
  id: string;
  lead_id: string;
  agent_run_id: string | null;
  event_type: string;
  payload: Record<string, unknown> | null;
  created_at: string | null;
}

export interface LeadDetail extends Lead {
  events: LeadEvent[];
}

export interface AgentRun {
  id: string;
  pipeline_run_id: string;
  agent_name: string;
  model: string | null;
  status: string | null;
  input_summary: string | null;
  output_summary: string | null;
  output_json: Record<string, unknown> | null;
  apis_consumed: Array<Record<string, unknown>> | null;
  records_processed: number | null;
  error_message: string | null;
  started_at: string | null;
  finished_at: string | null;
}

export interface PipelineRun {
  id: string;
  trigger: string | null;
  seed_query: string | null;
  status: string | null;
  started_at: string | null;
  finished_at: string | null;
  meta: Record<string, unknown> | null;
  agent_run_count?: number;
}

export interface ToolInfo {
  id: string;
  label: string;
  agents: string[];
}

export interface AgentProfile {
  agent_name: string;
  display_name: string;
  mission_prompt: string;
  enabled_tools: string[];
  model: string | null;
  default_seed_query: string | null;
  updated_at: string | null;
  available_tools: ToolInfo[];
}

export interface Stats {
  leads_total: number;
  leads_by_status: Record<string, number>;
  leads_avg_score: number;
  runs_today: number;
  run_success_rate: number;
  recent_runs: Array<{
    id: string;
    trigger: string | null;
    seed_query: string | null;
    status: string | null;
    started_at: string | null;
  }>;
  scout_active: boolean;
  scout_last_seed: string | null;
}

export interface ScoutStatus {
  scout_active: boolean;
  scout_last_seed: string | null;
  latest_missions: PipelineRun[];
}

export interface ScoutThread {
  id: string;
  title: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface ScoutMessage {
  id: string;
  thread_id: string;
  role: "user" | "assistant" | "tool";
  content: string | null;
  tool_name: string | null;
  tool_args: Record<string, unknown> | null;
  tool_result: { result?: unknown; error?: string | null } | Record<string, unknown> | null;
  created_at: string | null;
}

export interface DiscoveryStartOut {
  pipeline_run_id: string;
  status: string;
  seed_query: string;
  note?: string | null;
}

export interface DiscoveryFinishOut {
  pipeline_run_id: string;
  status: string;
}
```

`web/src/api/client.ts`:

```ts
const BASE = "";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function errorMessage(res: Response): Promise<string> {
  try {
    const data = await res.json();
    if (typeof data.detail === "string") return data.detail;
    return JSON.stringify(data);
  } catch {
    return res.statusText || `HTTP ${res.status}`;
  }
}

export async function apiGet<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { Accept: "application/json" },
  });
  if (!res.ok) throw new ApiError(res.status, await errorMessage(res));
  return (await res.json()) as T;
}

export async function apiSend<T>(
  path: string,
  method: "POST" | "PATCH",
  body?: unknown,
): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) throw new ApiError(res.status, await errorMessage(res));
  return (await res.json()) as T;
}
```

`web/src/api/sse.ts`:

```ts
export interface SseFrame {
  event: string;
  data: string;
}

export function parseSseFrames(buffer: string): SseFrame[] {
  const frames: SseFrame[] = [];
  for (const block of buffer.split("\n\n")) {
    const trimmed = block.trim();
    if (!trimmed) continue;
    let event = "";
    let data = "";
    for (const line of trimmed.split("\n")) {
      if (line.startsWith("event:")) event = line.slice("event:".length).trim();
      else if (line.startsWith("data:")) data = line.slice("data:".length).trim();
    }
    frames.push({ event, data });
  }
  return frames;
}

export function takeFrames(buffer: string): { frames: SseFrame[]; rest: string } {
  const sep = buffer.lastIndexOf("\n\n");
  if (sep === -1) return { frames: [], rest: buffer };
  return {
    frames: parseSseFrames(buffer.slice(0, sep)),
    rest: buffer.slice(sep + 2),
  };
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run (workdir `web`): `npm test`
Expected: 3 tests PASSED (sse: 2, client: 2).

- [ ] **Step 5: Verify build passes**

Run (workdir `web`): `npm run build`
Expected: no TS errors; `dist/` emitted.

- [ ] **Step 6: Commit**

```bash
git add web
git commit -m "feat: design tokens, typed API client, SSE parser"
```

---

### Task 3: Layout shell, routing, shared components

**Files:**
- Create: `web/src/components/Layout.tsx`
- Create: `web/src/components/Sidebar.tsx`
- Create: `web/src/components/Topbar.tsx`
- Create: `web/src/components/StatusBadge.tsx`
- Create: `web/src/components/KpiCard.tsx`
- Create: `web/src/components/ScoutActiveBadge.tsx`
- Create: `web/src/components/StatusDot.tsx`
- Create: `web/src/styles/layout.css`
- Create: `web/src/styles/components.css`
- Create: `web/src/pages/Dashboard.tsx` (placeholder)
- Create: `web/src/pages/ScoutHQ.tsx` (placeholder)
- Create: `web/src/pages/Leads.tsx` (placeholder)
- Create: `web/src/pages/LeadsDetail.tsx` (placeholder)
- Create: `web/src/pages/Runs.tsx` (placeholder)
- Create: `web/src/pages/RunsDetail.tsx` (placeholder)
- Create: `web/src/pages/Agents.tsx` (placeholder)
- Create: `web/src/pages/AgentsDetail.tsx` (placeholder)
- Modify: `web/src/App.tsx`
- Test: `web/src/components/StatusBadge.test.tsx`
- Test: `web/src/components/KpiCard.test.tsx`

**Interfaces:**
- Consumes: `web/src/styles/tokens.css` (CSS vars), `web/src/api/types.ts` (`Stats`), `web/src/api/client.ts` (`apiGet`).
- Produces:
  - `Layout` — renders `<Sidebar/><div class="main"><Topbar/><main>{children}</main></div>`; wraps all routed pages.
  - `Sidebar` — nav links: `/` Dashboard, `/scout-hq` Scout HQ, `/leads` Leads, `/runs` Runs, `/agents` Agents. `NavLink` active class `active`.
  - `Topbar` — props `{ title: string; scoutActive: boolean; statusOk: boolean }`; shows title, `<ScoutActiveBadge active/>`, `<StatusDot ok/>`.
  - `StatusBadge` — props `{ status: string | null }` → `<span className={"badge " + (status ?? "")}>{status ?? "—"}</span>`.
  - `KpiCard` — props `{ label: string; value: string | number; accent?: "violet" | "cyan" }`.
  - `ScoutActiveBadge` — props `{ active: boolean }` → "Scout active" / "Scout idle".
  - `StatusDot` — props `{ ok: boolean }` → green/red dot.
  - `App` — `BrowserRouter` + `Routes`; `Layout` wraps every route; lazy placeholder pages.

- [ ] **Step 1: Write the failing tests**

`web/src/components/StatusBadge.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { StatusBadge } from "./StatusBadge";

describe("StatusBadge", () => {
  it("applies the status value as class", () => {
    render(<StatusBadge status="success" />);
    expect(screen.getByText("success")).toHaveClass("badge success");
  });

  it("renders an em dash for null status", () => {
    render(<StatusBadge status={null} />);
    expect(screen.getByText("—")).toBeInTheDocument();
  });
});
```

`web/src/components/KpiCard.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { KpiCard } from "./KpiCard";

describe("KpiCard", () => {
  it("renders label and value", () => {
    render(<KpiCard label="Leads" value={42} />);
    expect(screen.getByText("Leads")).toBeInTheDocument();
    expect(screen.getByText("42")).toBeInTheDocument();
  });

  it("uses the accent class", () => {
    render(<KpiCard label="Rate" value="5%" accent="cyan" />);
    expect(screen.getByText("Rate").parentElement).toHaveClass("kpi-card kpi-cyan");
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run (workdir `web`): `npm test`
Expected: FAIL — `Cannot find module './StatusBadge'` etc.

- [ ] **Step 3: Create the files**

`web/src/styles/layout.css`:

```css
.app-shell {
  display: grid;
  grid-template-columns: var(--sidebar-w) 1fr;
  min-height: 100%;
}

.sidebar {
  background: var(--surface);
  border-right: 1px solid var(--border);
  padding: 1.25rem 0.75rem;
  position: sticky;
  top: 0;
  height: 100vh;
}

.brand {
  font-size: 1.05rem;
  font-weight: 700;
  background: var(--gradient);
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
  padding: 0 0.5rem 1.25rem;
}

.sidebar nav {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.sidebar a {
  color: var(--muted);
  padding: 0.5rem 0.75rem;
  border-radius: var(--radius);
  font-weight: 500;
}

.sidebar a:hover {
  color: var(--text);
  text-decoration: none;
  background: rgba(255, 255, 255, 0.04);
}

.sidebar a.active {
  color: var(--text);
  background: linear-gradient(135deg, rgba(124, 58, 237, 0.25), rgba(217, 70, 239, 0.25));
  box-shadow: inset 0 0 0 1px rgba(124, 58, 237, 0.4);
}

.main {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.9rem 1.5rem;
  border-bottom: 1px solid var(--border);
  background: rgba(19, 25, 38, 0.7);
  backdrop-filter: blur(6px);
  position: sticky;
  top: 0;
  z-index: 10;
}

.topbar h1 {
  font-size: 1.1rem;
  margin: 0;
}

.topbar-right {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.page {
  padding: 1.5rem;
  max-width: 1200px;
  width: 100%;
}
```

`web/src/styles/components.css`:

```css
.badge {
  display: inline-block;
  padding: 0.15rem 0.5rem;
  border-radius: 999px;
  font-size: 0.75rem;
  font-weight: 600;
  background: rgba(255, 255, 255, 0.06);
  color: var(--text);
}

.badge.success { background: rgba(34, 197, 94, 0.18); color: var(--success); }
.badge.failed { background: rgba(239, 68, 68, 0.18); color: var(--danger); }
.badge.running { background: rgba(34, 211, 238, 0.18); color: var(--cyan); }
.badge.cancelled { background: rgba(139, 152, 173, 0.2); color: var(--muted); }
.badge.cancelling { background: rgba(245, 158, 11, 0.18); color: var(--warning); }

.kpi-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 1rem;
  margin-bottom: 1.5rem;
}

.kpi-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 1rem 1.1rem;
}

.kpi-label {
  color: var(--muted);
  font-size: 0.8rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.kpi-value {
  font-size: 1.6rem;
  font-weight: 700;
  margin-top: 0.25rem;
}

.kpi-violet .kpi-value { color: var(--accent-2); }
.kpi-cyan .kpi-value { color: var(--cyan); }

.scout-pill {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0.25rem 0.6rem;
  border-radius: 999px;
  font-size: 0.78rem;
  font-weight: 600;
}

.scout-pill.on { background: rgba(34, 197, 94, 0.18); color: var(--success); }
.scout-pill.off { background: rgba(139, 152, 173, 0.18); color: var(--muted); }

.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  display: inline-block;
}

.dot.ok { background: var(--success); box-shadow: 0 0 6px var(--success); }
.dot.bad { background: var(--danger); box-shadow: 0 0 6px var(--danger); }

.panel {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 1rem;
}

.panel + .panel { margin-top: 1rem; }

table.data {
  width: 100%;
  border-collapse: collapse;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  overflow: hidden;
}

table.data th,
table.data td {
  text-align: left;
  padding: 0.6rem 0.75rem;
  border-bottom: 1px solid var(--border);
  font-size: 0.88rem;
  vertical-align: top;
}

table.data th {
  color: var(--muted);
  font-weight: 600;
  background: rgba(255, 255, 255, 0.03);
}

table.data tr:last-child td { border-bottom: none; }

.btn {
  display: inline-block;
  padding: 0.45rem 0.9rem;
  border: none;
  border-radius: var(--radius);
  background: var(--gradient);
  color: #fff;
  font: inherit;
  font-weight: 600;
  cursor: pointer;
}

.btn:hover { filter: brightness(1.08); }
.btn.secondary { background: rgba(255, 255, 255, 0.08); color: var(--text); }
.btn.danger { background: var(--danger); }
.btn:disabled { opacity: 0.5; cursor: not-allowed; }

input[type="text"],
textarea,
input[type="number"] {
  width: 100%;
  padding: 0.5rem 0.6rem;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  color: var(--text);
  font: inherit;
}

.form-row { margin-bottom: 0.9rem; }
label { display: block; font-weight: 600; margin-bottom: 0.3rem; font-size: 0.88rem; }

.flash { padding: 0.6rem 0.8rem; border-radius: var(--radius); margin-bottom: 1rem; background: rgba(34, 197, 94, 0.12); }
.flash.err { background: rgba(239, 68, 68, 0.14); }
```

`web/src/components/StatusBadge.tsx`:

```tsx
export function StatusBadge({ status }: { status: string | null }) {
  return <span className={`badge ${status ?? ""}`}>{status ?? "—"}</span>;
}
```

`web/src/components/KpiCard.tsx`:

```tsx
export function KpiCard({
  label,
  value,
  accent = "violet",
}: {
  label: string;
  value: string | number;
  accent?: "violet" | "cyan";
}) {
  return (
    <div className={`kpi-card kpi-${accent}`}>
      <div className="kpi-label">{label}</div>
      <div className="kpi-value">{value}</div>
    </div>
  );
}
```

`web/src/components/ScoutActiveBadge.tsx`:

```tsx
export function ScoutActiveBadge({ active }: { active: boolean }) {
  return (
    <span className={`scout-pill ${active ? "on" : "off"}`}>
      {active ? "Scout active" : "Scout idle"}
    </span>
  );
}
```

`web/src/components/StatusDot.tsx`:

```tsx
export function StatusDot({ ok }: { ok: boolean }) {
  return <span className={`dot ${ok ? "ok" : "bad"}`} title={ok ? "API reachable" : "API unreachable"} />;
}
```

`web/src/components/Sidebar.tsx`:

```tsx
import { NavLink } from "react-router-dom";

const LINKS = [
  { to: "/", label: "Dashboard" },
  { to: "/scout-hq", label: "Scout HQ" },
  { to: "/leads", label: "Leads" },
  { to: "/runs", label: "Runs" },
  { to: "/agents", label: "Agents" },
];

export function Sidebar() {
  return (
    <aside className="sidebar">
      <div className="brand">NextLevel</div>
      <nav>
        {LINKS.map((l) => (
          <NavLink key={l.to} to={l.to} end={l.to === "/"}>
            {l.label}
          </NavLink>
        ))}
      </nav>
    </aside>
  );
}
```

`web/src/components/Topbar.tsx`:

```tsx
import { ScoutActiveBadge } from "./ScoutActiveBadge";
import { StatusDot } from "./StatusDot";

export function Topbar({
  title,
  scoutActive,
  statusOk,
}: {
  title: string;
  scoutActive: boolean;
  statusOk: boolean;
}) {
  return (
    <header className="topbar">
      <h1>{title}</h1>
      <div className="topbar-right">
        <ScoutActiveBadge active={scoutActive} />
        <StatusDot ok={statusOk} />
      </div>
    </header>
  );
}
```

`web/src/components/Layout.tsx`:

```tsx
import { useQuery } from "@tanstack/react-query";
import { apiGet } from "../api/client";
import type { ScoutStatus } from "../api/types";
import { Sidebar } from "./Sidebar";
import { Topbar } from "./Topbar";

const TITLES: Record<string, string> = {
  "/": "Dashboard",
  "/scout-hq": "Scout HQ",
  "/leads": "Leads",
  "/runs": "Runs",
  "/agents": "Agents",
};

export function Layout({ children }: { children: React.ReactNode }) {
  const { data: status } = useQuery({
    queryKey: ["scout-status"],
    queryFn: () => apiGet<ScoutStatus>("/api/scout/status"),
    refetchInterval: 10000,
    retry: 0,
  });
  const title = TITLES[window.location.pathname] ?? "NextLevel";
  return (
    <div className="app-shell">
      <Sidebar />
      <div className="main">
        <Topbar
          title={title}
          scoutActive={Boolean(status?.scout_active)}
          statusOk={Boolean(status)}
        />
        <main className="page">{children}</main>
      </div>
    </div>
  );
}
```

Placeholder pages (all identical shape; create all eight):

`web/src/pages/Dashboard.tsx`:

```tsx
export default function Dashboard() {
  return <div className="panel muted">Dashboard — coming soon.</div>;
}
```

`web/src/pages/ScoutHQ.tsx`:

```tsx
export default function ScoutHQ() {
  return <div className="panel muted">Scout HQ — coming soon.</div>;
}
```

`web/src/pages/Leads.tsx`:

```tsx
export default function Leads() {
  return <div className="panel muted">Leads — coming soon.</div>;
}
```

`web/src/pages/LeadsDetail.tsx`:

```tsx
export default function LeadsDetail() {
  return <div className="panel muted">Lead detail — coming soon.</div>;
}
```

`web/src/pages/Runs.tsx`:

```tsx
export default function Runs() {
  return <div className="panel muted">Runs — coming soon.</div>;
}
```

`web/src/pages/RunsDetail.tsx`:

```tsx
export default function RunsDetail() {
  return <div className="panel muted">Run detail — coming soon.</div>;
}
```

`web/src/pages/Agents.tsx`:

```tsx
export default function Agents() {
  return <div className="panel muted">Agents — coming soon.</div>;
}
```

`web/src/pages/AgentsDetail.tsx`:

```tsx
export default function AgentsDetail() {
  return <div className="panel muted">Agent detail — coming soon.</div>;
}
```

`web/src/App.tsx`:

```tsx
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { Layout } from "./components/Layout";
import Dashboard from "./pages/Dashboard";
import ScoutHQ from "./pages/ScoutHQ";
import Leads from "./pages/Leads";
import LeadsDetail from "./pages/LeadsDetail";
import Runs from "./pages/Runs";
import RunsDetail from "./pages/RunsDetail";
import Agents from "./pages/Agents";
import AgentsDetail from "./pages/AgentsDetail";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route path="/" element={<Dashboard />} />
          <Route path="/scout-hq" element={<ScoutHQ />} />
          <Route path="/leads" element={<Leads />} />
          <Route path="/leads/:id" element={<LeadsDetail />} />
          <Route path="/runs" element={<Runs />} />
          <Route path="/runs/:id" element={<RunsDetail />} />
          <Route path="/agents" element={<Agents />} />
          <Route path="/agents/:name" element={<AgentsDetail />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
```

Note: `Layout` uses an `Outlet`. The `Layout` component above receives `children`, but with React Router's `element={<Layout />}` layout-route pattern, children must come from `<Outlet/>`. Fix `Layout.tsx` to use `Outlet`:

`web/src/components/Layout.tsx` (final):

```tsx
import { useQuery } from "@tanstack/react-query";
import { Outlet, useLocation } from "react-router-dom";
import { apiGet } from "../api/client";
import type { ScoutStatus } from "../api/types";
import { Sidebar } from "./Sidebar";
import { Topbar } from "./Topbar";

const TITLES: Record<string, string> = {
  "/": "Dashboard",
  "/scout-hq": "Scout HQ",
  "/leads": "Leads",
  "/runs": "Runs",
  "/agents": "Agents",
};

export function Layout() {
  const { pathname } = useLocation();
  const { data: status } = useQuery({
    queryKey: ["scout-status"],
    queryFn: () => apiGet<ScoutStatus>("/api/scout/status"),
    refetchInterval: 10000,
    retry: 0,
  });
  const title = TITLES[pathname] ?? "NextLevel";
  return (
    <div className="app-shell">
      <Sidebar />
      <div className="main">
        <Topbar
          title={title}
          scoutActive={Boolean(status?.scout_active)}
          statusOk={Boolean(status)}
        />
        <main className="page">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run (workdir `web`): `npm test`
Expected: 4 tests PASSED (StatusBadge 2, KpiCard 2).

- [ ] **Step 5: Verify build passes**

Run (workdir `web`): `npm run build`
Expected: no TS errors; `dist/` emitted.

- [ ] **Step 6: Verify routing serves**

Run (workdir `web`): `npm run dev` (background); `Invoke-RestMethod http://localhost:5173/` returns the app HTML; `http://localhost:5173/scout-hq` returns the shell. Stop dev server.

- [ ] **Step 7: Commit**

```bash
git add web
git commit -m "feat: app shell — sidebar, topbar, routing, shared UI primitives"
```

---

### Task 4: Dashboard page

**Files:**
- Create: `web/src/api/stats.ts`
- Create: `web/src/api/missions.ts`
- Modify: `web/src/pages/Dashboard.tsx`
- Test: `web/src/pages/Dashboard.test.tsx`

**Interfaces:**
- Consumes: `apiGet` (Task 2), `KpiCard`, `StatusBadge`, `ScoutActiveBadge` (Task 3), types `Stats`, `PipelineRun`.
- Produces:
  - `web/src/api/stats.ts`: `fetchStats(): Promise<Stats>` → `apiGet<Stats>("/api/stats")`.
  - `web/src/api/missions.ts`: `fetchRecentMissions(): Promise<PipelineRun[]>` → `apiGet<PipelineRun[]>("/api/pipeline-runs?limit=5")`.
  - `Dashboard` page — KPI cards (leads_total, leads_avg_score, runs_today, run_success_rate), active Scout widget + quick-start link to `/scout-hq`, recent runs feed.

- [ ] **Step 1: Write the failing test**

`web/src/pages/Dashboard.test.tsx`:

```tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import Dashboard from "./Dashboard";
import * as statsApi from "../api/stats";
import * as missionsApi from "../api/missions";

function renderDashboard() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <Dashboard />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("Dashboard", () => {
  it("renders KPI cards and recent missions", async () => {
    vi.spyOn(statsApi, "fetchStats").mockResolvedValue({
      leads_total: 6,
      leads_by_status: { raw: 6 },
      leads_avg_score: 3.5,
      runs_today: 35,
      run_success_rate: 5.0,
      recent_runs: [],
      scout_active: false,
      scout_last_seed: null,
    });
    vi.spyOn(missionsApi, "fetchRecentMissions").mockResolvedValue([
      { id: "r1", trigger: "api", seed_query: "agencies", status: "success", started_at: "2026-08-05T00:00:00", finished_at: null, meta: null },
    ]);

    renderDashboard();

    expect(await screen.findByText("Leads")).toBeInTheDocument();
    expect(screen.getByText("6")).toBeInTheDocument();
    expect(screen.getByText("Avg score")).toBeInTheDocument();
    expect(screen.getByText("3.5")).toBeInTheDocument();
    expect(screen.getByText("Runs today")).toBeInTheDocument();
    expect(screen.getByText("35")).toBeInTheDocument();
    expect(screen.getByText("Success rate")).toBeInTheDocument();
    expect(screen.getByText("5%")).toBeInTheDocument();
    expect(await screen.findByText("agencies")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open Scout HQ" })).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run (workdir `web`): `npm test`
Expected: FAIL — `Cannot find module './Dashboard'` or missing `fetchStats`.

- [ ] **Step 3: Create the files**

`web/src/api/stats.ts`:

```ts
import { apiGet } from "./client";
import type { Stats } from "./types";

export function fetchStats(): Promise<Stats> {
  return apiGet<Stats>("/api/stats");
}
```

`web/src/api/missions.ts`:

```ts
import { apiGet } from "./client";
import type { PipelineRun } from "./types";

export function fetchRecentMissions(): Promise<PipelineRun[]> {
  return apiGet<PipelineRun[]>("/api/pipeline-runs?limit=5");
}
```

`web/src/pages/Dashboard.tsx`:

```tsx
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { fetchRecentMissions } from "../api/missions";
import { fetchStats } from "../api/stats";
import { KpiCard } from "../components/KpiCard";
import { StatusBadge } from "../components/StatusBadge";
import { ScoutActiveBadge } from "../components/ScoutActiveBadge";

function fmt(v: number | null | undefined): string {
  return v == null ? "—" : String(v);
}

export default function Dashboard() {
  const { data: stats } = useQuery({ queryKey: ["stats"], queryFn: fetchStats });
  const { data: missions } = useQuery({
    queryKey: ["recent-missions"],
    queryFn: fetchRecentMissions,
  });

  return (
    <div>
      <div className="kpi-grid">
        <KpiCard label="Leads" value={fmt(stats?.leads_total)} />
        <KpiCard label="Avg score" value={fmt(stats?.leads_avg_score)} accent="cyan" />
        <KpiCard label="Runs today" value={fmt(stats?.runs_today)} />
        <KpiCard label="Success rate" value={stats?.run_success_rate != null ? `${stats.run_success_rate}%` : "—"} accent="cyan" />
      </div>

      <div className="panel">
        <h2>Active Scout</h2>
        <p>
          <ScoutActiveBadge active={Boolean(stats?.scout_active)} />
          {stats?.scout_active && stats.scout_last_seed ? (
            <span className="muted"> — running: {stats.scout_last_seed}</span>
          ) : null}
        </p>
        <Link className="btn" to="/scout-hq">Open Scout HQ</Link>
      </div>

      <div className="panel">
        <h2>Recent missions</h2>
        {!missions?.length ? (
          <p className="muted">No missions yet.</p>
        ) : (
          <table className="data">
            <thead>
              <tr>
                <th>Seed</th>
                <th>Status</th>
                <th>Trigger</th>
                <th>Started</th>
              </tr>
            </thead>
            <tbody>
              {missions.map((m) => (
                <tr key={m.id}>
                  <td>{m.seed_query ?? "—"}</td>
                  <td><StatusBadge status={m.status} /></td>
                  <td>{m.trigger ?? "—"}</td>
                  <td className="muted">{m.started_at ? new Date(m.started_at).toLocaleString() : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run (workdir `web`): `npm test`
Expected: 1 new test PASSED (Dashboard renders KPIs + missions).

- [ ] **Step 5: Verify build passes**

Run (workdir `web`): `npm run build`
Expected: no TS errors.

- [ ] **Step 6: Commit**

```bash
git add web
git commit -m "feat: dashboard page with KPI cards and recent missions"
```

---

### Task 5: Leads pages (list + detail)

**Files:**
- Create: `web/src/api/leads.ts`
- Modify: `web/src/pages/Leads.tsx`
- Modify: `web/src/pages/LeadsDetail.tsx`
- Test: `web/src/pages/Leads.test.tsx`

**Interfaces:**
- Consumes: `apiGet`, `apiSend`, `ApiError` (Task 2), `StatusBadge` (Task 3), types `Lead`, `LeadDetail`.
- Produces:
  - `web/src/api/leads.ts`: `fetchLeads(status?: string): Promise<Lead[]>` → `GET /api/leads?limit=100[&status=...]`; `fetchLead(id): Promise<LeadDetail>` → `GET /api/leads/{id}`; `updateLead(id, patch): Promise<Lead>` → `PATCH /api/leads/{id}`.
  - `Leads` page — list table with status filter dropdown (empty = all) + rows linking to `/leads/:id`.
  - `LeadsDetail` page — fields table + events table + status PATCH form (select status → update, refetch, flash message).

- [ ] **Step 1: Write the failing test**

`web/src/pages/Leads.test.tsx`:

```tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import Leads from "./Leads";
import * as leadsApi from "../api/leads";

function renderLeads() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <Leads />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("Leads", () => {
  it("renders leads from the api", async () => {
    vi.spyOn(leadsApi, "fetchLeads").mockResolvedValue([
      { id: "l1", name: "Acme", url: "https://acme.tn", status: "raw", source: "discovery", lead_score: 0.0, updated_at: null, created_at: null, country: null, industry: null, business_type: null, email: null, phone: null, seo_score: null, status_notes: null },
    ]);
    renderLeads();
    expect(await screen.findByText("Acme")).toBeInTheDocument();
    expect(screen.getByText("raw")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run (workdir `web`): `npm test`
Expected: FAIL — missing `fetchLeads`.

- [ ] **Step 3: Create the files**

`web/src/api/leads.ts`:

```ts
import { apiGet, apiSend } from "./client";
import type { Lead, LeadDetail } from "./types";

export function fetchLeads(status?: string): Promise<Lead[]> {
  const q = status ? `&status=${encodeURIComponent(status)}` : "";
  return apiGet<Lead[]>(`/api/leads?limit=100${q}`);
}

export function fetchLead(id: string): Promise<LeadDetail> {
  return apiGet<LeadDetail>(`/api/leads/${id}`);
}

export function updateLead(id: string, patch: Record<string, unknown>): Promise<Lead> {
  return apiSend<Lead>(`/api/leads/${id}`, "PATCH", patch);
}
```

`web/src/pages/Leads.tsx`:

```tsx
import { useQuery } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";
import { fetchLeads } from "../api/leads";
import { StatusBadge } from "../components/StatusBadge";

const STATUSES = ["raw", "categorized", "enriched", "contacted", "converted", "unreachable", "low_priority"];

export default function Leads() {
  const [params, setParams] = useSearchParams();
  const status = params.get("status") ?? "";
  const { data: leads } = useQuery({
    queryKey: ["leads", status],
    queryFn: () => fetchLeads(status || undefined),
  });

  return (
    <div>
      <div className="form-row" style={{ maxWidth: 240 }}>
        <label htmlFor="status-filter">Status</label>
        <select
          id="status-filter"
          value={status}
          onChange={(e) => {
            const v = e.target.value;
            setParams(v ? { status: v } : {});
          }}
        >
          <option value="">All</option>
          {STATUSES.map((s) => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>
      </div>

      {!leads?.length ? (
        <p className="muted">No leads yet. Run the discovery pipeline.</p>
      ) : (
        <table className="data">
          <thead>
            <tr>
              <th>Name</th>
              <th>URL</th>
              <th>Status</th>
              <th>Source</th>
              <th>Score</th>
            </tr>
          </thead>
          <tbody>
            {leads.map((lead) => (
              <tr key={lead.id}>
                <td><Link to={`/leads/${lead.id}`}>{lead.name ?? "—"}</Link></td>
                <td>{lead.url ? <a href={lead.url} target="_blank" rel="noopener noreferrer">{lead.url}</a> : "—"}</td>
                <td><StatusBadge status={lead.status} /></td>
                <td>{lead.source ?? "—"}</td>
                <td>{lead.lead_score ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
```

`web/src/pages/LeadsDetail.tsx`:

```tsx
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { fetchLead, updateLead } from "../api/leads";
import { StatusBadge } from "../components/StatusBadge";

const STATUSES = ["raw", "categorized", "enriched", "contacted", "converted", "unreachable", "low_priority"];

export default function LeadsDetail() {
  const { id = "" } = useParams();
  const qc = useQueryClient();
  const [flash, setFlash] = useState<string | null>(null);

  const { data: lead } = useQuery({
    queryKey: ["lead", id],
    queryFn: () => fetchLead(id),
  });

  const save = useMutation({
    mutationFn: (status: string) => updateLead(id, { status }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["lead", id] });
      qc.invalidateQueries({ queryKey: ["stats"] });
      setFlash("Status updated.");
    },
    onError: (e: Error) => setFlash(e.message),
  });

  if (!lead) return <p className="muted">Loading…</p>;

  const rows: Array<[string, string]> = [
    ["Source", lead.source ?? "—"],
    ["Country", lead.country ?? "—"],
    ["Industry", lead.industry ?? "—"],
    ["Business type", lead.business_type ?? "—"],
    ["Email", lead.email ?? "—"],
    ["Phone", lead.phone ?? "—"],
    ["SEO score", lead.seo_score != null ? String(lead.seo_score) : "—"],
    ["Lead score", lead.lead_score != null ? String(lead.lead_score) : "—"],
  ];

  return (
    <div>
      {flash ? <div className="flash">{flash}</div> : null}
      <h2>{lead.name ?? "—"} <StatusBadge status={lead.status} /></h2>
      {lead.url ? <p className="muted"><a href={lead.url} target="_blank" rel="noopener noreferrer">{lead.url}</a></p> : null}

      <div className="panel">
        <table className="data">
          <tbody>
            {rows.map(([k, v]) => (
              <tr key={k}><th style={{ width: 140 }}>{k}</th><td>{v}</td></tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="panel">
        <h3>Update status</h3>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            const fd = new FormData(e.currentTarget);
            save.mutate(String(fd.get("status")));
          }}
        >
          <div className="form-row" style={{ maxWidth: 240 }}>
            <label htmlFor="status">Status</label>
            <select id="status" name="status" defaultValue={lead.status ?? "raw"}>
              {STATUSES.map((s) => (
                <option key={s} value={s}>{s}</option>
              ))}
            </select>
          </div>
          <button className="btn" type="submit" disabled={save.isPending}>Save</button>
        </form>
      </div>

      <div className="panel">
        <h3>Events</h3>
        {!lead.events?.length ? (
          <p className="muted">No events.</p>
        ) : (
          <table className="data">
            <thead>
              <tr><th>Type</th><th>Agent run</th><th>When</th></tr>
            </thead>
            <tbody>
              {lead.events.map((e) => (
                <tr key={e.id}>
                  <td><StatusBadge status={e.event_type} /></td>
                  <td className="muted">{e.agent_run_id ?? "—"}</td>
                  <td className="muted">{e.created_at ? new Date(e.created_at).toLocaleString() : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <p><Link to="/leads">← Back to leads</Link></p>
    </div>
  );
}
```

Note: add a `select` style to `web/src/styles/components.css` (append to the existing input rules):

```css
select {
  width: 100%;
  padding: 0.5rem 0.6rem;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  color: var(--text);
  font: inherit;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run (workdir `web`): `npm test`
Expected: 1 new test PASSED.

- [ ] **Step 5: Verify build passes**

Run (workdir `web`): `npm run build`
Expected: no TS errors.

- [ ] **Step 6: Commit**

```bash
git add web
git commit -m "feat: leads list + detail pages with status editing"
```

---

### Task 6: Runs pages (list + detail)

**Files:**
- Create: `web/src/api/runs.ts`
- Modify: `web/src/pages/Runs.tsx`
- Modify: `web/src/pages/RunsDetail.tsx`
- Test: `web/src/pages/Runs.test.tsx`

**Interfaces:**
- Consumes: `apiGet` (Task 2), `StatusBadge` (Task 3), types `AgentRun`.
- Produces:
  - `web/src/api/runs.ts`: `fetchRuns(): Promise<AgentRun[]>` → `GET /api/agent-runs?limit=100`; `fetchRun(id): Promise<AgentRun>` → `GET /api/agent-runs/{id}`.
  - `Runs` page — table of agent runs (agent, model, status, duration, records, started).
  - `RunsDetail` page — run detail with input/output/apis/error `<pre>` blocks.

- [ ] **Step 1: Write the failing test**

`web/src/pages/Runs.test.tsx`:

```tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import Runs from "./Runs";
import * as runsApi from "../api/runs";

function renderRuns() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <Runs />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("Runs", () => {
  it("renders agent runs", async () => {
    vi.spyOn(runsApi, "fetchRuns").mockResolvedValue([
      { id: "ar1", pipeline_run_id: "p1", agent_name: "discovery", model: "m", status: "success", input_summary: "seed", output_summary: null, output_json: null, apis_consumed: null, records_processed: 4, error_message: null, started_at: "2026-08-05T00:00:00", finished_at: "2026-08-05T00:00:02" },
    ]);
    renderRuns();
    expect(await screen.findByText("discovery")).toBeInTheDocument();
    expect(screen.getByText("success")).toBeInTheDocument();
    expect(screen.getByText("4")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run (workdir `web`): `npm test`
Expected: FAIL — missing `fetchRuns`.

- [ ] **Step 3: Create the files**

`web/src/api/runs.ts`:

```ts
import { apiGet } from "./client";
import type { AgentRun } from "./types";

export function fetchRuns(): Promise<AgentRun[]> {
  return apiGet<AgentRun[]>("/api/agent-runs?limit=100");
}

export function fetchRun(id: string): Promise<AgentRun> {
  return apiGet<AgentRun>(`/api/agent-runs/${id}`);
}
```

`web/src/pages/Runs.tsx`:

```tsx
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { fetchRuns } from "../api/runs";
import { StatusBadge } from "../components/StatusBadge";

function durationMs(row: { started_at: string | null; finished_at: string | null }): string {
  if (!row.started_at || !row.finished_at) return "—";
  const d = new Date(row.finished_at).getTime() - new Date(row.started_at).getTime();
  if (d < 1000) return `${Math.round(d)} ms`;
  return `${(d / 1000).toFixed(2)} s`;
}

export default function Runs() {
  const { data: runs } = useQuery({ queryKey: ["runs"], queryFn: fetchRuns });

  if (!runs?.length) return <p className="muted">No agent runs yet.</p>;

  return (
    <table className="data">
      <thead>
        <tr>
          <th>Agent</th>
          <th>Model</th>
          <th>Status</th>
          <th>Duration</th>
          <th>Records</th>
          <th>Started</th>
        </tr>
      </thead>
      <tbody>
        {runs.map((r) => (
          <tr key={r.id}>
            <td><Link to={`/runs/${r.id}`}>{r.agent_name}</Link></td>
            <td className="muted">{r.model ?? "—"}</td>
            <td><StatusBadge status={r.status} /></td>
            <td>{durationMs(r)}</td>
            <td>{r.records_processed ?? 0}</td>
            <td className="muted">{r.started_at ? new Date(r.started_at).toLocaleString() : "—"}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
```

`web/src/pages/RunsDetail.tsx`:

```tsx
import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { fetchRun } from "../api/runs";
import { StatusBadge } from "../components/StatusBadge";

export default function RunsDetail() {
  const { id = "" } = useParams();
  const { data: run } = useQuery({
    queryKey: ["run", id],
    queryFn: () => fetchRun(id),
  });

  if (!run) return <p className="muted">Loading…</p>;

  return (
    <div>
      <h2>{run.agent_name} <StatusBadge status={run.status} /></h2>
      <p className="muted">Pipeline: {run.pipeline_run_id} · Model: {run.model ?? "—"}</p>

      <div className="panel">
        <h3>Input</h3>
        <pre>{run.input_summary ?? "—"}</pre>
      </div>

      <div className="panel">
        <h3>Output summary</h3>
        <pre>{run.output_summary ?? "—"}</pre>
      </div>

      {run.output_json ? (
        <div className="panel">
          <h3>Output JSON</h3>
          <pre>{JSON.stringify(run.output_json, null, 2)}</pre>
        </div>
      ) : null}

      {run.apis_consumed?.length ? (
        <div className="panel">
          <h3>APIs consumed</h3>
          <pre>{JSON.stringify(run.apis_consumed, null, 2)}</pre>
        </div>
      ) : null}

      {run.error_message ? (
        <div className="panel">
          <h3>Error</h3>
          <pre>{run.error_message}</pre>
        </div>
      ) : null}

      <p><Link to="/runs">← Back to runs</Link></p>
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run (workdir `web`): `npm test`
Expected: 1 new test PASSED.

- [ ] **Step 5: Verify build passes**

Run (workdir `web`): `npm run build`
Expected: no TS errors.

- [ ] **Step 6: Commit**

```bash
git add web
git commit -m "feat: agent runs list + detail pages"
```

---

### Task 7: Agents pages (roster + editor with Scout controls)

**Files:**
- Create: `web/src/api/agents.ts`
- Modify: `web/src/pages/Agents.tsx`
- Modify: `web/src/pages/AgentsDetail.tsx`
- Test: `web/src/pages/Agents.test.tsx`

**Interfaces:**
- Consumes: `apiGet`, `apiSend`, `ApiError` (Task 2), types `AgentProfile`, `DiscoveryStartOut`, `DiscoveryFinishOut`, `ScoutStatus`.
- Produces:
  - `web/src/api/agents.ts`:
    - `fetchAgents(): Promise<AgentProfile[]>` → `GET /api/agents`.
    - `fetchAgent(name): Promise<AgentProfile>` → `GET /api/agents/{name}`.
    - `updateAgent(name, patch): Promise<AgentProfile>` → `PATCH /api/agents/{name}` (patch `{display_name, mission_prompt, enabled_tools, model, default_seed_query}`).
    - `startScout(seedQuery, maxSearchResults): Promise<DiscoveryStartOut>` → `POST /api/agents/discovery/start` body `{seed_query, max_search_results}`.
    - `finishScout(): Promise<DiscoveryFinishOut>` → `POST /api/agents/discovery/finish`.
  - `Agents` page — roster table (agent, model, tools, default seed) linking to `/agents/:name`.
  - `AgentsDetail` page — profile editor (display name, mission prompt, model, default seed for discovery, tool checkboxes from `available_tools`, enabled tools) + Scout start/finish controls when `agent_name === "discovery"` + active status from `/api/scout/status`.

- [ ] **Step 1: Write the failing test**

`web/src/pages/Agents.test.tsx`:

```tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import Agents from "./Agents";
import * as agentsApi from "../api/agents";

function renderAgents() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <Agents />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("Agents", () => {
  it("renders the agent roster", async () => {
    vi.spyOn(agentsApi, "fetchAgents").mockResolvedValue([
      { agent_name: "discovery", display_name: "Discovery (Scout)", mission_prompt: "p", enabled_tools: ["web_search"], model: null, default_seed_query: "agencies", updated_at: null, available_tools: [] },
    ]);
    renderAgents();
    expect(await screen.findByText("Discovery (Scout)")).toBeInTheDocument();
    expect(screen.getByText("agencies")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run (workdir `web`): `npm test`
Expected: FAIL — missing `fetchAgents`.

- [ ] **Step 3: Create the files**

`web/src/api/agents.ts`:

```ts
import { apiGet, apiSend } from "./client";
import type { AgentProfile, DiscoveryFinishOut, DiscoveryStartOut } from "./types";

export function fetchAgents(): Promise<AgentProfile[]> {
  return apiGet<AgentProfile[]>("/api/agents");
}

export function fetchAgent(name: string): Promise<AgentProfile> {
  return apiGet<AgentProfile>(`/api/agents/${name}`);
}

export function updateAgent(name: string, patch: Record<string, unknown>): Promise<AgentProfile> {
  return apiSend<AgentProfile>(`/api/agents/${name}`, "PATCH", patch);
}

export function startScout(seedQuery: string, maxSearchResults: number): Promise<DiscoveryStartOut> {
  return apiSend<DiscoveryStartOut>("/api/agents/discovery/start", "POST", {
    seed_query: seedQuery,
    max_search_results: maxSearchResults,
  });
}

export function finishScout(): Promise<DiscoveryFinishOut> {
  return apiSend<DiscoveryFinishOut>("/api/agents/discovery/finish", "POST");
}
```

`web/src/pages/Agents.tsx`:

```tsx
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { fetchAgents } from "../api/agents";

export default function Agents() {
  const { data: agents } = useQuery({ queryKey: ["agents"], queryFn: fetchAgents });

  if (!agents?.length) return <p className="muted">No agent profiles.</p>;

  return (
    <table className="data">
      <thead>
        <tr>
          <th>Agent</th>
          <th>Model</th>
          <th>Tools</th>
          <th>Default seed</th>
        </tr>
      </thead>
      <tbody>
        {agents.map((a) => (
          <tr key={a.agent_name}>
            <td>
              <Link to={`/agents/${a.agent_name}`}>{a.display_name}</Link>
              <div className="muted">{a.agent_name}</div>
            </td>
            <td>{a.model || "settings default"}</td>
            <td>{a.enabled_tools.join(", ")}</td>
            <td className="muted">{a.default_seed_query || "—"}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
```

`web/src/pages/AgentsDetail.tsx`:

```tsx
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { fetchAgent, finishScout, startScout, updateAgent } from "../api/agents";
import type { ScoutStatus } from "../api/types";
import { apiGet } from "../api/client";

export default function AgentsDetail() {
  const { name = "" } = useParams();
  const qc = useQueryClient();
  const [flash, setFlash] = useState<string | null>(null);
  const [flashErr, setFlashErr] = useState(false);
  const [seed, setSeed] = useState("");
  const [maxResults, setMaxResults] = useState(5);

  const { data: agent } = useQuery({
    queryKey: ["agent", name],
    queryFn: () => fetchAgent(name),
  });

  const { data: status } = useQuery({
    queryKey: ["scout-status"],
    queryFn: () => apiGet<ScoutStatus>("/api/scout/status"),
    refetchInterval: 8000,
    retry: 0,
  });

  const isDiscovery = name === "discovery";

  const save = useMutation({
    mutationFn: (patch: Record<string, unknown>) => updateAgent(name, patch),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["agent", name] });
      qc.invalidateQueries({ queryKey: ["agents"] });
      setFlash("Profile saved.");
      setFlashErr(false);
    },
    onError: (e: Error) => {
      setFlash(e.message);
      setFlashErr(true);
    },
  });

  const start = useMutation({
    mutationFn: () => startScout(seed, maxResults),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["scout-status"] });
      setFlash("Scout started.");
      setFlashErr(false);
    },
    onError: (e: Error) => {
      setFlash(e.message);
      setFlashErr(true);
    },
  });

  const finish = useMutation({
    mutationFn: () => finishScout(),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["scout-status"] });
      setFlash("Finish requested.");
      setFlashErr(false);
    },
    onError: (e: Error) => {
      setFlash(e.message);
      setFlashErr(true);
    },
  });

  if (!agent) return <p className="muted">Loading…</p>;

  return (
    <div>
      {flash ? <div className={`flash ${flashErr ? "err" : ""}`}>{flash}</div> : null}
      <h2>{agent.display_name}</h2>
      <p className="muted"><Link to="/agents">← Agents</Link></p>

      {isDiscovery ? (
        <div className="panel">
          <h3>Scout controls</h3>
          <p><span className="scout-pill {status?.scout_active ? 'on' : 'off'}">{status?.scout_active ? "Scout active" : "Scout idle"}</span></p>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              start.mutate();
            }}
          >
            <div className="form-row">
              <label htmlFor="seed_query">Goal / seed hint (Start scout)</label>
              <input
                id="seed_query"
                type="text"
                value={seed}
                onChange={(e) => setSeed(e.target.value)}
                placeholder={agent.default_seed_query ?? ""}
                required
                minLength={2}
              />
            </div>
            <div className="form-row" style={{ maxWidth: 200 }}>
              <label htmlFor="max_search_results">Max search results</label>
              <input
                id="max_search_results"
                type="number"
                value={maxResults}
                min={1}
                onChange={(e) => setMaxResults(Number(e.target.value))}
              />
            </div>
            <button className="btn" type="submit" disabled={start.isPending}>Start scout</button>
            <button className="btn danger" type="button" onClick={() => finish.mutate()} disabled={finish.isPending}>Finish (cancel)</button>
          </form>
        </div>
      ) : null}

      <div className="panel">
        <h3>Profile</h3>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            const fd = new FormData(e.currentTarget);
            const tools = Array.from(fd.getAll("enabled_tools")).map(String);
            save.mutate({
              display_name: String(fd.get("display_name") ?? "").trim(),
              mission_prompt: String(fd.get("mission_prompt") ?? "").trim(),
              enabled_tools: tools,
              model: String(fd.get("model") ?? "").trim() || null,
              ...(isDiscovery ? { default_seed_query: String(fd.get("default_seed_query") ?? "").trim() || null } : {}),
            });
          }}
        >
          <div className="form-row">
            <label htmlFor="display_name">Display name</label>
            <input id="display_name" name="display_name" type="text" defaultValue={agent.display_name} />
          </div>
          <div className="form-row">
            <label htmlFor="mission_prompt">Mission prompt</label>
            <textarea id="mission_prompt" name="mission_prompt" rows={8} defaultValue={agent.mission_prompt} />
          </div>
          <div className="form-row">
            <label htmlFor="model">Model override (blank = settings default)</label>
            <input id="model" name="model" type="text" defaultValue={agent.model ?? ""} placeholder="e.g. discovery-model" />
          </div>
          {isDiscovery ? (
            <div className="form-row">
              <label htmlFor="default_seed_query">Default seed query</label>
              <input id="default_seed_query" name="default_seed_query" type="text" defaultValue={agent.default_seed_query ?? ""} />
            </div>
          ) : null}
          <div className="form-row">
            <label>Enabled tools</label>
            {agent.available_tools.map((t) => (
              <label key={t.id} style={{ fontWeight: 400, margin: "0.25rem 0" }}>
                <input
                  type="checkbox"
                  name="enabled_tools"
                  value={t.id}
                  defaultChecked={agent.enabled_tools.includes(t.id)}
                />{" "}
                <strong>{t.id}</strong> — {t.label}
              </label>
            ))}
          </div>
          <button className="btn" type="submit" disabled={save.isPending}>Save profile</button>
        </form>
      </div>
    </div>
  );
}
```

Note: the `className="scout-pill {status?.scout_active ? 'on' : 'off'}"` line is intentionally wrong template-literal syntax; replace it with a template literal:

```tsx
<span className={`scout-pill ${status?.scout_active ? "on" : "off"}`}>
```

- [ ] **Step 4: Run test to verify it passes**

Run (workdir `web`): `npm test`
Expected: 1 new test PASSED.

- [ ] **Step 5: Verify build passes**

Run (workdir `web`): `npm run build`
Expected: no TS errors.

- [ ] **Step 6: Commit**

```bash
git add web
git commit -m "feat: agents roster + profile editor + scout start/finish"
```

---

### Task 8: Scout HQ — mission board + SSE chat

**Files:**
- Create: `web/src/api/scout.ts`
- Create: `web/src/hooks/useScoutChat.ts`
- Create: `web/src/components/ToolActivityCard.tsx`
- Create: `web/src/components/MissionBoard.tsx`
- Create: `web/src/components/ScoutChat.tsx`
- Create: `web/src/styles/scout.css`
- Modify: `web/src/pages/ScoutHQ.tsx`
- Test: `web/src/hooks/useScoutChat.test.ts`
- Test: `web/src/components/ToolActivityCard.test.tsx`

**Interfaces:**
- Consumes: `apiGet`, `apiSend` (Task 2), `parseSseFrames`/`takeFrames` (Task 2), types `ScoutThread`, `ScoutMessage`, `PipelineRun`, `DiscoveryStartOut`; `startScout`, `finishScout` (Task 7).
- Produces:
  - `web/src/api/scout.ts`:
    - `fetchThreads(): Promise<ScoutThread[]>` → `GET /api/scout/threads?limit=50`.
    - `createThread(title?): Promise<ScoutThread>` → `POST /api/scout/threads` body `{title}`.
    - `fetchMessages(threadId): Promise<ScoutMessage[]>` → `GET /api/scout/threads/{id}/messages`.
    - `fetchMissions(): Promise<PipelineRun[]>` → `GET /api/pipeline-runs?limit=20`.
    - `streamScoutTurn(threadId, content, handlers)` — SSE POST consumer (defined in Task 2's `sse.ts`; export here).
  - `web/src/hooks/useScoutChat.ts`: `useScoutChat(threadId, onTurnDone)` returning `{ streaming, assistantText, error, toolCalls, send }`.
  - `ToolActivityCard` — renders a persisted `role="tool"` message (tool_name + args + result/error).
  - `MissionBoard` — mission list + Start/Finish Scout controls.
  - `ScoutChat` — thread list + messages + input box + SSE streaming + tool cards.
  - `ScoutHQ` — split view: `<MissionBoard/>` left, `<ScoutChat/>` right.

- [ ] **Step 1: Write the failing tests**

`web/src/hooks/useScoutChat.test.ts`:

```ts
import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useScoutChat } from "./useScoutChat";

function sseStream(frames: string[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  return new ReadableStream({
    start(controller) {
      for (const f of frames) controller.enqueue(encoder.encode(f));
      controller.close();
    },
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("useScoutChat", () => {
  it("streams deltas then calls onTurnDone", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true,
      body: sseStream([
        "event: start\ndata: {}\n\n",
        "event: delta\ndata: {\"delta\":\"Hel\"}\n\n",
        "event: delta\ndata: {\"delta\":\"lo\"}\n\n",
        "event: done\ndata: {\"thread_id\":\"t1\",\"assistant\":\"Hello\",\"tool_calls\":2}\n\n",
      ]),
    }));
    const onTurnDone = vi.fn();
    const { result } = renderHook(() => useScoutChat("t1", onTurnDone));

    act(() => {
      void result.current.send("hi");
    });

    await waitFor(() => expect(result.current.assistantText).toBe("Hello"));
    expect(result.current.toolCalls).toBe(2);
    expect(onTurnDone).toHaveBeenCalledTimes(1);
    expect(result.current.streaming).toBe(false);
  });

  it("surfaces an error event", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true,
      body: sseStream([
        "event: start\ndata: {}\n\n",
        "event: error\ndata: {\"detail\":\"engine blew up\"}\n\n",
      ]),
    }));
    const { result } = renderHook(() => useScoutChat("t1"));

    act(() => {
      void result.current.send("hi");
    });

    await waitFor(() => expect(result.current.error).toBe("engine blew up"));
  });
});
```

`web/src/components/ToolActivityCard.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ToolActivityCard } from "./ToolActivityCard";
import type { ScoutMessage } from "../api/types";

const toolMsg: ScoutMessage = {
  id: "m1",
  thread_id: "t1",
  role: "tool",
  content: "[web_search]",
  tool_name: "web_search",
  tool_args: { query: "plumber" },
  tool_result: { result: [{ title: "A" }], error: null },
  created_at: null,
};

describe("ToolActivityCard", () => {
  it("renders tool name and args", () => {
    render(<ToolActivityCard message={toolMsg} />);
    expect(screen.getByText("web_search")).toBeInTheDocument();
    expect(screen.getByText(/plumber/)).toBeInTheDocument();
  });

  it("renders the error when the tool failed", () => {
    render(<ToolActivityCard message={{ ...toolMsg, tool_result: { result: null, error: "boom" } }} />);
    expect(screen.getByText("boom")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run (workdir `web`): `npm test`
Expected: FAIL — missing modules.

- [ ] **Step 3: Create the files**

`web/src/api/scout.ts`:

```ts
import { apiGet, apiSend } from "./client";
import { takeFrames } from "./sse";
import type { PipelineRun, ScoutMessage, ScoutThread } from "./types";

export function fetchThreads(): Promise<ScoutThread[]> {
  return apiGet<ScoutThread[]>("/api/scout/threads?limit=50");
}

export function createThread(title?: string): Promise<ScoutThread> {
  return apiSend<ScoutThread>("/api/scout/threads", "POST", { title });
}

export function fetchMessages(threadId: string): Promise<ScoutMessage[]> {
  return apiGet<ScoutMessage[]>(`/api/scout/threads/${threadId}/messages`);
}

export function fetchMissions(): Promise<PipelineRun[]> {
  return apiGet<PipelineRun[]>("/api/pipeline-runs?limit=20");
}

export interface ScoutTurnHandlers {
  onStart?: () => void;
  onDelta?: (delta: string, index: number) => void;
  onDone?: (payload: { thread_id: string; assistant: string; tool_calls: number }) => void;
  onError?: (detail: string) => void;
}

export async function streamScoutTurn(
  threadId: string,
  content: string,
  handlers: ScoutTurnHandlers,
): Promise<void> {
  const res = await fetch(`/api/scout/threads/${threadId}/messages`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content }),
  });
  if (!res.ok) {
    const text = await res.text();
    handlers.onError?.(text || `HTTP ${res.status}`);
    return;
  }
  const reader = res.body?.getReader();
  if (!reader) {
    handlers.onError?.("No response body");
    return;
  }
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const { frames, rest } = takeFrames(buffer);
    buffer = rest;
    for (const frame of frames) {
      if (frame.event === "start") {
        handlers.onStart?.();
      } else if (frame.event === "delta") {
        try {
          const data = JSON.parse(frame.data) as { delta: string; index: number };
          handlers.onDelta?.(data.delta, data.index);
        } catch {
          // ignore malformed delta
        }
      } else if (frame.event === "done") {
        try {
          handlers.onDone?.(JSON.parse(frame.data) as { thread_id: string; assistant: string; tool_calls: number });
        } catch {
          // ignore
        }
      } else if (frame.event === "error") {
        try {
          const data = JSON.parse(frame.data) as { detail?: string };
          handlers.onError?.(data.detail ?? frame.data);
        } catch {
          handlers.onError?.(frame.data);
        }
      }
    }
  }
}
```

`web/src/hooks/useScoutChat.ts`:

```ts
import { useCallback, useState } from "react";
import { streamScoutTurn } from "../api/scout";

export function useScoutChat(threadId: string | null, onTurnDone?: () => void) {
  const [streaming, setStreaming] = useState(false);
  const [assistantText, setAssistantText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [toolCalls, setToolCalls] = useState(0);

  const send = useCallback(
    async (content: string) => {
      if (!threadId) return;
      setStreaming(true);
      setError(null);
      setAssistantText("");
      setToolCalls(0);
      try {
        await streamScoutTurn(threadId, content, {
          onStart: () => setStreaming(true),
          onDelta: (delta) => setAssistantText((prev) => prev + delta),
          onDone: (payload) => {
            setToolCalls(payload.tool_calls);
            onTurnDone?.();
          },
          onError: (detail) => setError(detail),
        });
      } finally {
        setStreaming(false);
      }
    },
    [threadId, onTurnDone],
  );

  return { streaming, assistantText, error, toolCalls, send };
}
```

`web/src/components/ToolActivityCard.tsx`:

```tsx
import type { ScoutMessage } from "../api/types";

export function ToolActivityCard({ message }: { message: ScoutMessage }) {
  const result = message.tool_result as { result?: unknown; error?: string | null } | null;
  const error = result?.error ?? null;
  return (
    <div className={`tool-card ${error ? "tool-card-error" : ""}`}>
      <div className="tool-card-title">
        <span className="tool-card-icon">⚙</span> {message.tool_name ?? "tool"}
      </div>
      {message.tool_args ? <pre>{JSON.stringify(message.tool_args, null, 2)}</pre> : null}
      {error ? (
        <p className="tool-card-error-text">Error: {error}</p>
      ) : (
        <pre>{JSON.stringify(result?.result ?? null, null, 2)}</pre>
      )}
    </div>
  );
}
```

`web/src/components/MissionBoard.tsx`:

```tsx
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { fetchMissions } from "../api/scout";
import { finishScout, startScout } from "../api/agents";
import { StatusBadge } from "./StatusBadge";

export function MissionBoard() {
  const qc = useQueryClient();
  const [seed, setSeed] = useState("");
  const [flash, setFlash] = useState<string | null>(null);
  const [flashErr, setFlashErr] = useState(false);

  const { data: missions } = useQuery({
    queryKey: ["missions"],
    queryFn: fetchMissions,
    refetchInterval: 10000,
  });

  const start = useMutation({
    mutationFn: () => startScout(seed, 5),
    onSuccess: () => {
      setSeed("");
      setFlash("Scout started.");
      setFlashErr(false);
      qc.invalidateQueries({ queryKey: ["missions"] });
      qc.invalidateQueries({ queryKey: ["scout-status"] });
    },
    onError: (e: Error) => {
      setFlash(e.message);
      setFlashErr(true);
    },
  });

  const finish = useMutation({
    mutationFn: () => finishScout(),
    onSuccess: () => {
      setFlash("Finish requested.");
      setFlashErr(false);
      qc.invalidateQueries({ queryKey: ["missions"] });
      qc.invalidateQueries({ queryKey: ["scout-status"] });
    },
    onError: (e: Error) => {
      setFlash(e.message);
      setFlashErr(true);
    },
  });

  return (
    <div className="mission-board">
      {flash ? <div className={`flash ${flashErr ? "err" : ""}`}>{flash}</div> : null}

      <div className="panel">
        <h3>Start Scout</h3>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            start.mutate();
          }}
        >
          <div className="form-row">
            <input
              type="text"
              placeholder="Seed query (e.g. agencies Tunisia)"
              value={seed}
              onChange={(e) => setSeed(e.target.value)}
              required
              minLength={2}
            />
          </div>
          <button className="btn" type="submit" disabled={start.isPending}>Start</button>
          <button className="btn danger" type="button" onClick={() => finish.mutate()} disabled={finish.isPending}>Finish</button>
        </form>
      </div>

      <div className="panel">
        <h3>Missions</h3>
        {!missions?.length ? (
          <p className="muted">No missions yet.</p>
        ) : (
          <table className="data">
            <thead>
              <tr>
                <th>Seed</th>
                <th>Status</th>
                <th>Runs</th>
                <th>Started</th>
              </tr>
            </thead>
            <tbody>
              {missions.map((m) => (
                <tr key={m.id}>
                  <td>{m.seed_query ?? "—"}</td>
                  <td><StatusBadge status={m.status} /></td>
                  <td>{m.agent_run_count ?? 0}</td>
                  <td className="muted">{m.started_at ? new Date(m.started_at).toLocaleString() : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
```

`web/src/components/ScoutChat.tsx`:

```tsx
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { createThread, fetchMessages, fetchThreads } from "../api/scout";
import { useScoutChat } from "../hooks/useScoutChat";
import { ToolActivityCard } from "./ToolActivityCard";

export function ScoutChat() {
  const qc = useQueryClient();
  const [threadId, setThreadId] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);

  const { data: threads } = useQuery({ queryKey: ["threads"], queryFn: fetchThreads });
  const { data: messages } = useQuery({
    queryKey: ["messages", threadId],
    queryFn: () => (threadId ? fetchMessages(threadId) : Promise.resolve([])),
    enabled: Boolean(threadId),
  });

  const create = useMutation({
    mutationFn: () => createThread("New chat"),
    onSuccess: (t) => {
      qc.invalidateQueries({ queryKey: ["threads"] });
      setThreadId(t.id);
    },
  });

  const { streaming, assistantText, error, toolCalls, send } = useScoutChat(
    threadId,
    () => {
      qc.invalidateQueries({ queryKey: ["messages", threadId] });
    },
  );

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, assistantText]);

  const toolMessages = (messages ?? []).filter((m) => m.role === "tool");
  const visibleAssistant =
    assistantText ||
    [...(messages ?? [])].reverse().find((m) => m.role === "assistant")?.content ||
    "";

  return (
    <div className="scout-chat">
      <div className="scout-chat-threads">
        <button className="btn" type="button" onClick={() => create.mutate()} disabled={create.isPending}>
          + New thread
        </button>
        {threads?.map((t) => (
          <button
            key={t.id}
            type="button"
            className={`thread-pill ${t.id === threadId ? "active" : ""}`}
            onClick={() => setThreadId(t.id)}
          >
            {t.title ?? "Untitled"}
          </button>
        ))}
      </div>

      <div className="scout-chat-messages">
        {!threadId ? (
          <p className="muted">Select or create a thread to start chatting with the Scout.</p>
        ) : (
          <>
            {messages?.map((m) => {
              if (m.role === "tool") {
                return <ToolActivityCard key={m.id} message={m} />;
              }
              return (
                <div key={m.id} className={`chat-bubble ${m.role}`}>
                  {m.content ?? ""}
                </div>
              );
            })}
            {assistantText ? <div className="chat-bubble assistant">{assistantText}</div> : null}
            {streaming ? <div className="muted">Scout is thinking{toolCalls > 0 ? ` · ${toolCalls} tool call(s)` : ""}…</div> : null}
            {error ? <div className="flash err">{error}</div> : null}
          </>
        )}
        <div ref={bottomRef} />
      </div>

      <form
        className="scout-chat-input"
        onSubmit={(e) => {
          e.preventDefault();
          const text = draft.trim();
          if (!text || !threadId) return;
          setDraft("");
          void send(text);
        }}
      >
        <input
          type="text"
          placeholder={threadId ? "Message the Scout…" : "Create a thread first"}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          disabled={!threadId || streaming}
        />
        <button className="btn" type="submit" disabled={!threadId || streaming || !draft.trim()}>
          Send
        </button>
      </form>
    </div>
  );
}
```

`web/src/styles/scout.css`:

```css
.scout-hq {
  display: grid;
  grid-template-columns: minmax(280px, 380px) 1fr;
  gap: 1rem;
  height: calc(100vh - 120px);
}

.mission-board {
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.scout-chat {
  display: flex;
  flex-direction: column;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  overflow: hidden;
}

.scout-chat-threads {
  display: flex;
  gap: 0.5rem;
  padding: 0.6rem;
  border-bottom: 1px solid var(--border);
  align-items: center;
  flex-wrap: wrap;
}

.thread-pill {
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid var(--border);
  color: var(--text);
  border-radius: 999px;
  padding: 0.25rem 0.6rem;
  font: inherit;
  font-size: 0.8rem;
  cursor: pointer;
}

.thread-pill.active {
  background: linear-gradient(135deg, rgba(124, 58, 237, 0.4), rgba(217, 70, 239, 0.4));
}

.scout-chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: 1rem;
  display: flex;
  flex-direction: column;
  gap: 0.6rem;
}

.chat-bubble {
  max-width: 78%;
  padding: 0.6rem 0.8rem;
  border-radius: var(--radius);
  white-space: pre-wrap;
}

.chat-bubble.user {
  align-self: flex-end;
  background: var(--gradient);
  color: #fff;
}

.chat-bubble.assistant {
  align-self: flex-start;
  background: rgba(255, 255, 255, 0.06);
}

.tool-card {
  align-self: stretch;
  border: 1px solid var(--border);
  border-left: 3px solid var(--cyan);
  border-radius: var(--radius);
  padding: 0.6rem 0.8rem;
  background: rgba(34, 211, 238, 0.05);
}

.tool-card-error {
  border-left-color: var(--danger);
}

.tool-card-title {
  font-weight: 700;
  font-size: 0.85rem;
  color: var(--cyan);
  margin-bottom: 0.4rem;
}

.tool-card pre {
  margin: 0.3rem 0;
  font-size: 0.78rem;
  color: var(--muted);
  overflow-x: auto;
}

.tool-card-error-text { color: var(--danger); font-weight: 600; margin: 0.2rem 0; }

.scout-chat-input {
  display: flex;
  gap: 0.5rem;
  padding: 0.6rem;
  border-top: 1px solid var(--border);
}

.scout-chat-input input { flex: 1; }
```

`web/src/pages/ScoutHQ.tsx`:

```tsx
import { MissionBoard } from "../components/MissionBoard";
import { ScoutChat } from "../components/ScoutChat";

export default function ScoutHQ() {
  return (
    <div className="scout-hq">
      <MissionBoard />
      <ScoutChat />
    </div>
  );
}
```

Add `@import "./scout.css";` to `web/src/styles/global.css` (replace the existing import line):

```css
@import "./tokens.css";
@import "./layout.css";
@import "./components.css";
@import "./scout.css";
```

- [ ] **Step 4: Run tests to verify they pass**

Run (workdir `web`): `npm test`
Expected: 4 new tests PASSED (useScoutChat 2, ToolActivityCard 2).

- [ ] **Step 5: Verify build passes**

Run (workdir `web`): `npm run build`
Expected: no TS errors.

- [ ] **Step 6: Verify SSE end-to-end against the running backend**

Run (workdir `web`): `npm run dev` (background). Then:
1. `Invoke-RestMethod -Method Post http://localhost:5173/api/scout/threads -ContentType "application/json" -Body '{"title":"ui smoke"}'` → capture `id`.
2. `Invoke-WebRequest http://localhost:5173/api/scout/threads/<id>/messages` → returns `[]`.
3. Open `http://localhost:5173/scout-hq` in a browser and send a message — the streamed response renders in the chat; after `done`, tool cards appear if tools ran.
Expected: chat page loads, threads list works, message POST streams `start → delta* → done` frames through the proxy. Stop dev server.

- [ ] **Step 7: Commit**

```bash
git add web
git commit -m "feat: scout HQ — mission board + SSE chat with tool activity cards"
```

---

### Task 9: Build, prod nginx service, docs

**Files:**
- Create: `web/Dockerfile`
- Create: `web/nginx.conf`
- Create: `web/.dockerignore`
- Modify: `docker-compose.yml` (add `web` service)
- Modify: `docs/ops/START_DEPARTMENT.md` (add SPA + Scout HQ UI rows)
- Verify: full frontend test suite + build; full backend pytest suite unchanged.

**Interfaces:**
- Consumes: everything from Tasks 1-8.
- Produces: a deployable `web` service on port `3000:80` that serves the SPA and proxies `/api` → `app:8000` (SSE-safe: `proxy_buffering off`).

- [ ] **Step 1: Create the deployment files**

`web/Dockerfile`:

```dockerfile
FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
```

`web/nginx.conf`:

```nginx
server {
  listen 80;
  server_name _;
  root /usr/share/nginx/html;
  index index.html;

  location /api/ {
    proxy_pass http://app:8000;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_read_timeout 120s;
    proxy_buffering off;
  }

  location /health {
    proxy_pass http://app:8000;
  }

  location / {
    try_files $uri $uri/ /index.html;
  }
}
```

`web/.dockerignore`:

```
node_modules
dist
```

- [ ] **Step 2: Add the `web` service to `docker-compose.yml`**

Append to the `services:` block (after the `app` service, before `wordpress`):

```yaml
  web:
    build: ./web
    container_name: marketing_web
    ports:
      - "3000:80"
    depends_on:
      - app
```

- [ ] **Step 3: Update ops docs**

In `docs/ops/START_DEPARTMENT.md`, update the "Open CRM" table — add the SPA and Scout HQ rows:

```
| SPA (React) | http://localhost:3000 |
| Scout HQ (chat + missions) | http://localhost:3000/scout-hq |
```

And add a note under the Scout HQ API section:

```
The React SPA is served by the `web` container on port 3000 (dev: `cd web && npm run dev`, proxying `/api` to `localhost:8000`).
```

- [ ] **Step 4: Verify frontend**

Run (workdir `web`): `npm test`
Expected: ALL frontend tests PASS.

Run (workdir `web`): `npm run build`
Expected: no errors; `dist/` emitted.

- [ ] **Step 5: Verify backend regression**

Run (repo root): `python -m pytest tests/ -q --no-header`
Expected: `50 passed, 6 skipped` (same as baseline; no new failures). The Python suite is untouched by this plan.

- [ ] **Step 6: Commit**

```bash
git add web docker-compose.yml docs/ops/START_DEPARTMENT.md
git commit -m "feat: web service (nginx) + SPA deployment docs"
```

---

## Self-Review Notes

- **Spec coverage:** §4 data model consumed via API (no schema work — backend complete). §5 all endpoints consumed: `/api/pipeline-runs` (MissionBoard, Dashboard), `/api/stats` (Dashboard, LeadsDetail), `/api/scout/status` (Topbar, AgentsDetail), `/api/scout/threads` + `/messages` + SSE POST (ScoutChat). §6 SSE contract: `start/delta/done/error` parsed by `sse.ts`; tool cards from persisted `role="tool"` messages refetched after `done` (per SDD decision). §7 design tokens + layout + pages implemented. §8 `web` nginx service + compose wiring. §10 risks: SSE buffering handled via `proxy_buffering off`; idle connection kept alive by backend streaming.
- **Out of scope:** mounting legacy Jinja UI at `/legacy` and deleting it (rollout phase 5, a backend change requiring double-verify against the SPA) — not in this plan. No Python files modified except `docker-compose.yml`.
- **Type consistency:** `ScoutMessage.role` is `"user" | "assistant" | "tool"` everywhere (types.ts, ScoutChat, ToolActivityCard). `streamScoutTurn` handlers signature matches `useScoutChat` usage. `fetchRecentMissions` (Task 4) and `fetchMissions` (Task 8) both return `PipelineRun[]` — Dashboard and MissionBoard render the same shape.
- **Known limitation:** Topbar "API status dot" reflects `/api/scout/status` reachability (no dedicated LLM-status endpoint exists); documented in Task 3.
