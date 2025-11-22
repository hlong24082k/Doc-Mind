import {
    DocumentsResponse,
} from '../types/document';
import {
    apiGetDocuments,
    apiUploadFile,
    apiDeleteDocument
} from '../config.ts';
import { apiFetch } from '../apiClient.ts';


/**
 * Handles authentication: login, refresh, logout.
 */
export const documentService = {
    async getDocuments(): Promise<DocumentsResponse> {
        const response = await apiFetch<DocumentsResponse>(apiGetDocuments, {
            method: "GET",
            auth: true,
        });
        return response;
    },

    async uploadFile(formData: FormData): Promise<DocumentsResponse> {
        const response = await apiFetch<DocumentsResponse>(apiUploadFile, {
            method: "POST",
            auth: true,
            body: formData,
        });
        return response;
    },

    async deleteDocument(documentId: string): Promise<boolean> {
        const response = await apiFetch<boolean>(apiDeleteDocument(documentId), {
            method: "DELETE",
            auth: true,
        });
        return response;
    }
};