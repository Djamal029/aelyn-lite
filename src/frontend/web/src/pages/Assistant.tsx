import { useEffect, useState } from "react";
import { useLocation } from "react-router-dom";
import { ChatHistory } from "../components/chat/ChatHistory";
import { CommandBar } from "../components/commandbar/CommandBar";
import { VoicePanel } from "../components/voice/VoicePanel";
import type { InterpretedCommand } from "../lib/commandInterpreter";
import type { ChatMessage } from "../types";
import { getChatHistory, type ApiChatEntry } from "../lib/api";
import { isBackendLive } from "../lib/backendStatus";
import { useChatMessages } from "../lib/chatStore";
import { useSpeechSynthesis } from "../lib/useSpeechSynthesis";
import styles from "./Assistant.module.css";

function fromApiEntry(entry: ApiChatEntry): ChatMessage {
  return {
    id: `api-${entry.id}`,
    role: entry.role === "assistant" ? "aelyn" : "user",
    timestamp: entry.ts,
    text: entry.content,
    via: "text",
  };
}

let nextId = 1000;

function appendExchange(
  prev: ChatMessage[],
  userText: string,
  result: InterpretedCommand,
  via: "text" | "voice"
): ChatMessage[] {
  const now = new Date().toISOString();
  const userMsg: ChatMessage = {
    id: `local-${nextId++}`,
    role: "user",
    timestamp: now,
    text: userText,
    via,
  };
  const aelynMsg: ChatMessage = {
    id: `local-${nextId++}`,
    role: "aelyn",
    timestamp: now,
    text: result.resultText || "Je n'ai pas de réponse pour ça.",
    understood: result.understood || undefined,
    command: result.command,
    status: result.status,
    via,
    resultType: result.resultType,
    results: result.results,
  };
  return [...prev, userMsg, aelynMsg];
}

/** The user's own message appears the instant they hit send (see
 * `handleTextSubmitted` below), paired with an empty, `status:
 * "executing"` AELYN placeholder that ChatMessage renders as a "thinking"
 * indicator instead of a frozen blank space, since a real assistant
 * never goes silent between "you spoke" and "I'm working on it". `token`
 * (from CommandBar) ties this pending pair to the eventual result. */
function appendPendingExchange(prev: ChatMessage[], userText: string, token: string): ChatMessage[] {
  const now = new Date().toISOString();
  const userMsg: ChatMessage = {
    id: `local-${token}-user`,
    role: "user",
    timestamp: now,
    text: userText,
    via: "text",
  };
  const pendingMsg: ChatMessage = {
    id: `local-${token}-aelyn`,
    role: "aelyn",
    timestamp: now,
    text: "",
    via: "text",
    status: "executing",
  };
  return [...prev, userMsg, pendingMsg];
}

/** Fills in the placeholder AELYN turn `appendPendingExchange` created,
 * in place, so the thinking indicator smoothly becomes the real reply
 * instead of a second message popping in underneath it. */
function resolvePendingExchange(prev: ChatMessage[], token: string, result: InterpretedCommand): ChatMessage[] {
  const pendingId = `local-${token}-aelyn`;
  return prev.map((m) =>
    m.id === pendingId
      ? {
          ...m,
          text: result.resultText || "Je n'ai pas de réponse pour ça.",
          understood: result.understood || undefined,
          command: result.command,
          status: result.status,
          resultType: result.resultType,
          results: result.results,
        }
      : m
  );
}

/** Assistant / Chat: the conversational surface of the console. Starts
 * genuinely empty (no fake pre-filled conversation) and loads for real
 * from aelyn-api's `GET /chat/history` (the same SQLite store the CLI
 * chat writes to) once the backend answers (see `historySource` below,
 * shown to the user rather than silently guessed). If the backend is
 * unreachable, the thread simply stays empty rather than showing a
 * simulated demo transcript as if it were real history. Each AELYN turn
 * shows the routed intent before its result for commands
 * (lib/commandResolver.ts executes verifier/chercher_offres/media for
 * real against aelyn-api when it's up); free conversation goes through
 * the real `POST /chat/message` and has no "COMPRIS" line, matching the
 * backend's own "no intent routing yet" behavior honestly. Voice mode
 * (VoicePanel) feeds the exact same history so nothing said out loud is
 * ever lost once the exchange is done. */
export function Assistant() {
  const location = useLocation();
  // Store au niveau du module (lib/chatStore.ts), pas un `useState` local :
  // cette page démonte/remonte à chaque navigation ailleurs dans le SPA
  // puis retour, et un simple état local perdait deux choses en route
  // (bugs réels observés en direct) - un échange encore en vol au moment
  // de quitter la page (ex. "oui" pour préparer un CV) dont la réponse
  // arrivait sur un composant déjà démonté, et le tableau de résultats
  // (resultType/results) de tours déjà affichés, écrasé par la version en
  // PROSE SEULE de GET /chat/history à chaque remontée (ce endpoint ne
  // porte jamais ces deux champs). Voir le fichier du store pour le détail.
  const [messages, setMessages] = useChatMessages();
  const [historySource, setHistorySource] = useState<"offline" | "live">("offline");
  const [voiceOpen, setVoiceOpen] = useState(Boolean((location.state as { openVoice?: boolean } | null)?.openVoice));
  const [speakReplies, setSpeakReplies] = useState(false);
  const [ttsError, setTtsError] = useState<string | null>(null);
  const tts = useSpeechSynthesis();

  useEffect(() => {
    if ((location.state as { openVoice?: boolean } | null)?.openVoice) {
      setVoiceOpen(true);
    }
  }, [location.state]);

  useEffect(() => {
    // Ne charge l'historique QUE si on n'a encore rien en mémoire (première
    // visite de l'app) : sinon, revenir sur Assistant après être allé
    // voir une autre page écraserait la conversation en cours (avec ses
    // vrais tableaux de résultats) par sa version texte brut rechargée
    // depuis GET /chat/history.
    if (messages.length > 0) {
      setHistorySource("live");
      return;
    }
    let cancelled = false;
    (async () => {
      const reachable = await isBackendLive();
      if (cancelled || !reachable) return;
      try {
        const history = await getChatHistory(50);
        if (cancelled) return;
        setMessages(history.map(fromApiEntry));
        setHistorySource("live");
      } catch {
        // backend reachable but history fetch failed: stay empty
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleTextSubmitted = (prompt: string, token: string) => {
    setMessages((prev) => appendPendingExchange(prev, prompt, token));
  };

  const handleTextExecuted = (_prompt: string, result: InterpretedCommand, token: string) => {
    setMessages((prev) => resolvePendingExchange(prev, token, result));
    if (speakReplies && result.resultText?.trim()) {
      setTtsError(null);
      tts.speak(result.resultText, { onError: (message) => setTtsError(message) });
    }
  };

  const handleVoiceComplete = (userText: string, result: InterpretedCommand) => {
    setMessages((prev) => appendExchange(prev, userText, result, "voice"));
  };

  // While a voice exchange is active, the orb takes over this whole page
  // (ChatGPT-style voice mode: the text thread isn't what you're looking
  // at while talking) instead of VoicePanel sitting inline above it.
  // Each exchange still lands in `messages` the moment it completes
  // (handleVoiceComplete, via VoicePanel's onComplete), a whole session
  // can carry several back-and-forth turns without leaving this view;
  // closing it is what reveals the text thread again, already containing
  // everything said during the session.
  if (voiceOpen) {
    return (
      <div className={styles.page}>
        <VoicePanel onClose={() => setVoiceOpen(false)} onComplete={handleVoiceComplete} />
      </div>
    );
  }

  return (
    <div className={styles.page}>
      <div className={styles.toolbar}>
        <div className={styles.titleGroup}>
          <span className={styles.title}>Assistant</span>
          <span className={styles.subtitle}>
            {historySource === "live"
              ? "historique réel (aelyn-api · SQLite, partagé avec le CLI), verifier / chercher_offres / media exécutés pour de vrai"
              : "AELYN Core (aelyn-api) injoignable : aucun historique, commandes simulées localement"}
          </span>
        </div>
        <div className={styles.toolbarActions}>
          {ttsError ? <span className={styles.ttsError}>{ttsError}</span> : null}
          <button
            className={[styles.voiceToggle, speakReplies ? styles.voiceToggleActive : ""].join(" ")}
            onClick={() => {
              const next = !speakReplies;
              setSpeakReplies(next);
              setTtsError(null);
              if (!next) tts.cancel();
            }}
            type="button"
            title="Voix AELYN (aelyn-api /tts) avec repli sur la voix du navigateur si indisponible"
          >
            {speakReplies ? "Lecture à voix haute : activée" : "Lire les réponses à voix haute"}
          </button>
          <button className={styles.voiceToggle} onClick={() => setVoiceOpen(true)} type="button">
            Contrôle vocal
          </button>
        </div>
      </div>

      <div className={styles.panelWrap}>
        <ChatHistory messages={messages} />
        <CommandBar
          variant="chatInput"
          placeholder="Écris à AELYN…"
          onSubmitted={handleTextSubmitted}
          onExecuted={handleTextExecuted}
          onMicClick={() => setVoiceOpen(true)}
        />
      </div>
    </div>
  );
}
