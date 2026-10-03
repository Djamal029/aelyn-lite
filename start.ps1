# Point d'entree racine : lance AELYN (API + frontend) sans jamais avoir a
# naviguer dans src/backend. Redirige vers le vrai script.
$ScriptDir = $PSScriptRoot
& "$ScriptDir\src\backend\scripts\start.ps1" @args
exit $LASTEXITCODE
