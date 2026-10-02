import type { SecurityEvent } from "../../types";
import { relativeFromNow } from "../../lib/time";
import { SECURITY_TYPE_SHORT } from "../../lib/securityLabels";
import styles from "./DetectionFilmstrip.module.css";

interface DetectionFilmstripProps {
  events: SecurityEvent[];
}

/** Frigate/UniFi Protect's recent-detection filmstrip: a strip of the
 * last crops the vision pipeline pulled for this camera, most recent
 * first. There is no real frame grabber wired up yet (see CameraTile's
 * "EN ATTENTE DE FLUX" placeholder for the same honesty rule), so each
 * frame renders the same explicit no-crop-available placeholder rather
 * than a fabricated photo; only the border color communicates real
 * severity, borrowed straight from the security-agent event. */
export function DetectionFilmstrip({ events }: DetectionFilmstripProps) {
  if (events.length === 0) {
    return (
      <div className={styles.wrap}>
        <div className={styles.empty}>Aucune détection récente</div>
      </div>
    );
  }

  return (
    <div className={styles.wrap}>
      <div className={styles.strip}>
        {events.map((e) => (
          <div key={e.id} className={[styles.frame, styles[e.severity]].join(" ")} title={e.detail}>
            <div className={styles.crop} />
            <div className={styles.caption}>
              <span className={styles.type}>{SECURITY_TYPE_SHORT[e.type]}</span>
              <span className={styles.time}>{relativeFromNow(e.timestamp)}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
