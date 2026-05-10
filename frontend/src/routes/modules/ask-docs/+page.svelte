<script lang="ts">
  import { askQuestion, chatBusy, chatTurns } from '$lib/stores/ask_docs_chat';

  type PreviewState = { filename: string; page_num: number; content: string } | null;

  let input = $state('');
  let preview = $state<PreviewState>(null);
  let previewError = $state<string | null>(null);

  async function handleSubmit(event: Event) {
    event.preventDefault();
    if (!input.trim() || $chatBusy) return;
    const q = input.trim();
    input = '';
    await askQuestion(q);
  }

  function openPreview(turnId: string, citationNumber: number) {
    const turn = $chatTurns.find((t) => t.id === turnId);
    if (!turn) return;
    const source = turn.sources.find((s) => s.number === citationNumber);
    if (!source) {
      previewError = `Source [${citationNumber}] not found in this turn.`;
      preview = null;
      return;
    }
    preview = {
      filename: source.filename,
      page_num: source.page_num,
      content: source.content,
    };
    previewError = null;
  }

  function closePreview() {
    preview = null;
    previewError = null;
  }

  function renderAnswerWithPills(text: string): Array<{ kind: 'text' | 'pill'; value: string; n?: number }> {
    const out: Array<{ kind: 'text' | 'pill'; value: string; n?: number }> = [];
    const re = /\[(\d+)\]/g;
    let lastIdx = 0;
    let match: RegExpExecArray | null;
    while ((match = re.exec(text)) !== null) {
      if (match.index > lastIdx) {
        out.push({ kind: 'text', value: text.slice(lastIdx, match.index) });
      }
      out.push({ kind: 'pill', value: match[0], n: parseInt(match[1], 10) });
      lastIdx = re.lastIndex;
    }
    if (lastIdx < text.length) {
      out.push({ kind: 'text', value: text.slice(lastIdx) });
    }
    return out;
  }
</script>

<div class="flex h-[calc(100vh-65px)]">
  <div class="flex-1 flex flex-col">
    <div class="px-6 py-4 border-b border-[color:var(--color-border)]">
      <h1 class="text-2xl font-semibold">Ask Docs</h1>
      <p class="text-sm text-[color:var(--color-text-muted)] mt-1">Ask a question about your indexed documents.</p>
    </div>

    <div class="flex-1 overflow-y-auto px-6 py-6 space-y-6">
      {#if $chatTurns.length === 0}
        <div class="text-center py-12">
          <p class="text-[color:var(--color-text-muted)]">No questions yet.</p>
          <p class="text-sm text-[color:var(--color-text-subtle)] mt-2">
            Try asking about something in your <a href="/modules/ask-docs/library" class="underline">document library</a>.
          </p>
        </div>
      {/if}

      {#each $chatTurns as turn (turn.id)}
        <div class="space-y-3">
          <div class="bg-[color:var(--color-surface-2)] border border-[color:var(--color-border)] rounded-lg p-4">
            <div class="text-xs uppercase tracking-wider text-[color:var(--color-text-subtle)] mb-1">You</div>
            <div>{turn.query}</div>
          </div>

          <div class="bg-[color:var(--color-surface)] border border-[color:var(--color-border)] rounded-lg p-4">
            <div class="text-xs uppercase tracking-wider text-[color:var(--color-text-subtle)] mb-1">
              Answer
              {#if turn.status === 'streaming'}<span class="text-[color:var(--color-accent)] ml-1">streaming...</span>{/if}
              {#if turn.status === 'error'}<span class="text-red-400 ml-1">error</span>{/if}
            </div>
            <div class="whitespace-pre-wrap leading-relaxed">
              {#each renderAnswerWithPills(turn.answer) as part}
                {#if part.kind === 'text'}{part.value}{:else}<button type="button" onclick={() => openPreview(turn.id, part.n!)} class="inline-flex items-center text-xs px-1.5 py-0.5 mx-0.5 rounded bg-[color:var(--color-accent)]/20 text-[color:var(--color-accent)] hover:bg-[color:var(--color-accent)]/30 cursor-pointer">{part.value}</button>{/if}
              {/each}
            </div>
            {#if turn.status === 'error' && turn.errorMessage}
              <div class="text-sm text-red-400 mt-2">{turn.errorMessage}</div>
            {/if}
          </div>
        </div>
      {/each}
    </div>

    <form onsubmit={handleSubmit} class="border-t border-[color:var(--color-border)] px-6 py-4 flex gap-3">
      <input
        type="text"
        bind:value={input}
        placeholder="Ask a question about your documents..."
        disabled={$chatBusy}
        class="flex-1 px-3 py-2 bg-[color:var(--color-bg)] border border-[color:var(--color-border)] rounded text-[color:var(--color-text)] focus:outline-none focus:border-[color:var(--color-accent)]"
      />
      <button
        type="submit"
        disabled={$chatBusy || !input.trim()}
        class="px-5 py-2 bg-[color:var(--color-accent)] text-[color:var(--color-bg)] rounded font-medium hover:opacity-90 disabled:opacity-50">
        {$chatBusy ? '...' : 'Ask'}
      </button>
    </form>
  </div>

  {#if preview || previewError}
    <aside class="w-96 border-l border-[color:var(--color-border)] flex flex-col">
      <div class="px-4 py-3 border-b border-[color:var(--color-border)] flex items-center justify-between">
        <h2 class="font-medium">Source preview</h2>
        <button type="button" onclick={closePreview} class="text-sm text-[color:var(--color-text-muted)] hover:text-[color:var(--color-text)]">
          Close
        </button>
      </div>
      <div class="flex-1 overflow-y-auto px-4 py-4">
        {#if previewError}
          <p class="text-sm text-red-400">{previewError}</p>
        {:else if preview}
          <div class="text-xs text-[color:var(--color-text-subtle)] uppercase tracking-wider mb-1">File</div>
          <div class="font-mono text-sm mb-3">{preview.filename}</div>
          <div class="text-xs text-[color:var(--color-text-subtle)] uppercase tracking-wider mb-1">Page</div>
          <div class="text-sm mb-4">{preview.page_num}</div>
          <div class="text-xs text-[color:var(--color-text-subtle)] uppercase tracking-wider mb-1">Chunk content</div>
          <div class="text-sm whitespace-pre-wrap leading-relaxed bg-[color:var(--color-bg)] border border-[color:var(--color-border)] rounded p-3">{preview.content}</div>
        {/if}
      </div>
    </aside>
  {/if}
</div>
