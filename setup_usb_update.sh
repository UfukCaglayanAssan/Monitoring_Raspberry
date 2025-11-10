#!/bin/bash
# USB Otomatik Güncelleme Kurulum Scripti

set -e

echo "=========================================="
echo "USB Otomatik Güncelleme Kurulumu"
echo "=========================================="

# Proje dizinini bul
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$SCRIPT_DIR"

echo "Proje dizini: $PROJECT_DIR"

# usb_updater.py'yi çalıştırılabilir yap
echo "1. usb_updater.py dosyasını çalıştırılabilir yapılıyor..."
chmod +x "$PROJECT_DIR/usb_updater.py"

# Systemd service dosyasını kopyala
echo "2. Systemd service dosyası kuruluyor..."
sudo cp "$PROJECT_DIR/usb-update.service" /etc/systemd/system/usb-update.service

# Service dosyasındaki yolu güncelle
sudo sed -i "s|/home/bms/Desktop/Monitoring_Raspberry|$PROJECT_DIR|g" /etc/systemd/system/usb-update.service

# Systemd'yi yeniden yükle
echo "3. Systemd yeniden yükleniyor..."
sudo systemctl daemon-reload

# Service'i etkinleştir
echo "4. Service etkinleştiriliyor..."
sudo systemctl enable usb-update.service

# Udev rules dosyasını kopyala
echo "5. Udev rules dosyası kuruluyor..."
sudo cp "$PROJECT_DIR/99-usb-update.rules" /etc/udev/rules.d/99-usb-update.rules

# Udev kurallarını yeniden yükle
echo "6. Udev kuralları yeniden yükleniyor..."
sudo udevadm control --reload-rules
sudo udevadm trigger

# Log dosyasını oluştur (proje dizininde)
echo "7. Log dosyası oluşturuluyor..."
touch "$PROJECT_DIR/usb_updater.log"
chmod 666 "$PROJECT_DIR/usb_updater.log"

# Backup dizinini oluştur (proje dizininde)
echo "8. Backup dizini oluşturuluyor..."
mkdir -p "$PROJECT_DIR/usb_update_backups"

echo ""
echo "=========================================="
echo "Kurulum Tamamlandı!"
echo "=========================================="
echo ""
echo "Kullanım:"
echo "1. USB cihazınızı hazırlayın"
echo "2. USB'nin kök dizininde 'UPDATE' adında bir klasör oluşturun"
echo "3. Güncellemek istediğiniz dosyaları UPDATE klasörüne koyun"
echo "4. USB'yi Raspberry Pi'ye takın"
echo "5. Güncelleme otomatik olarak başlayacak"
echo ""
echo "Log dosyası: $PROJECT_DIR/usb_updater.log"
echo "Backup dosyaları: $PROJECT_DIR/usb_update_backups"
echo ""
echo "Manuel test için:"
echo "  sudo systemctl start usb-update.service"
echo ""

