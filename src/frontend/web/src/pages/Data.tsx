import { Panel } from "../components/ui/Panel";
import { Sparkline } from "../components/ui/Sparkline";
import { RadialGauge } from "../components/ui/RadialGauge";
import { BarHistogram } from "../components/ui/BarHistogram";
import { resourceTrends, detectionFrequency, commandStats, cameraUptimeStats } from "../mocks";
import styles from "./Data.module.css";

const trend = resourceTrends[0];
const maxCommandCount = Math.max(...commandStats.map((c) => c.count));
const lastCpu = trend.cpu[trend.cpu.length - 1].v;
const lastRam = trend.ram[trend.ram.length - 1].v;
const lastTempC = trend.tempC[trend.tempC.length - 1].v;

export function Data() {
  return (
    <div className={styles.page}>
      <Panel title="Tendances système, AELYN Core (24 h)" className={styles.wide}>
        <div className={styles.trends}>
          <div className={styles.trendCol}>
            <RadialGauge label="CPU" percent={lastCpu} displayValue={`${lastCpu}%`} color="var(--state-blue)" size={64} />
            <Sparkline data={trend.cpu} unit="%" color="var(--state-blue)" max={100} />
          </div>
          <div className={styles.trendCol}>
            <RadialGauge label="RAM" percent={lastRam} displayValue={`${lastRam}%`} color="var(--state-green)" size={64} />
            <Sparkline data={trend.ram} unit="%" color="var(--state-green)" max={100} />
          </div>
          <div className={styles.trendCol}>
            <RadialGauge
              label="Température"
              percent={lastTempC}
              displayValue={`${lastTempC}°C`}
              color="var(--state-amber)"
              size={64}
            />
            <Sparkline data={trend.tempC} unit="°C" color="var(--state-amber)" />
          </div>
        </div>
      </Panel>

      <Panel title="Fréquence de détection (24 h, toutes caméras)" className={styles.wide}>
        <BarHistogram data={detectionFrequency.map((d) => ({ label: d.hour, value: d.count }))} />
      </Panel>

      <Panel title="Commandes exécutées (7 derniers jours)">
        {commandStats.map((c) => (
          <div className={styles.barRow} key={c.command}>
            <span className={styles.barLabel}>{c.label}</span>
            <span className={styles.barTrack}>
              <span className={styles.barFill} style={{ width: `${(c.count / maxCommandCount) * 100}%` }} />
            </span>
            <span className={styles.barCount}>{c.count}</span>
          </div>
        ))}
      </Panel>

      <Panel title="Disponibilité caméras (7 derniers jours)" noPad>
        <div className={styles.tableScroll}>
          <table className={styles.statTable}>
            <thead>
              <tr>
                <th>Caméra</th>
                <th>Disponibilité</th>
                <th>Détections (24 h)</th>
                <th>Latence moy.</th>
              </tr>
            </thead>
            <tbody>
              {cameraUptimeStats.map((c) => (
                <tr key={c.camera}>
                  <td>{c.camera}</td>
                  <td>{c.uptimePercent}%</td>
                  <td>{c.detections24h}</td>
                  <td>{c.avgLatencyMs > 0 ? `${c.avgLatencyMs} ms` : "N/A"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>
    </div>
  );
}
