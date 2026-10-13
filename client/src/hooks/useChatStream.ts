import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError } from "@/api/apiClient";
import { conversationService } from "@/api/services/conversation.service";
import type { Message } from "@/api/types/conversation";
import { useToast } from "@/hooks/use-toast";

export type Phase = "idle" | "searching" | "writing" | "error";

/** Message trên client: thêm trạng thái của bản nháp đang stream. */
export interface ChatMessage extends Message {
  status?: "streaming" | "stopped" | "error";
}

const REQUEST_ERRORS: Record<number, string> = {
  409: "Documents in this chat are no longer available.",
  429: "A reply is already in progress.",
  503: "Server is busy, try again in a few seconds.",
};

let tempId = 0;
const nextTempId = () => --tempId; // id âm: chưa lưu trên server

/**
 * State machine cho một lượt chat:
 * send → "searching" → contexts → "writing" → token… → final → "idle".
 * error / lỗi mạng → "error" (giữ phần text đã nhận); stop() → "stopped".
 */
export function useChatStream(conversationId: string | undefined, onFinal?: () => void) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [phase, setPhase] = useState<Phase>("idle");
  const abortRef = useRef<AbortController | null>(null);
  const lastContentRef = useRef("");
  const { toast } = useToast();

  // đổi hội thoại / unmount → hủy stream đang chạy
  useEffect(
    () => () => {
      abortRef.current?.abort();
      abortRef.current = null;
    },
    [conversationId]
  );

  const updateDraft = (draftId: number, patch: (m: ChatMessage) => Partial<ChatMessage>) =>
    setMessages((prev) => prev.map((m) => (m.id === draftId ? { ...m, ...patch(m) } : m)));

  /** Trả về false nếu server từ chối trước khi stream (409/429/503). */
  const send = useCallback(
    async (content: string): Promise<boolean> => {
      if (!conversationId || abortRef.current) return false;
      lastContentRef.current = content;
      const now = new Date().toISOString();
      const userId = nextTempId();
      const draftId = nextTempId();
      setMessages((prev) => [
        ...prev,
        { id: userId, role: "user", content, sources: null, grounded: null, refused: null, created_at: now },
        {
          id: draftId,
          role: "assistant",
          content: "",
          sources: null,
          grounded: null,
          refused: null,
          created_at: now,
          status: "streaming",
        },
      ]);
      setPhase("searching");

      const controller = new AbortController();
      abortRef.current = controller;
      let finished = false;
      try {
        await conversationService.sendMessage(conversationId, content, {
          signal: controller.signal,
          onEvent: (ev) => {
            switch (ev.event) {
              case "meta":
                console.debug("standalone query:", ev.data.standalone_query);
                break;
              case "contexts":
                updateDraft(draftId, () => ({ sources: ev.data.sources }));
                setPhase("writing");
                break;
              case "token":
                updateDraft(draftId, (m) => ({ content: m.content + ev.data.text }));
                break;
              case "final":
                finished = true;
                setMessages((prev) => prev.map((m) => (m.id === draftId ? ev.data.message : m)));
                setPhase("idle");
                onFinal?.();
                break;
              case "error":
                finished = true;
                updateDraft(draftId, () => ({ status: "error" }));
                setPhase("error");
                break;
            }
          },
        });
        if (!finished) throw new Error("Stream ended before the answer was complete");
        return true;
      } catch (error) {
        if (controller.signal.aborted) {
          updateDraft(draftId, () => ({ status: "stopped" }));
          setPhase("idle");
          return true;
        }
        if (error instanceof ApiError && REQUEST_ERRORS[error.status]) {
          setMessages((prev) => prev.filter((m) => m.id !== userId && m.id !== draftId));
          setPhase("idle");
          toast({ title: REQUEST_ERRORS[error.status], variant: "destructive" });
          return false;
        }
        updateDraft(draftId, () => ({ status: "error" }));
        setPhase("error");
        return true;
      } finally {
        if (abortRef.current === controller) abortRef.current = null;
      }
    },
    [conversationId, onFinal, toast]
  );

  const stop = useCallback(() => abortRef.current?.abort(), []);

  /** Gửi lại câu hỏi cuối, bỏ cặp message lỗi. */
  const retry = useCallback(() => {
    setMessages((prev) => {
      const draftIdx = prev.length - 1;
      return prev[draftIdx]?.status === "error" ? prev.slice(0, draftIdx - 1) : prev;
    });
    return send(lastContentRef.current);
  }, [send]);

  return { messages, setMessages, phase, send, stop, retry };
}
