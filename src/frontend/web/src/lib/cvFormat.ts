import type { ApiCvContent } from "./api";

/** Rendu texte lisible d'un `ApiCvContent`, même structure que
 * `format_cv_text` côté backend (career-agent/src/aelyn_career/
 * application_writer.py) : ce composant affiche le JSON structuré que
 * `POST /career/{id}/cv` renvoie, le backend lui-même ne formate QUE sa
 * propre réponse de chat (texte brut), jamais celle de cette route. */
export function formatCvAsText(cv: ApiCvContent): string {
  const lines: string[] = [cv.profil, "", "EXPÉRIENCES"];
  for (const e of cv.experiences) {
    lines.push(`  ${e.role} chez ${e.entreprise} (${e.periode})`);
    for (const p of e.puces) lines.push(`    • ${p}`);
  }
  if (cv.projets.length > 0) {
    lines.push("", "PROJETS");
    for (const p of cv.projets) lines.push(`  ${p.titre} : ${p.description}`);
  }
  lines.push("", "COMPÉTENCES");
  for (const [categorie, items] of Object.entries(cv.competences)) {
    lines.push(`  ${categorie} : ${items.join(", ")}`);
  }
  lines.push("", "FORMATION");
  for (const f of cv.formation) lines.push(`  ${f}`);
  if (cv.certifications.length > 0) {
    lines.push("", "CERTIFICATIONS");
    for (const c of cv.certifications) lines.push(`  ${c}`);
  }
  if (cv.langues.length > 0) lines.push("", `LANGUES : ${cv.langues.join(", ")}`);
  if (cv.centres_interet.length > 0) lines.push(`CENTRES D'INTÉRÊT : ${cv.centres_interet.join(", ")}`);
  return lines.join("\n");
}
