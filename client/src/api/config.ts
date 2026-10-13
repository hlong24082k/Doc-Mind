export const BASE_URL = import.meta.env.VITE_API_BASE_URL;

// ----------- auth --------------
export const apiAuthLogin = `${BASE_URL}/auth/login`;
export const apiRegister = `${BASE_URL}/auth/register`;

// ----------- document --------------
export const apiGetDocuments = `${BASE_URL}/document`;
export const apiUploadFile = `${BASE_URL}/document/uploadfile`;
export const apiDeleteDocument = (documentId: string) => `${BASE_URL}/document/${documentId}`;
export const apiDocumentFile = (documentId: string) => `${BASE_URL}/document/${documentId}/file`;
export const apiReindexDocument = (documentId: string) => `${BASE_URL}/document/${documentId}/reindex`;

// ----------- conversation --------------
export const apiConversations = `${BASE_URL}/conversation/`;
export const apiConversation = (conversationId: string) => `${BASE_URL}/conversation/${conversationId}`;
export const apiConversationMessages = (conversationId: string) =>
  `${BASE_URL}/conversation/${conversationId}/messages`;
