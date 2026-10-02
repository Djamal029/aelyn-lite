import { useEffect, useState } from "react";
import { CameraTile } from "../components/cameras/CameraTile";
import { cameras, securityEvents } from "../mocks";
import styles from "./Cameras.module.css";

// Matches the overlay's fade-out animation duration below, so the
// overlay actually unmounts only once that animation has had time to
// play instead of the whole thing just vanishing mid-fade.
const OVERLAY_CLOSE_MS = 160;

function eventsFor(cameraName: string) {
  return securityEvents
    .filter((e) => e.camera === cameraName)
    .sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime())
    .slice(0, 6);
}

export function Cameras() {
  const [expanded, setExpanded] = useState<string | null>(null);
  const [closing, setClosing] = useState(false);
  const expandedCamera = cameras.find((c) => c.id === expanded) || null;

  const closeOverlay = () => {
    setClosing(true);
    window.setTimeout(() => {
      setExpanded(null);
      setClosing(false);
    }, OVERLAY_CLOSE_MS);
  };

  useEffect(() => {
    if (!expanded) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") closeOverlay();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [expanded]);

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <div className={styles.title}>Cameras</div>
        <div className={styles.subtitle}>
          {cameras.length} caméras déclarées · pipeline de détection exécuté depuis AELYN Core en attendant le
          déploiement du Raspberry Pi Vision · test local avec une vraie webcam ou un téléphone via Iriun Webcam
        </div>
      </div>

      <div className={styles.grid}>
        {cameras.map((cam) => (
          <CameraTile
            key={cam.id}
            camera={cam}
            onExpand={() => setExpanded(cam.id)}
            recentEvents={eventsFor(cam.name)}
            enableLiveFeed={expanded !== cam.id}
          />
        ))}
      </div>

      {expandedCamera ? (
        <div
          className={[styles.overlay, closing ? styles.overlayClosing : ""].join(" ")}
          onClick={closeOverlay}
        >
          <div
            className={[styles.overlayInner, closing ? styles.overlayInnerClosing : ""].join(" ")}
            onClick={(e) => e.stopPropagation()}
          >
            <div className={styles.overlayHead}>
              <span className={styles.overlayTitle}>Caméra {expandedCamera.name} : vue plein écran</span>
              <button className={styles.closeButton} onClick={closeOverlay} type="button">
                Fermer (Échap)
              </button>
            </div>
            <CameraTile camera={expandedCamera} recentEvents={eventsFor(expandedCamera.name)} enableLiveFeed />
          </div>
        </div>
      ) : null}
    </div>
  );
}
