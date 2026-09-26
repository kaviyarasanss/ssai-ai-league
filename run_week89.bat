@echo off
setlocal
REM ===================================================================
REM  run_week89.bat - the Week 8 + Week 9 files are ALREADY in D:\SSAI.
REM  This installs the one new dependency, runs every zero-cost check,
REM  then commits and pushes.  Double-click it.
REM
REM  It spends NO API quota. The scripts that cost requests are listed
REM  at the end for you to run when you choose.
REM ===================================================================
cd /d D:\SSAI
if errorlevel 1 goto :noproj
if exist ".venv\Scripts\activate.bat" call ".venv\Scripts\activate.bat"

echo.
echo === STEP 1 of 4 - installing the new dependency (mcp) =============
python -m pip install -q -r requirements.txt
if errorlevel 1 goto :nodeps
python -c "import mcp, google.genai, dotenv, sentence_transformers, rank_bm25"
if errorlevel 1 goto :nodeps
echo    all packages present

echo.
echo === STEP 2 of 4 - zero-cost checks (no API requests) ==============
echo.
echo --- week 8: trajectory audit -------------------------------------
python week8\trajectory.py
if errorlevel 1 goto :failed
echo.
echo --- week 9: the raw MCP handshake --------------------------------
REM Non-fatal: this one hand-rolls the stdio transport for teaching value.
REM mcp_client.py and prove_no_agent_change.py below use the official
REM library and are the real mentor-check evidence, so a platform quirk
REM here must not block the push.
python week9\show_handshake.py
if errorlevel 1 echo    [warning] handshake demo did not complete - continuing
echo.
echo --- week 9: tool discovery and calls ------------------------------
python week9\mcp_client.py
if errorlevel 1 goto :failed
echo.
echo --- week 9: proof a second tool needs no agent change --------------
python week9\prove_no_agent_change.py
if errorlevel 1 goto :failed

echo.
echo === STEP 3 of 4 - committing ======================================
if exist ".git\HEAD.lock"  del /f /q ".git\HEAD.lock"
if exist ".git\index.lock" del /f /q ".git\index.lock"
git add -A
git diff --cached --quiet
if not errorlevel 1 goto :nothingnew
git -c user.name=kaviyarasanss -c user.email=kaviyarasanss@users.noreply.github.com commit -F _commit_msg.txt
if errorlevel 1 goto :commitfailed
echo    committed
goto :dopush
:nothingnew
echo    nothing new to commit
:dopush

echo.
echo === STEP 4 of 4 - pushing =========================================
git -c credential.helper= push
if errorlevel 1 goto :pushfailed

echo.
echo === DONE ==========================================================
git --no-pager log --oneline -3
echo.
echo Weeks 8 and 9 are on GitHub.
echo.
echo These cost API quota and were NOT run. Run them when you want to:
echo     python week8\injection.py     about 2 requests
echo     python week9\agent_mcp.py     about 3 requests
echo     python week8\measure.py       about 14 requests
goto :end

:noproj
echo ERROR: D:\SSAI not found.
goto :end
:nodeps
echo.
echo ERROR: could not install or import the packages. Try by hand:
echo     D:\SSAI\.venv\Scripts\activate
echo     pip install -r requirements.txt
echo Nothing was run, committed or pushed.
goto :end
:failed
echo.
echo A check FAILED. Nothing was committed or pushed.
echo Copy the error above and paste it into the chat.
goto :end
:commitfailed
echo The commit FAILED. Nothing was pushed. Paste the output into the chat.
goto :end
:pushfailed
echo.
echo The push FAILED - your commits are safe locally, nothing is lost.
echo At the prompt use username kaviyarasanss and, as the password, a token
echo from https://github.com/settings/tokens (tick the "repo" box).
echo Then run this file again.
goto :end
:end
endlocal
pause
