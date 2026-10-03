/** Canned phrases for the voice demo: there is no microphone input
 * wired up yet, so listening/transcription is scripted, but every
 * phrase and its result reuses the same interpreter as the command bar
 * (`interpretCommand`) so the exchange that lands in the chat history
 * is identical in shape to a typed command. */
export const VOICE_SCENARIOS = [
  "montre-moi la caméra de l'entrée",
  "vérifie mes mails",
  "cherche des offres data scientist à Rennes",
  "lance Netflix",
  "rapport de la journée",
] as const;

export function pickScenario(liteMode = false): string {
  const scenarios = liteMode
    ? VOICE_SCENARIOS.filter((scenario) => !/camera|caméra|vision|visage|sécurité/i.test(scenario))
    : VOICE_SCENARIOS;
  return scenarios[Math.floor(Math.random() * scenarios.length)];
}
