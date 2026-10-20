@echo off
REM ===================================================================
REM  Week 11 - run everything live, in order, and stop on a real error.
REM  Run from a terminal:   cd /d D:\SSAI    then:   run_week11.bat
REM  Costs roughly 18 API requests. Free tier is 20/day/model.
REM ===================================================================
setlocal
cd /d D:\SSAI

echo.
echo ===================================================================
echo  STEP 0  virtual environment + packages
echo ===================================================================
if exist .venv\Scripts\activate.bat (
    call .venv\Scripts\activate.bat
) else (
    echo   no .venv found - using system python
)
python -m pip install -r requirements.txt
if errorlevel 1 goto fail_pip

echo.
echo ===================================================================
echo  STEP 1  preflight  (0 API requests)
echo ===================================================================
python app.py --check
if errorlevel 1 goto fail_check

echo.
echo ===================================================================
echo  STEP 2  logged run  (~10 API requests)
echo    - 5 real requests through the instrumented agent
echo    - imports week 10's measured failures as traces
echo    - writes 400 synthetic noise traces (0 API)
echo ===================================================================
python week11\run_logged.py
if errorlevel 1 goto fail_logged

echo.
echo ===================================================================
echo  STEP 3  cost: justify, calibrate, baseline, improve  (~8 requests)
echo ===================================================================
python week11\cost.py --all
if errorlevel 1 goto fail_cost

echo.
echo ===================================================================
echo  STEP 4  regression suite, replayed  (0 API requests)
echo    NOTE: a FAIL here is DATA, not a crash. Do not panic.
echo ===================================================================
python week11\regress.py

echo.
echo ===================================================================
echo  STEP 5  regenerate RESULTS.md from the logs  (0 API requests)
echo ===================================================================
python week11\report.py
if errorlevel 1 goto fail_report

echo.
echo ===================================================================
echo  STEP 6  the demo, dry run - every number filled in  (0 requests)
echo ===================================================================
python app.py --demo --dry

echo.
echo ===================================================================
echo  DONE. Copy everything above and paste it back to Claude.
echo  Nothing has been committed or pushed yet - that is the next step.
echo ===================================================================
goto end

:fail_pip
echo.
echo  *** FAILED installing packages.
echo  *** Is the virtual environment activated? Try:
echo  ***     python -m venv .venv
echo  ***     .venv\Scripts\activate.bat
goto end

:fail_check
echo.
echo  *** PREFLIGHT FAILED - read the FAIL lines above.
echo  *** Each one names the command that fixes it. Nothing was spent.
goto end

:fail_logged
echo.
echo  *** STEP 2 failed. If it says 429 / RESOURCE_EXHAUSTED your daily
echo  *** quota is gone - progress IS checkpointed, so re-run tomorrow
echo  *** and it resumes where it stopped.
goto end

:fail_cost
echo.
echo  *** STEP 3 failed. Same quota note as above. The baseline is saved
echo  *** step by step, so re-running does not repeat finished work.
goto end

:fail_report
echo.
echo  *** STEP 5 failed - could not generate RESULTS.md.
goto end

:end
echo.
pause
