import { useMutation } from '@tanstack/react-query';
import type { QARequest, QAResponse, QASource } from '../api/types';

const API_BASE = '/api/v1';

export function useQAAsk() {
  return useMutation({
    mutationFn: async (request: QARequest): Promise<QAResponse> => {
      const token = localStorage.getItem('kb_curator_token');
      const headers: Record<string, string> = { 'Content-Type': 'application/json' };
      if (token) {
        headers['Authorization'] = `Bearer ${token}`;
      }
      const res = await fetch(`${API_BASE}/qa/ask`, {
        method: 'POST',
        headers,
        body: JSON.stringify(request),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail || '请求失败');
      }
      return res.json();
    },
  });
}

interface StreamCallbacks {
  onSources: (sources: QASource[]) => void;
  onToken: (token: string) => void;
  onDone: () => void;
  onError: (error: Error) => void;
}

export function useQAStream() {
  return useMutation({
    mutationFn: async ({
      request,
      callbacks,
    }: {
      request: QARequest;
      callbacks: StreamCallbacks;
    }): Promise<void> => {
      const token = localStorage.getItem('kb_curator_token');
      const headers: Record<string, string> = { 'Content-Type': 'application/json' };
      if (token) {
        headers['Authorization'] = `Bearer ${token}`;
      }

      const res = await fetch(`${API_BASE}/qa/ask/stream`, {
        method: 'POST',
        headers,
        body: JSON.stringify(request),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        callbacks.onError(new Error(err.detail || '请求失败'));
        return;
      }

      const reader = res.body?.getReader();
      if (!reader) {
        callbacks.onError(new Error('无法获取流式响应'));
        return;
      }

      const decoder = new TextDecoder();
      let buffer = '';

      try {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n');
          buffer = lines.pop() || '';

          for (const line of lines) {
            const trimmed = line.trim();
            if (!trimmed || !trimmed.startsWith('data: ')) continue;

            const data = trimmed.slice(6);
            if (data === '[DONE]') {
              callbacks.onDone();
              return;
            }

            try {
              const event = JSON.parse(data);
              if (event.type === 'sources') {
                callbacks.onSources(event.sources);
              } else if (event.type === 'token') {
                callbacks.onToken(event.content);
              }
            } catch {
              // Skip malformed JSON
            }
          }
        }
        callbacks.onDone();
      } catch (e) {
        callbacks.onError(e instanceof Error ? e : new Error(String(e)));
      }
    },
  });
}
