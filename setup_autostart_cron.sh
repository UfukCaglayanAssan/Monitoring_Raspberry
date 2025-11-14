#!/bin/bash
# Raspberry Pi Masaüstü Otomatik Başlatma Crontab Kurulum Scripti

echo "🔧 Masaüstü Otomatik Başlatma Crontab Kurulumu..."
echo ""

# Kullanıcı adını otomatik al
USER_HOME=$(eval echo ~$USER)
SCRIPT_DIR="$USER_HOME/Desktop/Monitoring_Raspberry"

# Start script dosyasını bul
START_SCRIPT=""
if [ -f "$SCRIPT_DIR/start.sh" ]; then
    START_SCRIPT="$SCRIPT_DIR/start.sh"
elif [ -f "$SCRIPT_DIR/start.py" ]; then
    START_SCRIPT="$SCRIPT_DIR/start.py"
elif [ -f "$SCRIPT_DIR/main.py" ]; then
    START_SCRIPT="$SCRIPT_DIR/main.py"
else
    echo "⚠️ Start script dosyası bulunamadı!"
    echo "Lütfen start script dosyasının yolunu girin:"
    read -p "Script yolu: " START_SCRIPT
    if [ ! -f "$START_SCRIPT" ]; then
        echo "❌ Dosya bulunamadı: $START_SCRIPT"
        exit 1
    fi
fi

echo "📁 Start script: $START_SCRIPT"

# Script'e çalıştırma izni ver
chmod +x "$START_SCRIPT"

# Mevcut crontab'ı al
crontab -l > /tmp/current_cron 2>/dev/null || touch /tmp/current_cron

# @reboot satırını kontrol et
if grep -q "@reboot.*$(basename $START_SCRIPT)" /tmp/current_cron; then
    echo "⚠️ @reboot cron job'u zaten mevcut!"
    echo "📋 Mevcut @reboot job'ları:"
    grep "@reboot" /tmp/current_cron
    echo ""
    read -p "Yeniden eklemek ister misiniz? (e/h): " answer
    if [ "$answer" != "e" ] && [ "$answer" != "E" ]; then
        echo "İşlem iptal edildi."
        rm /tmp/current_cron
        exit 0
    fi
    # Mevcut @reboot satırını sil
    grep -v "@reboot.*$(basename $START_SCRIPT)" /tmp/current_cron > /tmp/new_cron
    mv /tmp/new_cron /tmp/current_cron
fi

# Python script ise python3 ile çalıştır
if [[ "$START_SCRIPT" == *.py ]]; then
    # Log dosyası yolu
    LOG_FILE="$SCRIPT_DIR/autostart.log"
    # @reboot cron job ekle
    echo "@reboot sleep 30 && /usr/bin/python3 $START_SCRIPT >> $LOG_FILE 2>&1" >> /tmp/current_cron
    echo "✅ @reboot cron job'u eklendi (Python script)"
    echo "📝 Loglar: $LOG_FILE"
else
    # Shell script ise direkt çalıştır
    LOG_FILE="$SCRIPT_DIR/autostart.log"
    echo "@reboot sleep 30 && $START_SCRIPT >> $LOG_FILE 2>&1" >> /tmp/current_cron
    echo "✅ @reboot cron job'u eklendi (Shell script)"
    echo "📝 Loglar: $LOG_FILE"
fi

# Yeni crontab'ı yükle
crontab /tmp/current_cron

# Geçici dosyayı sil
rm /tmp/current_cron

echo ""
echo "📋 Tüm cron job'ları:"
crontab -l

echo ""
echo "✅ Kurulum tamamlandı!"
echo ""
echo "💡 İpuçları:"
echo "   - Cron job'ları görmek için: crontab -l"
echo "   - Cron job'ları düzenlemek için: crontab -e"
echo "   - Cron job'u silmek için: crontab -e (ilgili satırı silin)"
echo "   - Sistem yeniden başlatıldığında script otomatik çalışacak"
echo "   - Log dosyasını kontrol etmek için: tail -f $LOG_FILE"




