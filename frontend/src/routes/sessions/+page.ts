import { api } from '$lib/api/client';
import type { PageLoad } from './$types';

export const load: PageLoad = async () => {
  const [sessionsResponse, devicesResponse] = await Promise.all([
    api.getSessions(),
    api.getAllDevices()
  ]);
  return {
    sessions: sessionsResponse.sessions,
    devices: devicesResponse.devices
  };
};
