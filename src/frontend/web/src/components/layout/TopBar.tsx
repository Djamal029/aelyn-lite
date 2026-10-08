import { useEffect, useState } from "react";
import { formatClock } from "../../lib/time";
import { nodes } from "../../mocks";
import { StatusDot } from "../ui/StatusDot";
import styles from "./TopBar.module.css";

const core = nodes.find((n) => n.id === "core")!;

interface TopBarProps {
  /** Only rendered as a visible button below the tablet breakpoint (see
   * TopBar.module.css's `.menuButton`): opens the Sidebar drawer on
   * narrow screens, where it's no longer permanently docked. */
  onMenuClick?: () => void;
}

export function TopBar({ onMenuClick }: TopBarProps) {
  const [now, setNow] = useState(new Date());

  useEffect(() => {
    const id = window.setInterval(() => setNow(new Date()), 1000);
    return () => window.clearInterval(id);
  }, []);

  return (
    <header className={styles.bar}>
      <div className={styles.left}>
        <button className={styles.menuButton} onClick={onMenuClick} type="button" aria-label="Ouvrir le menu">
          <span className={styles.menuIcon}>
            <span />
            <span />
            <span />
          </span>
        </button>
        <span className={styles.brand}>AELYN</span>
        <span className={styles.status}>
          <StatusDot kind={core.state === "operational" ? "operational" : "offline"} />
          {core.state === "operational" ? "En ligne" : "Hors ligne"}
        </span>
      </div>
      <div className={styles.right}>
        <span className={styles.tailscale}>
          <StatusDot kind={core.tailscale === "connected" ? "connected" : "disconnected"} />
          Tailscale
        </span>
        <span className={styles.clock}>{formatClock(now)}</span>
      </div>
    </header>
  );
}
