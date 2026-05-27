@echo off
setlocal enabledelayedexpansion

REM ============================================================
REM Filenames - assumed to live in the same folder as this .bat.
REM Edit only if you rename them.
REM ============================================================
set "BLEND_FILE=%~dp0phones.blend"
set "SCRIPT_FILE=%~dp0render_screens.py"
REM ============================================================

REM ============================================================
REM Optional platform filter + flags (any order):
REM   render.bat                            -> iOS + Android (default)
REM   render.bat ios                        -> iOS only
REM   render.bat android                    -> Android only
REM   render.bat both | all                 -> explicit "render everything"
REM
REM Optional flags:
REM   -o DIR  | --output DIR | --output=DIR     override output_dir
REM   --outputs LIST | --outputs=LIST           override which outputs to write
REM       LIST is comma-separated, tokens:
REM         shadow     = png_with_shadow
REM         no_shadow  = png_no_shadow (alias: flat)
REM         svg        = svg_no_shadow
REM         all        = enable all three
REM         none       = disable all three
REM
REM Example:
REM   render.bat ios -o C:\tmp\preview --outputs shadow,svg
REM
REM Read by render_screens.py via the RENDER_PLATFORMS, RENDER_OUTPUT_DIR,
REM and RENDER_OUTPUTS env vars.
REM ============================================================
set "PLATFORM_ARG="
set "RENDER_PLATFORMS="
set "RENDER_OUTPUT_DIR="
set "RENDER_OUTPUTS="

:parse_args
if "%~1"=="" goto :args_done
set "ARG=%~1"
if /i "%ARG%"=="-h"       ( call :print_help & exit /b 0 )
if /i "%ARG%"=="--help"   ( call :print_help & exit /b 0 )
if /i "%ARG%"=="-o"       ( set "RENDER_OUTPUT_DIR=%~2" & shift & shift & goto :parse_args )
if /i "%ARG%"=="--output" ( set "RENDER_OUTPUT_DIR=%~2" & shift & shift & goto :parse_args )
if /i "%ARG%"=="--outputs" ( set "RENDER_OUTPUTS=%~2"   & shift & shift & goto :parse_args )
REM Handle --output=value / --outputs=value style.
set "_PREFIX="
if /i "%ARG:~0,9%"=="--output=" set "_PREFIX=output"
if /i "%ARG:~0,10%"=="--outputs=" set "_PREFIX=outputs"
if defined _PREFIX (
    if /i "%_PREFIX%"=="output"  set "RENDER_OUTPUT_DIR=%ARG:~9%"
    if /i "%_PREFIX%"=="outputs" set "RENDER_OUTPUTS=%ARG:~10%"
    set "_PREFIX="
    shift
    goto :parse_args
)
REM Reject other -* flags.
if "%ARG:~0,1%"=="-" (
    echo ERROR: Unknown flag "%ARG%". Run with --help for usage.
    exit /b 1
)
REM Positional platform.
if defined PLATFORM_ARG (
    echo ERROR: Unexpected extra argument "%ARG%" ^(platform already set to "%PLATFORM_ARG%"^).
    exit /b 1
)
set "PLATFORM_ARG=%ARG%"
shift
goto :parse_args
:args_done

if not defined PLATFORM_ARG goto :platform_done
if /i "%PLATFORM_ARG%"=="ios"     ( set "RENDER_PLATFORMS=iOS"     & goto :platform_done )
if /i "%PLATFORM_ARG%"=="android" ( set "RENDER_PLATFORMS=Android" & goto :platform_done )
if /i "%PLATFORM_ARG%"=="both"    goto :platform_done
if /i "%PLATFORM_ARG%"=="all"     goto :platform_done
echo ERROR: Unknown platform "%PLATFORM_ARG%". Use: ios, android, both, or no argument.
exit /b 1
:platform_done

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

:print_help
echo Usage: render.bat [ios^|android^|both] [-o DIR ^| --output DIR] [--outputs LIST]
echo.
echo Optional flags ^(any order, mix with platform^):
echo   -o DIR, --output DIR    Override output_dir ^(RENDER_OUTPUT_DIR^).
echo   --outputs LIST          Comma-separated list of outputs to enable.
echo                           Tokens: shadow, no_shadow ^(alias flat^), svg, all, none.
echo.
echo Example:
echo   render.bat ios -o C:\tmp\preview --outputs shadow,svg
exit /b 0

:found
echo Blender:    !BLENDER_EXE!
echo Blend file: !BLEND_FILE!
echo Script:     !SCRIPT_FILE!
if defined RENDER_PLATFORMS (
    echo Platforms:  !RENDER_PLATFORMS!
) else (
    echo Platforms:  iOS, Android ^(all^)
)
if defined RENDER_OUTPUT_DIR echo Output dir: !RENDER_OUTPUT_DIR!  ^(override^)
if defined RENDER_OUTPUTS    echo Outputs:    !RENDER_OUTPUTS!  ^(override^)
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