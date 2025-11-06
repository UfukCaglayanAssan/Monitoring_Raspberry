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
from alarm_processor import AlarmProcessor

# Unbuffered output - logların hemen görünmesi için
sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

# SNMP imports
from pysnmp.entity import engine, config
from pysnmp.entity.rfc3413 import cmdrsp, context
from pysnmp.carrier.asyncio.dgram import udp
from pysnmp.proto.api import v2c

# SNMP trap gönderme için gerekli sınıflar
# pysnmp.hlapi.v1arch modülünden import et (SNMPv1/v2c için)
from pysnmp.hlapi.v1arch import (
    UdpTransportTarget, ContextData, CommunityData, SnmpEngine
)
# sendNotification için - v1arch modülünde sendTrap veya sendNotification olabilir
# Senkron kullanım için v1arch.asyncio yerine v1arch içindeki fonksiyonu kullan
try:
    from pysnmp.hlapi.v1arch import sendNotification
except ImportError:
    try:
        from pysnmp.hlapi.v1arch import sendTrap as sendNotification
    except ImportError:
        # Son çare: v1arch.asyncio'dan al ama senkron kullan
        from pysnmp.hlapi.v1arch.asyncio import sendNotification

# NotificationType için
try:
    from pysnmp.hlapi import NotificationType
except ImportError:
    from pysnmp.hlapi.v1arch import NotificationType

# SMI ve proto modüllerinden tip sınıfları
from pysnmp.smi.rfc1902 import ObjectType, ObjectIdentity
from pysnmp.proto.rfc1902 import Integer, OctetString

# SNMP ayarları
SNMP_HOST = '0.0.0.0'  # Dışarıdan erişim için 0.0.0.0
SNMP_PORT = 1161
SNMP_COMMUNITY = 'public'

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

# Veri alma modu
data_retrieval_mode = False
data_retrieval_config = None
data_retrieval_lock = threading.Lock()
data_retrieval_waiting_for_period = False  # Tümünü Oku işlemi için periyot bekleme flag'i

# "Tümünü Oku" flag'i
read_all_mode = False
read_all_arm = None

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

# Alarm processor instance (db oluşturulduktan sonra)
import alarm_processor as alarm_processor_module
alarm_processor = AlarmProcessor(db)
alarm_processor_module.alarm_processor = alarm_processor  # Modül seviyesinde de set et

pi = pigpio.pi()
pi.set_mode(TX_PIN, pigpio.OUTPUT)

# Program başlangıç zamanı
program_start_time = int(time.time() * 1000)

def get_period_timestamp():
    """Aktif periyot için timestamp döndür"""
    global current_period_timestamp, period_active, last_data_received, data_retrieval_waiting_for_period
    
    current_time = time.time()
    
    if not period_active:
        current_period_timestamp = int(current_time * 1000)
        period_active = True
        last_data_received = current_time
        
        # Tümünü Oku işlemi periyot bekliyorsa, şimdi aktif et
        if data_retrieval_waiting_for_period:
            with data_retrieval_lock:
                data_retrieval_mode = True
                data_retrieval_waiting_for_period = False
    
    return current_period_timestamp

def reset_period():
    """Periyotu sıfırla"""
    global period_active, current_period_timestamp
    period_active = False
    current_period_timestamp = None

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

def set_data_retrieval_mode(enabled, config=None):
    """Veri alma modunu ayarla"""
    global data_retrieval_mode, data_retrieval_config, data_retrieval_waiting_for_period, period_active
    with data_retrieval_lock:
        old_mode = data_retrieval_mode
        data_retrieval_mode = enabled
        data_retrieval_config = config
        print(f"🔧 VERİ ALMA MODU DEĞİŞTİRİLDİ: {old_mode} -> {enabled}")
        
        # Timestamp artık web app tarafında tutuluyor
        
        # Tümünü Oku işlemi için özel flag
        if enabled and config and config.get('address') == 0:
            # Eğer aktif periyot varsa, onu bitir ve yeni periyot başlatma
            if period_active:
                print(f"🔄 TÜMÜNÜ OKU: Aktif periyot bitiriliyor, yeni periyot başlatılıyor.")
                reset_period()
                get_period_timestamp()
                data_retrieval_waiting_for_period = False
                print(f"🔍 Veri alma modu: Tümünü Oku - Yeni periyot başlatıldı")
            else:
                # Periyot aktif değilse, yeni periyot başlat (ikinci işlem için)
                print(f"🔄 TÜMÜNÜ OKU: Yeni periyot başlatılıyor (period_active=False)")
                get_period_timestamp()
                data_retrieval_waiting_for_period = False
                print(f"🔍 Veri alma modu: Tümünü Oku - Yeni periyot başlatıldı")
        else:
            data_retrieval_waiting_for_period = False
            print(f"🔍 Veri alma modu: {'Aktif' if enabled else 'Pasif'}")
        
        if config:
            print(f"📊 Veri alma konfigürasyonu: {config}")
        
        # JSON dosyasına kaydet
        save_data_retrieval_status()

def is_data_retrieval_mode():
    """Veri alma modu aktif mi kontrol et"""
    global data_retrieval_mode
    with data_retrieval_lock:
        return data_retrieval_mode

def get_data_retrieval_config():
    """Veri alma konfigürasyonunu al"""
    global data_retrieval_config
    with data_retrieval_lock:
        return data_retrieval_config

def save_data_retrieval_status():
    """Veri alma durumunu JSON dosyasına kaydet"""
    try:
        status = {
            'data_retrieval_mode': data_retrieval_mode,
            'data_retrieval_config': data_retrieval_config,
            'read_all_mode': read_all_mode,
            'read_all_arm': read_all_arm
        }
        with open('data_retrieval_status.json', 'w') as f:
            json.dump(status, f, indent=2)
    except Exception as e:
        print(f"❌ JSON kaydetme hatası: {e}")

def load_data_retrieval_status():
    """Veri alma durumunu JSON dosyasından yükle"""
    try:
        if os.path.exists('data_retrieval_status.json'):
            with open('data_retrieval_status.json', 'r') as f:
                status = json.load(f)
                return status
    except Exception as e:
        print(f"❌ JSON yükleme hatası: {e}")
    return None

def should_capture_data(arm_value, k_value, dtype, config):
    """Veri yakalanmalı mı kontrol et"""
    # Tüm kollar seçilmişse (arm=5) - Tümünü Oku
    if config['arm'] == 5:
        return True
    
    # Belirli kol seçilmişse
    if config['arm'] == arm_value:
        # Adres 0 ise Tümünü Oku işlemi - tüm verileri yakala
        if config['address'] == 0:
            return True
        # Adres 1-255 ise Veri Al işlemi - sadece istenen veriyi yakala
        else:
            return k_value > 2 and dtype == config['value']
    
    return False

def is_data_retrieval_period_complete(arm_value, k_value, dtype):
    """Veri alma modu için periyot tamamlandı mı kontrol et"""
    config = get_data_retrieval_config()
    if not config:
        return False
    
    # Tüm kollar seçilmişse (arm=5) - Tümünü Oku işlemi
    if config['arm'] == 5:
        # Son kolun son bataryasının dtype=14 (NTC3) verisi geldi mi?
        return is_period_complete(arm_value, k_value, dtype=dtype)
    
    # Belirli kol seçilmişse - Sadece o koldaki son batarya kontrolü
    if config['arm'] == arm_value:
        # Adres 0 ise Tümünü Oku işlemi - sadece seçilen koldaki son batarya
        if config['address'] == 0:
            # Sadece dtype=14 (NTC3) geldiğinde periyot biter (son batarya için)
            if dtype != 14:
                return False
                
            # Seçilen koldaki son batarya sayısını al (k değerine çevir)
            arm_slave_counts = db.get_arm_slave_counts()
            selected_arm = config['arm']
            last_battery_count = arm_slave_counts.get(selected_arm, 0)
            last_k_value = last_battery_count + 2  # k = battery_count + 2
            
            # Seçilen koldaki son bataryanın dtype=14 (NTC3) verisi geldi mi?
            if arm_value == selected_arm and k_value == last_k_value:
                print(f"✅ TÜMÜNÜ OKU PERİYOT BİTTİ - Kol {arm_value}, k={k_value}, dtype={dtype} (NTC3)")
                return True
            
            return False
        # Adres 1-255 ise Veri Al işlemi - sadece istenen veri
        else:
            # O koldaki son batarya numarasını al
            last_arm, last_battery = get_last_battery_info()
            if last_arm == arm_value and k_value == last_battery and dtype == config['value']:
                return True
    
    return False

def capture_data_for_retrieval(arm_value, k_value, dtype, salt_data):
    """Veri alma için veriyi yakala"""
    config = get_data_retrieval_config()
    if not config:
        return
    
    # Veriyi dosyaya yaz
    data_entry = {
        'timestamp': datetime.datetime.now().strftime('%H:%M:%S'),
        'arm': arm_value,
        'k': k_value,
        'dtype': dtype,
        'value': salt_data,
        'requested_value': config['valueText']
    }
    
    # pending_config.json dosyasına veri ekle
    try:
        if os.path.exists('pending_config.json'):
            with open('pending_config.json', 'r', encoding='utf-8') as f:
                existing_data = json.load(f)
        else:
            existing_data = {}
        
        if 'retrieved_data' not in existing_data:
            existing_data['retrieved_data'] = []
        
        existing_data['retrieved_data'].append(data_entry)
        
        with open('pending_config.json', 'w', encoding='utf-8') as f:
            json.dump(existing_data, f, indent=2, ensure_ascii=False)
        
        print(f"📊 Veri yakalandı: Kol {arm_value}, k={k_value}, dtype={dtype}, değer={salt_data}")
        
    except Exception as e:
        print(f"❌ Veri yakalama hatası: {e}")


def is_valid_arm_data(arm_value, k_value):
    """Veri doğrulama: Sadece aktif kollar ve bataryalar işlenir"""
    # DB'den güncel arm_slave_counts oku ve RAM'i güncelle
    global db
    try:
        battery_count = db.get_arm_slave_count(arm_value)
        if battery_count is not None:
            with data_lock:
                arm_slave_counts_ram[arm_value] = battery_count
        else:
            battery_count = 0
    except:
        battery_count = arm_slave_counts_ram.get(arm_value, 0)
    
    # Kol aktif mi kontrol et
    if battery_count == 0:
        print(f"⚠️ HATALI VERİ: Kol {arm_value} aktif değil (batarya sayısı: {battery_count})")
        return False
        
    # k=2 ise kol verisi, her zaman geçerli
    if k_value == 2:
        return True
    
    # Batarya verisi ise, k değeri = batarya numarası + 2
    # k=3 -> batarya 1, k=4 -> batarya 2, k=5 -> batarya 3, vs.
    # Maksimum k değeri = batarya sayısı + 2
    max_k_value = battery_count + 2
    if k_value > max_k_value:
        print(f"⚠️ HATALI VERİ: Kol {arm_value} için k={k_value} > maksimum k değeri={max_k_value} (batarya sayısı: {battery_count})")
        return False
    
    # k değeri 3'ten küçük olamaz (k=2 kol verisi, k=3+ batarya verisi)
    if k_value < 3:
        print(f"⚠️ HATALI VERİ: Kol {arm_value} için geçersiz k değeri: {k_value}")
        return False
    
    return True

def get_last_battery_info():
    """En son batarya bilgisini döndür (arm, k) - veritabanından oku"""
    try:
        # Veritabanından oku
        with db_lock:
            db_arm_slave_counts = db.get_arm_slave_counts()
        
        if not db_arm_slave_counts:
            print("⚠️ Veritabanından arm_slave_counts okunamadı")
            return None, None
        
        last_arm = None
        last_battery = None
        
        # Aktif kolları bul ve en son bataryayı belirle
        for arm in [1, 2, 3, 4]:
            if arm in db_arm_slave_counts and db_arm_slave_counts[arm] > 0:
                last_arm = arm
                # k değerleri 3'ten başlar, son k değeri = armslavecount + 2
                last_battery = db_arm_slave_counts[arm] + 2
        
        # Veritabanı okuma logları kaldırıldı
        
        return last_arm, last_battery
        
    except Exception as e:
        print(f"❌ get_last_battery_info hatası: {e}")
        return None, None

def is_period_complete(arm_value, k_value, is_missing_data=False, is_alarm=False, dtype=None):
    """Periyot tamamlandı mı kontrol et"""
    global read_all_mode, read_all_arm
    
    # Veri alma modu aktifse ve "Tümünü Oku" (address=0) ise
    if is_data_retrieval_mode():
        config = get_data_retrieval_config()
        if config and config.get('address') == 0:
            # arm=5 ise tüm kollar için "Tümünü Oku" - son kolun son bataryasına bak
            if config.get('arm') == 5:
                # Normal periyot kontrolü - son kolun son bataryasına bak
                last_arm, last_battery = get_last_battery_info()
                if arm_value == last_arm and k_value == last_battery:
                    if dtype is not None and dtype != 14:
                        return False
                    print(f"✅ TÜMÜNÜ OKU PERİYOT BİTTİ (Tüm Kollar) - Kol {arm_value}, k={k_value}, dtype={dtype}")
                    return True
                return False
            # Belirli bir kol için "Tümünü Oku" - sadece o kolun son bataryasına bak
            else:
                selected_arm = config['arm']
                arm_slave_counts = db.get_arm_slave_counts()
                last_battery_count = arm_slave_counts.get(selected_arm, 0)
                last_k_value = last_battery_count + 2  # k = battery_count + 2
                
                # Seçilen koldaki son bataryanın dtype=14 (NTC3) verisi geldi mi?
                if arm_value == selected_arm and k_value == last_k_value:
                    if dtype is not None and dtype != 14:
                        # dtype=14 değilse devam et
                        return False
                    print(f"✅ TÜMÜNÜ OKU PERİYOT BİTTİ (Kol {selected_arm}) - Kol {arm_value}, k={k_value}, dtype={dtype}")
                    return True
                return False
    
    if read_all_mode and read_all_arm is not None:
        # "Tümünü Oku" modu aktifse - sadece o koldaki son bataryanın dtype=14'ine bak
        last_arm, last_battery = get_last_battery_info()
        # Sadece o koldaki son batarya geldi mi? (dtype kontrolü sadece 11 byte veri işlenirken yapılır)
        if arm_value == read_all_arm and k_value == last_battery:
            if dtype is not None and dtype != 14:
                # 11 byte veri işlenirken dtype=14 değilse devam et
                return False
            return True
        return False
    else:
        # Normal mod - tüm kolların son bataryası
        last_arm, last_battery = get_last_battery_info()
    
    if not last_arm or not last_battery:
        return False
    
    # En son koldaki en son batarya verisi geldi mi?
    # SADECE dtype=14 (NTC3) geldiğinde periyot biter!
    if arm_value == last_arm and k_value == last_battery:
        if dtype is not None and dtype != 14:
            # Son batarya ama dtype=14 değil, periyot devam ediyor
            return False
        return True
    
    # Missing data geldi mi?
    if is_missing_data:
        return True
    
    # Alarm geldi mi? (son batarya alarmından sonra periyot biter)
    if is_alarm and arm_value == last_arm and k_value == last_battery:
        return True
    
    # Pasif balans kontrolü - son batarya pasif balansta mı?
    if arm_value == last_arm and k_value == last_battery - 1:
        # Son bataryadan bir önceki batarya geldi, son batarya pasif balansta mı kontrol et
        try:
            with db_lock:
                balance_data = db.get_passive_balance(arm=arm_value)
                # Aktif pasif balans durumunu kontrol et (status=0 ve slave=last_battery)
                for balance in balance_data:
                    if balance['slave'] == last_battery and balance['status'] == 0:
                        return True
        except Exception as e:
            print(f"❌ Pasif balans kontrol hatası: {e}")
    
    return False

def send_reset_system_signal():
    """Reset system sinyali gönder (0x55 0x55 0x55) - 1 saat aralık kontrolü ile - PASIF MOD"""
    try:
        # Reset system gönderilebilir mi kontrol et (minimum 1 saat aralık)
        if not db.can_send_reset_system(min_interval_hours=1):
            print("⏰ Reset system gönderilemiyor: Son reset'ten bu yana 1 saat geçmedi")
            return False
        
        # Reset öncesi missing data'ları kaydet
        save_missing_data_before_reset()
        
        # PASIF MOD: Sadece loglama, gerçek sinyal gönderilmiyor
        print("🔄 Reset system sinyali (PASIF MOD): 0x55 0x55 0x55 - Sadece loglandı")
        
        # Reset system gönderimini logla
        log_timestamp = db.log_reset_system("Missing data period completed - PASIF MOD")
        if log_timestamp:
            print(f"📝 Reset system log kaydedildi: {log_timestamp}")
        
        # Missing data listesini temizle
        clear_missing_data()
        
        return True
        
    except Exception as e:
        print(f"❌ Reset system sinyali gönderilirken hata: {e}")
        return False

def add_missing_data(arm_value, k_value):
    """Missing data ekle - k_value (3-122) ile çalışır"""
    battery_value = k_value - 2  # Batarya numarası (1-120)
    with missing_data_lock:
        missing_data_tracker.add((arm_value, k_value))
        print(f"📝 Missing data eklendi: Kol {arm_value}, k: {k_value}, Batarya {battery_value}")


def clear_missing_data():
    """Missing data listesini temizle"""
    with missing_data_lock:
        missing_data_tracker.clear()
        print("🧹 Missing data listesi temizlendi")

def resolve_missing_data(arm_value, k_value):
    """Missing data'yı düzelt (veri geldiğinde) - k_value (3-122) ile çalışır"""
    battery_value = k_value - 2  # Batarya numarası (1-120)
    with missing_data_lock:
        if (arm_value, k_value) in missing_data_tracker:
            missing_data_tracker.remove((arm_value, k_value))
            print(f"✅ Missing data düzeltildi: Kol {arm_value}, k: {k_value}, Batarya {battery_value}")
            return True
        return False

def save_missing_data_before_reset():
    """Reset system öncesi missing data'ları kaydet"""
    with missing_data_lock:
        with missing_data_before_reset_lock:
            missing_data_before_reset.clear()
            missing_data_before_reset.update(missing_data_tracker)
            print(f"📝 Reset öncesi missing data'lar kaydedildi: {len(missing_data_before_reset)} adet")

def check_missing_data_after_reset(arm_value, k_value):
    """Reset sonrası missing data kontrolü - status 0 gelirse alarm oluştur"""
    battery_value = k_value - 2  # Batarya numarası (1-120)
    with missing_data_before_reset_lock:
        if (arm_value, k_value) in missing_data_before_reset:
            # Bu batarya reset öncesi missing data'daydı, şimdi tekrar status 0 gelirse alarm
            print(f"🚨 VERİ GELMİYOR ALARMI: Kol {arm_value}, k: {k_value}, Batarya {battery_value} - Reset sonrası hala veri gelmiyor")
            # "Veri gelmiyor" alarmı oluştur - k_value kaydet
            alarm_processor.add_alarm(arm_value, k_value, 0, 0, int(time.time() * 1000))  # error_msb=0, error_lsb=0 = veri gelmiyor
            print(f"📝 Veri gelmiyor alarmı eklendi - Arm: {arm_value}, k: {k_value}, Battery: {battery_value}")
            # Status'u 0 yap (veri yok) - battery_value kullan (RAM için)
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
    global last_data_received, tumunu_oku_mode, tumunu_oku_arm, read_all_mode, read_all_arm
    
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
                k_value = int(data[1], 16)  # 2. byte k değeri (3-122 arası)
                battery = k_value - 2  # Batarya numarası (1-120 arası)
                error_msb = int(data[4], 16)
                error_lsb = int(data[5], 16)
                
                # Detaylı console log
                print(f"\n*** BATKON ALARM VERİSİ ALGILANDI - {timestamp} ***")
                print(f"Arm: {arm_value}, k: {k_value}, Battery: {battery}, Error MSB: {error_msb}, Error LSB: {error_lsb}")
                print(f"Ham Veri: {data}")
                
                # Validasyon: Geçersiz alarm kontrolü
                is_valid_alarm = True
                
                # 1. Arm kontrolü (1-4 arası olmalı)
                arm_valid = True
                if arm_value not in [1, 2, 3, 4]:
                    print(f"⚠️ GEÇERSİZ ALARM: Hatalı arm değeri ({arm_value}) - Veritabanına kaydedilmedi")
                    arm_valid = False
                    is_valid_alarm = False
                
                # 2. Batarya mevcut mu kontrolü (DB'den oku) - Her zaman yapılmalı (RAM temizleme için)
                try:
                    max_battery = db.get_arm_slave_count(arm_value)
                    if max_battery is None:
                        max_battery = 0
                    # RAM'i de güncelle
                    with data_lock:
                        arm_slave_counts_ram[arm_value] = max_battery
                except:
                    max_battery = arm_slave_counts_ram.get(arm_value, 0)
                
                # Batarya ve k_value kontrolü
                battery_valid = True
                if battery > max_battery:
                    print(f"⚠️ GEÇERSİZ ALARM: Batarya {battery} mevcut değil (Kol {arm_value} max: {max_battery})")
                    battery_valid = False
                
                # k_value kontrolü (3 ile max_battery+2 arası olmalı)
                min_k = 3
                max_k = max_battery + 2
                if k_value < min_k or k_value > max_k:
                    print(f"⚠️ GEÇERSİZ ALARM: Hatalı k_value ({k_value}) - Kol {arm_value} için geçerli aralık: {min_k}-{max_k}")
                    battery_valid = False
                
                # Alarm koşullarını her zaman kontrol et ve RAM'e kaydet (alarm düzeldiğinde de temizlemek için)
                if arm_valid and battery_valid:
                    alarm_data = {'error_msb': error_msb, 'error_lsb': error_lsb}
                    check_alarm_conditions(arm_value, battery, alarm_data)
                    print(f"✅ Alarm koşulları güncellendi - Kol {arm_value}, Batarya {battery}, MSB: {error_msb}, LSB: {error_lsb}")
                
                # 3. LSB=0 ve MSB=0 kontrolü (alarm yoksa veritabanına kaydetme)
                if error_lsb == 0 and error_msb == 0:
                    print(f"⚠️ ALARM YOK: LSB=0 ve MSB=0 - RAM temizlendi, veritabanına kaydedilmedi")
                    is_valid_alarm = False
                else:
                    is_valid_alarm = arm_valid and battery_valid
                
                # Geçerli alarm ise veritabanına kaydet
                if is_valid_alarm:
                    alarm_timestamp = int(time.time() * 1000)
                    
                    # Eğer errorlsb=1 ve errormsb=1 ise, mevcut alarmı düzelt
                    if error_lsb == 1 and error_msb == 1:
                        # Periyot bitiminde işlenecek şekilde düzeltme ekle
                        alarm_processor.add_resolve(arm_value, k_value)  # k_value kaydet (3-122)
                        print(f"📝 Batkon alarm düzeltme eklendi (beklemede) - Arm: {arm_value}, k: {k_value}, Battery: {battery}")
                    else:
                        # Periyot bitiminde işlenecek şekilde alarm ekle
                        alarm_processor.add_alarm(arm_value, k_value, error_msb, error_lsb, alarm_timestamp)  # k_value kaydet (3-122)
                        print("📝 Yeni Batkon alarm eklendi (beklemede)")
                    
                    # Periyot tamamlandı mı kontrol et (son batarya alarmından sonra)
                    if is_period_complete(arm_value, k_value, is_alarm=True):
                        print(f"🔄 PERİYOT BİTTİ - Son batarya alarmı: Kol {arm_value}, k: {k_value}, Batarya {battery}")
                        # Periyot bitti, alarmları işle
                        alarm_processor.process_period_end()
                        # Veri alma modunu durdur
                        if is_data_retrieval_mode():
                            set_data_retrieval_mode(False, None)
                            print("🛑 Veri alma modu durduruldu - Periyot bitti")
                        # Normal alarm verisi geldiğinde reset sinyali gönderme
                        # Reset sinyali sadece missing data durumunda gönderilir
                        # Yeni periyot başlat
                        reset_period()
                        get_period_timestamp()
                else:
                    print(f"❌ Geçersiz alarm atlandı - Veritabanına kaydedilmedi")
                
                continue

            # 5 byte'lık missing data verisi kontrolü
            if len(data) == 5:
                raw_bytes = [int(b, 16) for b in data]
                timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                
                print(f"\n*** MISSING DATA VERİSİ ALGILANDI - {timestamp} ***")
                
                # Missing data kaydı hazırla
                arm_value = raw_bytes[3]
                k_value = raw_bytes[1]  # k değeri (3-122)
                battery_value = k_value - 2  # Batarya numarası (1-120)
                status_value = raw_bytes[4]
                missing_timestamp = int(time.time() * 1000)
                
                print(f"Missing data: Kol {arm_value}, k: {k_value}, Batarya: {battery_value}, Status: {status_value}")
                
                # Status 0 = Veri gelmiyor, Status 1 = Veri geliyor (düzeltme)
                if status_value == 0:
                    # Veri gelmiyor - missing data ekle (k_value kaydet)
                    add_missing_data(arm_value, k_value)
                    print(f"🆕 VERİ GELMİYOR: Kol {arm_value}, Batarya {battery_value}")
                    
                    # Status güncelle (veri yok) - battery_value kullan (RAM için)
                    update_status(arm_value, battery_value, False)
                    
                    # Reset sonrası kontrol - k_value kaydet
                    check_missing_data_after_reset(arm_value, k_value)
                    
                    # Periyot tamamlandı mı kontrol et - k_value kullan
                    if is_period_complete(arm_value, k_value, is_missing_data=True):
                        # Periyot bitti, alarmları işle
                        alarm_processor.process_period_end()
                        # Veri alma modunu durdur
                        if is_data_retrieval_mode():
                            set_data_retrieval_mode(False, None)
                            print("🛑 Veri alma modu durduruldu - Periyot bitti (missing data)")
                        # Reset system sinyali gönder (1 saat aralık kontrolü ile)
                        if send_reset_system_signal():
                            # Periyot bitti, yeni periyot k=2 (akım verisi) geldiğinde başlayacak
                            reset_period()
                        else:
                            print("⏰ Reset system gönderilemedi, periyot devam ediyor")
                        
                elif status_value == 1:
                    # Veri geliyor - missing data düzelt (k_value kaydet)
                    if resolve_missing_data(arm_value, k_value):
                        print(f"✅ VERİ GELDİ: Kol {arm_value}, Batarya {battery_value} - Missing data düzeltildi")
                        # Status güncelle (veri var) - battery_value kullan (RAM için)
                        update_status(arm_value, battery_value, True)
                        # Alarm düzeltme işlemi - k_value kaydet
                        alarm_processor.add_resolve(arm_value, k_value)
                        print(f"📝 Missing data alarm düzeltme eklendi - Arm: {arm_value}, k: {k_value}, Battery: {battery_value}")
                    else:
                        print(f"ℹ️ VERİ GELDİ: Kol {arm_value}, Batarya {battery_value} - Missing data zaten yoktu")
                        # Status güncelle (veri var) - battery_value kullan (RAM için)
                        update_status(arm_value, battery_value, True)
                
                # SQLite'ye kaydet - k_value kaydet
                with db_lock:
                    db.insert_missing_data(arm_value, k_value, status_value, missing_timestamp)
                print("✓ Missing data SQLite'ye kaydedildi")
                continue

            # 11 byte'lık veri kontrolü
            if len(data) == 11:
                arm_value = int(data[3], 16)
                dtype = int(data[2], 16)
                k_value = int(data[1], 16)  # K değerini olduğu gibi al
                
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
                if dtype == 10 and k_value == 2:  # Akım verisi geldiğinde
                    # Yeni periyot başlat (k=2 akım verisi geldiğinde)
                    if not period_active:
                        get_period_timestamp()
                
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
                
                # Tanımlanmış dtype kontrolü
                valid_dtypes = [10, 11, 12, 13, 14, 15, 126]
                if dtype not in valid_dtypes:
                    print(f"⚠️ TANIMSIZ DTYPE ALGILANDI!")
                    print(f"   📦 Ham Paket: {' '.join([f'0x{b:02X}' for b in [int(x, 16) for x in data]])}")
                    print(f"   📊 Header: 0x{data[0]}, k: {k_value}, dtype: {dtype}, arm: {arm_value}")
                    print(f"   📊 Veri: {salt_data}")
                    print(f"   ❌ Bu veri veritabanına kaydedilmeyecek!")
                    continue  # Bu veriyi atla
                
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
                            "Dtype": 126,  # SOC = dtype 126
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
                        
                        # k=2 (kol verisi) için özel mapping
                        if k_value == 2:
                            if dtype == 10:  # Akım -> 1
                                battery_data_ram[arm_value][k_value][1] = {
                                    'value': salt_data,
                                    'timestamp': get_period_timestamp()
                                }
                                # RAM Mapping logları kaldırıldı
                            elif dtype == 11:  # Nem -> 2
                                # Veritabanına kaydet
                                nem_record = {
                                    "Arm": arm_value,
                                    "k": k_value,
                                    "Dtype": 11,
                                    "data": salt_data,
                                    "timestamp": get_period_timestamp()
                                }
                                batch.append(nem_record)
                            elif dtype == 15:  # Sıcaklık -> 3
                                # Veritabanına kaydet
                                sicaklik_record = {
                                    "Arm": arm_value,
                                    "k": k_value,
                                    "Dtype": 15,
                                    "data": salt_data,
                                    "timestamp": get_period_timestamp()
                                }
                                batch.append(sicaklik_record)
                                
                                # RAM'e kaydet (Modbus/SNMP için)
                                battery_data_ram[arm_value][k_value][3] = {
                                    'value': salt_data,
                                    'timestamp': get_period_timestamp()
                                }
                                # RAM Mapping logları kaldırıldı
                            # dtype 12 (NTC2) ayrı bölümde işleniyor
                                # RAM Mapping logları kaldırıldı
                        else:
                            # Batarya verisi için normal mapping: 1=Gerilim, 2=SOC, 3=RIMT, 4=SOH, 5=NTC1, 6=NTC2, 7=NTC3
                            if dtype == 10:  # Gerilim -> 1
                                battery_data_ram[arm_value][k_value][1] = {
                                    'value': salt_data,
                                    'timestamp': get_period_timestamp()
                                }
                                # RAM Mapping logları kaldırıldı
                            elif dtype == 11:  # SOH -> 4
                                battery_data_ram[arm_value][k_value][4] = {
                                    'value': salt_data,
                                    'timestamp': get_period_timestamp()
                                }
                            # dtype 12 (NTC2) ayrı bölümde işleniyor
                            elif dtype == 126:  # SOC -> 2
                                battery_data_ram[arm_value][k_value][2] = {
                                    'value': salt_data,
                                    'timestamp': get_period_timestamp()
                                }
                            elif dtype == 13:  # NTC1 -> 5
                                battery_data_ram[arm_value][k_value][5] = {
                                    'value': salt_data,
                                    'timestamp': get_period_timestamp()
                                }
                            elif dtype == 14:  # NTC3 -> 7
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
                        # RAM kayıt logları kaldırıldı
                    
                    # Status güncelle (sadece missing data durumunda)
                    # Normal veri geldiğinde status güncelleme yapmıyoruz
                    # Status sadece missing data (0) veya düzeldi (1) durumunda güncellenir
                    
                    # Alarm kontrolü kaldırıldı - sadece alarm verisi geldiğinde yapılır
                
                elif dtype == 11:  # SOH veya Nem
                    if k_value == 2:  # Nem verisi
                        record = {
                            "Arm": arm_value,
                            "k": k_value,
                            "Dtype": 11,  # Nem=11
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
                            # Arm verisi için dtype=11 -> RAM dtype=2 (Nem)
                            battery_data_ram[arm_value][k_value][2] = {
                                'value': salt_data,
                                'timestamp': get_period_timestamp()
                            }
                            # RAM Mapping logları kaldırıldı
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
                        
                        # SOH verisini dtype=11'ya kaydet
                        record = {
                            "Arm": arm_value,
                            "k": k_value,
                            "Dtype": 11,
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
                            
                            # RIMT verisini de RAM'e kaydet (DB'ye kaydetme)
                            # RIMT -> 3 (1-7 sıralama)
                            battery_data_ram[arm_value][k_value][3] = {
                                'value': salt_data,  # RIMT değeri
                                'timestamp': get_period_timestamp()
                            }
                
                
                elif dtype == 13:  # NTC1
                    period_ts = get_period_timestamp()
                    record = {
                            "Arm": arm_value,
                            "k": k_value,
                        "Dtype": 13,
                        "data": salt_data,
                            "timestamp": period_ts
                        }
                    batch.append(record)
                    
                    # RAM'e yaz (Modbus/SNMP için)
                    with data_lock:
                        if arm_value not in battery_data_ram:
                            battery_data_ram[arm_value] = {}
                        if k_value not in battery_data_ram[arm_value]:
                            battery_data_ram[arm_value][k_value] = {}
                        
                        if k_value == 2:  # Kol verisi
                            battery_data_ram[arm_value][k_value][4] = {  # ORTAM SICAKLIĞI -> 4
                            'value': salt_data,
                            'timestamp': get_period_timestamp()
                        }
                        else:  # Batarya verisi
                            battery_data_ram[arm_value][k_value][5] = {  # NTC1 -> 5
                            'value': salt_data,
                            'timestamp': get_period_timestamp()
                        }
                    
                    # Alarm kontrolü kaldırıldı - sadece alarm verisi geldiğinde yapılır
                
                elif dtype == 12:  # NTC2
                    period_ts = get_period_timestamp()
                    record = {
                        "Arm": arm_value,
                        "k": k_value,
                        "Dtype": 12,
                        "data": salt_data,
                        "timestamp": period_ts
                    }
                    batch.append(record)
                    
                    # RAM'e yaz (Modbus/SNMP için)
                    with data_lock:
                        if arm_value not in battery_data_ram:
                            battery_data_ram[arm_value] = {}
                        if k_value not in battery_data_ram[arm_value]:
                            battery_data_ram[arm_value][k_value] = {}
                        
                        if k_value == 2:  # Kol verisi
                            battery_data_ram[arm_value][k_value][3] = {  # MODÜL SICAKLIĞI -> 3
                            'value': salt_data,
                            'timestamp': get_period_timestamp()
                        }
                        else:  # Batarya verisi
                            battery_data_ram[arm_value][k_value][6] = {  # NTC2 -> 6
                                'value': salt_data,
                                'timestamp': get_period_timestamp()
                            }
                    
                    # Alarm kontrolü kaldırıldı - sadece alarm verisi geldiğinde yapılır
                
                elif dtype == 14:  # NTC3
                    period_ts = get_period_timestamp()
                    record = {
                        "Arm": arm_value,
                        "k": k_value,
                        "Dtype": 14,
                        "data": salt_data,
                        "timestamp": period_ts
                    }
                    batch.append(record)
                    
                    # RAM'e yaz (Modbus/SNMP için)
                    with data_lock:
                        if arm_value not in battery_data_ram:
                            battery_data_ram[arm_value] = {}
                        if k_value not in battery_data_ram[arm_value]:
                            battery_data_ram[arm_value][k_value] = {}
                        # NTC3 -> RAM[7]
                        battery_data_ram[arm_value][k_value][7] = {
                            'value': salt_data,
                            'timestamp': get_period_timestamp()
                        }
                    
                    # Alarm kontrolü kaldırıldı - sadece alarm verisi geldiğinde yapılır
                
                    # Veri alma modu kontrolü (dtype=14 için - Tümünü Oku periyot bitişi)
                    if is_data_retrieval_mode():
                        config = get_data_retrieval_config()
                        if config and should_capture_data(arm_value, k_value, dtype, config):
                            capture_data_for_retrieval(arm_value, k_value, dtype, salt_data)
                            
                            # Veri alma modu periyot tamamlandı mı kontrol et (dtype=14 için)
                            if is_data_retrieval_period_complete(arm_value, k_value, dtype):
                                print(f"🔄 VERİ ALMA PERİYOTU BİTTİ (NTC3) - Kol {arm_value}, k={k_value}, dtype={dtype}")
                                set_data_retrieval_mode(False, None)
                                print("🛑 Veri alma modu durduruldu - Tümünü Oku işlemi tamamlandı")
                
                else:  # Diğer Dtype değerleri için
                    # Bu noktaya gelirse tanımsız dtype demektir, zaten yukarıda kontrol edildi
                    print(f"⚠️ TANIMSIZ DTYPE ELSE BLOĞUNA GELDİ!")
                    print(f"   📊 dtype: {dtype}, arm: {arm_value}, k: {k_value}, data: {salt_data}")
                    continue  # Bu veriyi atla
                    
                    # RAM'e yaz (Modbus/SNMP için)
                    with data_lock:
                        if arm_value not in battery_data_ram:
                            battery_data_ram[arm_value] = {}
                        if k_value not in battery_data_ram[arm_value]:
                            battery_data_ram[arm_value][k_value] = {}
                        
                        # Dtype mapping: 12=NTC2→6, 13=NTC1→5, 14=NTC3→7, 126=SOC→2
                        # dtype 12 (NTC2) ayrı bölümde işleniyor
                        if dtype == 13:  # NTC1 -> 5
                            battery_data_ram[arm_value][k_value][5] = {
                                'value': salt_data,
                                'timestamp': get_period_timestamp()
                            }
                        elif dtype == 14:  # NTC3 -> 7
                            battery_data_ram[arm_value][k_value][7] = {
                                'value': salt_data,
                                'timestamp': get_period_timestamp()
                            }
                        elif dtype == 126:  # SOC -> 2
                            battery_data_ram[arm_value][k_value][2] = {
                                'value': salt_data,
                                'timestamp': get_period_timestamp()
                            }
                        else:
                            # Diğer dtype'lar için direkt kullan
                            battery_data_ram[arm_value][k_value][dtype] = {
                                'value': salt_data,
                                'timestamp': get_period_timestamp()
                            }
                    
                    # Alarm kontrolü kaldırıldı - sadece alarm verisi geldiğinde yapılır
                    
                    # Veri alma modu kontrolü
                    if is_data_retrieval_mode():
                        config = get_data_retrieval_config()
                        if config and should_capture_data(arm_value, k_value, dtype, config):
                            capture_data_for_retrieval(arm_value, k_value, dtype, salt_data)
                            
                            # Veri alma modu periyot tamamlandı mı kontrol et
                            if is_data_retrieval_period_complete(arm_value, k_value, dtype):
                                print(f"🔄 VERİ ALMA PERİYOTU BİTTİ - Kol {arm_value}, k={k_value}, dtype={dtype}")
                                set_data_retrieval_mode(False, None)
                                print("🛑 Veri alma modu durduruldu - İstenen veri alındı")
                    
                    # Genel periyot tamamlandı mı kontrol et (11 byte veri için)
                    if is_period_complete(arm_value, k_value):
                        print(f"🔄 PERİYOT BİTTİ - 11 byte veri: Kol {arm_value}, k={k_value}")
                        # Periyot bitti, alarmları işle
                        alarm_processor.process_period_end()
                        # Veri alma modunu durdur
                        if is_data_retrieval_mode():
                            print(f"🔍 VERİ ALMA MODU DURDURULUYOR - Önceki durum: {is_data_retrieval_mode()}")
                            set_data_retrieval_mode(False, None)
                            print(f"🛑 Veri alma modu durduruldu - Yeni durum: {is_data_retrieval_mode()}")
                        else:
                            print(f"ℹ️ Veri alma modu zaten kapalı - Durum: {is_data_retrieval_mode()}")
                        # Periyot bitti, yeni periyot k=2 (akım verisi) geldiğinde başlayacak
                        reset_period()

            # 6 byte'lık balans komutu veya armslavecounts kontrolü
            elif len(data) == 6:
                raw_bytes = [int(b, 16) for b in data]
                
                # Slave sayısı verisi: 2. byte (index 1) 0x7E ise
                if raw_bytes[1] == 0x7E:
                    arm1, arm2, arm3, arm4 = raw_bytes[2], raw_bytes[3], raw_bytes[4], raw_bytes[5]
                    print(f"armslavecounts verisi tespit edildi: arm1={arm1}, arm2={arm2}, arm3={arm3}, arm4={arm4}")
                    
                    # RAM'de armslavecounts güncelle (sadece RAM, veritabanı değil)
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
                    print(f"ℹ️ Not: Periyot kontrolü veritabanından yapılacak")
                    
                    # Veritabanına kaydet
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
                    
                    # Veritabanına kaydet
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
                            k_value = raw_bytes[1]  # k değeri (3-122 arası)
                            battery_value = k_value - 2  # Batarya numarası (1-120)
                            arm_value = raw_bytes[3]
                            status_value = raw_bytes[4]
                            balance_timestamp = updated_at
                            
                            with db_lock:
                                db.update_or_insert_passive_balance(arm_value, k_value, status_value, balance_timestamp)  # k_value kaydet
                            print(f"✓ Balans güncellendi: Arm={arm_value}, k={k_value}, Battery={battery_value}, Status={status_value}")
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
                
                # Normal veri işlendikten sonra periyot bitiş kontrolü
                # Son işlenen veriyi kontrol et (batch temizlenmeden önce)
                if batch_size > 0:
                    # Son batch'teki son veriyi al
                    last_record = batch[-1]
                    arm_value = last_record.get('Arm')
                    k_value = last_record.get('k')
                    if arm_value and k_value:
                        # Normal periyot bitiş kontrolü
                        last_dtype = last_record.get('Dtype')
                        if is_period_complete(arm_value, k_value, dtype=last_dtype):
                            # Periyot bitti, alarmları işle
                            alarm_processor.process_period_end()
                            
                            # "Tümünü Oku" modu aktifse flag'i False yap ve veri alma modunu durdur
                            if read_all_mode:
                                read_all_mode = False
                                read_all_arm = None
                                set_data_retrieval_mode(False, None)
                            
                            # Veri alma modu aktifse durdur
                            if is_data_retrieval_mode():
                                set_data_retrieval_mode(False, None)
                            
                            # Periyot bitti, yeni periyot k=2 (akım verisi) geldiğinde başlayacak
                            reset_period()
                
                with db_lock:
                    db.insert_battery_data_batch(batch)
                batch = []
                last_insert = time.time()
                # Batch kayıt logları kaldırıldı

            data_queue.task_done()
            
        except queue.Empty:
            if batch:
                batch_size = len(batch)
                
                # Normal veri işlendikten sonra periyot bitiş kontrolü
                # Son işlenen veriyi kontrol et (batch temizlenmeden önce)
                if batch_size > 0:
                    # Son batch'teki son veriyi al
                    last_record = batch[-1]
                    arm_value = last_record.get('Arm')
                    k_value = last_record.get('k')
                    if arm_value and k_value:
                        # "Tümünü Oku" periyot bitiş kontrolü - sadece veri alma modu aktifken
                        if is_data_retrieval_mode():
                            config = get_data_retrieval_config()
                            if config and config.get('address') == 0:  # Tümünü Oku
                                last_dtype = last_record.get('Dtype')
                                if last_dtype and is_data_retrieval_period_complete(arm_value, k_value, last_dtype):
                                    set_data_retrieval_mode(False, None)
                                    # Normal periyot bitiş kontrolüne geç
                                    if is_period_complete(arm_value, k_value):
                                        alarm_processor.process_period_end()
                                        reset_period()
                                    return  # "Tümünü Oku" bitti, normal akışa geç
                        
                        # Normal periyot bitiş kontrolü
                        last_dtype = last_record.get('Dtype')
                        period_complete = is_period_complete(arm_value, k_value, dtype=last_dtype)
                        if period_complete:
                            # Periyot bitti, alarmları işle
                            alarm_processor.process_period_end()
                            
                            # Veri alma modu aktifse durdur
                            if is_data_retrieval_mode():
                                set_data_retrieval_mode(False, None)
                            
                            # Periyot bitti, yeni periyot k=2 (akım verisi) geldiğinde başlayacak
                            reset_period()
                        # Periyot devam ediyor logları kaldırıldı
                
                with db_lock:
                    db.insert_battery_data_batch(batch)
                batch = []
                last_insert = time.time()
                # Batch kayıt logları kaldırıldı
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
    global read_all_mode, read_all_arm
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
                    elif config_data.get('type') == 'command':
                        # Toplu komut gönder (readAll, resetAll)
                        command = config_data.get('command')
                        arm = config_data.get('arm')
                        packet = config_data.get('packet')
                        if packet:
                            print(f"*** TOPLU KOMUT GÖNDERİLİYOR ***")
                            print(f"Komut: {command}, Kol: {arm}, Paket: {packet} (Hex: {[hex(x) for x in packet]})")
                            wave_uart_send(pi, TX_PIN, packet, int(1e6 / BAUD_RATE))
                            print(f"✓ {command} komutu cihaza gönderildi")
                            
                            # "Tümünü Oku" komutu gönderildiğinde flag'i True yap ve veri alma modunu başlat
                            if command == 'readAll':
                                read_all_mode = True
                                read_all_arm = arm
                                print(f"🔍 TÜMÜNÜ OKU MODU AKTİF - Kol {arm}")
                                
                                # Veri alma modunu da başlat
                                config = {
                                    'arm': arm,
                                    'address': 0,  # Tümünü Oku için adres 0
                                    'value': 0,    # Tümünü Oku için değer 0
                                    'valueText': 'Tüm Veriler'
                                }
                                set_data_retrieval_mode(True, config)
                                print(f"🔧 VERİ ALMA MODU BAŞLATILDI - Tümünü Oku için")
                    elif config_data.get('type') == 'dataget':
                        # Veri alma komutu gönder
                        arm_value = config_data.get('armValue')
                        slave_address = config_data.get('slaveAddress')
                        slave_command = config_data.get('slaveCommand')
                        packet = config_data.get('packet')
                        if packet:
                            print(f"*** VERİ ALMA KOMUTU GÖNDERİLİYOR ***")
                            print(f"Kol: {arm_value}, Adres: {slave_address}, Komut: {slave_command}, Paket: {packet} (Hex: {[hex(x) for x in packet]})")
                            wave_uart_send(pi, TX_PIN, packet, int(1e6 / BAUD_RATE))
                            print(f"✓ Veri alma komutu cihaza gönderildi")
                    elif config_data.get('type') == 'data_retrieval_start':
                        # Veri alma modunu başlat (JSON dosyasından)
                        config = config_data.get('config')
                        if config:
                            set_data_retrieval_mode(True, config)
                            print(f"🔧 VERİ ALMA MODU BAŞLATILDI (JSON'dan): {config}")
                            
                            # Eğer "Tümünü Oku" (address=0) ise, UART'a komut gönder
                            if config.get('address') == 0:
                                arm = config.get('arm')
                                if arm:
                                    # Tümünü Oku komutu paketini hazırla
                                    if arm == 5:  # Tüm kollar
                                        command_packet = [0x81, 5, 0x7A]  # 0x81 0x05 0x7A
                                    else:  # Belirli kol
                                        command_packet = [0x81, arm, 0x7A]  # 0x81 0xkol 0x7A
                                    
                                    print(f"*** TÜMÜNÜ OKU KOMUTU GÖNDERİLİYOR (Veri Alma Modu) ***")
                                    print(f"Kol: {arm}, Paket: {[f'0x{b:02X}' for b in command_packet]}")
                                    wave_uart_send(pi, TX_PIN, command_packet, int(1e6 / BAUD_RATE))
                                    print(f"✓ Tümünü oku komutu cihaza gönderildi (Veri Alma Modu)")
                                    
                                    # read_all_mode flag'ini de set et
                                    read_all_mode = True
                                    read_all_arm = arm
                                    print(f"🔍 TÜMÜNÜ OKU MODU AKTİF - Kol {arm}")
                    elif config_data.get('type') == 'data_retrieval_stop':
                        # Veri alma modunu durdur (JSON dosyasından)
                        set_data_retrieval_mode(False, None)
                        print(f"🛑 VERİ ALMA MODU DURDURULDU (JSON'dan)")
                    elif config_data.get('type') == 'reload_trap_targets':
                        # Trap hedeflerini yeniden yükle
                        load_trap_targets_to_ram()
                        print(f"🔄 Trap hedefleri yeniden yüklendi")
                    
                except Exception as e:
                    print(f"Konfigürasyon dosyası işlenirken hata: {e}")
                    if os.path.exists(config_file):
                        os.remove(config_file)
            time.sleep(1)
        except Exception as e:
            print(f"Config worker hatası: {e}")
            time.sleep(1)

def get_dynamic_data_by_index_new(start_index, quantity):
    """Dinamik veri indeksine göre veri döndür - YENİ MANTIK"""
    with data_lock:
        result = []
        
        print(f"DEBUG: Modbus isteği - Adres: {start_index}, Miktar: {quantity}")
        
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
        
        # YENİ MANTIK: Register mapping hesaplaması
        register_offset = start_index - arm_start  # Kol içindeki offset
        print(f"DEBUG: register_offset = {start_index} - {arm_start} = {register_offset}")
        
        print(f"DEBUG: Kol {target_arm} verileri işleniyor...")
        print(f"DEBUG: Başlangıç değerleri - start_index: {start_index}, arm_start: {arm_start}, target_arm: {target_arm}")
        print(f"DEBUG: battery_data_ram içeriği: {dict(battery_data_ram)}")
        print(f"DEBUG: arm_slave_counts_ram: {dict(arm_slave_counts_ram)}")
        
        # Sadece hedef kolu işle
        arm = target_arm
        
        # Kol verileri (Register 1-3: Akım, Nem, Sıcaklık)
        for i in range(quantity):
            current_register = start_index + i
            current_offset = current_register - arm_start
            
            print(f"DEBUG: İşlenen register: {current_register}, offset: {current_offset}")
            
            if current_offset <= 2:  # Kol verileri (0,1,2)
                # Kol verisi al
                try:
                    arm_data = dict(battery_data_ram.get(arm, {}))
                except Exception as e:
                    arm_data = None
                    
                if arm_data and 2 in arm_data:  # k=2 (kol verisi)
                    if current_offset == 0:  # Akım
                        value = arm_data[2].get(1, {}).get('value', 0)  # RAM dtype=1 (Akım)
                        print(f"DEBUG: Kol Akım: {value}")
                    elif current_offset == 1:  # Nem
                        value = arm_data[2].get(2, {}).get('value', 0)  # RAM dtype=2 (Nem)
                        print(f"DEBUG: Kol Nem: {value}")
                    elif current_offset == 2:  # Sıcaklık
                        value = arm_data[2].get(3, {}).get('value', 0)  # RAM dtype=3 (Sıcaklık)
                        print(f"DEBUG: Kol Sıcaklık: {value}")
                    else:
                        value = 0
                    result.append(float(value) if value else 0.0)
                else:
                    result.append(0.0)
            else:  # Batarya verileri (Register 4+)
                # Batarya hesaplaması
                battery_offset = current_offset - 3  # Kol verilerini atla
                battery_num = (battery_offset // 7) + 1  # Hangi batarya
                data_type_offset = battery_offset % 7  # Hangi veri tipi
                
                print(f"DEBUG: Batarya hesaplaması - battery_offset: {battery_offset}, battery_num: {battery_num}, data_type_offset: {data_type_offset}")
                
                # Batarya sayısı kontrolü
                battery_count = arm_slave_counts_ram.get(arm, 0)
                if battery_num > battery_count:
                    result.append(0.0)
                    print(f"DEBUG: Batarya {battery_num} mevcut değil (toplam: {battery_count})")
                    continue
                
                # Batarya verisi al
                k_value = battery_num + 2  # k=3,4,5,6...
                try:
                    arm_data = dict(battery_data_ram.get(arm, {}))
                except Exception as e:
                    arm_data = None
                    
                if arm_data and k_value in arm_data:
                    if data_type_offset == 0:  # Gerilim
                        value = arm_data[k_value].get(1, {}).get('value', 0)  # RAM dtype=1 (Gerilim)
                    elif data_type_offset == 1:  # SOC
                        value = arm_data[k_value].get(2, {}).get('value', 0)  # RAM dtype=2 (SOC)
                    elif data_type_offset == 2:  # RIMT
                        value = arm_data[k_value].get(3, {}).get('value', 0)  # RAM dtype=3 (RIMT)
                    elif data_type_offset == 3:  # SOH
                        value = arm_data[k_value].get(4, {}).get('value', 0)  # RAM dtype=4 (SOH)
                    elif data_type_offset == 4:  # NTC1
                        value = arm_data[k_value].get(5, {}).get('value', 0)  # RAM dtype=5 (NTC1)
                    elif data_type_offset == 5:  # NTC2
                        value = arm_data[k_value].get(6, {}).get('value', 0)  # RAM dtype=6 (NTC2)
                    elif data_type_offset == 6:  # NTC3
                        value = arm_data[k_value].get(7, {}).get('value', 0)  # RAM dtype=7 (NTC3)
                    else:
                        value = 0
                    result.append(float(value) if value else 0.0)
                    print(f"DEBUG: Batarya{battery_num} data_type_offset={data_type_offset} value={value}")
                else:
                    result.append(0.0)
                    print(f"DEBUG: Batarya{battery_num} verisi bulunamadı")
        
        # Temiz log - dönen verileri göster
        print(f"📊 Modbus Response: {len(result)} register döndürüldü")
        if result:
            print(f"🏭 Kol {target_arm}: Akım={result[0]:.1f}A, Nem={result[1]:.1f}%, Sıcaklık={result[2]:.1f}°C")
            
            # Tüm bataryaları göster
            battery_count = arm_slave_counts_ram.get(target_arm, 0)
            for i in range(min(battery_count, 5)):  # İlk 5 bataryayı göster
                start_idx = 4 + (i * 7)  # Her batarya 7 register
                if start_idx + 6 < len(result):
                    print(f"🔋 Batarya{i+1}: {result[start_idx]:.3f}V, SOC:{result[start_idx+1]:.1f}%, RIMT:{result[start_idx+2]:.1f}°C, SOH:{result[start_idx+3]:.1f}%, NTC1:{result[start_idx+4]:.1f}°C, NTC2:{result[start_idx+5]:.1f}°C, NTC3:{result[start_idx+6]:.1f}°C")
        return result

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
        
        # Status ve alarm RAM'lerini başlat (arm_slave_counts_ram dolu olduktan sonra)
        initialize_status_ram()
        initialize_alarm_ram()
        
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
        modbus_thread = threading.Thread(target=modbus_tcp_server, daemon=False)
        modbus_thread.start()
        print("Modbus TCP sunucu thread'i başlatıldı.")

        # SNMP sunucu thread'i
        snmp_thread = threading.Thread(target=snmp_server, daemon=False)
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
        
        print(f"DEBUG: Modbus isteği - Adres: {start_index}, Miktar: {quantity}")
        
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
        
        current_index = 1  # Register 1'den başla (kol verileri)
        
        print(f"DEBUG: Kol {target_arm} verileri işleniyor...")
        print(f"DEBUG: Başlangıç değerleri - start_index: {start_index}, current_index: {current_index}, target_arm: {target_arm}")
        print(f"DEBUG: battery_data_ram içeriği: {dict(battery_data_ram)}")
        print(f"DEBUG: arm_slave_counts_ram: {dict(arm_slave_counts_ram)}")
        
        
        # Sadece hedef kolu işle
        for arm in range(1, 5):  # Kol 1-4
            if arm != target_arm:
                continue  # Sadece hedef kolu işle
                
            
            # Kol verileri (akım, nem, sıcaklık, sıcaklık2)
            for data_type in range(1, 5):
                if current_index >= start_index and len(result) < quantity:
                    try:
                        arm_data = dict(battery_data_ram.get(arm, {}))
                    except Exception as e:
                        arm_data = None
                    if arm_data and 2 in arm_data:  # k=2 (kol verisi)
                        if data_type == 1:  # Akım
                            value = arm_data[2].get(1, {}).get('value', 0)  # RAM dtype=1 (Akım)
                        elif data_type == 2:  # Nem
                            value = arm_data[2].get(2, {}).get('value', 0)  # RAM dtype=2 (Nem)
                        elif data_type == 3:  # Sıcaklık
                            value = arm_data[2].get(3, {}).get('value', 0)  # RAM dtype=3 (Sıcaklık)
                        elif data_type == 4:  # Sıcaklık2
                            value = arm_data[2].get(4, {}).get('value', 0)  # RAM dtype=4 (Sıcaklık2)
                        else:
                            value = 0
                        result.append(float(value) if value else 0.0)
                    else:
                        result.append(0.0)
                else:
                    result.append(0.0)
                current_index += 1
                
                if len(result) >= quantity:
                    break
                    
            if len(result) >= quantity:
                break
                
            # Batarya verileri
            battery_count = arm_slave_counts_ram.get(arm, 0)
            print(f"DEBUG: {battery_count} batarya işleniyor...")
            for battery_num in range(1, battery_count + 1):
                k_value = battery_num + 2  # k=3,4,5,6...
                arm_data = dict(battery_data_ram.get(arm, {}))
                if arm_data and k_value in arm_data:
                    # Her batarya için 7 veri tipi
                    for data_type in range(5, 12):  # 5-11 (gerilim, soc, rint, soh, ntc1, ntc2, ntc3)
                        if current_index >= start_index and len(result) < quantity:
                            if data_type == 5:  # Gerilim
                                value = arm_data[k_value].get(1, {}).get('value', 0)  # RAM dtype=1 (Gerilim)
                            elif data_type == 6:  # SOC
                                value = arm_data[k_value].get(2, {}).get('value', 0)  # RAM dtype=2 (SOC)
                            elif data_type == 7:  # RIMT
                                value = arm_data[k_value].get(3, {}).get('value', 0)  # RAM dtype=3 (RIMT)
                            elif data_type == 8:  # SOH
                                value = arm_data[k_value].get(4, {}).get('value', 0)  # RAM dtype=4 (SOH)
                            elif data_type == 9:  # NTC1
                                value = arm_data[k_value].get(5, {}).get('value', 0)  # RAM dtype=5 (NTC1)
                            elif data_type == 10:  # NTC2
                                value = arm_data[k_value].get(6, {}).get('value', 0)  # RAM dtype=6 (NTC2)
                            elif data_type == 11:  # NTC3
                                value = arm_data[k_value].get(7, {}).get('value', 0)  # RAM dtype=7 (NTC3)
                            else:
                                value = 0
                            result.append(float(value) if value else 0.0)
                            print(f"DEBUG: Batarya{k_value-2} data_type={data_type} value={value}")
                        current_index += 1
                        
                        if len(result) >= quantity:
                            break
                            
                if len(result) >= quantity:
                    break
                    
            if len(result) >= quantity:
                break
                
        # Eksik registerler için 0.0 ekle
        while len(result) < quantity:
            result.append(0.0)
                
        # Temiz log - dönen verileri göster
        print(f"📊 Modbus Response: {len(result)} register döndürüldü")
        if result:
            print(f"🏭 Kol {target_arm}: Akım={result[0]:.1f}A, Nem={result[1]:.1f}%, Sıcaklık={result[2]:.1f}°C")
            
            # Tüm bataryaları göster
            battery_count = arm_slave_counts_ram.get(target_arm, 0)
            for i in range(min(battery_count, 5)):  # İlk 5 bataryayı göster
                start_idx = 4 + (i * 7)  # Her batarya 7 register
                if start_idx + 6 < len(result):
                    print(f"🔋 Batarya{i+1}: {result[start_idx]:.3f}V, SOC:{result[start_idx+1]:.1f}%, RIMT:{result[start_idx+2]:.1f}°C, SOH:{result[start_idx+3]:.1f}%, NTC1:{result[start_idx+4]:.1f}°C, NTC2:{result[start_idx+5]:.1f}°C, NTC3:{result[start_idx+6]:.1f}°C")
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
        
        # Başlangıç register'ından itibaren istenen miktarda alarm dön
        current_register = start_index
        max_battery_found = False  # Maksimum batarya sayısını geçtik mi?
        
        for i in range(quantity):
            # Hangi kolda olduğumuzu belirle (kol değişebilir)
            if 5001 <= current_register <= 5844:
                current_arm = 1
                current_arm_start = 5001
            elif 5845 <= current_register <= 6688:
                current_arm = 2
                current_arm_start = 5845
                max_battery_found = False  # Yeni kola geçtik, reset
            elif 6689 <= current_register <= 7532:
                current_arm = 3
                current_arm_start = 6689
                max_battery_found = False  # Yeni kola geçtik, reset
            elif 7533 <= current_register <= 8376:
                current_arm = 4
                current_arm_start = 7533
                max_battery_found = False  # Yeni kola geçtik, reset
            else:
                # Geçersiz aralık
                result.append(0)
                current_register += 1
                continue
            
            offset = current_register - current_arm_start  # Kol başlangıcından offset
            
            if 0 <= offset <= 3:
                # Kol alarmları (0-3 = alarm tip 1-4)
                alarm_type = offset + 1
                alarm_value = alarm_ram.get(current_arm, {}).get(0, {}).get(alarm_type, False)
                result.append(1 if alarm_value else 0)
                print(f"DEBUG: Register {current_register}: Kol {current_arm} alarm tip {alarm_type} = {alarm_value}")
            elif 4 <= offset <= 843:
                # Batarya alarmları (4-843 = 120 batarya × 7 alarm)
                battery_offset = offset - 4  # Kol alarmlarını atla (0'dan başla)
                battery_num = (battery_offset // 7) + 1  # Hangi batarya (1-120)
                alarm_type_index = battery_offset % 7    # 0-6 arası
                alarm_type = alarm_type_index + 1        # 1-7 arası alarm tipi
                
                # Optimizasyon: Eğer maksimum batarya aşıldıysa direkt 0 dön
                if max_battery_found:
                    result.append(0)
                    print(f"DEBUG: Register {current_register}: Kol {current_arm} Batarya {battery_num} - maksimum aşıldı, 0")
                else:
                    # RAM'de bu batarya var mı kontrol et
                    if battery_num in alarm_ram.get(current_arm, {}):
                        # RAM'de var - alarm değerini al
                        alarm_value = alarm_ram[current_arm][battery_num].get(alarm_type, False)
                        result.append(1 if alarm_value else 0)
                        print(f"DEBUG: Register {current_register}: Kol {current_arm} Batarya {battery_num} alarm tip {alarm_type} = {alarm_value}")
                    else:
                        # RAM'de yok - takılı değil - 0 dön ve flag set et
                        result.append(0)
                        max_battery_found = True  # Sonraki bataryalar da yok
                        print(f"DEBUG: Register {current_register}: Kol {current_arm} Batarya {battery_num} takılı değil - sonrakiler de yok")
            else:
                # Geçersiz offset - 0 dön
                result.append(0)
                print(f"DEBUG: Register {current_register}: Geçersiz offset {offset} - alarm = 0")
            
            current_register += 1
        
        print(f"DEBUG: Alarm sonuç: {result}")
        return result

def get_status_data_by_index(start_index, quantity):
    """Status verilerini indeksine göre döndür"""
    with status_lock:
        result = []
        current_index = start_index
        
        print(f"DEBUG: get_status_data_by_index start={start_index}, quantity={quantity}")
        
        # Aralık kontrolü (9001-9484)
        if start_index < 9001 or start_index > 9484:
            print(f"DEBUG: Geçersiz status aralığı! start_index={start_index} (9001-9484 arası olmalı)")
            return [0] * quantity
        
        # Hangi kol aralığında olduğunu belirle
        if 9001 <= start_index <= 9121:
            target_arm = 1
            arm_start = 9001
        elif 9122 <= start_index <= 9242:
            target_arm = 2
            arm_start = 9122
        elif 9243 <= start_index <= 9363:
            target_arm = 3
            arm_start = 9243
        elif 9364 <= start_index <= 9484:
            target_arm = 4
            arm_start = 9364
        else:
            print(f"DEBUG: Geçersiz status aralığı! start_index={start_index}")
            return [0] * quantity
        
        print(f"DEBUG: Hedef kol: {target_arm}, aralık: {arm_start}-{arm_start+120}")
        
        # Başlangıç register'ından itibaren istenen miktarda status dön
        current_register = start_index
        max_battery_found = False  # Maksimum batarya sayısını geçtik mi?
        
        for i in range(quantity):
            # Hangi kolda olduğumuzu belirle (kol değişebilir)
            if 9001 <= current_register <= 9121:
                current_arm = 1
                current_arm_start = 9001
            elif 9122 <= current_register <= 9242:
                current_arm = 2
                current_arm_start = 9122
                max_battery_found = False  # Yeni kola geçtik, reset
            elif 9243 <= current_register <= 9363:
                current_arm = 3
                current_arm_start = 9243
                max_battery_found = False  # Yeni kola geçtik, reset
            elif 9364 <= current_register <= 9484:
                current_arm = 4
                current_arm_start = 9364
                max_battery_found = False  # Yeni kola geçtik, reset
            else:
                # Geçersiz aralık
                result.append(0)
                current_register += 1
                continue
            
            offset = current_register - current_arm_start  # Kol başlangıcından offset
            
            if offset == 0:
                # Kol statusu
                status_value = status_ram.get(current_arm, {}).get(0, True)
                result.append(1 if status_value else 0)
                print(f"DEBUG: Register {current_register}: Kol {current_arm} status = {status_value}")
            elif 1 <= offset <= 120:
                # Batarya statusu (offset = batarya numarası)
                battery_num = offset
                
                # Optimizasyon: Eğer önceki batarya yoktu ve aynı koldaysak, direkt 0 dön
                if max_battery_found:
                    result.append(0)
                    print(f"DEBUG: Register {current_register}: Kol {current_arm} Batarya {battery_num} - maksimum aşıldı, 0")
                else:
                    # RAM'de bu batarya var mı kontrol et
                    if battery_num in status_ram.get(current_arm, {}):
                        # RAM'de var - değerini al
                        status_value = status_ram[current_arm][battery_num]
                        result.append(1 if status_value else 0)
                        print(f"DEBUG: Register {current_register}: Kol {current_arm} Batarya {battery_num} status = {status_value}")
                    else:
                        # RAM'de yok - takılı değil - 0 dön ve flag set et
                        result.append(0)
                        max_battery_found = True  # Sonraki bataryalar da yok
                        print(f"DEBUG: Register {current_register}: Kol {current_arm} Batarya {battery_num} takılı değil - sonrakiler de yok")
            else:
                # Geçersiz offset - 0 dön
                result.append(0)
                print(f"DEBUG: Register {current_register}: Geçersiz offset {offset} - status = 0")
            
            current_register += 1
        
        print(f"DEBUG: Status sonuç: {result}")
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

def load_arm_slave_counts_from_db():
    """DB'den arm_slave_counts değerlerini çekip RAM'e aktar"""
    try:
        with db_lock:
            with db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT arm, slave_count FROM arm_slave_counts ORDER BY arm")
                rows = cursor.fetchall()
                
                if rows:
                    for arm, slave_count in rows:
                        arm_slave_counts_ram[arm] = slave_count
                        print(f"✓ DB'den yüklendi - Kol {arm}: {slave_count} batarya")
                else:
                    # DB'de veri yoksa varsayılan değerler
                    for arm in range(1, 5):
                        arm_slave_counts_ram[arm] = 0
                        print(f"⚠️ DB'de veri yok - Kol {arm}: 0 batarya (varsayılan)")
                        
    except Exception as e:
        print(f"❌ DB'den arm_slave_counts yükleme hatası: {e}")
        # Hata durumunda varsayılan değerler
        for arm in range(1, 5):
            arm_slave_counts_ram[arm] = 0

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
        import traceback
        traceback.print_exc()

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
    """UART verilerine göre alarm koşullarını kontrol et ve RAM'e kaydet"""
    try:
        # Alarm türlerini sıfırla (önce tüm alarmları kapat)
        alarm_types = [1, 2, 3, 4, 5, 6, 7]  # LVoltageWarn, LVoltageAlarm, OVoltageWarn, OVoltageAlarm, OvertempD, OvertempP, OvertempN
        for alarm_type in alarm_types:
            update_alarm_ram(arm, battery, alarm_type, False)
        
        # Eğer error_msb ve error_lsb varsa, alarmları işle
        if 'error_msb' in data and 'error_lsb' in data:
            error_msb = data['error_msb']
            error_lsb = data['error_lsb']
            
            # Özel durum: error_msb=1 ve error_lsb=1 düzeltme sinyali (tüm alarmları temizle, yeni alarm aktif etme)
            if error_msb == 1 and error_lsb == 1:
                print(f"🔧 Düzeltme sinyali - Tüm alarmlar temizlendi - Kol {arm}, Batarya {battery}")
                # Tüm alarmlar zaten False yapıldı, başka bir şey yapmaya gerek yok
                return
            
            # MSB kontrolü (bit flag sistemi)
            if error_msb & 1:  # Bit 0 set - Pozitif kutup başı alarmı
                update_alarm_ram(arm, battery, 6, True)  # OvertempP
            if error_msb & 2:  # Bit 1 set - Negatif kutup başı sıcaklık alarmı
                update_alarm_ram(arm, battery, 7, True)  # OvertempN
            
            # LSB kontrolü (bit flag sistemi)
            if error_lsb & 4:   # Bit 2 set - Düşük batarya gerilim uyarısı
                update_alarm_ram(arm, battery, 1, True)  # LVoltageWarn
            if error_lsb & 8:   # Bit 3 set - Düşük batarya gerilimi alarmı
                update_alarm_ram(arm, battery, 2, True)  # LVoltageAlarm
            if error_lsb & 16:  # Bit 4 set - Yüksek batarya gerilimi uyarısı
                update_alarm_ram(arm, battery, 3, True)  # OVoltageWarn
            if error_lsb & 32:  # Bit 5 set - Yüksek batarya gerilimi alarmı
                update_alarm_ram(arm, battery, 4, True)  # OVoltageAlarm
            if error_lsb & 64:  # Bit 6 set - Modül sıcaklık alarmı
                update_alarm_ram(arm, battery, 5, True)  # OvertempD
                
            print(f"🔍 Alarm koşulları kontrol edildi - Kol {arm}, Batarya {battery}, MSB: {error_msb}, LSB: {error_lsb}")
        
    except Exception as e:
        print(f"❌ Alarm koşulları kontrol hatası: {e}")

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
                    daemon=False
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
        elif 5001 <= start_address <= 8376:  # Alarm verileri
            # Alarm verilerini döndür
            registers = get_alarm_data_by_index(start_address, quantity)
        elif 9001 <= start_address <= 9484:  # Status verileri
            # Status verilerini döndür
            registers = get_status_data_by_index(start_address, quantity)
        elif start_address >= 1:  # Dinamik veri okuma
            # Dinamik veri sistemi kullan
            try:
                registers = get_dynamic_data_by_index_new(start_address, quantity)
            except Exception as e:
                print(f"get_dynamic_data_by_index_new hatası: {e}")
                registers = [0.0] * quantity
        
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
        elif 5001 <= start_address <= 8376:  # Alarm verileri
            registers = get_alarm_data_by_index(start_address, quantity)
        elif 9001 <= start_address <= 9484:  # Status verileri
            registers = get_status_data_by_index(start_address, quantity)
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
        
        print(f"DEBUG: Modbus isteği - Adres: {start_index}, Miktar: {quantity}")
        
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
        
        current_index = 1  # Register 1'den başla (kol verileri)
        
        print(f"DEBUG: Kol {target_arm} verileri işleniyor...")
        print(f"DEBUG: Başlangıç değerleri - start_index: {start_index}, current_index: {current_index}, target_arm: {target_arm}")
        print(f"DEBUG: battery_data_ram içeriği: {dict(battery_data_ram)}")
        print(f"DEBUG: arm_slave_counts_ram: {dict(arm_slave_counts_ram)}")
        
        
        # Sadece hedef kolu işle
        for arm in range(1, 5):  # Kol 1-4
            if arm != target_arm:
                continue  # Sadece hedef kolu işle
                
            
            # Kol verileri (akım, nem, sıcaklık, sıcaklık2)
            for data_type in range(1, 5):
                if current_index >= start_index and len(result) < quantity:
                    try:
                        arm_data = dict(battery_data_ram.get(arm, {}))
                    except Exception as e:
                        arm_data = None
                    if arm_data and 2 in arm_data:  # k=2 (kol verisi)
                        if data_type == 1:  # Akım
                            value = arm_data[2].get(1, {}).get('value', 0)  # RAM dtype=1 (Akım)
                        elif data_type == 2:  # Nem
                            value = arm_data[2].get(2, {}).get('value', 0)  # RAM dtype=2 (Nem)
                        elif data_type == 3:  # Sıcaklık
                            value = arm_data[2].get(3, {}).get('value', 0)  # RAM dtype=3 (Sıcaklık)
                        elif data_type == 4:  # Sıcaklık2
                            value = arm_data[2].get(4, {}).get('value', 0)  # RAM dtype=4 (Sıcaklık2)
                        else:
                            value = 0
                        result.append(float(value) if value else 0.0)
                    else:
                        result.append(0.0)
                else:
                    result.append(0.0)
                current_index += 1
                
                if len(result) >= quantity:
                    break
                    
            if len(result) >= quantity:
                break
                
            # Batarya verileri
            battery_count = arm_slave_counts_ram.get(arm, 0)
            print(f"DEBUG: {battery_count} batarya işleniyor...")
            for battery_num in range(1, battery_count + 1):
                k_value = battery_num + 2  # k=3,4,5,6...
                arm_data = dict(battery_data_ram.get(arm, {}))
                if arm_data and k_value in arm_data:
                    # Her batarya için 7 veri tipi
                    for data_type in range(5, 12):  # 5-11 (gerilim, soc, rint, soh, ntc1, ntc2, ntc3)
                        if current_index >= start_index and len(result) < quantity:
                            if data_type == 5:  # Gerilim
                                value = arm_data[k_value].get(1, {}).get('value', 0)  # RAM dtype=1 (Gerilim)
                            elif data_type == 6:  # SOC
                                value = arm_data[k_value].get(2, {}).get('value', 0)  # RAM dtype=2 (SOC)
                            elif data_type == 7:  # RIMT
                                value = arm_data[k_value].get(3, {}).get('value', 0)  # RAM dtype=3 (RIMT)
                            elif data_type == 8:  # SOH
                                value = arm_data[k_value].get(4, {}).get('value', 0)  # RAM dtype=4 (SOH)
                            elif data_type == 9:  # NTC1
                                value = arm_data[k_value].get(5, {}).get('value', 0)  # RAM dtype=5 (NTC1)
                            elif data_type == 10:  # NTC2
                                value = arm_data[k_value].get(6, {}).get('value', 0)  # RAM dtype=6 (NTC2)
                            elif data_type == 11:  # NTC3
                                value = arm_data[k_value].get(7, {}).get('value', 0)  # RAM dtype=7 (NTC3)
                            else:
                                value = 0
                            result.append(float(value) if value else 0.0)
                            print(f"DEBUG: Batarya{k_value-2} data_type={data_type} value={value}")
                        current_index += 1
                        
                        if len(result) >= quantity:
                            break
                            
                if len(result) >= quantity:
                    break
                    
            if len(result) >= quantity:
                break
                
        # Eksik registerler için 0.0 ekle
        while len(result) < quantity:
                            result.append(0.0)
                
        # Temiz log - dönen verileri göster
        print(f"📊 Modbus Response: {len(result)} register döndürüldü")
        if result:
            print(f"🏭 Kol {target_arm}: Akım={result[0]:.1f}A, Nem={result[1]:.1f}%, Sıcaklık={result[2]:.1f}°C")
            
            # Tüm bataryaları göster
            battery_count = arm_slave_counts_ram.get(target_arm, 0)
            for i in range(min(battery_count, 5)):  # İlk 5 bataryayı göster
                start_idx = 4 + (i * 7)  # Her batarya 7 register
                if start_idx + 6 < len(result):
                    print(f"🔋 Batarya{i+1}: {result[start_idx]:.3f}V, SOC:{result[start_idx+1]:.1f}%, RIMT:{result[start_idx+2]:.1f}°C, SOH:{result[start_idx+3]:.1f}%, NTC1:{result[start_idx+4]:.1f}°C, NTC2:{result[start_idx+5]:.1f}°C, NTC3:{result[start_idx+6]:.1f}°C")
        return result

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
    """SNMP trap gönder - MIB uyumlu"""
    try:
        with trap_targets_lock:
            # trap_enabled kontrolü yap (varsa)
            active_targets = []
            for target in trap_targets_ram:
                # trap_enabled kolonu varsa onu kullan, yoksa is_active kullan
                if target.get('trap_enabled') is not None:
                    if target.get('trap_enabled') and target.get('is_active', True):
                        active_targets.append(target)
                elif target.get('is_active'):
                    active_targets.append(target)
        
        if not active_targets:
            print("⚠️ Aktif trap hedefi yok, trap gönderilmedi")
            return
        
        # Alarm bilgilerini oluştur
        # Alarm ID: timestamp bazlı benzersiz ID
        alarm_id = int(time.time() * 1000) % 2147483647  # PositiveInteger için
        
        # Alarm açıklaması
        alarm_type_names = {
            1: "Yüksek Akım",
            2: "Yüksek Nem",
            3: "Yüksek Ortam Sıcaklığı",
            4: "Yüksek Kol Sıcaklığı",
            11: "Düşük Gerilim Uyarısı",
            12: "Düşük Gerilim Alarmı",
            13: "Yüksek Gerilim Uyarısı",
            14: "Yüksek Gerilim Alarmı",
            15: "Modül Sıcaklık Alarmı",
            16: "Pozitif Kutup Sıcaklık Alarmı",
            17: "Negatif Kutup Sıcaklık Alarmı"
        }
        
        alarm_type_name = alarm_type_names.get(alarm_type, f"Alarm Tipi {alarm_type}")
        alarm_description = f"Kol {arm}"
        if battery > 0:
            alarm_description += f" Batarya {battery} - {alarm_type_name}"
        else:
            alarm_description += f" - {alarm_type_name}"
        
        # MIB'deki trap OID'lerini kullan
        if status:  # Alarm aktif
            trap_oid = '1.3.6.1.4.1.1001.5.1'  # tescomAlarmTrap
        else:  # Alarm çözüldü
            trap_oid = '1.3.6.1.4.1.1001.5.2'  # tescomAlarmClearedTrap
        
        # MIB'deki OBJECTS: alarmId, alarmArmIndex, alarmBatteryIndex, alarmType, alarmDescription
        # MIB OID'leri:
        # alarmId: 1.3.6.1.4.1.1001.4.4.1.1
        # alarmArmIndex: 1.3.6.1.4.1.1001.4.4.1.2
        # alarmBatteryIndex: 1.3.6.1.4.1.1001.4.4.1.3
        # alarmType: 1.3.6.1.4.1.1001.4.4.1.4
        # alarmDescription: 1.3.6.1.4.1.1001.4.4.1.5
        
        status_text = "AKTIF" if status else "ÇÖZÜLDÜ"
        print(f"📤 Trap gönderiliyor: Kol {arm}, Batarya {battery}, Alarm Tipi {alarm_type}, Durum: {status_text}")
        
        # Her aktif hedefe trap gönder
        for target in active_targets:
            try:
                send_single_trap(
                    target_ip=target['ip_address'],
                    target_port=target['port'],
                    trap_community=target.get('trap_community', 'public'),
                    trap_oid=trap_oid,
                    alarm_id=alarm_id,
                    alarm_arm_index=arm,
                    alarm_battery_index=battery,
                    alarm_type=alarm_type,
                    alarm_description=alarm_description
                )
                print(f"✅ Trap gönderildi: {target['name']} ({target['ip_address']}:{target['port']})")
            except Exception as e:
                print(f"❌ Trap gönderme hatası {target['name']}: {e}")
                
    except Exception as e:
        print(f"❌ Trap gönderme genel hatası: {e}")

def send_single_trap(target_ip, target_port, trap_community='public', trap_oid=None, alarm_id=None, alarm_arm_index=None, alarm_battery_index=None, alarm_type=None, alarm_description=None):
    """Tek bir trap gönder - MIB uyumlu"""
    try:
        # MIB'deki OBJECTS tanımına göre trap gönder
        # tescomAlarmTrap ve tescomAlarmClearedTrap OBJECTS:
        # - alarmId (1.3.6.1.4.1.1001.4.4.1.1)
        # - alarmArmIndex (1.3.6.1.4.1.1001.4.4.1.2)
        # - alarmBatteryIndex (1.3.6.1.4.1.1001.4.4.1.3)
        # - alarmType (1.3.6.1.4.1.1001.4.4.1.4)
        # - alarmDescription (1.3.6.1.4.1.1001.4.4.1.5)
        
        var_binds = [
            ObjectType(ObjectIdentity('1.3.6.1.4.1.1001.4.4.1.1'), Integer(alarm_id)),  # alarmId
            ObjectType(ObjectIdentity('1.3.6.1.4.1.1001.4.4.1.2'), Integer(alarm_arm_index)),  # alarmArmIndex
            ObjectType(ObjectIdentity('1.3.6.1.4.1.1001.4.4.1.3'), Integer(alarm_battery_index)),  # alarmBatteryIndex
            ObjectType(ObjectIdentity('1.3.6.1.4.1.1001.4.4.1.4'), Integer(alarm_type)),  # alarmType
            ObjectType(ObjectIdentity('1.3.6.1.4.1.1001.4.4.1.5'), OctetString(alarm_description[:255]))  # alarmDescription (max 255)
        ]
        
        # SNMP Trap gönder
        errorIndication, errorStatus, errorIndex, varBinds = next(
            sendNotification(
                SnmpEngine(),
                CommunityData(trap_community),
                UdpTransportTarget((target_ip, target_port)),
                ContextData(),
                'trap',
                NotificationType(
                    ObjectIdentity(trap_oid),
                    var_binds
                )
            )
        )
        
        if errorIndication:
            print(f"❌ Trap hatası: {errorIndication}")
        else:
            print(f"✅ Trap başarılı: {target_ip}")
            
    except Exception as e:
        print(f"❌ Trap gönderme hatası: {e}")
        import traceback
        traceback.print_exc()

def get_battery_data_ram(arm=None, k=None, dtype=None):
    """RAM'den batarya verisi al - modbus_snmp.py'den kopyalandı"""
    if arm is None and k is None and dtype is None:
        # Tüm veriyi döndür
        with data_lock:
            return battery_data_ram.copy()
    
    # Belirli veriyi döndür
    with data_lock:
        if arm in battery_data_ram and k in battery_data_ram[arm]:
            return battery_data_ram[arm][k].get(dtype, {})
        return {}

def snmp_server():
    """SNMP sunucu thread'i - modbus_snmp.py'den kopyalandı"""
    print("🚀 SNMP Agent Başlatılıyor...")
    print("📊 Modbus TCP Server RAM Sistemi ile Entegre")
    
    try:
        # Log dosyası yolu - mevcut dizine göre ayarla
        script_dir = os.path.dirname(os.path.abspath(__file__)) if '__file__' in globals() else os.getcwd()
        snmp_log_path = os.path.join(script_dir, "snmp_requests.log")
        print(f"📝 SNMP log dosyası: {snmp_log_path}")
        
        # Thread için yeni event loop oluştur
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        # Create SNMP engine
        snmpEngine = engine.SnmpEngine()
        print("✅ SNMP Engine oluşturuldu")

        # Transport setup - UDP over IPv4
        print(f"🔧 Transport oluşturuluyor: {SNMP_HOST}:{SNMP_PORT}")
        udp_transport = udp.UdpTransport()
        transport_fd = udp_transport.open_server_mode((SNMP_HOST, SNMP_PORT))
        config.add_transport(snmpEngine, udp.DOMAIN_NAME, transport_fd)
        print(f"✅ Transport ayarlandı ve açıldı: {SNMP_HOST}:{SNMP_PORT}")

        # SNMPv2c setup
        config.add_v1_system(snmpEngine, "my-area", "public")
        print("✅ SNMPv2c ayarlandı")

        # Allow read MIB access for this user / securityModels at VACM
        config.add_vacm_user(snmpEngine, 2, "my-area", "noAuthNoPriv", (1, 3, 6, 5))
        config.add_vacm_user(snmpEngine, 2, "my-area", "noAuthNoPriv", (1, 3, 6, 1, 4, 1, 1001))
        print("✅ VACM ayarlandı")

        # Create an SNMP context
        snmpContext = context.SnmpContext(snmpEngine)
        print("✅ SNMP Context oluşturuldu")

        # --- create custom Managed Object Instance ---
        mibBuilder = snmpContext.get_mib_instrum().get_mib_builder()

        MibScalar, MibScalarInstance = mibBuilder.import_symbols(
            "SNMPv2-SMI", "MibScalar", "MibScalarInstance"
        )
        print("✅ MIB Builder oluşturuldu")

        class ModbusRAMMibScalarInstance(MibScalarInstance):
            """Modbus TCP Server RAM sistemi ile MIB Instance - MIB TABLE yapısına uyumlu"""
            def getValue(self, name, **context):
                oid = '.'.join([str(x) for x in name])
                import sys
                import datetime
                import traceback
                
                # Log dosyası yolu
                script_dir = os.path.dirname(os.path.abspath(__file__)) if '__file__' in globals() else os.getcwd()
                log_path = os.path.join(script_dir, "snmp_requests.log")
                
                try:
                    # STDOUT'A YAZDIR - tümünü oku gibi
                    log_msg = f"📡 SNMP GET isteği - OID: {oid}"
                    print(log_msg)
                    
                    # DOSYAYA DA YAZDIR
                    try:
                        with open(log_path, "a") as f:
                            f.write(f"{datetime.datetime.now()} - getValue ÇAĞRILDI - OID: {oid}\n")
                            f.flush()  # Hemen yaz
                    except Exception as log_err:
                        # Log yazma hatası sessizce geçiliyor
                        pass
                    
                    # .0 eklemeden çalış - hem .0 ile hem .0 olmadan kabul et
                    # OID sonundaki .0'ı kaldır (varsa)
                    if oid.endswith('.0'):
                        oid = oid[:-2]
                    
                    # Sistem bilgileri - ESKİ TEST OID'leri (1.3.6.5.x)
                    if oid == "1.3.6.5.1":
                        return self.getSyntax().clone(
                            f"SNMP-V2 Python {sys.version} running on {sys.platform}"
                        )
                    elif oid == "1.3.6.5.2":  # totalBatteryCount
                        data = get_battery_data_ram()
                        battery_count = 0
                        for arm in data.keys():
                            for k in data[arm].keys():
                                if k > 2:  # k>2 olanlar batarya verisi
                                    battery_count += 1
                        return self.getSyntax().clone(str(battery_count if battery_count > 0 else 0))
                    elif oid == "1.3.6.5.3":  # totalArmCount
                        data = get_battery_data_ram()
                        return self.getSyntax().clone(str(len(data) if data else 0))
                    elif oid == "1.3.6.5.4":  # systemStatus
                        return self.getSyntax().clone("1")
                    elif oid == "1.3.6.5.5":  # lastUpdateTime
                        return self.getSyntax().clone(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                    elif oid == "1.3.6.5.6":  # dataCount
                        data = get_battery_data_ram()
                        total_data = 0
                        for arm in data.values():
                            for k in arm.values():
                                total_data += len(k)
                        return self.getSyntax().clone(str(total_data if total_data > 0 else 0))
                    
                    # ============================================
                    # MIB UYUMLU OID'LER (1.3.6.1.4.1.1001.x)
                    # ============================================
                    
                    # Sistem bilgileri - tescomBmsSystem (1.3.6.1.4.1.1001.1.x)
                    elif oid == "1.3.6.1.4.1.1001.1.1":  # systemInfo
                        return self.getSyntax().clone(
                            f"TESCOM BMS - Python {sys.version.split()[0]} on {sys.platform}"
                        )
                    elif oid == "1.3.6.1.4.1.1001.1.2":  # totalBatteryCount
                        data = get_battery_data_ram()
                        battery_count = 0
                        for arm in data.keys():
                            for k in data[arm].keys():
                                if k > 2:  # k>2 olanlar batarya verisi
                                    battery_count += 1
                        return self.getSyntax().clone(battery_count)
                    elif oid == "1.3.6.1.4.1.1001.1.3":  # totalArmCount
                        data = get_battery_data_ram()
                        return self.getSyntax().clone(len(data) if data else 0)
                    elif oid == "1.3.6.1.4.1.1001.1.4":  # systemStatus
                        return self.getSyntax().clone(1)  # 1=running
                    elif oid == "1.3.6.1.4.1.1001.1.5":  # lastUpdateTime
                        return self.getSyntax().clone(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                    elif oid == "1.3.6.1.4.1.1001.1.6":  # dataCount
                        data = get_battery_data_ram()
                        total_data = 0
                        for arm in data.values():
                            for k in arm.values():
                                total_data += len(k)
                        return self.getSyntax().clone(total_data if total_data > 0 else 0)
                    
                    # Alarm sayıları - tescomBmsAlarms (1.3.6.1.4.1.1001.4.x)
                    elif oid == "1.3.6.1.4.1.1001.4.1":  # tescomAlarmsPresent
                        with data_lock:
                            total_alarms = 0
                            if alarm_ram:
                                for arm_alarms in alarm_ram.values():
                                    for battery_alarms in arm_alarms.values():
                                        for alarm_value in battery_alarms.values():
                                            if alarm_value:
                                                total_alarms += 1
                            return self.getSyntax().clone(total_alarms)
                    elif oid == "1.3.6.1.4.1.1001.4.2":  # tescomArmAlarmsPresent
                        with data_lock:
                            arm_alarms = 0
                            if alarm_ram:
                                for arm_data in alarm_ram.values():
                                    if 0 in arm_data:  # battery=0 kol alarmları
                                        for alarm_value in arm_data[0].values():
                                            if alarm_value:
                                                arm_alarms += 1
                            return self.getSyntax().clone(arm_alarms)
                    elif oid == "1.3.6.1.4.1.1001.4.3":  # tescomBatteryAlarmsPresent
                        with data_lock:
                            battery_alarms = 0
                            if alarm_ram:
                                for arm_data in alarm_ram.values():
                                    for battery_id, battery_alarms_data in arm_data.items():
                                        if battery_id > 0:  # battery>0 batarya alarmları
                                            for alarm_value in battery_alarms_data.values():
                                                if alarm_value:
                                                    battery_alarms += 1
                            return self.getSyntax().clone(battery_alarms)
                    
                    else:
                        # OID parsing - MIB TABLE yapısına göre
                        if oid.startswith("1.3.6.1.4.1.1001."):
                            parts = oid.split('.')
                            
                            # ============================================
                            # armTable - 1.3.6.1.4.1.1001.2.1.1.{column}.{armIndex}
                            # ============================================
                            if len(parts) >= 11 and parts[7:10] == ["2", "1", "1"]:
                                column = int(parts[10])  # Column numarası (2-8) - MIB uyumlu
                                
                                # armIndex var mı?
                                if len(parts) >= 12:
                                    arm_index = int(parts[11])  # armIndex (1-4)
                                    
                                    with data_lock:
                                        # Column 2: armSlaveCount
                                        if column == 2:
                                            return self.getSyntax().clone(arm_slave_counts_ram.get(arm_index, 0))
                                        
                                        # Column 3: armCurrent (k=2, dtype=1) - String formatında gönder
                                        elif column == 3:
                                            if arm_index in battery_data_ram and 2 in battery_data_ram[arm_index]:
                                                if 1 in battery_data_ram[arm_index][2]:
                                                    value = battery_data_ram[arm_index][2][1].get('value', 0)
                                                    return self.getSyntax().clone(f"{value:.1f}")  # Ampere (virgüllü)
                                            return self.getSyntax().clone("0.0")
                                        
                                        # Column 4: armHumidity (k=2, dtype=2) - String formatında gönder (tam sayı - 100'ü geçmez)
                                        elif column == 4:
                                            if arm_index in battery_data_ram and 2 in battery_data_ram[arm_index]:
                                                if 2 in battery_data_ram[arm_index][2]:
                                                    value = battery_data_ram[arm_index][2][2].get('value', 0)
                                                    return self.getSyntax().clone(f"{int(value)}")  # % (tam sayı)
                                            return self.getSyntax().clone("0")
                                        
                                        # Column 5: armNtc1Temp (k=2, dtype=3) - String formatında gönder
                                        elif column == 5:
                                            if arm_index in battery_data_ram and 2 in battery_data_ram[arm_index]:
                                                if 3 in battery_data_ram[arm_index][2]:
                                                    value = battery_data_ram[arm_index][2][3].get('value', 0)
                                                    return self.getSyntax().clone(f"{value:.1f}")  # Celsius (virgüllü)
                                            return self.getSyntax().clone("0.0")
                                        
                                        # Column 6: armNtc2Temp (k=2, dtype=4) - String formatında gönder
                                        elif column == 6:
                                            if arm_index in battery_data_ram and 2 in battery_data_ram[arm_index]:
                                                if 4 in battery_data_ram[arm_index][2]:
                                                    value = battery_data_ram[arm_index][2][4].get('value', 0)
                                                    return self.getSyntax().clone(f"{value:.1f}")  # Celsius (virgüllü)
                                            return self.getSyntax().clone("0.0")
                                        
                                        # Column 7: armStatus
                                        elif column == 7:
                                            if arm_index in status_ram and 0 in status_ram[arm_index]:
                                                return self.getSyntax().clone(1 if status_ram[arm_index][0] else 0)
                                            return self.getSyntax().clone(0)
                                        
                                        # Column 8: armAlarmFlags (HEX bitmask - MIB uyumlu)
                                        # 0x1=Yüksek Akım, 0x2=Yüksek Nem, 0x4=Yüksek Ortam Sıcaklığı, 0x8=Yüksek Kol Sıcaklığı
                                        elif column == 8:
                                            if arm_index in alarm_ram and 0 in alarm_ram[arm_index]:
                                                flags = 0
                                                if alarm_ram[arm_index][0].get(1, False):  # Yüksek Akım
                                                    flags |= 0x1
                                                if alarm_ram[arm_index][0].get(2, False):  # Yüksek Nem
                                                    flags |= 0x2
                                                if alarm_ram[arm_index][0].get(3, False):  # Yüksek Ortam Sıcaklığı
                                                    flags |= 0x4
                                                if alarm_ram[arm_index][0].get(4, False):  # Yüksek Kol Sıcaklığı
                                                    flags |= 0x8
                                                return self.getSyntax().clone(flags)
                                            return self.getSyntax().clone(0)
                        
                            # ============================================
                            # batteryTable - 1.3.6.1.4.1.1001.3.1.1.{column}.{armIndex}.{batteryIndex}
                            # ============================================
                            elif len(parts) >= 12 and parts[7:10] == ["3", "1", "1"]:
                                column = int(parts[10])         # Column numarası (3-11) - MIB uyumlu
                                # armIndex var mı?
                                if len(parts) >= 12:
                                    arm_index = int(parts[11])      # armIndex (1-4)
                                else:
                                    arm_index = None
                                # batteryIndex var mı?
                                if len(parts) >= 13:
                                    battery_index = int(parts[12])  # batteryIndex (1-120)
                                else:
                                    battery_index = None
                                
                                # Eğer armIndex veya batteryIndex yoksa varsayılan dön
                                if arm_index is None or battery_index is None:
                                    print(f"   ⚠️  batteryTable: arm_index={arm_index}, battery_index={battery_index} - None")
                                    return self.getSyntax().clone(0)
                                
                                # battery_index'i k değerine çevir (k = battery_index + 2)
                                k = battery_index + 2
                                
                                with data_lock:
                                    # 120 batarya sınırına kadar izin ver (takılı olmasa bile)
                                    max_battery = arm_slave_counts_ram.get(arm_index, 0)
                                    if battery_index > 120:
                                        print(f"   ⚠️  batteryTable: battery_index {battery_index} > 120 (maksimum sınır)")
                                        return self.getSyntax().clone(0)
                                    
                                    # Takılı olmayan bataryalar için 0 dön (No Such Object yerine)
                                    if battery_index > max_battery:
                                        # Takılı değil ama 120 sınırı içinde - 0 dön
                                        return self.getSyntax().clone(0)
                                    
                                    # Column 3: batteryVoltage (dtype=1) - String formatında gönder
                                    if column == 3:
                                        if arm_index in battery_data_ram and k in battery_data_ram[arm_index]:
                                            if 1 in battery_data_ram[arm_index][k]:
                                                value = battery_data_ram[arm_index][k][1].get('value', 0)
                                                return self.getSyntax().clone(f"{value:.1f}")  # mV (virgüllü)
                                        return self.getSyntax().clone("0.0")
                                    
                                    # Column 4: batterySoc (dtype=2) - String formatında gönder (tam sayı - 100'ü geçmez)
                                    elif column == 4:
                                        if arm_index in battery_data_ram and k in battery_data_ram[arm_index]:
                                            if 2 in battery_data_ram[arm_index][k]:
                                                value = battery_data_ram[arm_index][k][2].get('value', 0)
                                                return self.getSyntax().clone(f"{int(value)}")  # % (tam sayı)
                                        return self.getSyntax().clone("0")
                                    
                                    # Column 5: batteryRimt (dtype=3) - String formatında gönder
                                    elif column == 5:
                                        if arm_index in battery_data_ram and k in battery_data_ram[arm_index]:
                                            if 3 in battery_data_ram[arm_index][k]:
                                                value = battery_data_ram[arm_index][k][3].get('value', 0)
                                                return self.getSyntax().clone(f"{value:.1f}")  # mOhm (virgüllü)
                                        return self.getSyntax().clone("0.0")
                                    
                                    # Column 6: batterySoh (dtype=4) - String formatında gönder (tam sayı - 100'ü geçmez)
                                    elif column == 6:
                                        if arm_index in battery_data_ram and k in battery_data_ram[arm_index]:
                                            if 4 in battery_data_ram[arm_index][k]:
                                                value = battery_data_ram[arm_index][k][4].get('value', 0)
                                                return self.getSyntax().clone(f"{int(value)}")  # % (tam sayı)
                                        return self.getSyntax().clone("0")
                                    
                                    # Column 7: batteryNtc1 (dtype=5) - String formatında gönder
                                    elif column == 7:
                                        if arm_index in battery_data_ram and k in battery_data_ram[arm_index]:
                                            if 5 in battery_data_ram[arm_index][k]:
                                                value = battery_data_ram[arm_index][k][5].get('value', 0)
                                                return self.getSyntax().clone(f"{value:.1f}")  # Celsius (virgüllü)
                                        return self.getSyntax().clone("0.0")
                                    
                                    # Column 8: batteryNtc2 (dtype=6) - String formatında gönder
                                    elif column == 8:
                                        if arm_index in battery_data_ram and k in battery_data_ram[arm_index]:
                                            if 6 in battery_data_ram[arm_index][k]:
                                                value = battery_data_ram[arm_index][k][6].get('value', 0)
                                                return self.getSyntax().clone(f"{value:.1f}")  # Celsius (virgüllü)
                                        return self.getSyntax().clone("0.0")
                                    
                                    # Column 9: batteryNtc3 (dtype=7) - String formatında gönder
                                    elif column == 9:
                                        if arm_index in battery_data_ram and k in battery_data_ram[arm_index]:
                                            if 7 in battery_data_ram[arm_index][k]:
                                                value = battery_data_ram[arm_index][k][7].get('value', 0)
                                                return self.getSyntax().clone(f"{value:.1f}")  # Celsius (virgüllü)
                                        return self.getSyntax().clone("0.0")
                                
                                # Column 10: batteryStatus (data_lock gerekmez - status_ram için)
                                if column == 10:
                                    if arm_index in status_ram and battery_index in status_ram[arm_index]:
                                        return self.getSyntax().clone(1 if status_ram[arm_index][battery_index] else 0)
                                    return self.getSyntax().clone(0)
                                
                                # Column 11: batteryAlarmFlags (HEX bitmask - MIB uyumlu)
                                # 0x1=Düşük Gerilim Uyarısı, 0x2=Düşük Gerilim Alarmı, 0x4=Yüksek Gerilim Uyarısı,
                                # 0x8=Yüksek Gerilim Alarmı, 0x10=Modül Sıcaklık Alarmı, 0x20=Pozitif Kutup Sıcaklık Alarmı,
                                # 0x40=Negatif Kutup Sıcaklık Alarmı
                                if column == 11:
                                    if arm_index in alarm_ram and battery_index in alarm_ram[arm_index]:
                                        flags = 0
                                        # Debug: Tüm alarm durumlarını logla
                                        alarm_states = {}
                                        for at in range(1, 8):
                                            alarm_states[at] = alarm_ram[arm_index][battery_index].get(at, False)
                                        print(f"🔍 DEBUG batteryAlarmFlags - Kol {arm_index}, Batarya {battery_index}: {alarm_states}")
                                        
                                        if alarm_ram[arm_index][battery_index].get(1, False):  # Düşük Gerilim Uyarısı
                                            flags |= 0x1
                                        if alarm_ram[arm_index][battery_index].get(2, False):  # Düşük Gerilim Alarmı
                                            flags |= 0x2
                                        if alarm_ram[arm_index][battery_index].get(3, False):  # Yüksek Gerilim Uyarısı
                                            flags |= 0x4
                                        if alarm_ram[arm_index][battery_index].get(4, False):  # Yüksek Gerilim Alarmı
                                            flags |= 0x8
                                        if alarm_ram[arm_index][battery_index].get(5, False):  # Modül Sıcaklık Alarmı
                                            flags |= 0x10
                                        if alarm_ram[arm_index][battery_index].get(6, False):  # Pozitif Kutup Sıcaklık Alarmı
                                            flags |= 0x20
                                        if alarm_ram[arm_index][battery_index].get(7, False):  # Negatif Kutup Sıcaklık Alarmı
                                            flags |= 0x40
                                        print(f"🔍 DEBUG batteryAlarmFlags - Dönen değer: {flags} (0x{flags:02X})")
                                        return self.getSyntax().clone(flags)
                                    return self.getSyntax().clone(0)
                    
                    return self.getSyntax().clone("No Such Object")
                
                except Exception as e:
                    # Exception olursa stdout'a ve log'a yaz
                    error_msg = f"❌ SNMP HATA - OID: {oid} - {str(e)}"
                    print(error_msg)
                    print(f"   Traceback: {traceback.format_exc()}")
                    
                    try:
                        with open(log_path, "a") as f:
                            f.write(f"{datetime.datetime.now()} - HATA OID: {oid} - {str(e)}\n")
                            f.write(f"{traceback.format_exc()}\n")
                            f.flush()  # Hemen yaz
                    except:
                        pass
                    # Exception durumunda 0 döndür
                    return self.getSyntax().clone(0)

        # MIB Objects oluştur
        mibBuilder.export_symbols(
            "__MODBUS_RAM_MIB",
            # Eski Sistem bilgileri (test için)
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
        
        # Yeni MIB - tescomBmsSystem OID'leri (1.3.6.1.4.1.1001.1.x)
        mibBuilder.export_symbols(
            "__TESCOM_BMS_SYSTEM_MIB",
            MibScalar((1, 3, 6, 1, 4, 1, 1001, 1, 1), v2c.OctetString()),  # systemInfo
            ModbusRAMMibScalarInstance((1, 3, 6, 1, 4, 1, 1001, 1, 1), (0,), v2c.OctetString()),
            
            MibScalar((1, 3, 6, 1, 4, 1, 1001, 1, 2), v2c.Integer()),  # totalBatteryCount
            ModbusRAMMibScalarInstance((1, 3, 6, 1, 4, 1, 1001, 1, 2), (0,), v2c.Integer()),
            
            MibScalar((1, 3, 6, 1, 4, 1, 1001, 1, 3), v2c.Integer()),  # totalArmCount
            ModbusRAMMibScalarInstance((1, 3, 6, 1, 4, 1, 1001, 1, 3), (0,), v2c.Integer()),
            
            MibScalar((1, 3, 6, 1, 4, 1, 1001, 1, 4), v2c.Integer()),  # systemStatus
            ModbusRAMMibScalarInstance((1, 3, 6, 1, 4, 1, 1001, 1, 4), (0,), v2c.Integer()),
            
            MibScalar((1, 3, 6, 1, 4, 1, 1001, 1, 5), v2c.OctetString()),  # lastUpdateTime
            ModbusRAMMibScalarInstance((1, 3, 6, 1, 4, 1, 1001, 1, 5), (0,), v2c.OctetString()),
            
            MibScalar((1, 3, 6, 1, 4, 1, 1001, 1, 6), v2c.Integer()),  # dataCount
            ModbusRAMMibScalarInstance((1, 3, 6, 1, 4, 1, 1001, 1, 6), (0,), v2c.Integer()),
        )
        
        # Alarm sayıları - tescomBmsAlarms (1.3.6.1.4.1.1001.4.x)
        mibBuilder.export_symbols(
            "__TESCOM_BMS_ALARMS_MIB",
            MibScalar((1, 3, 6, 1, 4, 1, 1001, 4, 1), v2c.Gauge32()),  # tescomAlarmsPresent
            ModbusRAMMibScalarInstance((1, 3, 6, 1, 4, 1, 1001, 4, 1), (0,), v2c.Gauge32()),
            
            MibScalar((1, 3, 6, 1, 4, 1, 1001, 4, 2), v2c.Gauge32()),  # tescomArmAlarmsPresent
            ModbusRAMMibScalarInstance((1, 3, 6, 1, 4, 1, 1001, 4, 2), (0,), v2c.Gauge32()),
            
            MibScalar((1, 3, 6, 1, 4, 1, 1001, 4, 3), v2c.Gauge32()),  # tescomBatteryAlarmsPresent
            ModbusRAMMibScalarInstance((1, 3, 6, 1, 4, 1, 1001, 4, 3), (0,), v2c.Gauge32()),
        )
        
        # ============================================
        # armTable - MIB TABLE yapısına uygun (1.3.6.1.4.1.1001.2.1.1.{column}.{armIndex})
        # ============================================
        print("⚙️  armTable OID'leri oluşturuluyor...")
        for arm_index in range(1, 5):  # 1-4 arası kol
            for column in range(2, 9):  # Column 2-8 (armSlaveCount'tan armAlarmFlags'e kadar - MIB uyumlu)
                oid = (1, 3, 6, 1, 4, 1, 1001, 2, 1, 1, column, arm_index)
                if column == 2:  # armSlaveCount
                    syntax = v2c.Integer()
                elif column in [3, 4, 5, 6]:  # armCurrent, armHumidity, armNtc1Temp, armNtc2Temp - String olarak gönder
                    syntax = v2c.OctetString()
                elif column == 7:  # armStatus
                    syntax = v2c.Integer()
                elif column == 8:  # armAlarmFlags (HEX bitmask)
                    syntax = v2c.Integer()
                
                mibBuilder.export_symbols(
                    f"__ARM_TABLE_{arm_index}_{column}",
                    MibScalar(oid, syntax),
                    ModbusRAMMibScalarInstance(oid, (0,), syntax),
                )
        
        # ============================================
        # batteryTable - MIB TABLE yapısına uygun (1.3.6.1.4.1.1001.3.1.1.{column}.{armIndex}.{batteryIndex})
        # ============================================
        print("⚙️  batteryTable OID'leri oluşturuluyor...")
        for arm_index in range(1, 5):  # 1-4 arası kol
            # Her zaman 120 batarya potansiyeli için OID oluştur
            battery_count = 120
            
            for battery_index in range(1, battery_count + 1):  # 1-120 arası batarya
                for column in range(3, 12):  # Column 3-11 (batteryVoltage'dan batteryAlarmFlags'e kadar - MIB uyumlu)
                    oid = (1, 3, 6, 1, 4, 1, 1001, 3, 1, 1, column, arm_index, battery_index)
                    if column == 3:  # batteryVoltage - String olarak gönder
                        syntax = v2c.OctetString()
                    elif column == 4:  # batterySoc - String olarak gönder
                        syntax = v2c.OctetString()
                    elif column == 5:  # batteryRimt - String olarak gönder
                        syntax = v2c.OctetString()
                    elif column == 6:  # batterySoh - String olarak gönder
                        syntax = v2c.OctetString()
                    elif column in [7, 8, 9]:  # batteryNtc1, batteryNtc2, batteryNtc3 - String olarak gönder
                        syntax = v2c.OctetString()
                    elif column == 10:  # batteryStatus
                        syntax = v2c.Integer()
                    elif column == 11:  # batteryAlarmFlags (HEX bitmask)
                        syntax = v2c.Integer()
                    
                    mibBuilder.export_symbols(
                        f"__BATTERY_TABLE_{arm_index}_{battery_index}_{column}",
                        MibScalar(oid, syntax),
                        ModbusRAMMibScalarInstance(oid, (0,), syntax),
                    )
        
        print("✅ MIB Objects oluşturuldu (TABLE yapısı)")

        # --- end of Managed Object Instance initialization ----

        # Register SNMP Applications at the SNMP engine for particular SNMP context
        cmdrsp.GetCommandResponder(snmpEngine, snmpContext)
        cmdrsp.NextCommandResponder(snmpEngine, snmpContext)
        cmdrsp.BulkCommandResponder(snmpEngine, snmpContext)
        print("✅ Command Responder'lar kaydedildi (GET/GETNEXT/GETBULK)")

        # Register an imaginary never-ending job to keep I/O dispatcher running forever
        snmpEngine.transport_dispatcher.job_started(1)
        print("✅ Job başlatıldı")

        print(f"🚀 SNMP Agent başlatılıyor...")
        print(f"📡 Port {SNMP_PORT}'de dinleniyor...")
        print("=" * 70)
        print("📋 MIB UYUMLU TABLE YAPISI - TESCOM-BMS-MIB")
        print("=" * 70)
        print("")
        print("🔹 Sistem Bilgileri (tescomBmsSystem - 1.3.6.1.4.1.1001.1.x):")
        print("   1.3.6.1.4.1.1001.1.1.0 - systemInfo")
        print("   1.3.6.1.4.1.1001.1.2.0 - totalBatteryCount")
        print("   1.3.6.1.4.1.1001.1.3.0 - totalArmCount")
        print("   1.3.6.1.4.1.1001.1.4.0 - systemStatus")
        print("   1.3.6.1.4.1.1001.1.5.0 - lastUpdateTime")
        print("   1.3.6.1.4.1.1001.1.6.0 - dataCount")
        print("")
        print("🔹 Kol Tablosu (armTable - 1.3.6.1.4.1.1001.2.1.1.{column}.{armIndex}):")
        print("   Örnek: 1.3.6.1.4.1.1001.2.1.1.2.1.0 - armSlaveCount (column 2), Kol 1")
        print("   Örnek: 1.3.6.1.4.1.1001.2.1.1.3.1.0 - armCurrent (column 3), Kol 1")
        print("   Örnek: 1.3.6.1.4.1.1001.2.1.1.4.1.0 - armHumidity (column 4), Kol 1")
        print("   Örnek: 1.3.6.1.4.1.1001.2.1.1.5.1.0 - armNtc1Temp (column 5), Kol 1")
        print("   Örnek: 1.3.6.1.4.1.1001.2.1.1.6.1.0 - armNtc2Temp (column 6), Kol 1")
        print("   Örnek: 1.3.6.1.4.1.1001.2.1.1.7.1.0 - armStatus (column 7), Kol 1")
        print("   Örnek: 1.3.6.1.4.1.1001.2.1.1.8.1.0 - armAlarmFlags (column 8), Kol 1")
        print("")
        print("🔹 Batarya Tablosu (batteryTable - 1.3.6.1.4.1.1001.3.1.1.{column}.{armIndex}.{batteryIndex}):")
        print("   Örnek: 1.3.6.1.4.1.1001.3.1.1.3.1.1.0  - batteryVoltage (column 3), Kol 1, Batarya 1")
        print("   Örnek: 1.3.6.1.4.1.1001.3.1.1.4.1.1.0  - batterySoc (column 4), Kol 1, Batarya 1")
        print("   Örnek: 1.3.6.1.4.1.1001.3.1.1.5.1.1.0  - batteryRimt (column 5), Kol 1, Batarya 1")
        print("   Örnek: 1.3.6.1.4.1.1001.3.1.1.10.1.1.0 - batteryStatus (column 10), Kol 1, Batarya 1")
        print("   Örnek: 1.3.6.1.4.1.1001.3.1.1.11.1.1.0 - batteryAlarmFlags (column 11), Kol 1, Batarya 1")
        print("")
        print("🔹 Alarm Bilgileri (tescomBmsAlarms - 1.3.6.1.4.1.1001.4.x):")
        print("   1.3.6.1.4.1.1001.4.1.0 - tescomAlarmsPresent (Toplam alarm sayısı)")
        print("   1.3.6.1.4.1.1001.4.2.0 - tescomArmAlarmsPresent (Kol alarm sayısı)")
        print("   1.3.6.1.4.1.1001.4.3.0 - tescomBatteryAlarmsPresent (Batarya alarm sayısı)")
        print("")
        print("=" * 70)
        print("🧪 SNMP Test Komutları:")
        print("=" * 70)
        print(f"# Sistem bilgileri:")
        print(f"snmpget -v2c -c public localhost:{SNMP_PORT} 1.3.6.1.4.1.1001.1.1.0")
        print(f"snmpget -v2c -c public localhost:{SNMP_PORT} 1.3.6.1.4.1.1001.1.2.0")
        print("")
        print(f"# Kol 1 verileri:")
        print(f"snmpget -v2c -c public localhost:{SNMP_PORT} 1.3.6.1.4.1.1001.2.1.1.2.1.0")
        print(f"snmpget -v2c -c public localhost:{SNMP_PORT} 1.3.6.1.4.1.1001.2.1.1.3.1.0")
        print(f"snmpget -v2c -c public localhost:{SNMP_PORT} 1.3.6.1.4.1.1001.2.1.1.8.1.0  # armAlarmFlags (HEX bitmask)")
        print("")
        print(f"# Batarya 1 verileri (Kol 1):")
        print(f"snmpget -v2c -c public localhost:{SNMP_PORT} 1.3.6.1.4.1.1001.3.1.1.3.1.1.0")
        print(f"snmpget -v2c -c public localhost:{SNMP_PORT} 1.3.6.1.4.1.1001.3.1.1.4.1.1.0")
        print(f"snmpget -v2c -c public localhost:{SNMP_PORT} 1.3.6.1.4.1.1001.3.1.1.11.1.1.0  # batteryAlarmFlags (HEX bitmask)")
        print("")
        print(f"# Tüm TESCOM BMS verilerini görmek için:")
        print(f"snmpwalk -v2c -c public localhost:{SNMP_PORT} 1.3.6.1.4.1.1001")
        print("")
        print(f"# Sadece armTable'ı görmek için:")
        print(f"snmpwalk -v2c -c public localhost:{SNMP_PORT} 1.3.6.1.4.1.1001.2")
        print("")
        print(f"# Sadece batteryTable'ı görmek için:")
        print(f"snmpwalk -v2c -c public localhost:{SNMP_PORT} 1.3.6.1.4.1.1001.3")
        print("=" * 70)
        print(f"✅ SNMP Agent hazır: {SNMP_HOST}:{SNMP_PORT}")
        print("=" * 50)

        # Run I/O dispatcher which would receive queries and send responses
        try:
            print("🔄 SNMP transport dispatcher hazırlanıyor...")
            
            # Port dinleniyor mu kontrol et
            print(f"🔍 Port {SNMP_PORT} kontrol ediliyor...")
            import socket
            import subprocess
            try:
                # Önce mevcut process'i kontrol et
                result = subprocess.run(
                    f"lsof -i :{SNMP_PORT} || netstat -tulpn | grep :{SNMP_PORT} || ss -tulpn | grep :{SNMP_PORT}",
                    shell=True, capture_output=True, text=True, timeout=2
                )
                if result.stdout:
                    print(f"⚠️  Port {SNMP_PORT} zaten kullanımda:")
                    print(f"   {result.stdout.strip()}")
                    print("   Mevcut process kapatılıyor veya yeni port kullanılacak...")
            except:
                pass
            
            # pysnmp asyncio transport için doğru kullanım:
            # simple_snmp_server.py örneğine göre: open_dispatcher() blocking çağrılır
            # Ama thread içinde olduğumuz için executor kullanıyoruz
            print("🔄 SNMP dispatcher başlatılıyor...")
            print("   (open_dispatcher çağrılıyor - executor'da...)")
            
            async def run_snmp_dispatcher():
                """SNMP dispatcher'ı async olarak çalıştır"""
                try:
                    # open_dispatcher() blocking olabilir, executor'da çağır
                    await loop.run_in_executor(None, snmpEngine.open_dispatcher)
                    print("✅ SNMP dispatcher açıldı")
                    
                    # transport_dispatcher kontrolü
                    if not snmpEngine.transport_dispatcher:
                        print("⚠️  transport_dispatcher None - open_dispatcher başarısız olmuş olabilir")
                        return
                    
                    # Asyncio transport için run_dispatcher() gerekli olmayabilir
                    # open_dispatcher() yeterli olabilir - event loop çalışıyor
                    print("✅ SNMP dispatcher hazır, event loop çalışıyor...")
                    
                    # Sonsuz döngü - event loop devam etsin
                    while True:
                        await asyncio.sleep(1)
                        
                except Exception as e:
                    print(f"❌ SNMP dispatcher hatası: {e}")
                    import traceback
                    traceback.print_exc()
                    try:
                        if snmpEngine.transport_dispatcher:
                            snmpEngine.transport_dispatcher.close_dispatcher()
                    except:
                        pass
            
            # Event loop çalışıyor mu kontrol için
            def loop_running_check():
                print("✅ SNMP event loop çalışıyor...")
                print("📡 SNMP Agent istekleri dinliyor...")
            
            # 2 saniye sonra kontrol mesajı göster
            loop.call_later(2, loop_running_check)
            
            # SNMP dispatcher'ı async olarak başlat
            loop.create_task(run_snmp_dispatcher())
            
            print("⚠️  Event loop başlatıldı - SNMP istekleri dinleniyor...")
            print("💡 Test için: snmpget -v2c -c public localhost:1161 1.3.6.1.4.1.1001.1.1.0")
            print("📡 SNMP Agent hazır ve istekleri bekliyor...")
            print("   (Event loop run_forever çağrılıyor...)")
            
            # stdout'u flush et - logların hemen görünmesi için
            import sys
            sys.stdout.flush()
            
            # Event loop'u çalıştır
            loop.run_forever()
        except KeyboardInterrupt:
            print("\n🛑 SNMP event loop durduruluyor...")
            try:
                loop.stop()
            except:
                pass
            try:
                snmpEngine.close_dispatcher()
            except:
                pass
        except Exception as e:
            print(f"❌ SNMP dispatcher hatası: {e}")
            import traceback
            traceback.print_exc()
            sys.stdout.flush()
            try:
                loop.stop()
            except:
                pass
            try:
                snmpEngine.close_dispatcher()
            except:
                pass
            # Exception'ı yeniden fırlatma - thread'i kill etme
            print("⚠️  SNMP dispatcher hatası, ancak thread devam ediyor...")
        
    except Exception as e:
        print(f"❌ SNMP sunucu hatası: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    print("Program başlatıldı ==>")
    main()