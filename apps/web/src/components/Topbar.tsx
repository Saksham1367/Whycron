import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { Button } from "./Button";
import { SymbolIcon } from "./SymbolIcon";

export interface Crumb {
  label: string;
  to?: string;
  last?: boolean;
}

interface Props {
  crumbs: Crumb[];
  onCreate?: () => void;
  onSignOut?: () => void;
  rightAside?: ReactNode;
}

export function Topbar({ crumbs, onCreate, onSignOut, rightAside }: Props) {
  return (
    <div className="wc-topbar">
      <div className="wc-topbar__crumb">
        {crumbs.map((c, i) => (
          <span
            key={i}
            style={{ display: "inline-flex", alignItems: "center", gap: ".55rem" }}
          >
            {i > 0 && (
              <SymbolIcon
                name="chevron_right"
                size="1rem"
                color="var(--wc-text-muted)"
              />
            )}
            {c.last || !c.to ? (
              <strong>{c.label}</strong>
            ) : (
              <Link to={c.to}>{c.label}</Link>
            )}
          </span>
        ))}
      </div>
      <div className="wc-topbar__spacer" />
      {rightAside}
      {onCreate && (
        <Button variant="primary" icon="add" onClick={onCreate}>
          New monitor
        </Button>
      )}
      {onSignOut && (
        <Button variant="ghost" icon="logout" onClick={onSignOut}>
          Sign out
        </Button>
      )}
    </div>
  );
}
