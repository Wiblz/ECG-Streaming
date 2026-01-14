import { api } from '$lib/api/client';
import { error } from '@sveltejs/kit';
import type { PageLoad } from './$types';

export const prerender = false;
export const ssr = false;

export const load: PageLoad = async ({ params }) => {
	const sessionId = parseInt(params.id);

	if (isNaN(sessionId)) {
		error(400, 'Invalid session ID');
	}

	try {
		const session = await api.getSession(sessionId);
		return {
			session
		};
	} catch (e) {
		error(404, e instanceof Error ? e.message : 'Session not found');
	}
};
