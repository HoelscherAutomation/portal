<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import {
    loadDashboard,
    loadQueries,
    loadQueryDetail,
  } from '$lib/stores/admin_ask_docs_dashboard';
  import type { DashboardPayload, QueryListItem, QueryDetail } from '$lib/api';
  import TokenChart from '$lib/components/TokenChart.svelte';

  let dashboard = $state<DashboardPayload | null>(null);
  let queries = $state<QueryListItem[]>([]);
  let loadError = $state<string | null>(null);
  let lastUpdatedISO = $state<string>('');
  let drillDown = $state<QueryDetail | null>(null);
  let drillDownError = $state<string | null>(null);

  let pollHandle: ReturnType<typeof setInterval> | null = null;
  const POLL_MS = 30_000;
  const PRICING_LAST_UPDATED = '2026-05-10';  // mirror backend pricing.LAST_UPDATED

  function errorMessage(err: unknown): string {
    if (err && typeof err === 'object') {
      const e = err as { detail?: string; message?: string };
      return e.detail ?? e.message ?? JSON.stringify(err);
    }
    return String(err);
  }

  async function refreshAll() {
    try {
      const [d, q] = await Promise.all([loadDashboard(), loadQueries(100, 0)]);
      dashboard = d;
      queries = q;
      lastUpdatedISO = new Date().toISOString();
      loadError = null;
    } catch (err) {
      loadError = errorMessage(err);
    }
  }

  async function openDrillDown(id: number) {
    drillDown = null;
    drillDownError = null;
    try {
      drillDown = await loadQueryDetail(id);
    } catch (err) {
      drillDownError = errorMessage(err);
    }
  }

  function closeDrillDown() {
    drillDown = null;
    drillDownError = null;
  }

  function fmtCost(usd: number): string {
    return usd === 0 ? '$0.00' : `$${usd.toFixed(2)}`;
  }

  function fmtTokens(n: number): string {
    if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
    if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
    return n.toLocaleString();
  }

  function fmtTimestamp(iso: string): string {
    return new Date(iso).toLocaleString(undefined, { dateStyle: 'short', timeStyle: 'short' });
  }

  function truncate(s: string, n: number): string {
    return s.length <= n ? s : s.slice(0, n - 1) + '…';
  }

  onMount(async () => {
    await refreshAll();
    pollHandle = setInterval(refreshAll, POLL_MS);
  });

  onDestroy(() => {
    if (pollHandle) clearInterval(pollHandle);
  });
</script>

<div class="flex h-[calc(100vh-65px)]">
  <div class="flex-1 overflow-y-auto p-6 space-y-6">
    <div class="flex items-baseline justify-between">
      <div>
        <h1 class="text-2xl font-semibold">Ask Docs · Admin Dashboard</h1>
        <p class="text-sm text-[color:var(--color-text-muted)] mt-1">
          Auto-refreshes every 30s · last update {lastUpdatedISO ? fmtTimestamp(lastUpdatedISO) : '—'}
        </p>
      </div>
      <a href="/admin/modules/ask-docs/config" class="text-sm text-[color:var(--color-accent)] hover:underline">
        Configure →
      </a>
    </div>

    {#if loadError}
      <div class="p-4 bg-red-900/30 border border-red-700 rounded text-sm">
        Failed to load: {loadError}
      </div>
    {/if}

    {#if dashboard?.update_banner}
      <div class="p-4 border border-[color:var(--color-accent)] rounded text-sm">
        {dashboard.update_banner.message}
      </div>
    {/if}

    {#if dashboard}
      <!-- 4 stat cards -->
      <div class="grid grid-cols-4 gap-4">
        <div class="border border-[color:var(--color-border)] rounded-lg p-4">
          <div class="text-xs uppercase tracking-wider text-[color:var(--color-text-subtle)]">Documents</div>
          <div class="text-2xl font-semibold mt-1">{dashboard.documents.total}</div>
          <div class="text-xs text-[color:var(--color-text-muted)] mt-1">{dashboard.documents.by_status.indexed} indexed</div>
        </div>
        <div class="border border-[color:var(--color-border)] rounded-lg p-4">
          <div class="text-xs uppercase tracking-wider text-[color:var(--color-text-subtle)]">Queries (30d)</div>
          <div class="text-2xl font-semibold mt-1">{dashboard.queries_30d.count}</div>
          <div class="text-xs text-[color:var(--color-text-muted)] mt-1">
            avg {dashboard.queries_30d.avg_latency_ms ?? '—'}ms · p95 {dashboard.queries_30d.p95_latency_ms ?? '—'}ms
          </div>
        </div>
        <div class="border border-[color:var(--color-border)] rounded-lg p-4">
          <div class="text-xs uppercase tracking-wider text-[color:var(--color-text-subtle)]">Tokens (30d)</div>
          <div class="text-2xl font-semibold mt-1">{fmtTokens(dashboard.queries_30d.tokens)}</div>
        </div>
        <div class="border border-[color:var(--color-border)] rounded-lg p-4" title="Estimated using prices last updated {PRICING_LAST_UPDATED}; Anthropic pricing may have changed since.">
          <div class="text-xs uppercase tracking-wider text-[color:var(--color-text-subtle)]">Estimated cost (30d)</div>
          <div class="text-2xl font-semibold mt-1">{fmtCost(dashboard.queries_30d.cost_usd_estimated)}</div>
          <div class="text-xs text-[color:var(--color-text-muted)] mt-1">prices as of {PRICING_LAST_UPDATED}</div>
        </div>
      </div>

      <!-- Token chart -->
      <TokenChart data={dashboard.queries_30d.tokens_per_day} />

      <!-- Mode breakdown + Doc status -->
      <div class="grid grid-cols-2 gap-4">
        <div class="border border-[color:var(--color-border)] rounded-lg p-4">
          <h3 class="font-medium text-sm mb-3">Mode breakdown (30d)</h3>
          {#if dashboard.queries_30d.by_mode.length === 0}
            <p class="text-sm text-[color:var(--color-text-muted)]">No queries yet.</p>
          {:else}
            <table class="w-full text-sm">
              <tbody>
                {#each dashboard.queries_30d.by_mode as row}
                  <tr>
                    <td class="py-1">{row.mode}</td>
                    <td class="py-1 text-right">{row.count} queries</td>
                    <td class="py-1 text-right">{fmtTokens(row.tokens)} tokens</td>
                  </tr>
                {/each}
              </tbody>
            </table>
          {/if}
        </div>
        <div class="border border-[color:var(--color-border)] rounded-lg p-4">
          <h3 class="font-medium text-sm mb-3">Document status</h3>
          <table class="w-full text-sm">
            <tbody>
              <tr><td class="py-1">Indexed</td><td class="py-1 text-right">{dashboard.documents.by_status.indexed}</td></tr>
              <tr><td class="py-1">Indexing</td><td class="py-1 text-right">{dashboard.documents.by_status.indexing}</td></tr>
              <tr><td class="py-1">Pending</td><td class="py-1 text-right">{dashboard.documents.by_status.pending}</td></tr>
              <tr><td class="py-1">Failed</td><td class="py-1 text-right">{dashboard.documents.by_status.failed}</td></tr>
              <tr><td class="py-1 border-t border-[color:var(--color-border)] mt-1">Total chunks</td><td class="py-1 text-right border-t border-[color:var(--color-border)]">{dashboard.documents.total_chunks.toLocaleString()}</td></tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- Query log -->
      <div class="border border-[color:var(--color-border)] rounded-lg overflow-hidden">
        <div class="px-4 py-3 border-b border-[color:var(--color-border)]">
          <h3 class="font-medium text-sm">Recent queries (last {queries.length})</h3>
        </div>
        {#if queries.length === 0}
          <p class="text-sm text-[color:var(--color-text-muted)] p-4">No queries logged yet.</p>
        {:else}
          <table class="w-full text-sm">
            <thead class="text-xs uppercase tracking-wider text-[color:var(--color-text-subtle)]">
              <tr>
                <th class="text-left px-4 py-2">Time</th>
                <th class="text-left px-4 py-2">User</th>
                <th class="text-left px-4 py-2">Query</th>
                <th class="text-right px-4 py-2">Cit</th>
                <th class="text-right px-4 py-2">Tok</th>
                <th class="text-right px-4 py-2">ms</th>
                <th class="text-left px-4 py-2">Mode</th>
              </tr>
            </thead>
            <tbody>
              {#each queries as q}
                <tr onclick={() => openDrillDown(q.id)} class="cursor-pointer hover:bg-[color:var(--color-surface-2)] border-t border-[color:var(--color-border)]">
                  <td class="px-4 py-2 whitespace-nowrap">{fmtTimestamp(q.created_at)}</td>
                  <td class="px-4 py-2 whitespace-nowrap text-xs text-[color:var(--color-text-muted)]">{q.user_email ?? '—'}</td>
                  <td class="px-4 py-2">{truncate(q.query_text, 60)}</td>
                  <td class="px-4 py-2 text-right">{q.citation_count}</td>
                  <td class="px-4 py-2 text-right">{q.tokens_used ?? '—'}</td>
                  <td class="px-4 py-2 text-right">{q.duration_ms}</td>
                  <td class="px-4 py-2 text-xs">{q.llm_mode}</td>
                </tr>
              {/each}
            </tbody>
          </table>
        {/if}
      </div>
    {:else if !loadError}
      <p class="text-[color:var(--color-text-muted)]">Loading...</p>
    {/if}
  </div>

  <!-- Drill-down side panel -->
  {#if drillDown || drillDownError}
    <aside class="w-[28rem] border-l border-[color:var(--color-border)] flex flex-col">
      <div class="px-4 py-3 border-b border-[color:var(--color-border)] flex items-center justify-between">
        <h2 class="font-medium">Query detail</h2>
        <button type="button" onclick={closeDrillDown} class="text-sm text-[color:var(--color-text-muted)] hover:text-[color:var(--color-text)]">Close</button>
      </div>
      <div class="flex-1 overflow-y-auto px-4 py-4 space-y-4">
        {#if drillDownError}
          <p class="text-sm text-red-400">{drillDownError}</p>
        {:else if drillDown}
          <div>
            <div class="text-xs uppercase tracking-wider text-[color:var(--color-text-subtle)] mb-1">Question</div>
            <div class="text-sm">{drillDown.query_text}</div>
          </div>
          <div>
            <div class="text-xs uppercase tracking-wider text-[color:var(--color-text-subtle)] mb-1">Answer</div>
            <div class="text-sm whitespace-pre-wrap">{drillDown.answer_text}</div>
          </div>
          <div class="grid grid-cols-2 gap-3 text-xs">
            <div><span class="text-[color:var(--color-text-subtle)]">Mode:</span> {drillDown.llm_mode}</div>
            <div><span class="text-[color:var(--color-text-subtle)]">Tokens:</span> {drillDown.tokens_used ?? '—'}</div>
            <div><span class="text-[color:var(--color-text-subtle)]">Latency:</span> {drillDown.duration_ms}ms</div>
            <div><span class="text-[color:var(--color-text-subtle)]">Citations:</span> {drillDown.citation_count}</div>
          </div>
          <div>
            <div class="text-xs uppercase tracking-wider text-[color:var(--color-text-subtle)] mb-2">Cited sources</div>
            {#if drillDown.sources_used.length === 0}
              <p class="text-sm text-[color:var(--color-text-muted)]">None.</p>
            {:else}
              <div class="space-y-3">
                {#each drillDown.sources_used as src}
                  <div class="border border-[color:var(--color-border)] rounded p-3 text-sm">
                    <div class="text-xs text-[color:var(--color-text-subtle)] mb-1">[{src.number}] {src.filename} · page {src.page_num}</div>
                    <div class="text-sm whitespace-pre-wrap">{src.content}</div>
                  </div>
                {/each}
              </div>
            {/if}
          </div>
        {/if}
      </div>
    </aside>
  {/if}
</div>
