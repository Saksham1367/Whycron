import { SurfaceCard } from "./SurfaceCard";
import { SymbolIcon } from "./SymbolIcon";

export interface Metric {
  label: string;
  value: string | number;
  help?: string;
  icon: string;
  tone: "healthy" | "late" | "failing" | "paused";
}

const TONE_COLORS: Record<Metric["tone"], string> = {
  healthy: "var(--wc-success)",
  late: "var(--wc-warning)",
  failing: "var(--wc-danger)",
  paused: "var(--wc-paused)",
};

export function MetricCard({ metric }: { metric: Metric }) {
  const color = TONE_COLORS[metric.tone];
  return (
    <SurfaceCard>
      <div className="wc-metric">
        <div className="wc-metric__head">
          <span className="wc-metric__label">{metric.label}</span>
          <SymbolIcon name={metric.icon} color={color} size="1.4rem" />
        </div>
        <strong className="wc-metric__value" style={{ color }}>
          {metric.value}
        </strong>
        {metric.help && (
          <span className="wc-metric__help">{metric.help}</span>
        )}
      </div>
    </SurfaceCard>
  );
}
