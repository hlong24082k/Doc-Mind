import { Link } from "react-router-dom";
import { Plus } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import type { Conversation } from "@/api/types/conversation";
import { cn, timeAgo } from "@/lib/utils";

interface Props {
  conversations: Conversation[];
  loading: boolean;
  activeId?: string;
  onNew: () => void;
}

const ConversationList = ({ conversations, loading, activeId, onNew }: Props) => (
  <div className="flex min-h-0 flex-col gap-2">
    <Button variant="outline" className="justify-start" onClick={onNew}>
      <Plus />
      New chat
    </Button>
    <nav className="flex min-h-0 flex-1 flex-col gap-1 overflow-y-auto">
      {loading ? (
        [0, 1, 2].map((i) => (
          <div key={i} className="space-y-2 px-3 py-2">
            <Skeleton className="h-4 w-40" />
            <Skeleton className="h-3 w-24" />
          </div>
        ))
      ) : conversations.length === 0 ? (
        <div className="px-3 py-6 text-sm">
          <p className="font-medium">No chats yet</p>
          <p className="text-muted-foreground">Start one from your documents.</p>
        </div>
      ) : (
        conversations.map((c) => (
          <Link
            key={c.id}
            to={`/chat/${c.id}`}
            className={cn(
              "rounded-lg px-3 py-2 text-sm transition-colors hover:bg-muted",
              c.id === activeId && "bg-muted"
            )}
          >
            <div className="truncate font-medium">{c.title || "Untitled chat"}</div>
            <div className="text-xs text-muted-foreground">
              {c.documents.length} {c.documents.length === 1 ? "doc" : "docs"} · {timeAgo(c.updated_at)}
            </div>
          </Link>
        ))
      )}
    </nav>
  </div>
);

export default ConversationList;
