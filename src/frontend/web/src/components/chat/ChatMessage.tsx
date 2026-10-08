import type { ChatMessage as ChatMessageT } from "../../types";
import { formatTimestamp } from "../../lib/time";
import { StatusDot } from "../ui/StatusDot";
import { ChatResultTable } from "./ChatResultTable";
import styles from "./ChatMessage.module.css";

const STATUS_LABEL: Record<NonNullable<ChatMessageT["status"]>, string> = {
  executing: "EXÉCUTION...",
  done: "EXÉCUTÉ",
  error: "ERREUR",
  cancelled: "ANNULÉ",
};

const STATUS_CLASS: Record<NonNullable<ChatMessageT["status"]>, string> = {
  executing: styles.statusExecuting,
  done: styles.statusDone,
  error: styles.statusError,
  cancelled: styles.statusCancelled,
};

/** One turn of the conversation. Classic messaging layout: the user's
 * turns sit on the right, AELYN's on the left, like any normal chat app,
 * but each turn is still a plain rounded card (soft dark, not a
 * cartoon SMS bubble/tail), and AELYN's card always shows what was
 * understood (the routed intent) before the result text, mirroring the
 * real backend's transparency (`intent.reformulation` said before
 * `_run_command` executes, in conversational-agent/agent.py). */
interface ChatMessageProps {
  message: ChatMessageT;
  onPrepareCvs?: (offers: { id: string; title: string }[]) => void;
  onPrepareCoverLetters?: (offers: { id: string; title: string }[]) => void;
}

export function ChatMessage({ message, onPrepareCvs, onPrepareCoverLetters }: ChatMessageProps) {
  const isAelyn = message.role === "aelyn";
  const hasTable = Boolean(message.resultType && message.results && message.results.length > 0);
  // When a real table is rendered below, `text` (whether the backend's
  // own natural-language reply or this app's fast-path summary) still
  // carries the full itemized list as its own sentence/bullets; showing
  // only its first line as the intro avoids saying the same list twice.
  const displayText = hasTable ? message.text.split("\n")[0] : message.text;
  return (
    <div className={[styles.wrap, isAelyn ? styles.wrapAelyn : styles.wrapUser].join(" ")}>
      <div className={[styles.row, isAelyn ? styles.aelyn : styles.user].join(" ")}>
        <div className={styles.header}>
          <span className={[styles.sender, isAelyn ? styles.senderAelyn : ""].join(" ")}>
            {isAelyn ? "AELYN" : "Toi"}
          </span>
          <span className={styles.timestamp}>{formatTimestamp(message.timestamp)}</span>
          {message.via === "voice" ? <span className={styles.via}>voix</span> : null}
        </div>

        {message.understood ? <div className={styles.understood}>{message.understood}</div> : null}

        {isAelyn && message.status === "executing" && !message.text ? (
          <div className={styles.thinking} aria-label="AELYN réfléchit">
            <span className={styles.dot} />
            <span className={styles.dot} />
            <span className={styles.dot} />
          </div>
        ) : (
          <div className={styles.text}>{displayText}</div>
        )}

        {hasTable ? (
          <ChatResultTable
            resultType={message.resultType!}
            results={message.results!}
            onPrepareCvs={message.resultType === "offers" ? onPrepareCvs : undefined}
            onPrepareCoverLetters={message.resultType === "offers" ? onPrepareCoverLetters : undefined}
          />
        ) : null}

        {isAelyn && message.status && !(message.status === "executing" && !message.text) ? (
          <div className={[styles.statusRow, STATUS_CLASS[message.status]].join(" ")}>
            <StatusDot
              kind={
                message.status === "executing"
                  ? "executing"
                  : message.status === "done"
                    ? "done"
                    : message.status === "error"
                      ? "error"
                      : "neutral"
              }
              pulse={message.status === "executing"}
            />
            {STATUS_LABEL[message.status]}
          </div>
        ) : null}
      </div>
    </div>
  );
}
