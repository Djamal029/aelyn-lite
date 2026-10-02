import { useCallback, useEffect, useRef, useState } from "react";
import { synthesizeSpeech } from "./api";
import { isBackendLive } from "./backendStatus";

export interface SpeakHandlers {
  onStart?: () => void;
  onEnd?: () => void;
  onError?: (message: string) => void;
}

export type TtsEngine = "api" | "browser";

export interface SpeechSynthesisController {
  /** True for exactly as long as audio is actually playing, whichever
   * engine produced it, driven by real playback events, not a fixed
   * timer, so callers (VoiceOrb's "réponse" state) reflect real audio. */
  speaking: boolean;
  /** Which engine produced the last utterance: "api" is AELYN's real
   * voice (aelyn-api's `POST /tts`, Edge TTS "Vivienne" or local
   * Kokoro, the same voice the CLI's `aelyn chat --voix` uses);
   * "browser" is the Web Speech API fallback used when aelyn-api isn't
   * reachable or `/tts` fails. `null` before anything has been spoken
   * yet. */
  lastEngine: TtsEngine | null;
  /** True once the browser's voice list has loaded and none of them
   * match French: only meaningful for the "browser" engine fallback;
   * AELYN's real API voice always speaks French regardless. */
  frenchVoiceMissing: boolean;
  speak: (text: string, handlers?: SpeakHandlers) => void;
  cancel: () => void;
}

function findFrenchVoice(): SpeechSynthesisVoice | null {
  const voices = window.speechSynthesis.getVoices();
  return voices.find((v) => v.lang.toLowerCase().startsWith("fr")) ?? null;
}

/** Real speech output, preferring AELYN's actual voice over the
 * browser's: every `speak()` call tries `aelyn-api`'s `POST /tts`
 * first (real synthesized audio, same voice as the CLI) and only falls
 * back to the browser's built-in `SpeechSynthesis` (`fr-FR`) if the API
 * is unreachable or the call fails, matching the same graceful-degrade
 * pattern used everywhere else in this app. Completes the voice loop
 * alongside lib/useSpeechRecognition.ts (listening). */
export function useSpeechSynthesis(): SpeechSynthesisController {
  const browserSupported = typeof window !== "undefined" && "speechSynthesis" in window;
  const [speaking, setSpeaking] = useState(false);
  const [lastEngine, setLastEngine] = useState<TtsEngine | null>(null);
  const [frenchVoiceMissing, setFrenchVoiceMissing] = useState(false);

  const audioRef = useRef<HTMLAudioElement | null>(null);
  const objectUrlRef = useRef<string | null>(null);
  const requestIdRef = useRef(0);

  useEffect(() => {
    if (!browserSupported) return;
    const checkVoices = () => {
      const voices = window.speechSynthesis.getVoices();
      if (voices.length > 0) setFrenchVoiceMissing(findFrenchVoice() === null);
    };
    checkVoices();
    window.speechSynthesis.addEventListener("voiceschanged", checkVoices);
    return () => window.speechSynthesis.removeEventListener("voiceschanged", checkVoices);
  }, [browserSupported]);

  const cleanupAudio = useCallback(() => {
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current.onplay = null;
      audioRef.current.onended = null;
      audioRef.current.onerror = null;
      audioRef.current = null;
    }
    if (objectUrlRef.current) {
      URL.revokeObjectURL(objectUrlRef.current);
      objectUrlRef.current = null;
    }
  }, []);

  // Never leave AELYN mid-sentence when the panel closes or the page
  // navigates away.
  useEffect(() => {
    return () => {
      cleanupAudio();
      if (browserSupported) window.speechSynthesis.cancel();
    };
  }, [browserSupported, cleanupAudio]);

  const speakViaBrowser = useCallback(
    (text: string, handlers: SpeakHandlers) => {
      if (!browserSupported) {
        handlers.onError?.("Synthèse vocale indisponible (ni aelyn-api, ni ce navigateur).");
        return;
      }
      window.speechSynthesis.cancel();
      const utterance = new SpeechSynthesisUtterance(text);
      utterance.lang = "fr-FR";
      const voice = findFrenchVoice();
      if (voice) utterance.voice = voice;

      utterance.onstart = () => {
        setSpeaking(true);
        setLastEngine("browser");
        handlers.onStart?.();
      };
      utterance.onend = () => {
        setSpeaking(false);
        handlers.onEnd?.();
      };
      utterance.onerror = (event) => {
        setSpeaking(false);
        if (event.error !== "interrupted" && event.error !== "canceled") {
          handlers.onError?.(`Erreur de synthèse vocale (${event.error}).`);
        }
      };

      window.speechSynthesis.speak(utterance);
    },
    [browserSupported]
  );

  const speak = useCallback(
    (text: string, handlers: SpeakHandlers = {}) => {
      const trimmed = text.trim();
      if (!trimmed) return;

      // Invalidate any previous in-flight call so a fast second
      // speak() (or cancel()) doesn't have a stale request finish late
      // and start talking over the current one.
      const requestId = ++requestIdRef.current;
      cleanupAudio();
      if (browserSupported) window.speechSynthesis.cancel();

      void (async () => {
        const live = await isBackendLive();
        if (requestId !== requestIdRef.current) return;

        if (live) {
          try {
            const { blob } = await synthesizeSpeech(trimmed);
            if (requestId !== requestIdRef.current) return;

            const url = URL.createObjectURL(blob);
            objectUrlRef.current = url;
            const audio = new Audio(url);
            audioRef.current = audio;

            audio.onplay = () => {
              setSpeaking(true);
              setLastEngine("api");
              handlers.onStart?.();
            };
            audio.onended = () => {
              setSpeaking(false);
              cleanupAudio();
              handlers.onEnd?.();
            };
            audio.onerror = () => {
              setSpeaking(false);
              cleanupAudio();
              if (requestId === requestIdRef.current) speakViaBrowser(trimmed, handlers);
            };

            await audio.play();
            return;
          } catch {
            if (requestId !== requestIdRef.current) return;
            // aelyn-api reachable but /tts failed (400/502/timeout):
            // fall back to the browser voice below.
          }
        }

        if (requestId !== requestIdRef.current) return;
        speakViaBrowser(trimmed, handlers);
      })();
    },
    [browserSupported, cleanupAudio, speakViaBrowser]
  );

  const cancel = useCallback(() => {
    requestIdRef.current++;
    cleanupAudio();
    if (browserSupported) window.speechSynthesis.cancel();
    setSpeaking(false);
  }, [browserSupported, cleanupAudio]);

  return { speaking, lastEngine, frenchVoiceMissing, speak, cancel };
}
