<#
.SYNOPSIS
    Выпускает новую версию Патрика: версия → сборка → релиз на GitHub.

.DESCRIPTION
    Замыкает цикл обновления: установленная у пользователя программа раз в сутки
    смотрит на последний релиз репозитория, поэтому «обновить» — значит выпустить
    релиз с приложенным setup.exe.

    Шаги:
      1. записывает версию в packaging/VERSION (единственный источник правды);
      2. собирает приложение и установщик через build.ps1;
      3. считает sha256 — установщик проверяет её после загрузки;
      4. создаёт черновик релиза с тегом vX.Y.Z и файлами setup.exe и zip.

    Черновик, а не публикация: содержимое релиза стоит просмотреть глазами,
    а публикуется он одной кнопкой на GitHub (или ключом -Publish).

.PARAMETER Version
    Новая версия, например 1.1.0.

.PARAMETER Publish
    Опубликовать релиз сразу, не оставляя черновиком.

.PARAMETER SkipBuild
    Использовать уже собранные файлы в packaging/out.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File packaging\release.ps1 -Version 1.1.0
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Version,
    [switch]$Publish,
    [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"

$PackagingDir = $PSScriptRoot
$Root         = Split-Path -Parent $PackagingDir
$OutDir       = Join-Path $PackagingDir "out"

function Write-Step($text) { Write-Host "`n=== $text ===" -ForegroundColor Cyan }
function Write-Ok($text)   { Write-Host "  $text" -ForegroundColor Green }

if ($Version -notmatch '^\d+\.\d+\.\d+$') {
    throw "Версия должна быть вида 1.2.3, получено: $Version"
}

if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
    throw "Не найден gh (GitHub CLI). Поставьте: winget install -e --id GitHub.cli"
}

# ── 1. Версия ───────────────────────────────────────────────────────────────
Write-Step "Версия $Version"
$VersionFile = Join-Path $PackagingDir "VERSION"
$Previous = (Get-Content $VersionFile -Raw).Trim()
Set-Content -Path $VersionFile -Value $Version -NoNewline -Encoding utf8
Write-Ok "packaging\VERSION: $Previous → $Version"

# ── 2. Сборка ───────────────────────────────────────────────────────────────
if ($SkipBuild) {
    Write-Step "Сборка пропущена (-SkipBuild)"
} else {
    Write-Step "Сборка"
    & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PackagingDir "build.ps1")
    if ($LASTEXITCODE -ne 0) { throw "Сборка завершилась с ошибкой" }
}

$Setup = Join-Path $OutDir "AtomTerminalPet-$Version-setup.exe"
$Zip   = Join-Path $OutDir "AtomTerminalPet-$Version-portable.zip"
if (-not (Test-Path $Setup)) { throw "Не найден установщик: $Setup" }

# ── 3. Контрольная сумма ────────────────────────────────────────────────────
Write-Step "Контрольная сумма"
$Hash = (Get-FileHash -Algorithm SHA256 $Setup).Hash.ToLower()
$SizeMb = [math]::Round((Get-Item $Setup).Length / 1MB, 1)
Write-Ok "sha256: $Hash"

# ── 4. Релиз ────────────────────────────────────────────────────────────────
Write-Step "Релиз на GitHub"
$Tag = "v$Version"

$Notes = @"
Обновление до $Version.

Установите поверх предыдущей версии — настройки, заметки и память питомца
останутся на месте (они лежат в %LOCALAPPDATA%\AtomTerminalPet).

| Файл | Размер | SHA-256 |
|---|---|---|
| ``AtomTerminalPet-$Version-setup.exe`` | $SizeMb МБ | ``$Hash`` |
"@

$NotesFile = Join-Path $env:TEMP "atompet-release-notes.md"
Set-Content -Path $NotesFile -Value $Notes -Encoding utf8

$Files = @($Setup)
if (Test-Path $Zip) { $Files += $Zip }

$Arguments = @("release", "create", $Tag) + $Files + @(
    "--title", "Патрик $Version",
    "--notes-file", $NotesFile
)
if (-not $Publish) { $Arguments += "--draft" }

& gh @Arguments
if ($LASTEXITCODE -ne 0) { throw "gh release create завершился с ошибкой" }

Write-Host "`nГотово." -ForegroundColor Green
if ($Publish) {
    Write-Host "  Релиз $Tag опубликован — установленные копии увидят обновление в течение суток."
} else {
    Write-Host "  Черновик релиза $Tag создан. Проверьте его и нажмите Publish release."
}
Write-Host "  Не забудьте закоммитить packaging\VERSION."
