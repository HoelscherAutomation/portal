<script lang="ts">
  let { data }: { data: Array<{ date: string; tokens: number }> } = $props();

  const max = $derived(Math.max(1, ...data.map((d) => d.tokens)));
  const total = $derived(data.reduce((sum, d) => sum + d.tokens, 0));
</script>

<div class="border border-[color:var(--color-border)] rounded-lg p-4">
  <div class="flex items-baseline justify-between mb-3">
    <h3 class="font-medium text-sm">Token usage (last 30 days)</h3>
    <span class="text-xs text-[color:var(--color-text-muted)]">
      Max day: {max.toLocaleString()} · Total: {total.toLocaleString()}
    </span>
  </div>

  <div class="flex items-end gap-[2px] h-24">
    {#each data as point}
      {@const heightPct = max > 0 ? (point.tokens / max) * 100 : 0}
      <div class="flex-1 group relative">
        <div
          class="bg-[color:var(--color-accent)] hover:opacity-80 transition-opacity"
          style="height: {heightPct}%; min-height: 1px;"
          title="{point.date}: {point.tokens.toLocaleString()} tokens">
        </div>
        <div class="absolute bottom-full left-1/2 -translate-x-1/2 mb-1 hidden group-hover:block whitespace-nowrap text-xs bg-[color:var(--color-surface-2)] border border-[color:var(--color-border)] rounded px-2 py-1 z-10">
          {point.date}: {point.tokens.toLocaleString()}
        </div>
      </div>
    {/each}
  </div>

  <div class="flex justify-between text-xs text-[color:var(--color-text-subtle)] mt-2">
    <span>{data[0]?.date ?? ''}</span>
    <span>{data[data.length - 1]?.date ?? ''}</span>
  </div>
</div>
