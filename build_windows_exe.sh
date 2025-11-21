#!/bin/bash
# TESCOM BMS IP Bulucu - Windows EXE Oluşturma Scripti (Linux/Mac için)
# Bu script, Python uygulamasını Windows exe dosyasına çevirir (Wine kullanarak)

echo "========================================"
echo "TESCOM BMS IP Bulucu - EXE Oluşturucu"
echo "========================================"
echo ""

# PyInstaller'ın yüklü olup olmadığını kontrol et
python3 -c "import PyInstaller" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "PyInstaller bulunamadı, yükleniyor..."
    pip3 install pyinstaller
    if [ $? -ne 0 ]; then
        echo "HATA: PyInstaller yüklenemedi!"
        exit 1
    fi
fi

echo ""
echo "EXE dosyası oluşturuluyor..."
echo ""

# PyInstaller ile exe oluştur
pyinstaller --onefile \
    --windowed \
    --name "TESCOM_BMS_IP_Bulucu" \
    --icon=NONE \
    windows_ip_finder.py

if [ $? -ne 0 ]; then
    echo ""
    echo "HATA: EXE oluşturulamadı!"
    exit 1
fi

echo ""
echo "========================================"
echo "Başarılı! EXE dosyası oluşturuldu."
echo "========================================"
echo ""
echo "EXE dosyası: dist/TESCOM_BMS_IP_Bulucu.exe"
echo ""



