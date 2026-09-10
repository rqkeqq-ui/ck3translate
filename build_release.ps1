$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

$pythonPath = if (Test-Path -LiteralPath ".venv\Scripts\python.exe") {
    (Resolve-Path -LiteralPath ".venv\Scripts\python.exe").Path
} else {
    (Get-Command python -ErrorAction Stop).Source
}

& $pythonPath -m pip install --quiet -r requirements.txt -r requirements-build.txt
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& $pythonPath tools\build_release.py
exit $LASTEXITCODE
