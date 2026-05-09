// ── Domain types mirroring backend Pydantic schemas ──────────────────────────

export interface DocumentMetadata {
  document_id: string;
  filename: string;
  file_size_bytes: number;
  page_count: number;
  chunk_count: number;
  uploaded_at: string;
  status: "processing" | "ready" | "error";
}

export interface SourceChunk {
  document_id: string;
  filename: string;
  page_number: number;
  chunk_text: string;
  relevance_score: number;
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  timestamp: string;
  sources?: SourceChunk[];
  processing_time_ms?: number;
  isError?: boolean;
}

export interface ChatRequest {
  session_id: string;
  document_ids: string[];
  question: string;
  chat_history: Array<{ role: string; content: string; timestamp: string }>;
}

export interface ChatResponse {
  session_id: string;
  answer: string;
  sources: SourceChunk[];
  model_used: string;
  tokens_used: number | null;
  processing_time_ms: number;
}

export interface UploadResponse {
  document_id: string;
  filename: string;
  message: string;
  chunk_count: number;
  page_count: number;
}

export type UploadStatus = "idle" | "uploading" | "success" | "error";
