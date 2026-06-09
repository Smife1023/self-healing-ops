@echo off
cd /d g:\Desktop\btry\projectidea\projectidea\self-healing-ops
del /q _fix_all.py _fix_and_push.py _push.bat _push2.bat 2>nul
git config http.sslVerify false
git add -A
git commit -m "fix: pure ASCII docs, remove emoji, verify no API keys"
git push
echo.
echo ==================== DONE ====================
del _push3.bat