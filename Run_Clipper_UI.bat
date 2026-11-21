@echo off
title AI Video Clipper - Shorts Generator
cd /d "%~dp0"

echo ========================================================
echo   AI Video Clipper ^& Shorts Generator
echo   Launching Streamlit Web Dashboard...
echo ========================================================
echo.

py -3.11 -m streamlit run streamlit_app.py --server.address localhost --server.port 8501

pause
