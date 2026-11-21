@echo off
title Hugging Face Spaces 1-Click Deployer
cd /d "%~dp0"

echo ================================================================
echo   🚀 AI Video Clipper - Hugging Face Spaces Deployer
echo ================================================================
echo.
echo Please create a new Space on Hugging Face (https://huggingface.co/new-space)
echo  1. Space name: e.g. ai-video-clipper
echo  2. Select SDK: Streamlit
echo  3. License: MIT / Apache-2.0
echo  4. Space Hardware: Free (CPU basic - 2 vCPU, 16GB RAM)
echo.
echo Once created, Hugging Face will show you the Space Git URL, like:
echo   https://huggingface.co/spaces/YOUR_USERNAME/ai-video-clipper
echo.
set /p SPACE_URL="Enter your Hugging Face Space Git URL: "

if "%SPACE_URL%"=="" (
    echo [Error] No URL entered! Exiting...
    pause
    exit /b
)

echo.
echo [1/3] Configuring git remote...
git remote remove space 2>nul
git remote add space %SPACE_URL%

echo [2/3] Preparing main branch...
git branch -M main

echo [3/3] Uploading project to Hugging Face Spaces...
git push -u space main --force

echo.
echo ================================================================
echo  🎉 All files pushed to Hugging Face successfully!
echo  Hugging Face is now building your container and installing FFmpeg.
echo  Your Space will be LIVE in 2-3 minutes!
echo ================================================================
echo.
pause
