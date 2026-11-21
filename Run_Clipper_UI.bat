@echo off
title AI Video Clipper - YouTube to Shorts
cd /d "%~dp0"

echo ========================================================
echo   🎬 AI Video Clipper & Shorts Generator
echo   Auto-extracting viral shorts from YouTube videos
echo ========================================================
echo.
echo Launching Gradio Web Dashboard in your browser...
echo.

py -3.11 app.py

pause
