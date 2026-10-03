import { NavLink } from "react-router-dom";
import { cameras, securityEvents } from "../../mocks";
import { StatusDot } from "../ui/StatusDot";
import { LITE_MODE } from "../../lib/liteMode";
import styles from "./Sidebar.module.css";

const ALL_NAV_ITEMS = [
  { path: "/", label: "Overview" },
  { path: "/cameras", label: "Cameras" },
  { path: "/security", label: "Security" },
  { path: "/assistant", label: "Assistant" },
  { path: "/data", label: "Data" },
  { path: "/activity", label: "Activity" },
  { path: "/system", label: "System" },
  { path: "/settings", label: "Settings" },
] as const;

// Pas de matériel caméra en version lite : lien retiré plutôt que menant
// vers une page vide/webcam de démo.
const NAV_ITEMS = LITE_MODE ? ALL_NAV_ITEMS.filter((item) => item.path !== "/cameras") : ALL_NAV_ITEMS;

const recentCritical = securityEvents.filter((e) => e.severity !== "info").length;
const disconnectedCameras = cameras.filter((c) => c.connection !== "connected").length;

interface SidebarProps {
  /** Only meaningful below the tablet breakpoint, where Sidebar.module.css
   * turns this into an off-canvas drawer instead of a permanently docked
   * column; ignored (no visual effect) above it. */
  open?: boolean;
  /** Fired when a nav item is actually chosen, so the drawer closes
   * itself after navigating on narrow screens instead of staying open
   * over the page it just navigated to. */
  onNavigate?: () => void;
}

export function Sidebar({ open, onNavigate }: SidebarProps) {
  return (
    <nav className={[styles.nav, open ? styles.navOpen : ""].join(" ")}>
      {NAV_ITEMS.map((item) => (
        <NavLink
          key={item.path}
          to={item.path}
          end={item.path === "/"}
          onClick={onNavigate}
          className={({ isActive }) => [styles.item, isActive ? styles.itemActive : ""].join(" ")}
        >
          <span className={styles.label}>{item.label}</span>
          {item.path === "/security" && recentCritical > 0 ? (
            <span className={styles.indicator}>
              <StatusDot kind="warning" />
              {recentCritical}
            </span>
          ) : null}
          {item.path === "/cameras" && disconnectedCameras > 0 ? (
            <span className={styles.indicator}>
              <StatusDot kind="offline" />
              {disconnectedCameras}
            </span>
          ) : null}
        </NavLink>
      ))}
    </nav>
  );
}
