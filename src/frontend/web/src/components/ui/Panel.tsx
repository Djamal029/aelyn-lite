import type { ReactNode } from "react";
import styles from "./Panel.module.css";

interface PanelProps {
  title: string;
  meta?: ReactNode;
  children: ReactNode;
  noPad?: boolean;
  className?: string;
}

/** The base surface for every section of the console. Deliberately
 * plain: a title bar and a body, thin border, no shadow/glass/rounded
 * excess: a panel exists to group something the user can read or act
 * on, not to decorate the page. */
export function Panel({ title, meta, children, noPad, className }: PanelProps) {
  return (
    <section className={[styles.panel, className].filter(Boolean).join(" ")}>
      <header className={styles.header}>
        <h2 className={styles.title}>{title}</h2>
        {meta ? <div className={styles.meta}>{meta}</div> : null}
      </header>
      <div className={[styles.body, noPad ? styles.noPad : ""].join(" ")}>{children}</div>
    </section>
  );
}
