#!/bin/bash

# pigpiod başlat
sudo pigpiod

sleep 10

# Home dizinine geç
cd /home/assan/Desktop

# Ortam değişkenleri için PATH ayarla (bazı cron ortamlarında eksik olur)
export PATH="/home/assan/Desktop/venv/bin:$PATH"

# Virtual environment'i etkinleştir
source /home/assan/Desktop/venv/bin/activate

# Virtual environment'teki Python'un tam yolu
VENV_PYTHON="/home/assan/Desktop/venv/bin/python"

# Python scriptini çalıştır ve logla
PYTHONUNBUFFERED=1 python /home/assan/Desktop/Monitoring_Raspberry/main.py >> /home/assan/Desktop/Monitoring_Raspberry/script.log 2>&1 &

# web_app.py için venv içindeki Python'u kullan (bcrypt için gerekli)
# sudo ile çalıştırırken venv Python'unu kullan
PYTHONUNBUFFERED=1 sudo $VENV_PYTHON /home/assan/Desktop/Monitoring_Raspberry/web_app.py >> /home/assan/Desktop/Monitoring_Raspberry/web.log 2>&1 &

# IP Broadcast servisini başlat (Windows IP bulucu için)
PYTHONUNBUFFERED=1 python /home/assan/Desktop/Monitoring_Raspberry/ip_broadcast_service.py >> /home/assan/Desktop/Monitoring_Raspberry/broadcast.log 2>&1 &

