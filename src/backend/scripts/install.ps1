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

function Say($msg) { Write-Host "`n$msg" -ForegroundColor Cyan }
function Warn($msg) { Write-Host "! $msg" -ForegroundColor Yellow }
function Fail($msg) { Write-Host "x $msg" -ForegroundColor Red; exit 1 }

# ---------------------------------------------------------------- 1. prerequis

Say "1/7 Verification des prerequis"

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Fail "uv est introuvable. Installe-le : https://docs.astral.sh/uv/getting-started/installation/"
}
Write-Host "  uv : $(uv --version)"

if (-not (Get-Command ollama -ErrorAction SilentlyContinue)) {
    Fail "Ollama est introuvable. Installe-le : https://ollama.com/download"
}
try {
    ollama list | Out-Null
} catch {
    Fail "Ollama est installe mais ne repond pas. Lance 'ollama serve' dans un autre terminal puis relance ce script."
}
Write-Host "  ollama : $(ollama --version 2>&1 | Select-Object -First 1)"

if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    Fail "npm est introuvable. Installe Node.js : https://nodejs.org"
}
Write-Host "  npm : $(npm --version)"

if (-not $NoVoice -and -not (Get-Command espeak-ng -ErrorAction SilentlyContinue)) {
    Warn "espeak-ng introuvable (voix Kokoro indisponible sans lui)."
    Warn "winget install eSpeak-NG.eSpeak-NG -- sinon relance avec -NoVoice."
}

# ---------------------------------------------------------------- 2. GPU

Say "2/7 Detection GPU"

$GpuIndex = "pytorch-cpu"
$nvidiaSmi = Get-Command nvidia-smi -ErrorAction SilentlyContinue
if ($nvidiaSmi) {
    try {
        $gpuName = & nvidia-smi --query-gpu=name --format=csv,noheader 2>$null | Select-Object -First 1
        if ($gpuName) {
            Write-Host "  GPU NVIDIA detecte : $gpuName -> torch CUDA (pytorch-cu130)"
            $GpuIndex = "pytorch-cu130"
        }
    } catch {}
}
if ($GpuIndex -eq "pytorch-cpu") {
    Write-Host "  Aucun GPU NVIDIA detecte -> torch CPU (plus lent sur les embeddings/la transcription, mais fonctionne partout)"
}

foreach ($proj in @("$BackendDir\career-agent\pyproject.toml", "$BackendDir\security-agent\pyproject.toml")) {
    $content = Get-Content $proj -Raw
    if ($content -match "AELYN_TORCH_INDEX") {
        $content = $content -replace '\{ index = "AELYN_TORCH_INDEX" \}', "{ index = `"$GpuIndex`" }"
        Set-Content -Path $proj -Value $content -NoNewline
    }
}

# ---------------------------------------------------------------- 3. .env

Say "3/7 Configuration (.env)"

if (-not (Test-Path $EnvFile)) {
    Copy-Item $EnvExample $EnvFile
    Write-Host "  .env cree depuis .env.example"
}

# `profil.json` est volontairement non versionne (donnees perso) : sans ce
# copier, aelyn-api plante au tout premier demarrage (profil_manager le
# charge a l'import du module, donc avant meme qu'une route reponde),
# observe en direct sur un clone neuf de la version lite.
$ProfilFile = Join-Path $BackendDir "career-agent\src\aelyn_career\profil.json"
$ProfilExample = Join-Path $BackendDir "career-agent\src\aelyn_career\profil.example.json"
if ((-not (Test-Path $ProfilFile)) -and (Test-Path $ProfilExample)) {
    Copy-Item $ProfilExample $ProfilFile
    Write-Host "  profil.json cree depuis profil.example.json (edite-le avec tes vraies infos pour un CV/lettre pertinents)"
}

function Get-EnvValue($Key) {
    $out = uv run --project $BackendDir python -c "
import dotenv, sys
v = dotenv.dotenv_values(r'$EnvFile').get('$Key')
sys.stdout.write(v or '')
" 2>$null
    return $out
}

function Set-EnvValue($Key, $Value) {
    $escaped = $Value -replace "'", "''"
    uv run --project $BackendDir python -c "
from aelyn_api.env_file import set_env_value
set_env_value('$Key', '''$escaped''')
" 2>$null | Out-Null
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

function Prompt-Secret($Key, $Label) {
    $current = Get-EnvValue $Key
    if ($current -and -not $Reconfigure) {
        $script:AlreadySet += $Key
        return
    }
    $secure = Read-Host $Label -AsSecureString
    $bstr = [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    $value = [System.Runtime.InteropServices.Marshal]::PtrToStringAuto($bstr)
    [System.Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
    Set-EnvValue $Key $value
    $script:Prompted += $Key
}

Prompt-Field "USER_NAME" "Ton prenom (utilise pour signer les brouillons de mail)"
Prompt-Field "USER_FULL_NAME" "Ton nom complet (en-tete CV/lettre de motivation)"
$EmailUserCurrent = Get-EnvValue "EMAIL_USER"
Prompt-Field "USER_CONTACT_EMAIL" "Email de contact pour le CV/la lettre de motivation" $EmailUserCurrent
Prompt-Field "USER_PHONE" "Telephone (optionnel)"
Prompt-Field "USER_LINKEDIN" "LinkedIn (optionnel)"
Prompt-Field "USER_CITY" "Ville (optionnel)"

Prompt-Field "EMAIL_USER" "Adresse Gmail (agent mail)"
if ((-not (Get-EnvValue "EMAIL_PASS")) -or $Reconfigure) {
    Write-Host "  Mot de passe d'application Gmail (PAS ton mot de passe normal) :"
    Write-Host "  https://myaccount.google.com/apppasswords"
}
Prompt-Secret "EMAIL_PASS" "Mot de passe d'application Gmail"

if ((-not (Get-EnvValue "SETTINGS_PASSKEY")) -or $Reconfigure) {
    $bytes = New-Object byte[] 24
    [System.Security.Cryptography.RandomNumberGenerator]::Fill($bytes)
    $generated = -join ($bytes | ForEach-Object { $_.ToString("x2") })
    $value = Read-Host "Passkey pour modifier les reglages depuis le frontend [Entree pour accepter $generated, ou tape la tienne]"
    if (-not $value) { $value = $generated }
    Set-EnvValue "SETTINGS_PASSKEY" $value
    $script:Prompted += "SETTINGS_PASSKEY"
} else {
    $script:AlreadySet += "SETTINGS_PASSKEY"
}

Write-Host "  France Travail (recherche d'offres, optionnel -- Entree pour passer) : https://francetravail.io"
Prompt-Field "FRANCE_TRAVAIL_CLIENT_ID" "  Client ID France Travail"
Prompt-Field "FRANCE_TRAVAIL_CLIENT_SECRET" "  Client Secret France Travail"

Prompt-Field "KEYWORDS" "Mots-cles de recherche d'offres, separes par des virgules" "Data Scientist,Machine Learning,Intelligence artificielle"
Prompt-Field "DEPARTMENT" "Codes departement (INSEE, 2 chiffres), separes par des virgules" "35,75"

Write-Host "  YouTube (recherche video, optionnel -- Entree pour passer) : https://console.cloud.google.com/apis/credentials"
Prompt-Field "YOUTUBE_API_KEY" "  Cle API YouTube Data v3"

if ($GpuIndex -eq "pytorch-cu130") {
    Set-EnvValue "EMBEDDING_DEVICE" "cuda"
    Set-EnvValue "WHISPER_DEVICE" "cuda"
} else {
    Set-EnvValue "EMBEDDING_DEVICE" "cpu"
    Set-EnvValue "WHISPER_DEVICE" "cpu"
}

if ($script:AlreadySet.Count -gt 0) {
    Write-Host "  Deja configure, laisse tel quel : $($script:AlreadySet -join ', ')"
}
if ($script:Prompted.Count -gt 0) {
    Write-Host "  Configure a l'instant : $($script:Prompted -join ', ')"
}

# ---------------------------------------------------------------- 4. uv sync

Say "4/7 Installation des dependances Python (peut prendre plusieurs minutes)"

$syncArgs = @("--project", $BackendDir)
if (-not $NoVoice) {
    $syncArgs += @("--extra", "voice")
    Write-Host "  Avec la voix (reconnaissance + synthese) -- relance avec -NoVoice pour sauter cette etape."
}
Push-Location $BackendDir
try {
    & uv sync @syncArgs
} finally {
    Pop-Location
}

# ---------------------------------------------------------------- 5. ollama

Say "5/7 Telechargement des modeles Ollama"

ollama pull qwen3:4b
ollama pull gemma3:4b
if ($WithHeavyModel) {
    ollama pull mistral:7b
} else {
    Write-Host "  Optionnel : 'ollama pull mistral:7b' ameliore le routage d'intention sur PC (pas sur Raspberry Pi), ignore par defaut."
}

# ---------------------------------------------------------------- 6. frontend

Say "6/7 Installation du frontend"

Push-Location $FrontendDir
try {
    & npm install
} finally {
    Pop-Location
}
$FrontendEnvLocal = Join-Path $FrontendDir ".env.local"
if (-not (Test-Path $FrontendEnvLocal)) {
    Copy-Item (Join-Path $FrontendDir ".env.example") $FrontendEnvLocal
    Write-Host "  $FrontendEnvLocal cree depuis .env.example"
}

# ---------------------------------------------------------------- 7. resume

Say "7/7 Termine"

Write-Host "Pour lancer AELYN : $ScriptDir\start.ps1"
Write-Host "  Frontend : http://localhost:5173"
Write-Host "  API      : http://localhost:8001/docs"
if (-not (Get-EnvValue "FRANCE_TRAVAIL_CLIENT_ID")) {
    Warn "France Travail non configure : la recherche d'offres ne fonctionnera pas tant que FRANCE_TRAVAIL_CLIENT_ID/_SECRET ne sont pas renseignes dans $EnvFile."
}
