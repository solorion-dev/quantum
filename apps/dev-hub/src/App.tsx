import { useCallback, useEffect, useRef, useState } from "react";

type Health = "up" | "down" | "degraded" | "unknown";

interface Service {
  name: string;
  kind: string;
  status: Health;
  latency_ms: number | null;
  detail: string;
}

interface ServiceGroup {
  name: string;
  services: Service[];
}

interface Bootcheck {
  verdict: string | null;
  fails: number | null;
  warns: number | null;
  at: string | null;
  headline: string | null;
  ok_count: number;
  fail_count: number;
  lines: string[];
}

interface Disk {
  mount: string;
  total_bytes: number | null;
  used_bytes: number | null;
  free_bytes: number | null;
  used_pct: number | null;
  error?: string;
}

interface FleetStatus {
  generated_at: string;
  sources: Record<string, string>;
  bootcheck: Bootcheck;
  fleet: { groups: ServiceGroup[]; totals: Record<Health, number> };
  host: {
    hostname: string;
    uptime_seconds: number;
    load: number[];
    memory: { total_bytes: number; available_bytes: number; used_pct: number };
    disks: Disk[];
  };
  tracker: { total: number; by_status: Record<string, number>; error?: string };
}

interface Session {
  login: string;
  name: string | null;
  source: string;
  peer: string;
}

const NAV = [
  { label: "Overview", active: true, stub: false },
  { label: "Logs", active: false, stub: true },
  { label: "Tailscale", active: false, stub: true },
  { label: "Home Assistant", active: false, stub: true },
  { label: "Cron", active: false, stub: true },
];

function gb(bytes: number | null): string {
  if (bytes === null || bytes === undefined) return "—";
  return `${(bytes / 1024 ** 3).toFixed(1)} GB`;
}

function uptimeText(seconds: number): string {
  const d = Math.floor(seconds / 86400);
  const h = Math.floor((seconds % 86400) / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  if (d > 0) return `${d}d ${h}h ${m}m`;
  if (h > 0) return `${h}h ${m}m`;
  return `${m}m`;
}

function chip(status: Health) {
  const styles: Record<Health, string> = {
    up: "bg-emerald-50 text-emerald-800 border-emerald-200",
    down: "bg-red-50 text-red-800 border-red-200",
    degraded: "bg-amber-50 text-amber-800 border-amber-200",
    unknown: "bg-neutral-100 text-neutral-600 border-neutral-200",
  };
  const labels: Record<Health, string> = {
    up: "Up",
    down: "Down",
    degraded: "Degraded",
    unknown: "Unknown",
  };
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-medium ${styles[status]}`}
    >
      {labels[status]}
    </span>
  );
}

function Bar({ pct }: { pct: number | null }) {
  const v = pct ?? 0;
  const color = v >= 95 ? "bg-red-500" : v >= 85 ? "bg-amber-500" : "bg-neutral-800";
  return (
    <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-neutral-100">
      <div className={`h-full ${color}`} style={{ width: `${Math.min(100, v)}%` }} />
    </div>
  );
}

export function App() {
  const [session, setSession] = useState<Session | null>(null);
  const [data, setData] = useState<FleetStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const timer = useRef<number | null>(null);

  const load = useCallback(async () => {
    try {
      const sRes = await fetch("/api/session");
      if (sRes.status === 401) {
        setError("unauthorized — this tailnet identity is not on the Developer Hub allowlist");
        return;
      }
      if (sRes.ok) setSession((await sRes.json()) as Session);
      const res = await fetch("/api/fleet/status");
      if (res.status === 401) {
        setError("unauthorized — this tailnet identity is not on the Developer Hub allowlist");
        return;
      }
      if (!res.ok) throw new Error(`fleet status HTTP ${res.status}`);
      setData((await res.json()) as FleetStatus);
      setError(null);
      setLastUpdated(new Date());
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, []);

  useEffect(() => {
    void load();
    timer.current = window.setInterval(() => void load(), 15000);
    return () => {
      if (timer.current) window.clearInterval(timer.current);
    };
  }, [load]);

  const verdict = data?.bootcheck.verdict ?? null;
  const banner =
    verdict === "HEALTHY"
      ? "border-emerald-200 bg-emerald-50 text-emerald-900"
      : verdict
        ? "border-amber-200 bg-amber-50 text-amber-900"
        : "border-neutral-200 bg-white text-neutral-700";
  const serviceCount = data
    ? data.fleet.groups.reduce((n, g) => n + g.services.length, 0)
    : 0;

  return (
    <div className="min-h-screen bg-[#fafafa] text-neutral-900">
      <div className="mx-auto flex max-w-7xl flex-col gap-0 px-4 sm:px-6 lg:flex-row">
        {/* Nav */}
        <aside className="shrink-0 border-b border-neutral-200 py-4 lg:min-h-screen lg:w-56 lg:border-b-0 lg:border-r lg:py-6 lg:pr-6">
          <div className="flex items-center gap-2">
            <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-[#7c5cff] text-sm font-bold text-white">
              D
            </span>
            <div>
              <p className="text-sm font-semibold leading-tight">Developer Hub</p>
              <p className="text-[11px] leading-tight text-neutral-500">dev.dsect.net · slice 1</p>
            </div>
          </div>
          <nav className="mt-4 flex gap-1 overflow-x-auto lg:mt-6 lg:flex-col" aria-label="Sections">
            {NAV.map((item) =>
              item.stub ? (
                <span
                  key={item.label}
                  aria-disabled="true"
                  className="flex cursor-not-allowed items-center justify-between whitespace-nowrap rounded-md px-3 py-2 text-sm text-neutral-400"
                >
                  {item.label}
                  <span className="ml-2 rounded-full border border-neutral-200 px-1.5 py-0.5 text-[10px] text-neutral-400">
                    next slice
                  </span>
                </span>
              ) : (
                <span
                  key={item.label}
                  aria-current="page"
                  className="whitespace-nowrap rounded-md bg-[#f2efff] px-3 py-2 text-sm font-medium text-[#7c5cff]"
                >
                  {item.label}
                </span>
              ),
            )}
          </nav>
          {session && (
            <p className="mt-4 hidden text-[11px] leading-relaxed text-neutral-500 lg:block">
              Signed in as <span className="font-medium text-neutral-700">{session.login}</span>
              <br />
              via {session.source}
            </p>
          )}
        </aside>

        {/* Main */}
        <main className="min-w-0 flex-1 py-4 lg:py-6 lg:pl-6">
          <header className="flex flex-wrap items-center justify-between gap-3">
            <h1 className="text-xl font-semibold">Overview</h1>
            <div className="flex items-center gap-3">
              <span className="text-xs text-neutral-500">
                {lastUpdated ? `Last updated ${lastUpdated.toLocaleTimeString()}` : "Loading…"}
                {" · "}auto-refresh 15s
              </span>
              <button
                type="button"
                onClick={() => void load()}
                className="rounded-md bg-black px-3 py-1.5 text-sm font-medium text-white"
              >
                Refresh
              </button>
            </div>
          </header>

          {error && (
            <div className="mt-4 rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-900" role="alert">
              {error}
            </div>
          )}

          {data && (
            <>
              {/* Bootcheck banner */}
              <section className={`mt-4 rounded-xl border p-4 ${banner}`} aria-label="Bootcheck verdict">
                <h2 className="text-sm font-semibold">
                  Bootcheck: {verdict ?? "no verdict found"}
                  {data.bootcheck.fails !== null &&
                    ` · fails ${data.bootcheck.fails} · warns ${data.bootcheck.warns ?? 0}`}
                </h2>
                <p className="mt-1 text-xs opacity-80">
                  {data.bootcheck.headline ?? "quantum-bootcheck latest summary not readable"}
                  {data.bootcheck.at ? ` · recorded ${data.bootcheck.at}` : ""}
                  {" · "}
                  {data.bootcheck.ok_count} OK / {data.bootcheck.fail_count} FAIL lines · source:{" "}
                  {data.sources.bootcheck}
                </p>
              </section>

              {/* Fleet services */}
              <section className="mt-6" aria-label="Fleet services">
                <h2 className="text-base font-semibold">
                  Fleet services{" "}
                  <span className="text-sm font-normal text-neutral-500">
                    ({serviceCount} shown · {data.fleet.totals.up ?? 0} up,{" "}
                    {data.fleet.totals.down ?? 0} down · source: {data.sources.fleet})
                  </span>
                </h2>
                <div className="mt-3 grid grid-cols-1 gap-4 xl:grid-cols-3">
                  {data.fleet.groups.map((group) => (
                    <div key={group.name} className="rounded-xl border border-neutral-200 bg-white p-4">
                      <h3 className="text-sm font-semibold">{group.name}</h3>
                      <ul className="mt-2 divide-y divide-neutral-100">
                        {group.services.map((svc) => (
                          <li
                            key={`${group.name}-${svc.name}`}
                            data-service-row="true"
                            className="flex items-center justify-between gap-2 py-2"
                          >
                            <div className="min-w-0">
                              <p className="truncate text-sm font-medium">{svc.name}</p>
                              <p className="truncate text-[11px] text-neutral-500">{svc.detail}</p>
                            </div>
                            <div className="flex shrink-0 items-center gap-2">
                              {svc.latency_ms !== null && (
                                <span className="text-[11px] tabular-nums text-neutral-500">
                                  {svc.latency_ms} ms
                                </span>
                              )}
                              {chip(svc.status)}
                            </div>
                          </li>
                        ))}
                        {group.services.length === 0 && (
                          <li className="py-2 text-sm text-neutral-500">No services reported.</li>
                        )}
                      </ul>
                    </div>
                  ))}
                </div>
              </section>

              {/* Host */}
              <section className="mt-6" aria-label="Host">
                <h2 className="text-base font-semibold">
                  Host · {data.host.hostname}{" "}
                  <span className="text-sm font-normal text-neutral-500">(source: {data.sources.host})</span>
                </h2>
                <div className="mt-3 grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
                  <div className="rounded-xl border border-neutral-200 bg-white p-4">
                    <h3 className="text-sm font-semibold">Uptime</h3>
                    <p className="mt-1 text-2xl font-semibold">{uptimeText(data.host.uptime_seconds)}</p>
                    <p className="text-xs text-neutral-500">since last boot</p>
                  </div>
                  <div className="rounded-xl border border-neutral-200 bg-white p-4">
                    <h3 className="text-sm font-semibold">Load average</h3>
                    <p className="mt-1 text-2xl font-semibold tabular-nums">
                      {data.host.load.map((n) => n.toFixed(2)).join(" · ")}
                    </p>
                    <p className="text-xs text-neutral-500">1m · 5m · 15m</p>
                  </div>
                  <div className="rounded-xl border border-neutral-200 bg-white p-4">
                    <h3 className="text-sm font-semibold">Memory</h3>
                    <p className="mt-1 text-2xl font-semibold">{data.host.memory.used_pct}% used</p>
                    <p className="text-xs text-neutral-500">
                      {gb(data.host.memory.total_bytes - data.host.memory.available_bytes)} of{" "}
                      {gb(data.host.memory.total_bytes)}
                    </p>
                    <Bar pct={data.host.memory.used_pct} />
                  </div>
                  <div className="rounded-xl border border-neutral-200 bg-white p-4">
                    <h3 className="text-sm font-semibold">Tracker</h3>
                    <p className="mt-1 text-2xl font-semibold">{data.tracker.total} items</p>
                    <p className="text-xs text-neutral-500">source: {data.sources.tracker}</p>
                  </div>
                </div>

                <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-3">
                  {data.host.disks.map((disk) => (
                    <div key={disk.mount} className="rounded-xl border border-neutral-200 bg-white p-4">
                      <h3 className="text-sm font-semibold">Disk {disk.mount}</h3>
                      {disk.error ? (
                        <p className="mt-1 text-sm text-red-700">{disk.error}</p>
                      ) : (
                        <>
                          <p className="mt-1 text-lg font-semibold">{disk.used_pct}% used</p>
                          <p className="text-xs text-neutral-500">
                            {gb(disk.used_bytes)} of {gb(disk.total_bytes)} · {gb(disk.free_bytes)} free
                          </p>
                          <Bar pct={disk.used_pct} />
                        </>
                      )}
                    </div>
                  ))}
                </div>
              </section>

              {/* Tracker counts */}
              <section className="mt-6" aria-label="Tracker counts">
                <h2 className="text-base font-semibold">Tracker counts by status</h2>
                <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4 xl:grid-cols-7">
                  {Object.entries(data.tracker.by_status).map(([status, count]) => (
                    <div key={status} className="rounded-xl border border-neutral-200 bg-white p-3">
                      <p className="text-[11px] font-medium uppercase tracking-wide text-neutral-500">{status}</p>
                      <p className="mt-1 text-xl font-semibold tabular-nums">{count}</p>
                    </div>
                  ))}
                </div>
                {data.tracker.error && (
                  <p className="mt-2 text-sm text-red-700">Tracker read failed: {data.tracker.error}</p>
                )}
              </section>

              <footer className="mt-8 border-t border-neutral-200 pt-3 text-[11px] text-neutral-500">
                Read-only slice 1. Data generated {new Date(data.generated_at).toLocaleString()} on the box.
                Mutating actions are not built — they stay gated on an explicit decision.
              </footer>
            </>
          )}

          {!data && !error && <p className="mt-6 text-sm text-neutral-500">Loading live fleet status…</p>}
        </main>
      </div>
    </div>
  );
}
