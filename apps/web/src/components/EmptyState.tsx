import type { ReactNode } from "react";
import { SurfaceCard } from "./SurfaceCard";
import { SymbolIcon } from "./SymbolIcon";

interface Props {
  icon?: string;
  title: string;
  description?: string;
  action?: ReactNode;
}

export function EmptyState({ icon = "schedule_send", title, description, action }: Props) {
  return (
    <SurfaceCard>
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          gap: ".8rem",
          padding: "2rem 1rem",
          textAlign: "center",
        }}
      >
        <SymbolIcon
          name={icon}
          size="2.4rem"
          color="var(--wc-text-muted)"
        />
        <strong style={{ color: "var(--wc-text)", fontSize: "1.05rem" }}>
          {title}
        </strong>
        {description && (
          <p
            style={{
              color: "var(--wc-text-soft)",
              margin: 0,
              maxWidth: 380,
              fontSize: ".88rem",
            }}
          >
            {description}
          </p>
        )}
        {action}
      </div>
    </SurfaceCard>
  );
}
