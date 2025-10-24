#!/bin/bash
# FTP Backup Cron Job Setup Script

echo "🔧 FTP Yedekleme Cron Job'u kuruluyor..."

# Script'e çalıştırma izni ver
chmod +x /home/bms/Desktop/Monitoring_Raspberry/ftp_backup.py

# Mevcut crontab'ı al
crontab -l > /tmp/current_cron 2>/dev/null || touch /tmp/current_cron

# FTP backup satırını kontrol et
if grep -q "ftp_backup.py" /tmp/current_cron; then
    echo "⚠️ FTP backup cron job'u zaten mevcut!"
    echo "📋 Mevcut cron job'ları:"
    grep "ftp_backup.py" /tmp/current_cron
else
    # Her gün saat 11:00'da çalışacak cron job ekle (Türkiye saati)
    echo "0 11 * * * /usr/bin/python3 /home/bms/Desktop/Monitoring_Raspberry/ftp_backup.py >> /home/bms/Desktop/Monitoring_Raspberry/ftp_backup.log 2>&1" >> /tmp/current_cron
    
    # Yeni crontab'ı yükle
    crontab /tmp/current_cron
    
    echo "✅ FTP backup cron job'u eklendi!"
    echo "⏰ Her gün saat 11:00'da çalışacak (Türkiye saati)"
    echo "📝 Loglar: /home/bms/Desktop/Monitoring_Raspberry/ftp_backup.log"
fi

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
echo "   - FTP backup'ı manuel test etmek için: python3 /home/bms/Desktop/Monitoring_Raspberry/ftp_backup.py"

