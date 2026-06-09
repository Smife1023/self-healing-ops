@echo off
cd /d g:\Desktop\btry\projectidea\projectidea\self-healing-ops
git config http.sslVerify false
git add -A
git commit -m "feat: add hand-drawn architecture diagram via GPT-image-2"
git push
echo.
echo ==================== DONE ====================
del _push_final.bat