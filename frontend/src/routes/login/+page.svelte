<script lang="ts">
  import { goto } from '$app/navigation';
  import { login } from '$lib/stores/auth';

  let email = $state('');
  let password = $state('');
  let error = $state<string | null>(null);
  let busy = $state(false);

  async function handleSubmit(event: Event) {
    event.preventDefault();
    error = null;
    busy = true;
    try {
      await login(email, password);
      await goto('/');
    } catch (err) {
      const detail = (err as { detail?: string }).detail;
      error = detail ?? 'Login failed';
    } finally {
      busy = false;
    }
  }
</script>

<div class="min-h-screen flex items-center justify-center px-4">
  <form onsubmit={handleSubmit} class="w-full max-w-sm bg-[color:var(--color-surface)] p-8 rounded-lg border border-[color:var(--color-border)]">
    <h1 class="text-2xl font-semibold mb-6">Sign in</h1>

    <label class="block mb-4">
      <span class="block text-sm text-[color:var(--color-text-muted)] mb-1">Email</span>
      <input
        type="email"
        bind:value={email}
        required
        autocomplete="email"
        class="w-full px-3 py-2 bg-[color:var(--color-bg)] border border-[color:var(--color-border)] rounded text-[color:var(--color-text)] focus:outline-none focus:border-[color:var(--color-accent)]"
      />
    </label>

    <label class="block mb-6">
      <span class="block text-sm text-[color:var(--color-text-muted)] mb-1">Password</span>
      <input
        type="password"
        bind:value={password}
        required
        autocomplete="current-password"
        class="w-full px-3 py-2 bg-[color:var(--color-bg)] border border-[color:var(--color-border)] rounded text-[color:var(--color-text)] focus:outline-none focus:border-[color:var(--color-accent)]"
      />
    </label>

    {#if error}
      <p class="text-sm text-red-400 mb-4">{error}</p>
    {/if}

    <button
      type="submit"
      disabled={busy}
      class="w-full py-2 bg-[color:var(--color-accent)] text-[color:var(--color-bg)] rounded font-medium hover:opacity-90 disabled:opacity-50"
    >
      {busy ? 'Signing in...' : 'Sign in'}
    </button>
  </form>
</div>
