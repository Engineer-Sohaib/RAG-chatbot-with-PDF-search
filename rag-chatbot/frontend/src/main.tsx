import React, { useState, useEffect, useRef, useCallback } from "react";
import ReactDOM from "react-dom/client";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { useDropzone } from "react-dropzone";
import { v4 as uuidv4 } from "uuid";

// ── Types ─────────────────────────────────────────────────────────────────────

interface DocumentMetadata {
  document_id: string;
  filename: string;
  file_size_bytes: number;
  page_count: number;
  chunk_count: number;
  uploaded_at: string;
  status: "processing" | "ready" | "error";
}

interface SourceChunk {
  document_id: string;
  filename: string;
  page_number: number;
  chunk_text: string;
  relevance_score: number;
}

interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: string;
  sources?: SourceChunk[];
  processing_time_ms?: number;
  isError?: boolean;
}

// ── API ───────────────────────────────────────────────────────────────────────

const BASE_URL = (typeof import.meta !== "undefined" && (import.meta as any).env?.VITE_API_URL) 
  ?? "http://localhost:8000";

class ApiError extends Error {
  constructor(public detail: string, public status: number) {
    super(detail);
  }
}

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, init);
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail ?? detail; } catch {}
    throw new ApiError(detail, res.status);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

async function uploadDocument(file: File): Promise<{ document_id: string; filename: string; message: string; chunk_count: number; page_count: number }> {
  const form = new FormData();
  form.append("file", file);
  return apiFetch("/api/documents/upload", { method: "POST", body: form });
}

async function listDocuments(): Promise<DocumentMetadata[]> {
  const res = await apiFetch<{ documents: DocumentMetadata[]; total: number }>("/api/documents/");
  return res.documents;
}

async function deleteDocument(id: string): Promise<void> {
  await apiFetch(`/api/documents/${id}`, { method: "DELETE" });
}

async function sendChat(payload: {
  session_id: string;
  document_ids: string[];
  question: string;
  chat_history: Array<{ role: string; content: string; timestamp: string }>;
}): Promise<{ answer: string; sources: SourceChunk[]; processing_time_ms: number; model_used: string }> {
  return apiFetch("/api/chat/query", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

// ── Utils ─────────────────────────────────────────────────────────────────────

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

// ── Icons (inline SVGs to avoid extra deps) ───────────────────────────────────

const UploadIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="w-5 h-5">
    <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M17 8l-5-5-5 5M12 3v12"/>
  </svg>
);
const FileIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="w-4 h-4">
    <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/>
  </svg>
);
const TrashIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="w-4 h-4">
    <polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 01-2 2H8a2 2 0 01-2-2L5 6m3 0V4a1 1 0 011-1h4a1 1 0 011 1v2"/>
  </svg>
);
const SendIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="w-5 h-5">
    <line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/>
  </svg>
);
const BotIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="w-5 h-5">
    <rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0110 0v4M12 3v4M8 15h.01M16 15h.01"/>
  </svg>
);
const CheckIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.5} className="w-3.5 h-3.5">
    <polyline points="20 6 9 17 4 12"/>
  </svg>
);
const ChevronIcon = ({ open }: { open: boolean }) => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className={`w-4 h-4 transition-transform ${open ? "rotate-180" : ""}`}>
    <polyline points="6 9 12 15 18 9"/>
  </svg>
);
const BookIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="w-3.5 h-3.5">
    <path d="M4 19.5A2.5 2.5 0 016.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 014 19.5v-15A2.5 2.5 0 016.5 2z"/>
  </svg>
);
const XIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="w-3.5 h-3.5">
    <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
  </svg>
);
const SparkleIcon = () => (
  <svg viewBox="0 0 24 24" fill="currentColor" className="w-5 h-5">
    <path d="M12 2l2.4 7.6H22l-6.2 4.5 2.4 7.6L12 17.2l-6.2 4.5 2.4-7.6L2 9.6h7.6L12 2z"/>
  </svg>
);

// ── Spinner ───────────────────────────────────────────────────────────────────

const Spinner = ({ size = 4 }: { size?: number }) => (
  <div
    className={`w-${size} h-${size} border-2 border-current border-t-transparent rounded-full animate-spin`}
    style={{ width: `${size * 4}px`, height: `${size * 4}px` }}
  />
);

// ── SourcesPanel ──────────────────────────────────────────────────────────────

function SourcesPanel({ sources }: { sources: SourceChunk[] }) {
  const [open, setOpen] = useState(false);
  if (!sources.length) return null;

  // Group by filename
  const grouped = sources.reduce<Record<string, SourceChunk[]>>((acc, s) => {
    (acc[s.filename] ??= []).push(s);
    return acc;
  }, {});

  return (
    <div className="mt-3 border border-stone-700/60 rounded-xl overflow-hidden">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center gap-2 px-4 py-2.5 bg-stone-800/60 hover:bg-stone-800 text-stone-400 hover:text-stone-300 text-xs font-mono transition-colors"
      >
        <BookIcon />
        <span>{sources.length} source{sources.length !== 1 ? "s" : ""} cited</span>
        <span className="ml-auto"><ChevronIcon open={open} /></span>
      </button>
      {open && (
        <div className="bg-stone-900/80 divide-y divide-stone-800">
          {Object.entries(grouped).map(([filename, chunks]) => (
            <div key={filename} className="px-4 py-3">
              <p className="text-xs font-semibold text-amber-400 mb-2 flex items-center gap-1.5">
                <FileIcon />
                {filename}
              </p>
              {chunks.map((chunk, i) => (
                <div key={i} className="mb-2 last:mb-0">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-xs px-2 py-0.5 bg-stone-800 text-stone-400 rounded-full font-mono">
                      p. {chunk.page_number}
                    </span>
                    <span className="text-xs text-stone-500">
                      {(chunk.relevance_score * 100).toFixed(0)}% match
                    </span>
                  </div>
                  <p className="text-xs text-stone-400 leading-relaxed line-clamp-3 pl-1 border-l-2 border-stone-700">
                    {chunk.chunk_text}
                  </p>
                </div>
              ))}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── MessageBubble ─────────────────────────────────────────────────────────────

function MessageBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user";

  return (
    <div className={`flex gap-3 ${isUser ? "flex-row-reverse" : "flex-row"} mb-6`}>
      {/* Avatar */}
      <div className={`flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold
        ${isUser
          ? "bg-amber-500 text-stone-900"
          : message.isError
            ? "bg-red-900 text-red-300"
            : "bg-stone-700 text-amber-400"
        }`}>
        {isUser ? "You" : <BotIcon />}
      </div>

      {/* Content */}
      <div className={`max-w-[82%] ${isUser ? "items-end" : "items-start"} flex flex-col`}>
        <div className={`px-4 py-3 rounded-2xl text-sm leading-relaxed
          ${isUser
            ? "bg-amber-500 text-stone-900 rounded-tr-sm font-medium"
            : message.isError
              ? "bg-red-950/60 border border-red-800/50 text-red-300 rounded-tl-sm"
              : "bg-stone-800/80 border border-stone-700/50 text-stone-200 rounded-tl-sm"
          }`}>
          {isUser ? (
            <p>{message.content}</p>
          ) : (
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              className="prose prose-sm prose-invert max-w-none prose-p:my-1 prose-headings:my-2 prose-li:my-0.5"
            >
              {message.content}
            </ReactMarkdown>
          )}
        </div>

        {/* Metadata */}
        <div className={`flex items-center gap-3 mt-1.5 px-1 ${isUser ? "flex-row-reverse" : "flex-row"}`}>
          <span className="text-stone-600 text-xs font-mono">{formatTime(message.timestamp)}</span>
          {message.processing_time_ms && (
            <span className="text-stone-600 text-xs font-mono">
              {message.processing_time_ms < 1000
                ? `${message.processing_time_ms.toFixed(0)}ms`
                : `${(message.processing_time_ms / 1000).toFixed(1)}s`}
            </span>
          )}
        </div>

        {/* Sources */}
        {message.sources && <SourcesPanel sources={message.sources} />}
      </div>
    </div>
  );
}

// ── TypingIndicator ───────────────────────────────────────────────────────────

function TypingIndicator() {
  return (
    <div className="flex gap-3 mb-6">
      <div className="flex-shrink-0 w-8 h-8 rounded-full bg-stone-700 text-amber-400 flex items-center justify-center">
        <BotIcon />
      </div>
      <div className="px-4 py-3 bg-stone-800/80 border border-stone-700/50 rounded-2xl rounded-tl-sm">
        <div className="flex gap-1 items-center h-4">
          {[0, 1, 2].map((i) => (
            <span
              key={i}
              className="w-1.5 h-1.5 bg-amber-500 rounded-full animate-bounce"
              style={{ animationDelay: `${i * 150}ms`, animationDuration: "1.2s" }}
            />
          ))}
        </div>
      </div>
    </div>
  );
}

// ── DocumentCard ──────────────────────────────────────────────────────────────

function DocumentCard({
  doc,
  selected,
  onToggle,
  onDelete,
}: {
  doc: DocumentMetadata;
  selected: boolean;
  onToggle: () => void;
  onDelete: () => void;
}) {
  const [deleting, setDeleting] = useState(false);

  const handleDelete = async (e: React.MouseEvent) => {
    e.stopPropagation();
    if (!confirm(`Delete "${doc.filename}"?`)) return;
    setDeleting(true);
    onDelete();
  };

  return (
    <div
      onClick={onToggle}
      className={`relative group flex items-start gap-3 p-3 rounded-xl cursor-pointer transition-all
        ${selected
          ? "bg-amber-500/15 border border-amber-500/50"
          : "bg-stone-800/50 border border-stone-700/50 hover:border-stone-600"
        }`}
    >
      {/* Select indicator */}
      <div className={`flex-shrink-0 w-4 h-4 mt-0.5 rounded border-2 flex items-center justify-center transition-all
        ${selected ? "bg-amber-500 border-amber-500" : "border-stone-600"}`}>
        {selected && <CheckIcon />}
      </div>

      {/* Info */}
      <div className="flex-1 min-w-0">
        <p className="text-stone-200 text-xs font-medium truncate">{doc.filename}</p>
        <p className="text-stone-500 text-xs mt-0.5 font-mono">
          {doc.page_count}p · {doc.chunk_count} chunks · {formatBytes(doc.file_size_bytes)}
        </p>
      </div>

      {/* Delete */}
      <button
        onClick={handleDelete}
        disabled={deleting}
        className="opacity-0 group-hover:opacity-100 flex-shrink-0 p-1 rounded-lg text-stone-600 hover:text-red-400 hover:bg-red-950/40 transition-all"
        title="Delete document"
      >
        {deleting ? <Spinner size={3} /> : <TrashIcon />}
      </button>

      {/* Status badge */}
      {doc.status !== "ready" && (
        <span className={`absolute top-2 right-2 text-xs px-2 py-0.5 rounded-full font-mono
          ${doc.status === "processing" ? "bg-blue-950 text-blue-400" : "bg-red-950 text-red-400"}`}>
          {doc.status}
        </span>
      )}
    </div>
  );
}

// ── DropZone ──────────────────────────────────────────────────────────────────

function DropZone({ onUploaded }: { onUploaded: (doc: DocumentMetadata) => void }) {
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const onDrop = useCallback(async (acceptedFiles: File[]) => {
    const file = acceptedFiles[0];
    if (!file) return;

    setUploading(true);
    setError(null);
    setSuccess(null);

    try {
      const res = await uploadDocument(file);
      setSuccess(res.message);
      // Optimistically add to list (backend will have full meta)
      onUploaded({
        document_id: res.document_id,
        filename: res.filename,
        file_size_bytes: file.size,
        page_count: res.page_count,
        chunk_count: res.chunk_count,
        uploaded_at: new Date().toISOString(),
        status: "ready",
      });
      setTimeout(() => setSuccess(null), 4000);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Upload failed");
    } finally {
      setUploading(false);
    }
  }, [onUploaded]);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: { "application/pdf": [".pdf"] },
    maxFiles: 1,
    disabled: uploading,
  });

  return (
    <div className="space-y-2">
      <div
        {...getRootProps()}
        className={`relative border-2 border-dashed rounded-xl p-4 text-center cursor-pointer transition-all
          ${isDragActive
            ? "border-amber-500 bg-amber-500/10"
            : uploading
              ? "border-stone-700 bg-stone-800/30 cursor-not-allowed"
              : "border-stone-700 hover:border-amber-500/50 hover:bg-stone-800/30"
          }`}
      >
        <input {...getInputProps()} />
        <div className="flex flex-col items-center gap-2">
          {uploading ? (
            <>
              <Spinner size={5} />
              <p className="text-stone-400 text-xs">Indexing document…</p>
            </>
          ) : (
            <>
              <div className="text-stone-500"><UploadIcon /></div>
              <p className="text-stone-400 text-xs">
                {isDragActive ? "Drop PDF here" : "Drop PDF or click to upload"}
              </p>
              <p className="text-stone-600 text-xs">Max 50 MB</p>
            </>
          )}
        </div>
      </div>

      {error && (
        <div className="flex items-start gap-2 px-3 py-2 bg-red-950/50 border border-red-800/50 rounded-lg">
          <p className="text-red-400 text-xs">{error}</p>
        </div>
      )}
      {success && (
        <div className="flex items-start gap-2 px-3 py-2 bg-emerald-950/50 border border-emerald-800/50 rounded-lg">
          <p className="text-emerald-400 text-xs">{success}</p>
        </div>
      )}
    </div>
  );
}

// ── ChatInput ─────────────────────────────────────────────────────────────────

function ChatInput({
  onSend,
  disabled,
  noDocsSelected,
}: {
  onSend: (q: string) => void;
  disabled: boolean;
  noDocsSelected: boolean;
}) {
  const [value, setValue] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const submit = () => {
    const q = value.trim();
    if (!q || disabled || noDocsSelected) return;
    onSend(q);
    setValue("");
    if (textareaRef.current) textareaRef.current.style.height = "auto";
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  };

  const handleInput = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setValue(e.target.value);
    const ta = e.target;
    ta.style.height = "auto";
    ta.style.height = `${Math.min(ta.scrollHeight, 160)}px`;
  };

  const placeholder = noDocsSelected
    ? "Select documents above to start chatting…"
    : "Ask anything about your documents… (Enter to send)";

  return (
    <div className="p-4 border-t border-stone-800">
      <div className={`flex items-end gap-3 bg-stone-800/60 border rounded-2xl px-4 py-3 transition-colors
        ${noDocsSelected ? "border-stone-700/50 opacity-60" : "border-stone-600 focus-within:border-amber-500/50"}`}>
        <textarea
          ref={textareaRef}
          value={value}
          onChange={handleInput}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          disabled={disabled || noDocsSelected}
          rows={1}
          className="flex-1 bg-transparent text-stone-200 text-sm placeholder-stone-600 resize-none outline-none leading-relaxed"
          style={{ maxHeight: "160px" }}
        />
        <button
          onClick={submit}
          disabled={disabled || noDocsSelected || !value.trim()}
          className="flex-shrink-0 w-8 h-8 rounded-xl bg-amber-500 hover:bg-amber-400 disabled:bg-stone-700 disabled:text-stone-600 text-stone-900 flex items-center justify-center transition-all"
        >
          {disabled ? <Spinner size={4} /> : <SendIcon />}
        </button>
      </div>
      <p className="text-center text-stone-700 text-xs mt-2 font-mono">
        Shift+Enter for new line · AI can make mistakes
      </p>
    </div>
  );
}

// ── Main App ──────────────────────────────────────────────────────────────────

const SESSION_ID = uuidv4();

export default function App() {
  const [documents, setDocuments] = useState<DocumentMetadata[]>([]);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [loadingDocs, setLoadingDocs] = useState(true);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Load documents on mount
  useEffect(() => {
    listDocuments()
      .then(setDocuments)
      .catch(console.error)
      .finally(() => setLoadingDocs(false));
  }, []);

  // Auto-scroll
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isLoading]);

  const selectedDocs = documents.filter((d) => selectedIds.has(d.document_id));

  const toggleDoc = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  };

  const handleDocUploaded = (doc: DocumentMetadata) => {
    setDocuments((prev) => [doc, ...prev]);
    setSelectedIds((prev) => new Set([...prev, doc.document_id]));
  };

  const handleDocDeleted = async (id: string) => {
    try {
      await deleteDocument(id);
      setDocuments((prev) => prev.filter((d) => d.document_id !== id));
      setSelectedIds((prev) => {
        const next = new Set(prev);
        next.delete(id);
        return next;
      });
    } catch (err) {
      console.error("Delete failed:", err);
    }
  };

  const handleAsk = async (question: string) => {
    if (!question.trim() || isLoading || selectedDocs.length === 0) return;

    const userMsg: ChatMessage = {
      id: uuidv4(),
      role: "user",
      content: question,
      timestamp: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, userMsg]);
    setIsLoading(true);

    try {
      const response = await sendChat({
        session_id: SESSION_ID,
        document_ids: selectedDocs.map((d) => d.document_id),
        question,
        chat_history: messages.slice(-10).map(({ role, content, timestamp }) => ({
          role,
          content,
          timestamp,
        })),
      });

      setMessages((prev) => [
        ...prev,
        {
          id: uuidv4(),
          role: "assistant",
          content: response.answer,
          timestamp: new Date().toISOString(),
          sources: response.sources,
          processing_time_ms: response.processing_time_ms,
        },
      ]);
    } catch (err) {
      const detail = err instanceof ApiError ? err.detail : "An unexpected error occurred.";
      setMessages((prev) => [
        ...prev,
        {
          id: uuidv4(),
          role: "assistant",
          content: `⚠️ ${detail}`,
          timestamp: new Date().toISOString(),
          isError: true,
        },
      ]);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="h-screen flex flex-col bg-stone-950 text-stone-100 font-sans overflow-hidden">
      {/* ── Header ─────────────────────────────────────────────────────────── */}
      <header className="flex-shrink-0 border-b border-stone-800 px-6 py-3 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-xl bg-amber-500 text-stone-900 flex items-center justify-center">
            <SparkleIcon />
          </div>
          <div>
            <h1 className="text-sm font-bold text-stone-100 tracking-tight">DocSearch AI</h1>
            <p className="text-xs text-stone-500 font-mono">RAG-powered document intelligence</p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          {selectedDocs.length > 0 && (
            <div className="flex items-center gap-1.5 px-3 py-1.5 bg-amber-500/15 border border-amber-500/30 rounded-full">
              <div className="w-1.5 h-1.5 bg-amber-500 rounded-full" />
              <span className="text-amber-400 text-xs font-mono">
                {selectedDocs.length} doc{selectedDocs.length !== 1 ? "s" : ""} active
              </span>
            </div>
          )}
          {messages.length > 0 && (
            <button
              onClick={() => setMessages([])}
              className="text-xs text-stone-500 hover:text-stone-300 transition-colors font-mono"
            >
              Clear chat
            </button>
          )}
        </div>
      </header>

      {/* ── Main ───────────────────────────────────────────────────────────── */}
      <div className="flex-1 flex overflow-hidden">
        {/* ── Sidebar ─────────────────────────────────────────────────────── */}
        <aside className="w-72 flex-shrink-0 border-r border-stone-800 flex flex-col bg-stone-900/50">
          <div className="p-4 border-b border-stone-800">
            <h2 className="text-xs font-semibold text-stone-400 uppercase tracking-widest mb-3">
              Documents
            </h2>
            <DropZone onUploaded={handleDocUploaded} />
          </div>

          <div className="flex-1 overflow-y-auto p-4 space-y-2">
            {loadingDocs ? (
              <div className="flex items-center justify-center py-8">
                <Spinner size={5} />
              </div>
            ) : documents.length === 0 ? (
              <div className="text-center py-8">
                <div className="text-stone-700 mb-2 flex justify-center"><FileIcon /></div>
                <p className="text-stone-600 text-xs">No documents yet.</p>
                <p className="text-stone-700 text-xs">Upload a PDF to get started.</p>
              </div>
            ) : (
              <>
                <div className="flex items-center justify-between mb-1">
                  <p className="text-xs text-stone-600 font-mono">{documents.length} indexed</p>
                  {selectedIds.size !== documents.length ? (
                    <button
                      onClick={() => setSelectedIds(new Set(documents.map((d) => d.document_id)))}
                      className="text-xs text-amber-500 hover:text-amber-400 font-mono"
                    >
                      Select all
                    </button>
                  ) : (
                    <button
                      onClick={() => setSelectedIds(new Set())}
                      className="text-xs text-stone-500 hover:text-stone-400 font-mono"
                    >
                      Deselect all
                    </button>
                  )}
                </div>
                {documents.map((doc) => (
                  <DocumentCard
                    key={doc.document_id}
                    doc={doc}
                    selected={selectedIds.has(doc.document_id)}
                    onToggle={() => toggleDoc(doc.document_id)}
                    onDelete={() => handleDocDeleted(doc.document_id)}
                  />
                ))}
              </>
            )}
          </div>
        </aside>

        {/* ── Chat area ───────────────────────────────────────────────────── */}
        <main className="flex-1 flex flex-col overflow-hidden">
          {/* Messages */}
          <div className="flex-1 overflow-y-auto px-6 py-6">
            {messages.length === 0 ? (
              <div className="h-full flex flex-col items-center justify-center text-center max-w-md mx-auto">
                <div className="w-16 h-16 rounded-2xl bg-amber-500/20 text-amber-500 flex items-center justify-center mb-5">
                  <SparkleIcon />
                </div>
                <h2 className="text-xl font-bold text-stone-200 mb-2">Ask your documents anything</h2>
                <p className="text-stone-500 text-sm leading-relaxed mb-6">
                  Upload PDFs, select them in the sidebar, then ask natural-language questions.
                  The AI retrieves relevant passages and cites exact page numbers.
                </p>
                <div className="grid grid-cols-1 gap-2 w-full">
                  {[
                    "Summarise the key findings of this document",
                    "What are the main recommendations?",
                    "List all dates and deadlines mentioned",
                  ].map((q) => (
                    <button
                      key={q}
                      onClick={() => selectedDocs.length > 0 && handleAsk(q)}
                      disabled={selectedDocs.length === 0}
                      className="px-4 py-2.5 bg-stone-800/60 hover:bg-stone-800 disabled:opacity-40 border border-stone-700 hover:border-stone-600 rounded-xl text-stone-400 hover:text-stone-300 text-sm text-left transition-all"
                    >
                      {q}
                    </button>
                  ))}
                </div>
                {selectedDocs.length === 0 && (
                  <p className="text-stone-700 text-xs mt-4 font-mono">
                    ↑ Select documents in the sidebar first
                  </p>
                )}
              </div>
            ) : (
              <>
                {messages.map((msg) => (
                  <MessageBubble key={msg.id} message={msg} />
                ))}
                {isLoading && <TypingIndicator />}
                <div ref={messagesEndRef} />
              </>
            )}
          </div>

          {/* Input */}
          <ChatInput
            onSend={handleAsk}
            disabled={isLoading}
            noDocsSelected={selectedDocs.length === 0}
          />
        </main>
      </div>
    </div>
  );
}

// ── Bootstrap ─────────────────────────────────────────────────────────────────
ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
