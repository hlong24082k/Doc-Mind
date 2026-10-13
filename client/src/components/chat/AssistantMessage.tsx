import { useState } from "react";
import { ChevronRight, Info, RotateCw } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useToast } from "@/hooks/use-toast";
import type { ChatMessage, Phase } from "@/hooks/useChatStream";
import type { Source } from "@/api/types/conversation";
import { documentService } from "@/api/services/document.service";
import { cn } from "@/lib/utils";

const CITATION = /(\[\d+\])/;

interface Props {
  message: ChatMessage;
  phase: Phase;
  onRetry?: () => void; // chỉ có ở message cuối
}

const pages = (s: Source) => (s.page_start === s.page_end ? `${s.page_start}` : `${s.page_start}-${s.page_end}`);

const AssistantMessage = ({ message, phase, onRetry }: Props) => {
  const [showAll, setShowAll] = useState(false);
  const [expanded, setExpanded] = useState<Set<number>>(new Set());
  const [highlight, setHighlight] = useState<number | null>(null);
  const { toast } = useToast();

  const sources = message.refused ? [] : message.sources ?? [];
  const byRef = new Map(sources.map((s) => [s.ref, s]));
  const cited = sources.filter((s) => s.cited);
  const rest = sources.filter((s) => !s.cited);
  const streaming = message.status === "streaming";
  const anchor = (ref: number) => `source-${message.id}-${ref}`;

  const focusSource = (ref: number) => {
    if (!byRef.get(ref)?.cited) setShowAll(true);
    setHighlight(ref);
    requestAnimationFrame(() => document.getElementById(anchor(ref))?.scrollIntoView({ block: "nearest" }));
    window.setTimeout(() => setHighlight((h) => (h === ref ? null : h)), 1500);
  };

  const toggleExpanded = (ref: number) =>
    setExpanded((prev) => {
      const next = new Set(prev);
      if (!next.delete(ref)) next.add(ref);
      return next;
    });

  const openSource = (s: Source) =>
    documentService
      .openFile(s.document_id, s.page_start)
      .catch(() => toast({ title: "Couldn't open the file", variant: "destructive" }));

  if (message.refused) {
    return (
      <div className="flex max-w-[70ch] items-start gap-2 text-muted-foreground">
        <Info className="mt-1 h-4 w-4 shrink-0" />
        <p className="whitespace-pre-wrap leading-relaxed">{message.content}</p>
      </div>
    );
  }

  return (
    <div className="max-w-[70ch]">
      {streaming && !message.content ? (
        <p className="text-sm text-muted-foreground">
          {phase === "searching" ? "Searching documents…" : "Writing answer…"}
        </p>
      ) : (
        <p className="whitespace-pre-wrap leading-relaxed">
          {message.content.split(CITATION).map((part, i) => {
            const ref = Number(part.match(/^\[(\d+)\]$/)?.[1]);
            if (!byRef.has(ref)) return part;
            return (
              <button
                key={i}
                type="button"
                className="mx-0.5 rounded-sm bg-muted px-1 align-super text-xs transition-colors hover:bg-accent"
                onClick={() => focusSource(ref)}
              >
                {ref}
              </button>
            );
          })}
          {streaming && <span className="motion-safe:animate-pulse">▍</span>}
        </p>
      )}

      {sources.length > 0 && (
        <div className="mt-3 space-y-1">
          <p className="text-xs font-medium text-muted-foreground">Sources</p>
          {(showAll ? [...cited, ...rest] : cited).map((s) => {
            const open = expanded.has(s.ref);
            return (
              <div
                key={s.ref}
                id={anchor(s.ref)}
                className={cn(
                  "rounded-lg px-2 py-1 text-sm transition-colors",
                  highlight === s.ref && "bg-muted ring-1 ring-ring"
                )}
              >
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    aria-expanded={open}
                    className="flex min-w-0 flex-1 items-center gap-2 text-left"
                    onClick={() => toggleExpanded(s.ref)}
                  >
                    <ChevronRight className={cn("h-3 w-3 shrink-0", open && "rotate-90")} />
                    <span className="shrink-0 font-medium">[{s.ref}]</span>
                    <span className="truncate">
                      {s.document_title || s.document_name} · p. {pages(s)}
                      {s.section ? ` · ${s.section}` : ""}
                    </span>
                  </button>
                  <Button variant="ghost" size="sm" className="h-7 px-2" onClick={() => openSource(s)}>
                    Open
                  </Button>
                </div>
                {open && <p className="mt-1 whitespace-pre-wrap pl-5 text-xs text-muted-foreground">{s.snippet}</p>}
              </div>
            );
          })}
          {!showAll && rest.length > 0 && (
            <button
              type="button"
              className="px-2 text-xs text-muted-foreground transition-colors hover:text-foreground"
              onClick={() => setShowAll(true)}
            >
              Show {rest.length} more
            </button>
          )}
        </div>
      )}

      {message.grounded === false && (
        <p className="mt-2 text-xs text-muted-foreground">Some statements could not be matched to a source.</p>
      )}
      {message.status === "stopped" && <p className="mt-2 text-xs text-muted-foreground">Stopped</p>}
      {message.status === "error" && (
        <div className="mt-2 flex items-center gap-2 text-sm text-destructive">
          Couldn't finish this answer.
          {onRetry && (
            <Button variant="outline" size="sm" className="h-7 px-2" onClick={onRetry}>
              <RotateCw />
              Retry
            </Button>
          )}
        </div>
      )}
    </div>
  );
};

export default AssistantMessage;
