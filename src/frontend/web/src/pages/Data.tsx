import { useEffect, useState } from "react";
import { ApiError, getSystemResources } from "../lib/api";
import { Panel } from "../components/ui/Panel";
import { RadialGauge } from "../components/ui/RadialGauge";
import { Sparkline } from "../components/ui/Sparkline";
import type { TimeSeriesPoint } from "../types";
import { useResourcesState, type ResourceSample } from "../lib/resourcesStore";
import styles from "./Data.module.css";

const REFRESH_MS = 15_000;
const MAX_SAMPLES = 48;

function formatMemory(mb: number): string {
  if (mb < 1024) return `${Math.round(mb)} Mo`;
  return `${(mb / 1024).toFixed(1)} Go`;
}

function formatNetwork(bytes: number): string {
  if (bytes < 1_000_000) return `${(bytes / 1_000).toFixed(0)} Ko`;
  if (bytes < 1_000_000_000) return `${(bytes / 1_000_000).toFixed(1)} Mo`;
  return `${(bytes / 1_000_000_000).toFixed(2)} Go`;
}

function chartPoints(samples: ResourceSample[], key: "cpu" | "ram" | "gpu"): TimeSeriesPoint[] {
  return samples.flatMap((sample) => {
    const value = sample[key];
    return typeof value === "number" ? [{ t: sample.time, v: value }] : [];
  });
}

export function Data() {
  const [{ resources, samples, updatedAt }, setResourcesState] = useResourcesState();
  // `loading` ne doit être vrai qu'au tout premier chargement de l'app
  // (rien en mémoire) : sur une revisite de la page, le store a déjà le
  // dernier relevé connu, donc l'écran "Aucune mesure disponible" ne doit
  // plus jamais réapparaître juste parce que le composant a été démonté.
  const [loading, setLoading] = useState(resources === null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    let refreshing = false;

    const refresh = async () => {
      if (refreshing) return;
      refreshing = true;
      try {
        const latest = await getSystemResources();
        if (cancelled) return;
        const now = new Date();
        setResourcesState((prev) => ({
          resources: latest,
          updatedAt: now.toLocaleTimeString("fr-FR"),
          samples: [
            ...prev.samples,
            {
              time: now.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" }),
              cpu: latest.cpu_percent,
              ram: latest.ram.percent,
              ...(latest.gpu.available ? { gpu: latest.gpu.utilization_percent } : {}),
            },
          ].slice(-MAX_SAMPLES),
        }));
        setError(null);
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof ApiError ? err.message : "Mesures système indisponibles.");
        }
      } finally {
        refreshing = false;
        if (!cancelled) setLoading(false);
      }
    };

    void refresh();
    const timer = window.setInterval(() => void refresh(), REFRESH_MS);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const cpuTrend = chartPoints(samples, "cpu");
  const ramTrend = chartPoints(samples, "ram");
  const gpuTrend = chartPoints(samples, "gpu");

  return (
    <div className={styles.page}>
      <header className={styles.heading}>
        <div>
          <div className={styles.eyebrow}>MESURES LOCALES</div>
          <h1 className={styles.title}>Données système</h1>
          <p className={styles.subtitle}>Des mesures réelles, actualisées pendant votre visite.</p>
        </div>
        <div className={styles.refreshStatus} role="status" aria-live="polite">
          <span className={[styles.liveDot, resources ? styles.live : ""].join(" ")} />
          {resources ? `Actualisé à ${updatedAt}` : loading ? "Connexion aux mesures…" : "Mesures indisponibles"}
        </div>
      </header>

      {resources ? (
        <>
          <Panel title="Ressources de cette machine" className={styles.wide}>
            <div className={styles.metrics}>
              <div className={styles.metric}>
                <RadialGauge label="CPU" percent={resources.cpu_percent} displayValue={`${Math.round(resources.cpu_percent)}%`} size={68} />
                <span className={styles.metricNote}>Processeur</span>
              </div>
              <div className={styles.metric}>
                <RadialGauge label="RAM" percent={resources.ram.percent} displayValue={`${Math.round(resources.ram.percent)}%`} color="var(--state-green)" size={68} />
                <span className={styles.metricNote}>
                  {formatMemory(resources.ram.used_mb)} sur {formatMemory(resources.ram.total_mb)}
                </span>
              </div>
              {resources.disks && resources.disks.length > 0 ? (
                resources.disks.map((disk) => (
                  <div className={styles.metric} key={disk.mountpoint}>
                    <RadialGauge
                      label={`Disque ${disk.mountpoint.replace(/[\\/]+$/, "")}`}
                      percent={disk.percent}
                      displayValue={`${Math.round(disk.percent)}%`}
                      color="var(--state-amber)"
                      size={68}
                    />
                    <span className={styles.metricNote}>
                      {disk.used_gb.toFixed(1)} Go sur {disk.total_gb.toFixed(1)} Go
                    </span>
                  </div>
                ))
              ) : (
                <div className={styles.metric}>
                  <RadialGauge label="Disque" percent={resources.disk.percent} displayValue={`${Math.round(resources.disk.percent)}%`} color="var(--state-amber)" size={68} />
                  <span className={styles.metricNote}>
                    {resources.disk.used_gb.toFixed(1)} Go sur {resources.disk.total_gb.toFixed(1)} Go
                  </span>
                </div>
              )}
              {resources.gpu.available ? (
                <div className={styles.metric}>
                  <RadialGauge label="GPU" percent={resources.gpu.utilization_percent} displayValue={`${Math.round(resources.gpu.utilization_percent)}%`} color="var(--state-blue)" size={68} />
                  <span className={styles.metricNote}>{resources.gpu.name}</span>
                  <span className={styles.metricDetail}>
                    {resources.gpu.temperature_celsius}°C · VRAM {formatMemory(resources.gpu.memory_used_mb)} / {formatMemory(resources.gpu.memory_total_mb)}
                  </span>
                </div>
              ) : null}
            </div>
            <div className={styles.measurementNote}>
              <span>
                {resources.cpu_temp_celsius.available
                  ? `Température CPU : ${resources.cpu_temp_celsius.value}°C`
                  : "Température CPU non fournie par cette machine."}
              </span>
              <span>
                Réseau cumulé depuis le démarrage : {formatNetwork(resources.network.bytes_sent + resources.network.bytes_recv)}.
              </span>
            </div>
          </Panel>

          <Panel
            title="Évolution pendant cette visite"
            className={styles.wide}
            meta={<span>{samples.length} relevé(s) · actualisation toutes les 15 secondes</span>}
          >
            {samples.length < 2 ? (
              <p className={styles.waiting}>La courbe se dessinera après le prochain relevé réel.</p>
            ) : (
              <div className={styles.trends}>
                <div className={styles.trend}>
                  <span className={styles.trendLabel}>Processeur</span>
                  <Sparkline data={cpuTrend} unit="%" color="var(--state-blue)" max={100} />
                </div>
                <div className={styles.trend}>
                  <span className={styles.trendLabel}>Mémoire vive</span>
                  <Sparkline data={ramTrend} unit="%" color="var(--state-green)" max={100} />
                </div>
                {resources.gpu.available ? (
                  <div className={styles.trend}>
                    <span className={styles.trendLabel}>Carte graphique</span>
                    <Sparkline data={gpuTrend} unit="%" color="var(--state-blue)" max={100} />
                  </div>
                ) : null}
              </div>
            )}
          </Panel>
        </>
      ) : (
        <Panel title="Aucune mesure disponible" className={styles.wide}>
          <p className={styles.emptyState}>
            {error ?? "La connexion au service de mesures est en cours."}
          </p>
          <p className={styles.metricNote}>Démarrez AELYN Core pour afficher les relevés réels de cette machine.</p>
        </Panel>
      )}
    </div>
  );
}