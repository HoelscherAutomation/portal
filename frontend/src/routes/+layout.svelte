<script lang="ts">
  import { goto } from '$app/navigation';
  import { logout } from '$lib/stores/auth';
  import '../app.css';

  let { children, data } = $props();

  async function handleLogout() {
    await logout();
    await goto('/login');
  }
</script>

{#if data.user}
  <header class="border-b border-[color:var(--color-border)] px-6 py-4 flex items-center justify-between">
    <a href="/" class="text-lg font-semibold">Portal</a>
    <nav class="flex items-center gap-4">
      <a href="/admin" class="text-sm text-[color:var(--color-text-muted)] hover:text-[color:var(--color-text)]">Admin</a>
      <span class="text-sm text-[color:var(--color-text-subtle)]">{data.user.email}</span>
      <button
        type="button"
        onclick={handleLogout}
        class="text-sm text-[color:var(--color-text-muted)] hover:text-[color:var(--color-text)]"
      >
        Sign out
      </button>
    </nav>
  </header>
{/if}

<main>
  {@render children()}
</main>
