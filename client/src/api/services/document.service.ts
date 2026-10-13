import {
    Document,
    DocumentsResponse,
    UploadResponse,
} from '../types/document';
import {
    apiGetDocuments,
    apiUploadFile,
    apiDeleteDocument,
    apiDocumentFile,
    apiReindexDocument,
} from '../config.ts';
import { apiFetch, apiFetchBlob } from '../apiClient.ts';


export const documentService = {
    async getDocuments(): Promise<DocumentsResponse> {
        return apiFetch<DocumentsResponse>(apiGetDocuments, {
            method: "GET",
            auth: true,
        });
    },

    async uploadFile(formData: FormData): Promise<UploadResponse> {
        return apiFetch<UploadResponse>(apiUploadFile, {
            method: "POST",
            auth: true,
            body: formData,
        });
    },

    async deleteDocument(documentId: string): Promise<void> {
        await apiFetch<void>(apiDeleteDocument(documentId), {
            method: "DELETE",
            auth: true,
        });
    },

    async reindex(documentId: string): Promise<Document> {
        return apiFetch<Document>(apiReindexDocument(documentId), {
            method: "POST",
            auth: true,
        });
    },

    /** Tải PDF kèm Bearer rồi mở ở tab mới (tại trang `page` nếu có). */
    async openFile(documentId: string, page?: number): Promise<void> {
        const blob = await apiFetchBlob(apiDocumentFile(documentId));
        const url = URL.createObjectURL(blob);
        window.open(url + (page ? `#page=${page}` : ""), "_blank");
        setTimeout(() => URL.revokeObjectURL(url), 60_000);
    },
};
