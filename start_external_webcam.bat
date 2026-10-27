@echo off
title AI Pothole Detection - External Webcam Pipeline
cd /d "%~dp0"
echo ============================================================
echo   AI POTHOLE DETECTION SYSTEM - EXTERNAL WEBCAM PIPELINE
echo ============================================================
echo.
echo Connecting to External USB Webcam (Device Index 1)...
echo Model: weights/pothole_best.pt
echo.
py -m edge_detection.detector --use-webcam --camera-index 1
pause
