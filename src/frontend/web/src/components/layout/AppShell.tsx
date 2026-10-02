import { useEffect, useState } from "react";
import { Outlet, useLocation } from "react-router-dom";
import { TopBar } from "./TopBar";
import { Sidebar } from "./Sidebar";
import styles from "./AppShell.module.css";

/** Owns the Sidebar-as-drawer state for narrow screens (the sidebar is
 * permanently docked above the tablet breakpoint, where this is simply
 * never opened/rendered as a backdrop; see Sidebar.module.css). */
export function AppShell() {
  const location = useLocation();
  const [navOpen, setNavOpen] = useState(false);

  // Never leave the drawer open over a page the user already navigated
  // to, and never leave it open if the window gets resized back to desktop.
  useEffect(() => setNavOpen(false), [location.pathname]);

  useEffect(() => {
    if (!navOpen) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") setNavOpen(false);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [navOpen]);

  return (
    <div className={styles.shell}>
      <TopBar onMenuClick={() => setNavOpen((v) => !v)} />
      <div className={styles.body}>
        <Sidebar open={navOpen} onNavigate={() => setNavOpen(false)} />
        {navOpen ? <div className={styles.backdrop} onClick={() => setNavOpen(false)} /> : null}
        <main className={styles.content}>
          {/* Keyed by path so each page section gets its own mount and
           * plays its own subtle enter animation instead of content just
           * snapping into place on navigation (App.tsx already renders a
           * different component per route, so this key doesn't change
           * what already remounts, it just gives that remount somewhere
           * to hang a transition). */}
          <div key={location.pathname} className={styles.pageEnter}>
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
}
