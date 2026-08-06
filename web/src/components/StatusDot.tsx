export function StatusDot({ ok }: { ok: boolean }) {
  return <span className={`dot ${ok ? "ok" : "bad"}`} title={ok ? "API reachable" : "API unreachable"} />;
}
