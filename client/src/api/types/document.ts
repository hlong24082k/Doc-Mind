export interface DocumentsResponse {
    documents: Document[];
}

export interface Document {
    _id: string;
    user_id: string;
    name: string;
    created_at: string;
}