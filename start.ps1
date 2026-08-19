<#
.SYNOPSIS
    Скрипт для автоматической установки и запуска бэкенда AI Companion.
.DESCRIPTION
    Этот скрипт проверяет наличие Python, создает виртуальное окружение,
    устанавливает необходимые зависимости и запускает сервер FastAPI.
#>

$ErrorActionPreference = "Stop"

# Получаем текущую директорию скрипта
$BaseDir = $PSScriptRoot
$BackendDir = Join-Path -Path $BaseDir -ChildPath "backend"

$VenvDir = Join-Path -Path $BackendDir -ChildPath "venv"
$VenvPython = Join-Path -Path $VenvDir -ChildPath "Scripts\python.exe"

Write-Host "=== AI Companion Setup & Run ===" -ForegroundColor Cyan
Write-Host "1. Start Server (Fast)" -ForegroundColor Green
Write-Host "2. Full Reinstall (Delete environment and reinstall dependencies)" -ForegroundColor Yellow
Write-Host "3. Dev Mode (Auto-restart on change for Backend and Frontend)" -ForegroundColor Magenta
$Choice = Read-Host "Choose an option [1/2/3]"

try {
    if ($Choice -eq '2' -and (Test-Path -Path $VenvDir)) {
        Write-Host "Deleting old virtual environment..." -ForegroundColor Yellow
        Remove-Item -Recurse -Force $VenvDir
    }

    if (-Not (Test-Path -Path $VenvPython)) {
        # 1. Checking for Python
        Write-Host "Checking for Python..."
        try {
            $pythonVersion = python --version 2>&1
            Write-Host "Found: $pythonVersion" -ForegroundColor Green
        } catch {
            Write-Host "Error: Python not found. Please install Python 3.11+ and add it to PATH." -ForegroundColor Red
            Pause
            exit
        }

        # 2. Creating virtual environment
        Write-Host "Creating virtual environment (venv)..." -ForegroundColor Yellow
        Push-Location -Path $BackendDir
        python -m venv venv
        Pop-Location
        if ($LASTEXITCODE -ne 0) {
            Write-Host "Error creating virtual environment." -ForegroundColor Red
            Pause
            exit
        }

        # Ensure pip is installed by checking if pip.exe exists
        $VenvPip = Join-Path -Path $VenvDir -ChildPath "Scripts\pip.exe"
        if (-Not (Test-Path -Path $VenvPip)) {
            Write-Host "pip.exe not found in venv. Installing pip using ensurepip..." -ForegroundColor Yellow
            & $VenvPython -m ensurepip --upgrade
        }
    }

    # Always ensure requirements from requirements.txt are installed
    Write-Host "Updating pip..." -ForegroundColor Yellow
    & $VenvPython -m pip install --default-timeout=1000 --trusted-host pypi.org --trusted-host files.pythonhosted.org --upgrade pip -q
    Write-Host "Checking dependencies from requirements.txt..." -ForegroundColor Yellow
    $ReqFile = Join-Path -Path $BackendDir -ChildPath "requirements.txt"
    & $VenvPython -m pip install -r $ReqFile

    # 4. Compile firmware if binaries are missing or full reinstall chosen
    $FirmwareDir = Join-Path -Path $BaseDir -ChildPath "firmware"
    $BootloaderBin = Join-Path -Path $BaseDir -ChildPath "web\firmware\bootloader.bin"

    if ($Choice -ne '3' -and (-Not (Test-Path -Path $BootloaderBin) -or $Choice -eq '2')) {
        Write-Host "Compiling ESP32 firmware using PlatformIO..." -ForegroundColor Yellow
        Push-Location -Path $FirmwareDir
        & $VenvPython -m platformio run
        Pop-Location
    } elseif ($Choice -eq '3') {
        Write-Host "Skipping firmware compilation (Dev Mode)." -ForegroundColor DarkGray
    }

    # 5. Build frontend (Vite)
    $WebDir = Join-Path -Path $BaseDir -ChildPath "web"
    $WebDistDir = Join-Path -Path $WebDir -ChildPath "dist"
    
    if ($Choice -ne '3' -and (-Not (Test-Path -Path $WebDistDir) -or $Choice -eq '2')) {
        Write-Host "Building Web UI (npm install & build)..." -ForegroundColor Yellow
        Push-Location -Path $WebDir
        try {
            # Run npm install and build
            Start-Process -FilePath "npm.cmd" -ArgumentList "install" -Wait -NoNewWindow
            Start-Process -FilePath "npm.cmd" -ArgumentList "run build" -Wait -NoNewWindow
            Write-Host "Web UI built successfully!" -ForegroundColor Green
        } catch {
            Write-Host "Warning: Failed to build Web UI. Ensure Node.js is installed." -ForegroundColor Red
        }
        Pop-Location
    }

    # 6. Starting the server
    if ($Choice -eq '3') {
        Write-Host "Starting Vite frontend dev server in new window..." -ForegroundColor Magenta
        
        # Ensure npm install is run if node_modules doesn't exist
        $NodeModulesDir = Join-Path -Path $WebDir -ChildPath "node_modules"
        if (-Not (Test-Path -Path $NodeModulesDir)) {
            Write-Host "Installing frontend dependencies (npm install)..." -ForegroundColor Yellow
            Push-Location -Path $WebDir
            Start-Process -FilePath "npm.cmd" -ArgumentList "install" -Wait -NoNewWindow
            Pop-Location
        }
        
        Start-Process -FilePath "npm.cmd" -ArgumentList "run dev" -WorkingDirectory $WebDir
        
        Write-Host "Starting FastAPI backend server with auto-reload..." -ForegroundColor Cyan
        Write-Host "Web UI (Dev) will be available at: http://localhost:5173/" -ForegroundColor Green
        Write-Host "Backend API will be available at: http://localhost:8000/" -ForegroundColor Green
        Write-Host "Press Ctrl+C to stop the backend." -ForegroundColor Yellow
        
        Push-Location -Path $BackendDir
        & $VenvPython main.py
        Pop-Location
    } else {
        Write-Host "Starting FastAPI server..." -ForegroundColor Cyan
        Write-Host "Web UI will be available at: http://localhost:8000/" -ForegroundColor Green
        Write-Host "Press Ctrl+C to stop the server." -ForegroundColor Yellow

        Push-Location -Path $BackendDir
        & $VenvPython main.py
        Pop-Location
    }
} finally {
    Set-Location -Path $BaseDir
}

Pause
