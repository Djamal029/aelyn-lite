export type ActivitySource =
  | "voice"
  | "text"
  | "vision"
  | "system"
  | "email"
  | "career"
  | "media";

export interface ActivityEntry {
  id: string;
  timestamp: string;
  message: string;
  source: ActivitySource;
}
