@echo off
chcp 65001 >nul
echo ========================================
echo   Shinsung EP Sample System 실행
echo ========================================
echo.

REM Python 설치 확인
python --version >nul 2>&1
if errorlevel 1 (
    echo [오류] Python이 설치되어 있지 않거나 PATH에 등록되어 있지 않습니다.
    echo Python을 설치한 후 다시 시도해주세요.
    pause
    exit /b 1
)

echo Python 버전 확인 중...
python --version
echo.

REM Streamlit 설치 확인 및 설치
echo 필요한 패키지 확인 중...
python -c "import streamlit" >nul 2>&1
if errorlevel 1 (
    echo Streamlit이 설치되어 있지 않습니다. 설치를 시작합니다...
    echo.
    pip install streamlit pandas openpyxl
    if errorlevel 1 (
        echo [오류] 패키지 설치에 실패했습니다.
        pause
        exit /b 1
    )
    echo.
    echo 패키지 설치가 완료되었습니다.
    echo.
) else (
    echo 필요한 패키지가 모두 설치되어 있습니다.
    echo.
)

echo Streamlit 애플리케이션을 시작합니다...
echo.

python -m streamlit run app.py

pause

