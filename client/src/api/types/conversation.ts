import type { DocumentStatus } from "./document";

export interface DocumentRef {
  id: string;
  name: string;
  title: string | null;
  status: DocumentStatus;
}

export interface Conversation {
  id: string;
  title: string | null;
  documents: DocumentRef[];
  created_at: string;
  updated_at: string;
}

export interface Source {
  ref: number;
  document_id: string;
  document_name: string;
  document_title: string | null;
  page_start: number;
  page_end: number;
  section: string | null;
  snippet: string;
  cited: boolean;
}

export interface Message {
  id: number;
  role: "user" | "assistant";
  content: string;
  sources: Source[] | null;
  grounded: boolean | null;
  refused: boolean | null;
  created_at: string;
}

export interface ConversationDetail extends Conversation {
  messages: Message[];
}

export interface ConversationsResponse {
  conversations: Conversation[];
}

export type ChatEvent =
  | { event: "meta"; data: { standalone_query: string } }
  | { event: "contexts"; data: { sources: Source[] } }
  | { event: "token"; data: { text: string } }
  | { event: "final"; data: { message: Message; timings_ms: Record<string, number> } }
  | { event: "error"; data: { detail: string } };
