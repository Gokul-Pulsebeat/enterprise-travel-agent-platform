# Sync the local virtual environment on Windows.
#
# requirements.txt is compiled inside a Linux container (see compile-requirements.ps1), so it omits
# Windows-only dependencies such as pywin32 (required by the MCP SDK on Windows). requirements-windows.txt
# supplies them. Syncing both files together stops pip-sync from uninstalling them.
#
# Usage (virtual environment active):  .\scripts\sync-dev.ps1

# Run from the repository root regardless of where the script is invoked from.
Set-Location (Split-Path -Parent $PSScriptRoot)

if (-not (Get-Command pip-sync -ErrorAction SilentlyContinue)) {
    Write-Error "pip-sync not found. Activate the virtual environment and run: pip install pip-tools"
    exit 1
}

pip-sync requirements.txt requirements-windows.txt
exit $LASTEXITCODE
