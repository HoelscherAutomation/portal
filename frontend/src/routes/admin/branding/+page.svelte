<script lang="ts">
  import { tenant, updateTenant, uploadLogo, logoUrl } from '$lib/stores/tenant';

  let companyName = $state('');
  let primaryColor = $state('#6dd5fa');
  let welcomeMessage = $state('');
  let logoFile = $state<File | null>(null);
  let busy = $state(false);
  let message = $state<{ kind: 'ok' | 'err'; text: string } | null>(null);

  $effect(() => {
    const t = $tenant;
    if (t) {
      companyName = t.company_name;
      primaryColor = t.primary_color;
      welcomeMessage = t.welcome_message ?? '';
    }
  });

  async function handleSubmit(event: Event) {
    event.preventDefault();
    busy = true;
    message = null;
    try {
      // Upload logo first; if it fails, abort before mutating other fields.
      if (logoFile) {
        await uploadLogo(logoFile);
        logoFile = null;
      }
      await updateTenant({
        company_name: companyName,
        primary_color: primaryColor,
        welcome_message: welcomeMessage || null
      });
      message = { kind: 'ok', text: 'Branding saved.' };
    } catch (err) {
      const detail = (err as { detail?: string }).detail;
      message = { kind: 'err', text: detail ?? 'Save failed.' };
    } finally {
      busy = false;
    }
  }

  function handleLogoSelect(event: Event) {
    const input = event.target as HTMLInputElement;
    logoFile = input.files?.[0] ?? null;
  }

  const currentLogoUrl = $derived($tenant ? logoUrl($tenant.logo_filename) : null);
</script>

<div class="px-6 py-12 max-w-2xl">
  <h1 class="text-3xl font-semibold mb-2">Branding</h1>
  <p class="text-[color:var(--color-text-muted)] mb-8">
    Customize how the portal appears to your team.
  </p>

  <form onsubmit={handleSubmit} class="space-y-6">
    <label class="block">
      <span class="block text-sm text-[color:var(--color-text-muted)] mb-1">Company name</span>
      <input
        type="text"
        bind:value={companyName}
        required
        maxlength="120"
        class="w-full px-3 py-2 bg-[color:var(--color-bg)] border border-[color:var(--color-border)] rounded text-[color:var(--color-text)] focus:outline-none focus:border-[color:var(--color-accent)]"
      />
    </label>

    <label class="block">
      <span class="block text-sm text-[color:var(--color-text-muted)] mb-1">Primary color</span>
      <div class="flex gap-3 items-center">
        <input
          type="color"
          bind:value={primaryColor}
          class="h-10 w-16 rounded border border-[color:var(--color-border)] bg-[color:var(--color-bg)]"
        />
        <input
          type="text"
          bind:value={primaryColor}
          pattern="^#[0-9A-Fa-f]{'{6}'}$"
          class="flex-1 px-3 py-2 bg-[color:var(--color-bg)] border border-[color:var(--color-border)] rounded text-[color:var(--color-text)] font-mono text-sm"
        />
      </div>
    </label>

    <label class="block">
      <span class="block text-sm text-[color:var(--color-text-muted)] mb-1">Welcome message (optional)</span>
      <textarea
        bind:value={welcomeMessage}
        maxlength="500"
        rows="3"
        class="w-full px-3 py-2 bg-[color:var(--color-bg)] border border-[color:var(--color-border)] rounded text-[color:var(--color-text)]"
      ></textarea>
    </label>

    <div class="block">
      <span class="block text-sm text-[color:var(--color-text-muted)] mb-2">Logo</span>
      {#if currentLogoUrl}
        <div class="mb-3 p-3 bg-[color:var(--color-surface)] rounded border border-[color:var(--color-border)] inline-block">
          <img src={currentLogoUrl} alt="Current logo" class="h-12 w-auto" />
        </div>
      {/if}
      <input
        type="file"
        accept="image/png,image/jpeg,image/svg+xml"
        onchange={handleLogoSelect}
        class="block text-sm text-[color:var(--color-text-muted)]"
      />
      {#if logoFile}
        <p class="mt-2 text-xs text-[color:var(--color-text-subtle)]">Selected: {logoFile.name}</p>
      {/if}
    </div>

    {#if message}
      <p class="text-sm {message.kind === 'ok' ? 'text-green-400' : 'text-red-400'}">{message.text}</p>
    {/if}

    <button
      type="submit"
      disabled={busy}
      class="px-5 py-2 bg-[color:var(--color-accent)] text-[color:var(--color-bg)] rounded font-medium hover:opacity-90 disabled:opacity-50"
    >
      {busy ? 'Saving...' : 'Save changes'}
    </button>
  </form>
</div>
