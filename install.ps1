# Point d'entree racine : installe AELYN sans jamais avoir a naviguer dans
# src/backend. Redirige simplement vers le vrai script, en transmettant
# tous les arguments (ex. -Reconfigure, -NoVoice).
$ScriptDir = $PSScriptRoot
& "$ScriptDir\src\backend\scripts\install.ps1" @args
exit $LASTEXITCODE
