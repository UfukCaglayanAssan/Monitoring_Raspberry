@echo off
REM TESCOM BMS IP Bulucu - Windows EXE Oluşturma Scripti
REM Bu script, Python uygulamasını Windows exe dosyasına çevirir

echo ========================================
echo TESCOM BMS IP Bulucu - EXE Oluşturucu
echo ========================================
echo.

REM PyInstaller'ın yüklü olup olmadığını kontrol et
python -c "import PyInstaller" 2>nul
if errorlevel 1 (
    echo PyInstaller bulunamadı, yükleniyor...
    pip install pyinstaller
    if errorlevel 1 (
        echo HATA: PyInstaller yüklenemedi!
        pause
        exit /b 1
    )
)

echo.
echo EXE dosyası oluşturuluyor...
echo.

REM PyInstaller ile exe oluştur
pyinstaller --onefile ^
    --windowed ^
    --name "TESCOM_BMS_IP_Bulucu" ^
    --icon=NONE ^
    --add-data "windows_ip_finder.py;." ^
    windows_ip_finder.py

if errorlevel 1 (
    echo.
    echo HATA: EXE oluşturulamadı!
    pause
    exit /b 1
)

echo.
echo ========================================
echo Basarili! EXE dosyasi olusturuldu.
echo ========================================
echo.
echo EXE dosyasi: dist\TESCOM_BMS_IP_Bulucu.exe
echo.
pause



