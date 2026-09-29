export const BASE_URL = import.meta.env.VITE_API_BASE_URL;

// ----------- auth --------------
export const apiAuthLogin = `${BASE_URL}/auth/login`;
export const apiRegister = `${BASE_URL}/auth/register`;

// ----------- document --------------
export const apiGetDocuments = `${BASE_URL}/document`;
export const apiUploadFile = `${BASE_URL}/document/uploadfile`;
export const apiDeleteDocument = (documentId: string) => `${BASE_URL}/document/${documentId}`;