/**
 * Tiny formatting helpers shared by screens. Avoids pulling in a date lib.
 */

export function fmtRelative(iso: string | null | undefined): string {
  if (!iso) return "—";
  const when = new Date(iso).getTime();
  const diffSec = Math.round((Date.now() - when) / 1000);
  if (Number.isNaN(diffSec)) return iso;
  if (diffSec < 60) return `${diffSec}s ago`;
  if (diffSec < 3600) return `${Math.round(diffSec / 60)}m ago`;
  if (diffSec < 86_400) return `${Math.round(diffSec / 3600)}h ago`;
  return `${Math.round(diffSec / 86_400)}d ago`;
}

export function fmtDuration(ms: number | null | undefined): string {
  if (ms == null) return "—";
  if (ms < 1000) return `${ms} ms`;
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)}s`;
  return `${(ms / 60_000).toFixed(1)} min`;
}

export function fmtAbsolute(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString();
}

export function fmtCostMicroUSD(micro: number | null | undefined): string {
  if (micro == null) return "—";
  if (micro === 0) return "free (cache hit)";
  return `$${(micro / 1_000_000).toFixed(4)}`;
}
