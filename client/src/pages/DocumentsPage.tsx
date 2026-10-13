import React, { useCallback, useEffect, useRef, useState } from "react";
import { ExternalLink, MessageSquare, RotateCw, Search, Trash2, Upload } from "lucide-react";
import { useNavigate } from "react-router-dom";

import { useToast } from "@/hooks/use-toast";
import { cn, formatMB, parseServerDate, timeAgo } from "@/lib/utils";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import DocumentStatusBadge from "@/components/documents/DocumentStatusBadge";
import { ApiError } from "@/api/apiClient";
import type { Document, DocumentStatus, RejectReason, Usage } from "@/api/types/document";
import { documentService } from "@/api/services/document.service";
import { conversationService } from "@/api/services/conversation.service";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
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

// Khớp với settings server (upload_max_mb, upload_max_files); server vẫn kiểm tra lại
const UPLOAD_MAX_MB = 25;
const UPLOAD_MAX_FILES = 10;
const MAX_SELECTED = 10;
const POLL_MS = 3000;
const COLUMNS = 6;

type SkipReason = RejectReason | "too_many";

const REASON_LABEL: Record<SkipReason, string> = {
  not_pdf: "not a PDF",
  too_large: `larger than ${UPLOAD_MAX_MB} MB`,
  empty_name: "invalid file name",
  busy: "still processing",
  unchanged: "unchanged",
  quota_exceeded: "storage quota reached",
  too_many: `more than ${UPLOAD_MAX_FILES} files at once`,
};

const UPLOAD_ERRORS: Record<number, string> = {
  409: "Storage quota reached, delete documents to free space",
  413: "Upload is too large, send fewer files at once",
  503: "Too many uploads right now, try again in a few seconds",
  507: "Server storage is full, contact the administrator",
};

const isActive = (status: DocumentStatus) => status === "pending" || status === "processing";

const DocumentsPage: React.FC = () => {
  const [documents, setDocuments] = useState<Document[]>([]);
  const [usage, setUsage] = useState<Usage | null>(null);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [search, setSearch] = useState("");
  const statusRef = useRef<Map<string, DocumentStatus>>(new Map());
  const fileInputRef = useRef<HTMLInputElement>(null);
  const navigate = useNavigate();
  const { toast } = useToast();

  const refresh = useCallback(async () => {
    const res = await documentService.getDocuments();
    // so với snapshot trước để báo khi một document xong
    for (const doc of res.documents) {
      const before = statusRef.current.get(doc.id);
      if (before && isActive(before) && !isActive(doc.status)) {
        toast(
          doc.status === "indexed"
            ? { title: `${doc.name} is ready` }
            : { title: `${doc.name} failed`, description: doc.error ?? undefined, variant: "destructive" }
        );
      }
    }
    statusRef.current = new Map(res.documents.map((d) => [d.id, d.status]));
    setDocuments(res.documents);
    setUsage(res.usage);
    const ready = new Set(res.documents.filter((d) => d.status === "indexed").map((d) => d.id));
    setSelected((prev) => new Set([...prev].filter((id) => ready.has(id))));
  }, [toast]);

  useEffect(() => {
    refresh()
      .catch(() => toast({ title: "Couldn't load documents", variant: "destructive" }))
      .finally(() => setLoading(false));
  }, [refresh, toast]);

  const hasActive = documents.some((d) => isActive(d.status));
  useEffect(() => {
    if (!hasActive) return;
    const id = setInterval(() => {
      if (!document.hidden) refresh().catch(() => undefined);
    }, POLL_MS);
    return () => clearInterval(id);
  }, [hasActive, refresh]);

  const handleFileChange = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const picked = Array.from(event.target.files ?? []);
    event.target.value = "";
    if (picked.length === 0) return;

    const skipped: { filename: string; reason: SkipReason }[] = [];
    const valid: File[] = [];
    for (const file of picked) {
      if (!file.name.toLowerCase().endsWith(".pdf")) skipped.push({ filename: file.name, reason: "not_pdf" });
      else if (file.size > UPLOAD_MAX_MB * 2 ** 20) skipped.push({ filename: file.name, reason: "too_large" });
      else if (valid.length >= UPLOAD_MAX_FILES) skipped.push({ filename: file.name, reason: "too_many" });
      else valid.push(file);
    }

    let queued = 0;
    if (valid.length > 0) {
      const formData = new FormData();
      valid.forEach((file) => formData.append("files", file));
      setUploading(true);
      try {
        const res = await documentService.uploadFile(formData);
        queued = res.documents.length;
        skipped.push(...res.rejected);
        await refresh();
      } catch (error) {
        const status = error instanceof ApiError ? error.status : 0;
        toast({
          title: "Upload failed",
          description: UPLOAD_ERRORS[status] ?? "Something went wrong, try again",
          variant: "destructive",
        });
        return;
      } finally {
        setUploading(false);
      }
    }

    const details = skipped.map((s) => `${s.filename}: ${REASON_LABEL[s.reason]}`).join("\n");
    if (queued > 0) {
      toast({
        title: `${queued} queued for processing`,
        description: details ? <span className="whitespace-pre-line">Skipped:{"\n"}{details}</span> : undefined,
      });
    } else if (skipped.length > 0) {
      toast({
        title: "No files uploaded",
        description: <span className="whitespace-pre-line">{details}</span>,
        variant: "destructive",
      });
    }
  };

  const startChat = async (documentIds: string[]) => {
    try {
      const conversation = await conversationService.create({ document_ids: documentIds });
      navigate(`/chat/${conversation.id}`);
    } catch (error) {
      const notReady = error instanceof ApiError && error.status === 409;
      toast({
        title: notReady ? "Some documents are not ready yet" : "Couldn't start the chat",
        variant: "destructive",
      });
    }
  };

  const handleRetry = async (documentId: string) => {
    try {
      await documentService.reindex(documentId);
      await refresh();
    } catch {
      toast({ title: "Couldn't retry this document", variant: "destructive" });
    }
  };

  const handleOpen = (documentId: string) => {
    documentService.openFile(documentId).catch(() =>
      toast({ title: "Couldn't open the file", description: "Upload it again to restore it.", variant: "destructive" })
    );
  };

  const handleDelete = async (documentId: string) => {
    try {
      await documentService.deleteDocument(documentId);
      await refresh();
      toast({ title: "Document deleted" });
    } catch {
      toast({ title: "Couldn't delete the document", variant: "destructive" });
    }
  };

  const toggleSelected = (documentId: string) =>
    setSelected((prev) => {
      const next = new Set(prev);
      if (!next.delete(documentId)) next.add(documentId);
      return next;
    });

  const term = search.trim().toLowerCase();
  const filteredDocuments = documents.filter(
    (doc) => doc.name.toLowerCase().includes(term) || (doc.title ?? "").toLowerCase().includes(term)
  );
  const nearQuota =
    usage !== null &&
    (usage.bytes > usage.quota_bytes * 0.9 || usage.documents > usage.quota_documents * 0.9);
  const openUpload = () => fileInputRef.current?.click();

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold">Documents</h1>
          {usage && (
            <p className={cn("text-sm", nearQuota ? "text-destructive" : "text-muted-foreground")}>
              {formatMB(usage.bytes)} of {formatMB(usage.quota_bytes)} used, {usage.documents} of{" "}
              {usage.quota_documents} documents
            </p>
          )}
        </div>
        <div className="flex flex-wrap gap-2">
          {selected.size > 0 && (
            <Button variant="outline" onClick={() => startChat([...selected])}>
              <MessageSquare />
              Chat with {selected.size} selected
            </Button>
          )}
          <Button onClick={openUpload} disabled={uploading}>
            <Upload />
            {uploading ? "Uploading…" : "Upload PDF"}
          </Button>
          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf,application/pdf"
            multiple
            className="hidden"
            onChange={handleFileChange}
          />
        </div>
      </div>

      <div className="relative">
        <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          type="text"
          placeholder="Search documents…"
          className="pl-9"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </div>

      <div className="rounded-lg border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-10">
                <span className="sr-only">Select</span>
              </TableHead>
              <TableHead>Name</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Pages</TableHead>
              <TableHead>Uploaded</TableHead>
              <TableHead className="text-right">
                <span className="sr-only">Actions</span>
              </TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {loading ? (
              [0, 1, 2].map((i) => (
                <TableRow key={i}>
                  <TableCell><Skeleton className="h-4 w-4" /></TableCell>
                  <TableCell><Skeleton className="h-4 w-48" /></TableCell>
                  <TableCell><Skeleton className="h-5 w-20" /></TableCell>
                  <TableCell><Skeleton className="h-4 w-6" /></TableCell>
                  <TableCell><Skeleton className="h-4 w-16" /></TableCell>
                  <TableCell><Skeleton className="ml-auto h-8 w-28" /></TableCell>
                </TableRow>
              ))
            ) : documents.length === 0 ? (
              <TableRow>
                <TableCell colSpan={COLUMNS} className="py-12 text-center">
                  <p className="font-medium">No documents yet</p>
                  <p className="mb-4 text-sm text-muted-foreground">
                    Upload a PDF to start asking questions about it.
                  </p>
                  <Button onClick={openUpload} disabled={uploading}>
                    <Upload />
                    Upload PDF
                  </Button>
                </TableCell>
              </TableRow>
            ) : filteredDocuments.length === 0 ? (
              <TableRow>
                <TableCell colSpan={COLUMNS} className="h-24 text-center text-muted-foreground">
                  No documents match your search.
                </TableCell>
              </TableRow>
            ) : (
              filteredDocuments.map((doc) => {
                const ready = doc.status === "indexed";
                const isSelected = selected.has(doc.id);
                return (
                  <TableRow key={doc.id}>
                    <TableCell>
                      <input
                        type="checkbox"
                        className="accent-primary"
                        aria-label={`Select ${doc.name}`}
                        checked={isSelected}
                        disabled={!ready || (!isSelected && selected.size >= MAX_SELECTED)}
                        onChange={() => toggleSelected(doc.id)}
                      />
                    </TableCell>
                    <TableCell className="max-w-[28rem]">
                      <div className="truncate font-medium">{doc.name}</div>
                      {doc.title && (
                        <div className="truncate text-xs text-muted-foreground">{doc.title}</div>
                      )}
                      {doc.status === "failed" && doc.error && (
                        <div className="truncate text-xs text-destructive/80" title={doc.error}>
                          {doc.error}
                        </div>
                      )}
                    </TableCell>
                    <TableCell>
                      <DocumentStatusBadge doc={doc} />
                    </TableCell>
                    <TableCell>{doc.num_pages ?? "–"}</TableCell>
                    <TableCell>
                      <span title={parseServerDate(doc.created_at).toISOString()}>
                        {timeAgo(doc.created_at)}
                      </span>
                    </TableCell>
                    <TableCell>
                      <div className="flex justify-end gap-1">
                        {doc.status === "failed" ? (
                          <Button variant="ghost" size="sm" onClick={() => handleRetry(doc.id)}>
                            <RotateCw />
                            Retry
                          </Button>
                        ) : (
                          <Button
                            variant="ghost"
                            size="sm"
                            disabled={!ready}
                            onClick={() => startChat([doc.id])}
                          >
                            <MessageSquare />
                            Chat
                          </Button>
                        )}
                        {ready && (
                          <Button variant="ghost" size="sm" onClick={() => handleOpen(doc.id)}>
                            <ExternalLink />
                            Open
                          </Button>
                        )}
                        <AlertDialog>
                          <AlertDialogTrigger asChild>
                            <Button variant="ghost" size="sm" aria-label={`Delete ${doc.name}`}>
                              <Trash2 />
                            </Button>
                          </AlertDialogTrigger>
                          <AlertDialogContent>
                            <AlertDialogHeader>
                              <AlertDialogTitle>Delete this document?</AlertDialogTitle>
                              <AlertDialogDescription>
                                <span className="font-medium">{doc.name}</span> and its index will be
                                removed. Chats that use it lose access to it.
                              </AlertDialogDescription>
                            </AlertDialogHeader>
                            <AlertDialogFooter>
                              <AlertDialogCancel>Cancel</AlertDialogCancel>
                              <AlertDialogAction onClick={() => handleDelete(doc.id)}>Delete</AlertDialogAction>
                            </AlertDialogFooter>
                          </AlertDialogContent>
                        </AlertDialog>
                      </div>
                    </TableCell>
                  </TableRow>
                );
              })
            )}
          </TableBody>
        </Table>
      </div>
    </div>
  );
};

export default DocumentsPage;
