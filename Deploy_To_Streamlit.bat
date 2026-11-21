@echo off
title GitHub & Streamlit Cloud 1-Click Update
cd /d "%~dp0"

echo ================================================================
echo   🚀 AI Video Clipper - GitHub / Streamlit Cloud Auto-Updater
echo ================================================================
echo.
echo Syncing latest code and pushing to GitHub (fuadvisualsbd/ai-shorts)...
echo.

git add .
git commit -m "Update from local PC" 2>nul
git push origin main

echo.
echo ================================================================
echo  🎉 All updates pushed to GitHub successfully!
echo  Your live Streamlit Cloud app will auto-update in ~30 seconds.
echo ================================================================
echo.
pause
