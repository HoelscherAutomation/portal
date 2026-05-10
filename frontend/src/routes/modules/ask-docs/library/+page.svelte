<script lang="ts">
  import { onDestroy, onMount } from 'svelte';

  import {
    askDocsDocuments,
    askDocsError,
    deleteDocument,
    loadDocuments,
    uploadDocument,
  } from '$lib/stores/ask_docs';

  let busyId = $state<string | null>(null);
  let uploading = $state(false);
  let message = $state<{ kind: 'ok' | 'err'; text: string } | null>(null);
  let pollTimer: ReturnType<typeof setInterval> | null = null;

  onMount(() => {
    pollTimer = setInterval(() => {
      loadDocuments();
    }, 3000);
  });

  onDestroy(() => {
    if (pollTimer) clearInterval(pollTimer);
  });

  function timeAgo(iso: string): string {
    const seconds = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
    if (seconds < 60) return `${seconds}s ago`;
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
    if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
    return `${Math.floor(seconds / 86400)}d ago`;
  }

  function fmtSize(bytes: number): string {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  }

  async function handleUpload(event: Event) {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    if (!file) return;

    uploading = true;
    message = null;
    try {
      const created = await uploadDocument(file);
      message = { kind: 'ok', text: `Queued: ${created.filename}` };
      input.value = '';
    } catch (err) {
      const detail = (err as { detail?: string }).detail;
      message = { kind: 'err', text: detail ?? 'Upload failed' };
    } finally {
      uploading = false;
    }
  }

  async function handleDelete(id: string, filename: string) {
    if (!confirm(`Delete ${filename}? This removes its chunks from the index.`)) return;
    busyId = id;
    try {
      await deleteDocument(id);
      message = { kind: 'ok', text: `Deleted ${filename}` };
    } catch (err) {
      const detail = (err as { detail?: string }).detail;
      message = { kind: 'err', text: detail ?? 'Delete failed' };
    } finally {
      busyId = null;
    }
  }
</script>

<div class="px-6 py-12 max-w-5xl">
  <div class="flex items-center justify-between mb-6">
    <div>
      <a href="/modules/ask-docs" class="text-sm text-[color:var(--color-text-muted)] hover:text-[color:var(--color-text)]">← Ask Docs</a>
      <h1 class="text-3xl font-semibold mt-2">Document library</h1>
    </div>
    <label class="px-4 py-2 bg-[color:var(--color-accent)] text-[color:var(--color-bg)] rounded font-medium hover:opacity-90 cursor-pointer">
      {uploading ? 'Uploading...' : '+ Upload document'}
      <input
        type="file"
        accept="application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/plain,text/markdown,.pdf,.docx,.txt,.md"
        onchange={handleUpload}
        disabled={uploading}
        class="hidden"
      />
    </label>
  </div>

  {#if $askDocsError}
    <p class="text-sm text-red-400 mb-4">{$askDocsError}</p>
  {/if}
  {#if message}
    <p class="mb-4 text-sm {message.kind === 'ok' ? 'text-green-400' : 'text-red-400'}">{message.text}</p>
  {/if}

  {#if $askDocsDocuments.length === 0}
    <div class="bg-[color:var(--color-surface)] border border-[color:var(--color-border)] rounded-lg p-8 text-center">
      <p class="text-[color:var(--color-text-muted)]">No documents yet.</p>
      <p class="text-sm text-[color:var(--color-text-subtle)] mt-2">Upload a PDF, DOCX, TXT, or Markdown file to get started.</p>
    </div>
  {:else}
    <div class="bg-[color:var(--color-surface)] border border-[color:var(--color-border)] rounded-lg overflow-hidden">
      <table class="w-full">
        <thead class="border-b border-[color:var(--color-border)]">
          <tr class="text-left text-xs uppercase tracking-wider text-[color:var(--color-text-subtle)]">
            <th class="px-4 py-3">Filename</th>
            <th class="px-4 py-3">Status</th>
            <th class="px-4 py-3">Chunks</th>
            <th class="px-4 py-3">Size</th>
            <th class="px-4 py-3">Uploaded</th>
            <th class="px-4 py-3"></th>
          </tr>
        </thead>
        <tbody>
          {#each $askDocsDocuments as doc (doc.id)}
            <tr class="border-b border-[color:var(--color-border)] last:border-0">
              <td class="px-4 py-3">{doc.filename}</td>
              <td class="px-4 py-3 text-sm">
                {#if doc.status === 'indexed'}
                  <span class="text-[color:var(--color-success)]">● indexed</span>
                {:else if doc.status === 'indexing'}
                  <span class="text-[color:var(--color-accent)]">⟳ indexing</span>
                {:else if doc.status === 'pending'}
                  <span class="text-[color:var(--color-text-muted)]">⏳ pending</span>
                {:else}
                  <span class="text-red-400" title={doc.error_message ?? ''}>✗ failed</span>
                {/if}
              </td>
              <td class="px-4 py-3 text-sm text-[color:var(--color-text-muted)]">{doc.chunk_count}</td>
              <td class="px-4 py-3 text-sm text-[color:var(--color-text-muted)]">{fmtSize(doc.size_bytes)}</td>
              <td class="px-4 py-3 text-sm text-[color:var(--color-text-subtle)]">{timeAgo(doc.uploaded_at)}</td>
              <td class="px-4 py-3 text-right">
                <button type="button" onclick={() => handleDelete(doc.id, doc.filename)} disabled={busyId === doc.id}
                  class="text-xs px-3 py-1 rounded text-red-400 hover:bg-red-900/20 disabled:opacity-50">
                  {busyId === doc.id ? '...' : 'Delete'}
                </button>
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  {/if}
</div>
