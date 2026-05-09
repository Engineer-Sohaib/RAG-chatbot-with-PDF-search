/**
 * useChat — manages chat session state, history, and API calls.
 * Decouples all async logic from the UI component.
 */

import { useState, useCallback } from "react";
import { v4 as uuidv4 } from "uuid";
import { sendMessage, ApiError } from "../services/api";
import type { ChatMessage, DocumentMetadata } from "../types";

const SESSION_ID = uuidv4(); // one session per browser tab

export function useChat(selectedDocs: DocumentMetadata[]) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isLoading, setIsLoading] = useState(false);

  const addMessage = useCallback((msg: ChatMessage) => {
    setMessages((prev) => [...prev, msg]);
  }, []);

  const ask = useCallback(
    async (question: string) => {
      if (!question.trim() || isLoading || selectedDocs.length === 0) return;

      const userMsg: ChatMessage = {
        role: "user",
        content: question,
        timestamp: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, userMsg]);
      setIsLoading(true);

      try {
        const response = await sendMessage({
          session_id: SESSION_ID,
          document_ids: selectedDocs.map((d) => d.document_id),
          question,
          // Only send last 10 turns to keep payload small
          chat_history: messages.slice(-10).map(({ role, content, timestamp }) => ({
            role,
            content,
            timestamp,
          })),
        });

        const assistantMsg: ChatMessage = {
          role: "assistant",
          content: response.answer,
          timestamp: new Date().toISOString(),
          sources: response.sources,
          processing_time_ms: response.processing_time_ms,
        };
        setMessages((prev) => [...prev, assistantMsg]);
      } catch (err) {
        const detail =
          err instanceof ApiError
            ? err.detail ?? err.message
            : "An unexpected error occurred.";

        const errMsg: ChatMessage = {
          role: "assistant",
          content: `⚠️ ${detail}`,
          timestamp: new Date().toISOString(),
          isError: true,
        };
        setMessages((prev) => [...prev, errMsg]);
      } finally {
        setIsLoading(false);
      }
    },
    [isLoading, messages, selectedDocs]
  );

  const clearHistory = useCallback(() => setMessages([]), []);

  return { messages, isLoading, ask, clearHistory, addMessage };
}
