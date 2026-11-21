@echo off
title Hugging Face Spaces 1-Click Update
cd /d "%~dp0"

echo ================================================================
echo   🚀 AI Video Clipper - Hugging Face Spaces Auto-Updater
echo ================================================================
echo.
echo Syncing latest code and pushing to Hugging Face (ai-shorts)...
echo.

git add .
git commit -m "Update from local PC" 2>nul
git push space main

echo.
echo ================================================================
echo  🎉 All updates pushed to Hugging Face successfully!
echo  Your live Space will update in 1-2 minutes:
echo  https://huggingface.co/spaces/fuyad212002/ai-shorts
echo ================================================================
echo.
pause
