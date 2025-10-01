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

# Python scriptini çalıştır ve logla
PYTHONUNBUFFERED=1 python /home/assan/Desktop/Monitoring_Raspberry/main.py >> /home/assan/Desktop/Monitoring_Raspberry/script.log 2>&1 &

# Web uygulamasını çalıştır ve logla
PYTHONUNBUFFERED=1 python /home/assan/Desktop/Monitoring_Raspberry/web_app.py >> /home/assan/Desktop/Monitoring_Raspberry/web.log 2>&1
