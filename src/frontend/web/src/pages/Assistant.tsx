import { useEffect, useState } from "react";
import { useLocation } from "react-router-dom";
import { ChatHistory } from "../components/chat/ChatHistory";
import { CommandBar } from "../components/commandbar/CommandBar";
import { VoicePanel } from "../components/voice/VoicePanel";
import type { InterpretedCommand } from "../lib/commandInterpreter";
import type { ChatMessage } from "../types";
import { chatHistory as initialHistory } from "../mocks";
import { getChatHistory, type ApiChatEntry } from "../lib/api";
import { isBackendLive } from "../lib/backendStatus";
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

/** Assistant / Chat: the conversational surface of the console. History
 * loads for real from aelyn-api's `GET /chat/history` (the same SQLite
 * store the CLI chat writes to) when the backend is reachable, falling
 * back to the realistic mock transcript (mocks/chat.ts) otherwise (see
 * `historySource` below, shown to the user rather than silently
 * guessed). Each AELYN turn shows the routed intent before its result
 * for commands (lib/commandResolver.ts executes verifier/
 * chercher_offres/media for real against aelyn-api when it's up); free
 * conversation goes through the real `POST /chat/message` and has no
 * "COMPRIS" line, matching the backend's own "no intent routing yet"
 * behavior honestly. Voice mode (VoicePanel) feeds the exact same
 * history so nothing said out loud is ever lost once the exchange is
 * done. */
export function Assistant() {
  const location = useLocation();
  const [messages, setMessages] = useState<ChatMessage[]>(initialHistory);
  const [historySource, setHistorySource] = useState<"mock" | "live">("mock");
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
        // stay on the mock transcript
      }
    })();
    return () => {
      cancelled = true;
    };
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
              : "historique de démonstration : AELYN Core (aelyn-api) injoignable, commandes simulées localement"}
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
