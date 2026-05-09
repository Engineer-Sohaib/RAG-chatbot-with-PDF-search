/**
 * API Service
 * ────────────
 * Typed wrappers around every backend endpoint.
 * All errors are normalised to ApiError for consistent handling in components.
 */

import type {
  ChatRequest,
  ChatResponse,
  DocumentMetadata,
  UploadResponse,
} from "../types";

const BASE_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public detail?: string
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(
  path: string,
  init?: RequestInit
): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json", ...init?.headers },
    ...init,
  });

  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ?? detail;
    } catch {
      // ignore JSON parse failure
    }
    throw new ApiError(`Request failed: ${detail}`, res.status, detail);
  }

  // Handle 204 No Content
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

// ── Documents ─────────────────────────────────────────────────────────────────

export async function uploadDocument(file: File): Promise<UploadResponse> {
  const form = new FormData();
  form.append("file", file);
  return request<UploadResponse>("/api/documents/upload", {
    method: "POST",
    // Let the browser set Content-Type with boundary for multipart
    headers: {},
    body: form,
  });
}

export async function listDocuments(): Promise<DocumentMetadata[]> {
  const res = await request<{ documents: DocumentMetadata[]; total: number }>(
    "/api/documents/"
  );
  return res.documents;
}

export async function deleteDocument(documentId: string): Promise<void> {
  await request(`/api/documents/${documentId}`, { method: "DELETE" });
}

// ── Chat ──────────────────────────────────────────────────────────────────────

export async function sendMessage(payload: ChatRequest): Promise<ChatResponse> {
  return request<ChatResponse>("/api/chat/query", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

// ── Health ────────────────────────────────────────────────────────────────────

export async function checkHealth(): Promise<{ status: string }> {
  return request("/api/health");
}

export { ApiError };
