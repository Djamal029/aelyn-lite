import { useNavigate } from "react-router-dom";
import { Panel } from "../components/ui/Panel";
import { MetricRow, thresholdState, type MetricItem } from "../components/ui/MetricRow";
import { StatusDot } from "../components/ui/StatusDot";
import { CameraTile } from "../components/cameras/CameraTile";
import { EventsTable } from "../components/security/EventsTable";
import { LogPanel } from "../components/ui/LogPanel";
import { CommandBar } from "../components/commandbar/CommandBar";
import { nodes, cameras, securityEvents, activityLog } from "../mocks";
import { useCoreNode } from "../lib/useCoreNode";
import { LITE_MODE } from "../lib/liteMode";
import styles from "./Overview.module.css";

// Les nœuds Raspberry Pi sont du matériel cible non déployé même en version
// complète ; en lite, personne n'en a, donc on les masque plutôt que
// d'afficher "non déployé" pour un appareil qui n'existera jamais ici.
const otherNodes = nodes.filter((n) => n.id !== "core" && !(LITE_MODE && n.id.startsWith("pi-")));

export function Overview() {
  const navigate = useNavigate();
  const { core, networkTotal, live, gpu } = useCoreNode();

  const metricItems: MetricItem[] = [
    { label: "CPU", value: `${core.cpuPercent}%`, state: thresholdState(core.cpuPercent, 70, 90), gauge: { value: core.cpuPercent, max: 100 } },
    { label: "RAM", value: `${core.ramPercent}%`, state: thresholdState(core.ramPercent, 75, 90), gauge: { value: core.ramPercent, max: 100 } },
  ];
  if (gpu) {
    metricItems.push({
      label: "GPU",
      value: `${Math.round(gpu.utilization_percent)}%`,
      state: thresholdState(gpu.utilization_percent, 70, 90),
      gauge: { value: gpu.utilization_percent, max: 100 },
    });
  }
  // Honest, not a placeholder: when GET /system/status says there's no
  // reliable CPU temperature reading on this machine (the common case on
  // Windows without third-party sensor software), the gauge is dropped
  // entirely rather than showing a fabricated number.
  if (core.tempC !== null) {
    metricItems.push({
      label: "TEMP",
      value: `${core.tempC}°C`,
      state: thresholdState(core.tempC, 65, 80),
      gauge: { value: core.tempC, max: 100 },
    });
  }
  metricItems.push({
    label: "DISQUE",
    value: `${core.diskPercent}%`,
    state: thresholdState(core.diskPercent, 80, 95),
    gauge: { value: core.diskPercent, max: 100 },
  });
  // Live: a real cumulative transfer total (see lib/systemStatus.ts for
  // why this can't honestly be an instantaneous rate). Mock: the old
  // flat placeholder rate.
  metricItems.push({ label: "RÉSEAU", value: networkTotal ? `${networkTotal} cumulés` : `${core.netMbps} Mb/s` });

  return (
    <div className={styles.page}>
      <div className={styles.grid}>
        <header className={styles.welcome}>
          <div>
            <div className={styles.eyebrow}>AELYN · ESPACE PERSONNEL</div>
            <h1 className={styles.welcomeTitle}>Votre espace, en un coup d’œil</h1>
            <p className={styles.welcomeText}>Un regard calme sur votre système et vos activités.</p>
          </div>
          <div className={styles.welcomeMark} aria-hidden="true">
            <span />
          </div>
        </header>
        <Panel
          title="Système"
          className={styles.systemPanel}
          meta={
            <span>
              {core.label} · {core.uptime} · {live ? "mesures réelles" : "mode démo — chiffres fictifs"}
            </span>
          }
        >
          <MetricRow items={metricItems} />
          {gpu ? (
            <div className={styles.systemNote}>
              {gpu.name} · {gpu.temperature_celsius}°C · VRAM {Math.round(gpu.memory_used_mb)} / {Math.round(gpu.memory_total_mb)} Mo
            </div>
          ) : null}
          <div className={styles.nodeSummary} style={{ marginTop: 12 }}>
            {otherNodes.map((n) => (
              <div className={styles.nodeLine} key={n.id}>
                <StatusDot kind={n.state === "operational" ? "operational" : "offline"} />
                {n.label} : {n.state === "offline" ? "non déployé" : n.state}
              </div>
            ))}
          </div>
        </Panel>

        {LITE_MODE ? null : (
          <div className={styles.camerasRow}>
            {cameras.slice(0, 2).map((cam) => (
              <CameraTile key={cam.id} camera={cam} onExpand={() => navigate("/cameras")} />
            ))}
          </div>
        )}

        {!LITE_MODE ? <Panel
          title="Événements sécurité"
          className={styles.columnPanel}
          meta={
            <a className={styles.link} onClick={() => navigate("/security")} href="#security">
              Tout voir →
            </a>
          }
          noPad
        >
          <EventsTable events={securityEvents} limit={5} />
        </Panel> : null}

        <Panel
          title="Activité AELYN"
          className={LITE_MODE ? styles.fullPanel : styles.columnPanel}
          meta={
            <a className={styles.link} onClick={() => navigate("/activity")} href="#activity">
              Journal complet →
            </a>
          }
          noPad
        >
          <div className={styles.logBody}>
            <LogPanel entries={activityLog.slice(0, 8)} />
          </div>
        </Panel>
      </div>

      <CommandBar variant="console" onMicClick={() => navigate("/assistant", { state: { openVoice: true } })} />
    </div>
  );
}
