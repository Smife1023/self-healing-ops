@echo off
cd /d g:\Desktop\btry\projectidea\projectidea\self-healing-ops
git config http.sslVerify false
git add -A
git commit -m "docs: add badges, kbd tags, details panels to README"
git push
echo.
echo ==================== DONE ====================
del _commit_push.bat