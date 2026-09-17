# TaskTimer install script (Windows PowerShell)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

Write-Host "==> TaskTimer setup in $Root" -ForegroundColor Cyan

function Find-Python {
  $candidates = @(
    @{ Cmd = "py"; Args = @("-3") },
    @{ Cmd = "python"; Args = @() },
    @{ Cmd = "C:\Users\Admin\python\python.exe"; Args = @() },
    @{ Cmd = "C:\Python311\python.exe"; Args = @() },
    @{ Cmd = "C:\Python312\python.exe"; Args = @() }
  )
  foreach ($c in $candidates) {
    try {
      if ($c.Cmd -like "*\*") {
        if (Test-Path $c.Cmd) { return @{ Exe = $c.Cmd; Prefix = @() } }
      } else {
        $ver = & $c.Cmd @($c.Args + "--version") 2>$null
        if ($LASTEXITCODE -eq 0 -or $ver) {
          return @{ Exe = $c.Cmd; Prefix = $c.Args }
        }
      }
    } catch {}
  }
  return $null
}

$py = Find-Python
if (-not $py) {
  Write-Host "Python 3.11+ not found. Install from https://www.python.org/downloads/ and re-run." -ForegroundColor Red
  exit 1
}

Write-Host "Using: $($py.Exe) $($py.Prefix -join ' ')" -ForegroundColor Green

if (-not (Test-Path ".venv")) {
  & $py.Exe @($py.Prefix + @("-m", "venv", ".venv"))
}

$pip = Join-Path $Root ".venv\Scripts\pip.exe"
$python = Join-Path $Root ".venv\Scripts\python.exe"
$flet = Join-Path $Root ".venv\Scripts\flet.exe"

& $python -m pip install -U pip
& $pip install -r requirements.txt

Write-Host ""
Write-Host "Done. Run:" -ForegroundColor Green
Write-Host "  .\.venv\Scripts\Activate.ps1"
Write-Host "  flet run app/main.py"
Write-Host "or:"
Write-Host "  .\.venv\Scripts\python.exe app\main.py"
