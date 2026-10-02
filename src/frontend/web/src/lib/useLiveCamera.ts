import { useCallback, useEffect, useRef, useState } from "react";

export type LiveCameraStatus =
  | "unsupported"
  | "idle"
  | "requesting"
  | "live"
  | "denied"
  | "no-device"
  | "error";

export interface LiveCameraController {
  status: LiveCameraStatus;
  devices: MediaDeviceInfo[];
  selectedDeviceId: string | null;
  errorMessage: string | null;
  /** Ask for camera permission and start streaming the system default
   * device (or the last selected one). */
  start: () => void;
  /** Switch to a specific input device: used to point a tile at a real
   * laptop webcam vs. a phone exposed through Iriun Webcam. */
  selectDevice: (deviceId: string) => void;
  stop: () => void;
}

/** Real `getUserMedia`/`enumerateDevices` wiring for local testing:
 * genuinely opens the browser's camera permission prompt and renders an
 * actual live feed, it does not fabricate a stream. Used by CameraTile
 * when `enableLiveFeed` is set (Cameras page only). Every failure mode
 * (permission denied, no device, unsupported browser) is surfaced as an
 * explicit status rather than silently falling back to the placeholder
 * without explanation. */
export function useLiveCamera(videoEl: HTMLVideoElement | null): LiveCameraController {
  const supported =
    typeof navigator !== "undefined" && !!navigator.mediaDevices && !!navigator.mediaDevices.getUserMedia;

  const [status, setStatus] = useState<LiveCameraStatus>(supported ? "idle" : "unsupported");
  const [devices, setDevices] = useState<MediaDeviceInfo[]>([]);
  const [selectedDeviceId, setSelectedDeviceId] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const streamRef = useRef<MediaStream | null>(null);

  const stopStream = useCallback(() => {
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    if (videoEl) videoEl.srcObject = null;
  }, [videoEl]);

  const applyStream = useCallback(
    async (constraints: MediaStreamConstraints) => {
      setStatus("requesting");
      setErrorMessage(null);
      try {
        const stream = await navigator.mediaDevices.getUserMedia(constraints);
        stopStream();
        streamRef.current = stream;
        if (videoEl) videoEl.srcObject = stream;

        const track = stream.getVideoTracks()[0];
        setSelectedDeviceId(track?.getSettings().deviceId ?? null);

        // Device labels are only populated once permission has been
        // granted at least once: refresh the list now that it has.
        const list = await navigator.mediaDevices.enumerateDevices();
        setDevices(list.filter((d) => d.kind === "videoinput"));

        setStatus("live");
      } catch (err) {
        const name = err instanceof DOMException ? err.name : "";
        if (name === "NotAllowedError" || name === "PermissionDeniedError") {
          setStatus("denied");
          setErrorMessage("Accès à la caméra refusé.");
        } else if (name === "NotFoundError" || name === "DevicesNotFoundError") {
          setStatus("no-device");
          setErrorMessage("Aucun périphérique vidéo trouvé.");
        } else {
          setStatus("error");
          setErrorMessage(err instanceof Error ? err.message : "Erreur inconnue.");
        }
      }
    },
    [videoEl, stopStream]
  );

  const start = useCallback(() => {
    if (!supported) return;
    void applyStream({ video: true, audio: false });
  }, [supported, applyStream]);

  const selectDevice = useCallback(
    (deviceId: string) => {
      if (!supported) return;
      void applyStream({ video: { deviceId: { exact: deviceId } }, audio: false });
    },
    [supported, applyStream]
  );

  const stop = useCallback(() => {
    stopStream();
    setStatus("idle");
    setSelectedDeviceId(null);
  }, [stopStream]);

  // Stop the real hardware stream whenever the <video> element goes
  // away: either this tile unmounts, or the caller stops rendering the
  // video (CameraTile does this for the grid tile behind an open
  // fullscreen overlay of the same camera, to avoid two simultaneous
  // getUserMedia sessions fighting over one device).
  useEffect(() => stopStream, [stopStream]);

  // The stream is gone once `videoEl` disappears, but `status`/`
  // selectedDeviceId` would otherwise stay stuck on a stale "live":
  // reset them so a tile that re-enables its feed later (e.g. closing
  // that fullscreen overlay) shows an honest "not activated" state
  // instead of a frozen "live" label with no picture.
  useEffect(() => {
    if (videoEl === null) {
      setStatus(supported ? "idle" : "unsupported");
      setSelectedDeviceId(null);
    }
  }, [videoEl, supported]);

  return { status, devices, selectedDeviceId, errorMessage, start, selectDevice, stop };
}
