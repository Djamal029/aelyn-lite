import { useCallback } from "react";
import { resolveCommand } from "./commandResolver";
import { isBackendLive } from "./backendStatus";
import { recordLocalActivity } from "./localActivity";
import type { InterpretedCommand } from "./commandInterpreter";

/** Classifies the phrase and, when aelyn-api is reachable, actually
 * executes the commands that have a real endpoint behind them
 * (commandResolver.ts). A short minimum delay runs alongside the real
 * call so "EXÉCUTION..." is visible for at least a beat even when the
 * backend answers instantly, instead of flashing straight to a result;
 * matches the design doc's transcript example. */
export function useCommandRunner() {
  return useCallback(async (text: string): Promise<InterpretedCommand> => {
    const minDelay = new Promise((resolve) => window.setTimeout(resolve, 300 + Math.random() * 200));
    const [interpreted] = await Promise.all([resolveCommand(text), minDelay]);
    if (!(await isBackendLive()) || interpreted.command === "media") {
      recordLocalActivity(text, interpreted);
    }
    return interpreted;
  }, []);
}
