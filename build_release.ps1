$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

$pythonPath = if (Test-Path -LiteralPath ".venv\Scripts\python.exe") {
    (Resolve-Path -LiteralPath ".venv\Scripts\python.exe").Path
} else {
    (Get-Command python -ErrorAction Stop).Source
}

& $pythonPath -m pip install --quiet -r requirements.txt -r requirements-build.txt
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& $pythonPath -m unittest discover -s tests
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& $pythonPath tools\validate_community_db.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& $pythonPath -m PyInstaller --noconfirm --clean --onedir --windowed `
    --name CK3LocalizationManager `
    --collect-submodules keyring.backends `
    --copy-metadata keyring `
    --add-data "ck3loc\lang;ck3loc\lang" `
    --add-data "ck3loc\community_db_config.json;ck3loc" `
    ck3loc\desktop\__main__.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$releaseDir = Join-Path $PSScriptRoot "dist\CK3LocalizationManager"
$userGuide = Get-ChildItem -LiteralPath $PSScriptRoot -File -Filter "README-*.md" |
    Select-Object -First 1
if ($null -ne $userGuide) {
    Copy-Item -LiteralPath $userGuide.FullName `
        -Destination (Join-Path $releaseDir "USER_GUIDE.md") -Force
}
$version = (& $pythonPath -c "import ck3loc; print(ck3loc.__version__)").Trim()
$archive = Join-Path $PSScriptRoot "dist\CK3LocalizationManager-$version-win64.zip"
Compress-Archive -Path (Join-Path $releaseDir "*") -DestinationPath $archive -Force
Write-Host "Release ready: $archive"
