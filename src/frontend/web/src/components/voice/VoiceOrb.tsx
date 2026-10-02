import styles from "./VoiceOrb.module.css";

export type VoiceState = "veille" | "ecoute" | "traitement" | "reponse";

interface VoiceOrbProps {
  state: VoiceState;
  /** Amplitude samples (0-1) driving the listening bars: a lightweight
   * "AELYN is listening" motion cue, not a measured audio level (that
   * would need a separate AnalyserNode on the mic stream). */
  amplitude?: number[];
  /** When set, the orb itself is the primary control: click it to
   * start or stop listening, JARVIS-style, instead of only a separate
   * button next to it. Omit to make the orb purely a state indicator. */
  onClick?: () => void;
  /** True for exactly as long as AELYN's reply is actually being read
   * aloud (lib/useSpeechSynthesis.ts's real onstart/onend). Drives a
   * gentle continuous pulse during "réponse" so the orb reflects real
   * audio instead of just holding a static settled color for however
   * long the text happens to be. */
  speaking?: boolean;
}

/** The single circular voice indicator ("Siri direction" in the design
 * doc): veille (idle, neutral, slow breathing) -> écoute (blue, reacts
 * to amplitude via bars) -> traitement (blue, spinner) -> réponse
 * (green, settles, then pulses gently while actually speaking). No
 * microphone icon, no mascot.
 *
 * Dressed as a real HUD instrument face (concentric bezel ring + tick
 * marks, a slow scanning arc while listening, a soft glow on the active
 * states, all built on the state colors already used elsewhere): this is
 * a visual skin only, layered on top of the state machine and the real
 * speech-driven animation (amplitude bars, the `speaking` pulse) above,
 * neither of which changes here. */
export function VoiceOrb({ state, amplitude = [], onClick, speaking }: VoiceOrbProps) {
  const interactive = Boolean(onClick);
  return (
    <div
      className={[styles.wrap, styles[state], interactive ? styles.interactive : "", speaking ? styles.speaking : ""].join(
        " "
      )}
      onClick={onClick}
      role={interactive ? "button" : undefined}
      tabIndex={interactive ? 0 : undefined}
      aria-label={interactive ? "Parler à AELYN" : undefined}
      onKeyDown={
        interactive
          ? (e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                onClick?.();
              }
            }
          : undefined
      }
    >
      <div className={styles.ticks} aria-hidden="true" />
      <div className={styles.ringOuter} aria-hidden="true" />
      <div className={styles.ring} />
      {state === "ecoute" ? <div className={styles.scanArc} aria-hidden="true" /> : null}
      <div className={styles.core} />
      {state === "ecoute" ? (
        <div className={styles.bars}>
          {amplitude.map((a, i) => (
            <span key={i} className={styles.bar} style={{ height: `${8 + a * 28}px` }} />
          ))}
        </div>
      ) : null}
      {state === "traitement" ? <div className={styles.spinner} /> : null}
    </div>
  );
}
