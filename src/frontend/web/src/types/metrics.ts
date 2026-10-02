export interface TimeSeriesPoint {
  t: string;
  v: number;
}

export interface ResourceTrend {
  nodeId: string;
  nodeLabel: string;
  cpu: TimeSeriesPoint[];
  ram: TimeSeriesPoint[];
  tempC: TimeSeriesPoint[];
}

export interface DetectionFrequencyBucket {
  hour: string;
  count: number;
}

export interface CommandStat {
  command: string;
  label: string;
  count: number;
}

export interface CameraUptimeStat {
  camera: string;
  uptimePercent: number;
  detections24h: number;
  avgLatencyMs: number;
}
