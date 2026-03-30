import { error } from '@sveltejs/kit';
import { api } from '$lib/api/client';
import type { PageLoad } from './$types';

export const prerender = false;
export const ssr = false;

export const load: PageLoad = async ({ params }) => {
  const sessionId = parseInt(params.id);

  if (isNaN(sessionId)) {
    throw error(400, 'Invalid session ID');
  }

  try {
    const [session, devicesResponse] = await Promise.all([
      api.getSession(sessionId),
      api.getAllDevices()
    ]);
    return {
      session,
      devices: devicesResponse.devices
    };
  } catch (e) {
    throw error(404, e instanceof Error ? e.message : 'Session not found');
  }
};
