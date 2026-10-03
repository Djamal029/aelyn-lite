import { useEffect, useState } from "react";
import type { ChatMessage } from "../types";

/** État de la conversation au niveau du MODULE, pas d'un composant : par
 * construction, `Assistant.tsx` démonte/remonte à chaque fois qu'on quitte
 * cette page du SPA puis qu'on y revient (route React Router comme une
 * autre). Avec un simple `useState` local (comportement d'origine), deux
 * bugs réels observés en direct :
 *
 * 1. Un échange encore "en vol" au moment de quitter la page (ex. "oui"
 *    pour préparer un CV, réponse lente) perdait sa réponse : quand le
 *    fetch finissait enfin, `setMessages` s'appelait sur un composant déjà
 *    démonté, silencieusement ignoré par React - au retour sur
 *    Assistant, plus aucune trace du résultat.
 * 2. Chaque remontée de la page re-déclenchait le chargement de
 *    `GET /chat/history` et ÉCRASAIT les messages déjà en mémoire -
 *    y compris ceux de la session en cours, avec leur vrai tableau de
 *    résultats (`resultType`/`results`). `ChatMessageOut` (le schéma de
 *    `/chat/history`) ne porte QUE du texte brut, jamais ces deux champs :
 *    revisiter Assistant faisait donc disparaître tous les tableaux
 *    précédemment affichés, remplacés par la même liste en prose.
 *
 * En gardant `messages` ici plutôt que dans le composant, les deux
 * bugs disparaissent : l'échange en vol se résout toujours (le store
 * survit au démontage), et une revisite ne recharge l'historique que
 * si on n'a RIEN en mémoire (premier chargement de l'app), jamais pour
 * écraser une conversation déjà en cours. */
let messages: ChatMessage[] = [];
const listeners = new Set<() => void>();

function notify(): void {
  listeners.forEach((listener) => listener());
}

export function getChatMessages(): ChatMessage[] {
  return messages;
}

export function setChatMessages(updater: ChatMessage[] | ((prev: ChatMessage[]) => ChatMessage[])): void {
  messages = typeof updater === "function" ? (updater as (prev: ChatMessage[]) => ChatMessage[])(messages) : updater;
  notify();
}

export function useChatMessages(): [ChatMessage[], typeof setChatMessages] {
  const [snapshot, setSnapshot] = useState(messages);
  useEffect(() => {
    const listener = () => setSnapshot(messages);
    listeners.add(listener);
    // Une mise à jour a pu arriver entre le rendu initial (snapshot pris
    // avant le montage de cet effet) et cet abonnement : resynchronise
    // une fois, au cas où.
    setSnapshot(messages);
    return () => {
      listeners.delete(listener);
    };
  }, []);
  return [snapshot, setChatMessages];
}
