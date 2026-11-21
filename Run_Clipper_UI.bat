@echo off
title AI Video Clipper - YouTube to Shorts
cd /d "%~dp0"

echo ========================================================
echo   🎬 AI Video Clipper & Shorts Generator
echo   Auto-extracting viral shorts from YouTube videos
echo ========================================================
echo.
echo Launching Web Dashboard in your browser...
echo.

py -3.11 -m streamlit run app.py --server.port 8501 --server.headless false

pause
