import { useState } from "react";
import type { Camera, SecurityEvent } from "../../types";
import { relativeFromNow } from "../../lib/time";
import { useLiveCamera } from "../../lib/useLiveCamera";
import { DetectionFilmstrip } from "./DetectionFilmstrip";
import styles from "./CameraTile.module.css";

interface CameraTileProps {
  camera: Camera;
  onExpand?: () => void;
  /** Recent security-agent events for this camera, most recent first:
   * rendered as a Frigate-style filmstrip below the metadata row. Omit
   * to hide the filmstrip entirely (e.g. dense Overview grids). */
  recentEvents?: SecurityEvent[];
  /** Turns on real `getUserMedia` wiring for local testing (laptop
   * webcam, or a phone via Iriun Webcam showing up as a normal video
   * input): a device picker appears and, once a device is chosen, a
   * genuine live `<video>` replaces the placeholder. Off by default so
   * dense grids (Overview) stay pure display. */
  enableLiveFeed?: boolean;
}

const LIVE_STATUS_LABEL: Record<string, string> = {
  unsupported: "CAMÉRA RÉELLE NON PRISE EN CHARGE",
  idle: "CAMÉRA NON ACTIVÉE",
  requesting: "DEMANDE D'ACCÈS…",
  denied: "ACCÈS CAMÉRA REFUSÉ",
  "no-device": "AUCUN PÉRIPHÉRIQUE TROUVÉ",
  error: "ERREUR CAMÉRA",
};

/** A camera panel structured to receive a real video element (the frame
 * is the exact spot a stream mounts); the diagonal fill and "EN
 * ATTENTE DE FLUX" label are an explicit "no stream" state, not a fake
 * live picture, used for the dense/display-only tiles (Overview) and as
 * the fallback here whenever the real feed (see `enableLiveFeed`,
 * lib/useLiveCamera.ts) isn't live. Metadata (fps, resolution, latency,
 * last detection, recording) is real per-camera data, laid out like
 * Frigate/UniFi Protect's camera tiles. */
export function CameraTile({ camera, onExpand, recentEvents, enableLiveFeed }: CameraTileProps) {
  const isConnected = camera.connection === "connected";
  const [videoNode, setVideoNode] = useState<HTMLVideoElement | null>(null);
  const live = useLiveCamera(enableLiveFeed ? videoNode : null);
  const isLive = Boolean(enableLiveFeed) && live.status === "live";

  return (
    <div className={styles.tile}>
      <div className={styles.head}>
        <span className={styles.name}>{camera.name.toUpperCase()}</span>
        {camera.recording === "recording" ? (
          <span className={styles.rec}>
            <span className={styles.recDot} />
            REC
          </span>
        ) : null}
      </div>

      <div className={[styles.frame, !isConnected && !isLive ? styles.offline : ""].join(" ")}>
        <span className={styles.corner + " " + styles.tl} />
        <span className={styles.corner + " " + styles.tr} />
        <span className={styles.corner + " " + styles.bl} />
        <span className={styles.corner + " " + styles.br} />

        {enableLiveFeed ? (
          <video
            ref={setVideoNode}
            className={[styles.video, isLive ? styles.videoLive : ""].join(" ")}
            autoPlay
            playsInline
            muted
          />
        ) : null}

        {!isLive ? (
          <span className={[styles.placeholderLabel, !isConnected ? styles.noSignal : ""].join(" ")}>
            {enableLiveFeed ? LIVE_STATUS_LABEL[live.status] : isConnected ? "EN ATTENTE DE FLUX" : "SIGNAL PERDU"}
          </span>
        ) : null}

        {onExpand && (isConnected || isLive) ? (
          <button className={styles.expandButton} onClick={onExpand} type="button">
            Plein écran
          </button>
        ) : null}
      </div>

      {enableLiveFeed ? (
        <div className={styles.liveControls}>
          {live.status === "unsupported" ? (
            <span className={styles.liveNote}>
              Ce navigateur ne prend pas en charge l'accès caméra (essayez Chrome/Edge).
            </span>
          ) : (
            <>
              <select
                className={styles.liveSelect}
                value={live.selectedDeviceId ?? ""}
                onChange={(e) => live.selectDevice(e.target.value)}
                disabled={live.status === "requesting"}
              >
                <option value="" disabled>
                  {live.devices.length ? "Choisir un périphérique…" : "Aucun périphérique listé"}
                </option>
                {live.devices.map((d, i) => (
                  <option key={d.deviceId} value={d.deviceId}>
                    {d.label || `Caméra ${i + 1}`}
                  </option>
                ))}
              </select>
              {live.status === "live" ? (
                <button type="button" className={styles.liveButton} onClick={live.stop}>
                  Arrêter
                </button>
              ) : (
                <button
                  type="button"
                  className={styles.liveButton}
                  onClick={live.start}
                  disabled={live.status === "requesting"}
                >
                  {live.status === "requesting" ? "Connexion…" : "Activer la caméra réelle"}
                </button>
              )}
            </>
          )}
          {live.errorMessage ? <span className={styles.liveError}>{live.errorMessage}</span> : null}
        </div>
      ) : null}

      <div className={styles.meta}>
        <span className={styles.metaItem}>
          <span>FPS </span>
          {isConnected ? camera.fps : "N/A"}
        </span>
        <span className={styles.metaItem}>
          <span>RÉS </span>
          {camera.resolution}
        </span>
        <span className={styles.metaItem}>
          <span>LATENCE </span>
          {isConnected ? `${camera.latencyMs} ms` : "N/A"}
        </span>
        <span className={styles.metaItem}>
          <span>DERNIÈRE DÉTECTION </span>
          {camera.lastDetectionAt ? `${camera.lastDetectionLabel} · ${relativeFromNow(camera.lastDetectionAt)}` : "aucune"}
        </span>
      </div>

      {recentEvents ? <DetectionFilmstrip events={recentEvents} /> : null}
    </div>
  );
}
