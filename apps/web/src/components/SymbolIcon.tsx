import type { CSSProperties } from "react";

interface Props {
  name: string;
  filled?: boolean;
  size?: string | number;
  color?: string;
  style?: CSSProperties;
}

export function SymbolIcon({
  name,
  filled = false,
  size,
  color,
  style,
}: Props) {
  return (
    <span
      className="wc-icon"
      style={{
        fontFamily: "'Material Symbols Outlined'",
        fontVariationSettings: `'FILL' ${filled ? 1 : 0}, 'wght' 500, 'opsz' 20`,
        fontFeatureSettings: "'liga'",
        WebkitFontFeatureSettings: "'liga'",
        fontStyle: "normal",
        lineHeight: 1,
        letterSpacing: "normal",
        textTransform: "none",
        whiteSpace: "nowrap",
        direction: "ltr",
        fontSize: size ?? "1.25rem",
        color,
        ...style,
      }}
    >
      {name}
    </span>
  );
}
