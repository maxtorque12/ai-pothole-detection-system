@echo off
title AI Pothole Detection - Mobile GPS HTTPS Tunnel
echo ===================================================
echo Starting Secure HTTPS Tunnel for Mobile Phone GPS...
echo ===================================================
echo.
.\cloudflared.exe tunnel --url http://127.0.0.1:5000
pause
