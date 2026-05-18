import { NavLink } from "react-router-dom";
import { SymbolIcon } from "./SymbolIcon";

interface NavItem {
  id: string;
  label: string;
  icon: string;
  path: string;
}

const WORKSPACE_NAV: NavItem[] = [
  { id: "overview", label: "Overview", icon: "dashboard", path: "/overview" },
  { id: "monitors", label: "Monitors", icon: "timer", path: "/monitors" },
  { id: "failures", label: "Failures", icon: "error", path: "/failures" },
  {
    id: "channels",
    label: "Notifications",
    icon: "notifications",
    path: "/channels",
  },
];

const ACCOUNT_NAV: NavItem[] = [
  { id: "account", label: "Account", icon: "person", path: "/account" },
  { id: "api-keys", label: "API keys", icon: "vpn_key", path: "/api-keys" },
  {
    id: "status-page",
    label: "Status page",
    icon: "public",
    path: "/status-page",
  },
];

export function Sidebar({ orgName }: { orgName: string }) {
  return (
    <aside className="wc-sidebar">
      <div className="wc-sidebar__brand">
        <strong>Whycron</strong>
      </div>
      <div className="wc-sidebar__sub">{orgName}</div>
      <div className="wc-sidebar__heading">Workspace</div>
      <div className="wc-sidebar__group">
        {WORKSPACE_NAV.map((n) => (
          <SidebarItem key={n.id} item={n} />
        ))}
      </div>
      <div className="wc-sidebar__heading">Account</div>
      <div className="wc-sidebar__group">
        {ACCOUNT_NAV.map((n) => (
          <SidebarItem key={n.id} item={n} />
        ))}
      </div>
      <div className="wc-sidebar__foot">
        <span style={{ fontSize: ".72rem" }}>
          v2026.05 · Status: operational
        </span>
      </div>
    </aside>
  );
}

function SidebarItem({ item }: { item: NavItem }) {
  return (
    <NavLink
      to={item.path}
      end={item.path === "/overview"}
      className={({ isActive }) =>
        `wc-nav-item ${isActive ? "wc-nav-item--active" : ""}`
      }
    >
      {({ isActive }) => (
        <>
          <SymbolIcon name={item.icon} filled={isActive} />
          <span>{item.label}</span>
        </>
      )}
    </NavLink>
  );
}
