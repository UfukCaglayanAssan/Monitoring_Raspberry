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
from database import BatteryDatabase
from alarm_processor import alarm_processor

# Global variables
buffer = bytearray()
data_queue = queue.Queue()
RX_PIN = 16
TX_PIN = 26
BAUD_RATE = 9600
BIT_TIME = int(1e6 / BAUD_RATE)

# Armslavecount verilerini tutmak için
arm_slave_counts = {1: 0, 2: 0, 3: 0, 4: 0}  # Her kol için batarya sayısı
arm_slave_counts_lock = threading.Lock()  # Thread-safe erişim için

# Missing data takibi için
missing_data_tracker = set()  # (arm, battery) tuple'ları
missing_data_lock = threading.Lock()  # Thread-safe erişim için

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
        current_index = 1  # 1'den başla (Modbus 1-based)
        
        print(f"DEBUG: get_dynamic_data_by_index start={start_index}, quantity={quantity}")
        print(f"DEBUG: arm_slave_counts_ram = {arm_slave_counts_ram}")
        
        # Armslavecounts'a göre sıralı veri oluştur - sadece bataryası olan kolları işle
        for arm in range(1, 5):  # Kol 1-4
            if arm_slave_counts_ram.get(arm, 0) == 0:
                print(f"DEBUG: Kol {arm} atlandı (batarya yok)")
                continue  # Bu kolda batarya yok, atla
                
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
                            value = arm_data[2].get(10, {}).get('value', 0)  # dtype=10
                        elif data_type == 2:  # Nem
                            value = arm_data[2].get(11, {}).get('value', 0)  # dtype=11
                        elif data_type == 3:  # Sıcaklık
                            value = arm_data[2].get(12, {}).get('value', 0)  # dtype=12
                        elif data_type == 4:  # Sıcaklık2
                            value = arm_data[2].get(13, {}).get('value', 0)  # dtype=13
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
                                value = arm_data[k_value].get(10, {}).get('value', 0)  # dtype=10
                            elif data_type == 6:  # SOC
                                value = arm_data[k_value].get(126, {}).get('value', 0)  # dtype=126 (SOC)
                            elif data_type == 7:  # Rint
                                value = arm_data[k_value].get(12, {}).get('value', 0)  # dtype=12
                            elif data_type == 8:  # SOH
                                value = arm_data[k_value].get(11, {}).get('value', 0)  # dtype=11 (SOH)
                            elif data_type == 9:  # NTC1
                                value = arm_data[k_value].get(13, {}).get('value', 0)  # dtype=13
                            elif data_type == 10:  # NTC2
                                value = arm_data[k_value].get(14, {}).get('value', 0)  # dtype=14
                            elif data_type == 11:  # NTC3
                                value = arm_data[k_value].get(15, {}).get('value', 0)  # dtype=15
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
            with data_lock:
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

        class ModbusRAMMibScalarInstance(MibScalarInstance):
            """Modbus TCP Server RAM sistemi ile MIB Instance"""
            def getValue(self, name, **context):
                oid = '.'.join([str(x) for x in name])
                print(f"🔍 SNMP OID sorgusu: {oid}")
                
                # Sistem bilgileri
                if oid == "1.3.6.5.1.0":
                    return self.getSyntax().clone(
                        f"Python {sys.version} running on a {sys.platform} platform"
                    )
                elif oid == "1.3.6.5.2.0":  # totalBatteryCount
                    data = get_battery_data_ram()
                    battery_count = 0
                    for arm in data.keys():
                        for k in data[arm].keys():
                            if k > 2:  # k>2 olanlar batarya verisi
                                battery_count += 1
                    return self.getSyntax().clone(str(battery_count if battery_count > 0 else 0))
                elif oid == "1.3.6.5.3.0":  # totalArmCount
                    data = get_battery_data_ram()
                    return self.getSyntax().clone(str(len(data) if data else 0))
                elif oid == "1.3.6.5.4.0":  # systemStatus
                    return self.getSyntax().clone("1")
                elif oid == "1.3.6.5.5.0":  # lastUpdateTime
                    return self.getSyntax().clone(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                elif oid == "1.3.6.5.6.0":  # dataCount
                    data = get_battery_data_ram()
                    total_data = 0
                    for arm in data.values():
                        for k in arm.values():
                            total_data += len(k)
                    return self.getSyntax().clone(str(total_data if total_data > 0 else 0))
                elif oid == "1.3.6.5.7.0":  # arm1SlaveCount
                    with data_lock:
                        return self.getSyntax().clone(str(arm_slave_counts_ram.get(1, 0)))
                elif oid == "1.3.6.5.8.0":  # arm2SlaveCount
                    with data_lock:
                        return self.getSyntax().clone(str(arm_slave_counts_ram.get(2, 0)))
                elif oid == "1.3.6.5.9.0":  # arm3SlaveCount
                    with data_lock:
                        return self.getSyntax().clone(str(arm_slave_counts_ram.get(3, 0)))
                elif oid == "1.3.6.5.10.0":  # arm4SlaveCount
                    with data_lock:
                        return self.getSyntax().clone(str(arm_slave_counts_ram.get(4, 0)))
                else:
                    # Gerçek batarya verileri - Modbus TCP Server RAM'den oku
                    if oid.startswith("1.3.6.5.10."):
                        parts = oid.split('.')
                        if len(parts) >= 8:  # 1.3.6.5.10.arm.k.dtype.0
                            arm = int(parts[5])    # 1.3.6.5.10.{arm}
                            k = int(parts[6])      # 1.3.6.5.10.arm.{k}
                            dtype = int(parts[7])  # 1.3.6.5.10.arm.k.{dtype}
                            
                            data = get_battery_data_ram(arm, k, dtype)
                            if data:
                                return self.getSyntax().clone(str(data['value']))
                            return self.getSyntax().clone("0")
                    
                    return self.getSyntax().clone("No Such Object")

        # MIB Objects oluştur
        mibBuilder.export_symbols(
            "__MODBUS_RAM_MIB",
            # Sistem bilgileri
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
        
        # Batarya verileri için MIB Objects - Dinamik olarak oluştur
        for arm in range(1, 5):  # 1, 2, 3, 4
            for k in range(2, 6):  # 2, 3, 4, 5
                for dtype in range(10, 15):  # 10, 11, 12, 13, 14
                    oid = (1, 3, 6, 5, 10, arm, k, dtype)
                    mibBuilder.export_symbols(
                        f"__BATTERY_MIB_{arm}_{k}_{dtype}",
                        MibScalar(oid, v2c.OctetString()),
                        ModbusRAMMibScalarInstance(oid, (0,), v2c.OctetString()),
                    )
                
                # SOC verisi için dtype=126
                oid = (1, 3, 6, 5, 10, arm, k, 126)
                mibBuilder.export_symbols(
                    f"__BATTERY_MIB_{arm}_{k}_126",
                    MibScalar(oid, v2c.OctetString()),
                    ModbusRAMMibScalarInstance(oid, (0,), v2c.OctetString()),
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
    with data_lock:
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
    """Reset system sinyali gönder (0x55 0x55 0x55)"""
    try:
        signal_data = [0x55, 0x55, 0x55]
        wave_uart_send(pi, TX_PIN, signal_data, int(1e6 / BAUD_RATE))
        print("🔄 Reset system sinyali gönderildi: 0x55 0x55 0x55")
    except Exception as e:
        print(f"❌ Reset system sinyali gönderilirken hata: {e}")

def add_missing_data(arm_value, battery_value):
    """Missing data ekle"""
    with missing_data_lock:
        missing_data_tracker.add((arm_value, battery_value))
        print(f"📝 Missing data eklendi: Kol {arm_value}, Batarya {battery_value}")

def is_new_missing_data(arm_value, battery_value):
    """Yeni missing data mı kontrol et"""
    with missing_data_lock:
        return (arm_value, battery_value) not in missing_data_tracker

def clear_missing_data():
    """Missing data listesini temizle"""
    with missing_data_lock:
        missing_data_tracker.clear()
        print("🧹 Missing data listesi temizlendi")

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
                
                # Missing data ekle
                add_missing_data(arm_value, slave_value)
                
                # Yeni missing data mı kontrol et
                if is_new_missing_data(arm_value, slave_value):
                    print(f"🆕 YENİ MISSING DATA: Kol {arm_value}, Batarya {slave_value}")
                    
                    # Periyot tamamlandı mı kontrol et
                    if is_period_complete(arm_value, slave_value, is_missing_data=True):
                        # Periyot bitti, alarmları işle
                        alarm_processor.process_period_end()
                        # Reset system sinyali gönder
                        send_reset_system_signal()
                        # Missing data listesini temizle
                        clear_missing_data()
                        # Yeni periyot başlat
                        reset_period()
                        get_period_timestamp()
                else:
                    print(f"🔄 TEKRAR MISSING DATA: Kol {arm_value}, Batarya {slave_value} - Reset sinyali gönderilmedi")
                
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
                    
                    # SOC hesapla ve dtype=126'ya kaydet (sadece batarya verisi için)
                    if k_value != 2:  # k_value 2 değilse SOC hesapla
                        soc_value = Calc_SOC(salt_data)
                        soc_record = {
                            "Arm": arm_value,
                            "k": k_value,
                            "Dtype": 126,
                            "data": soc_value,
                            "timestamp": get_period_timestamp()
                        }
                        batch.append(soc_record)
                
                elif dtype == 11:  # SOH veya Nem
                    if k_value == 2:  # Nem verisi
                        print(f"*** VERİ ALGILANDI - Arm: {arm_value}, Nem: {salt_data}% ***")
                        record = {
                            "Arm": arm_value,
                            "k": k_value,
                            "Dtype": 11,
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
                        
                        # SOH verisini dtype=11'e kaydet (çift kayıt kaldırıldı)
                        record = {
                            "Arm": arm_value,
                            "k": k_value,
                            "Dtype": 11,
                            "data": soh_value,
                            "timestamp": get_period_timestamp()
                        }
                        batch.append(record)
                
                else:  # Diğer Dtype değerleri için
                    record = {
                        "Arm": arm_value,
                        "k": k_value,
                        "Dtype": dtype,
                        "data": salt_data,
                        "timestamp": get_period_timestamp()
                    }
                    batch.append(record)

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
                    
                    print(f"✓ Armslavecounts RAM'e kaydedildi: {arm_slave_counts}")
                    
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

        # Modbus TCP Server thread'i
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

if __name__ == '__main__':
    print("Program başlatıldı ==>")
    main()