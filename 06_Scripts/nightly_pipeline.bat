@echo off
REM nightly_pipeline.bat — Finance Data Lake Nightly ETL
REM =====================================================
REM รันทุกเช้า 07:00 ผ่าน Windows Task Scheduler
REM เป็น backup ของ watch_bronze.py
REM
REM Setup (ทำครั้งเดียว):
REM   1. เปิด Task Scheduler → Create Basic Task
REM   2. Name: "Finance Data Lake - Nightly Pipeline"
REM   3. Trigger: Daily, 07:00
REM   4. Action: Start a program
REM      Program: D:\_Work_Workspace\03_Data_Projects\_Finance_Data_Lake\06_Scripts\nightly_pipeline.bat
REM   5. Finish

setlocal EnableDelayedExpansion

set LAKE_ROOT=D:\_Work_Workspace\03_Data_Projects\_Finance_Data_Lake
set LOG_DIR=%LAKE_ROOT%\logs
set LOG_FILE=%LOG_DIR%\pipeline_%date:~10,4%%date:~4,2%%date:~7,2%.log
set PYTHON=python

REM สร้าง logs folder ถ้ายังไม่มี
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

echo ============================================================ >> "%LOG_FILE%"
echo [%date% %time%] Nightly pipeline เริ่มทำงาน >> "%LOG_FILE%"
echo ============================================================ >> "%LOG_FILE%"

cd /d "%LAKE_ROOT%"

REM รัน full pipeline: Silver + Gold + DuckDB
echo [%time%] รัน run_pipeline.py --all ... >> "%LOG_FILE%"
%PYTHON% run_pipeline.py --all >> "%LOG_FILE%" 2>&1

if %ERRORLEVEL% EQU 0 (
    echo [%time%] Pipeline SUCCESS ✓ >> "%LOG_FILE%"
    echo Pipeline เสร็จสมบูรณ์ — ดู %LOG_FILE%
) else (
    echo [%time%] Pipeline FAILED ✗ (exit code %ERRORLEVEL%) >> "%LOG_FILE%"
    echo ERROR: Pipeline ล้มเหลว — ดู %LOG_FILE%
    exit /b 1
)

echo [%date% %time%] เสร็จสิ้น >> "%LOG_FILE%"
echo ============================================================ >> "%LOG_FILE%"
