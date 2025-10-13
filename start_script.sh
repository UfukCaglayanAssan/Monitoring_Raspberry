#!/bin/bash

# pigpiod başlat
sudo pigpiod
sleep 2

# Home dizinine geç
cd /home/bms/Desktop

# Ortam değişkenleri için PATH ayarla (bazı cron ortamlarında eksik olur)
export PATH="/home/bms/Desktop/myenv/bin:$PATH"

# Virtual environment'i etkinleştir
source /home/bms/Desktop/myenv/bin/activate

# WiFi Monitor'ü başlat (arka planda)
echo "WiFi Monitor başlatılıyor..."
PYTHONUNBUFFERED=1 python /home/bms/Desktop/wifi_monitor.py >> /home/bms/Desktop/wifi_monitor.log 2>&1 &
sleep 2

# Python scriptini çalıştır ve logla
PYTHONUNBUFFERED=1 python /home/bms/Desktop/Monitoring_Raspberry/main.py >> /home/bms/Desktop/Monitoring_Raspberry/script.log 2>&1 &

# Web uygulamasını çalıştır ve logla
PYTHONUNBUFFERED=1 python /home/bms/Desktop/Monitoring_Raspberry/web_app.py >> /home/bms/Desktop/Monitoring_Raspberry/web.log 2>&1
