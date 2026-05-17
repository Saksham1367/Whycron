import type { CSSProperties, ReactNode } from "react";

interface Props {
  variant?: "ai" | "critical";
  children: ReactNode;
  style?: CSSProperties;
  className?: string;
}

export function SurfaceCard({
  variant,
  children,
  style,
  className = "",
}: Props) {
  return (
    <section
      className={`wc-card ${variant ? `wc-card--${variant}` : ""} ${className}`}
      style={style}
    >
      {children}
    </section>
  );
}
