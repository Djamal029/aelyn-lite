import { useState, type KeyboardEvent } from "react";
import { useCommandRunner } from "../../lib/useCommandRunner";
import type { InterpretedCommand } from "../../lib/commandInterpreter";
import { StatusDot } from "../ui/StatusDot";
import styles from "./CommandBar.module.css";

interface ScrollbackEntry {
  id: string;
  prompt: string;
  result?: InterpretedCommand;
  pending: boolean;
}

interface CommandBarProps {
  /** "console" renders its own mini scrollback (Overview, matches the
   * design doc's bottom command zone). "chatInput" renders only the
   * input row, since the full transcript already lives in ChatHistory
   * above it (Assistant page). */
  variant?: "console" | "chatInput";
  placeholder?: string;
  onMicClick?: () => void;
  /** Fired the instant a command is submitted, before it resolves, so a
   * caller can show the user's own message right away instead of
   * sitting frozen until the round-trip finishes; a real assistant never
   * goes silent the moment you speak. `token` identifies this
   * submission and is handed back unchanged to `onExecuted`, so the
   * caller can match the eventual result to the right pending turn. */
  onSubmitted?: (prompt: string, token: string) => void;
  /** Called once a command has resolved: lets the Assistant page fold
   * the exchange into the persistent chat history instead of keeping a
   * second, separate log. */
  onExecuted?: (prompt: string, result: InterpretedCommand, token: string) => void;
}

export function CommandBar({ variant = "console", placeholder, onMicClick, onSubmitted, onExecuted }: CommandBarProps) {
  const [value, setValue] = useState("");
  const [scrollback, setScrollback] = useState<ScrollbackEntry[]>([]);
  const run = useCommandRunner();

  const submit = async () => {
    const text = value.trim();
    if (!text) return;
    setValue("");

    const id = `${Date.now()}`;
    setScrollback((prev) => [...prev.slice(-3), { id, prompt: text, pending: true }]);
    onSubmitted?.(text, id);

    const result = await run(text);

    setScrollback((prev) => prev.map((e) => (e.id === id ? { ...e, result, pending: false } : e)));
    onExecuted?.(text, result, id);
  };

  const onKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") submit();
  };

  return (
    <div className={styles.bar}>
      {variant === "console" ? (
        <div className={styles.scrollback}>
          {scrollback.map((entry) => (
            <div className={styles.entry} key={entry.id}>
              <div className={styles.prompt}>
                <span className={styles.promptGlyph}>{">"}</span>
                {entry.prompt}
              </div>
              {entry.pending ? (
                <div className={[styles.status, styles.statusExecuting].join(" ")}>
                  <StatusDot kind="executing" pulse />
                  EXÉCUTION...
                </div>
              ) : entry.result ? (
                <>
                  {entry.result.understood ? <div className={styles.understood}>{entry.result.understood}</div> : null}
                  {entry.result.resultText ? <div className={styles.result}>{entry.result.resultText}</div> : null}
                  <div
                    className={[
                      styles.status,
                      entry.result.status === "done" ? styles.statusDone : styles.statusError,
                    ].join(" ")}
                  >
                    <StatusDot kind={entry.result.status === "done" ? "done" : "error"} />
                    {entry.result.status === "done" ? "EXÉCUTÉ" : "ERREUR"}
                  </div>
                </>
              ) : null}
            </div>
          ))}
        </div>
      ) : null}

      <div className={styles.inputRow}>
        <span className={styles.glyph}>{">"}</span>
        <input
          className={styles.input}
          type="text"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder={placeholder ?? "Tapez une commande… (ex : montre-moi la caméra de l'entrée)"}
        />
        {onMicClick ? (
          <button className={styles.voiceButton} onClick={onMicClick} type="button">
            Voix
          </button>
        ) : null}
      </div>
    </div>
  );
}
