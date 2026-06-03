@echo off
REM ============================================================================
REM  YouTube News Automation – Windows Task Scheduler Setup
REM  ======================================================
REM
REM  This batch file creates 6 Windows Scheduled Tasks, one for each daily
REM  video slot. Each task triggers ~2.5 hours BEFORE the scheduled publish
REM  time to allow for scraping, AI generation, video assembly, and upload.
REM
REM  SLOT SCHEDULE:
REM  ┌──────┬──────────────┬──────────────┬──────────────────────────────────┐
REM  │ Slot │ Publish Time │ Trigger Time │ Notes                            │
REM  ├──────┼──────────────┼──────────────┼──────────────────────────────────┤
REM  │  1   │  8:00 AM     │  5:30 AM     │ Morning news                     │
REM  │  2   │ 11:00 AM     │  8:30 AM     │ Mid-morning update               │
REM  │  3   │  1:30 PM     │ 11:00 AM     │ Afternoon news                   │
REM  │  4   │  5:00 PM     │  2:30 PM     │ Evening news                     │
REM  │  5   │  8:00 PM     │  5:30 PM     │ Prime-time news                  │
REM  │  6   │ 10:30 PM     │  8:00 PM     │ Night news                       │
REM  └──────┴──────────────┴──────────────┴──────────────────────────────────┘
REM
REM  USAGE:
REM    1. Right-click this file → "Run as Administrator"
REM    2. Verify tasks in Task Scheduler (taskschd.msc)
REM
REM  IMPORTANT:
REM    - Update PYTHON_PATH and PROJECT_PATH below to match your system
REM    - Must run as Administrator to create scheduled tasks
REM    - Tasks run DAILY and repeat every day
REM
REM ============================================================================

echo.
echo ============================================================
echo   YouTube News Automation - Scheduler Setup
echo ============================================================
echo.

REM ---------------------------------------------------------------------------
REM  CONFIGURATION – UPDATE THESE PATHS FOR YOUR SYSTEM
REM ---------------------------------------------------------------------------

SET PYTHON_PATH=C:\Users\mahesh\AppData\Local\Programs\Python\Python314\python.exe
SET PROJECT_PATH=C:\Users\mahesh\OneDrive\Desktop\ULESH\SCREEN SHOT\ai edtech\youtube-automation
SET MAIN_SCRIPT=%PROJECT_PATH%\main.py

REM Verify paths exist
if not exist "%PYTHON_PATH%" (
    echo [ERROR] Python not found at: %PYTHON_PATH%
    echo         Please update PYTHON_PATH in this script.
    echo         Find your Python path by running: where python
    pause
    exit /b 1
)

if not exist "%MAIN_SCRIPT%" (
    echo [ERROR] main.py not found at: %MAIN_SCRIPT%
    echo         Please update PROJECT_PATH in this script.
    pause
    exit /b 1
)

echo Using Python : %PYTHON_PATH%
echo Project path : %PROJECT_PATH%
echo.

REM ---------------------------------------------------------------------------
REM  SLOT 1: Morning News
REM  Publish at 8:00 AM → Trigger at 5:30 AM (2.5 hours processing buffer)
REM ---------------------------------------------------------------------------
echo [1/6] Creating Slot 1 - Morning News (trigger: 5:30 AM, publish: 8:00 AM)...
schtasks /Create /F /TN "YouTubeNews_Slot1" ^
    /TR "\"%PYTHON_PATH%\" \"%MAIN_SCRIPT%\" --slot 1" ^
    /SC DAILY ^
    /ST 05:30 ^
    /RL HIGHEST
if %errorlevel% equ 0 (echo    [OK] Slot 1 created successfully) else (echo    [FAIL] Could not create Slot 1)

REM ---------------------------------------------------------------------------
REM  SLOT 2: Mid-Morning Update
REM  Publish at 11:00 AM → Trigger at 8:30 AM
REM ---------------------------------------------------------------------------
echo [2/6] Creating Slot 2 - Mid-Morning Update (trigger: 8:30 AM, publish: 11:00 AM)...
schtasks /Create /F /TN "YouTubeNews_Slot2" ^
    /TR "\"%PYTHON_PATH%\" \"%MAIN_SCRIPT%\" --slot 2" ^
    /SC DAILY ^
    /ST 08:30 ^
    /RL HIGHEST
if %errorlevel% equ 0 (echo    [OK] Slot 2 created successfully) else (echo    [FAIL] Could not create Slot 2)

REM ---------------------------------------------------------------------------
REM  SLOT 3: Afternoon News
REM  Publish at 1:30 PM → Trigger at 11:00 AM
REM ---------------------------------------------------------------------------
echo [3/6] Creating Slot 3 - Afternoon News (trigger: 11:00 AM, publish: 1:30 PM)...
schtasks /Create /F /TN "YouTubeNews_Slot3" ^
    /TR "\"%PYTHON_PATH%\" \"%MAIN_SCRIPT%\" --slot 3" ^
    /SC DAILY ^
    /ST 11:00 ^
    /RL HIGHEST
if %errorlevel% equ 0 (echo    [OK] Slot 3 created successfully) else (echo    [FAIL] Could not create Slot 3)

REM ---------------------------------------------------------------------------
REM  SLOT 4: Evening News
REM  Publish at 5:00 PM → Trigger at 2:30 PM
REM ---------------------------------------------------------------------------
echo [4/6] Creating Slot 4 - Evening News (trigger: 2:30 PM, publish: 5:00 PM)...
schtasks /Create /F /TN "YouTubeNews_Slot4" ^
    /TR "\"%PYTHON_PATH%\" \"%MAIN_SCRIPT%\" --slot 4" ^
    /SC DAILY ^
    /ST 14:30 ^
    /RL HIGHEST
if %errorlevel% equ 0 (echo    [OK] Slot 4 created successfully) else (echo    [FAIL] Could not create Slot 4)

REM ---------------------------------------------------------------------------
REM  SLOT 5: Prime-Time News
REM  Publish at 8:00 PM → Trigger at 5:30 PM
REM ---------------------------------------------------------------------------
echo [5/6] Creating Slot 5 - Prime-Time News (trigger: 5:30 PM, publish: 8:00 PM)...
schtasks /Create /F /TN "YouTubeNews_Slot5" ^
    /TR "\"%PYTHON_PATH%\" \"%MAIN_SCRIPT%\" --slot 5" ^
    /SC DAILY ^
    /ST 17:30 ^
    /RL HIGHEST
if %errorlevel% equ 0 (echo    [OK] Slot 5 created successfully) else (echo    [FAIL] Could not create Slot 5)

REM ---------------------------------------------------------------------------
REM  SLOT 6: Night News
REM  Publish at 10:30 PM → Trigger at 8:00 PM
REM ---------------------------------------------------------------------------
echo [6/6] Creating Slot 6 - Night News (trigger: 8:00 PM, publish: 10:30 PM)...
schtasks /Create /F /TN "YouTubeNews_Slot6" ^
    /TR "\"%PYTHON_PATH%\" \"%MAIN_SCRIPT%\" --slot 6" ^
    /SC DAILY ^
    /ST 20:00 ^
    /RL HIGHEST
if %errorlevel% equ 0 (echo    [OK] Slot 6 created successfully) else (echo    [FAIL] Could not create Slot 6)

echo.
echo Configuring advanced settings (Wake to Run, Catch-up, and Battery run)...
powershell -Command "Get-ScheduledTask -TaskName 'YouTubeNews_Slot*' | ForEach-Object { $s = $_.Settings; $s.WakeToRun = $true; $s.StartWhenAvailable = $true; $s.DisallowStartIfOnBatteries = $false; $s.StopIfGoingOnBatteries = $false; Set-ScheduledTask -InputObject $_ -Settings $s }"
if %errorlevel% equ 0 (echo    [OK] Advanced settings configured successfully) else (echo    [FAIL] Could not configure advanced settings)

echo.
echo ============================================================
echo   Listing all YouTube News scheduled tasks:
echo ============================================================
echo.

schtasks /Query /TN "YouTubeNews_Slot1" /V /FO LIST 2>nul
echo.
schtasks /Query /TN "YouTubeNews_Slot2" /V /FO LIST 2>nul
echo.
schtasks /Query /TN "YouTubeNews_Slot3" /V /FO LIST 2>nul
echo.
schtasks /Query /TN "YouTubeNews_Slot4" /V /FO LIST 2>nul
echo.
schtasks /Query /TN "YouTubeNews_Slot5" /V /FO LIST 2>nul
echo.
schtasks /Query /TN "YouTubeNews_Slot6" /V /FO LIST 2>nul

echo.
echo ============================================================
echo   Setup complete! Verify in Task Scheduler (taskschd.msc)
echo ============================================================
echo.

REM ============================================================================
REM  UNINSTALL SECTION – Remove all scheduled tasks
REM  Uncomment the lines below and run this script to remove all tasks.
REM ============================================================================

REM echo.
REM echo ============================================================
REM echo   REMOVING all YouTube News scheduled tasks...
REM echo ============================================================
REM echo.
REM schtasks /Delete /TN "YouTubeNews_Slot1" /F
REM schtasks /Delete /TN "YouTubeNews_Slot2" /F
REM schtasks /Delete /TN "YouTubeNews_Slot3" /F
REM schtasks /Delete /TN "YouTubeNews_Slot4" /F
REM schtasks /Delete /TN "YouTubeNews_Slot5" /F
REM schtasks /Delete /TN "YouTubeNews_Slot6" /F
REM echo.
REM echo   All YouTube News tasks have been removed.
REM echo ============================================================

pause
