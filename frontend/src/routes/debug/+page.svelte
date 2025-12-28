<script lang="ts">
	import { onMount } from 'svelte';

	type ConnectionInfo = {
		id: number;
		client?: [string, number] | null;
		headers?: Record<string, string>;
	};

	type ConnectionsResponse = {
		count: number;
		connections: ConnectionInfo[];
	};

	const defaultBase =
		(import.meta.env.VITE_AGGREGATOR_BASE as string | undefined) ?? 'http://localhost:7999';

	let apiBase = defaultBase;
	let data: ConnectionsResponse | null = null;
	let loading = false;
	let error: string | null = null;
	let lastFetched: Date | null = null;
	let statusText = 'Idle';

	const normalizeBase = (base: string) => base.trim().replace(/\/$/, '');

	const formatClient = (client?: [string, number] | null) => {
		if (!client) return 'unknown';
		const [host, port] = client;
		return `${host}:${port}`;
	};

	async function fetchConnections() {
		const url = `${normalizeBase(apiBase)}/debug/connections`;

		loading = true;
		error = null;
		statusText = `Requesting ${url}`;

		try {
			const res = await fetch(url, { headers: { Accept: 'application/json' } });
			if (!res.ok) {
				throw new Error(`Request failed with status ${res.status}`);
			}
			const json = (await res.json()) as ConnectionsResponse;
			data = json;
			lastFetched = new Date();
			statusText = `OK (${json.count} connections)`;
		} catch (err) {
			error = err instanceof Error ? err.message : String(err);
			data = null;
			statusText = `Error hitting ${url}`;
		} finally {
			loading = false;
		}
	}

	onMount(fetchConnections);
</script>

<div class="min-h-screen bg-slate-50 text-slate-900">
	<div class="mx-auto max-w-5xl p-6 space-y-6">
		<header class="flex flex-wrap items-center justify-between gap-3">
			<div>
				<p class="text-sm uppercase tracking-[0.2em] text-slate-500">Diagnostics</p>
				<h1 class="text-3xl font-bold">WebSocket Connections</h1>
			</div>
			<div class="flex items-center gap-3">
				<div class="rounded-full bg-slate-900 px-3 py-1 text-xs text-white shadow-sm">
					{loading ? 'Requesting…' : statusText}
				</div>
				<button
					class="rounded-md bg-slate-900 px-4 py-2 text-white shadow-sm transition hover:bg-slate-800 active:translate-y-px disabled:opacity-60"
					on:click={fetchConnections}
					disabled={loading}
				>
					{loading ? 'Refreshing…' : 'Refresh'}
				</button>
				{#if lastFetched}
					<span class="text-sm text-slate-500">
						Updated {lastFetched.toLocaleTimeString()}
					</span>
				{/if}
			</div>
		</header>

		<section class="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
			<div class="flex flex-wrap items-center gap-3">
				<label class="text-sm font-medium text-slate-700" for="apiBase">Aggregator base URL</label>
				<input
					id="apiBase"
					type="text"
					class="flex-1 min-w-[240px] rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm outline-none focus:border-slate-400 focus:bg-white focus:ring-2 focus:ring-slate-200"
					bind:value={apiBase}
				/>
				<span class="text-xs text-slate-500">Default: {defaultBase}</span>
			</div>
			<p class="mt-2 text-sm text-slate-500">
				This calls <code class="rounded bg-slate-100 px-1 py-0.5 text-xs">/debug/connections</code> on
				the aggregator. Make sure this URL is reachable from the browser and not blocked by a proxy.
			</p>
		</section>

		{#if error}
			<div class="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-800">
				<strong>Error:</strong>
				{error}
			</div>
		{/if}

		<section class="rounded-xl border border-slate-200 bg-white p-4 shadow-sm space-y-3">
			<div class="flex items-center justify-between">
				<div class="flex items-center gap-2">
					<div class="h-2 w-2 rounded-full {loading ? 'bg-amber-500' : 'bg-emerald-500'}"></div>
					<p class="text-sm text-slate-600">Active connections</p>
				</div>
				<p class="text-lg font-semibold">
					{#if data}
						{data.count}
					{:else if loading}
						…
					{:else}
						0
					{/if}
				</p>
			</div>

			<div class="overflow-auto rounded-lg border border-slate-100">
				<table class="min-w-full text-left text-sm">
					<thead class="bg-slate-50 text-slate-600">
						<tr>
							<th class="px-3 py-2 font-semibold">Connection ID</th>
							<th class="px-3 py-2 font-semibold">Client</th>
							<th class="px-3 py-2 font-semibold">Headers (subset)</th>
						</tr>
					</thead>
					<tbody class="divide-y divide-slate-100">
						{#if loading}
							<tr>
								<td colspan="3" class="px-3 py-4 text-center text-slate-500">Loading…</td>
							</tr>
						{:else if data && data.connections.length > 0}
							{#each data.connections as conn}
								<tr class="hover:bg-slate-50">
									<td class="px-3 py-2 font-mono text-xs text-slate-700">{conn.id}</td>
									<td class="px-3 py-2 text-slate-800">{formatClient(conn.client)}</td>
									<td class="px-3 py-2">
										{#if conn.headers}
											<div class="flex flex-wrap gap-1 text-[11px] text-slate-700">
												{#each Object.entries(conn.headers).slice(0, 6) as [k, v]}
													<span class="rounded bg-slate-100 px-2 py-1">
														<strong>{k}:</strong>
														{v}
													</span>
												{/each}
												{#if Object.keys(conn.headers).length > 6}
													<span class="rounded bg-slate-100 px-2 py-1">…</span>
												{/if}
											</div>
										{:else}
											<span class="text-slate-400">n/a</span>
										{/if}
									</td>
								</tr>
							{/each}
						{:else}
							<tr>
								<td colspan="3" class="px-3 py-4 text-center text-slate-500">
									No active connections reported.
								</td>
							</tr>
						{/if}
					</tbody>
				</table>
			</div>
		</section>
	</div>
</div>
