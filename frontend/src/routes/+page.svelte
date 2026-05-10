<script lang="ts">
  let { data } = $props();
  // Layout guarantees data.user is non-null on this route (redirects to /login otherwise).
  const user = data.user!;
</script>

<div class="px-6 py-12">
  <h1 class="text-3xl font-semibold mb-2">Welcome, {user.email}</h1>
  <p class="text-[color:var(--color-text-muted)]">No modules enabled yet. The shell is up — modules come in subsequent plans.</p>
</div>
