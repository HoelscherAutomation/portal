import { writable } from 'svelte/store';

import { API_BASE, api, type ChatEvent, type ChunkPreview } from '../api';

export type ChatTurn = {
  id: string;
  query: string;
  answer: string;
  citations: number[];
  sources: Array<{ number: number; filename: string; page_num: number; content: string }>;
  status: 'streaming' | 'done' | 'error';
  errorMessage?: string;
};

export const chatTurns = writable<ChatTurn[]>([]);
export const chatBusy = writable<boolean>(false);

export async function askQuestion(query: string): Promise<void> {
  const turnId = crypto.randomUUID();
  const turn: ChatTurn = {
    id: turnId,
    query,
    answer: '',
    citations: [],
    sources: [],
    status: 'streaming',
  };
  chatTurns.update((t) => [...t, turn]);
  chatBusy.set(true);

  try {
    const response = await fetch(`${API_BASE}/api/modules/ask-docs/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ query }),
    });

    if (!response.ok) {
      let detail = response.statusText;
      try {
        const body = await response.json();
        detail = body.detail ?? detail;
      } catch {
        /* ignore */
      }
      _updateTurn(turnId, { status: 'error', errorMessage: detail });
      return;
    }

    const reader = response.body!.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      const events = buffer.split('\n\n');
      buffer = events.pop() ?? '';

      for (const block of events) {
        const line = block.split('\n').find((l) => l.startsWith('data: '));
        if (!line) continue;
        const event: ChatEvent = JSON.parse(line.slice('data: '.length));
        _applyEvent(turnId, event);
      }
    }

    chatTurns.update((turns) =>
      turns.map((t) => (t.id === turnId && t.status === 'streaming' ? { ...t, status: 'done' } : t))
    );
  } catch (err) {
    _updateTurn(turnId, { status: 'error', errorMessage: String(err) });
  } finally {
    chatBusy.set(false);
  }
}

function _applyEvent(turnId: string, event: ChatEvent): void {
  if (event.type === 'sources') {
    _updateTurn(turnId, { sources: event.sources });
  } else if (event.type === 'delta') {
    chatTurns.update((turns) =>
      turns.map((t) => (t.id === turnId ? { ...t, answer: t.answer + event.text } : t))
    );
  } else if (event.type === 'final') {
    _updateTurn(turnId, { answer: event.answer, citations: event.citations });
  } else if (event.type === 'error') {
    _updateTurn(turnId, { status: 'error', errorMessage: event.detail });
  }
}

function _updateTurn(turnId: string, patch: Partial<ChatTurn>): void {
  chatTurns.update((turns) => turns.map((t) => (t.id === turnId ? { ...t, ...patch } : t)));
}

export function clearChat(): void {
  chatTurns.set([]);
}

export async function fetchChunkPreview(docId: string, chunkIndex: number): Promise<ChunkPreview> {
  return await api.get<ChunkPreview>(`/api/modules/ask-docs/chunks/${docId}/${chunkIndex}`);
}
