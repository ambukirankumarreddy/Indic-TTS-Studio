# Stage a relocatable copy of Indic TTS Studio into installer\stage (no admin needed).
# Layout:  stage\python\   real CPython 3.12 + this app's site-packages
#          stage\app\      code + models
#          stage\run.bat   launcher
$ErrorActionPreference = "Stop"
$root  = Split-Path -Parent $PSScriptRoot
$stage = Join-Path $PSScriptRoot "stage"
$venv  = Join-Path $root ".venv"

$cfg = Get-Content (Join-Path $venv "pyvenv.cfg")
$home_ = ($cfg | Where-Object { $_ -like "home*" }) -replace "^home\s*=\s*", ""
if (-not (Test-Path (Join-Path $home_ "python.exe"))) { throw "Base Python not found: $home_" }

if (Test-Path $stage) { Write-Host "Cleaning old stage..."; Remove-Item $stage -Recurse -Force }
New-Item -ItemType Directory -Force $stage, "$stage\python", "$stage\app" | Out-Null

function Rc($src, $dst, [string[]]$extra) {
    $args_ = @($src, $dst, "/E", "/NFL", "/NDL", "/NJH", "/NJS", "/NP", "/R:2", "/W:2") + $extra
    robocopy @args_ | Out-Null
    if ($LASTEXITCODE -ge 8) { throw "robocopy failed ($LASTEXITCODE): $src" }
}

Write-Host "1/4 Base Python (tkinter included)..."
Rc $home_ "$stage\python" @("/XD", "site-packages", "__pycache__", "Doc", "include", "/XF", "*.pyc")

Write-Host "2/4 Site-packages from .venv..."
Rc (Join-Path $venv "Lib\site-packages") "$stage\python\Lib\site-packages" @("/XD", "__pycache__", "/XF", "*.pyc")

Write-Host "3/4 App code..."
Get-ChildItem $root -File | Where-Object { $_.Extension -in ".py", ".json", ".txt", ".md", ".bat" } |
    Where-Object { $_.Name -notin @("studio_prefs.json", "requirements.lock.backup.txt", "run.bat") } |
    ForEach-Object { Copy-Item $_.FullName "$stage\app\" }
Rc "$root\engines" "$stage\app\engines" @("/XD", "__pycache__")
Rc "$root\ui"      "$stage\app\ui"      @("/XD", "__pycache__")
Copy-Item "$root\run.bat" "$stage\run.bat"

Write-Host "4/4 Models..."
Rc "$root\models" "$stage\app\models" @("/XF", "*.part", "*.lock", "*.incomplete", "/XD", ".locks")
New-Item -ItemType Directory -Force "$stage\app\generated_audio" | Out-Null

$gb = [math]::Round(((Get-ChildItem $stage -Recurse -File | Measure-Object Length -Sum).Sum) / 1GB, 2)
Write-Host "Stage ready: $stage  ($gb GB)"
