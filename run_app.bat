@echo off
cd /d "C:\Users\Admin\.gemini\antigravity\scratch\google_business_scraper"

:: Check if Streamlit is already running on port 8501
netstat -ano | findstr :8501 >nul
if %errorlevel% neq 0 (
    echo Starting Lead Extractor server...
    start /b python -m streamlit run app.py --server.port 8501 --server.headless true
    timeout /t 3 /nobreak >nul
)

:: Find Chrome path to launch in --app mode (dedicated separate window)
set "CHROME_PATH=chrome.exe"
if exist "%ProgramFiles%\Google\Chrome\Application\chrome.exe" (
    set "CHROME_PATH=%ProgramFiles%\Google\Chrome\Application\chrome.exe"
) else if exist "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe" (
    set "CHROME_PATH=%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"
) else if exist "%LocalAppData%\Google\Chrome\Application\chrome.exe" (
    set "CHROME_PATH=%LocalAppData%\Google\Chrome\Application\chrome.exe"
)

start "" "%CHROME_PATH%" --app=http://localhost:8501
exit
