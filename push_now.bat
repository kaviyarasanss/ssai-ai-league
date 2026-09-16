@echo off
setlocal
REM ===================================================================
REM  push_now.bat  -  commit and push everything. NO API calls, so this
REM  costs nothing from the daily quota. Safe to run any time.
REM
REM  Double-click it, or run:  D:\SSAI\push_now.bat
REM ===================================================================

cd /d D:\SSAI
if errorlevel 1 goto :nofolder

echo.
echo === STEP 1 of 3 - clearing stale git locks =========================
echo.
REM A crashed or interrupted git leaves these behind, and while they
REM exist EVERY commit silently fails. This is what blocked the last run.
if not exist ".git\HEAD.lock" goto :nohead
del /f /q ".git\HEAD.lock"
echo    removed .git\HEAD.lock
:nohead
if not exist ".git\index.lock" goto :noindex
del /f /q ".git\index.lock"
echo    removed .git\index.lock
:noindex
echo    locks clear

echo.
echo === STEP 2 of 3 - committing =======================================
echo.
git add -A
git diff --cached --quiet
if not errorlevel 1 goto :nothingnew
git -c user.name=kaviyarasanss -c user.email=kaviyarasanss@users.noreply.github.com commit -F _commit_msg.txt
if errorlevel 1 goto :commitfailed
echo    committed
goto :dopush
:nothingnew
echo    nothing new to commit - carrying on to push
:dopush

echo.
echo === STEP 3 of 3 - pushing ==========================================
echo.
git -c credential.helper= push
if errorlevel 1 goto :pushfailed

echo.
echo === DONE ===========================================================
echo.
echo Local history:
git --no-pager log --oneline -4
echo.
echo On GitHub now:
git --no-pager ls-remote --heads origin
echo.
echo Both should show the same newest commit. Paste this window into the
echo chat and it can be confirmed for you.
goto :end

:nofolder
echo ERROR: could not enter D:\SSAI
goto :end

:commitfailed
echo.
echo The commit FAILED. Nothing was pushed.
echo Copy everything above and paste it into the chat.
goto :end

:pushfailed
echo.
echo The push FAILED - but your commits are safe locally, nothing is lost.
echo GitHub stopped accepting account passwords in 2021. At the prompt use:
echo     username: kaviyarasanss
echo     password: a Personal Access Token from
echo               https://github.com/settings/tokens
echo               (tick the "repo" checkbox when creating it)
echo Then just run this file again.
goto :end

:end
endlocal
pause
