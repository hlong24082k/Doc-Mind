import type {
  ChatEvent,
  Conversation,
  ConversationDetail,
  ConversationsResponse,
} from "../types/conversation";
import {
  apiConversation,
  apiConversationMessages,
  apiConversations,
} from "../config.ts";
import { apiFetch, apiStream } from "../apiClient.ts";

export const conversationService = {
  async list(): Promise<Conversation[]> {
    const res = await apiFetch<ConversationsResponse>(apiConversations);
    return res.conversations;
  },

  async get(id: string): Promise<ConversationDetail> {
    return apiFetch<ConversationDetail>(apiConversation(id));
  },

  async create(body: { document_ids: string[]; title?: string }): Promise<Conversation> {
    return apiFetch<Conversation>(apiConversations, { method: "POST", json: body });
  },

  async remove(id: string): Promise<void> {
    await apiFetch<void>(apiConversation(id), { method: "DELETE" });
  },

  sendMessage(
    id: string,
    content: string,
    opts: { signal?: AbortSignal; onEvent: (event: ChatEvent) => void }
  ): Promise<void> {
    return apiStream(apiConversationMessages(id), {
      json: { content },
      signal: opts.signal,
      onEvent: (event, data) => opts.onEvent({ event, data } as ChatEvent),
    });
  },
};
