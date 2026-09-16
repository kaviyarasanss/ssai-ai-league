@echo off
setlocal
REM ===================================================================
REM  finish_week7.bat  -  run the Week 7 race, then commit and push.
REM
REM  Just double-click it, or run:   D:\SSAI\finish_week7.bat
REM  It activates D:\SSAI\.venv itself.
REM
REM  Costs about 16 of the 20 daily requests on the workhorse model.
REM  Re-running is cheap: finished questions are skipped and cached
REM  calls cost nothing. Use  python week7\race.py --fresh  to redo all.
REM ===================================================================

cd /d D:\SSAI
if errorlevel 1 goto :nofolder

if exist ".venv\Scripts\activate.bat" (
    call ".venv\Scripts\activate.bat"
    echo    venv activated
) else (
    echo    no .venv found - using whatever python is on PATH
)

python -c "import google.genai, sentence_transformers, rank_bm25" 2>nul
if errorlevel 1 goto :nodeps

echo.
echo === STEP 1 of 3 - running the race =================================
echo.
python week7\race.py
if errorlevel 1 goto :racefailed

echo.
echo === STEP 2 of 3 - committing =======================================
echo.
git add -A
git -c user.name=kaviyarasanss -c user.email=kaviyarasanss@users.noreply.github.com commit -F _commit_msg.txt
if errorlevel 1 echo    (nothing new to commit - carrying on)

echo.
echo === STEP 3 of 3 - pushing ==========================================
echo.
git -c credential.helper= push
if errorlevel 1 goto :pushfailed

echo.
echo === DONE ===========================================================
git --no-pager log --oneline -3
echo.
echo Pushed. week7\race_results.json holds the raw traces and
echo week7\RESULTS.md holds the write-up. Paste the race output back
echo into the chat so Part B of RESULTS.md can be filled in.
goto :end

:nofolder
echo ERROR: could not enter D:\SSAI
goto :end

:nodeps
echo.
echo ERROR: the packages are missing in this environment. Install them with:
echo     pip install -r requirements.txt
echo Nothing was run, committed or pushed.
goto :end

:racefailed
echo.
echo The race did not finish cleanly. Nothing was committed or pushed.
echo If it stopped on quota, any finished questions are already saved in
echo week7\race_results.json - just run this again tomorrow.
goto :end

:pushfailed
echo.
echo The commit succeeded but the push did not.
echo GitHub stopped accepting account passwords in 2021, so use a
echo Personal Access Token as the password at the prompt:
echo     https://github.com/settings/tokens
echo Then retry with:  git -c credential.helper= push
goto :end

:end
endlocal
pause
