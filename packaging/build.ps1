# claude-tray - (c) 2026 Svatka Technologies(TM) (Alex Merovic). All rights reserved.
# Build completo: icone -> ClaudeTray.exe (PyInstaller) -> instalador (Inno Setup).
# Rodar da raiz do repo:  powershell -ExecutionPolicy Bypass -File packaging\build.ps1
$ErrorActionPreference = "Stop"
$raiz = Split-Path -Parent $PSScriptRoot
Set-Location $raiz

$py = Join-Path $raiz ".build-venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
    py -3 -m venv .build-venv
    & $py -m pip install -q pyinstaller pystray pillow
}

& $py packaging\make_icon.py

# --windowed: sem console, senao todo logon piscaria uma janela preta.
# --onefile: um .exe so, que e o que o instalador e o npm distribuem.
& $py -m PyInstaller --noconfirm --clean --onefile --windowed `
    --name ClaudeTray `
    --icon packaging\ClaudeTray.ico `
    --version-file packaging\version_info.txt `
    --paths src `
    --distpath dist --workpath build `
    packaging\entry.py
if ($LASTEXITCODE -ne 0) { throw "PyInstaller falhou" }

# Pacote npm: o lancador so executa o .exe cujo hash bate com este. Gravado a
# cada build, porque todo rebuild do PyInstaller muda o hash.
$versao = (Select-String -Path pyproject.toml -Pattern '^version = "(.+)"').Matches[0].Groups[1].Value
$hash = (Get-FileHash dist\ClaudeTray.exe -Algorithm SHA256).Hash.ToLower()
$release = [ordered]@{
    version = $versao
    url     = "https://github.com/alexmerovic/claude-tray/releases/download/v$versao/ClaudeTray.exe"
    sha256  = $hash
}
[IO.File]::WriteAllText((Join-Path $raiz "packaging\npm\release.json"),
    ($release | ConvertTo-Json), (New-Object Text.UTF8Encoding $false))
Copy-Item LICENSE, AGENTS.md packaging\npm\ -Force

$iscc = @(
    "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) { throw "Inno Setup 6 nao encontrado (winget install JRSoftware.InnoSetup)" }

& $iscc /Q packaging\installer.iss
if ($LASTEXITCODE -ne 0) { throw "Inno Setup falhou" }

Get-ChildItem dist\ClaudeTray.exe, dist\ClaudeTray-Setup-*.exe |
    Select-Object Name, @{n = "MB"; e = { [math]::Round($_.Length / 1MB, 1) } }
