import { useEffect, useRef, useState } from "react";
import { VoiceOrb, type VoiceState } from "./VoiceOrb";
import type { InterpretedCommand } from "../../lib/commandInterpreter";
import { resolveCommand } from "../../lib/commandResolver";
import { pickScenario } from "../../lib/voiceDemo";
import { useSpeechRecognition } from "../../lib/useSpeechRecognition";
import { useSpeechSynthesis } from "../../lib/useSpeechSynthesis";
import styles from "./VoicePanel.module.css";

const STATE_LABEL: Record<VoiceState, string> = {
  veille: "Veille",
  ecoute: "Écoute…",
  traitement: "Traitement…",
  reponse: "Réponse",
};

interface VoicePanelProps {
  onClose: () => void;
  /** Fired once the exchange is over: the caller folds it into the
   * same chat history used by text commands, so voice never becomes a
   * "lost" interaction once it's finished. */
  onComplete: (userText: string, result: InterpretedCommand) => void;
}

/** Voice interaction surface for the Assistant page, "direction Siri":
 * veille -> écoute -> traitement -> réponse, one continuous flow (tap
 * the orb itself to start/stop, JARVIS-style, not a form with a submit
 * button) that always lands back in the same chat history.
 *
 * Takes over the Assistant page's whole content area while open (matching
 * ChatGPT's voice mode: the orb is the only thing you're looking at,
 * the text conversation is not visible underneath it), replacing
 * ChatHistory/CommandBar rather than stacking above them (see
 * Assistant.tsx). Each exchange still lands in the real chat history the
 * moment it completes via `onComplete` exactly as before, a whole voice
 * session can carry several back-to-back exchanges without leaving this
 * view; the text thread simply isn't the visible surface again until the
 * user closes this panel, at which point everything said during the
 * session is already there waiting.
 *
 * Both halves of the conversation are real:
 *  - Listening: the Web Speech API (`fr-FR`) transcribes the actual
 *    microphone live while "écoute" is active (lib/useSpeechRecognition.ts).
 *    The text shown is what the browser actually heard.
 *  - Understanding/acting: the recognized phrase goes through
 *    lib/commandResolver.ts, which executes for real against aelyn-api
 *    (checking mail, searching offers, controlling the TV) when it's
 *    reachable, falling back to the local demo classification otherwise.
 *    Same resolver the typed command bar uses, so voice isn't a
 *    second, less capable path.
 *  - Speaking: AELYN's reply is genuinely read aloud via the browser's
 *    `SpeechSynthesis` API (lib/useSpeechSynthesis.ts). The "réponse"
 *    state's duration is driven by the utterance's own start/end
 *    events, not a fixed timer, so the orb reflects whether audio is
 *    actually playing.
 *
 * Support for either Web Speech half is inconsistent across browsers
 * (Chrome/Edge yes, Firefox generally no for recognition); when
 * something is unavailable this says so plainly rather than silently
 * faking it. Recognition falls back to an explicitly labeled scripted
 * demo (lib/voiceDemo.ts), and synthesis falls back to a fixed pause so
 * the flow never hangs waiting for speech that will never happen. */
export function VoicePanel({ onClose, onComplete }: VoicePanelProps) {
  const [state, setState] = useState<VoiceState>("veille");
  const [displayTranscript, setDisplayTranscript] = useState("");
  const [notice, setNotice] = useState<string | null>(null);
  const [amplitude, setAmplitude] = useState<number[]>(Array(7).fill(0.1));
  const [result, setResult] = useState<InterpretedCommand | null>(null);
  const timers = useRef<number[]>([]);
  const ampInterval = useRef<number | null>(null);
  const stt = useSpeechRecognition();
  const tts = useSpeechSynthesis();

  const clearTimers = () => {
    timers.current.forEach((t) => window.clearTimeout(t));
    timers.current = [];
  };
  const stopAmplitude = () => {
    if (ampInterval.current) {
      window.clearInterval(ampInterval.current);
      ampInterval.current = null;
    }
  };
  const startAmplitude = () => {
    stopAmplitude();
    ampInterval.current = window.setInterval(() => {
      setAmplitude(Array.from({ length: 7 }, () => Math.random()));
    }, 90);
  };

  const ttsCancelRef = useRef(tts.cancel);
  useEffect(() => {
    ttsCancelRef.current = tts.cancel;
  });

  useEffect(
    () => () => {
      clearTimers();
      stopAmplitude();
      ttsCancelRef.current();
    },
    []
  );

  const onCloseRef = useRef(onClose);
  useEffect(() => {
    onCloseRef.current = onClose;
  });

  // This view now takes over the whole page while open (see the
  // component doc comment), so it gets the same Escape-to-close affordance
  // as the other fullscreen-style surface in the app (Cameras.tsx's
  // expanded camera overlay).
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onCloseRef.current();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  // Mirror the live recognized text while actually listening: kept in
  // its own state (rather than reading `stt.transcript` directly at
  // render time) so the final phrase stays visible through
  // traitement/réponse instead of vanishing once listening ends.
  useEffect(() => {
    if (stt.listening) setDisplayTranscript(stt.transcript);
  }, [stt.transcript, stt.listening]);

  const finishExchange = (userText: string, interpreted: InterpretedCommand) => {
    onComplete(userText, interpreted);
    setState("veille");
    setResult(null);
    setDisplayTranscript("");
  };

  const resolve = async (userText: string) => {
    stopAmplitude();
    setState("traitement");
    const interpreted = await resolveCommand(userText);
    setResult(interpreted);
    setState("reponse");

    const textToSpeak = interpreted.resultText?.trim();
    if (!textToSpeak) {
      timers.current.push(window.setTimeout(() => finishExchange(userText, interpreted), 900));
      return;
    }

    // The orb stays in "réponse" for exactly as long as AELYN is
    // actually talking, driven by the utterance's real onstart/onend,
    // not a guessed duration. If speech isn't available at all (or
    // errors out), fall back to a fixed pause so the exchange doesn't
    // hang forever waiting for audio that will never play.
    tts.speak(textToSpeak, {
      onEnd: () => finishExchange(userText, interpreted),
      onError: () => {
        timers.current.push(window.setTimeout(() => finishExchange(userText, interpreted), 1700));
      },
    });
  };

  const showTransientNotice = (message: string) => {
    stopAmplitude();
    setNotice(message);
    setState("veille");
    setDisplayTranscript("");
    timers.current.push(window.setTimeout(() => setNotice(null), 2400));
  };

  const startRealListening = () => {
    clearTimers();
    tts.cancel();
    setResult(null);
    setNotice(null);
    setDisplayTranscript("");
    setState("ecoute");
    startAmplitude();
    stt.start({
      onFinal: (text) => {
        setDisplayTranscript(text);
        void resolve(text);
      },
      onEmpty: () => showTransientNotice("Rien entendu."),
      onError: (message) => showTransientNotice(message),
    });
  };

  const stopRealListening = () => {
    stt.stop();
  };

  const startScriptedDemo = () => {
    clearTimers();
    tts.cancel();
    setResult(null);
    setNotice(null);
    setDisplayTranscript("");
    setState("ecoute");
    startAmplitude();

    const scenario = pickScenario();
    const words = scenario.split(" ");
    words.forEach((_, i) => {
      timers.current.push(
        window.setTimeout(() => setDisplayTranscript(words.slice(0, i + 1).join(" ")), 260 * (i + 1))
      );
    });
    timers.current.push(window.setTimeout(() => void resolve(scenario), 260 * words.length + 420));
  };

  const busyLocked = state === "traitement" || state === "reponse";
  const orbInteractive = state === "ecoute" || (state === "veille" && stt.supported);

  const handleOrbClick = () => {
    if (state === "ecoute") stopRealListening();
    else if (state === "veille" && stt.supported) startRealListening();
  };

  return (
    <div className={styles.panel}>
      <button className={styles.closeCorner} onClick={onClose} type="button" aria-label="Fermer le contrôle vocal">
        Fermer (Échap)
      </button>

      <div className={styles.orbStage}>
        <div className={styles.orbScale}>
          <VoiceOrb
            state={state}
            amplitude={amplitude}
            speaking={state === "reponse" && tts.speaking}
            onClick={orbInteractive ? handleOrbClick : undefined}
          />
        </div>
      </div>

      <div className={styles.info}>
        <div className={[styles.stateLabel, styles[state]].join(" ")}>{STATE_LABEL[state]}</div>

        {notice ? (
          <div className={styles.notice}>{notice}</div>
        ) : state === "veille" ? (
          <div className={styles.hint}>
            {stt.supported
              ? "Touche l'orbe ou « Parler » pour t'adresser à AELYN."
              : "Reconnaissance vocale non prise en charge par ce navigateur (Chrome ou Edge requis), utilise la démo scriptée."}
          </div>
        ) : (
          <div className={styles.transcript}>
            {displayTranscript}
            {state === "ecoute" ? <span className={styles.cursor} /> : null}
          </div>
        )}

        {result?.understood ? <div className={styles.understood}>{result.understood}</div> : null}
        {state === "reponse" && result?.resultText ? <div className={styles.result}>{result.resultText}</div> : null}

        {tts.lastEngine === "browser" ? (
          <div className={styles.ttsNote}>
            Voix de secours du navigateur (AELYN Core /tts injoignable)
            {tts.frenchVoiceMissing ? ", aucune voix française détectée sur ce système" : ""}.
          </div>
        ) : null}
      </div>

      <div className={styles.actions}>
        {stt.supported ? (
          <button
            className={styles.talkButton}
            onClick={state === "ecoute" ? stopRealListening : startRealListening}
            disabled={busyLocked}
            type="button"
          >
            {state === "ecoute" ? "Arrêter l'écoute" : "Parler"}
          </button>
        ) : (
          <button className={styles.talkButton} onClick={startScriptedDemo} disabled={busyLocked || state === "ecoute"} type="button">
            Démo scriptée
          </button>
        )}
      </div>
    </div>
  );
}
