<script lang="ts">
  import { onMount } from 'svelte';
  import {
    loadAskDocsConfig,
    saveAskDocsConfig,
    probeAskDocsConfig,
  } from '$lib/stores/admin_module_config';
  import { errorMessage, type AskDocsConfig, type ProbeResult } from '$lib/api';

  type PreviewState = { filename: string; page_num: number; content: string } | null;

  let config = $state<AskDocsConfig | null>(null);
  let loadError = $state<string | null>(null);
  let saveStatus = $state<'idle' | 'saving' | 'saved' | 'error'>('idle');
  let saveError = $state<string | null>(null);

  let probeAnthropic = $state<{ status: 'idle' | 'running' | 'done'; result: ProbeResult | null }>({ status: 'idle', result: null });
  let probeOllama = $state<{ status: 'idle' | 'running' | 'done'; result: ProbeResult | null }>({ status: 'idle', result: null });

  let anthropicKeyInput = $state<string>('');
  let anthropicKeyDirty = $state<boolean>(false);

  /** Resolve the api_key field for save/probe payloads.
   * - dirty + value typed → send the plaintext
   * - dirty + cleared → send null (delete the saved key)
   * - not dirty + saved key exists → send {_set: true} (keep what's saved)
   * - not dirty + no saved key → send null (treat as unset, not as a "_set" sentinel)
   */
  function resolveAnthropicKeyField(): string | null | { _set: true } {
    if (anthropicKeyDirty) return anthropicKeyInput || null;
    const savedSet = (config?.anthropic.api_key as { _set: boolean } | undefined)?._set ?? false;
    return savedSet ? { _set: true } : null;
  }

  onMount(async () => {
    try {
      config = await loadAskDocsConfig();
      anthropicKeyInput = '';
    } catch (err) {
      loadError = errorMessage(err);
    }
  });

  function setAnthropicKey(value: string) {
    anthropicKeyInput = value;
    anthropicKeyDirty = true;
  }

  function clearAnthropicKey() {
    anthropicKeyInput = '';
    anthropicKeyDirty = true;
  }

  function buildSavePayload(): AskDocsConfig {
    if (!config) throw new Error('Not loaded');
    return {
      llm_mode: config.llm_mode,
      anthropic: { ...config.anthropic, api_key: resolveAnthropicKeyField() as never },
      ollama: { ...config.ollama },
      hoelscher_proxy: {},
      reranker: { ...config.reranker },
    };
  }

  async function handleSave() {
    saveStatus = 'saving';
    saveError = null;
    try {
      config = await saveAskDocsConfig(buildSavePayload());
      anthropicKeyInput = '';
      anthropicKeyDirty = false;
      saveStatus = 'saved';
      setTimeout(() => { if (saveStatus === 'saved') saveStatus = 'idle'; }, 3000);
    } catch (err) {
      saveStatus = 'error';
      saveError = errorMessage(err);
    }
  }

  async function runProbe(mode: 'anthropic' | 'ollama') {
    if (!config) return;
    const slot = mode === 'anthropic' ? probeAnthropic : probeOllama;
    slot.status = 'running';
    slot.result = null;

    let settings: Record<string, unknown>;
    if (mode === 'anthropic') {
      settings = {
        api_key: resolveAnthropicKeyField(),
        model: config.anthropic.model,
        max_tokens: config.anthropic.max_tokens,
      };
    } else {
      settings = { url: config.ollama.url, model: config.ollama.model, max_tokens: config.ollama.max_tokens };
    }

    try {
      slot.result = await probeAskDocsConfig(mode, settings);
    } catch (err) {
      slot.result = { ok: false, error: errorMessage(err) };
    }
    slot.status = 'done';
    if (mode === 'anthropic') probeAnthropic = slot; else probeOllama = slot;
  }
</script>

<div class="max-w-3xl mx-auto p-6 space-y-6">
  <div>
    <h1 class="text-2xl font-semibold">Ask Docs · LLM Configuration</h1>
    <p class="text-sm text-[color:var(--color-text-muted)] mt-1">Choose which LLM backend powers the chat.</p>
  </div>

  {#if loadError}
    <div class="p-4 bg-red-900/30 border border-red-700 rounded text-sm">
      Failed to load config: {loadError}
    </div>
  {:else if !config}
    <p class="text-[color:var(--color-text-muted)]">Loading...</p>
  {:else}
    <fieldset class="space-y-3">
      <legend class="font-medium">Active mode</legend>
      <label class="flex items-center gap-2">
        <input type="radio" bind:group={config.llm_mode} value="anthropic" />
        <span>Anthropic (cloud)</span>
      </label>
      <label class="flex items-center gap-2">
        <input type="radio" bind:group={config.llm_mode} value="ollama" />
        <span>BYO Ollama (self-hosted)</span>
      </label>
      <label class="flex items-center gap-2 opacity-50">
        <input type="radio" disabled value="hoelscher_proxy" />
        <span>Hoelscher proxy <em class="text-xs">(coming soon)</em></span>
      </label>
    </fieldset>

    <section class="border border-[color:var(--color-border)] rounded-lg p-4 space-y-3">
      <h2 class="font-medium">Anthropic settings</h2>
      <div class="space-y-2">
        <label class="block">
          <span class="text-sm">API key</span>
          {#if !anthropicKeyDirty && (config.anthropic.api_key as { _set: boolean })?._set}
            <div class="flex items-center gap-2">
              <input type="password" value="••••••••set" disabled
                class="flex-1 px-3 py-2 bg-[color:var(--color-bg)] border border-[color:var(--color-border)] rounded text-sm font-mono opacity-70" />
              <button type="button" onclick={clearAnthropicKey} class="text-xs px-3 py-2 border border-[color:var(--color-border)] rounded hover:bg-[color:var(--color-surface-2)]">
                Clear
              </button>
            </div>
          {:else}
            <input
              type="password"
              placeholder="sk-ant-api03-..."
              value={anthropicKeyInput}
              oninput={(e) => setAnthropicKey((e.target as HTMLInputElement).value)}
              class="w-full px-3 py-2 bg-[color:var(--color-bg)] border border-[color:var(--color-border)] rounded text-sm font-mono"
            />
          {/if}
        </label>
        <label class="block">
          <span class="text-sm">Model</span>
          <input type="text" bind:value={config.anthropic.model}
            class="w-full px-3 py-2 bg-[color:var(--color-bg)] border border-[color:var(--color-border)] rounded text-sm font-mono" />
        </label>
        <label class="block">
          <span class="text-sm">Max answer tokens</span>
          <input type="number" min="1" max="8192" bind:value={config.anthropic.max_tokens}
            class="w-32 px-3 py-2 bg-[color:var(--color-bg)] border border-[color:var(--color-border)] rounded text-sm font-mono" />
        </label>
        <div class="flex items-center gap-3 pt-2">
          <button type="button" disabled={probeAnthropic.status === 'running'}
            onclick={() => runProbe('anthropic')}
            class="px-3 py-1.5 text-sm border border-[color:var(--color-border)] rounded hover:bg-[color:var(--color-surface-2)] disabled:opacity-50">
            {probeAnthropic.status === 'running' ? 'Testing...' : 'Test Anthropic'}
          </button>
          {#if probeAnthropic.result}
            {#if probeAnthropic.result.ok}
              <span class="text-xs text-green-400">OK · {probeAnthropic.result.latency_ms}ms</span>
            {:else}
              <span class="text-xs text-red-400">{probeAnthropic.result.error}</span>
            {/if}
          {/if}
        </div>
      </div>
    </section>

    <section class="border border-[color:var(--color-border)] rounded-lg p-4 space-y-3">
      <h2 class="font-medium">Ollama settings</h2>
      <div class="space-y-2">
        <label class="block">
          <span class="text-sm">URL</span>
          <input type="text" placeholder="http://192.168.10.50:11434" bind:value={config.ollama.url}
            class="w-full px-3 py-2 bg-[color:var(--color-bg)] border border-[color:var(--color-border)] rounded text-sm font-mono" />
        </label>
        <label class="block">
          <span class="text-sm">Model</span>
          <input type="text" placeholder="llama3.1:8b" bind:value={config.ollama.model}
            class="w-full px-3 py-2 bg-[color:var(--color-bg)] border border-[color:var(--color-border)] rounded text-sm font-mono" />
        </label>
        <label class="block">
          <span class="text-sm">Max answer tokens</span>
          <input type="number" min="1" max="8192" bind:value={config.ollama.max_tokens}
            class="w-32 px-3 py-2 bg-[color:var(--color-bg)] border border-[color:var(--color-border)] rounded text-sm font-mono" />
        </label>
        <div class="flex items-center gap-3 pt-2">
          <button type="button" disabled={probeOllama.status === 'running'}
            onclick={() => runProbe('ollama')}
            class="px-3 py-1.5 text-sm border border-[color:var(--color-border)] rounded hover:bg-[color:var(--color-surface-2)] disabled:opacity-50">
            {probeOllama.status === 'running' ? 'Testing...' : 'Test Ollama'}
          </button>
          {#if probeOllama.result}
            {#if probeOllama.result.ok}
              <span class="text-xs text-green-400">OK · {probeOllama.result.latency_ms}ms</span>
            {:else}
              <span class="text-xs text-red-400">{probeOllama.result.error}</span>
            {/if}
          {/if}
        </div>
      </div>
    </section>

    <!-- Advanced -->
    <section class="border border-[color:var(--color-border)] rounded-lg p-4 space-y-3">
      <h2 class="font-medium">Advanced</h2>
      <label class="flex items-start gap-3">
        <input type="checkbox" bind:checked={config.reranker.enabled} class="mt-1" />
        <span class="text-sm">
          <span class="block font-medium">Cross-encoder reranking</span>
          <span class="block text-[color:var(--color-text-muted)] mt-1">
            Improves citation quality at the cost of ~50–200ms per query. The first chat after
            enabling pulls an ~80MB model into the backend container (one-time, ~5–10s).
          </span>
        </span>
      </label>
    </section>

    <!-- Hoelscher proxy placeholder -->
    <section class="border border-[color:var(--color-border)] rounded-lg p-4 opacity-60">
      <h2 class="font-medium">Hoelscher proxy</h2>
      <p class="text-sm text-[color:var(--color-text-muted)] mt-1">Coming soon — managed inference via Hoelscher Automation.</p>
    </section>

    <div class="flex items-center gap-3 pt-2">
      <button type="button" onclick={handleSave} disabled={saveStatus === 'saving'}
        class="px-5 py-2 bg-[color:var(--color-accent)] text-[color:var(--color-bg)] rounded font-medium hover:opacity-90 disabled:opacity-50">
        {saveStatus === 'saving' ? 'Saving...' : 'Save changes'}
      </button>
      {#if saveStatus === 'saved'}
        <span class="text-xs text-green-400">Saved</span>
      {:else if saveStatus === 'error'}
        <span class="text-xs text-red-400">{saveError}</span>
      {/if}
    </div>
  {/if}
</div>
