import { Panel } from "../components/ui/Panel";
import { MetricRow, thresholdState, type MetricItem } from "../components/ui/MetricRow";
import { RadialGauge } from "../components/ui/RadialGauge";
import { StatusDot } from "../components/ui/StatusDot";
import { nodes } from "../mocks";
import { useCoreNode } from "../lib/useCoreNode";
import { LITE_MODE } from "../lib/liteMode";
import type { NodeStatus } from "../types";
import styles from "./System.module.css";

function buildMetricItems(node: NodeStatus, networkTotal: string | null): MetricItem[] {
  const items: MetricItem[] = [
    { label: "CPU", value: `${node.cpuPercent}%`, state: thresholdState(node.cpuPercent, 70, 90), gauge: { value: node.cpuPercent, max: 100 } },
    { label: "RAM", value: `${node.ramPercent}%`, state: thresholdState(node.ramPercent, 75, 90), gauge: { value: node.ramPercent, max: 100 } },
  ];
  // Honest, not a placeholder: dropped entirely rather than showing a
  // fabricated number when the backend has no reliable sensor for it
  // (the common case on Windows without third-party sensor software).
  if (node.tempC !== null) {
    items.push({
      label: "TEMP",
      value: `${node.tempC}°C`,
      state: thresholdState(node.tempC, 65, 80),
      gauge: { value: node.tempC, max: 100 },
    });
  }
  items.push({
    label: "DISQUE",
    value: `${node.diskPercent}%`,
    state: thresholdState(node.diskPercent, 80, 95),
    gauge: { value: node.diskPercent, max: 100 },
  });
  items.push({ label: "RÉSEAU", value: networkTotal ? `${networkTotal} cumulés` : `${node.netMbps} Mb/s` });
  return items;
}

export function System() {
  const { core, live, networkTotal, gpu, tailscale } = useCoreNode();
  const displayNodes = nodes
    .filter((n) => !(LITE_MODE && n.id.startsWith("pi-")))
    .map((n) => (n.id === "core" ? core : n));

  return (
    <div className={styles.page}>
      {displayNodes.map((node) => (
        <Panel
          key={node.id}
          title={node.label}
          meta={<span className={styles.uptime}>uptime {node.uptime}</span>}
        >
          <div className={styles.nodeHead}>
            <div>
              <div className={styles.nodeTitle}>
                <StatusDot kind={node.state === "operational" ? "operational" : node.state === "degraded" ? "degraded" : "offline"} />
                {node.state === "operational" ? "Opérationnel" : node.state === "degraded" ? "Dégradé" : "Hors ligne"}
              </div>
              <div className={styles.role}>{node.role}</div>
            </div>
          </div>

          <div style={{ marginTop: 12 }}>
            <MetricRow
              items={node.state === "offline" ? [{ label: "STATUT", value: "matériel non déployé" }] : buildMetricItems(node, node.id === "core" ? networkTotal : null)}
            />
          </div>

          {node.id === "core" && live && gpu ? (
            <div className={styles.gpuRow}>
              <RadialGauge
                label="GPU"
                percent={gpu.utilization_percent}
                displayValue={`${Math.round(gpu.utilization_percent)}%`}
                color="var(--state-blue)"
                size={64}
              />
              <div className={styles.gpuInfo}>
                <div className={styles.gpuName}>{gpu.name}</div>
                <div className={styles.gpuDetail}>
                  {gpu.temperature_celsius}°C · VRAM {Math.round(gpu.memory_used_mb)} / {Math.round(gpu.memory_total_mb)} Mo
                </div>
              </div>
            </div>
          ) : null}

          <div className={styles.tailscaleLine}>
            <StatusDot kind={node.tailscale === "connected" ? "connected" : "disconnected"} />
            Tailscale : {node.tailscale === "connected" ? "connecté" : "déconnecté"}
            {node.id === "core" && live && tailscale
              ? ` (${tailscale.available ? tailscale.backend_state : tailscale.reason})`
              : null}
          </div>

          <div className={styles.services}>
            {node.services.map((s) => (
              <div className={styles.service} key={s.name}>
                <StatusDot kind={s.state === "operational" ? "operational" : s.state === "degraded" ? "degraded" : "offline"} />
                <span className={styles.serviceName}>{s.name}</span>
                {s.detail ? <span className={styles.serviceDetail}>: {s.detail}</span> : null}
              </div>
            ))}
          </div>
        </Panel>
      ))}
    </div>
  );
}
