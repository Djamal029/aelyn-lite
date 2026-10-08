import { useEffect, useState } from "react";
import type { SystemResources } from "./api";

export interface ResourceSample {
  time: string;
  cpu: number;
  ram: number;
  gpu?: number;
}

export interface ResourcesState {
  resources: SystemResources | null;
  samples: ResourceSample[];
  updatedAt: string | null;
}

/** État au niveau du MODULE, pas d'un composant : même raison et même
 * remède que chatStore.ts. `Data.tsx` démonte/remonte à chaque fois
 * qu'on quitte la page "Données" du SPA puis qu'on y revient. Avec un
 * simple `useState` local (comportement d'origine, bug réel signalé en
 * usage), chaque retour sur la page repartait de `resources=null` et
 * affichait "Aucune mesure disponible" le temps d'un nouvel aller-retour
 * réseau — alors que le endpoint répond en fait très vite et que les
 * dernières valeurs connues étaient déjà en mémoire une seconde plus
 * tôt. En gardant l'état ici, une revisite réaffiche IMMÉDIATEMENT le
 * dernier relevé connu pendant que le prochain se charge en arrière-plan,
 * au lieu de clignoter sur un écran vide à chaque navigation. */
let state: ResourcesState = { resources: null, samples: [], updatedAt: null };
const listeners = new Set<() => void>();

function notify(): void {
  listeners.forEach((listener) => listener());
}

export function getResourcesState(): ResourcesState {
  return state;
}

export function setResourcesState(updater: ResourcesState | ((prev: ResourcesState) => ResourcesState)): void {
  state = typeof updater === "function" ? (updater as (prev: ResourcesState) => ResourcesState)(state) : updater;
  notify();
}

export function useResourcesState(): [ResourcesState, typeof setResourcesState] {
  const [snapshot, setSnapshot] = useState(state);
  useEffect(() => {
    const listener = () => setSnapshot(state);
    listeners.add(listener);
    setSnapshot(state);
    return () => {
      listeners.delete(listener);
    };
  }, []);
  return [snapshot, setResourcesState];
}
