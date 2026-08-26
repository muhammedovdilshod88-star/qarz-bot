@echo off
title Serverni Yangilash (Render / GitHub)
color 0A
echo ========================================================
echo   QARZ DAFTARI BOTI — SERVERGA YANGILANISH YUBORISH
echo ========================================================
echo.
echo 1. O'zgarishlar saqlanmoqda...
git add .
git commit -m "Auto update from system"

echo.
echo 2. Serverga yuborilmoqda (GitHub Push)...
git push origin main

echo.
echo ========================================================
echo   Muvaffaqiyatli yuborildi! Render avtomatik yangilanadi.
echo ========================================================
echo.
pause
