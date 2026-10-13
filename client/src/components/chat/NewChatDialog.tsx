import { useEffect, useState } from "react";
import { Search } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { useToast } from "@/hooks/use-toast";
import { documentService } from "@/api/services/document.service";
import { conversationService } from "@/api/services/conversation.service";
import type { Document } from "@/api/types/document";
import type { Conversation } from "@/api/types/conversation";

const MAX_SELECTED = 10;

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreated: (conversation: Conversation) => void;
}

const NewChatDialog = ({ open, onOpenChange, onCreated }: Props) => {
  const [documents, setDocuments] = useState<Document[] | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [search, setSearch] = useState("");
  const [creating, setCreating] = useState(false);
  const { toast } = useToast();

  useEffect(() => {
    if (!open) return;
    setDocuments(null);
    setSelected(new Set());
    setSearch("");
    documentService
      .getDocuments()
      .then((res) => setDocuments(res.documents.filter((d) => d.status === "indexed")))
      .catch(() => {
        setDocuments([]);
        toast({ title: "Couldn't load documents", variant: "destructive" });
      });
  }, [open, toast]);

  const toggle = (id: string) =>
    setSelected((prev) => {
      const next = new Set(prev);
      if (!next.delete(id)) next.add(id);
      return next;
    });

  const start = async () => {
    setCreating(true);
    try {
      onCreated(await conversationService.create({ document_ids: [...selected] }));
    } catch {
      toast({ title: "Couldn't start the chat", variant: "destructive" });
    } finally {
      setCreating(false);
    }
  };

  const term = search.trim().toLowerCase();
  const visible = (documents ?? []).filter(
    (d) => d.name.toLowerCase().includes(term) || (d.title ?? "").toLowerCase().includes(term)
  );

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>New chat</DialogTitle>
          <DialogDescription>Pick up to {MAX_SELECTED} ready documents to ask about.</DialogDescription>
        </DialogHeader>
        <div className="relative">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            placeholder="Search documents…"
            className="pl-9"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <div className="max-h-72 space-y-1 overflow-y-auto">
          {documents === null ? (
            [0, 1, 2].map((i) => <Skeleton key={i} className="h-9 w-full" />)
          ) : visible.length === 0 ? (
            <p className="py-6 text-center text-sm text-muted-foreground">
              {documents.length === 0 ? "No ready documents. Upload a PDF first." : "No documents match your search."}
            </p>
          ) : (
            visible.map((d) => {
              const checked = selected.has(d.id);
              return (
                <label
                  key={d.id}
                  className="flex cursor-pointer items-center gap-3 rounded-lg px-2 py-2 text-sm transition-colors hover:bg-muted"
                >
                  <input
                    type="checkbox"
                    className="accent-primary"
                    checked={checked}
                    disabled={!checked && selected.size >= MAX_SELECTED}
                    onChange={() => toggle(d.id)}
                  />
                  <span className="min-w-0">
                    <span className="block truncate font-medium">{d.name}</span>
                    {d.title && <span className="block truncate text-xs text-muted-foreground">{d.title}</span>}
                  </span>
                </label>
              );
            })
          )}
        </div>
        <DialogFooter>
          <Button disabled={selected.size === 0 || creating} onClick={start}>
            {creating ? "Starting…" : "Start chat"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export default NewChatDialog;
