import type { CSSProperties, ReactNode } from "react";

interface Props {
  children: ReactNode;
  tone?: string;
  style?: CSSProperties;
}

export function Eyebrow({ children, tone, style }: Props) {
  return (
    <span className="wc-eyebrow" style={{ color: tone, ...style }}>
      {children}
    </span>
  );
}
