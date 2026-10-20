@echo off
REM ===================================================================
REM  Re-run the regression suite after the two week-12 seam fixes.
REM
REM  FIX 1  the validator now matches a CALL - construct_event( - not the
REM         bare name, so it stops rejecting its own repair.
REM  FIX 2  AGENT_REPLY_TOKENS raises the agent's output budget for THIS
REM         run only. The gate makes prompts longer, which pushed the
REM         model into empty replies (tok_out = 0). The default in
REM         week7/agent.py is unchanged at 2000, so weeks 7, 8 and 10
REM         still reproduce exactly as measured.
REM ===================================================================
setlocal
cd /d D:\SSAI
if exist .venv\Scripts\activate.bat call .venv\Scripts\activate.bat

set AGENT_REPLY_TOKENS=6000
echo   AGENT_REPLY_TOKENS=%AGENT_REPLY_TOKENS%  (default 2000 is unchanged in the file)

echo.
echo === live regression suite  (~8-10 API requests) ===
python week11\regress.py --live

echo.
echo === regenerate RESULTS.md from the logs  (0 requests) ===
python week11\report.py

echo.
echo === demo numbers  (0 requests) ===
python app.py --demo --dry

echo.
echo Done. Paste everything above back to Claude.
pause
