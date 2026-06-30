@echo off
cd /d "C:\Users\Arshia4\Vande Matrabhoomi News Portal"
echo. >> update_log.txt
echo ============================================================ >> update_log.txt
echo [%date% %time%] Starting Prasar Bharati fetch... >> update_log.txt

:: Try 'py' launcher first (Windows Python Launcher — most reliable in scheduled tasks)
py -3 fetch_news.py >> update_log.txt 2>&1
if %errorlevel% equ 0 goto done

:: Fall back to 'python' if 'py' not found
python fetch_news.py >> update_log.txt 2>&1
if %errorlevel% equ 0 goto done

:: Last resort — try common install paths
"C:\Python312\python.exe" fetch_news.py >> update_log.txt 2>&1
if %errorlevel% equ 0 goto done
"C:\Python311\python.exe" fetch_news.py >> update_log.txt 2>&1
if %errorlevel% equ 0 goto done
"%LOCALAPPDATA%\Programs\Python\Python312\python.exe" fetch_news.py >> update_log.txt 2>&1
if %errorlevel% equ 0 goto done
"%LOCALAPPDATA%\Programs\Python\Python311\python.exe" fetch_news.py >> update_log.txt 2>&1

:done
echo [%date% %time%] Fetch complete. >> update_log.txt

:: Push updated news-data.js to GitHub so the live site refreshes
echo [%date% %time%] Pushing to GitHub... >> update_log.txt
git add news-data.js >> update_log.txt 2>&1
git commit -m "news update %date% %time%" >> update_log.txt 2>&1
git push >> update_log.txt 2>&1
echo [%date% %time%] Push complete. >> update_log.txt
