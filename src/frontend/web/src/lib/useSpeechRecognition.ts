import { useCallback, useEffect, useRef, useState } from "react";

export interface SpeechRecognitionController {
  /** False in browsers with no `SpeechRecognition`/`webkitSpeechRecognition`
   * (Firefox, most non-Chromium browsers). Callers must show an honest
   * "not available" message in that case rather than silently pretending
   * to listen. */
  supported: boolean;
  listening: boolean;
  /** Live interim + final transcript, updated as the browser recognizes
   * speech: this is what actually gets shown while "écoute" is active,
   * not a scripted animation. */
  transcript: string;
  start: (handlers: { onFinal: (text: string) => void; onEmpty: () => void; onError: (message: string) => void }) => void;
  /** Ends listening early (e.g. the user taps the orb again): the
   * browser then fires its normal end-of-speech handling with whatever
   * was captured so far. */
  stop: () => void;
}

function getRecognitionCtor(): (new () => SpeechRecognitionLike) | null {
  if (typeof window === "undefined") return null;
  return window.SpeechRecognition ?? window.webkitSpeechRecognition ?? null;
}

/** How long to wait, with zero recognition activity, before giving up on
 * total silence ourselves. The browser's own `"no-speech"` error is
 * NOT reliable (confirmed by testing: staying silent can leave Chrome's
 * recognizer hanging indefinitely, with neither `onerror` nor `onend`
 * ever firing), so this is a real guarantee rather than a best-effort
 * nicety. Reset on every `onresult`, so someone pausing mid-sentence
 * isn't cut off, only genuine silence. */
const SILENCE_TIMEOUT_MS = 6000;

/** Absolute ceiling regardless of activity: a single non-continuous
 * utterance shouldn't run forever even if the recognizer keeps producing
 * interim results (background noise, a long ramble, …). */
const MAX_LISTEN_MS = 20000;

/** Real microphone transcription via the Web Speech API, French
 * (`fr-FR`), interim results shown live while listening. Support is
 * inconsistent across browsers (Chrome/Edge yes, Firefox generally no):
 * `supported` tells the caller so it can show a clear message instead of
 * silently falling back to a fake transcript. */
export function useSpeechRecognition(): SpeechRecognitionController {
  const [Ctor] = useState(() => getRecognitionCtor());
  const supported = Ctor !== null;

  const [listening, setListening] = useState(false);
  const [transcript, setTranscript] = useState("");
  const recognitionRef = useRef<SpeechRecognitionLike | null>(null);
  const finalRef = useRef("");
  const latestRef = useRef("");

  useEffect(() => () => recognitionRef.current?.abort(), []);

  const start = useCallback<SpeechRecognitionController["start"]>(
    ({ onFinal, onEmpty, onError }) => {
      if (!Ctor) return;
      const recognition = new Ctor();
      recognition.lang = "fr-FR";
      recognition.interimResults = true;
      recognition.continuous = false;
      recognition.maxAlternatives = 1;

      finalRef.current = "";
      latestRef.current = "";
      setTranscript("");
      setListening(true);

      // Some browsers fire BOTH `onerror` (e.g. "no-speech") and then
      // `onend` for the same session; without this guard that meant
      // `onEmpty`/`onFinal` could fire twice for one exchange (observed:
      // a stray second call could re-trigger `resolve()` after the UI had
      // already moved on, landing the orb in a confusing state).
      let ended = false;
      let silenceTimer: number | null = null;
      let hardTimer: number | null = null;

      const clearWatchdogs = () => {
        if (silenceTimer !== null) window.clearTimeout(silenceTimer);
        if (hardTimer !== null) window.clearTimeout(hardTimer);
        silenceTimer = null;
        hardTimer = null;
      };

      const armSilenceTimer = () => {
        if (silenceTimer !== null) window.clearTimeout(silenceTimer);
        silenceTimer = window.setTimeout(() => {
          // Total silence and the browser never told us: stop it
          // ourselves exactly as if the user had tapped "stop" manually,
          // rather than leaving "écoute" hanging indefinitely.
          recognition.stop();
        }, SILENCE_TIMEOUT_MS);
      };

      recognition.onresult = (event) => {
        armSilenceTimer();
        let interim = "";
        for (let i = event.resultIndex; i < event.results.length; i++) {
          const res = event.results[i];
          const text = res[0]?.transcript ?? "";
          if (res.isFinal) finalRef.current += text;
          else interim += text;
        }
        const combined = `${finalRef.current}${interim}`.trim();
        latestRef.current = combined;
        setTranscript(combined);
      };

      recognition.onerror = (event) => {
        if (ended) return;
        ended = true;
        clearWatchdogs();
        setListening(false);
        if (event.error === "no-speech" || event.error === "aborted") {
          onEmpty();
        } else if (event.error === "not-allowed" || event.error === "service-not-allowed") {
          onError("Micro refusé, autorise l'accès au micro dans les paramètres du navigateur.");
        } else if (event.error === "audio-capture") {
          onError("Aucun micro détecté.");
        } else {
          onError(`Erreur de reconnaissance vocale (${event.error}).`);
        }
      };

      recognition.onend = () => {
        if (ended) return;
        ended = true;
        clearWatchdogs();
        setListening(false);
        const text = latestRef.current.trim();
        if (text) onFinal(text);
        else onEmpty();
      };

      recognitionRef.current = recognition;
      recognition.start();
      armSilenceTimer();
      hardTimer = window.setTimeout(() => recognition.stop(), MAX_LISTEN_MS);
    },
    [Ctor]
  );

  const stop = useCallback(() => {
    recognitionRef.current?.stop();
  }, []);

  return { supported, listening, transcript, start, stop };
}
