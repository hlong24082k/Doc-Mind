import React, { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ArrowLeft, MessageSquare, Plus, Send, Square, Trash2 } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import AssistantMessage from "@/components/chat/AssistantMessage";
import ConversationList from "@/components/chat/ConversationList";
import NewChatDialog from "@/components/chat/NewChatDialog";
import { useChatStream } from "@/hooks/useChatStream";
import { useToast } from "@/hooks/use-toast";
import { conversationService } from "@/api/services/conversation.service";
import type { Conversation, ConversationDetail } from "@/api/types/conversation";
import { cn } from "@/lib/utils";

const MAX_CHARS = 2000;
const MAX_ROWS = 6;
const STICK_PX = 80;

const ChatPage: React.FC = () => {
  const { conversationId } = useParams<{ conversationId: string }>();
  const navigate = useNavigate();
  const { toast } = useToast();
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [listLoading, setListLoading] = useState(true);
  const [detail, setDetail] = useState<ConversationDetail | null>(null);
  const [threadLoading, setThreadLoading] = useState(false);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [input, setInput] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);
  const stickRef = useRef(true);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const loadList = useCallback(() => {
    conversationService
      .list()
      .then(setConversations)
      .catch(() => toast({ title: "Couldn't load chats", variant: "destructive" }))
      .finally(() => setListLoading(false));
  }, [toast]);

  useEffect(loadList, [loadList]);

  // sau `final` thì refetch list để cập nhật title / thứ tự
  const { messages, setMessages, phase, send, stop, retry } = useChatStream(conversationId, loadList);
  const streaming = phase === "searching" || phase === "writing";

  useEffect(() => {
    setDetail(null);
    setMessages([]);
    if (!conversationId) return;
    let cancelled = false;
    setThreadLoading(true);
    conversationService
      .get(conversationId)
      .then((d) => {
        if (cancelled) return;
        stickRef.current = true;
        setDetail(d);
        setMessages(d.messages);
      })
      .catch(() => {
        if (cancelled) return;
        toast({ title: "Chat not found", variant: "destructive" });
        navigate("/chat", { replace: true });
      })
      .finally(() => !cancelled && setThreadLoading(false));
    return () => {
      cancelled = true;
    };
  }, [conversationId, navigate, setMessages, toast]);

  // chỉ tự cuộn khi người dùng đang ở cuối danh sách
  const handleScroll = () => {
    const el = scrollRef.current;
    if (el) stickRef.current = el.scrollHeight - el.scrollTop - el.clientHeight <= STICK_PX;
  };
  useLayoutEffect(() => {
    const el = scrollRef.current;
    if (el && stickRef.current) el.scrollTop = el.scrollHeight;
  }, [messages]);

  // textarea tự giãn tới MAX_ROWS dòng
  useLayoutEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    const cs = getComputedStyle(el);
    const border = parseFloat(cs.borderTopWidth) + parseFloat(cs.borderBottomWidth);
    const padding = parseFloat(cs.paddingTop) + parseFloat(cs.paddingBottom);
    const max = (parseFloat(cs.lineHeight) || 20) * MAX_ROWS + padding + border;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight + border, max)}px`;
  }, [input, conversationId]);

  const submit = async () => {
    const text = input.trim();
    if (!text || streaming) return;
    setInput("");
    stickRef.current = true;
    if (!(await send(text))) setInput(text); // bị từ chối trước khi stream
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      submit();
    }
  };

  const handleDelete = async () => {
    if (!conversationId) return;
    try {
      await conversationService.remove(conversationId);
      navigate("/chat");
      loadList();
    } catch {
      toast({ title: "Couldn't delete the chat", variant: "destructive" });
    }
  };

  const handleCreated = (conversation: Conversation) => {
    setDialogOpen(false);
    navigate(`/chat/${conversation.id}`);
    loadList();
  };

  const current = conversations.find((c) => c.id === conversationId) ?? detail;

  return (
    <div className="grid h-[calc(100dvh-5.5rem)] gap-4 md:h-[calc(100dvh-2rem)] md:grid-cols-[260px_1fr] lg:h-[calc(100dvh-3rem)]">
      <aside className={cn("min-h-0 flex-col md:flex md:border-r md:pr-4", conversationId ? "hidden" : "flex")}>
        <ConversationList
          conversations={conversations}
          loading={listLoading}
          activeId={conversationId}
          onNew={() => setDialogOpen(true)}
        />
      </aside>

      <section className={cn("min-h-0 flex-col", conversationId ? "flex" : "hidden md:flex")}>
        {!conversationId ? (
          <div className="m-auto max-w-sm text-center">
            <MessageSquare className="mx-auto mb-3 h-8 w-8 text-muted-foreground" />
            <p className="font-medium">Pick a conversation or start a new one</p>
            <p className="mb-4 text-sm text-muted-foreground">
              A chat answers from the documents you choose and cites its pages.
            </p>
            <Button onClick={() => setDialogOpen(true)}>
              <Plus />
              New chat
            </Button>
          </div>
        ) : (
          <>
            <header className="flex items-start gap-2 border-b pb-3">
              <Button variant="ghost" size="icon" className="md:hidden" asChild>
                <Link to="/chat">
                  <ArrowLeft />
                  <span className="sr-only">Back to chats</span>
                </Link>
              </Button>
              <div className="min-w-0 flex-1">
                {current ? (
                  <>
                    <h2 className="truncate text-lg font-semibold">{current.title || "New chat"}</h2>
                    <div className="mt-1 flex flex-wrap gap-1">
                      {current.documents.map((d) => (
                        <Badge key={d.id} variant="secondary" title={d.title ?? undefined}>
                          {d.name}
                        </Badge>
                      ))}
                    </div>
                  </>
                ) : (
                  <Skeleton className="h-6 w-56" />
                )}
              </div>
              <AlertDialog>
                <AlertDialogTrigger asChild>
                  <Button variant="ghost" size="icon" aria-label="Delete chat">
                    <Trash2 />
                  </Button>
                </AlertDialogTrigger>
                <AlertDialogContent>
                  <AlertDialogHeader>
                    <AlertDialogTitle>Delete this chat?</AlertDialogTitle>
                    <AlertDialogDescription>
                      All messages in this chat will be removed. Your documents stay.
                    </AlertDialogDescription>
                  </AlertDialogHeader>
                  <AlertDialogFooter>
                    <AlertDialogCancel>Cancel</AlertDialogCancel>
                    <AlertDialogAction onClick={handleDelete}>Delete</AlertDialogAction>
                  </AlertDialogFooter>
                </AlertDialogContent>
              </AlertDialog>
            </header>

            <div ref={scrollRef} onScroll={handleScroll} className="min-h-0 flex-1 overflow-y-auto py-4 pr-1">
              {threadLoading ? (
                <div className="space-y-6">
                  <Skeleton className="ml-auto h-10 w-1/2" />
                  <div className="space-y-2">
                    <Skeleton className="h-4 w-3/4" />
                    <Skeleton className="h-4 w-2/3" />
                    <Skeleton className="h-4 w-1/2" />
                  </div>
                </div>
              ) : messages.length === 0 ? (
                <p className="m-auto max-w-sm pt-16 text-center text-sm text-muted-foreground">
                  Ask a question about the selected documents. Answers cite the pages they come from.
                </p>
              ) : (
                <div className="space-y-6">
                  {messages.map((m, i) =>
                    m.role === "user" ? (
                      <div key={m.id} className="flex justify-end">
                        <div className="max-w-[80%] whitespace-pre-wrap rounded-lg bg-primary px-4 py-2 text-primary-foreground">
                          {m.content}
                        </div>
                      </div>
                    ) : (
                      <AssistantMessage
                        key={m.id}
                        message={m}
                        phase={phase}
                        onRetry={i === messages.length - 1 && !streaming ? retry : undefined}
                      />
                    )
                  )}
                </div>
              )}
            </div>

            <form
              className="flex items-end gap-2 border-t pt-3"
              onSubmit={(e) => {
                e.preventDefault();
                submit();
              }}
            >
              <Textarea
                ref={textareaRef}
                rows={1}
                value={input}
                maxLength={MAX_CHARS}
                disabled={streaming || threadLoading}
                placeholder="Ask about the selected documents…"
                className="min-h-10 resize-none"
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
              />
              {streaming ? (
                <Button type="button" variant="outline" onClick={stop}>
                  <Square />
                  Stop
                </Button>
              ) : (
                <Button type="submit" disabled={!input.trim()}>
                  <Send />
                  Send
                </Button>
              )}
            </form>
          </>
        )}
      </section>

      <NewChatDialog open={dialogOpen} onOpenChange={setDialogOpen} onCreated={handleCreated} />
    </div>
  );
};

export default ChatPage;
