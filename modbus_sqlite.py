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

# SNMP imports
from pysnmp.entity import engine, config
from pysnmp.entity.rfc3413 import cmdrsp, context
from pysnmp.carrier.asyncio.dgram import udp
from pysnmp.proto.api import v2c

# Global variables
buffer = bytearray()
data_queue = queue.Queue()
RX_PIN = 16
TX_PIN = 26
BAUD_RATE = 9600

# Periyot sistemi için global değişkenler
current_period_timestamp = None
period_active = False
last_data_received = time.time()
last_k_value = None  # Son gelen verinin k değerini tutar
last_k_value_lock = threading.Lock()  # Thread-safe erişim için

# Database instance
db = BatteryDatabase()
db_lock = threading.Lock()  # Thread-safe erişim için

# Dinamik veri indeksleme sistemi
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
    """Dinamik veri indeksine göre veri döndür - SQLite'den oku"""
    try:
        with db_lock:
            result = []
            current_index = 1  # 1'den başla (Modbus 1-based)
            
            print(f"DEBUG: get_dynamic_data_by_index start={start_index}, quantity={quantity}")
            
            # Periyot verilerinden armslavecounts al
            arm_slave_counts = db.get_arm_slave_counts_from_period()
            print(f"DEBUG: arm_slave_counts = {arm_slave_counts}")
            
            # Periyot verilerini al
            period_data = db.get_current_period_data()
            print(f"DEBUG: period_data = {period_data}")
            
            # Armslavecounts'a göre sıralı veri oluştur - sadece bataryası olan kolları işle
            for arm in range(1, 5):  # Kol 1-4
                if arm_slave_counts.get(arm, 0) == 0:
                    print(f"DEBUG: Kol {arm} atlandı (batarya yok)")
                    continue  # Bu kolda batarya yok, atla
                    
                print(f"DEBUG: Kol {arm} işleniyor...")
                
                # Kol verileri (akım, nem, sıcaklık, sıcaklık2)
                for data_type in range(1, 5):
                    if current_index >= start_index and len(result) < quantity:
                        if arm in period_data and 2 in period_data[arm]:
                            if data_type == 1:  # Akım
                                value = period_data[arm][2].get(10, {}).get('value', 0)  # dtype=10
                            elif data_type == 2:  # Nem
                                value = period_data[arm][2].get(11, {}).get('value', 0)  # dtype=11
                            elif data_type == 3:  # Sıcaklık
                                value = period_data[arm][2].get(12, {}).get('value', 0)  # dtype=12
                            elif data_type == 4:  # Sıcaklık2
                                value = period_data[arm][2].get(13, {}).get('value', 0)  # dtype=13
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
                battery_count = arm_slave_counts.get(arm, 0)
                print(f"DEBUG: Kol {arm} batarya sayısı: {battery_count}")
                for battery_num in range(1, battery_count + 1):
                    k_value = battery_num + 2  # k=3,4,5,6...
                    
                    if arm in period_data and k_value in period_data[arm]:
                        # Her batarya için 7 veri tipi
                        for data_type in range(5, 12):  # 5-11 (gerilim, soc, rint, soh, ntc1, ntc2, ntc3)
                            if current_index >= start_index and len(result) < quantity:
                                if data_type == 5:  # Gerilim
                                    value = period_data[arm][k_value].get(10, {}).get('value', 0)  # dtype=10
                                elif data_type == 6:  # SOC
                                    value = period_data[arm][k_value].get(11, {}).get('value', 0)  # dtype=11 (SOC)
                                elif data_type == 7:  # Rint
                                    value = period_data[arm][k_value].get(12, {}).get('value', 0)  # dtype=12
                                elif data_type == 8:  # SOH
                                    value = period_data[arm][k_value].get(126, {}).get('value', 0)  # dtype=126 (SOH)
                                elif data_type == 9:  # NTC1
                                    value = period_data[arm][k_value].get(13, {}).get('value', 0)  # dtype=13
                                elif data_type == 10:  # NTC2
                                    value = period_data[arm][k_value].get(14, {}).get('value', 0)  # dtype=14
                                elif data_type == 11:  # NTC3
                                    value = period_data[arm][k_value].get(15, {}).get('value', 0)  # dtype=15
                                else:
                                    value = 0
                                result.append(float(value) if value else 0.0)
                            else:
                                result.append(0.0)
                            current_index += 1
                            
                            if len(result) >= quantity:
                                break
                    else:
                        # Veri yoksa 0'lar ekle
                        for data_type in range(5, 12):
                            if current_index >= start_index and len(result) < quantity:
                                result.append(0.0)
                            current_index += 1
                            
                            if len(result) >= quantity:
                                break
                    
                    if len(result) >= quantity:
                        break
                        
                if len(result) >= quantity:
                    break
                    
            # Eksik veriler için 0 ekle
            while len(result) < quantity:
                result.append(0.0)
                
            print(f"DEBUG: Sonuç: {result}")
            return result
            
    except Exception as e:
        print(f"❌ get_dynamic_data_by_index hatası: {e}")
        return [0.0] * quantity

def get_dynamic_register_names(start_index, quantity):
    """Dinamik register isimlerini oluştur"""
    names = []
    current_index = start_index
    
    # Armslavecounts'a göre sıralı isim oluştur
    for arm in range(1, 5):  # Kol 1-4
        if arm_slave_counts_ram.get(arm, 0) == 0:
            continue  # Bu kolda batarya yok, atla
            
        # Kol verileri (akım, nem, sıcaklık, sıcaklık2)
        for data_type in range(1, 5):
            if current_index >= start_index and len(names) < quantity:
                if data_type == 1:  # Akım
                    names.append(f"Kol{arm}_Akım(A)")
                elif data_type == 2:  # Nem
                    names.append(f"Kol{arm}_Nem(%)")
                elif data_type == 3:  # Sıcaklık
                    names.append(f"Kol{arm}_Sıcaklık(°C)")
                elif data_type == 4:  # Sıcaklık2
                    names.append(f"Kol{arm}_Sıcaklık2(°C)")
            current_index += 1
            
            if len(names) >= quantity:
                break
                
        if len(names) >= quantity:
            break
            
        # Batarya verileri
        battery_count = arm_slave_counts_ram.get(arm, 0)
        for battery_num in range(1, battery_count + 1):
            # Her batarya için 7 veri tipi
            for data_type in range(5, 12):  # 5-11 (gerilim, soc, rint, soh, ntc1, ntc2, ntc3)
                if current_index >= start_index and len(names) < quantity:
                    if data_type == 5:  # Gerilim
                        names.append(f"Kol{arm}_Bat{battery_num}_Gerilim(V)")
                    elif data_type == 6:  # SOC
                        names.append(f"Kol{arm}_Bat{battery_num}_SOC(%)")
                    elif data_type == 7:  # Rint
                        names.append(f"Kol{arm}_Bat{battery_num}_Rint(Ω)")
                    elif data_type == 8:  # SOH
                        names.append(f"Kol{arm}_Bat{battery_num}_SOH(%)")
                    elif data_type == 9:  # NTC1
                        names.append(f"Kol{arm}_Bat{battery_num}_NTC1(°C)")
                    elif data_type == 10:  # NTC2
                        names.append(f"Kol{arm}_Bat{battery_num}_NTC2(°C)")
                    elif data_type == 11:  # NTC3
                        names.append(f"Kol{arm}_Bat{battery_num}_NTC3(°C)")
                current_index += 1
                
                if len(names) >= quantity:
                    break
                    
            if len(names) >= quantity:
                break
                
        if len(names) >= quantity:
            break
            
    return names

# Modbus TCP server ayarları
MODBUS_TCP_PORT = 1502  # Port 1502 kullan (SNMP ile uyumlu)
MODBUS_TCP_HOST = '0.0.0.0'

# SNMP Agent ayarları
SNMP_PORT = 1161
SNMP_HOST = '0.0.0.0'  # Dışarıdan erişim için 0.0.0.0

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

# RAM fonksiyonları kaldırıldı - sadece SQLite kullanılıyor

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

def data_processor():
    """Gelen verileri işle ve RAM'e kaydet"""
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
                
                print(f"\n*** BATKON ALARM VERİSİ ALGILANDI - {timestamp} ***")
                print(f"Ham Veri: {data}")
                continue

            # 5 byte'lık missing data verisi kontrolü
            if len(data) == 5:
                raw_bytes = [int(b, 16) for b in data]
                timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                
                print(f"\n*** MISSING DATA VERİSİ ALGILANDI - {timestamp} ***")
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
                
                # Veri işleme ve RAM'e kayıt
                if dtype == 10:  # Gerilim
                    # Ham gerilim verisini kaydet
                    update_battery_data_ram(arm_value, k_value, 10, salt_data)
                    
                    # SOC hesapla ve dtype=126'ya kaydet
                    if k_value != 2:  # k_value 2 değilse SOC hesapla
                        soc_value = Calc_SOC(salt_data)
                        update_battery_data_ram(arm_value, k_value, 126, soc_value)
                
                elif dtype == 11:  # SOH veya Nem
                    if k_value == 2:  # Nem verisi
                        print(f"*** VERİ ALGILANDI - Arm: {arm_value}, Nem: {salt_data}% ***")
                        update_battery_data_ram(arm_value, k_value, 11, salt_data)
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
                        
                        # SOH verisini dtype=11'e kaydet
                        update_battery_data_ram(arm_value, k_value, 11, soh_value)
                
                elif dtype == 12:  # NTC1
                    update_battery_data_ram(arm_value, k_value, 12, salt_data)
                
                elif dtype == 13:  # NTC2
                    update_battery_data_ram(arm_value, k_value, 13, salt_data)
                

                
                else:  # Diğer Dtype değerleri için
                    update_battery_data_ram(arm_value, k_value, dtype, salt_data)

            # 6 byte'lık balans komutu veya armslavecounts kontrolü
            elif len(data) == 6:
                raw_bytes = [int(b, 16) for b in data]
                
                # Slave sayısı verisi: 2. byte (index 1) 0x7E ise
                if raw_bytes[1] == 0x7E:
                    arm1, arm2, arm3, arm4 = raw_bytes[2], raw_bytes[3], raw_bytes[4], raw_bytes[5]
                    print(f"armslavecounts verisi tespit edildi: arm1={arm1}, arm2={arm2}, arm3={arm3}, arm4={arm4}")
                    
                    # RAM'de armslavecounts güncelle
                    with db_lock:
                        arm_slave_counts_ram[1] = arm1
                        arm_slave_counts_ram[2] = arm2
                        arm_slave_counts_ram[3] = arm3
                        arm_slave_counts_ram[4] = arm4
                    
                    print(f"✓ Armslavecounts RAM'e kaydedildi: {arm_slave_counts_ram}")
                    continue
                
                # Balans verisi: 3. byte (index 2) 0x0F ise
                elif raw_bytes[2] == 0x0F:
                    print(f"Balans verisi tespit edildi")
                    continue
                
                # Hatkon alarmı: 3. byte (index 2) 0x7D ise
                elif raw_bytes[2] == 0x7D:
                    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                    print(f"\n*** HATKON ALARM VERİSİ ALGILANDI - {timestamp} ***")
                    continue

            data_queue.task_done()
            
        except queue.Empty:
            continue
        except Exception as e:
            print(f"\ndata_processor'da beklenmeyen hata: {e}")
            continue

def modbus_tcp_server():
    """Modbus TCP server - cihazlardan gelen istekleri dinle"""
    try:
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_socket.bind((MODBUS_TCP_HOST, MODBUS_TCP_PORT))
        server_socket.listen(5)
        
        print(f"Modbus TCP Server başlatıldı: {MODBUS_TCP_HOST}:{MODBUS_TCP_PORT}")
        
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
            with db_lock:
                for i in range(quantity):
                    if i < 4:  # İlk 4 register armslavecounts
                        arm_num = i + 1
                        registers.append(float(arm_slave_counts_ram.get(arm_num, 0)))
                    else:
                        registers.append(0.0)  # Boş register
            print(f"DEBUG: Armslavecounts verileri: {registers}")
        elif start_address >= 1:  # Dinamik veri okuma
            # Dinamik veri sistemi kullan
            registers = get_dynamic_data_by_index(start_address, quantity)
            print(f"DEBUG: Dinamik veri (start={start_address}, qty={quantity}): {registers}")
        else:
            # Bilinmeyen adres için boş veri
            registers = [0.0] * quantity
            print(f"DEBUG: Bilinmeyen adres {start_address}, boş veri: {registers}")
        
        # Modbus TCP response hazırla
        byte_count = len(registers) * 2  # Her register 2 byte
        response = struct.pack('>HHHBB', 
                      transaction_id,
                      0,
                      byte_count + 3,
                      unit_id,
                      3
                     )
        response += struct.pack('B', byte_count)

        for reg in registers:
            # Virgüllü sayıları 100 ile çarpıp integer olarak gönder
            if reg == int(reg):  # Tam sayı ise
                response += struct.pack('>H', int(reg))
            else:  # Virgüllü sayı ise
                response += struct.pack('>H', int(reg * 100))  # 100 ile çarp

        
        # Register isimlerini hazırla
        register_names = []
        if start_address == 0:
            register_names = ["Arm1", "Arm2", "Arm3", "Arm4"]
        elif start_address >= 1:
            # Dinamik veri isimleri
            register_names = get_dynamic_register_names(start_address, quantity)
        else:
            register_names = ["Bilinmeyen"]
        
        print(f"DEBUG: Response hazırlandı, byte_count={byte_count}")
        print(f"DEBUG: Register Names: {register_names[:len(registers)]}")
        print(f"DEBUG: Register Values: {registers}")
        print(f"DEBUG: Modbus Values (100x): {[int(reg * 100) if reg != int(reg) else int(reg) for reg in registers]}")
        return response
        
    except Exception as e:
        print(f"Read Holding Registers hatası: {e}")
        import traceback
        traceback.print_exc()
        return None

def handle_read_input_registers(transaction_id, unit_id, start_address, quantity):
    """Read Input Registers (Function Code 4) işle"""
    # Şimdilik Read Holding Registers ile aynı
    return handle_read_holding_registers(transaction_id, unit_id, start_address, quantity)

def format_arm_data_for_modbus(arm_data, k_value, quantity):
    """Arm verilerini Modbus register formatına çevir - sadece k=2 (arm) verileri"""
    registers = []
    
    # Veri tiplerini sırala: 10 (akım), 11 (nem), 12 (ntc1), 13 (ntc2)
    data_types = [10, 11, 12, 13]
    
    # Sadece mevcut veri tiplerini döndür, quantity'yi sınırla
    max_registers = min(quantity, len(data_types))
    
    for i in range(max_registers):
        dtype = data_types[i]
        value = 0.0
        
        # Sadece k=2 (arm) verilerini kontrol et
        if k_value in arm_data and dtype in arm_data[k_value]:
            value = arm_data[k_value][dtype]['value']
            print(f"DEBUG: k={k_value} (arm) verisi kullanıldı: dtype={dtype}, value={value}")
        
        registers.append(value)
    
    return registers

def format_specific_battery_data(arm_data, battery_num, quantity):
    """Belirli bir bataryanın verilerini Modbus register formatına çevir"""
    registers = []
    
    # Veri tiplerini sırala: 10 (gerilim/akım), 11 (soh/nem), 12 (ntc1), 13 (ntc2), 14 (ntc3), 126 (soc)
    data_types = [10, 11, 12, 13, 14, 126]
    
    # Sadece mevcut veri tiplerini döndür, quantity'yi sınırla
    max_registers = min(quantity, len(data_types))
    
    for i in range(max_registers):
        dtype = data_types[i]
        value = 0.0
        
        # Belirli batarya numarası için veri ara
        if battery_num in arm_data and dtype in arm_data[battery_num]:
            value = arm_data[battery_num][dtype]['value']
            print(f"DEBUG: Batarya {battery_num} verisi kullanıldı: dtype={dtype}, value={value}")
        
        registers.append(value)
    
    return registers

def format_specific_dtype_data(arm_data, battery_num, dtype, quantity):
    """Belirli bir dtype'ın verilerini Modbus register formatına çevir - tek değer döner"""
    registers = []
    
    # Tek değer döndür
    value = 0.0
    
    # Belirli batarya numarası ve dtype için veri ara
    if battery_num in arm_data and dtype in arm_data[battery_num]:
        value = arm_data[battery_num][dtype]['value']
        print(f"DEBUG: Batarya {battery_num}, dtype={dtype} verisi kullanıldı: value={value}")
    
    # Quantity kadar aynı değeri döndür
    for i in range(quantity):
        registers.append(value)
    
    return registers

def start_snmp_agent():
    """SNMP Agent başlat - Modbus TCP Server RAM sistemi ile"""
    print("🚀 SNMP Agent Başlatılıyor...")
    print("📊 Modbus TCP Server RAM Sistemi ile Entegre")
    
    try:
        # Thread için yeni event loop oluştur
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        # Create SNMP engine
        snmpEngine = engine.SnmpEngine()
        print("✅ SNMP Engine oluşturuldu")

        # Transport setup - UDP over IPv4
        config.add_transport(
            snmpEngine, udp.DOMAIN_NAME, udp.UdpTransport().open_server_mode((SNMP_HOST, SNMP_PORT))
        )
        print("✅ Transport ayarlandı")

        # SNMPv2c setup
        config.add_v1_system(snmpEngine, "my-area", "public")
        print("✅ SNMPv2c ayarlandı")

        # Allow read MIB access for this user / securityModels at VACM
        config.add_vacm_user(snmpEngine, 2, "my-area", "noAuthNoPriv", (1, 3, 6, 5))
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

        class ModbusSQLiteMibScalarInstance(MibScalarInstance):
            """Modbus TCP Server SQLite sistemi ile MIB Instance"""
            def getValue(self, name, **context):
                oid = '.'.join([str(x) for x in name])
                print(f"🔍 SNMP OID sorgusu: {oid}")
                
                try:
                    with db_lock:
                        # Sistem bilgileri
                        if oid == "1.3.6.5.1.0":
                            return self.getSyntax().clone(
                                f"Python {sys.version} running on a {sys.platform} platform"
                            )
                        elif oid == "1.3.6.5.2.0":  # totalBatteryCount
                            arm_counts = db.get_arm_slave_counts_from_period()
                            total_batteries = sum(arm_counts.values())
                            return self.getSyntax().clone(str(total_batteries))
                        elif oid == "1.3.6.5.3.0":  # totalArmCount
                            arm_counts = db.get_arm_slave_counts_from_period()
                            active_arms = sum(1 for count in arm_counts.values() if count > 0)
                            return self.getSyntax().clone(str(active_arms))
                        elif oid == "1.3.6.5.4.0":  # systemStatus
                            return self.getSyntax().clone("1")
                        elif oid == "1.3.6.5.5.0":  # lastUpdateTime
                            return self.getSyntax().clone(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                        elif oid == "1.3.6.5.6.0":  # dataCount
                            period_data = db.get_current_period_data()
                            total_data = 0
                            for arm_data in period_data.values():
                                for k_data in arm_data.values():
                                    total_data += len(k_data)
                            return self.getSyntax().clone(str(total_data))
                        elif oid == "1.3.6.5.7.0":  # arm1SlaveCount
                            arm_counts = db.get_arm_slave_counts_from_period()
                            return self.getSyntax().clone(str(arm_counts.get(1, 0)))
                        elif oid == "1.3.6.5.8.0":  # arm2SlaveCount
                            arm_counts = db.get_arm_slave_counts_from_period()
                            return self.getSyntax().clone(str(arm_counts.get(2, 0)))
                        elif oid == "1.3.6.5.9.0":  # arm3SlaveCount
                            arm_counts = db.get_arm_slave_counts_from_period()
                            return self.getSyntax().clone(str(arm_counts.get(3, 0)))
                        elif oid == "1.3.6.5.10.0":  # arm4SlaveCount
                            arm_counts = db.get_arm_slave_counts_from_period()
                            return self.getSyntax().clone(str(arm_counts.get(4, 0)))
                        else:
                            # Gerçek batarya verileri - SQLite'den oku
                            if oid.startswith("1.3.6.5.10."):
                                parts = oid.split('.')
                                if len(parts) >= 8:  # 1.3.6.5.10.arm.k.dtype.0
                                    arm = int(parts[5])    # 1.3.6.5.10.{arm}
                                    k = int(parts[6])      # 1.3.6.5.10.arm.{k}
                                    dtype = int(parts[7])  # 1.3.6.5.10.arm.k.{dtype}
                                    
                                    period_data = db.get_current_period_data(arm=arm, k=k, dtype=dtype)
                                    if arm in period_data and k in period_data[arm] and dtype in period_data[arm][k]:
                                        value = period_data[arm][k][dtype]['value']
                                        return self.getSyntax().clone(str(value))
                                    return self.getSyntax().clone("0")
                            
                            return self.getSyntax().clone("No Such Object")
                            
                except Exception as e:
                    print(f"❌ SNMP getValue hatası: {e}")
                    return self.getSyntax().clone("0")

        # MIB Objects oluştur
        mibBuilder.export_symbols(
            "__MODBUS_SQLITE_MIB",
            # Sistem bilgileri
            MibScalar((1, 3, 6, 5, 1), v2c.OctetString()),
            ModbusSQLiteMibScalarInstance((1, 3, 6, 5, 1), (0,), v2c.OctetString()),
            
            MibScalar((1, 3, 6, 5, 2), v2c.OctetString()),
            ModbusSQLiteMibScalarInstance((1, 3, 6, 5, 2), (0,), v2c.OctetString()),
            
            MibScalar((1, 3, 6, 5, 3), v2c.OctetString()),
            ModbusSQLiteMibScalarInstance((1, 3, 6, 5, 3), (0,), v2c.OctetString()),
            
            MibScalar((1, 3, 6, 5, 4), v2c.OctetString()),
            ModbusSQLiteMibScalarInstance((1, 3, 6, 5, 4), (0,), v2c.OctetString()),
            
            MibScalar((1, 3, 6, 5, 5), v2c.OctetString()),
            ModbusSQLiteMibScalarInstance((1, 3, 6, 5, 5), (0,), v2c.OctetString()),
            
            MibScalar((1, 3, 6, 5, 6), v2c.OctetString()),
            ModbusSQLiteMibScalarInstance((1, 3, 6, 5, 6), (0,), v2c.OctetString()),
            
            # Armslavecounts OID'leri
            MibScalar((1, 3, 6, 5, 7), v2c.OctetString()),
            ModbusSQLiteMibScalarInstance((1, 3, 6, 5, 7), (0,), v2c.OctetString()),
            
            MibScalar((1, 3, 6, 5, 8), v2c.OctetString()),
            ModbusSQLiteMibScalarInstance((1, 3, 6, 5, 8), (0,), v2c.OctetString()),
            
            MibScalar((1, 3, 6, 5, 9), v2c.OctetString()),
            ModbusSQLiteMibScalarInstance((1, 3, 6, 5, 9), (0,), v2c.OctetString()),
            
            MibScalar((1, 3, 6, 5, 10), v2c.OctetString()),
            ModbusSQLiteMibScalarInstance((1, 3, 6, 5, 10), (0,), v2c.OctetString()),
        )
        
        # Batarya verileri için MIB Objects - Dinamik olarak oluştur
        for arm in range(1, 5):  # 1, 2, 3, 4
            for k in range(2, 6):  # 2, 3, 4, 5
                for dtype in range(10, 15):  # 10, 11, 12, 13, 14
                    oid = (1, 3, 6, 5, 10, arm, k, dtype)
                    mibBuilder.export_symbols(
                        f"__BATTERY_MIB_{arm}_{k}_{dtype}",
                        MibScalar(oid, v2c.OctetString()),
                        ModbusSQLiteMibScalarInstance(oid, (0,), v2c.OctetString()),
                    )
                
                # SOC verisi için dtype=126
                oid = (1, 3, 6, 5, 10, arm, k, 126)
                mibBuilder.export_symbols(
                    f"__BATTERY_MIB_{arm}_{k}_126",
                    MibScalar(oid, v2c.OctetString()),
                    ModbusSQLiteMibScalarInstance(oid, (0,), v2c.OctetString()),
                )
        print("✅ MIB Objects oluşturuldu")

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
        print("=" * 50)
        print("SNMP Test komutları:")
        print(f"snmpget -v2c -c public localhost:{SNMP_PORT} 1.3.6.5.2.0")
        print(f"snmpget -v2c -c public localhost:{SNMP_PORT} 1.3.6.5.7.0")
        print(f"snmpget -v2c -c public localhost:{SNMP_PORT} 1.3.6.5.8.0")
        print(f"snmpget -v2c -c public localhost:{SNMP_PORT} 1.3.6.5.9.0")
        print(f"snmpget -v2c -c public localhost:{SNMP_PORT} 1.3.6.5.10.0")
        print(f"snmpwalk -v2c -c public localhost:{SNMP_PORT} 1.3.6.5")
        print("=" * 50)

        # Run I/O dispatcher which would receive queries and send responses
        try:
            snmpEngine.open_dispatcher()
        except:
            snmpEngine.close_dispatcher()
            raise
        
    except Exception as e:
        print(f"❌ SNMP Agent hatası: {e}")
        import traceback
        traceback.print_exc()

def set_static_arm_counts():
    """Statik armslavecounts değerlerini ayarla"""
    with db_lock:
        # Statik armslavecounts değerleri
        arm_slave_counts_ram[1] = 0  # Kol 1'de batarya yok
        arm_slave_counts_ram[2] = 0  # Kol 2'de batarya yok
        arm_slave_counts_ram[3] = 7  # Kol 3'te 7 batarya
        arm_slave_counts_ram[4] = 0  # Kol 4'te batarya yok
        
        print("✓ Statik armslavecounts ayarlandı")
        print(f"  Kol 1: {arm_slave_counts_ram[1]} batarya")
        print(f"  Kol 2: {arm_slave_counts_ram[2]} batarya")
        print(f"  Kol 3: {arm_slave_counts_ram[3]} batarya")
        print(f"  Kol 4: {arm_slave_counts_ram[4]} batarya")

def main():
    try:
        # RAM'i temizle
        with db_lock:
            battery_data_ram.clear()
        print("RAM temizlendi.")
        
        # Statik armslavecounts ayarla
        set_static_arm_counts()
        
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

        # Veri işleme thread'i
        data_thread = threading.Thread(target=data_processor, daemon=True)
        data_thread.start()
        print("data_processor thread'i başlatıldı.")

        # Modbus TCP server thread'i
        modbus_thread = threading.Thread(target=modbus_tcp_server, daemon=True)
        modbus_thread.start()
        print("modbus_tcp_server thread'i başlatıldı.")

        print(f"\nSistem başlatıldı.")
        print("Program çalışıyor... (Ctrl+C ile durdurun)")
        print("=" * 50)
        print("Modbus TCP Server: Port 1502")
        print(f"SNMP Agent: Port {SNMP_PORT}")
        print("=" * 50)
        print("Dinamik Modbus Test (Sadece Kol 3'te 7 batarya):")
        print("  Start=1, Quantity=4: Kol3_Akım, Kol3_Nem, Kol3_Sıcaklık, Kol3_Sıcaklık2")
        print("  Start=5, Quantity=7: Kol3_Bat1_Gerilim, Kol3_Bat1_SOC, Kol3_Bat1_Rint, Kol3_Bat1_SOH, Kol3_Bat1_NTC1, Kol3_Bat1_NTC2, Kol3_Bat1_NTC3")
        print("  Start=12, Quantity=7: Kol3_Bat2_Gerilim, Kol3_Bat2_SOC, Kol3_Bat2_Rint, Kol3_Bat2_SOH, Kol3_Bat2_NTC1, Kol3_Bat2_NTC2, Kol3_Bat2_NTC3")
        print("  Start=19, Quantity=7: Kol3_Bat3_Gerilim, Kol3_Bat3_SOC, Kol3_Bat3_Rint, Kol3_Bat3_SOH, Kol3_Bat3_NTC1, Kol3_Bat3_NTC2, Kol3_Bat3_NTC3")
        print("  ... (Kol3_Bat4, Kol3_Bat5, Kol3_Bat6, Kol3_Bat7)")
        print("=" * 50)

        # SNMP Agent thread'i
        snmp_thread = threading.Thread(target=start_snmp_agent, daemon=True)
        snmp_thread.start()
        print("snmp_agent thread'i başlatıldı.")

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

if __name__ == '__main__':
    print("Modbus TCP Server başlatıldı ==>")
    main()

 