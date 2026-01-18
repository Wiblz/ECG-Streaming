import { api } from '$lib/api/client'
import type { LayoutLoad } from './$types'

export const prerender = true
export const ssr = false

export const load: LayoutLoad = async () => {
	try {
		const response = await api.getVersion()
		return {
			version: response.version
		}
	} catch (err) {
		console.error('Failed to fetch version:', err)
		return {
			version: ''
		}
	}
}
