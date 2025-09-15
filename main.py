# -*- coding: utf-8 -*-

import time
import datetime
import threading
import queue
import math
import pigpio
import json
import os
import socket
import struct
import sys
from collections import defaultdict
from database import BatteryDatabase
from alarm_processor import alarm_processor

# SNMP imports
from pysnmp.entity import engine, config
from pysnmp.entity.rfc3413 import cmdrsp, context
from pysnmp.hlapi import *
from pysnmp.carrier.asyncio.dgram import udp
from pysnmp.proto.api import v2c

# Global variables
buffer = bytearray()
data_queue = queue.Queue()
RX_PIN = 16
TX_PIN = 26
BAUD_RATE = 9600
BIT_TIME = int(1e6 / BAUD_RATE)

# Armslavecount verilerini tutmak için
arm_slave_counts = {1: 0, 2: 0, 3: 7, 4: 0}  # Her kol için batarya sayısı (default değerler)
arm_slave_counts_lock = threading.Lock()  # Thread-safe erişim için

# RAM'de veri tutma sistemi (Modbus/SNMP için)
battery_data_ram = defaultdict(dict)  # {arm: {k: {dtype: value}}}
arm_slave_counts_ram = {1: 0, 2: 0, 3: 0, 4: 0}  # Her kol için batarya sayısı
data_lock = threading.Lock()  # Thread-safe erişim için

# Alarm verileri için RAM yapısı
alarm_ram = {}  # {arm: {battery: {alarm_type: bool}}}
alarm_lock = threading.Lock()  # Thread-safe erişim için

# Status verileri için RAM yapısı
status_ram = {}  # {arm: {battery: bool}} - True=veri var, False=veri yok
status_lock = threading.RLock()  # Thread-safe erişim için

# Trap hedefleri için RAM yapısı
trap_targets_ram = []  # [{'id': int, 'name': str, 'ip_address': str, 'port': int, 'is_active': bool}]
trap_targets_lock = threading.Lock()  # Thread-safe erişim için

# Missing data takibi için
missing_data_tracker = set()  # (arm, battery) tuple'ları
missing_data_lock = threading.Lock()  # Thread-safe erişim için

# Reset system öncesi missing data'ları tutma
missing_data_before_reset = set()  # Reset öncesi missing data'lar
missing_data_before_reset_lock = threading.Lock()  # Thread-safe erişim için

# Periyot sistemi için global değişkenler
current_period_timestamp = None
period_active = False
last_data_received = time.time()
last_k_value = None  # Son gelen verinin k değerini tutar
last_k_value_lock = threading.Lock()  # Thread-safe erişim için

# Database instance
db = BatteryDatabase()
db_lock = threading.Lock()  # Veritabanı işlemleri için lock

pi = pigpio.pi()
pi.set_mode(TX_PIN, pigpio.OUTPUT)

# Program başlangıç zamanı
program_start_time = int(time.time() * 1000)

def get_period_timestamp():
    """Aktif periyot için timestamp döndür"""
    global current_period_timestamp, period_active, last_data_received
    
    current_time = time.time()
    
    if not period_active:
        current_period_timestamp = int(current_time * 1000)
        period_active = True
        last_data_received = current_time
        # timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        # print(f"[{timestamp}] Yeni periyot başlatıldı: {current_period_timestamp}")
    
    return current_period_timestamp

def reset_period():
    """Periyotu sıfırla"""
    global period_active, current_period_timestamp
    period_active = False
    current_period_timestamp = None
    # timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    # print(f"[{timestamp}] Periyot sıfırlandı")

def update_last_k_value(new_value):
    """Thread-safe olarak last_k_value güncelle"""
    global last_k_value
    with last_k_value_lock:
        last_k_value = new_value

def get_last_k_value():
    """Thread-safe olarak last_k_value oku"""
    global last_k_value
    with last_k_value_lock:
        return last_k_value

def load_arm_slave_counts_from_db():
    """Veritabanından en son armslavecount değerlerini çek ve RAM'e yükle"""
    try:
        with db_lock:
            # Her kol için en son armslavecount değerini çek
            for arm in [1, 2, 3, 4]:
                result = db.execute_query('''
                    SELECT slave_count FROM arm_slave_counts 
                    WHERE arm = ? 
                    ORDER BY created_at DESC 
                    LIMIT 1
                ''', (arm,))
                
                rows = result.fetchall()
                if rows and len(rows) > 0:
                    slave_count = rows[0][0]
                    with arm_slave_counts_lock:
                        arm_slave_counts[arm] = slave_count
                    print(f"✓ Kol {arm} armslavecount veritabanından yüklendi: {slave_count}")
                else:
                    print(f"⚠️ Kol {arm} için armslavecount verisi bulunamadı, varsayılan: 0")
        
        print(f"✓ RAM armslavecount değerleri güncellendi: {arm_slave_counts}")
        
    except Exception as e:
        print(f"❌ Armslavecount verileri yüklenirken hata: {e}")

def is_valid_arm_data(arm_value, k_value):
    """Veri doğrulama: Sadece aktif kollar ve bataryalar işlenir"""
    with arm_slave_counts_lock:
        # Kol aktif mi kontrol et
        if arm_slave_counts[arm_value] == 0:
            print(f"⚠️ HATALI VERİ: Kol {arm_value} aktif değil (batarya sayısı: 0)")
            return False
        
        # k=2 ise kol verisi, her zaman geçerli
        if k_value == 2:
            return True
        
        # Batarya verisi ise, k değeri = batarya numarası + 2
        # k=3 -> batarya 1, k=4 -> batarya 2, k=5 -> batarya 3, vs.
        # Maksimum k değeri = batarya sayısı + 2
        max_k_value = arm_slave_counts[arm_value] + 2
        if k_value > max_k_value:
            print(f"⚠️ HATALI VERİ: Kol {arm_value} için k={k_value} > maksimum k değeri={max_k_value} (batarya sayısı: {arm_slave_counts[arm_value]})")
            return False
        
        # k değeri 3'ten küçük olamaz (k=2 kol verisi, k=3+ batarya verisi)
        if k_value < 3:
            print(f"⚠️ HATALI VERİ: Kol {arm_value} için geçersiz k değeri: {k_value}")
            return False
        
        return True

def get_last_battery_info():
    """En son batarya bilgisini döndür (arm, k)"""
    with arm_slave_counts_lock:
        last_arm = None
        last_battery = None
        
        # Aktif kolları bul ve en son bataryayı belirle
        for arm in [1, 2, 3, 4]:
            if arm_slave_counts[arm] > 0:
                last_arm = arm
                # k değerleri 3'ten başlar, son k değeri = armslavecount + 2
                last_battery = arm_slave_counts[arm] + 2
        
        return last_arm, last_battery

def is_period_complete(arm_value, k_value, is_missing_data=False, is_alarm=False):
    """Periyot tamamlandı mı kontrol et"""
    last_arm, last_battery = get_last_battery_info()
    
    if not last_arm or not last_battery:
        return False
    
    # Debug: Periyot kontrol bilgilerini yazdır
    print(f"🔍 PERİYOT KONTROL: Kol {arm_value}, k={k_value}, Beklenen son k: {last_battery}")
    
    # En son koldaki en son batarya verisi geldi mi?
    if arm_value == last_arm and k_value == last_battery:
        print(f"✅ PERİYOT TAMAMLANDI: En son batarya verisi geldi - Kol {arm_value}, Batarya {k_value}")
        return True
    
    # Missing data geldi mi?
    if is_missing_data:
        print(f"✅ PERİYOT TAMAMLANDI: Missing data geldi - Kol {arm_value}, Batarya {k_value}")
        return True
    
    # Alarm geldi mi? (son batarya alarmından sonra periyot biter)
    if is_alarm and arm_value == last_arm and k_value == last_battery:
        print(f"✅ PERİYOT TAMAMLANDI: Son batarya alarmı geldi - Kol {arm_value}, Batarya {k_value}")
        return True
    
    return False

def send_reset_system_signal():
    """Reset system sinyali gönder (0x55 0x55 0x55) - 1 saat aralık kontrolü ile"""
    try:
        # Reset system gönderilebilir mi kontrol et (minimum 1 saat aralık)
        if not db.can_send_reset_system(min_interval_hours=1):
            print("⏰ Reset system gönderilemiyor: Son reset'ten bu yana 1 saat geçmedi")
            return False
        
        # Reset öncesi missing data'ları kaydet
        save_missing_data_before_reset()
        
        signal_data = [0x55, 0x55, 0x55]
        wave_uart_send(pi, TX_PIN, signal_data, int(1e6 / BAUD_RATE))
        print("🔄 Reset system sinyali gönderildi: 0x55 0x55 0x55")
        
        # Reset system gönderimini logla
        log_timestamp = db.log_reset_system("Missing data period completed")
        if log_timestamp:
            print(f"📝 Reset system log kaydedildi: {log_timestamp}")
        
        # Missing data listesini temizle
        clear_missing_data()
        
        return True
        
    except Exception as e:
        print(f"❌ Reset system sinyali gönderilirken hata: {e}")
        return False

def add_missing_data(arm_value, battery_value):
    """Missing data ekle"""
    with missing_data_lock:
        missing_data_tracker.add((arm_value, battery_value))
        print(f"📝 Missing data eklendi: Kol {arm_value}, Batarya {battery_value}")


def clear_missing_data():
    """Missing data listesini temizle"""
    with missing_data_lock:
        missing_data_tracker.clear()
        print("🧹 Missing data listesi temizlendi")

def resolve_missing_data(arm_value, battery_value):
    """Missing data'yı düzelt (veri geldiğinde)"""
    with missing_data_lock:
        if (arm_value, battery_value) in missing_data_tracker:
            missing_data_tracker.remove((arm_value, battery_value))
            print(f"✅ Missing data düzeltildi: Kol {arm_value}, Batarya {battery_value}")
            return True
        return False

def save_missing_data_before_reset():
    """Reset system öncesi missing data'ları kaydet"""
    with missing_data_lock:
        with missing_data_before_reset_lock:
            missing_data_before_reset.clear()
            missing_data_before_reset.update(missing_data_tracker)
            print(f"📝 Reset öncesi missing data'lar kaydedildi: {len(missing_data_before_reset)} adet")

def check_missing_data_after_reset(arm_value, battery_value):
    """Reset sonrası missing data kontrolü - status 0 gelirse alarm oluştur"""
    with missing_data_before_reset_lock:
        if (arm_value, battery_value) in missing_data_before_reset:
            # Bu batarya reset öncesi missing data'daydı, şimdi tekrar status 0 gelirse alarm
            print(f"🚨 VERİ GELMİYOR ALARMI: Kol {arm_value}, Batarya {battery_value} - Reset sonrası hala veri gelmiyor")
            # "Veri gelmiyor" alarmı oluştur
            alarm_processor.add_alarm(arm_value, battery_value, 0, 0, int(time.time() * 1000))  # error_msb=0, error_lsb=0 = veri gelmiyor
            print(f"📝 Veri gelmiyor alarmı eklendi - Arm: {arm_value}, Battery: {battery_value}")
            # Status'u 0 yap (veri yok)
            update_status(arm_value, battery_value, False)
            return True
    return False

def update_status(arm_value, battery_value, has_data):
    """Status güncelle - True=veri var, False=veri yok"""
    with status_lock:
        if arm_value in status_ram and battery_value in status_ram[arm_value]:
            status_ram[arm_value][battery_value] = has_data
            print(f"📊 Status güncellendi - Kol {arm_value}, Batarya {battery_value}: {'Veri var' if has_data else 'Veri yok'}")
        else:
            print(f"⚠️ Status güncellenemedi - Kol {arm_value}, Batarya {battery_value} bulunamadı")

def Calc_SOH(x):
    if x is None:
        return None
    
    try:
        a1, b1, c1 = 85.918, 0.0181, 0.0083
        a2, b2, c2 = 85.11, 0.0324, 0.0104
        a3, b3, c3 = 0.3085, 0.0342, 0.0021
        a4, b4, c4 = 16.521, 0.0382, 0.0013
        a5, b5, c5 = -13.874, 0.0381, 0.0011
        a6, b6, c6 = 40.077, 0.0474, 0.0079
        a7, b7, c7 = 18.207, 0.0556, 0.0048

        SohSonuc = (
            a1 * math.exp(-((x - b1) / c1) ** 2) +
            a2 * math.exp(-((x - b2) / c2) ** 2) +
            a3 * math.exp(-((x - b3) / c3) ** 2) +
            a4 * math.exp(-((x - b4) / c4) ** 2) +
            a5 * math.exp(-((x - b5) / c5) ** 2) +
            a6 * math.exp(-((x - b6) / c6) ** 2) +
            a7 * math.exp(-((x - b7) / c7) ** 2)
        )
        
        if SohSonuc > 100.0:
            SohSonuc = 100.0
        
        return round(SohSonuc, 4)
    except Exception as e:
        print(f"SOH hesaplama hatası: {str(e)}")
        return None

def Calc_SOC(x):
    if x is None:
        return None
        
    a1, a2, a3, a4 = 112.1627, 14.3937, 0, 10.5555
    b1, b2, b3, b4 = 14.2601, 11.6890, 12.7872, 10.9406
    c1, c2, c3, c4 = 1.8161, 0.8211, 0.0025, 0.3866
    
    try:
        Soctahmin = (
            a1 * math.exp(-((x - b1) / c1) ** 2) +
            a2 * math.exp(-((x - b2) / c2) ** 2) +
            a3 * math.exp(-((x - b3) / c3) ** 2) +
            a4 * math.exp(-((x - b4) / c4) ** 2)
        )
        
        if Soctahmin > 100.0:
            Soctahmin = 100.0
        elif Soctahmin < 0.0:
            Soctahmin = 0.0
            
        return round(Soctahmin, 4)
    except Exception as e:
        print(f"SOC hesaplama hatası: {str(e)}")
        return None

def read_serial(pi):
    """Bit-banging ile GPIO üzerinden seri veri oku"""
    global buffer
    print("\nBit-banging UART veri alımı başladı...")
    
    buffer.clear()

    while True:
        try:
            (count, data) = pi.bb_serial_read(RX_PIN)
            if count > 0:
                buffer.extend(data)
                
                while len(buffer) >= 3:
                    try:
                        # Header (0x80 veya 0x81) bul
                        header_index = -1
                        for i, byte in enumerate(buffer):
                            if byte == 0x80 or byte == 0x81:
                                header_index = i
                                break
                        
                        if header_index == -1:
                            buffer.clear()
                            break

                        if header_index > 0:
                            buffer = buffer[header_index:]

                        # Paket uzunluğunu belirle
                        if len(buffer) >= 3:
                            dtype = buffer[2]
                            
                            # 5 byte'lık missing data paketi kontrolü
                            if dtype == 0x7F and len(buffer) >= 5:
                                packet_length = 5
                            # 6 byte'lık paket kontrolü
                            elif len(buffer) >= 6 and (buffer[2] == 0x0F or buffer[1] == 0x7E or (buffer[2] == 0x7D and buffer[1] == 2)):
                                packet_length = 6
                            elif dtype == 0x7D and len(buffer) >= 7 and buffer[1] > 2:
                                packet_length = 7
                            else:
                                packet_length = 11

                            if len(buffer) >= packet_length:
                                packet = buffer[:packet_length]
                                buffer = buffer[packet_length:]
                                hex_packet = [f"{b:02x}" for b in packet]
                                data_queue.put(hex_packet)
                            else:
                                # Paket tamamlanmamış, daha fazla veri bekle
                                break
                        else:
                            break

                    except Exception as e:
                        print(f"Paket işleme hatası: {e}")
                        buffer.clear()
                        continue

            time.sleep(0.01)

        except Exception as e:
            print(f"Veri okuma hatası: {e}")
            time.sleep(1)

def db_worker():
    """Veritabanı işlemleri"""
    batch = []
    last_insert = time.time()
    global last_data_received
    
    while True:
        try:
            data = data_queue.get(timeout=1)
            if data is None:
                break
            
            # Veri alındığında zaman damgasını güncelle
            last_data_received = time.time()
        
            # 7 byte Batkon alarm verisi kontrolü
            if len(data) == 7:
                raw_bytes = [int(b, 16) for b in data]
                timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                
                # Batkon alarm verisi işleme
                arm_value = int(data[3], 16)
                battery = int(data[1], 16)  # 2. byte batarya numarası
                error_msb = int(data[4], 16)
                error_lsb = int(data[5], 16)
                
                # Detaylı console log
                print(f"\n*** BATKON ALARM VERİSİ ALGILANDI - {timestamp} ***")
                print(f"Arm: {arm_value}, Battery: {battery}, Error MSB: {error_msb}, Error LSB: {error_lsb}")
                print(f"Ham Veri: {data}")
                alarm_timestamp = int(time.time() * 1000)
                
                # Eğer errorlsb=1 ve errormsb=1 ise, mevcut alarmı düzelt
                if error_lsb == 1 and error_msb == 1:
                    # Periyot bitiminde işlenecek şekilde düzeltme ekle
                    alarm_processor.add_resolve(arm_value, battery)
                    print(f"📝 Batkon alarm düzeltme eklendi (beklemede) - Arm: {arm_value}, Battery: {battery}")
                else:
                    # Periyot bitiminde işlenecek şekilde alarm ekle
                    alarm_processor.add_alarm(arm_value, battery, error_msb, error_lsb, alarm_timestamp)
                    print("📝 Yeni Batkon alarm eklendi (beklemede)")
                
                # Periyot tamamlandı mı kontrol et (son batarya alarmından sonra)
                if is_period_complete(arm_value, battery, is_alarm=True):
                    print(f"🔄 PERİYOT BİTTİ - Son batarya alarmı: Kol {arm_value}, Batarya {battery}")
                    # Periyot bitti, alarmları işle
                    alarm_processor.process_period_end()
                    # Normal alarm verisi geldiğinde reset sinyali gönderme
                    # Reset sinyali sadece missing data durumunda gönderilir
                    # Yeni periyot başlat
                    reset_period()
                    get_period_timestamp()
                
                continue

            # 5 byte'lık missing data verisi kontrolü
            if len(data) == 5:
                raw_bytes = [int(b, 16) for b in data]
                timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                
                print(f"\n*** MISSING DATA VERİSİ ALGILANDI - {timestamp} ***")
                
                # Missing data kaydı hazırla
                arm_value = raw_bytes[3]
                slave_value = raw_bytes[1]
                status_value = raw_bytes[4]
                missing_timestamp = int(time.time() * 1000)
                
                print(f"Missing data: Kol {arm_value}, Batarya {slave_value}, Status: {status_value}")
                
                # Status 0 = Veri gelmiyor, Status 1 = Veri geliyor (düzeltme)
                if status_value == 0:
                    # Veri gelmiyor - missing data ekle
                    add_missing_data(arm_value, slave_value)
                    print(f"🆕 VERİ GELMİYOR: Kol {arm_value}, Batarya {slave_value}")
                    
                    # Status güncelle (veri yok)
                    update_status(arm_value, slave_value, False)
                    
                    # Reset sonrası kontrol - eğer bu batarya reset öncesi missing data'daydı ve hala status 0 geliyorsa alarm
                    check_missing_data_after_reset(arm_value, slave_value)
                    
                    # Periyot tamamlandı mı kontrol et
                    if is_period_complete(arm_value, slave_value, is_missing_data=True):
                        # Periyot bitti, alarmları işle
                        alarm_processor.process_period_end()
                        # Reset system sinyali gönder (1 saat aralık kontrolü ile)
                        if send_reset_system_signal():
                            # Yeni periyot başlat
                            reset_period()
                            get_period_timestamp()
                        else:
                            print("⏰ Reset system gönderilemedi, periyot devam ediyor")
                        
                elif status_value == 1:
                    # Veri geliyor - missing data düzelt
                    if resolve_missing_data(arm_value, slave_value):
                        print(f"✅ VERİ GELDİ: Kol {arm_value}, Batarya {slave_value} - Missing data düzeltildi")
                        # Status güncelle (veri var)
                        update_status(arm_value, slave_value, True)
                        # Alarm düzeltme işlemi
                        alarm_processor.add_resolve(arm_value, slave_value)
                        print(f"📝 Missing data alarm düzeltme eklendi - Arm: {arm_value}, Battery: {slave_value}")
                    else:
                        print(f"ℹ️ VERİ GELDİ: Kol {arm_value}, Batarya {slave_value} - Missing data zaten yoktu")
                        # Status güncelle (veri var)
                        update_status(arm_value, slave_value, True)
                
                # SQLite'ye kaydet
                with db_lock:
                    db.insert_missing_data(arm_value, slave_value, status_value, missing_timestamp)
                print("✓ Missing data SQLite'ye kaydedildi")
                continue

            # 11 byte'lık veri kontrolü
            if len(data) == 11:
                arm_value = int(data[3], 16)
                dtype = int(data[2], 16)
                k_value = int(data[1], 16)
                
                # k_value 2 geldiğinde yeni periyot başlat (ard arda gelmemesi şartıyla)
                if k_value == 2:
                    if get_last_k_value() != 2:  # Non-consecutive arm data
                        reset_period()
                        get_period_timestamp()
                    update_last_k_value(2)
                else:  # Battery data
                    update_last_k_value(k_value)
                
                # Arm değeri kontrolü
                if arm_value not in [1, 2, 3, 4]:
                    print(f"\nHATALI ARM DEĞERİ: {arm_value}")
                    continue
                
                # Veri doğrulama: Sadece aktif kollar ve bataryalar işlenir
                if not is_valid_arm_data(arm_value, k_value):
                    continue
                
                # Missing data düzeltme (veri geldiğinde)
                if k_value > 2:  # Batarya verisi
                    battery_num = k_value - 2
                    resolve_missing_data(arm_value, battery_num)
                
                # Normal batarya verisi geldiğinde reset sinyali gönderilmez
                # Sadece missing data geldiğinde reset sinyali gönderilir
                
                # Salt data hesapla
                if dtype == 11 and k_value == 2:  # Nem hesapla
                    onlar = int(data[5], 16)
                    birler = int(data[6], 16)
                    kusurat1 = int(data[7], 16)
                    kusurat2 = int(data[8], 16)
                    
                    tam_kisim = (onlar * 10 + birler)
                    kusurat_kisim = (kusurat1 * 0.1 + kusurat2 * 0.01)
                    salt_data = tam_kisim + kusurat_kisim
                    salt_data = round(salt_data, 4)
                else:
                    # Normal hesaplama
                    saltData = int(data[4], 16) * 100 + int(data[5], 16) * 10 + int(data[6], 16) + int(data[7], 16) * 0.1 + int(data[8], 16) * 0.01 + int(data[9], 16) * 0.001
                    salt_data = round(saltData, 4)
                
                # Veri tipine göre log mesajı - KALDIRILDI
                
                # Veri işleme ve kayıt (tek tabloya)
                if dtype == 10:  # Gerilim
                    # Ham gerilim verisini kaydet
                    record = {
                        "Arm": arm_value,
                        "k": k_value,
                        "Dtype": 10,
                        "data": salt_data,
                        "timestamp": get_period_timestamp()
                    }
                    batch.append(record)
                    
                    # SOC hesapla ve dtype=11'ya kaydet (sadece batarya verisi için)
                    if k_value != 2:  # k_value 2 değilse SOC hesapla
                        soc_value = Calc_SOC(salt_data)
                        soc_record = {
                            "Arm": arm_value,
                            "k": k_value,
                            "Dtype": 11,  # SOC = dtype 11 (MIB ile uyumlu)
                            "data": soc_value,
                            "timestamp": get_period_timestamp()
                        }
                        batch.append(soc_record)
                    
                    # RAM'e yaz (Modbus/SNMP için)
                    with data_lock:
                        if arm_value not in battery_data_ram:
                            battery_data_ram[arm_value] = {}
                        if k_value not in battery_data_ram[arm_value]:
                            battery_data_ram[arm_value][k_value] = {}
                        # 1-7 sıralama mapping: 1=Gerilim, 2=SOC, 3=RIMT, 4=SOH, 5=NTC1, 6=NTC2, 7=NTC3
                        if dtype == 10:  # Gerilim -> 1
                            battery_data_ram[arm_value][k_value][1] = {
                                'value': salt_data,
                                'timestamp': get_period_timestamp()
                            }
                            print(f"📊 RAM Mapping: UART dtype={dtype} -> RAM dtype=1 (Gerilim)")
                        elif dtype == 11:  # SOC -> 2
                            battery_data_ram[arm_value][k_value][2] = {
                                'value': salt_data,
                                'timestamp': get_period_timestamp()
                            }
                        elif dtype == 12:  # RIMT -> 3
                            battery_data_ram[arm_value][k_value][3] = {
                                'value': salt_data,
                                'timestamp': get_period_timestamp()
                            }
                        elif dtype == 126:  # SOH -> 4
                            battery_data_ram[arm_value][k_value][4] = {
                                'value': salt_data,
                                'timestamp': get_period_timestamp()
                            }
                        elif dtype == 13:  # NTC1 -> 5
                            battery_data_ram[arm_value][k_value][5] = {
                                'value': salt_data,
                                'timestamp': get_period_timestamp()
                            }
                        elif dtype == 14:  # NTC2 -> 6
                            battery_data_ram[arm_value][k_value][6] = {
                                'value': salt_data,
                                'timestamp': get_period_timestamp()
                            }
                        elif dtype == 15:  # NTC3 -> 7
                            battery_data_ram[arm_value][k_value][7] = {
                                'value': salt_data,
                                'timestamp': get_period_timestamp()
                            }
                        
                        # SOC hesapla ve 2'ye kaydet (sadece batarya verisi için)
                        if k_value != 2 and dtype == 10:  # Gerilim verisi geldiğinde SOC hesapla
                            battery_data_ram[arm_value][k_value][2] = {
                                'value': soc_value,
                                'timestamp': get_period_timestamp()
                            }
                        print(f"RAM'e kaydedildi: Arm={arm_value}, k={k_value}, dtype={dtype}, value={salt_data}")
                        if k_value != 2 and dtype == 10:
                            print(f"RAM'e kaydedildi: Arm={arm_value}, k={k_value}, dtype=2 (SOC), value={soc_value}")
                    
                    # Status güncelle (sadece missing data durumunda)
                    # Normal veri geldiğinde status güncelleme yapmıyoruz
                    # Status sadece missing data (0) veya düzeldi (1) durumunda güncellenir
                    
                    # Alarm kontrolü kaldırıldı - sadece alarm verisi geldiğinde yapılır
                
                elif dtype == 11:  # RIMT veya Nem
                    if k_value == 2:  # Nem verisi
                        print(f"*** VERİ ALGILANDI - Arm: {arm_value}, Data: {salt_data}% ***")
                        record = {
                            "Arm": arm_value,
                            "k": k_value,
                            "Dtype": 12,  # RIMT=12
                            "data": salt_data,
                            "timestamp": get_period_timestamp()
                        }
                        batch.append(record)
                    
                        # RAM'e yaz (Modbus/SNMP için)
                        with data_lock:
                            if arm_value not in battery_data_ram:
                                battery_data_ram[arm_value] = {}
                            if k_value not in battery_data_ram[arm_value]:
                                battery_data_ram[arm_value][k_value] = {}
                            # 1-7 sıralama mapping
                            if dtype == 10:  # Gerilim -> 1
                                battery_data_ram[arm_value][k_value][1] = {
                                    'value': salt_data,
                                    'timestamp': get_period_timestamp()
                                }
                            elif dtype == 11:  # SOC -> 2
                                battery_data_ram[arm_value][k_value][2] = {
                                    'value': salt_data,
                                    'timestamp': get_period_timestamp()
                                }
                            elif dtype == 12:  # RIMT -> 3
                                battery_data_ram[arm_value][k_value][3] = {
                                    'value': salt_data,
                                    'timestamp': get_period_timestamp()
                                }
                            elif dtype == 126:  # SOH -> 4
                                battery_data_ram[arm_value][k_value][4] = {
                                    'value': salt_data,
                                    'timestamp': get_period_timestamp()
                                }
                            elif dtype == 13:  # NTC1 -> 5
                                battery_data_ram[arm_value][k_value][5] = {
                                    'value': salt_data,
                                    'timestamp': get_period_timestamp()
                                }
                            elif dtype == 14:  # NTC2 -> 6
                                battery_data_ram[arm_value][k_value][6] = {
                                    'value': salt_data,
                                    'timestamp': get_period_timestamp()
                                }
                            elif dtype == 15:  # NTC3 -> 7
                                battery_data_ram[arm_value][k_value][7] = {
                                    'value': salt_data,
                                    'timestamp': get_period_timestamp()
                                }
                        
                        # Alarm kontrolü kaldırıldı - sadece alarm verisi geldiğinde yapılır
                    else:  # RIMT verisi
                        record = {
                            "Arm": arm_value,
                            "k": k_value,
                            "Dtype": 12,  # RIMT=12
                            "data": salt_data,
                        "timestamp": get_period_timestamp()
                    }
                    batch.append(record)
                
                    # RAM'e yaz (Modbus/SNMP için)
                    with data_lock:
                            if arm_value not in battery_data_ram:
                                battery_data_ram[arm_value] = {}
                            if k_value not in battery_data_ram[arm_value]:
                                battery_data_ram[arm_value][k_value] = {}
                            # 1-7 sıralama mapping
                            if dtype == 10:  # Gerilim -> 1
                                battery_data_ram[arm_value][k_value][1] = {
                                    'value': salt_data,
                                    'timestamp': get_period_timestamp()
                                }
                            elif dtype == 11:  # SOC -> 2
                                battery_data_ram[arm_value][k_value][2] = {
                                    'value': salt_data,
                                    'timestamp': get_period_timestamp()
                                }
                            elif dtype == 12:  # RIMT -> 3
                                battery_data_ram[arm_value][k_value][3] = {
                                    'value': salt_data,
                                    'timestamp': get_period_timestamp()
                                }
                            elif dtype == 126:  # SOH -> 4
                                battery_data_ram[arm_value][k_value][4] = {
                                    'value': salt_data,
                                    'timestamp': get_period_timestamp()
                                }
                            elif dtype == 13:  # NTC1 -> 5
                                battery_data_ram[arm_value][k_value][5] = {
                                    'value': salt_data,
                                    'timestamp': get_period_timestamp()
                                }
                            elif dtype == 14:  # NTC2 -> 6
                                battery_data_ram[arm_value][k_value][6] = {
                                    'value': salt_data,
                                    'timestamp': get_period_timestamp()
                                }
                            elif dtype == 15:  # NTC3 -> 7
                                battery_data_ram[arm_value][k_value][7] = {
                                    'value': salt_data,
                                    'timestamp': get_period_timestamp()
                                }
                        
                        # Alarm kontrolü kaldırıldı - sadece alarm verisi geldiğinde yapılır
                
                elif dtype == 12:  # SOH
                    if k_value == 2:  # Nem verisi (eski sistem)
                        print(f"*** VERİ ALGILANDI - Arm: {arm_value}, Data: {salt_data}% ***")
                        record = {
                            "Arm": arm_value,
                            "k": k_value,
                            "Dtype": 12,  # RIMT=12
                            "data": salt_data,
                            "timestamp": get_period_timestamp()
                        }
                        batch.append(record)
                    else:  # SOH verisi
                        if int(data[4], 16) == 1:  # Eğer data[4] 1 ise SOH 100'dür
                            soh_value = 100.0
                        else:
                            onlar = int(data[5], 16)
                            birler = int(data[6], 16)
                            kusurat1 = int(data[7], 16)
                            kusurat2 = int(data[8], 16)
                            
                            tam_kisim = (onlar * 10 + birler)
                            kusurat_kisim = (kusurat1 * 0.1 + kusurat2 * 0.01)
                            soh_value = tam_kisim + kusurat_kisim
                            soh_value = round(soh_value, 4)
                        
                        # SOH verisini dtype=126'ya kaydet
                        record = {
                            "Arm": arm_value,
                            "k": k_value,
                            "Dtype": 126,
                            "data": soh_value,
                            "timestamp": get_period_timestamp()
                        }
                        batch.append(record)
                        
                        # RAM'e yaz (Modbus/SNMP için)
                        with data_lock:
                            if arm_value not in battery_data_ram:
                                battery_data_ram[arm_value] = {}
                            if k_value not in battery_data_ram[arm_value]:
                                battery_data_ram[arm_value][k_value] = {}
                            # SOH verisi -> 4 (1-7 sıralama)
                            battery_data_ram[arm_value][k_value][4] = {
                                'value': soh_value,
                                'timestamp': get_period_timestamp()
                            }
                        
                        # Alarm kontrolü kaldırıldı - sadece alarm verisi geldiğinde yapılır
                
                elif dtype == 13:  # NTC1
                    record = {
                            "Arm": arm_value,
                            "k": k_value,
                        "Dtype": 13,
                        "data": salt_data,
                            "timestamp": get_period_timestamp()
                        }
                    batch.append(record)
                    
                    # RAM'e yaz (Modbus/SNMP için)
                    with data_lock:
                        if arm_value not in battery_data_ram:
                            battery_data_ram[arm_value] = {}
                        if k_value not in battery_data_ram[arm_value]:
                            battery_data_ram[arm_value][k_value] = {}
                        battery_data_ram[arm_value][k_value][dtype] = {
                            'value': salt_data,
                            'timestamp': get_period_timestamp()
                        }
                    
                    # Alarm kontrolü kaldırıldı - sadece alarm verisi geldiğinde yapılır
                
                elif dtype == 14:  # NTC2
                    record = {
                        "Arm": arm_value,
                        "k": k_value,
                        "Dtype": 14,
                        "data": salt_data,
                        "timestamp": get_period_timestamp()
                    }
                    batch.append(record)
                    
                    # RAM'e yaz (Modbus/SNMP için)
                    with data_lock:
                        if arm_value not in battery_data_ram:
                            battery_data_ram[arm_value] = {}
                        if k_value not in battery_data_ram[arm_value]:
                            battery_data_ram[arm_value][k_value] = {}
                        battery_data_ram[arm_value][k_value][dtype] = {
                            'value': salt_data,
                            'timestamp': get_period_timestamp()
                        }
                    
                    # Alarm kontrolü kaldırıldı - sadece alarm verisi geldiğinde yapılır
                
                elif dtype == 15:  # NTC3
                    record = {
                        "Arm": arm_value,
                        "k": k_value,
                        "Dtype": 15,
                        "data": salt_data,
                        "timestamp": get_period_timestamp()
                    }
                    batch.append(record)
                    
                    # RAM'e yaz (Modbus/SNMP için)
                    with data_lock:
                        if arm_value not in battery_data_ram:
                            battery_data_ram[arm_value] = {}
                        if k_value not in battery_data_ram[arm_value]:
                            battery_data_ram[arm_value][k_value] = {}
                        battery_data_ram[arm_value][k_value][dtype] = {
                            'value': salt_data,
                            'timestamp': get_period_timestamp()
                        }
                    
                    # Alarm kontrolü kaldırıldı - sadece alarm verisi geldiğinde yapılır
                
                else:  # Diğer Dtype değerleri için
                    record = {
                        "Arm": arm_value,
                        "k": k_value,
                        "Dtype": dtype,
                        "data": salt_data,
                        "timestamp": get_period_timestamp()
                    }
                    batch.append(record)
                    
                    # RAM'e yaz (Modbus/SNMP için)
                    with data_lock:
                        if arm_value not in battery_data_ram:
                            battery_data_ram[arm_value] = {}
                        if k_value not in battery_data_ram[arm_value]:
                            battery_data_ram[arm_value][k_value] = {}
                        battery_data_ram[arm_value][k_value][dtype] = {
                            'value': salt_data,
                            'timestamp': get_period_timestamp()
                        }
                    
                    # Alarm kontrolü kaldırıldı - sadece alarm verisi geldiğinde yapılır

            # 6 byte'lık balans komutu veya armslavecounts kontrolü
            elif len(data) == 6:
                raw_bytes = [int(b, 16) for b in data]
                
                # Slave sayısı verisi: 2. byte (index 1) 0x7E ise
                if raw_bytes[1] == 0x7E:
                    arm1, arm2, arm3, arm4 = raw_bytes[2], raw_bytes[3], raw_bytes[4], raw_bytes[5]
                    print(f"armslavecounts verisi tespit edildi: arm1={arm1}, arm2={arm2}, arm3={arm3}, arm4={arm4}")
                    
                    # RAM'de armslavecounts güncelle
                    with arm_slave_counts_lock:
                        arm_slave_counts[1] = arm1
                        arm_slave_counts[2] = arm2
                        arm_slave_counts[3] = arm3
                        arm_slave_counts[4] = arm4
                    
                    # Modbus/SNMP için RAM'e de kaydet
                    with data_lock:
                        arm_slave_counts_ram[1] = arm1
                        arm_slave_counts_ram[2] = arm2
                        arm_slave_counts_ram[3] = arm3
                        arm_slave_counts_ram[4] = arm4
                    
                    # Alarm RAM yapısını güncelle
                    initialize_alarm_ram()
                    
                    # Status RAM yapısını başlat
                    initialize_status_ram()
                    
                    print(f"✓ Armslavecounts RAM'e kaydedildi: {arm_slave_counts}")
                    print(f"✓ Modbus/SNMP RAM'e kaydedildi: {arm_slave_counts_ram}")
                    
                # Hatkon (kol) alarm verisi: 2. byte (index 1) 0x8E ise
                elif raw_bytes[1] == 0x8E:
                    arm_value = raw_bytes[2]
                    error_msb = raw_bytes[3]
                    error_lsb = raw_bytes[4]
                    status = raw_bytes[5]
                    
                    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                    print(f"\n*** HATKON ALARM VERİSİ ALGILANDI - {timestamp} ***")
                    print(f"Arm: {arm_value}, Error MSB: {error_msb}, Error LSB: {error_lsb}, Status: {status}")
                    print(f"Ham Veri: {data}")
                    
                    alarm_timestamp = int(time.time() * 1000)
                    
                    # Eğer errorlsb=9 ve errormsb=1 ise, mevcut kol alarmını düzelt
                    if error_lsb == 9 and error_msb == 1:
                        # Periyot bitiminde işlenecek şekilde düzeltme ekle
                        alarm_processor.add_resolve(arm_value, 0)  # 0 = kol alarmı
                        print(f"📝 Hatkon alarm düzeltme eklendi (beklemede) - Arm: {arm_value}")
                    else:
                        # Periyot bitiminde işlenecek şekilde alarm ekle
                        alarm_processor.add_alarm(arm_value, 0, error_msb, error_lsb, alarm_timestamp)  # 0 = kol alarmı
                        print("📝 Yeni Hatkon alarm eklendi (beklemede)")
                    
                    continue
                    try:
                        updated_at = int(time.time() * 1000)
                        # Her arm için ayrı kayıt oluştur
                        with db_lock:
                            db.insert_arm_slave_counts(1, arm1)
                            db.insert_arm_slave_counts(2, arm2)
                            db.insert_arm_slave_counts(3, arm3)
                            db.insert_arm_slave_counts(4, arm4)
                        print("✓ Armslavecounts SQLite'ye kaydedildi")
                        
                    except Exception as e:
                        print(f"armslavecounts kayıt hatası: {e}")
                    continue
                
                # Balans verisi: 3. byte (index 2) 0x0F ise
                elif raw_bytes[2] == 0x0F:
                    try:
                        updated_at = int(time.time() * 1000)
                        global program_start_time
                        if updated_at > program_start_time:
                            slave_value = raw_bytes[1]
                            arm_value = raw_bytes[3]
                            status_value = raw_bytes[4]
                            balance_timestamp = updated_at
                            
                            with db_lock:
                                db.update_or_insert_passive_balance(arm_value, slave_value, status_value, balance_timestamp)
                            print(f"✓ Balans güncellendi: Arm={arm_value}, Slave={slave_value}, Status={status_value}")
                            program_start_time = updated_at
                    except Exception as e:
                        print(f"Balans kayıt hatası: {e}")
                    continue
                
                # Hatkon alarmı: 3. byte (index 2) 0x7D ise
                elif raw_bytes[2] == 0x7D:
                    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                    print(f"\n*** HATKON ALARM VERİSİ ALGILANDI - {timestamp} ***")

                    arm_value = raw_bytes[3]
                    error_msb = raw_bytes[4]
                    error_lsb = 9
                    alarm_timestamp = int(time.time() * 1000)
                    
                    # Eğer error_msb=1 veya error_msb=0 ise, mevcut alarmı düzelt
                    if error_msb == 1 or error_msb == 0:
                        with db_lock:
                            if db.resolve_alarm(arm_value, 2):  # Hatkon alarmları için battery=2
                                print(f"✓ Hatkon alarm düzeltildi - Arm: {arm_value} (error_msb: {error_msb})")
                            else:
                                print(f"⚠ Düzeltilecek aktif Hatkon alarm bulunamadı - Arm: {arm_value}")
                    else:
                        # Yeni alarm ekle
                        with db_lock:
                            db.insert_alarm(arm_value, 2, error_msb, error_lsb, alarm_timestamp)
                        print("✓ Yeni Hatkon alarm SQLite'ye kaydedildi")
                    continue

            # Batch kontrolü ve kayıt
            if len(batch) >= 100 or (time.time() - last_insert) > 5:
                # Sadece yazma işlemi için kısa süreli kilit
                batch_size = len(batch)
                with db_lock:
                    db.insert_battery_data_batch(batch)
                batch = []
                last_insert = time.time()
                print(f"✅ {batch_size} veri batch olarak eklendi")

            data_queue.task_done()
            
        except queue.Empty:
            if batch:
                batch_size = len(batch)
                with db_lock:
                    db.insert_battery_data_batch(batch)
                batch = []
                last_insert = time.time()
                print(f"✅ {batch_size} veri batch olarak eklendi")
        except Exception as e:
            print(f"\ndb_worker'da beklenmeyen hata: {e}")
            continue

def send_batconfig_to_device(config_data):
    """Batarya konfigürasyonunu cihaza gönder"""
    try:
        # UART paketi hazırla: Header(0x81) + Arm + Dtype(0x7C) + tüm parametreler + CRC
        config_packet = bytearray([0x81])  # Header
        
        # Arm değerini ekle
        arm_value = int(config_data['armValue']) & 0xFF
        config_packet.append(arm_value)
        
        # Dtype ekle
        config_packet.append(0x7C)
        
        # Float değerleri 2 byte olarak hazırla (1 byte tam kısım, 1 byte ondalık kısım)
        vnom = float(str(config_data['Vnom']))
        vmax = float(str(config_data['Vmax']))
        vmin = float(str(config_data['Vmin']))
        
        # Float değerleri ekle (Vnom, Vmax, Vmin)
        config_packet.extend([
            int(vnom) & 0xFF,                # Vnom tam kısım
            int((vnom % 1) * 100) & 0xFF,    # Vnom ondalık kısım
            int(vmax) & 0xFF,                # Vmax tam kısım
            int((vmax % 1) * 100) & 0xFF,    # Vmax ondalık kısım
            int(vmin) & 0xFF,                # Vmin tam kısım
            int((vmin % 1) * 100) & 0xFF     # Vmin ondalık kısım
        ])
        
        # 1 byte değerleri ekle
        config_packet.extend([
            int(config_data['Rintnom']) & 0xFF,
            int(config_data['Tempmin_D']) & 0xFF,
            int(config_data['Tempmax_D']) & 0xFF,
            int(config_data['Tempmin_PN']) & 0xFF,
            int(config_data['Tempmax_PN']) & 0xFF,
            int(config_data['Socmin']) & 0xFF,
            int(config_data['Sohmin']) & 0xFF
        ])
        
        # CRC hesapla (tüm byte'ların toplamı)
        crc = sum(config_packet) & 0xFF
        config_packet.append(crc)
        
        # Detaylı log
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        print(f"\n*** BATARYA KONFİGÜRASYONU GÖNDERİLİYOR - {timestamp} ***")
        print(f"Kol: {config_data['armValue']}")
        print(f"Vnom: {vnom} (2 byte: {int(vnom) & 0xFF}, {int((vnom % 1) * 100) & 0xFF})")
        print(f"Vmax: {vmax} (2 byte: {int(vmax) & 0xFF}, {int((vmax % 1) * 100) & 0xFF})")
        print(f"Vmin: {vmin} (2 byte: {int(vmin) & 0xFF}, {int((vmin % 1) * 100) & 0xFF})")
        print(f"Rintnom: {config_data['Rintnom']}")
        print(f"Tempmin_D: {config_data['Tempmin_D']}")
        print(f"Tempmax_D: {config_data['Tempmax_D']}")
        print(f"Tempmin_PN: {config_data['Tempmin_PN']}")
        print(f"Tempmax_PN: {config_data['Tempmax_PN']}")
        print(f"Socmin: {config_data['Socmin']}")
        print(f"Sohmin: {config_data['Sohmin']}")
        print(f"CRC: 0x{crc:02X}")
        print(f"UART Paketi: {[f'0x{b:02X}' for b in config_packet]}")
        print(f"Paket Uzunluğu: {len(config_packet)} byte")
        
        # Paketi gönder
        wave_uart_send(pi, TX_PIN, config_packet, int(1e6 / BAUD_RATE))
        print(f"✓ Kol {config_data['armValue']} batarya konfigürasyonu cihaza gönderildi")
        
        # Veritabanına kaydet
        try:
            with db_lock:
                db.insert_batconfig(
                    arm=config_data['armValue'],
                    vnom=config_data['Vnom'],
                    vmax=config_data['Vmax'],
                    vmin=config_data['Vmin'],
                    rintnom=config_data['Rintnom'],
                    tempmin_d=config_data['Tempmin_D'],
                    tempmax_d=config_data['Tempmax_D'],
                    tempmin_pn=config_data['Tempmin_PN'],
                    tempmax_pn=config_data['Tempmax_PN'],
                    socmin=config_data['Socmin'],
                    sohmin=config_data['Sohmin']
                )
            print(f"✓ Kol {config_data['armValue']} batarya konfigürasyonu veritabanına kaydedildi")
        except Exception as e:
            print(f"❌ Veritabanı kayıt hatası: {e}")
        
        print("*** BATARYA KONFİGÜRASYONU TAMAMLANDI ***\n")
        
    except Exception as e:
        print(f"Batarya konfigürasyonu cihaza gönderilirken hata: {e}")

def send_armconfig_to_device(config_data):
    """Kol konfigürasyonunu cihaza gönder"""
    try:
        # UART paketi hazırla: Header(0x81) + Arm + Dtype(0x7B) + tüm parametreler + CRC
        config_packet = bytearray([0x81])  # Header
        
        # Arm değerini ekle
        arm_value = int(config_data['armValue']) & 0xFF
        config_packet.append(arm_value)
        
        # Dtype ekle (0x7B)
        config_packet.append(0x7B)
        
        # akimMax değerini 3 haneli formata çevir
        akimMax = int(config_data['akimMax'])
        akimMax_str = f"{akimMax:03d}"  # 3 haneli string formatı (örn: 045, 126)
        
        # ArmConfig değerlerini ekle
        config_packet.extend([
            int(config_data['akimKats']) & 0xFF,    # akimKats
            int(akimMax_str[0]) & 0xFF,            # akimMax1 (ilk hane)
            int(akimMax_str[1]) & 0xFF,            # akimMax2 (ikinci hane)
            int(akimMax_str[2]) & 0xFF,            # akimMax3 (üçüncü hane)
            int(config_data['nemMax']) & 0xFF,      # nemMax
            int(config_data['nemMin']) & 0xFF,      # nemMin
            int(config_data['tempMax']) & 0xFF,     # tempMax
            int(config_data['tempMin']) & 0xFF      # tempMin
        ])
        
        # CRC hesapla (tüm byte'ların toplamı)
        crc = sum(config_packet) & 0xFF
        config_packet.append(crc)
        
        # Detaylı log
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        print(f"\n*** KOL KONFİGÜRASYONU GÖNDERİLİYOR - {timestamp} ***")
        print(f"Kol: {config_data['armValue']}")
        print(f"Akım Katsayısı: {config_data['akimKats']}")
        print(f"Maksimum Akım: {akimMax} (3 haneli: {akimMax_str})")
        print(f"akimMax1: {akimMax_str[0]} (ilk hane)")
        print(f"akimMax2: {akimMax_str[1]} (ikinci hane)")
        print(f"akimMax3: {akimMax_str[2]} (üçüncü hane)")
        print(f"Nem Max: {config_data['nemMax']}%")
        print(f"Nem Min: {config_data['nemMin']}%")
        print(f"Sıcaklık Max: {config_data['tempMax']}°C")
        print(f"Sıcaklık Min: {config_data['tempMin']}°C")
        print(f"CRC: 0x{crc:02X}")
        print(f"UART Paketi: {[f'0x{b:02X}' for b in config_packet]}")
        print(f"Paket Uzunluğu: {len(config_packet)} byte")
        
        # Paketi gönder
        wave_uart_send(pi, TX_PIN, config_packet, int(1e6 / BAUD_RATE))
        print(f"✓ Kol {config_data['armValue']} konfigürasyonu cihaza gönderildi")
        
        # Veritabanına kaydet
        try:
            with db_lock:
                db.insert_armconfig(
                    arm=config_data['armValue'],
                    nem_max=config_data['nemMax'],
                    nem_min=config_data['nemMin'],
                    temp_max=config_data['tempMax'],
                    temp_min=config_data['tempMin']
                )
            print(f"✓ Kol {config_data['armValue']} konfigürasyonu veritabanına kaydedildi")
        except Exception as e:
            print(f"❌ Veritabanı kayıt hatası: {e}")
        
        print("*** KOL KONFİGÜRASYONU TAMAMLANDI ***\n")
        
    except Exception as e:
        print(f"Kol konfigürasyonu cihaza gönderilirken hata: {e}")


def wave_uart_send(pi, gpio_pin, data_bytes, bit_time):
    """Bit-banging UART ile veri gönder"""
    try:
        # Start bit (0) + data bits + stop bit (1)
        wave_data = []
        
        for byte in data_bytes:
            # Start bit
            wave_data.append(pigpio.pulse(0, 1 << gpio_pin, bit_time))
            # Data bits (LSB first)
            for i in range(8):
                bit = (byte >> i) & 1
                if bit:
                    wave_data.append(pigpio.pulse(1 << gpio_pin, 0, bit_time))
                else:
                    wave_data.append(pigpio.pulse(0, 1 << gpio_pin, bit_time))
            # Stop bit
            wave_data.append(pigpio.pulse(1 << gpio_pin, 0, bit_time))
        
        # Wave oluştur ve gönder
        pi.wave_clear()
        pi.wave_add_generic(wave_data)
        wave_id = pi.wave_create()
        pi.wave_send_once(wave_id)
        
        # Wave'i temizle
        pi.wave_delete(wave_id)
        
        # UART gönderim log'u
        print(f"  → UART Gönderim: GPIO{TX_PIN}, {len(data_bytes)} byte, {BAUD_RATE} baud")
        print(f"  → Wave ID: {wave_id}, Wave Data: {len(wave_data)} pulse")
        
    except Exception as e:
        print(f"UART gönderim hatası: {e}")

def send_read_all_command(command):
    """Tümünü oku komutu gönder (0x81 0x05 0x7A)"""
    try:
        # Komutu parse et: "5 5 0x7A" -> [0x81, 0x05, 0x7A]
        parts = command.split()
        if len(parts) >= 3:
            arm = int(parts[0])
            dtype = int(parts[1])
            cmd = int(parts[2], 16) if parts[2].startswith('0x') else int(parts[2])
            
            # UART paketi hazırla (0x81 zaten dtype değeri içeriyor)
            packet = [0x81, arm, cmd]
            
            print(f"*** TÜMÜNÜ OKU KOMUTU GÖNDERİLİYOR ***")
            print(f"Arm: {arm}, Dtype: 0x{dtype:02X}, Cmd: 0x{cmd:02X}")
            print(f"UART Paketi: {[f'0x{b:02X}' for b in packet]}")
            
            # UART'a gönder
            wave_uart_send(pi, TX_PIN, packet, int(1e6 / BAUD_RATE))
            print(f"✓ Tümünü oku komutu cihaza gönderildi")
            
        else:
            print(f"❌ Geçersiz komut formatı: {command}")
            
    except Exception as e:
        print(f"❌ Tümünü oku komutu gönderilirken hata: {e}")

def config_worker():
    """Konfigürasyon değişikliklerini işle"""
    while True:
        try:
            config_file = "pending_config.json"
            if os.path.exists(config_file):
                try:
                    with open(config_file, 'r', encoding='utf-8') as f:
                        config_data = json.load(f)
                    os.remove(config_file)
                    
                    if config_data.get('type') == 'batconfig':
                        # Database'deki yeni fonksiyonu kullan
                        data = config_data['data']
                        db.save_battery_config(
                            data['armValue'], data['Vmin'], data['Vmax'], data['Vnom'],
                            data['Rintnom'], data['Tempmin_D'], data['Tempmax_D'],
                            data['Tempmin_PN'], data['Tempmax_PN'], data['Socmin'], data['Sohmin']
                        )
                        # Cihaza da gönder
                        send_batconfig_to_device(data)
                    elif config_data.get('type') == 'armconfig':
                        # Database'deki yeni fonksiyonu kullan
                        data = config_data['data']
                        db.save_arm_config(
                            data['armValue'], data['akimKats'], data['akimMax'],
                            data['nemMax'], data['nemMin'], data['tempMax'], data['tempMin']
                        )
                        # Cihaza da gönder
                        send_armconfig_to_device(data)
                    elif config_data.get('type') == 'send_to_device':
                        # Tümünü oku komutu gönder
                        command = config_data.get('command', '5 5 0x7A')
                        send_read_all_command(command)
                    elif config_data.get('type') == 'manual_set':
                        # Manuel kol set komutu gönder
                        arm = config_data.get('arm')
                        slave = config_data.get('slave', 0)
                        command = config_data.get('command')
                        if command:
                            print(f"*** MANUEL KOL SET KOMUTU GÖNDERİLİYOR ***")
                            print(f"Arm: {arm}, Slave: {slave}, Komut: {command} (Hex: {[hex(x) for x in command]})")
                            wave_uart_send(pi, TX_PIN, command, int(1e6 / BAUD_RATE))
                            print(f"✓ Kol {arm}, Batarya {slave} manuel set komutu cihaza gönderildi")
                    
                except Exception as e:
                    print(f"Konfigürasyon dosyası işlenirken hata: {e}")
                    if os.path.exists(config_file):
                        os.remove(config_file)
            time.sleep(1)
        except Exception as e:
            print(f"Config worker hatası: {e}")
            time.sleep(1)

def main():
    try:
        # Database sınıfı __init__'de tabloları ve default değerleri oluşturuyor
        
        # Başlangıçta varsayılan armslavecount değerlerini ayarla
        with arm_slave_counts_lock:
            arm_slave_counts[1] = 0
            arm_slave_counts[2] = 0
            arm_slave_counts[3] = 0
            arm_slave_counts[4] = 0
        print(f"✓ Başlangıç varsayılan armslavecount değerleri: {arm_slave_counts}")
        
        # Veritabanından en son armslavecount değerlerini çek
        load_arm_slave_counts_from_db()
        
        # Trap hedeflerini RAM'e yükle
        load_trap_targets_to_ram()
        
        if not pi.connected:
            print("pigpio bağlantısı sağlanamadı!")
            return
            
        pi.write(TX_PIN, 1)

        # Okuma thread'i
        pi.bb_serial_read_open(RX_PIN, BAUD_RATE)
        print(f"GPIO{RX_PIN} bit-banging UART başlatıldı @ {BAUD_RATE} baud.")

        # Okuma thread'i
        read_thread = threading.Thread(target=read_serial, args=(pi,), daemon=True)
        read_thread.start()
        print("read_serial thread'i başlatıldı.")

        # Veritabanı işlemleri
        db_thread = threading.Thread(target=db_worker, daemon=True)
        db_thread.start()
        print("db_worker thread'i başlatıldı.")

        # Konfigürasyon işlemleri
        config_thread = threading.Thread(target=config_worker, daemon=True)
        config_thread.start()
        print("Config worker thread'i başlatıldı.")

        # Modbus TCP sunucu
        modbus_thread = threading.Thread(target=modbus_tcp_server, daemon=True)
        modbus_thread.start()
        print("Modbus TCP sunucu thread'i başlatıldı.")

        # SNMP sunucu thread'i
        snmp_thread = threading.Thread(target=snmp_server, daemon=True)
        snmp_thread.start()
        print("SNMP sunucu thread'i başlatıldı.")

        print(f"\nSistem başlatıldı.")
        print("Program çalışıyor... (Ctrl+C ile durdurun)")

        while True:
            time.sleep(0.1)

    except KeyboardInterrupt:
        print("\nProgram sonlandırılıyor...")

    finally:
        if 'pi' in locals():
            try:
                pi.bb_serial_read_close(RX_PIN)
                print("Bit-bang UART kapatıldı.")
            except pigpio.error:
                print("Bit-bang UART zaten kapalı.")
            pi.stop()

# ==============================================
# MODBUS TCP SERVER FUNCTIONS
# ==============================================

def get_dynamic_data_index(arm, battery_num, data_type):
    """Dinamik veri indeksi hesapla"""
    # Veri tipleri:
    # 1: Kol akım, 2: Kol nem, 3: Kol sıcaklık, 4: Kol sıcaklık2
    # 5: Batarya gerilim, 6: SOC, 7: Rint, 8: SOH, 9: NTC1, 10: NTC2, 11: NTC3
    
    if data_type == 1:  # Kol akım
        return 1
    elif data_type == 2:  # Kol nem
        return 2
    elif data_type == 3:  # Kol sıcaklık
        return 3
    elif data_type == 4:  # Kol sıcaklık2
        return 4
    elif data_type == 5:  # Batarya gerilim
        return 5 + (battery_num - 1) * 7  # Her batarya için 7 veri
    elif data_type == 6:  # SOC
        return 6 + (battery_num - 1) * 7
    elif data_type == 7:  # Rint
        return 7 + (battery_num - 1) * 7
    elif data_type == 8:  # SOH
        return 8 + (battery_num - 1) * 7
    elif data_type == 9:  # NTC1
        return 9 + (battery_num - 1) * 7
    elif data_type == 10:  # NTC2
        return 10 + (battery_num - 1) * 7
    elif data_type == 11:  # NTC3
        return 11 + (battery_num - 1) * 7
    else:
        return 0

def get_dynamic_data_by_index(start_index, quantity):
    """Dinamik veri indeksine göre veri döndür"""
    with data_lock:
        result = []
        current_index = start_index  # start_index'ten başla
        
        print(f"DEBUG: get_dynamic_data_by_index start={start_index}, quantity={quantity}")
        print(f"DEBUG: arm_slave_counts_ram = {arm_slave_counts_ram}")
        
        # Aralık kontrolü
        if start_index < 1001 or start_index > 4994:
            print(f"DEBUG: Geçersiz aralık! start_index={start_index} (1001-4994 arası olmalı)")
            return [0.0] * quantity
        
        # Hangi kol aralığında olduğunu belirle
        if 1001 <= start_index <= 1994:
            target_arm = 1
            arm_start = 1001
        elif 2001 <= start_index <= 2994:
            target_arm = 2
            arm_start = 2001
        elif 3001 <= start_index <= 3994:
            target_arm = 3
            arm_start = 3001
        elif 4001 <= start_index <= 4994:
            target_arm = 4
            arm_start = 4001
        else:
            print(f"DEBUG: Geçersiz aralık! start_index={start_index}")
            return [0.0] * quantity
        
        print(f"DEBUG: Hedef kol: {target_arm}, aralık: {arm_start}-{arm_start+993}")
        
        # Sadece hedef kolu işle
        for arm in range(1, 5):  # Kol 1-4
            if arm != target_arm:
                continue  # Sadece hedef kolu işle
                
            print(f"DEBUG: Kol {arm} işleniyor...")
            print(f"DEBUG: battery_data_ram[{arm}] = {battery_data_ram.get(arm, 'YOK')}")
            
            # Kol verileri (akım, nem, sıcaklık, sıcaklık2)
            for data_type in range(1, 5):
                print(f"DEBUG: current_index={current_index}, start_index={start_index}, len(result)={len(result)}, quantity={quantity}")
                if current_index >= start_index and len(result) < quantity:
                    print(f"DEBUG: IF BLOĞU GİRİLDİ!")
                    print(f"DEBUG: get_battery_data_ram({arm}) çağrılıyor...")
                    try:
                        # data_lock zaten alınmış, direkt erişim
                        arm_data = dict(battery_data_ram.get(arm, {}))
                        print(f"DEBUG: arm_data = {arm_data}")
                        print(f"DEBUG: arm_data type = {type(arm_data)}")
                    except Exception as e:
                        print(f"DEBUG: HATA! arm_data okuma hatası: {e}")
                        arm_data = None
                    if arm_data and 2 in arm_data:  # k=2 (kol verisi)
                        print(f"DEBUG: k=2 verisi bulundu!")
                        if data_type == 1:  # Akım
                            value = arm_data[2].get(10, {}).get('value', 0)  # dtype=10 (A)
                        elif data_type == 2:  # Nem
                            value = arm_data[2].get(11, {}).get('value', 0)  # dtype=11 (B)
                        elif data_type == 3:  # Sıcaklık
                            value = arm_data[2].get(12, {}).get('value', 0)  # dtype=12 (C)
                        elif data_type == 4:  # Sıcaklık2
                            value = arm_data[2].get(13, {}).get('value', 0)  # dtype=13 (D)
                        else:
                            value = 0
                        result.append(float(value) if value else 0.0)
                        print(f"DEBUG: current_index={current_index}, data_type={data_type}, value={value}")
                    else:
                        print(f"DEBUG: k=2 verisi bulunamadı!")
                        result.append(0.0)
                        print(f"DEBUG: current_index={current_index}, data_type={data_type}, value=0.0 (veri yok)")
                else:
                    print(f"DEBUG: IF BLOĞU GİRİLMEDİ!")
                    result.append(0.0)
                    print(f"DEBUG: current_index={current_index}, data_type={data_type}, value=0.0 (IF girmedi)")
                current_index += 1
                
                if len(result) >= quantity:
                    break
                    
            if len(result) >= quantity:
                break
                
            # Batarya verileri
            battery_count = arm_slave_counts_ram.get(arm, 0)
            print(f"DEBUG: Kol {arm} batarya sayısı: {battery_count}")
            for battery_num in range(1, battery_count + 1):
                print(f"DEBUG: Batarya {battery_num} işleniyor...")
                k_value = battery_num + 2  # k=3,4,5,6...
                print(f"DEBUG: k_value = {k_value}")
                # data_lock zaten alınmış, direkt erişim
                arm_data = dict(battery_data_ram.get(arm, {}))
                print(f"DEBUG: arm_data = {arm_data}")
                if arm_data and k_value in arm_data:
                    print(f"DEBUG: k={k_value} verisi bulundu!")
                    # Her batarya için 7 veri tipi
                    for data_type in range(5, 12):  # 5-11 (gerilim, soc, rint, soh, ntc1, ntc2, ntc3)
                        print(f"DEBUG: current_index={current_index}, start_index={start_index}, len(result)={len(result)}, quantity={quantity}")
                        if current_index >= start_index and len(result) < quantity:
                            print(f"DEBUG: BATARYA IF BLOĞU GİRİLDİ!")
                            if data_type == 5:  # Gerilim
                                value = arm_data[k_value].get(10, {}).get('value', 0)  # dtype=10 (Gerilim)
                            elif data_type == 6:  # SOC
                                value = arm_data[k_value].get(11, {}).get('value', 0)  # dtype=11 (SOC)
                            elif data_type == 7:  # RIMT
                                value = arm_data[k_value].get(12, {}).get('value', 0)  # dtype=12 (RIMT)
                            elif data_type == 8:  # SOH
                                value = arm_data[k_value].get(126, {}).get('value', 0)  # dtype=126 (SOH)
                            elif data_type == 9:  # NTC1
                                value = arm_data[k_value].get(13, {}).get('value', 0)  # dtype=13 (NTC1)
                            elif data_type == 10:  # NTC2
                                value = arm_data[k_value].get(14, {}).get('value', 0)  # dtype=14 (NTC2)
                            elif data_type == 11:  # NTC3
                                value = arm_data[k_value].get(15, {}).get('value', 0)  # dtype=15 (NTC3)
                            else:
                                value = 0
                            result.append(float(value) if value else 0.0)
                            print(f"DEBUG: current_index={current_index}, arm={arm}, bat={battery_num}, data_type={data_type}, value={value}")
                        else:
                            print(f"DEBUG: BATARYA IF BLOĞU GİRİLMEDİ!")
                        current_index += 1
                        
                        if len(result) >= quantity:
                            break
                else:
                    print(f"DEBUG: k={k_value} verisi bulunamadı!")
                            
                if len(result) >= quantity:
                    break
                    
            if len(result) >= quantity:
                break
                
        print(f"DEBUG: Sonuç: {result}")
        return result

def get_alarm_data_by_index(start_index, quantity):
    """Alarm verilerini indeksine göre döndür"""
    with alarm_lock:
        result = []
        current_index = start_index
        
        print(f"DEBUG: get_alarm_data_by_index start={start_index}, quantity={quantity}")
        
        # Aralık kontrolü (5001-8376)
        if start_index < 5001 or start_index > 8376:
            print(f"DEBUG: Geçersiz alarm aralığı! start_index={start_index} (5001-8376 arası olmalı)")
            return [0] * quantity
        
        # Hangi kol aralığında olduğunu belirle
        if 5001 <= start_index <= 5844:
            target_arm = 1
            arm_start = 5001
        elif 5845 <= start_index <= 6688:
            target_arm = 2
            arm_start = 5845
        elif 6689 <= start_index <= 7532:
            target_arm = 3
            arm_start = 6689
        elif 7533 <= start_index <= 8376:
            target_arm = 4
            arm_start = 7533
        else:
            print(f"DEBUG: Geçersiz alarm aralığı! start_index={start_index}")
            return [0] * quantity
        
        print(f"DEBUG: Hedef kol: {target_arm}, aralık: {arm_start}-{arm_start+843}")
        
        # Kol alarmları (4 adet)
        for alarm_type in range(1, 5):  # 1-4
            if current_index >= start_index and len(result) < quantity:
                alarm_value = alarm_ram.get(target_arm, {}).get(0, {}).get(alarm_type, False)
                result.append(1 if alarm_value else 0)
                print(f"DEBUG: Kol {target_arm} alarm {alarm_type}: {alarm_value}")
            current_index += 1
            
            if len(result) >= quantity:
                break
        
        # Batarya alarmları (120 × 7 = 840 adet)
        battery_count = arm_slave_counts_ram.get(target_arm, 0)
        for battery_num in range(1, battery_count + 1):
            for alarm_type in range(1, 8):  # 1-7
                if current_index >= start_index and len(result) < quantity:
                    alarm_value = alarm_ram.get(target_arm, {}).get(battery_num, {}).get(alarm_type, False)
                    result.append(1 if alarm_value else 0)
                    print(f"DEBUG: Kol {target_arm} Batarya {battery_num} alarm {alarm_type}: {alarm_value}")
                current_index += 1
                
                if len(result) >= quantity:
                    break
            
            if len(result) >= quantity:
                break
        
        # Eksik veriler için 0 ekle
        while len(result) < quantity:
            result.append(0)
        
        print(f"DEBUG: Alarm sonuç: {result}")
        return result

def initialize_alarm_ram():
    """Alarm RAM yapısını başlat"""
    with alarm_lock:
        for arm in range(1, 5):
            alarm_ram[arm] = {}
            # Kol alarmları (0 = kol)
            alarm_ram[arm][0] = {1: False, 2: False, 3: False, 4: False}
            # Batarya alarmları (sadece mevcut batarya sayısı kadar)
            battery_count = arm_slave_counts_ram.get(arm, 0)
            for battery in range(1, battery_count + 1):
                alarm_ram[arm][battery] = {1: False, 2: False, 3: False, 4: False, 5: False, 6: False, 7: False}
        print(f"DEBUG: Alarm RAM yapısı başlatıldı - Kol 1: {arm_slave_counts_ram[1]}, Kol 2: {arm_slave_counts_ram[2]}, Kol 3: {arm_slave_counts_ram[3]}, Kol 4: {arm_slave_counts_ram[4]} batarya")

def initialize_status_ram():
    """Status RAM yapısını başlat"""
    with status_lock:
        for arm in range(1, 5):
            status_ram[arm] = {}
            # Kol statusu (0 = kol)
            status_ram[arm][0] = True  # Kol varsayılan olarak veri var
            # Batarya statusları (sadece mevcut batarya sayısı kadar)
            battery_count = arm_slave_counts_ram.get(arm, 0)
            for battery in range(1, battery_count + 1):
                status_ram[arm][battery] = True  # Başlangıçta veri var
        print(f"DEBUG: Status RAM yapısı başlatıldı - Kol 1: {arm_slave_counts_ram.get(1, 0)}, Kol 2: {arm_slave_counts_ram.get(2, 0)}, Kol 3: {arm_slave_counts_ram.get(3, 0)}, Kol 4: {arm_slave_counts_ram.get(4, 0)} batarya")

def load_trap_targets_to_ram():
    """Trap hedeflerini veritabanından RAM'e yükle"""
    try:
        with db_lock:
            targets = db.get_trap_targets()
            with trap_targets_lock:
                trap_targets_ram.clear()
                trap_targets_ram.extend(targets)
            print(f"✓ {len(targets)} trap hedefi RAM'e yüklendi")
    except Exception as e:
        print(f"❌ Trap hedefleri yüklenirken hata: {e}")

def update_alarm_ram(arm, battery, alarm_type, status):
    """Alarm RAM'ini güncelle"""
    with alarm_lock:
        if arm in alarm_ram and battery in alarm_ram[arm] and alarm_type in alarm_ram[arm][battery]:
            # Önceki durumu kontrol et
            previous_status = alarm_ram[arm][battery][alarm_type]
            alarm_ram[arm][battery][alarm_type] = status
            print(f"DEBUG: Alarm güncellendi - Kol {arm}, Batarya {battery}, Alarm {alarm_type}: {status}")
            
            # Durum değiştiyse trap gönder
            if previous_status != status:
                send_snmp_trap(arm, battery, alarm_type, status)

def check_alarm_conditions(arm, battery, data):
    """Bu fonksiyon kaldırıldı - alarmlar error_msb/error_lsb değerlerine göre işleniyor"""
    pass

def modbus_tcp_server():
    """Modbus TCP sunucu thread'i"""
    print("Modbus TCP sunucu başlatılıyor...")
    
    try:
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_socket.bind(('0.0.0.0', 1502))
        server_socket.listen(5)
        
        print(f"Modbus TCP Server başlatıldı: 0.0.0.0:1502")
        
        while True:
            try:
                client_socket, client_address = server_socket.accept()
                print(f"Yeni bağlantı: {client_address}")
                
                # Her bağlantı için ayrı thread
                client_thread = threading.Thread(
                    target=handle_modbus_client,
                    args=(client_socket, client_address),
                    daemon=True
                )
                client_thread.start()
                
            except Exception as e:
                print(f"Modbus TCP server hatası: {e}")
                continue
                
    except Exception as e:
        print(f"Modbus TCP server başlatma hatası: {e}")

def handle_modbus_client(client_socket, client_address):
    """Modbus TCP client isteklerini işle"""
    try:
        while True:
            # Modbus TCP frame oku
            data = client_socket.recv(1024)
            if not data:
                break
            
            if len(data) < 8:  # Minimum Modbus TCP frame boyutu
                continue
            
            # Modbus TCP frame parse et
            transaction_id = struct.unpack('>H', data[0:2])[0]
            protocol_id = struct.unpack('>H', data[2:4])[0]
            length = struct.unpack('>H', data[4:6])[0]
            unit_id = data[6]
            function_code = data[7]
            
            print(f"Modbus TCP isteği: Transaction={transaction_id}, Function={function_code}, Unit={unit_id}")
            
            # Function code 3 (Read Holding Registers) işle
            if function_code == 3:
                if len(data) >= 12:
                    start_address = struct.unpack('>H', data[8:10])[0]
                    quantity = struct.unpack('>H', data[10:12])[0]
                    
                    response = handle_read_holding_registers(transaction_id, unit_id, start_address, quantity)
                    if response:
                        client_socket.send(response)
            
            # Function code 4 (Read Input Registers) işle
            elif function_code == 4:
                if len(data) >= 12:
                    start_address = struct.unpack('>H', data[8:10])[0]
                    quantity = struct.unpack('>H', data[10:12])[0]
                    
                    response = handle_read_input_registers(transaction_id, unit_id, start_address, quantity)
                    if response:
                        client_socket.send(response)
            
    except Exception as e:
        print(f"Client {client_address} işleme hatası: {e}")
    finally:
        client_socket.close()
        print(f"Client {client_address} bağlantısı kapatıldı")

def handle_read_holding_registers(transaction_id, unit_id, start_address, quantity):
    """Read Holding Registers (Function Code 3) işle"""
    try:
        print(f"DEBUG: start_address={start_address}, quantity={quantity}")
        
        # Batarya verilerini hazırla
        registers = []
        
        # Start address'e göre veri döndür
        if start_address == 0:  # Armslavecounts verileri
            # Register 0'dan başlayarak armslavecounts doldur
            registers = []
            with data_lock:
                for i in range(quantity):
                    if i < 4:  # İlk 4 register armslavecounts
                        arm_num = i + 1
                        registers.append(float(arm_slave_counts_ram.get(arm_num, 0)))
                    else:
                        registers.append(0.0)  # Boş register
            print(f"DEBUG: Armslavecounts verileri: {registers}")
        elif 5001 <= start_address <= 5844:  # Alarm verileri
            # Alarm verilerini döndür
            registers = get_alarm_data_by_index(start_address, quantity)
        elif start_address >= 1:  # Dinamik veri okuma
            # Dinamik veri sistemi kullan
            registers = get_dynamic_data_by_index(start_address, quantity)
        
        # Modbus TCP response hazırla
        if registers:
            # Response header
            response = struct.pack('>H', transaction_id)  # Transaction ID
            response += struct.pack('>H', 0)  # Protocol ID
            response += struct.pack('>H', 2 + 1 + 2 * len(registers))  # Length
            response += struct.pack('B', unit_id)  # Unit ID
            response += struct.pack('B', 3)  # Function Code
            
            # Byte count
            response += struct.pack('B', 2 * len(registers))
            
            # Register values
            for value in registers:
                # Float'ı 16-bit integer'a çevir (basit scaling)
                int_value = int(value * 100)  # 2 decimal place precision
                response += struct.pack('>H', int_value)
            
            print(f"DEBUG: Response hazırlandı, {len(registers)} register")
            return response
        
        return None
        
    except Exception as e:
        print(f"Read holding registers hatası: {e}")
        return None

def handle_read_input_registers(transaction_id, unit_id, start_address, quantity):
    """Read Input Registers (Function Code 4) işle"""
    try:
        print(f"DEBUG: Input registers start_address={start_address}, quantity={quantity}")
        
        # Input registers için de aynı mantık
        registers = []
        
        if start_address == 0:  # Armslavecounts verileri
            with data_lock:
                for i in range(quantity):
                    if i < 4:
                        arm_num = i + 1
                        registers.append(float(arm_slave_counts_ram.get(arm_num, 0)))
                    else:
                        registers.append(0.0)
        elif 5001 <= start_address <= 5844:  # Alarm verileri
            registers = get_alarm_data_by_index(start_address, quantity)
        elif start_address >= 1:
            registers = get_dynamic_data_by_index(start_address, quantity)
        
        # Modbus TCP response hazırla
        if registers:
            response = struct.pack('>H', transaction_id)
            response += struct.pack('>H', 0)
            response += struct.pack('>H', 2 + 1 + 2 * len(registers))
            response += struct.pack('B', unit_id)
            response += struct.pack('B', 4)  # Function Code 4
            
            response += struct.pack('B', 2 * len(registers))
            
            for value in registers:
                int_value = int(value * 100)
                response += struct.pack('>H', int_value)
            
            print(f"DEBUG: Input registers response hazırlandı, {len(registers)} register")
            return response
        
        return None
        
    except Exception as e:
        print(f"Read input registers hatası: {e}")
        return None

def get_dynamic_data_by_index(start_index, quantity):
    """Dinamik veri indeksine göre veri döndür"""
    with data_lock:
        result = []
        current_index = start_index  # start_index'ten başla
        
        print(f"DEBUG: get_dynamic_data_by_index start={start_index}, quantity={quantity}")
        print(f"DEBUG: arm_slave_counts_ram = {arm_slave_counts_ram}")
        
        # Aralık kontrolü
        if start_index < 1001 or start_index > 4994:
            print(f"DEBUG: Geçersiz aralık! start_index={start_index} (1001-4994 arası olmalı)")
            return [0.0] * quantity
        
        # Hangi kol aralığında olduğunu belirle
        if 1001 <= start_index <= 1994:
            target_arm = 1
            arm_start = 1001
        elif 2001 <= start_index <= 2994:
            target_arm = 2
            arm_start = 2001
        elif 3001 <= start_index <= 3994:
            target_arm = 3
            arm_start = 3001
        elif 4001 <= start_index <= 4994:
            target_arm = 4
            arm_start = 4001
        else:
            print(f"DEBUG: Geçersiz aralık! start_index={start_index}")
            return [0.0] * quantity
        
        print(f"DEBUG: Hedef kol: {target_arm}, aralık: {arm_start}-{arm_start+993}")
        
        # Sadece hedef kolu işle
        for arm in range(1, 5):  # Kol 1-4
            if arm != target_arm:
                continue  # Sadece hedef kolu işle
                
            print(f"DEBUG: Kol {arm} işleniyor...")
            print(f"DEBUG: battery_data_ram[{arm}] = {battery_data_ram.get(arm, 'YOK')}")
            
            # Kol verileri (akım, nem, sıcaklık, sıcaklık2)
            for data_type in range(1, 5):
                print(f"DEBUG: current_index={current_index}, start_index={start_index}, len(result)={len(result)}, quantity={quantity}")
                if current_index >= start_index and len(result) < quantity:
                    print(f"DEBUG: IF BLOĞU GİRİLDİ!")
                    print(f"DEBUG: get_battery_data_ram({arm}) çağrılıyor...")
                    try:
                        # data_lock zaten alınmış, direkt erişim
                        arm_data = dict(battery_data_ram.get(arm, {}))
                        print(f"DEBUG: arm_data = {arm_data}")
                        print(f"DEBUG: arm_data type = {type(arm_data)}")
                    except Exception as e:
                        print(f"DEBUG: HATA! arm_data okuma hatası: {e}")
                        arm_data = None
                    if arm_data and 2 in arm_data:  # k=2 (kol verisi)
                        print(f"DEBUG: k=2 verisi bulundu!")
                        if data_type == 1:  # Akım
                            value = arm_data[2].get(10, {}).get('value', 0)  # dtype=10 (A)
                        elif data_type == 2:  # Nem
                            value = arm_data[2].get(11, {}).get('value', 0)  # dtype=11 (B)
                        elif data_type == 3:  # Sıcaklık
                            value = arm_data[2].get(12, {}).get('value', 0)  # dtype=12 (C)
                        elif data_type == 4:  # Sıcaklık2
                            value = arm_data[2].get(13, {}).get('value', 0)  # dtype=13 (D)
                        else:
                            value = 0
                        result.append(float(value) if value else 0.0)
                        print(f"DEBUG: current_index={current_index}, data_type={data_type}, value={value}")
                    else:
                        print(f"DEBUG: k=2 verisi bulunamadı!")
                        result.append(0.0)
                        print(f"DEBUG: current_index={current_index}, data_type={data_type}, value=0.0 (veri yok)")
                else:
                    print(f"DEBUG: IF BLOĞU GİRİLMEDİ!")
                    result.append(0.0)
                    print(f"DEBUG: current_index={current_index}, data_type={data_type}, value=0.0 (IF girmedi)")
                current_index += 1
                
                if len(result) >= quantity:
                    break
                    
            if len(result) >= quantity:
                break
                
            # Batarya verileri
            battery_count = arm_slave_counts_ram.get(arm, 0)
            print(f"DEBUG: Kol {arm} batarya sayısı: {battery_count}")
            for battery_num in range(1, battery_count + 1):
                print(f"DEBUG: Batarya {battery_num} işleniyor...")
                k_value = battery_num + 2  # k=3,4,5,6...
                print(f"DEBUG: k_value = {k_value}")
                # data_lock zaten alınmış, direkt erişim
                arm_data = dict(battery_data_ram.get(arm, {}))
                print(f"DEBUG: arm_data = {arm_data}")
                if arm_data and k_value in arm_data:
                    print(f"DEBUG: k={k_value} verisi bulundu!")
                    # Her batarya için 7 veri tipi
                    for data_type in range(5, 12):  # 5-11 (gerilim, soc, rint, soh, ntc1, ntc2, ntc3)
                        print(f"DEBUG: current_index={current_index}, start_index={start_index}, len(result)={len(result)}, quantity={quantity}")
                        if current_index >= start_index and len(result) < quantity:
                            print(f"DEBUG: BATARYA IF BLOĞU GİRİLDİ!")
                            if data_type == 5:  # Gerilim
                                value = arm_data[k_value].get(10, {}).get('value', 0)  # dtype=10 (Gerilim)
                            elif data_type == 6:  # SOC
                                value = arm_data[k_value].get(11, {}).get('value', 0)  # dtype=11 (SOC)
                            elif data_type == 7:  # RIMT
                                value = arm_data[k_value].get(12, {}).get('value', 0)  # dtype=12 (RIMT)
                            elif data_type == 8:  # SOH
                                value = arm_data[k_value].get(126, {}).get('value', 0)  # dtype=126 (SOH)
                            elif data_type == 9:  # NTC1
                                value = arm_data[k_value].get(13, {}).get('value', 0)  # dtype=13 (NTC1)
                            elif data_type == 10:  # NTC2
                                value = arm_data[k_value].get(14, {}).get('value', 0)  # dtype=14 (NTC2)
                            elif data_type == 11:  # NTC3
                                value = arm_data[k_value].get(15, {}).get('value', 0)  # dtype=15 (NTC3)
                            else:
                                value = 0
                            result.append(float(value) if value else 0.0)
                            print(f"DEBUG: current_index={current_index}, arm={arm}, bat={battery_num}, data_type={data_type}, value={value}")
                        else:
                            print(f"DEBUG: BATARYA IF BLOĞU GİRİLMEDİ!")
                        current_index += 1
                        
                        if len(result) >= quantity:
                            break
                else:
                    print(f"DEBUG: k={k_value} verisi bulunamadı!")
                            
                if len(result) >= quantity:
                    break
                    
            if len(result) >= quantity:
                break
                
        print(f"DEBUG: Sonuç: {result}")
        return result

def get_alarm_data_by_index(start_address, quantity):
    """Alarm verilerini indekse göre döndür"""
    try:
        print(f"DEBUG: get_alarm_data_by_index start_address={start_address}, quantity={quantity}")
        
        result = []
        current_address = start_address
        
        # Alarm adres aralıkları: 5001-5844
        # 5001-5004: Kol 1 alarmları (akım, nem, ortam sıcaklığı, kol sıcaklığı)
        # 5005-5844: Batarya alarmları (7 alarm türü x 120 batarya x 4 kol)
        
        for i in range(quantity):
            if current_address >= 5001 and current_address <= 5844:
                # Kol alarmları (5001-5004)
                if 5001 <= current_address <= 5004:
                    arm = 1
                    alarm_type = current_address - 5000  # 1, 2, 3, 4
                    
                    with data_lock:
                        if arm in alarm_ram and 0 in alarm_ram[arm]:
                            alarm_status = alarm_ram[arm][0].get(alarm_type, False)
                            result.append(1.0 if alarm_status else 0.0)
                        else:
                            result.append(0.0)
                
                # Batarya alarmları (5005-5844)
                elif 5005 <= current_address <= 5844:
                    # Hesaplama: (current_address - 5005) / 7 = batarya numarası
                    battery_offset = current_address - 5005
                    battery_num = (battery_offset // 7) + 1
                    alarm_type = (battery_offset % 7) + 1
                    
                    # Hangi kola ait olduğunu hesapla
                    arm = 1  # Basit hesaplama, gerçekte daha karmaşık olabilir
                    
                    with data_lock:
                        if arm in alarm_ram and battery_num in alarm_ram[arm]:
                            alarm_status = alarm_ram[arm][battery_num].get(alarm_type, False)
                            result.append(1.0 if alarm_status else 0.0)
                        else:
                            result.append(0.0)
                else:
                    result.append(0.0)
            else:
                result.append(0.0)
            
            current_address += 1
            
        print(f"DEBUG: Alarm sonuç: {result}")
        return result
        
    except Exception as e:
        print(f"get_alarm_data_by_index hatası: {e}")
        return []

def get_snmp_data(oid):
    """SNMP OID'ine göre veri döndür"""
    try:
        # OID'yi parse et
        oid_parts = oid.split('.')
        
        # Kol alarmları: .7.0.1-.7.0.4
        if len(oid_parts) >= 4 and oid_parts[-3] == '7' and oid_parts[-2] == '0':
            arm_num = int(oid_parts[-4])
            alarm_type = int(oid_parts[-1])
            
            if 1 <= arm_num <= 4 and 1 <= alarm_type <= 4:
                with alarm_lock:
                    alarm_value = alarm_ram.get(arm_num, {}).get(0, {}).get(alarm_type, False)
                    return 1 if alarm_value else 0
        
        # Batarya alarmları: .7.{BATTERY}.1-.7.{BATTERY}.7
        elif len(oid_parts) >= 4 and oid_parts[-3] == '7':
            arm_num = int(oid_parts[-4])
            battery_num = int(oid_parts[-2])
            alarm_type = int(oid_parts[-1])
            
            if 1 <= arm_num <= 4 and 1 <= battery_num <= 120 and 1 <= alarm_type <= 7:
                with alarm_lock:
                    alarm_value = alarm_ram.get(arm_num, {}).get(battery_num, {}).get(alarm_type, False)
                    return 1 if alarm_value else 0
        
        # Diğer OID'ler için 0 döndür
        return 0
        
    except Exception as e:
        print(f"❌ SNMP veri alma hatası: {e}")
        return 0

def send_snmp_trap(arm, battery, alarm_type, status):
    """SNMP trap gönder"""
    try:
        with trap_targets_lock:
            active_targets = [target for target in trap_targets_ram if target['is_active']]
        
        if not active_targets:
            print("⚠️ Aktif trap hedefi yok, trap gönderilmedi")
            return
        
        # Trap OID'ini oluştur
        if battery == 0:  # Kol alarmı
            trap_oid = f'1.3.6.1.4.1.1001.{arm}.7.0.{alarm_type}'
            trap_name = f"Kol {arm} Alarm {alarm_type}"
        else:  # Batarya alarmı
            trap_oid = f'1.3.6.1.4.1.1001.{arm}.7.{battery}.{alarm_type}'
            trap_name = f"Kol {arm} Batarya {battery} Alarm {alarm_type}"
        
        # Trap mesajı
        status_text = "AKTIF" if status else "ÇÖZÜLDÜ"
        trap_message = f"{trap_name}: {status_text}"
        
        print(f"📤 Trap gönderiliyor: {trap_message}")
        
        # Her aktif hedefe trap gönder
        for target in active_targets:
            try:
                send_single_trap(target['ip_address'], target['port'], trap_oid, trap_message)
                print(f"✅ Trap gönderildi: {target['name']} ({target['ip_address']}:{target['port']})")
            except Exception as e:
                print(f"❌ Trap gönderme hatası {target['name']}: {e}")
                
    except Exception as e:
        print(f"❌ Trap gönderme genel hatası: {e}")

def send_single_trap(target_ip, target_port, trap_oid, message):
    """Tek bir trap gönder"""
    try:
        # SNMP Trap gönder
        errorIndication, errorStatus, errorIndex, varBinds = next(
            sendNotification(
                SnmpEngine(),
                CommunityData('public'),
                UdpTransportTarget((target_ip, target_port)),
                ContextData(),
                'trap',
                NotificationType(
                    ObjectIdentity(trap_oid),
                    [ObjectType(ObjectIdentity('1.3.6.1.4.1.1001.999.1.1'), OctetString(message))]
                )
            )
        )
        
        if errorIndication:
            print(f"❌ Trap hatası: {errorIndication}")
        else:
            print(f"✅ Trap başarılı: {target_ip}")
            
    except Exception as e:
        print(f"❌ Trap gönderme hatası: {e}")

def snmp_server():
    """SNMP sunucu thread'i"""
    print("SNMP sunucu başlatılıyor...")
    
    try:
        import asyncio
        
        # Yeni event loop oluştur
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        # SNMP Engine oluştur
        snmp_engine = engine.SnmpEngine()
        
        # UDP transport
        config.add_transport(
            snmp_engine,
            udp.DOMAIN_NAME,
            udp.UdpTransport().open_server_mode(('0.0.0.0', 1161))
        )
        
        # SNMPv2c community
        config.add_v1_system(snmp_engine, 'my-area', 'public')
        
        # VACM ayarları
        config.add_vacm_user(snmp_engine, 2, 'my-area', 'noAuthNoPriv', (1, 3, 6, 5))
        
        # SNMP Context
        snmp_context = context.SnmpContext(snmp_engine)
        
        # MIB Builder
        mib_builder = snmp_context.get_mib_instrum().get_mib_builder()
        
        # MIB Objects oluştur
        MibScalar, MibScalarInstance = mib_builder.import_symbols(
            "SNMPv2-SMI", "MibScalar", "MibScalarInstance"
        )
        
        class ModbusRAMMibScalarInstance(MibScalarInstance):
            """Modbus TCP Server RAM sistemi ile MIB Instance"""
            def getValue(self, name, **context):
                oid = '.'.join([str(x) for x in name])
                print(f"🔍 SNMP getValue çağrıldı: {oid}")
                
                # Sistem bilgileri
                if oid == "1.3.6.5.1.0":
                    print(f"✅ Sistem OID: {oid} - Python bilgisi")
                    return self.getSyntax().clone(
                        f"Python {sys.version} running on a {sys.platform} platform"
                    )
                elif oid == "1.3.6.5.2.0":  # totalBatteryCount
                    total_count = sum(arm_slave_counts_ram.values())
                    print(f"✅ Sistem OID: {oid} - Batarya sayısı: {total_count}")
                    return self.getSyntax().clone(str(total_count))
                elif oid == "1.3.6.5.3.0":  # totalArmCount
                    active_arms = sum(1 for count in arm_slave_counts_ram.values() if count > 0)
                    print(f"✅ Sistem OID: {oid} - Kol sayısı: {active_arms}")
                    return self.getSyntax().clone(str(active_arms))
                elif oid == "1.3.6.5.4.0":  # systemStatus
                    print(f"✅ Sistem OID: {oid} - Sistem durumu")
                    return self.getSyntax().clone("1")
                elif oid == "1.3.6.5.5.0":  # lastUpdateTime
                    print(f"✅ Sistem OID: {oid} - Son güncelleme")
                    return self.getSyntax().clone(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                elif oid == "1.3.6.5.6.0":  # dataCount
                    total_data = 0
                    with data_lock:
                        for arm_data in battery_data_ram.values():
                            for battery_data in arm_data.values():
                                total_data += len(battery_data)
                    print(f"✅ Sistem OID: {oid} - Veri sayısı: {total_data}")
                    return self.getSyntax().clone(str(total_data))
                elif oid == "1.3.6.5.7.0":  # arm1SlaveCount
                    count = arm_slave_counts_ram.get(1, 0)
                    print(f"✅ Sistem OID: {oid} - Kol 1 batarya sayısı: {count}")
                    return self.getSyntax().clone(str(count))
                elif oid == "1.3.6.5.8.0":  # arm2SlaveCount
                    count = arm_slave_counts_ram.get(2, 0)
                    print(f"✅ Sistem OID: {oid} - Kol 2 batarya sayısı: {count}")
                    return self.getSyntax().clone(str(count))
                elif oid == "1.3.6.5.9.0":  # arm3SlaveCount
                    count = arm_slave_counts_ram.get(3, 0)
                    print(f"✅ Sistem OID: {oid} - Kol 3 batarya sayısı: {count}")
                    return self.getSyntax().clone(str(count))
                elif oid == "1.3.6.5.10.0":  # arm4SlaveCount
                    count = arm_slave_counts_ram.get(4, 0)
                    print(f"✅ Sistem OID: {oid} - Kol 4 batarya sayısı: {count}")
                    return self.getSyntax().clone(str(count))
                else:
                    # Kol verileri - 1.3.6.1.4.1.1001.arm.dtype veya 1.3.6.1.4.1.1001.arm.dtype.0
                    if oid.startswith("1.3.6.1.4.1.1001."):
                        parts = oid.split('.')
                        if len(parts) >= 9:  # En az 9 parça olmalı (1.3.6.1.4.1.1001.arm.dtype)
                            arm = int(parts[7])
                            dtype = int(parts[8])
                            
                            with data_lock:
                                if arm in battery_data_ram and 2 in battery_data_ram[arm]:
                                    value = battery_data_ram[arm][2].get(dtype, 0)
                                    return self.getSyntax().clone(str(value))
                                else:
                                    return self.getSyntax().clone("0")
                    
                    # Batarya verileri - 1.3.6.1.4.1.1001.arm.5.k.dtype veya 1.3.6.1.4.1.1001.arm.5.k.dtype.0
                    elif oid.startswith("1.3.6.1.4.1.1001."):
                        parts = oid.split('.')
                        print(f"🔍 SNMP Batarya OID Parsing: {oid} -> parts={parts}")
                        # Hem .0'lı hem .0'sız isteklere cevap ver
                        if len(parts) >= 11:  # En az 11 parça olmalı (1.3.6.1.4.1.1001.arm.5.k.dtype)
                            arm = int(parts[7])
                            if parts[8] == "5":  # Batarya verileri
                                k = int(parts[9])
                                dtype = int(parts[10])
                                print(f"🔍 SNMP Parsed: arm={arm}, k={k}, dtype={dtype}")
                                
                                with data_lock:
                                    if arm in battery_data_ram and k in battery_data_ram[arm]:
                                        print(f"🔍 RAM'de veri var: arm={arm}, k={k}")
                                        print(f"🔍 RAM verisi: {battery_data_ram[arm][k]}")
                                        # 1-7 sıralama: dtype 1-7 arası olmalı
                                        if 1 <= dtype <= 7:
                                            value_data = battery_data_ram[arm][k].get(dtype, {})
                                            if isinstance(value_data, dict):
                                                value = value_data.get('value', 0)
                                            else:
                                                value = value_data
                                            print(f"✅ Batarya OID: {oid} - Arm={arm}, k={k}, dtype={dtype}, value={value}")
                                            return self.getSyntax().clone(str(value))
                                        else:
                                            print(f"❌ Batarya OID: {oid} - dtype={dtype} 1-7 aralığında değil")
                                            return self.getSyntax().clone("0")
                                    else:
                                        print(f"🔍 SNMP Hata: arm={arm}, k={k} RAM'de bulunamadı")
                                        return self.getSyntax().clone("0")
                    
                    # Status verileri - 1.3.6.1.4.1.1001.arm.6.battery veya 1.3.6.1.4.1.1001.arm.6.battery.0
                    elif oid.startswith("1.3.6.1.4.1.1001."):
                        parts = oid.split('.')
                        if len(parts) >= 10:  # En az 10 parça olmalı (1.3.6.1.4.1.1001.arm.6.battery)
                            arm = int(parts[7])
                            if parts[8] == "6":  # Status verileri
                                battery = int(parts[9])
                                
                                with status_lock:
                                    if arm in status_ram and battery in status_ram[arm]:
                                        # Status: True=1, False=0
                                        has_data = status_ram[arm][battery]
                                        return self.getSyntax().clone("1" if has_data else "0")
                                    else:
                                        return self.getSyntax().clone("0")
                    
                    # Alarm verileri - 1.3.6.1.4.1.1001.arm.7.battery.alarm_type veya 1.3.6.1.4.1.1001.arm.7.battery.alarm_type.0
                    elif oid.startswith("1.3.6.1.4.1.1001."):
                        parts = oid.split('.')
                        if len(parts) >= 11:  # En az 11 parça olmalı (1.3.6.1.4.1.1001.arm.7.battery.alarm_type)
                            arm = int(parts[7])
                            if parts[8] == "7":  # Alarm verileri
                                battery = int(parts[9])
                                alarm_type = int(parts[10])
                                
                                with data_lock:
                                    if arm in alarm_ram and battery in alarm_ram[arm]:
                                        alarm_status = alarm_ram[arm][battery].get(alarm_type, False)
                                        return self.getSyntax().clone("1" if alarm_status else "0")
                                    else:
                                        return self.getSyntax().clone("0")
                    
                    return self.getSyntax().clone("0")
        
        # MIB Objects oluştur
        mib_builder.export_symbols(
            "__BATTERY_MIB_SYSTEM",
            MibScalar((1, 3, 6, 5, 1), v2c.OctetString()),
            ModbusRAMMibScalarInstance((1, 3, 6, 5, 1), (0,), v2c.OctetString()),
            
            MibScalar((1, 3, 6, 5, 2), v2c.OctetString()),
            ModbusRAMMibScalarInstance((1, 3, 6, 5, 2), (0,), v2c.OctetString()),
            
            MibScalar((1, 3, 6, 5, 3), v2c.OctetString()),
            ModbusRAMMibScalarInstance((1, 3, 6, 5, 3), (0,), v2c.OctetString()),
            
            MibScalar((1, 3, 6, 5, 4), v2c.OctetString()),
            ModbusRAMMibScalarInstance((1, 3, 6, 5, 4), (0,), v2c.OctetString()),
            
            MibScalar((1, 3, 6, 5, 5), v2c.OctetString()),
            ModbusRAMMibScalarInstance((1, 3, 6, 5, 5), (0,), v2c.OctetString()),
            
            MibScalar((1, 3, 6, 5, 6), v2c.OctetString()),
            ModbusRAMMibScalarInstance((1, 3, 6, 5, 6), (0,), v2c.OctetString()),
            
            # Armslavecounts OID'leri
            MibScalar((1, 3, 6, 5, 7), v2c.OctetString()),
            ModbusRAMMibScalarInstance((1, 3, 6, 5, 7), (0,), v2c.OctetString()),
            
            MibScalar((1, 3, 6, 5, 8), v2c.OctetString()),
            ModbusRAMMibScalarInstance((1, 3, 6, 5, 8), (0,), v2c.OctetString()),
            
            MibScalar((1, 3, 6, 5, 9), v2c.OctetString()),
            ModbusRAMMibScalarInstance((1, 3, 6, 5, 9), (0,), v2c.OctetString()),
            
            MibScalar((1, 3, 6, 5, 10), v2c.OctetString()),
            ModbusRAMMibScalarInstance((1, 3, 6, 5, 10), (0,), v2c.OctetString()),
        )
        
        # Batarya verileri için OID'ler oluştur (MIB yapısına uygun)
        print(f"🔧 SNMP MIB Export başlıyor...")
        for arm in range(1, 5):
            for k in range(3, 8):  # 3-7 arası batarya numaraları (k=2 arm verisi)
                # 1-7 sıralama: 1=Gerilim, 2=SOC, 3=RIMT, 4=SOH, 5=NTC1, 6=NTC2, 7=NTC3
                for dtype in range(1, 8):  # 1-7 arası dtype'lar
                    oid = (1, 3, 6, 1, 4, 1, 1001, arm, 5, k, dtype)
                    oid_str = '.'.join(map(str, oid))
                    try:
                        mib_scalar = MibScalar(oid, v2c.OctetString())
                        mib_instance = ModbusRAMMibScalarInstance(oid, (0,), v2c.OctetString())
                        mib_builder.export_symbols(
                            f"__BATTERY_MIB_{arm}_{k}_{dtype}",
                            mib_scalar,
                            mib_instance,
                        )
                    except Exception as e:
                        print(f"❌ Batarya OID hatası: Arm={arm}, k={k}, dtype={dtype} - {e}")
        print(f"🔧 SNMP MIB Export tamamlandı!")
        
        # Alarm verileri için OID'ler oluştur
        for arm in range(1, 5):
            # Kol alarmları (0 = kol alarmı)
            for alarm_type in range(1, 5):  # 1-4 arası alarm türleri
                oid = (1, 3, 6, 5, 7, arm, 0, alarm_type)
                mib_builder.export_symbols(
                    f"__ALARM_MIB_{arm}_0_{alarm_type}",
                    MibScalar(oid, v2c.OctetString()),
                    ModbusRAMMibScalarInstance(oid, (0,), v2c.OctetString()),
                )
            
            # Batarya alarmları
            for battery in range(1, 8):  # 1-7 arası batarya numaraları
                for alarm_type in range(1, 8):  # 1-7 arası alarm türleri
                    oid = (1, 3, 6, 5, 7, arm, battery, alarm_type)
                    mib_builder.export_symbols(
                        f"__ALARM_MIB_{arm}_{battery}_{alarm_type}",
                        MibScalar(oid, v2c.OctetString()),
                        ModbusRAMMibScalarInstance(oid, (0,), v2c.OctetString()),
                    )
        
        # SNMP Agent
        print(f"🔧 SNMP Agent oluşturuluyor...")
        try:
            snmp_agent = cmdrsp.GetCommandResponder(snmp_engine, snmp_context)
            print(f"✅ SNMP Agent oluşturuldu: {snmp_agent}")
        except Exception as e:
            print(f"❌ SNMP Agent oluşturma hatası: {e}")
            import traceback
            traceback.print_exc()
        
        # MIB yapısını debug et
        print("🔍 SNMP MIB yapısı debug:")
        mib_instrum = snmp_context.get_mib_instrum()
        mib_builder = mib_instrum.get_mib_builder()
        mib_symbols = mib_builder.mibSymbols
        print(f"  Toplam MIB sembolü: {len(mib_symbols)}")
        
        # Sadece batarya OID'lerini göster
        print("🔍 SNMP Batarya OID'leri:")
        for oid, obj in mib_builder.mibSymbols.items():
            oid_str = '.'.join(map(str, oid))
            if '1001' in oid_str and '.5.' in oid_str:
                print(f"  {oid_str}: {obj}")
        
        # Batarya OID'lerini kontrol et
        battery_oids = []
        for oid_tuple, obj in mib_builder.mibSymbols.items():
            oid_str = '.'.join(map(str, oid_tuple))
            if '1001' in oid_str and '.5.' in oid_str:
                battery_oids.append(oid_str)
        
        print(f"  Batarya OID'leri ({len(battery_oids)} adet):")
        for oid in sorted(battery_oids)[:10]:  # İlk 10'unu göster
            print(f"    {oid}")
        if len(battery_oids) > 10:
            print(f"    ... ve {len(battery_oids) - 10} tane daha")
        
        print("✅ SNMP sunucu başlatıldı - Port: 1161")
        print("📡 Port 1161'de dinleniyor...")
        print("=" * 50)
        print("SNMP Test OID'leri:")
        print("1.3.6.5.1.0  - Python bilgisi")
        print("1.3.6.5.2.0  - Batarya sayısı")
        print("1.3.6.5.3.0  - Kol sayısı")
        print("1.3.6.5.4.0  - Sistem durumu")
        print("1.3.6.5.5.0  - Son güncelleme zamanı")
        print("1.3.6.5.6.0  - Veri sayısı")
        print("1.3.6.5.7.0  - Kol 1 batarya sayısı")
        print("1.3.6.5.8.0  - Kol 2 batarya sayısı")
        print("1.3.6.5.9.0  - Kol 3 batarya sayısı")
        print("1.3.6.5.10.0 - Kol 4 batarya sayısı")
        print("")
        print("Kol verileri:")
        print("1.3.6.1.4.1.1001.1.1 - Kol 1 Akım")
        print("1.3.6.1.4.1.1001.1.2 - Kol 1 Nem")
        print("1.3.6.1.4.1.1001.1.3 - Kol 1 NTC1 (Sıcaklık)")
        print("1.3.6.1.4.1.1001.1.4 - Kol 1 NTC2 (Sıcaklık2)")
        print("1.3.6.1.4.1.1001.3.3 - Kol 3 NTC1 (Sıcaklık)")
        print("1.3.6.1.4.1.1001.3.4 - Kol 3 NTC2 (Sıcaklık2)")
        print("")
        print("Batarya verileri:")
        print("1.3.6.1.4.1.1001.1.5.1.10 - Kol 1 Batarya 1 Gerilim")
        print("1.3.6.1.4.1.1001.1.5.1.11 - Kol 1 Batarya 1 SOC")
        print("1.3.6.1.4.1.1001.1.5.1.12 - Kol 1 Batarya 1 RIMT")
        print("1.3.6.1.4.1.1001.1.5.1.126 - Kol 1 Batarya 1 SOH")
        print("1.3.6.1.4.1.1001.1.5.1.13 - Kol 1 Batarya 1 NTC1 (Modül Sıcaklığı)")
        print("1.3.6.1.4.1.1001.1.5.1.14 - Kol 1 Batarya 1 NTC2 (Pozitif Kutup Sıcaklığı)")
        print("1.3.6.1.4.1.1001.1.5.1.15 - Kol 1 Batarya 1 NTC3 (Negatif Kutup Sıcaklığı)")
        print("1.3.6.1.4.1.1001.3.5.2.126 - Kol 3 Batarya 2 SOH")
        print("")
        print("Status verileri:")
        print("1.3.6.1.4.1.1001.1.6.0 - Kol 1 Status")
        print("1.3.6.1.4.1.1001.1.6.1 - Kol 1 Batarya 1 Status")
        print("1.3.6.1.4.1.1001.3.6.2 - Kol 3 Batarya 2 Status")
        print("")
        print("Alarm verileri:")
        print("1.3.6.1.4.1.1001.1.7.0.1 - Kol 1 Akım alarmı")
        print("1.3.6.1.4.1.1001.1.7.0.2 - Kol 1 Nem alarmı")
        print("1.3.6.1.4.1.1001.1.7.1.1 - Kol 1 Batarya 1 VoltageWarn alarmı")
        print("1.3.6.1.4.1.1001.1.7.1.2 - Kol 1 Batarya 1 LVoltageAlarm alarmı")
        print("1.3.6.1.4.1.1001.3.7.2.1 - Kol 3 Batarya 2 VoltageWarn alarmı")
        print("=" * 50)
        print("SNMP Test komutları:")
        print("snmpget -v2c -c public localhost:1161 1.3.6.5.2.0")
        print("snmpget -v2c -c public localhost:1161 1.3.6.5.7.0")
        print("snmpget -v2c -c public localhost:1161 1.3.6.1.4.1.1001.1.1")
        print("snmpget -v2c -c public localhost:1161 1.3.6.1.4.1.1001.1.5.1.10")
        print("snmpget -v2c -c public localhost:1161 1.3.6.1.4.1.1001.1.6.1")
        print("snmpget -v2c -c public localhost:1161 1.3.6.1.4.1.1001.1.7.0.1")
        print("snmpget -v2c -c public localhost:1161 1.3.6.1.4.1.1001.1.7.1.1")
        print("snmpwalk -v2c -c public localhost:1161 1.3.6.1.4.1.1001")
        print("=" * 50)
        
        # SNMP sunucu çalıştır
        print(f"🔧 SNMP Engine başlatılıyor...")
        try:
            snmp_engine.open_dispatcher()
            print(f"✅ SNMP Engine başarıyla başlatıldı!")
            snmp_engine.transport_dispatcher.job_started(1)
            print(f"✅ SNMP Engine job başlatıldı!")
        except Exception as e:
            print(f"❌ SNMP Engine başlatma hatası: {e}")
            snmp_engine.close_dispatcher()
            raise
        
    except Exception as e:
        print(f"❌ SNMP sunucu hatası: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    print("Program başlatıldı ==>")
    main()