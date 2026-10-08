import { Panel } from "../components/ui/Panel";
import { LITE_MODE } from "../lib/liteMode";
import styles from "./Commands.module.css";

interface CommandExample {
  phrase: string;
  desc: string;
}

interface CommandGroup {
  title: string;
  note?: string;
  examples: CommandExample[];
}

// Un seul et même routeur (fast_router.py puis le LLM en repli) traite le
// texte tapé et la voix : chaque exemple ci-dessous marche à l'identique
// dans les deux modes, et ce n'est qu'un sous-ensemble illustratif, pas
// une syntaxe figée (une formulation proche fonctionne aussi).
const MAIL_GROUP: CommandGroup = {
  title: "Mails",
  examples: [
    { phrase: "Vérifie mes mails", desc: "Relève les nouveaux mails et résume ce qu'ils contiennent." },
    { phrase: "Quoi de neuf ?", desc: "Équivalent à « vérifie mes mails »." },
    { phrase: "Trie mes mails", desc: "Analyse les mails et propose une action pour chacun." },
    { phrase: "Fais-moi un rapport", desc: "Résumé des actions des dernières 24h." },
    { phrase: "Valide la 3", desc: "Exécute l'action n°3 proposée par le triage." },
    { phrase: "Rejette la 2", desc: "Ignore l'action n°2 proposée par le triage." },
  ],
};

const CAREER_GROUP: CommandGroup = {
  title: "Recherche d'offres",
  note: "Mots-clés, ville, type de contrat (stage, alternance...) et nombre d'offres sont compris dans une phrase libre.",
  examples: [
    { phrase: "Cherche des offres de data scientist", desc: "Recherche générale sur le profil." },
    { phrase: "Trouve-moi 5 stages de développeur à Paris", desc: "Filtre par contrat, ville et nombre de résultats." },
    { phrase: "Des offres chez EDF", desc: "Recherche ciblée sur une entreprise." },
  ],
};

const MEDIA_GROUP: CommandGroup = {
  title: "Télé (Freebox)",
  examples: [
    { phrase: "Lance Netflix", desc: "" },
    { phrase: "Lance YouTube", desc: "" },
    { phrase: "Cherche Stranger Things sur Netflix", desc: "Lance une recherche avec le titre demandé." },
    { phrase: "Cherche des vidéos de chats sur YouTube", desc: "" },
    { phrase: "Mets en pause / Reprends la lecture", desc: "" },
    { phrase: "Suivant / Précédent", desc: "" },
    { phrase: "Monte le son / Baisse le son / Coupe le son", desc: "" },
    { phrase: "Reviens à l'accueil / Retour", desc: "" },
    { phrase: "Allume la télé", desc: "Signal HDMI-CEC : n'a d'effet que si le téléviseur le prend en charge." },
  ],
};

const CAMERA_GROUP: CommandGroup = {
  title: "Caméras",
  examples: [
    { phrase: "Montre la caméra de l'entrée", desc: "" },
    { phrase: "Montre la caméra du salon", desc: "" },
    { phrase: "Montre toute la pièce", desc: "Équivalent à « caméra du salon »." },
  ],
};

const FREE_GROUP: CommandGroup = {
  title: "Conversation libre",
  examples: [
    { phrase: "N'importe quelle autre question", desc: "Pas de formule magique nécessaire : AELYN répond normalement en dehors de ces commandes." },
  ],
};

export function Commands() {
  const groups = LITE_MODE
    ? [MAIL_GROUP, CAREER_GROUP, MEDIA_GROUP, FREE_GROUP]
    : [MAIL_GROUP, CAREER_GROUP, MEDIA_GROUP, CAMERA_GROUP, FREE_GROUP];

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <div className={styles.title}>Commandes</div>
        <div className={styles.subtitle}>
          Ce qu'AELYN comprend aujourd'hui, à l'écrit comme à la voix. Une formulation proche
          fonctionne aussi : ce n'est pas une syntaxe figée.
        </div>
      </div>

      <div className={styles.grid}>
        {groups.map((group) => (
          <Panel key={group.title} title={group.title}>
            <div className={styles.group}>
              {group.note ? <div className={styles.groupNote}>{group.note}</div> : null}
              {group.examples.map((example) => (
                <div key={example.phrase} className={styles.row}>
                  <span className={styles.phrase}>{example.phrase}</span>
                  {example.desc ? <span className={styles.desc}>{example.desc}</span> : null}
                </div>
              ))}
            </div>
          </Panel>
        ))}
      </div>
    </div>
  );
}
