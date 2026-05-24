@echo off
setlocal enabledelayedexpansion

REM ============================================================
REM Filenames - assumed to live in the same folder as this .bat.
REM Edit only if you rename them.
REM ============================================================
set "BLEND_FILE=%~dp0phones.blend"
set "SCRIPT_FILE=%~dp0render_screens.py"
REM ============================================================

REM 1. Manual override via env var: set BLENDER_EXE=C:\path\to\blender.exe
if defined BLENDER_EXE (
    if exist "!BLENDER_EXE!" goto :found
)

REM 2. Check PATH.
for /f "delims=" %%I in ('where blender 2^>nul') do (
    set "BLENDER_EXE=%%I"
    goto :found
)

REM 3. Check common install locations.
call :find_versioned "%ProgramFiles%\Blender Foundation"
if defined BLENDER_EXE goto :found
call :find_versioned "%ProgramFiles(x86)%\Blender Foundation"
if defined BLENDER_EXE goto :found
call :find_versioned "%LOCALAPPDATA%\Programs\Blender Foundation"
if defined BLENDER_EXE goto :found
call :find_direct "%ProgramFiles(x86)%\Steam\steamapps\common\Blender"
if defined BLENDER_EXE goto :found
call :find_direct "%ProgramFiles%\Steam\steamapps\common\Blender"
if defined BLENDER_EXE goto :found
call :find_direct "%LOCALAPPDATA%\Microsoft\WinGet\Packages\BlenderFoundation.Blender_Microsoft.Winget.Source_8wekyb3d8bbwe"
if defined BLENDER_EXE goto :found

REM 4. Try the registry.
for /f "tokens=2*" %%A in ('reg query "HKLM\Software\BlenderFoundation" /v "Install_Dir" 2^>nul ^| findstr /i Install_Dir') do (
    if exist "%%B\blender.exe" (
        set "BLENDER_EXE=%%B\blender.exe"
        goto :found
    )
)

echo.
echo ERROR: Could not find blender.exe automatically.
echo.
echo Tried:
echo   - BLENDER_EXE environment variable
echo   - PATH (where blender)
echo   - Program Files\Blender Foundation (and x86)
echo   - LocalAppData Programs\Blender Foundation
echo   - Steam (default library)
echo   - Winget package location
echo   - HKLM\Software\BlenderFoundation registry key
echo.
echo Fix by one of:
echo   1. set BLENDER_EXE=C:\path\to\blender.exe   (then re-run)
echo   2. Add the folder containing blender.exe to your PATH.
echo   3. Edit this .bat and hardcode BLENDER_EXE at the top.
echo.
pause
exit /b 1

:find_versioned
REM Look for Blender X.Y subfolders inside %~1, pick the newest.
if not exist "%~1" exit /b 0
for /f "delims=" %%V in ('dir /b /ad /o-n "%~1\Blender*" 2^>nul') do (
    if exist "%~1\%%V\blender.exe" (
        set "BLENDER_EXE=%~1\%%V\blender.exe"
        exit /b 0
    )
)
exit /b 0

:find_direct
REM blender.exe sits directly inside %~1 (Steam, portable installs).
if exist "%~1\blender.exe" set "BLENDER_EXE=%~1\blender.exe"
exit /b 0

:found
echo Blender:    !BLENDER_EXE!
echo Blend file: !BLEND_FILE!
echo Script:     !SCRIPT_FILE!
echo.

if not exist "!BLEND_FILE!" (
    echo ERROR: .blend file not found at !BLEND_FILE!
    echo Place it in the same folder as this .bat, or edit BLEND_FILE at the top.
    pause
    exit /b 1
)
if not exist "!SCRIPT_FILE!" (
    echo ERROR: Python script not found at !SCRIPT_FILE!
    echo Place it in the same folder as this .bat, or edit SCRIPT_FILE at the top.
    pause
    exit /b 1
)

"!BLENDER_EXE!" --background "!BLEND_FILE!" --python "!SCRIPT_FILE!"
set "EXITCODE=!ERRORLEVEL!"

echo.
if !EXITCODE! NEQ 0 (
    echo === Render failed with exit code !EXITCODE! ===
) else (
    echo === Done ===
)
pause
exit /b !EXITCODE!