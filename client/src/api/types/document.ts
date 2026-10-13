export type DocumentStatus = "pending" | "processing" | "indexed" | "failed";

export type RejectReason =
    | "not_pdf"
    | "too_large"
    | "empty_name"
    | "busy"
    | "unchanged"
    | "quota_exceeded";

export interface Document {
    id: string;
    name: string;
    title: string | null;
    status: DocumentStatus;
    error: string | null;
    size_bytes: number;
    num_pages: number | null;
    num_chunks: number;
    created_at: string;
    indexed_at: string | null;
}

export interface Usage {
    bytes: number;
    documents: number;
    quota_bytes: number;
    quota_documents: number;
}

export interface DocumentsResponse {
    documents: Document[];
    usage: Usage;
}

export interface UploadResponse {
    documents: Document[];
    rejected: { filename: string; reason: RejectReason }[];
    usage: Usage;
}
