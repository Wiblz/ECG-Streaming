import type {
  ApiClient,
  BufferStats,
  CollectorsResponse,
  DeviceListParams,
  DeviceInfo,
  DeviceSummaryParams,
  DevicesResponse,
  DeviceStatusResponse,
  Session,
  SessionAccelerometerSamplesResponse,
  SessionListParams,
  SessionSamplesResponse,
  SessionsResponse,
  SyncStats
} from '$lib/types/api';
import { getMockCollectors, getMockDevices, updateMockData } from './mockData';

/**
 * Mock API client implementation for UI testing
 */
export class MockClient implements ApiClient {
  private devicesCache: DeviceInfo[] = [];
  private collectorsCache: CollectorsResponse['collectors'] = [];
  private updateInterval: number | undefined;

  async getVersion(): Promise<{ version: string }> {
    return { version: '0.1.0-mock' };
  }

  constructor() {
    // Initialize mock data
    this.devicesCache = getMockDevices();
    this.collectorsCache = getMockCollectors();

    // Start simulating live updates
    if (typeof window !== 'undefined') {
      this.updateInterval = setInterval(() => {
        const updated = updateMockData(this.devicesCache, this.collectorsCache);
        this.devicesCache = updated.devices;
        this.collectorsCache = updated.collectors;
      }, 2000) as unknown as number;
    }
  }

  /**
   * Cleanup interval on destruction
   */
  destroy() {
    if (this.updateInterval !== undefined) {
      clearInterval(this.updateInterval);
      this.updateInterval = undefined;
    }
  }

  async getDevices(params?: DeviceSummaryParams): Promise<DevicesResponse> {
    // Filter to only synced devices (similar to real API)
    let devices = this.devicesCache.filter((d) => d.sync_ready);

    if (params?.search) {
      const search = params.search.toLowerCase();
      devices = devices.filter((d) => d.device_id.toLowerCase().includes(search));
    }

    if (params?.sync_ready !== undefined) {
      devices = devices.filter((d) => d.sync_ready === params.sync_ready);
    }

    devices = [...devices].sort((a, b) => {
      const direction = params?.sort_order === 'desc' ? -1 : 1;
      switch (params?.sort_by) {
        case 'sync_ready':
          return direction * (Number(a.sync_ready) - Number(b.sync_ready));
        case 'confidence':
          return direction * ((a.sync?.confidence ?? -1) - (b.sync?.confidence ?? -1));
        case 'sample_count':
          return direction * ((a.sync?.sample_count ?? -1) - (b.sync?.sample_count ?? -1));
        case 'device_id':
        default:
          return direction * a.device_id.localeCompare(b.device_id);
      }
    });

    return this.paginateDevices(devices, params);
  }

  async getAllDevices(params?: DeviceListParams): Promise<DevicesResponse> {
    let devices = [...this.devicesCache];

    if (params?.search) {
      const search = params.search.toLowerCase();
      devices = devices.filter(
        (d) =>
          d.device_id.toLowerCase().includes(search) ||
          (d.nickname !== undefined &&
            d.nickname !== null &&
            d.nickname.toLowerCase().includes(search))
      );
    }

    if (params?.sync_ready !== undefined) {
      devices = devices.filter((d) => d.sync_ready === params.sync_ready);
    }

    if (params?.status !== undefined) {
      devices = devices.filter((d) => d.status === params.status);
    }

    if (params?.collector_id !== undefined) {
      devices = devices.filter((d) => d.collector_id === params.collector_id);
    }

    if (params?.has_nickname === true) {
      devices = devices.filter(
        (d) => d.nickname !== undefined && d.nickname !== null && d.nickname.trim() !== ''
      );
    } else if (params?.has_nickname === false) {
      devices = devices.filter(
        (d) => d.nickname === undefined || d.nickname === null || d.nickname.trim() === ''
      );
    }

    devices.sort((a, b) => {
      const direction = params?.sort_order === 'asc' ? 1 : -1;
      switch (params?.sort_by) {
        case 'first_seen':
          return direction * ((a.first_seen ?? 0) - (b.first_seen ?? 0));
        case 'total_samples':
          return direction * ((a.total_samples ?? 0) - (b.total_samples ?? 0));
        case 'device_id':
          return direction * a.device_id.localeCompare(b.device_id);
        case 'nickname':
          return direction * (a.nickname ?? '').localeCompare(b.nickname ?? '');
        case 'status':
          return direction * (a.status ?? '').localeCompare(b.status ?? '');
        case 'last_update':
          return direction * ((a.last_update ?? 0) - (b.last_update ?? 0));
        case 'last_seen':
        default:
          return direction * ((a.last_seen ?? 0) - (b.last_seen ?? 0));
      }
    });

    return this.paginateDevices(devices, params);
  }

  async getDeviceStatus(): Promise<DeviceStatusResponse> {
    // Return only currently connected devices
    const connectedDevices = this.devicesCache
      .filter((d) => d.status && d.status !== 'DISCONNECTED' && d.status !== 'UNKNOWN')
      .map((d) => ({
        device_id: d.device_id,
        collector_id: d.collector_id ?? null,
        collector_name:
          this.collectorsCache.find((c) => c.collector_id === d.collector_id)?.display_name || null,
        status: d.status!,
        last_update: d.last_update!,
        battery_level: d.battery_level ?? null,
        error_message: d.error_message ?? null
      }));
    return { devices: connectedDevices, count: connectedDevices.length };
  }

  async updateDeviceNickname(
    deviceId: string,
    nickname: string | null
  ): Promise<{ success: boolean; device_id: string; nickname: string | null }> {
    const device = this.devicesCache.find((d) => d.device_id === deviceId);
    if (device) {
      device.nickname = nickname;
      return { success: true, device_id: deviceId, nickname };
    }
    throw new Error('Device not found');
  }

  async getCollectors(): Promise<CollectorsResponse> {
    return { collectors: this.collectorsCache };
  }

  async getStats(): Promise<{
    sync: SyncStats;
    grpc: Record<string, unknown>;
    ecg_websocket_connections: number;
    acc_websocket_connections: number;
    ecg_buffer: BufferStats;
    acc_buffer: BufferStats;
  }> {
    // Return mock stats
    const emptyStats: BufferStats = {
      total_samples: 0,
      duration_seconds: 0,
      device_count: 0,
      samples_per_device: {},
      samples_per_second: 0,
      samples_per_second_per_device: {},
      oldest_timestamp: null,
      newest_timestamp: null,
      total_processed: 0,
      buffer_utilization: 0
    };
    return {
      sync: { total_devices: 0, ready_devices: 0, devices: {} },
      grpc: {},
      ecg_websocket_connections: 0,
      acc_websocket_connections: 0,
      ecg_buffer: emptyStats,
      acc_buffer: emptyStats
    };
  }

  async getBufferStats(): Promise<BufferStats> {
    return {
      total_samples: 0,
      duration_seconds: 0,
      device_count: 0,
      samples_per_device: {},
      samples_per_second: 0,
      samples_per_second_per_device: {},
      oldest_timestamp: null,
      newest_timestamp: null,
      total_processed: 0,
      buffer_utilization: 0
    };
  }

  async getAccelerometerBufferStats(): Promise<BufferStats> {
    return {
      total_samples: 0,
      duration_seconds: 0,
      device_count: 0,
      samples_per_device: {},
      samples_per_second: 0,
      samples_per_second_per_device: {},
      oldest_timestamp: null,
      newest_timestamp: null,
      total_processed: 0,
      buffer_utilization: 0
    };
  }

  async getSessions(_params?: SessionListParams): Promise<SessionsResponse> {
    // Return empty sessions for mock mode
    return {
      sessions: [],
      count: 0,
      total: 0,
      limit: _params?.limit ?? null,
      offset: _params?.offset ?? 0
    };
  }

  private paginateDevices(
    devices: DeviceInfo[],
    params?: { limit?: number; offset?: number }
  ): DevicesResponse {
    const offset = params?.offset ?? 0;
    const limit = params?.limit;
    const paginatedDevices =
      limit !== undefined ? devices.slice(offset, offset + limit) : devices.slice(offset);

    return {
      devices: paginatedDevices,
      count: paginatedDevices.length,
      total: devices.length,
      limit: limit ?? null,
      offset
    };
  }

  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  async getSession(_sessionId: number): Promise<Session> {
    throw new Error('Sessions not supported in mock mode');
  }

  async getSessionSamples(
    // eslint-disable-next-line @typescript-eslint/no-unused-vars
    _sessionId: number,
    // eslint-disable-next-line @typescript-eslint/no-unused-vars
    _params?: {
      device_id?: string;
      start_time?: number;
      end_time?: number;
      limit?: number;
      offset?: number;
    }
  ): Promise<SessionSamplesResponse> {
    throw new Error('Sessions not supported in mock mode');
  }

  async getSessionAccelerometerSamples(
    // eslint-disable-next-line @typescript-eslint/no-unused-vars
    _sessionId: number,
    // eslint-disable-next-line @typescript-eslint/no-unused-vars
    _params?: {
      device_id?: string;
      start_time?: number;
      end_time?: number;
      limit?: number;
      offset?: number;
    }
  ): Promise<SessionAccelerometerSamplesResponse> {
    throw new Error('Sessions not supported in mock mode');
  }

  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  async deleteSession(_sessionId: number): Promise<{ success: boolean }> {
    throw new Error('Sessions not supported in mock mode');
  }

  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  getSessionExportUrl(_sessionId: number): string {
    throw new Error('Sessions not supported in mock mode');
  }

  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  async importSession(_file: File): Promise<{
    success: boolean;
    session_id?: number;
    message?: string;
    error?: string;
  }> {
    throw new Error('Sessions not supported in mock mode');
  }

  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  async startSession(_notes?: string | null): Promise<{
    success: boolean;
    session_id?: number;
    message: string;
    error?: string;
  }> {
    throw new Error('Session control not supported in mock mode');
  }

  async stopSession(): Promise<{
    success: boolean;
    session_id?: number;
    message: string;
    error?: string;
  }> {
    throw new Error('Session control not supported in mock mode');
  }

  async getActiveSession(): Promise<{
    active: boolean;
    session?: Session;
  }> {
    throw new Error('Session control not supported in mock mode');
  }
}
