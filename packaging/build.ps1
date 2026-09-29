<#
.SYNOPSIS
    Собирает Патрика в приложение Windows: панель, exe в трее и установщик.

.DESCRIPTION
    Порядок шагов:
      1. панель (npm run build) — Vite заодно копирует web/public в web/dist,
         так что свежие образы прошивки попадают в сборку сами;
      2. иконка .ico из того же кода, что рисует значок в трее;
      3. PyInstaller (onedir) — packaging/dist/AtomPet;
      4. zip с этой папкой — работает и без установщика;
      5. установщик Inno Setup, если в системе есть ISCC.

.PARAMETER SkipWeb
    Не пересобирать панель (нужна уже собранная web/dist).

.PARAMETER SkipInstaller
    Остановиться на zip, установщик не собирать.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File packaging\build.ps1
#>

[CmdletBinding()]
param(
    [switch]$SkipWeb,
    [switch]$SkipInstaller
)

$ErrorActionPreference = "Stop"

$PackagingDir = $PSScriptRoot
$Root         = Split-Path -Parent $PackagingDir
$BackendDir   = Join-Path $Root "backend"
$WebDir       = Join-Path $Root "web"
$Python       = Join-Path $BackendDir "venv\Scripts\python.exe"
$DistDir      = Join-Path $PackagingDir "dist"
$OutDir       = Join-Path $PackagingDir "out"

function Write-Step($text) { Write-Host "`n=== $text ===" -ForegroundColor Cyan }
function Write-Ok($text)   { Write-Host "  $text" -ForegroundColor Green }
function Write-Warn($text) { Write-Host "  $text" -ForegroundColor Yellow }

$Version = (Get-Content (Join-Path $PackagingDir "VERSION") -Raw).Trim()
Write-Host "Atom Terminal Pet $Version" -ForegroundColor White

# ── Проверки ────────────────────────────────────────────────────────────────
Write-Step "Проверка окружения"

if (-not (Test-Path $Python)) {
    throw "Не найден $Python. Создайте окружение: cd backend; python -m venv venv; venv\Scripts\pip install -r requirements.txt"
}
Write-Ok "Python: $((& $Python --version) -join '')"

& $Python -c "import PyInstaller, pystray, PIL, webview" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Warn "Ставлю зависимости сборки (pyinstaller, pystray, pillow, pywebview)…"
    & $Python -m pip install --quiet pyinstaller pystray pillow pywebview
    if ($LASTEXITCODE -ne 0) { throw "Не удалось поставить зависимости сборки" }
}
Write-Ok "PyInstaller, pystray, Pillow, pywebview на месте"

# Запущенный экземпляр держит файлы в dist и ломает пересборку.
Get-Process -Name "AtomPet" -ErrorAction SilentlyContinue | ForEach-Object {
    Write-Warn "Закрываю запущенный AtomPet.exe (PID $($_.Id))"
    Stop-Process -Id $_.Id -Force
    Start-Sleep -Milliseconds 500
}

# ── 1. Панель ───────────────────────────────────────────────────────────────
if ($SkipWeb) {
    Write-Step "Панель — пропущена (-SkipWeb)"
    if (-not (Test-Path (Join-Path $WebDir "dist\index.html"))) {
        throw "web\dist не собран, а -SkipWeb запрещает его собирать"
    }
} else {
    Write-Step "Сборка панели"
    Push-Location $WebDir
    try {
        if (-not (Test-Path (Join-Path $WebDir "node_modules"))) {
            Write-Ok "npm install…"
            & npm.cmd install
            if ($LASTEXITCODE -ne 0) { throw "npm install завершился с ошибкой" }
        }
        & npm.cmd run build
        if ($LASTEXITCODE -ne 0) { throw "npm run build завершился с ошибкой" }
    } finally { Pop-Location }
    Write-Ok "Панель собрана в web\dist"
}

# ── 2. Иконка ───────────────────────────────────────────────────────────────
Write-Step "Иконка"
& $Python (Join-Path $BackendDir "tray_icon.py") (Join-Path $PackagingDir "atompet.ico")
if ($LASTEXITCODE -ne 0) { throw "Не удалось создать иконку" }
Write-Ok "packaging\atompet.ico"

# ── 3. PyInstaller ──────────────────────────────────────────────────────────
Write-Step "Сборка приложения"
if (Test-Path $DistDir) { Remove-Item -Recurse -Force $DistDir }

Push-Location $Root
try {
    & $Python -m PyInstaller --noconfirm `
        --distpath $DistDir `
        --workpath (Join-Path $PackagingDir "build") `
        (Join-Path $PackagingDir "atompet.spec")
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller завершился с ошибкой" }
} finally { Pop-Location }

$AppExe = Join-Path $DistDir "AtomPet\AtomPet.exe"
if (-not (Test-Path $AppExe)) { throw "AtomPet.exe не появился в $DistDir" }

$SizeMb = [math]::Round((Get-ChildItem (Join-Path $DistDir "AtomPet") -Recurse |
                         Measure-Object -Property Length -Sum).Sum / 1MB, 1)
Write-Ok "packaging\dist\AtomPet ($SizeMb МБ)"

# ── 4. Архив ────────────────────────────────────────────────────────────────
Write-Step "Архив"
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
$Zip = Join-Path $OutDir "AtomTerminalPet-$Version-portable.zip"
if (Test-Path $Zip) { Remove-Item -Force $Zip }
Compress-Archive -Path (Join-Path $DistDir "AtomPet") -DestinationPath $Zip
Write-Ok (Split-Path -Leaf $Zip)

# ── 5. Установщик ───────────────────────────────────────────────────────────
if ($SkipInstaller) {
    Write-Step "Установщик — пропущен (-SkipInstaller)"
    exit 0
}

Write-Step "Установщик"
$Iscc = $null
$Candidates = @(
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
    # winget ставит Inno Setup для текущего пользователя — не в Program Files
    "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
)
foreach ($candidate in $Candidates) {
    if (Test-Path $candidate) { $Iscc = $candidate; break }
}
if (-not $Iscc) {
    $found = Get-Command iscc.exe -ErrorAction SilentlyContinue
    if ($found) { $Iscc = $found.Source }
}

if (-not $Iscc) {
    Write-Warn "Inno Setup не найден — установщик не собран."
    Write-Warn "Поставьте его и запустите сборку снова:"
    Write-Warn "    winget install -e --id JRSoftware.InnoSetup"
    Write-Warn "Портативный архив уже готов: $Zip"
    exit 0
}

Push-Location $PackagingDir
try {
    & $Iscc "/DAppVersion=$Version" "installer.iss"
    if ($LASTEXITCODE -ne 0) { throw "Inno Setup завершился с ошибкой" }
} finally { Pop-Location }

Write-Ok "out\AtomTerminalPet-$Version-setup.exe"

Write-Host "`nГотово." -ForegroundColor Green
Write-Host "  Установщик: $OutDir\AtomTerminalPet-$Version-setup.exe"
Write-Host "  Портативно: $Zip"
