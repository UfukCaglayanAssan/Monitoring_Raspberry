#!/bin/bash

# pigpiod başlat
sudo pigpiod
sleep 2

# Home dizinine geç
cd /home/assan/Desktop

# Ortam değişkenleri için PATH ayarla (bazı cron ortamlarında eksik olur)
export PATH="/home/assan/Desktop/myenv/bin:$PATH"

# Virtual environment'i etkinleştir
source /home/assan/Desktop/myenv/bin/activate

# PID dosyalarını temizle
rm -f /home/assan/Desktop/monitoring/Monitoring_Raspberry/main.pid
rm -f /home/assan/Desktop/monitoring/Monitoring_Raspberry/web.pid

# main.py'yi başlat ve PID'ini kaydet
PYTHONUNBUFFERED=1 python /home/assan/Desktop/monitoring/Monitoring_Raspberry/main.py >> /home/assan/Desktop/monitoring/Monitoring_Raspberry/script.log 2>&1 &
echo $! > /home/assan/Desktop/monitoring/Monitoring_Raspberry/main.pid

# web_app.py'yi başlat ve PID'ini kaydet
PYTHONUNBUFFERED=1 python /home/assan/Desktop/monitoring/Monitoring_Raspberry/web_app.py >> /home/assan/Desktop/monitoring/Monitoring_Raspberry/web.log 2>&1 &
echo $! > /home/assan/Desktop/monitoring/Monitoring_Raspberry/web.pid

echo "Sistem başlatıldı - Main PID: $(cat /home/assan/Desktop/monitoring/Monitoring_Raspberry/main.pid), Web PID: $(cat /home/assan/Desktop/monitoring/Monitoring_Raspberry/web.pid)"
