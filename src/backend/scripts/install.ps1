# Installation/configuration d'AELYN en une commande (equivalent PowerShell
# de install.sh, meme sequence, voir ce fichier pour les commentaires
# detailles sur chaque etape).
#
# Usage : powershell -ExecutionPolicy Bypass -File install.ps1 [-Reconfigure] [-NoVoice] [-WithHeavyModel]
param(
    [switch]$Reconfigure,
    [switch]$NoVoice,
    [switch]$WithHeavyModel
)

$ErrorActionPreference = "Stop"

$ScriptDir = $PSScriptRoot
$BackendDir = (Resolve-Path (Join-Path $ScriptDir "..")).Path
$FrontendDir = (Resolve-Path (Join-Path $BackendDir "..\frontend\web")).Path
$EnvFile = Join-Path $BackendDir ".env"
$EnvExample = Join-Path $BackendDir ".env.example"

# ---------------------------------------------------------- 0. langue du script
#
# Langue d'AFFICHAGE DE CE SCRIPT uniquement : AELYN lui-meme (prompts LLM,
# routage de phrases, interface web) reste entierement en francais quel que
# soit ce choix - le traduire est un chantier separe bien plus gros, pas
# celui de cet installeur.
Write-Host ""
Write-Host "Langue du script d'installation / Installer script language :"
Write-Host "  1) Francais (par defaut)"
Write-Host "  2) English"
$LangAnswer = Read-Host ">"
$LangChoice = if ($LangAnswer -in @("2", "en", "EN", "English", "english")) { "en" } else { "fr" }

$Messages = @{
    fr = @{
        step_prereq = "1/8 Verification des prerequis"
        step_gpu = "2/8 Detection GPU"
        step_env = "3/8 Configuration (.env)"
        step_profile = "4/8 Ton profil (profil.json)"
        step_sync = "5/8 Installation des dependances Python (peut prendre plusieurs minutes)"
        step_ollama = "6/8 Telechargement des modeles Ollama"
        step_frontend = "7/8 Installation du frontend"
        step_done = "8/8 Termine"
        err_uv = "uv reste introuvable meme apres une tentative d'installation automatique (pas d'acces internet, ou configuration non prise en charge). Installe-le a la main : https://docs.astral.sh/uv/getting-started/installation/, puis relance ce script."
        info_installing_uv = "uv introuvable, installation automatique en cours..."
        err_ollama_missing = "Ollama est introuvable. Installe-le : https://ollama.com/download"
        err_ollama_down = "Ollama est installe mais ne repond pas. Lance 'ollama serve' dans un autre terminal puis relance ce script."
        err_npm = "npm est introuvable. Installe Node.js : https://nodejs.org"
        warn_espeak = "espeak-ng introuvable (voix Kokoro indisponible sans lui)."
        warn_espeak_win = "winget install eSpeak-NG.eSpeak-NG -- sinon relance avec -NoVoice."
        gpu_found = "GPU NVIDIA detecte :"
        gpu_none = "Aucun GPU NVIDIA detecte -> torch CPU (plus lent sur les embeddings/la transcription, mais fonctionne partout)"
        gpu_other_vendor = "Remarque : une carte graphique non-NVIDIA (AMD/Intel) a ete detectee, mais il n'existe pas de build PyTorch Windows fiable pour elle (ROCm Linux uniquement, Intel XPU experimental) -> repli sur CPU."
        env_created = ".env cree depuis .env.example"
        profil_created = "profil.json cree depuis profil.example.json (suis l'etape suivante pour le remplir avec tes vraies infos)"
        already_set = "Deja configure, laisse tel quel :"
        prompted = "Configure a l'instant :"
        user_name = "Ton prenom (utilise pour signer les brouillons de mail)"
        user_full_name = "Ton nom complet (en-tete CV/lettre de motivation)"
        user_contact_email = "Email de contact pour le CV/la lettre de motivation"
        user_phone = "Telephone (optionnel)"
        user_linkedin = "LinkedIn (optionnel)"
        user_city = "Ville (optionnel)"
        email_user = "Adresse Gmail (agent mail)"
        email_pass_deferred = "Mot de passe d'application Gmail : laisse VIDE volontairement (voir le rappel a la fin de l'installation)."
        passkey_prompt = "Passkey pour modifier les reglages depuis le frontend [Entree pour accepter {0}, ou tape la tienne]"
        ft_intro = "France Travail (recherche d'offres, optionnel -- Entree pour passer) : https://francetravail.io"
        ft_client_id = "  Client ID France Travail"
        ft_client_secret = "  Client Secret France Travail"
        keywords = "Mots-cles de recherche d'offres, separes par des virgules"
        department = "Codes departement (INSEE, 2 chiffres), separes par des virgules"
        youtube_intro = "YouTube (recherche video, optionnel -- Entree pour passer) : https://console.cloud.google.com/apis/credentials"
        youtube_key = "  Cle API YouTube Data v3"
        public_apis_intro = "Sources d'offres complementaires (optionnel, en plus de France Travail -- Entree pour passer chacune)."
        public_apis_enable = "Activer les sources complementaires maintenant ? [o/N]"
        adzuna_intro = "  Adzuna (international) : https://developer.adzuna.com"
        adzuna_app_id = "  Adzuna app_id"
        adzuna_app_key = "  Adzuna app_key"
        reed_intro = "  Reed (Royaume-Uni) : https://www.reed.co.uk/developers"
        reed_key = "  Cle API Reed"
        careerjet_intro = "  Careerjet (programme Publisher) : https://careerjet.com/partners/register/as-publisher"
        careerjet_key = "  Cle API Careerjet"
        jooble_intro = "  Jooble : https://fr.jooble.org/api/about"
        jooble_key = "  Cle API Jooble"
        public_apis_free_note = "  RemoteOK, Remotive et Arbeitnow ne demandent aucune cle et sont utilisees automatiquement des que les sources complementaires sont activees."
        profil_intro = "Remplissons ton vrai profil (repris mot pour mot pour ton CV/tes lettres de motivation, rien n'est jamais invente au-dela)."
        profil_howto_1 = "  1. Ouvre le fichier exemple ci-dessous, et ton propre CV/export LinkedIn/tes notes."
        profil_howto_2 = "  2. Colle LES DEUX dans un assistant IA (ChatGPT, Claude...) et demande-lui de reecrire TES informations dans EXACTEMENT cette structure JSON."
        profil_howto_3 = "  3. Colle le resultat JSON ci-dessous, puis tape une ligne contenant juste : EOF"
        profil_howto_skip = "  (Ou tape simplement : skip  -- pour garder l'exemple pour l'instant et editer profil.json a la main plus tard.)"
        profil_example_path = "  Fichier exemple :"
        profil_paste_prompt = "Colle ton JSON maintenant :"
        profil_ok = "  profil.json mis a jour avec tes informations."
        profil_skip = "  Etape ignoree - profil.json garde le contenu de l'exemple. Edite-le a la main plus tard, ou relance avec -Reconfigure."
        profil_invalid = "  Non valide, profil.json laisse tel quel (exemple garde) :"
        profil_already_customized = "  profil.json a deja l'air personnalise (different de l'exemple) - laisse tel quel. Relance avec -Reconfigure pour refaire cette etape."
        sync_voice = "  Avec la voix (reconnaissance + synthese) -- relance avec -NoVoice pour sauter cette etape."
        warn_voice_sync_failed = "L'installation des dependances vocales a echoue (PyAudio a souvent besoin des en-tetes PortAudio + d'un compilateur C). On continue SANS la voix : le reste d'AELYN fonctionne tres bien sans elle. Corrige PortAudio/les outils de build et relance avec -Reconfigure pour rajouter la voix plus tard."
        ollama_heavy_note = "  Optionnel : 'ollama pull mistral:7b' ameliore le routage d'intention sur PC (pas sur Raspberry Pi), ignore par defaut."
        frontend_env_created = "cree depuis .env.example"
        done_launch = "Pour lancer AELYN :"
        done_frontend = "  Frontend :"
        done_api = "  API :"
        warn_ft_missing = "France Travail non configure : la recherche d'offres ne fonctionnera pas tant que FRANCE_TRAVAIL_CLIENT_ID/_SECRET ne sont pas renseignes dans"
        reminder_title = "IMPORTANT - il te reste une etape manuelle :"
        reminder_email_pass_1 = "  Ouvre le fichier .env ci-dessus et renseigne EMAIL_PASS a la main (un mot de passe d'APPLICATION Gmail, pas ton mot de passe normal) :"
        reminder_email_pass_2 = "  1. Active la validation en deux etapes sur ton compte Google si ce n'est pas deja fait : https://myaccount.google.com/security"
        reminder_email_pass_3 = "  2. Genere un mot de passe d'application ici : https://myaccount.google.com/apppasswords"
        reminder_email_pass_4 = "  3. Colle-le comme EMAIL_PASS=... dans"
        reminder_email_pass_done = "  (Deja renseigne -- rien a faire ici.)"
    }
    en = @{
        step_prereq = "1/8 Checking prerequisites"
        step_gpu = "2/8 GPU detection"
        step_env = "3/8 Configuration (.env)"
        step_profile = "4/8 Your profile (profil.json)"
        step_sync = "5/8 Installing Python dependencies (can take several minutes)"
        step_ollama = "6/8 Downloading Ollama models"
        step_frontend = "7/8 Installing the frontend"
        step_done = "8/8 Done"
        err_uv = "uv still not found after attempting to install it automatically (no internet access, or an unsupported setup). Install it by hand: https://docs.astral.sh/uv/getting-started/installation/, then re-run this script."
        info_installing_uv = "uv not found, installing it automatically..."
        err_ollama_missing = "Ollama not found. Install it: https://ollama.com/download"
        err_ollama_down = "Ollama is installed but not responding. Run 'ollama serve' in another terminal, then re-run this script."
        err_npm = "npm not found. Install Node.js: https://nodejs.org"
        warn_espeak = "espeak-ng not found (Kokoro voice unavailable without it)."
        warn_espeak_win = "winget install eSpeak-NG.eSpeak-NG -- or re-run with -NoVoice."
        gpu_found = "NVIDIA GPU detected:"
        gpu_none = "No NVIDIA GPU detected -> CPU torch (slower on embeddings/transcription, but works everywhere)"
        gpu_other_vendor = "Note: a non-NVIDIA GPU (AMD/Intel) was detected, but there is no reliable Windows PyTorch build for it yet (ROCm is Linux-only, Intel XPU is experimental) -> falling back to CPU."
        env_created = ".env created from .env.example"
        profil_created = "profil.json created from profil.example.json (follow the next step to fill it with your real info)"
        already_set = "Already configured, left as-is:"
        prompted = "Configured just now:"
        user_name = "Your first name (used to sign draft emails)"
        user_full_name = "Your full name (CV / cover letter header)"
        user_contact_email = "Contact email for the CV / cover letter"
        user_phone = "Phone (optional)"
        user_linkedin = "LinkedIn (optional)"
        user_city = "City (optional)"
        email_user = "Gmail address (email agent)"
        email_pass_deferred = "Gmail app password: left EMPTY on purpose (see the reminder at the end of this install)."
        passkey_prompt = "Passkey to change settings from the web frontend [Enter to accept {0}, or type your own]"
        ft_intro = "France Travail (job search, optional -- Enter to skip): https://francetravail.io"
        ft_client_id = "  France Travail Client ID"
        ft_client_secret = "  France Travail Client Secret"
        keywords = "Job search keywords, comma-separated"
        department = "Department codes (INSEE, 2 digits), comma-separated"
        youtube_intro = "YouTube (video search, optional -- Enter to skip): https://console.cloud.google.com/apis/credentials"
        youtube_key = "  YouTube Data v3 API key"
        public_apis_intro = "Extra job sources (optional, complement France Travail -- Enter to skip each one)."
        public_apis_enable = "Enable extra job sources now? [y/N]"
        adzuna_intro = "  Adzuna (international): https://developer.adzuna.com"
        adzuna_app_id = "  Adzuna app_id"
        adzuna_app_key = "  Adzuna app_key"
        reed_intro = "  Reed (UK): https://www.reed.co.uk/developers"
        reed_key = "  Reed API key"
        careerjet_intro = "  Careerjet (publisher program): https://careerjet.com/partners/register/as-publisher"
        careerjet_key = "  Careerjet API key"
        jooble_intro = "  Jooble: https://fr.jooble.org/api/about"
        jooble_key = "  Jooble API key"
        public_apis_free_note = "  RemoteOK, Remotive and Arbeitnow need no API key and are used automatically once extra sources are enabled."
        profil_intro = "Let's fill in your real profile (used word-for-word for your CV/cover letters, nothing is ever invented beyond it)."
        profil_howto_1 = "  1. Open the example file below, and your own CV/LinkedIn export/notes."
        profil_howto_2 = "  2. Paste BOTH into an AI assistant (ChatGPT, Claude...) and ask it to rewrite YOUR information into EXACTLY this JSON structure."
        profil_howto_3 = "  3. Paste the JSON result below, then type a line with only: EOF"
        profil_howto_skip = "  (Or just type: skip  -- to keep the example for now and edit profil.json by hand later.)"
        profil_example_path = "  Example file:"
        profil_paste_prompt = "Paste your JSON now:"
        profil_ok = "  profil.json updated with your information."
        profil_skip = "  Skipped - profil.json keeps the example content. Edit it by hand later, or re-run with -Reconfigure."
        profil_invalid = "  Not valid, profil.json left unchanged (example kept):"
        profil_already_customized = "  profil.json already looks customized (different from the example) - left as-is. Re-run with -Reconfigure to redo this step."
        sync_voice = "  With voice (speech recognition + synthesis) -- re-run with -NoVoice to skip this."
        warn_voice_sync_failed = "Installing voice dependencies failed (PyAudio often needs PortAudio headers + a C compiler). Continuing WITHOUT voice: the rest of AELYN works fine without it. Fix PortAudio/build tools and re-run with -Reconfigure to add voice back later."
        ollama_heavy_note = "  Optional: 'ollama pull mistral:7b' improves intent routing on a PC (not on Raspberry Pi), skipped by default."
        frontend_env_created = "created from .env.example"
        done_launch = "To launch AELYN:"
        done_frontend = "  Frontend:"
        done_api = "  API:"
        warn_ft_missing = "France Travail not configured: job search will not work until FRANCE_TRAVAIL_CLIENT_ID/_SECRET are set in"
        reminder_title = "IMPORTANT - one manual step left:"
        reminder_email_pass_1 = "  Open the .env file above and set EMAIL_PASS by hand (a Gmail APP password, not your normal password):"
        reminder_email_pass_2 = "  1. Turn on 2-Step Verification on your Google account if not already on: https://myaccount.google.com/security"
        reminder_email_pass_3 = "  2. Generate an app password here: https://myaccount.google.com/apppasswords"
        reminder_email_pass_4 = "  3. Paste it as EMAIL_PASS=... in"
        reminder_email_pass_done = "  (Already set -- nothing to do here.)"
    }
}

function T($Key) { $Messages[$LangChoice][$Key] }

function Say($msg) { Write-Host "`n$msg" -ForegroundColor Cyan }
function Warn($msg) { Write-Host "! $msg" -ForegroundColor Yellow }
function Fail($msg) { Write-Host "x $msg" -ForegroundColor Red; exit 1 }

# ---------------------------------------------------------------- 1. prerequis

Say (T "step_prereq")

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Warn (T "info_installing_uv")
    try {
        Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression
    } catch {}
    # L'installateur officiel place uv dans %USERPROFILE%\.local\bin et
    # met a jour le PATH utilisateur de facon PERSISTANTE (registre),
    # jamais repris par CETTE session PowerShell deja demarree : complete
    # le PATH de cette execution plutot que de forcer un redemarrage de
    # terminal pour continuer l'installation en cours.
    $env:PATH = "$env:USERPROFILE\.local\bin;$env:PATH"
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        Fail (T "err_uv")
    }
}
Write-Host "  uv : $(uv --version)"

if (-not (Get-Command ollama -ErrorAction SilentlyContinue)) {
    Fail (T "err_ollama_missing")
}
try {
    ollama list | Out-Null
} catch {
    Fail (T "err_ollama_down")
}
Write-Host "  ollama : $(ollama --version 2>&1 | Select-Object -First 1)"

if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    Fail (T "err_npm")
}
Write-Host "  npm : $(npm --version)"

if (-not $NoVoice -and -not (Get-Command espeak-ng -ErrorAction SilentlyContinue)) {
    Warn (T "warn_espeak")
    Warn (T "warn_espeak_win")
}

# ---------------------------------------------------------------- 2. GPU

Say (T "step_gpu")

$GpuIndex = "pytorch-cpu"
$nvidiaSmi = Get-Command nvidia-smi -ErrorAction SilentlyContinue
if ($nvidiaSmi) {
    try {
        $gpuName = & nvidia-smi --query-gpu=name --format=csv,noheader 2>$null | Select-Object -First 1
        if ($gpuName) {
            Write-Host "  $(T 'gpu_found') $gpuName -> torch CUDA (pytorch-cu130)"
            $GpuIndex = "pytorch-cu130"
        }
    } catch {}
}
if ($GpuIndex -eq "pytorch-cpu") {
    Write-Host "  $(T 'gpu_none')"
    # Repli informatif seulement : AMD/Intel detecte ou non, le resultat
    # est le meme (CPU) tant qu'aucun wheel PyTorch fiable n'existe pour
    # eux sous Windows - inutile de risquer une install cassee avec un
    # chemin DirectML non teste.
    try {
        $otherGpu = Get-CimInstance Win32_VideoController -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -match "AMD|Radeon|Intel" }
        if ($otherGpu) { Write-Host "  $(T 'gpu_other_vendor')" }
    } catch {}
}

foreach ($proj in @("$BackendDir\career-agent\pyproject.toml", "$BackendDir\security-agent\pyproject.toml")) {
    $content = Get-Content $proj -Raw
    if ($content -match "AELYN_TORCH_INDEX") {
        $content = $content -replace '\{ index = "AELYN_TORCH_INDEX" \}', "{ index = `"$GpuIndex`" }"
        Set-Content -Path $proj -Value $content -NoNewline
    }
}

# ---------------------------------------------------------------- 3. .env

Say (T "step_env")

if (-not (Test-Path $EnvFile)) {
    Copy-Item $EnvExample $EnvFile
    Write-Host "  $(T 'env_created')"
}

# `profil.json` est volontairement non versionne (donnees perso) : sans ce
# copier, aelyn-api plante au tout premier demarrage (profil_manager le
# charge a l'import du module, donc avant meme qu'une route reponde),
# observe en direct sur un clone neuf de la version lite.
$ProfilFile = Join-Path $BackendDir "career-agent\src\aelyn_career\profil.json"
$ProfilExample = Join-Path $BackendDir "career-agent\src\aelyn_career\profil.example.json"
if ((-not (Test-Path $ProfilFile)) -and (Test-Path $ProfilExample)) {
    Copy-Item $ProfilExample $ProfilFile
    Write-Host "  $(T 'profil_created')"
}

function Get-EnvValue($Key) {
    # `$ErrorActionPreference = "Continue"` LOCAL a cette fonction (ne
    # touche pas la variable du script appelant) : sous le "Stop" global
    # ci-dessus, la moindre ligne stderr d'un exe natif (ex. un simple
    # avertissement uv, tres frequent : hardlink, VIRTUAL_ENV ignore...)
    # devient une erreur TERMINANTE malgre le `2>$null`, qui n'arrive pas
    # a temps pour l'empecher - observe en direct, un avertissement uv
    # anodin faisait planter tout l'installeur a cette etape.
    $ErrorActionPreference = "Continue"
    $out = uv run --project $BackendDir python -c "
import dotenv, sys
v = dotenv.dotenv_values(r'$EnvFile').get('$Key')
sys.stdout.write(v or '')
" 2>$null
    return $out
}

function Set-EnvValue($Key, $Value) {
    # `Push-Location $BackendDir` est necessaire ICI (pas juste
    # `--project`) : `set_env_value` (aelyn_api/env_file.py) resout le
    # `.env` via `dotenv.find_dotenv(usecwd=True)`, qui remonte depuis le
    # REPERTOIRE DE TRAVAIL du process Python, jamais depuis `--project`.
    # Bug reel constate en testant l'equivalent bash de ce script : invoque
    # depuis la racine du depot (le point d'entree documente), aucun
    # `.env` n'etait trouve en remontant depuis la racine (il est dans
    # `src/backend/`, pas un ancetre).
    $ErrorActionPreference = "Continue"
    $escaped = $Value -replace "'", "''"
    Push-Location $BackendDir
    try {
        uv run --project $BackendDir python -c "
from aelyn_api.env_file import set_env_value
set_env_value('$Key', '''$escaped''')
" 2>$null | Out-Null
    } finally {
        Pop-Location
    }
}

$script:AlreadySet = @()
$script:Prompted = @()

function Prompt-Field($Key, $Label, $Default = "") {
    $current = Get-EnvValue $Key
    if ($current -and -not $Reconfigure) {
        $script:AlreadySet += $Key
        return
    }
    $hint = if ($Default) { " [$Default]" } else { "" }
    $value = Read-Host "$Label$hint"
    if (-not $value) { $value = $Default }
    Set-EnvValue $Key $value
    $script:Prompted += $Key
}

Prompt-Field "USER_NAME" (T "user_name")
Prompt-Field "USER_FULL_NAME" (T "user_full_name")
$EmailUserCurrent = Get-EnvValue "EMAIL_USER"
Prompt-Field "USER_CONTACT_EMAIL" (T "user_contact_email") $EmailUserCurrent
Prompt-Field "USER_PHONE" (T "user_phone")
Prompt-Field "USER_LINKEDIN" (T "user_linkedin")
Prompt-Field "USER_CITY" (T "user_city")

Prompt-Field "EMAIL_USER" (T "email_user")
# EMAIL_PASS n'est PLUS demande ici : obtenir un mot de passe
# d'application Gmail implique de quitter le terminal, ce qui coupe le
# flux d'install en plein milieu pour rien - un rappel clair en fin de
# script (etape 8/8) suffit et n'interrompt plus rien ici.
Write-Host "  $(T 'email_pass_deferred')"

if ((-not (Get-EnvValue "SETTINGS_PASSKEY")) -or $Reconfigure) {
    $bytes = New-Object byte[] 24
    [System.Security.Cryptography.RandomNumberGenerator]::Fill($bytes)
    $generated = -join ($bytes | ForEach-Object { $_.ToString("x2") })
    $label = [string]::Format((T "passkey_prompt"), $generated)
    $value = Read-Host $label
    if (-not $value) { $value = $generated }
    Set-EnvValue "SETTINGS_PASSKEY" $value
    $script:Prompted += "SETTINGS_PASSKEY"
} else {
    $script:AlreadySet += "SETTINGS_PASSKEY"
}

Write-Host "$(T 'ft_intro')"
Prompt-Field "FRANCE_TRAVAIL_CLIENT_ID" (T "ft_client_id")
Prompt-Field "FRANCE_TRAVAIL_CLIENT_SECRET" (T "ft_client_secret")

Prompt-Field "KEYWORDS" (T "keywords") "Data Scientist,Machine Learning,Intelligence artificielle"
Prompt-Field "DEPARTMENT" (T "department") "35,75"

Write-Host "$(T 'youtube_intro')"
Prompt-Field "YOUTUBE_API_KEY" (T "youtube_key")

# Sources d'offres complementaires (Adzuna/Reed/Careerjet/Jooble, +
# RemoteOK/Remotive/Arbeitnow qui ne demandent aucune cle) : desactivees
# par defaut, on ne les propose que si l'utilisateur dit explicitement
# oui, pour eviter des appels reseau et des quotas inattendus.
Write-Host ""
Write-Host (T "public_apis_intro")
$EnablePublicApisCurrent = Get-EnvValue "AELYN_ENABLE_PUBLIC_JOB_APIS"
if ($EnablePublicApisCurrent -ne "true" -or $Reconfigure) {
    $enableAnswer = Read-Host (T "public_apis_enable")
    if ($enableAnswer -in @("y", "Y", "yes", "YES", "o", "O", "oui", "OUI")) {
        Set-EnvValue "AELYN_ENABLE_PUBLIC_JOB_APIS" "true"
        Write-Host (T "adzuna_intro")
        Prompt-Field "ADZUNA_APP_ID" (T "adzuna_app_id")
        Prompt-Field "ADZUNA_APP_KEY" (T "adzuna_app_key")
        Write-Host (T "reed_intro")
        Prompt-Field "REED_API_KEY" (T "reed_key")
        Write-Host (T "careerjet_intro")
        Prompt-Field "CAREERJET_API_KEY" (T "careerjet_key")
        Write-Host (T "jooble_intro")
        Prompt-Field "JOOBLE_API_KEY" (T "jooble_key")
        Write-Host (T "public_apis_free_note")
    } else {
        Set-EnvValue "AELYN_ENABLE_PUBLIC_JOB_APIS" "false"
    }
} else {
    $script:AlreadySet += "AELYN_ENABLE_PUBLIC_JOB_APIS"
}

if ($GpuIndex -eq "pytorch-cu130") {
    Set-EnvValue "EMBEDDING_DEVICE" "cuda"
    Set-EnvValue "WHISPER_DEVICE" "cuda"
} else {
    Set-EnvValue "EMBEDDING_DEVICE" "cpu"
    Set-EnvValue "WHISPER_DEVICE" "cpu"
}

if ($script:AlreadySet.Count -gt 0) {
    Write-Host "  $(T 'already_set') $($script:AlreadySet -join ', ')"
}
if ($script:Prompted.Count -gt 0) {
    Write-Host "  $(T 'prompted') $($script:Prompted -join ', ')"
}

# ------------------------------------------------------------- 4. profil.json

Say (T "step_profile")

$ProfilIsDefault = $false
if ((Test-Path $ProfilFile) -and (Test-Path $ProfilExample)) {
    $a = Get-Content $ProfilFile -Raw
    $b = Get-Content $ProfilExample -Raw
    if ($a -eq $b) { $ProfilIsDefault = $true }
}

if ($ProfilIsDefault -or $Reconfigure) {
    Write-Host (T "profil_intro")
    Write-Host (T "profil_howto_1")
    Write-Host "$(T 'profil_example_path') $ProfilExample"
    Write-Host (T "profil_howto_2")
    Write-Host (T "profil_howto_3")
    Write-Host (T "profil_howto_skip")
    Write-Host (T "profil_paste_prompt")

    $PasteLines = @()
    $SkipProfil = $false
    $FirstLine = $true
    while ($true) {
        $line = Read-Host
        if ($FirstLine -and $line -eq "skip") {
            $SkipProfil = $true
            break
        }
        $FirstLine = $false
        if ($line -eq "EOF") { break }
        $PasteLines += $line
    }

    if ($SkipProfil -or $PasteLines.Count -eq 0) {
        Write-Host (T "profil_skip")
    } else {
        $PasteFile = [System.IO.Path]::GetTempFileName()
        $PasteLines -join "`n" | Set-Content -Path $PasteFile -Encoding utf8 -NoNewline
        Push-Location $BackendDir
        # Sauvegarde/restauration explicite (pas juste un scope de
        # fonction) : ce bloc est directement dans le corps du script, pas
        # dans une fonction - sans ça, le "Continue" fuiterait sur tout le
        # reste du script. Meme raison que Get-EnvValue/Set-EnvValue
        # ci-dessus : `2>&1` sur un exe natif est encore plus sensible au
        # "Stop" global (chaque ligne stderr devient un ErrorRecord
        # terminant), et cet appel en a besoin pour remonter les erreurs
        # Python au lieu de simplement les jeter.
        $PreviousEap = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        try {
            $validation = uv run --project $BackendDir python -c "
import json
from aelyn_career.profil_manager import validate_profil_structure

with open(r'$PasteFile', encoding='utf-8') as f:
    text = f.read()
try:
    data = json.loads(text)
except json.JSONDecodeError as exc:
    print(f'JSON invalide/invalid JSON: {exc}')
    raise SystemExit(1)
problems = validate_profil_structure(data)
if problems:
    print(chr(10).join(problems))
    raise SystemExit(1)
with open(r'$ProfilFile', 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
print('OK')
" 2>&1
        } finally {
            Pop-Location
            Remove-Item $PasteFile -ErrorAction SilentlyContinue
            $ErrorActionPreference = $PreviousEap
        }
        if ($validation -join "`n" -eq "OK") {
            Write-Host (T "profil_ok")
        } else {
            Warn (T "profil_invalid")
            Write-Host ($validation -join "`n")
        }
    }
} else {
    Write-Host (T "profil_already_customized")
}

# ---------------------------------------------------------------- 5. uv sync

Say (T "step_sync")

$syncArgs = @("--project", $BackendDir)
if (-not $NoVoice) {
    $syncArgs += @("--extra", "voice")
    Write-Host (T "sync_voice")
}
# `PyAudio` (extra voice) compile depuis les sources sur beaucoup de
# machines (pas de wheel prebuilt pour toutes les combinaisons
# OS/Python) et a besoin des en-tetes PortAudio + d'un compilateur C :
# un echec de build ici ne doit pas faire echouer tout le script (Ollama,
# frontend restent a faire). En cas d'echec AVEC --extra voice, on
# retente SANS (le reste d'AELYN fonctionne tres bien sans la voix, cf.
# `aelyn.core.voice`, dont les imports lourds sont tous paresseux).
Push-Location $BackendDir
try {
    & uv sync @syncArgs
    if ($LASTEXITCODE -ne 0) {
        if (-not $NoVoice) {
            Warn (T "warn_voice_sync_failed")
            & uv sync --project $BackendDir
            if ($LASTEXITCODE -ne 0) {
                throw "uv sync failed"
            }
            $NoVoice = $true
        } else {
            throw "uv sync failed"
        }
    }
} finally {
    Pop-Location
}

# ---------------------------------------------------------------- 6. ollama

Say (T "step_ollama")

ollama pull qwen3:4b
ollama pull gemma3:4b
if ($WithHeavyModel) {
    ollama pull mistral:7b
} else {
    Write-Host (T "ollama_heavy_note")
}

# ---------------------------------------------------------------- 7. frontend

Say (T "step_frontend")

Push-Location $FrontendDir
try {
    & npm install
} finally {
    Pop-Location
}
$FrontendEnvLocal = Join-Path $FrontendDir ".env.local"
if (-not (Test-Path $FrontendEnvLocal)) {
    Copy-Item (Join-Path $FrontendDir ".env.example") $FrontendEnvLocal
    Write-Host "  $FrontendEnvLocal $(T 'frontend_env_created')"
}

# ---------------------------------------------------------------- 8. resume

Say (T "step_done")

Write-Host "$(T 'done_launch') $ScriptDir\start.ps1"
Write-Host "$(T 'done_frontend') http://localhost:5173"
Write-Host "$(T 'done_api') http://localhost:8001/docs"
if (-not (Get-EnvValue "FRANCE_TRAVAIL_CLIENT_ID")) {
    Warn "$(T 'warn_ft_missing') $EnvFile."
}

Say (T "reminder_title")
if (-not (Get-EnvValue "EMAIL_PASS")) {
    Write-Host "$(T 'reminder_email_pass_1') $EnvFile"
    Write-Host (T "reminder_email_pass_2")
    Write-Host (T "reminder_email_pass_3")
    Write-Host "$(T 'reminder_email_pass_4') $EnvFile"
} else {
    Write-Host (T "reminder_email_pass_done")
}
