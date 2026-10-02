# Lance l'API (aelyn-api) et le frontend web ensemble, affiche les deux
# URLs, et arrete les deux proprement sur Ctrl+C.

$ScriptDir = $PSScriptRoot
$BackendDir = (Resolve-Path (Join-Path $ScriptDir "..")).Path
$FrontendDir = (Resolve-Path (Join-Path $BackendDir "..\frontend\web")).Path
$BackendPort = 8001
$FrontendPort = 5173

if (-not (Test-Path (Join-Path $BackendDir ".env"))) {
    Write-Host "Aucun .env trouve. Lance d'abord $ScriptDir\install.ps1" -ForegroundColor Red
    exit 1
}

# `Start-Process -PassThru` (pas `Start-Job`) : un PID de process reel et
# fiable directement, sans la couche job PowerShell qui peut laisser des
# processus enfants orphelins au nettoyage.
$backendProc = Start-Process -FilePath "uv" `
    -ArgumentList "run", "uvicorn", "aelyn_api.main:app", "--port", "$BackendPort", "--app-dir", "aelyn-api/src" `
    -WorkingDirectory $BackendDir -PassThru -NoNewWindow

# `npm.cmd` explicitement (pas juste "npm") : `Get-Command npm` résout vers
# `npm.ps1` sur les installations Node.js récentes, qu'un `Start-Process`
# normal ne sait pas lancer directement (ce n'est pas un vrai exécutable) —
# échouait silencieusement en test (aucun process node, port 5173 jamais
# ouvert, sans la moindre erreur visible). `npm.cmd` existe toujours à côté
# et se lance comme un .exe classique.
$frontendProc = Start-Process -FilePath "npm.cmd" `
    -ArgumentList "run", "dev" `
    -WorkingDirectory $FrontendDir -PassThru -NoNewWindow

Write-Host ""
Write-Host "AELYN demarre..."
Write-Host "  API      : http://localhost:$BackendPort/docs"
Write-Host "  Frontend : http://localhost:$FrontendPort"
Write-Host "(Ctrl+C pour tout arreter)"
Write-Host ""

# `taskkill /T /F` tue l'arbre de processus complet (uv -> python,
# npm -> node) : un `Stop-Process` seul sur le PID de tete peut laisser le
# vrai serveur (uvicorn/node) tourner, le process de tete n'etant qu'un
# lanceur.
function Stop-Tree($Process) {
    if ($Process -and -not $Process.HasExited) {
        try {
            taskkill /PID $Process.Id /T /F | Out-Null
        } catch {}
    }
}

try {
    # Boucle de surveillance plutot qu'un `Wait-Process` bloquant unique :
    # permet a Ctrl+C (qui leve une exception arretant le pipeline) d'etre
    # intercepte par le `finally` ci-dessous a tout moment, et detecte
    # aussi le cas ou l'un des deux serveurs s'arrete tout seul.
    while (-not $backendProc.HasExited -and -not $frontendProc.HasExited) {
        Start-Sleep -Seconds 1
    }
} finally {
    Stop-Tree $backendProc
    Stop-Tree $frontendProc
}
