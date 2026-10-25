param(
    [string]$Python = "",
    [switch]$SkipInstall,
    [string]$OutputDirectory = "dist"
)

$ErrorActionPreference = "Stop"
Push-Location -LiteralPath $PSScriptRoot
try {
    $releaseRoot = if ([IO.Path]::IsPathRooted($OutputDirectory)) {
        [IO.Path]::GetFullPath($OutputDirectory)
    } else {
        [IO.Path]::GetFullPath((Join-Path $PSScriptRoot $OutputDirectory))
    }
    if (-not $Python) {
        $candidates = @("$PSScriptRoot\.venv\Scripts\python.exe")
        $pythonRoot = Join-Path $env:LOCALAPPDATA "Programs\Python"
        if (Test-Path -LiteralPath $pythonRoot) {
            $candidates += @(Get-ChildItem -LiteralPath $pythonRoot -Directory |
                Sort-Object Name -Descending |
                ForEach-Object { Join-Path $_.FullName "python.exe" })
        }
        $onPath = Get-Command python.exe -ErrorAction SilentlyContinue
        if ($onPath -and $onPath.Source -notlike "*\WindowsApps\*") {
            $candidates += $onPath.Source
        }
        foreach ($candidate in $candidates) {
            if (Test-Path -LiteralPath $candidate) {
                $Python = $candidate
                break
            }
        }
        if (-not $Python) {
            $launcher = Get-Command py.exe -ErrorAction SilentlyContinue
            if ($launcher) {
                $located = & $launcher.Source -3 -c "import sys; print(sys.executable)" 2>$null
                if ($LASTEXITCODE -eq 0 -and $located) { $Python = $located.Trim() }
            }
        }
    }
    if (-not $Python) {
        throw "Python 3.10+ not found. Install Python or pass -Python with its full path."
    }
    & $Python -c "import sys, tkinter; assert sys.version_info >= (3, 10), 'Python 3.10+ is required'"
    if ($LASTEXITCODE -ne 0) { throw "Python/Tkinter check failed." }

    if (-not $SkipInstall) {
        $venvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
        if (-not (Test-Path -LiteralPath $venvPython)) {
            & $Python -m venv .venv
            if ($LASTEXITCODE -ne 0) { throw "Could not create .venv." }
        }
        $Python = $venvPython
        & $Python -m pip install --disable-pip-version-check -r requirements-build.txt
        if ($LASTEXITCODE -ne 0) { throw "Dependency installation failed." }
    }

    & $Python -m unittest discover -s tests -v
    if ($LASTEXITCODE -ne 0) { throw "Tests failed; build stopped." }
    & $Python main.py --smoke-test
    if ($LASTEXITCODE -ne 0) { throw "Tkinter startup test failed." }
    & $Python -m PyInstaller --noconfirm --clean --distpath $releaseRoot VRLab2GIF.spec
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed." }

    $executable = Join-Path $releaseRoot "VRLab2GIF.exe"
    $smoke = Start-Process -FilePath $executable -ArgumentList "--smoke-test" -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -Wait -PassThru
    if ($smoke.ExitCode -ne 0) { throw "Packaged startup test failed with exit code $($smoke.ExitCode)." }
    Copy-Item -LiteralPath "README.md" -Destination (Join-Path $releaseRoot "README.md") -Force
    Copy-Item -LiteralPath "QUICKSTART.txt" -Destination (Join-Path $releaseRoot "QUICKSTART.txt") -Force
    $releaseDocs = Join-Path $releaseRoot "docs"
    New-Item -ItemType Directory -Path $releaseDocs -Force | Out-Null
    Copy-Item -LiteralPath "docs\apple-design.png" -Destination (Join-Path $releaseDocs "apple-design.png") -Force
    Copy-Item -LiteralPath "docs\dark-mode.png", "docs\light-mode.png" -Destination $releaseDocs -Force
    Copy-Item -LiteralPath "docs\angle-filters.png", "docs\runtime-logs.png" -Destination $releaseDocs -Force
    Copy-Item -LiteralPath "docs\fonts.md" -Destination $releaseDocs -Force
    Copy-Item -LiteralPath "docs\observer-angles.md" -Destination $releaseDocs -Force
    Copy-Item -LiteralPath "docs\theme-transition.md" -Destination $releaseDocs -Force
    Copy-Item -LiteralPath "docs\ppt-export.md", "docs\ppt-export-dark.png", "docs\ppt-export-light.png" -Destination $releaseDocs -Force
    $releaseNotices = Join-Path $releaseDocs "third-party"
    New-Item -ItemType Directory -Path $releaseNotices -Force | Out-Null
    Copy-Item -LiteralPath "docs\third-party\tkinterdnd2-LICENSE.txt", "docs\third-party\TkDnD-LICENSE.txt" -Destination $releaseNotices -Force
    $releaseAssets = Join-Path $releaseRoot "assets"
    New-Item -ItemType Directory -Path $releaseAssets -Force | Out-Null
    Copy-Item -LiteralPath "assets\vrlab2gif-logo.png", "assets\vrlab2gif.ico", "assets\LOGO.md" -Destination $releaseAssets -Force
    $releaseFiles = @($executable, (Join-Path $releaseRoot "README.md"), (Join-Path $releaseRoot "QUICKSTART.txt"), $releaseDocs, $releaseAssets)
    Compress-Archive -LiteralPath $releaseFiles -DestinationPath (Join-Path $releaseRoot "VRLab2GIF-Windows-x64.zip") -Force
    Write-Host "Build complete: $executable"
}
finally {
    Pop-Location
}
