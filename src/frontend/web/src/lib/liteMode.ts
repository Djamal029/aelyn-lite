/** Version "lite" distribuée aux camarades (pas de caméra/Raspberry Pi
 * physiques) : `VITE_LITE_MODE=true` masque ces sections de l'UI plutôt que
 * d'afficher du matériel qui n'existe pas chez eux. Absent/`false` par
 * défaut, donc l'instance privée (celle de l'auteur) garde tout. */
export const LITE_MODE = import.meta.env.VITE_LITE_MODE === "true";
