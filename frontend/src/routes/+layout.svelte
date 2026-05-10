<script lang="ts">
  import { goto } from '$app/navigation';
  import { onMount } from 'svelte';

  import { logout } from '$lib/stores/auth';
  import { logoUrl } from '$lib/stores/tenant';
  import { loadModules, modules } from '$lib/stores/modules';

  import '../app.css';

  let { children, data } = $props();

  async function handleLogout() {
    await logout();
    await goto('/login');
  }

  onMount(() => {
    if (data.user) {
      loadModules();
    }
  });

  const tenantLogoUrl = $derived(data.tenant ? logoUrl(data.tenant.logo_filename) : null);
  const companyName = $derived(data.tenant?.company_name ?? 'Portal');
  const askDocsEnabled = $derived($modules.find((m) => m.key === 'ask-docs')?.enabled ?? false);
</script>

<svelte:head>
  <title>{companyName}</title>
</svelte:head>

{#if data.user}
  <header class="border-b border-[color:var(--color-border)] px-6 py-4 flex items-center justify-between">
    <a href="/" class="flex items-center gap-2">
      {#if tenantLogoUrl}
        <img src={tenantLogoUrl} alt="" class="h-7 w-auto" />
      {/if}
      <span class="text-lg font-semibold">{companyName}</span>
    </a>
    <nav class="flex items-center gap-4">
      {#if askDocsEnabled}
        <a href="/modules/ask-docs" class="text-sm text-[color:var(--color-text-muted)] hover:text-[color:var(--color-text)]">Ask Docs</a>
      {/if}
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
