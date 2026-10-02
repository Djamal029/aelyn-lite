/** Minimal ambient types for the Web Speech API's `SpeechRecognition`,
 * not part of TypeScript's DOM lib, and only vendor-prefixed in the
 * browsers that implement it (Chrome/Edge; not Firefox). Declares only
 * the shape lib/useSpeechRecognition.ts actually uses. */
export {};

declare global {
  interface SpeechRecognitionResultLike {
    isFinal: boolean;
    [index: number]: { transcript: string };
  }

  interface SpeechRecognitionEventLike extends Event {
    resultIndex: number;
    results: ArrayLike<SpeechRecognitionResultLike>;
  }

  interface SpeechRecognitionErrorEventLike extends Event {
    error: string;
  }

  interface SpeechRecognitionLike extends EventTarget {
    lang: string;
    interimResults: boolean;
    continuous: boolean;
    maxAlternatives: number;
    start(): void;
    stop(): void;
    abort(): void;
    onresult: ((event: SpeechRecognitionEventLike) => void) | null;
    onerror: ((event: SpeechRecognitionErrorEventLike) => void) | null;
    onend: (() => void) | null;
    onstart: (() => void) | null;
  }

  interface Window {
    SpeechRecognition?: new () => SpeechRecognitionLike;
    webkitSpeechRecognition?: new () => SpeechRecognitionLike;
  }
}
