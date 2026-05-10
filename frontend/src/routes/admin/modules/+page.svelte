<script lang="ts">
  import { modules, requestModule } from '$lib/stores/modules';

  let busyKey = $state<string | null>(null);
  let message = $state<{ kind: 'ok' | 'err'; text: string } | null>(null);

  async function handleRequest(key: string) {
    busyKey = key;
    message = null;
    try {
      await requestModule(key);
      message = { kind: 'ok', text: 'Request sent. Hoelscher will follow up.' };
    } catch (err) {
      const detail = (err as { detail?: string }).detail;
      message = { kind: 'err', text: detail ?? 'Request failed.' };
    } finally {
      busyKey = null;
    }
  }
</script>

<div class="px-6 py-12 max-w-5xl">
  <h1 class="text-3xl font-semibold mb-2">Modules</h1>
  <p class="text-[color:var(--color-text-muted)] mb-8">
    Browse the Hoelscher Portal roadmap. Request modules you'd like enabled —
    Hoelscher will reach out to schedule activation.
  </p>

  {#if message}
    <p class="mb-4 text-sm {message.kind === 'ok' ? 'text-green-400' : 'text-red-400'}">{message.text}</p>
  {/if}

  <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
    {#each $modules as module (module.key)}
      <div class="bg-[color:var(--color-surface)] border border-[color:var(--color-border)] rounded-lg p-5 flex flex-col">
        <div class="flex items-start justify-between mb-3">
          <h2 class="text-lg font-medium">{module.name}</h2>
          {#if module.enabled}
            <span class="text-xs px-2 py-0.5 rounded bg-[color:var(--color-success)]/20 text-[color:var(--color-success)]">Active</span>
          {:else if module.status === 'live'}
            <span class="text-xs px-2 py-0.5 rounded bg-[color:var(--color-surface-2)] text-[color:var(--color-text-muted)]">Live</span>
          {:else}
            <span class="text-xs px-2 py-0.5 rounded bg-[color:var(--color-surface-2)] text-[color:var(--color-text-subtle)]">Preview</span>
          {/if}
        </div>

        <p class="text-sm text-[color:var(--color-text-muted)] mb-4 flex-1">{module.description}</p>

        <div class="flex items-center justify-between">
          <span class="text-xs text-[color:var(--color-text-subtle)]">{module.target}</span>
          {#if module.enabled}
            <span class="text-xs text-[color:var(--color-text-subtle)]">Enabled</span>
          {:else if module.has_pending_request}
            <span class="text-xs px-3 py-1 rounded bg-[color:var(--color-surface-2)] text-[color:var(--color-text-muted)]">Requested</span>
          {:else}
            <button
              type="button"
              onclick={() => handleRequest(module.key)}
              disabled={busyKey === module.key}
              class="text-xs px-3 py-1 rounded bg-[color:var(--color-accent)] text-[color:var(--color-bg)] font-medium hover:opacity-90 disabled:opacity-50"
            >
              {busyKey === module.key ? 'Requesting...' : 'Request'}
            </button>
          {/if}
        </div>
      </div>
    {/each}
  </div>
</div>
