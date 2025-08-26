# interface/database.py
import sqlite3
import threading
import os
from datetime import datetime, timedelta
import time

class BatteryDatabase:
    def __init__(self, db_path="battery_data.db"):
        self.db_path = db_path
        self.lock = threading.Lock()
        self.conn = None
        # Veritabanı yoksa oluştur, varsa sadece bağlan
        if not os.path.exists(self.db_path):
            self.init_database()
        else:
            print(f"Veritabanı zaten mevcut: {self.db_path}")
    
    def init_database(self):
        with self.lock:
            print(f"Yeni veritabanı oluşturuluyor: {self.db_path}")
            
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                print("Yeni veritabanı oluşturuluyor...")
                
                # Tek veri tablosu (tüm veriler için)
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS battery_data (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        arm INTEGER,
                        k INTEGER,
                        dtype INTEGER,
                        data REAL,
                        timestamp INTEGER,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                print("✓ battery_data tablosu oluşturuldu")
                
                # Dil tablosu
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS languages (
                        language_code TEXT PRIMARY KEY,
                        language_name TEXT,
                        is_active BOOLEAN DEFAULT TRUE,
                        is_default BOOLEAN DEFAULT FALSE
                    )
                ''')
                print("✓ languages tablosu oluşturuldu")
                
                # Veri tipi tablosu (dtype + k_value ile)
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS data_types (
                        dtype INTEGER,
                        k_value INTEGER,
                        name TEXT,
                        unit TEXT,
                        description TEXT,
                        PRIMARY KEY (dtype, k_value)
                    )
                ''')
                print("✓ data_types tablosu oluşturuldu")
                
                # Veri tipi çevirileri
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS data_type_translations (
                        dtype INTEGER,
                        k_value INTEGER,
                        language_code TEXT,
                        name TEXT,
                        description TEXT,
                        PRIMARY KEY (dtype, k_value, language_code),
                        FOREIGN KEY (language_code) REFERENCES languages(language_code)
                    )
                ''')
                print("✓ data_type_translations tablosu oluşturuldu")
                
                # Alarm tablosu
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS alarms (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        arm INTEGER,
                        error_code_msb INTEGER,
                        error_code_lsb INTEGER,
                        timestamp INTEGER,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                print("✓ alarms tablosu oluşturuldu")
                
                # Missing data tablosu
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS missing_data (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        arm INTEGER,
                        slave INTEGER,
                        status INTEGER,
                        timestamp INTEGER,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                print("✓ missing_data tablosu oluşturuldu")
                
                # Balans tablosu
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS passive_balance (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        arm INTEGER,
                        slave INTEGER,
                        status INTEGER,
                        timestamp INTEGER,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                print("✓ passive_balance tablosu oluşturuldu")
                
                # Arm slave counts tablosu
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS arm_slave_counts (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        arm INTEGER,
                        slave_count INTEGER,
                        timestamp INTEGER,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                print("✓ arm_slave_counts tablosu oluşturuldu")
                
                # Dilleri ekle
                cursor.execute('''
                    INSERT OR IGNORE INTO languages (language_code, language_name, is_active, is_default)
                    VALUES 
                        ('tr', 'Türkçe', TRUE, TRUE),
                        ('en', 'English', TRUE, FALSE),
                        ('de', 'Deutsch', TRUE, FALSE)
                ''')
                print("✓ Diller eklendi")
                
                # Veri tiplerini ekle (k=2: Arm, k!=2: Battery)
                cursor.execute('''
                    INSERT OR IGNORE INTO data_types (dtype, k_value, name, unit, description)
                    VALUES 
                        -- Arm veri tipleri (k=2)
                        (10, 2, 'Akım', 'A', 'Arm akım değeri'),
                        (11, 2, 'Nem', '%', 'Arm nem değeri'),
                        (12, 2, 'Sıcaklık', '°C', 'Arm sıcaklık değeri'),
                        
                        -- Battery veri tipleri (k!=2)
                        (10, 1, 'Gerilim', 'V', 'Batarya gerilim değeri'),
                        (11, 1, 'Şarj Durumu', '%', 'Batarya şarj durumu'),
                        (12, 1, 'Modül Sıcaklığı', '°C', 'Batarya modül sıcaklığı'),
                        (13, 1, 'Pozitif Kutup Başı Sıcaklığı', '°C', 'Pozitif kutup başı sıcaklığı'),
                        (14, 1, 'Negatif Kutup Başı Sıcaklığı', '°C', 'Negatif kutup başı sıcaklığı'),
                        (126, 1, 'Sağlık Durumu', '%', 'Batarya sağlık durumu (SOH)'),
                        
                        -- Battery veri tipleri (k=3,4,5...)
                        (10, 3, 'Gerilim', 'V', 'Batarya gerilim değeri'),
                        (11, 3, 'Şarj Durumu', '%', 'Batarya şarj durumu'),
                        (12, 3, 'Modül Sıcaklığı', '°C', 'Batarya modül sıcaklığı'),
                        (13, 3, 'Pozitif Kutup Başı Sıcaklığı', '°C', 'Pozitif kutup başı sıcaklığı'),
                        (14, 3, 'Negatif Kutup Başı Sıcaklığı', '°C', 'Negatif kutup başı sıcaklığı'),
                        (126, 3, 'Sağlık Durumu', '%', 'Batarya sağlık durumu (SOH)'),
                        
                        (10, 4, 'Gerilim', 'V', 'Batarya gerilim değeri'),
                        (11, 4, 'Şarj Durumu', '%', 'Batarya şarj durumu'),
                        (12, 4, 'Modül Sıcaklığı', '°C', 'Batarya modül sıcaklığı'),
                        (13, 4, 'Pozitif Kutup Başı Sıcaklığı', '°C', 'Pozitif kutup başı sıcaklığı'),
                        (14, 4, 'Negatif Kutup Başı Sıcaklığı', '°C', 'Negatif kutup başı sıcaklığı'),
                        (126, 4, 'Sağlık Durumu', '%', 'Batarya sağlık durumu (SOH)'),
                        
                        (10, 5, 'Gerilim', 'V', 'Batarya gerilim değeri'),
                        (11, 5, 'Şarj Durumu', '%', 'Batarya şarj durumu'),
                        (12, 5, 'Modül Sıcaklığı', '°C', 'Batarya modül sıcaklığı'),
                        (13, 5, 'Pozitif Kutup Başı Sıcaklığı', '°C', 'Pozitif kutup başı sıcaklığı'),
                        (14, 5, 'Negatif Kutup Başı Sıcaklığı', '°C', 'Negatif kutup başı sıcaklığı'),
                        (126, 5, 'Sağlık Durumu', '%', 'Batarya sağlık durumu (SOH)')
                ''')
                print("✓ Veri tipleri eklendi")
                
                # Türkçe çevirileri ekle
                cursor.execute('''
                    INSERT OR IGNORE INTO data_type_translations (dtype, k_value, language_code, name, description)
                    VALUES 
                        -- Arm veri tipleri (k=2)
                        (10, 2, 'tr', 'Akım', 'Arm akım değeri'),
                        (11, 2, 'tr', 'Nem', 'Arm nem değeri'),
                        (12, 2, 'tr', 'Sıcaklık', 'Arm sıcaklık değeri'),
                        
                        -- Battery veri tipleri (k!=2)
                        (10, 1, 'tr', 'Gerilim', 'Batarya gerilim değeri'),
                        (11, 1, 'tr', 'Şarj Durumu', 'Batarya şarj durumu'),
                        (12, 1, 'tr', 'Modül Sıcaklığı', 'Batarya modül sıcaklığı'),
                        (13, 1, 'tr', 'Pozitif Kutup Başı Sıcaklığı', 'Pozitif kutup başı sıcaklığı'),
                        (14, 1, 'tr', 'Negatif Kutup Başı Sıcaklığı', 'Negatif kutup başı sıcaklığı'),
                        (126, 1, 'tr', 'Sağlık Durumu', 'Batarya sağlık durumu (SOH)'),
                        
                        (10, 3, 'tr', 'Gerilim', 'Batarya gerilim değeri'),
                        (11, 3, 'tr', 'Şarj Durumu', 'Batarya şarj durumu'),
                        (12, 3, 'tr', 'Modül Sıcaklığı', 'Batarya modül sıcaklığı'),
                        (13, 3, 'tr', 'Pozitif Kutup Başı Sıcaklığı', 'Pozitif kutup başı sıcaklığı'),
                        (14, 3, 'tr', 'Negatif Kutup Başı Sıcaklığı', 'Negatif kutup başı sıcaklığı'),
                        (126, 3, 'tr', 'Sağlık Durumu', 'Batarya sağlık durumu (SOH)'),
                        
                        (10, 4, 'tr', 'Gerilim', 'Batarya gerilim değeri'),
                        (11, 4, 'tr', 'Şarj Durumu', 'Batarya şarj durumu'),
                        (12, 4, 'tr', 'Modül Sıcaklığı', 'Batarya modül sıcaklığı'),
                        (13, 4, 'tr', 'Pozitif Kutup Başı Sıcaklığı', 'Pozitif kutup başı sıcaklığı'),
                        (14, 4, 'tr', 'Negatif Kutup Başı Sıcaklığı', 'Negatif kutup başı sıcaklığı'),
                        (126, 4, 'tr', 'Sağlık Durumu', 'Batarya sağlık durumu (SOH)'),
                        
                        (10, 5, 'tr', 'Gerilim', 'Batarya gerilim değeri'),
                        (11, 5, 'tr', 'Şarj Durumu', 'Batarya şarj durumu'),
                        (12, 5, 'tr', 'Modül Sıcaklığı', 'Batarya modül sıcaklığı'),
                        (13, 5, 'tr', 'Pozitif Kutup Başı Sıcaklığı', 'Pozitif kutup başı sıcaklığı'),
                        (14, 5, 'tr', 'Negatif Kutup Başı Sıcaklığı', 'Negatif kutup başı sıcaklığı'),
                        (126, 5, 'tr', 'Sağlık Durumu', 'Batarya sağlık durumu (SOH)')
                ''')
                print("✓ Türkçe çeviriler eklendi")
                
                # İngilizce çevirileri ekle
                cursor.execute('''
                    INSERT OR IGNORE INTO data_type_translations (dtype, k_value, language_code, name, description)
                    VALUES 
                        -- Arm veri tipleri (k=2)
                        (10, 2, 'en', 'Current', 'Arm current value'),
                        (11, 2, 'en', 'Humidity', 'Arm humidity value'),
                        (12, 2, 'en', 'Temperature', 'Arm temperature value'),
                        
                        -- Battery veri tipleri (k!=2)
                        (10, 1, 'en', 'Voltage', 'Battery voltage value'),
                        (11, 1, 'en', 'State of Charge', 'Battery state of charge'),
                        (12, 1, 'en', 'Module Temperature', 'Battery module temperature'),
                        (13, 1, 'en', 'Positive Terminal Temperature', 'Positive terminal temperature'),
                        (14, 1, 'en', 'Negative Terminal Temperature', 'Negative terminal temperature'),
                        (126, 1, 'en', 'State of Health', 'Battery state of health (SOH)'),
                        
                        (10, 3, 'en', 'Voltage', 'Battery voltage value'),
                        (11, 3, 'en', 'State of Charge', 'Battery state of charge'),
                        (12, 3, 'en', 'Module Temperature', 'Battery module temperature'),
                        (13, 3, 'en', 'Positive Terminal Temperature', 'Positive terminal temperature'),
                        (14, 3, 'en', 'Negative Terminal Temperature', 'Negative terminal temperature'),
                        (126, 3, 'en', 'State of Health', 'Battery state of health (SOH)'),
                        
                        (10, 4, 'en', 'Voltage', 'Battery voltage value'),
                        (11, 4, 'en', 'State of Charge', 'Battery state of charge'),
                        (12, 4, 'en', 'Module Temperature', 'Battery module temperature'),
                        (13, 4, 'en', 'Positive Terminal Temperature', 'Positive terminal temperature'),
                        (14, 4, 'en', 'Negative Terminal Temperature', 'Negative terminal temperature'),
                        (126, 4, 'en', 'State of Health', 'Battery state of health (SOH)'),
                        
                        (10, 5, 'en', 'Voltage', 'Battery voltage value'),
                        (11, 5, 'en', 'State of Charge', 'Battery state of charge'),
                        (12, 5, 'en', 'Module Temperature', 'Battery module temperature'),
                        (13, 5, 'en', 'Positive Terminal Temperature', 'Positive terminal temperature'),
                        (14, 5, 'en', 'Negative Terminal Temperature', 'Negative terminal temperature'),
                        (126, 5, 'en', 'State of Health', 'Battery state of health (SOH)')
                ''')
                print("✓ İngilizce çeviriler eklendi")
                
                # Almanca çevirileri ekle
                cursor.execute('''
                    INSERT OR IGNORE INTO data_type_translations (dtype, k_value, language_code, name, description)
                    VALUES 
                        -- Arm veri tipleri (k=2)
                        (10, 2, 'de', 'Strom', 'Arm Stromwert'),
                        (11, 2, 'de', 'Luftfeuchtigkeit', 'Arm Luftfeuchtigkeitswert'),
                        (12, 2, 'de', 'Temperatur', 'Arm Temperaturwert'),
                        
                        -- Battery veri tipleri (k!=2)
                        (10, 1, 'de', 'Spannung', 'Batterie Spannungswert'),
                        (11, 1, 'de', 'Ladezustand', 'Batterie Ladezustand'),
                        (12, 1, 'de', 'Modultemperatur', 'Batterie Modultemperatur'),
                        (13, 1, 'de', 'Positive Klemmentemperatur', 'Positive Klemmentemperatur'),
                        (14, 1, 'de', 'Negative Klemmentemperatur', 'Negative Klemmentemperatur'),
                        (126, 1, 'de', 'Gesundheitszustand', 'Batterie Gesundheitszustand (SOH)'),
                        
                        (10, 3, 'de', 'Spannung', 'Batterie Spannungswert'),
                        (11, 3, 'de', 'Ladezustand', 'Batterie Ladezustand'),
                        (12, 3, 'de', 'Modultemperatur', 'Batterie Modultemperatur'),
                        (13, 3, 'de', 'Positive Klemmentemperatur', 'Positive Klemmentemperatur'),
                        (14, 3, 'de', 'Negative Klemmentemperatur', 'Negative Klemmentemperatur'),
                        (126, 3, 'de', 'Gesundheitszustand', 'Batterie Gesundheitszustand (SOH)'),
                        
                        (10, 4, 'de', 'Spannung', 'Batterie Spannungswert'),
                        (11, 4, 'de', 'Ladezustand', 'Batterie Ladezustand'),
                        (12, 4, 'de', 'Modultemperatur', 'Batterie Modultemperatur'),
                        (13, 4, 'de', 'Positive Klemmentemperatur', 'Positive Klemmentemperatur'),
                        (14, 4, 'de', 'Negative Klemmentemperatur', 'Negative Klemmentemperatur'),
                        (126, 4, 'de', 'Gesundheitszustand', 'Batterie Gesundheitszustand (SOH)'),
                        
                        (10, 5, 'de', 'Spannung', 'Batterie Spannungswert'),
                        (11, 5, 'de', 'Ladezustand', 'Batterie Ladezustand'),
                        (12, 5, 'de', 'Modultemperatur', 'Batterie Modultemperatur'),
                        (13, 5, 'de', 'Positive Klemmentemperatur', 'Positive Klemmentemperatur'),
                        (14, 5, 'de', 'Negative Klemmentemperatur', 'Negative Klemmentemperatur'),
                        (126, 5, 'de', 'Gesundheitszustand', 'Battery Gesundheitszustand (SOH)')
                ''')
                print("✓ Almanca çeviriler eklendi")
                
                # Index'ler oluştur
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_k_timestamp ON battery_data(k, timestamp)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_arm_k_dtype ON battery_data(arm, k, dtype)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_alarm_timestamp ON alarms(timestamp)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_timestamp ON battery_data(timestamp)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_arm ON battery_data(arm)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_dtype ON battery_data(dtype)')
                print("✓ Index'ler oluşturuldu")
                
                conn.commit()
                print("✓ Veritabanı başarıyla oluşturuldu!")
                
                # Veritabanı boyutunu göster
                db_size = os.path.getsize(self.db_path) / (1024 * 1024)  # MB
                print(f"Veritabanı boyutu: {db_size:.2f} MB")
    
    def get_connection(self):
        """Thread-safe bağlantı döndür"""
        return sqlite3.connect(self.db_path)
    
    def insert_battery_data(self, arm, k, dtype, data, timestamp):
        """Veri ekle (arm ve battery için tek tablo)"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO battery_data (arm, k, dtype, data, timestamp)
                VALUES (?, ?, ?, ?, ?)
            ''', (arm, k, dtype, data, timestamp))
            conn.commit()
    
    def insert_alarm(self, arm, error_code_msb, error_code_lsb, timestamp):
        """Alarm verisi ekle"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO alarms (arm, error_code_msb, error_code_lsb, timestamp)
                VALUES (?, ?, ?, ?)
            ''', (arm, error_code_msb, error_code_lsb, timestamp))
            conn.commit()
    
    def insert_missing_data(self, arm, slave, status, timestamp):
        """Missing data verisi ekle"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO missing_data (arm, slave, status, timestamp)
                VALUES (?, ?, ?, ?)
            ''', (arm, slave, status, timestamp))
            conn.commit()
    
    def insert_passive_balance(self, arm, slave, status, timestamp):
        """Passive balance verisi ekle"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO passive_balance (arm, slave, status, timestamp)
                VALUES (?, ?, ?, ?)
            ''', (arm, slave, status, timestamp))
            conn.commit()
    
    def insert_arm_slave_counts(self, arm, slave_count, timestamp):
        """Arm slave count verisi ekle"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO arm_slave_counts (arm, slave_count, timestamp)
                VALUES (?, ?, ?)
            ''', (arm, slave_count, timestamp))
            conn.commit()
    
    def get_recent_data_with_translations(self, minutes=5, arm=None, battery=None, dtype=None, data_type=None, limit=100, language='tr'):
        """Son verileri çevirilerle birlikte getir"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Temel sorgu
            query = '''
                SELECT 
                    bd.arm,
                    bd.k as batteryAddress,
                    bd.dtype,
                    bd.data,
                    bd.timestamp,
                    dt.name,
                    dt.unit,
                    COALESCE(dtt.name, dt.name) as translated_name,
                    COALESCE(dtt.description, dt.description) as translated_description
                FROM battery_data bd
                JOIN data_types dt ON bd.dtype = dt.dtype AND bd.k = dt.k_value
                LEFT JOIN data_type_translations dtt ON dt.dtype = dtt.dtype 
                    AND dt.k_value = dtt.k_value 
                    AND dtt.language_code = ?
                WHERE bd.timestamp >= ?
            '''
            
            params = [language, int((datetime.now() - timedelta(minutes=minutes)).timestamp() * 1000)]
            
            # Filtreler
            if arm:
                query += ' AND bd.arm = ?'
                params.append(arm)
            
            if battery:
                query += ' AND bd.k = ?'
                params.append(battery)
            
            if dtype:
                query += ' AND bd.dtype = ?'
                params.append(dtype)
            
            if data_type and data_type != 'all':
                if data_type == 'arm':
                    query += ' AND bd.k = 2'
                elif data_type == 'battery':
                    query += ' AND bd.k != 2'
            
            query += ' ORDER BY bd.timestamp DESC LIMIT ?'
            params.append(limit)
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            
            return [{
                'arm': row[0],
                'batteryAddress': row[1],
                'dtype': row[2],
                'data': row[3],
                'timestamp': row[4],
                'name': row[5],
                'unit': row[6],
                'translated_name': row[7],
                'translated_description': row[8]
            } for row in rows]
    
    def get_data_types_by_language(self, language='tr'):
        """Dile göre veri tiplerini getir"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT 
                    dt.dtype,
                    dt.k_value,
                    COALESCE(dtt.name, dt.name) as name,
                    dt.unit,
                    COALESCE(dtt.description, dt.description) as description
                FROM data_types dt
                LEFT JOIN data_type_translations dtt ON dt.dtype = dtt.dtype 
                    AND dt.k_value = dtt.k_value 
                    AND dtt.language_code = ?
                ORDER BY dt.k_value, dt.dtype
            ''', (language,))
            
            rows = cursor.fetchall()
            return [{
                'dtype': row[0],
                'k_value': row[1],
                'name': row[2],
                'unit': row[3],
                'description': row[4]
            } for row in rows]
    
    def get_data_by_date_range_with_translations(self, start_date, end_date, arm=None, battery=None, dtype=None, language='tr'):
        """Tarih aralığında veri getir (çevirilerle)"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Tarihleri timestamp'e çevir
            start_timestamp = int(datetime.strptime(start_date, '%Y-%m-%d').timestamp() * 1000)
            end_timestamp = int(datetime.strptime(end_date, '%Y-%m-%d').timestamp() * 1000) + (24 * 60 * 60 * 1000) - 1
            
            query = '''
                SELECT 
                    bd.arm,
                    bd.k as batteryAddress,
                    bd.dtype,
                    bd.data,
                    bd.timestamp,
                    dt.name,
                    dt.unit,
                    COALESCE(dtt.name, dt.name) as translated_name,
                    COALESCE(dtt.description, dt.description) as translated_description
                FROM battery_data bd
                JOIN data_types dt ON bd.dtype = dt.dtype AND bd.k = dt.k_value
                LEFT JOIN data_type_translations dtt ON dt.dtype = dtt.dtype 
                    AND dt.k_value = dtt.k_value 
                    AND dtt.language_code = ?
                WHERE bd.timestamp >= ? AND bd.timestamp <= ?
            '''
            
            params = [language, start_timestamp, end_timestamp]
            
            if arm:
                query += ' AND bd.arm = ?'
                params.append(arm)
            
            if battery:
                query += ' AND bd.k = ?'
                params.append(battery)
            
            if dtype:
                query += ' AND bd.dtype = ?'
                params.append(dtype)
            
            query += ' ORDER BY bd.timestamp DESC'
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            
            return [{
                'arm': row[0],
                'batteryAddress': row[1],
                'dtype': row[2],
                'data': row[3],
                'timestamp': row[4],
                'name': row[5],
                'unit': row[6],
                'translated_name': row[7],
                'translated_description': row[8]
            } for row in rows]
    
    def get_logs_with_filters(self, page=1, page_size=50, filters=None):
        """Filtrelenmiş log verilerini getir"""
        if filters is None:
            filters = {}
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Temel sorgu
            query = '''
                SELECT 
                    bd.arm,
                    bd.k as batteryAddress,
                    bd.dtype,
                    bd.data,
                    bd.timestamp,
                    dt.name,
                    dt.unit
                FROM battery_data bd
                JOIN data_types dt ON bd.dtype = dt.dtype AND bd.k = dt.k_value
                WHERE 1=1
            '''
            
            params = []
            
            # Filtreler
            if filters.get('arm'):
                query += ' AND bd.arm = ?'
                params.append(filters['arm'])
            
            if filters.get('battery'):
                query += ' AND bd.k = ?'
                params.append(filters['battery'])
            
            if filters.get('dtype'):
                query += ' AND bd.dtype = ?'
                params.append(filters['dtype'])
            
            if filters.get('status'):
                if filters['status'] == 'success':
                    query += ' AND bd.data > 0'
                elif filters['status'] == 'error':
                    query += ' AND bd.data <= 0'
                elif filters['status'] == 'warning':
                    query += ' AND bd.data BETWEEN 0 AND 50'
            
            if filters.get('start_date'):
                start_timestamp = int(datetime.strptime(filters['start_date'], '%Y-%m-%d').timestamp() * 1000)
                query += ' AND bd.timestamp >= ?'
                params.append(start_timestamp)
            
            if filters.get('end_date'):
                end_timestamp = int(datetime.strptime(filters['end_date'], '%Y-%m-%d').timestamp() * 1000) + (24 * 60 * 60 * 1000) - 1
                query += ' AND bd.timestamp <= ?'
                params.append(end_timestamp)
            
            # Toplam sayı
            count_query = f"SELECT COUNT(*) FROM ({query})"
            cursor.execute(count_query, params)
            total_count = cursor.fetchone()[0]
            
            # Sayfalama
            query += ' ORDER BY bd.timestamp DESC LIMIT ? OFFSET ?'
            params.extend([page_size, (page - 1) * page_size])
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            
            logs = []
            for row in rows:
                # Status belirle
                status = 'success'
                if row[3] <= 0:
                    status = 'error'
                elif row[3] < 50:
                    status = 'warning'
                
                logs.append({
                    'arm': row[0],
                    'batteryAddress': row[1],
                    'dtype': row[2],
                    'data': row[3],
                    'timestamp': row[4],
                    'name': row[5],
                    'unit': row[6],
                    'status': status
                })
            
            return {
                'logs': logs,
                'totalCount': total_count,
                'totalPages': (total_count + page_size - 1) // page_size,
                'currentPage': page
            }
    
    def export_logs_to_csv(self, filters=None):
        """Log verilerini CSV formatında export et"""
        if filters is None:
            filters = {}
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            query = '''
                SELECT 
                    bd.arm,
                    bd.k as batteryAddress,
                    bd.dtype,
                    bd.data,
                    bd.timestamp,
                    dt.name,
                    dt.unit
                FROM battery_data bd
                JOIN data_types dt ON bd.dtype = dt.dtype AND bd.k = dt.k_value
                WHERE 1=1
            '''
            
            params = []
            
            # Filtreler
            if filters.get('arm'):
                query += ' AND bd.arm = ?'
                params.append(filters['arm'])
            
            if filters.get('battery'):
                query += ' AND bd.k = ?'
                params.append(filters['battery'])
            
            if filters.get('dtype'):
                query += ' AND bd.dtype = ?'
                params.append(filters['dtype'])
            
            if filters.get('status'):
                if filters['status'] == 'success':
                    query += ' AND bd.data > 0'
                elif filters['status'] == 'error':
                    query += ' AND bd.data <= 0'
                elif filters['status'] == 'warning':
                    query += ' AND bd.data BETWEEN 0 AND 50'
            
            if filters.get('start_date'):
                start_timestamp = int(datetime.strptime(filters['start_date'], '%Y-%m-%d').timestamp() * 1000)
                query += ' AND bd.timestamp >= ?'
                params.append(start_timestamp)
            
            if filters.get('end_date'):
                end_timestamp = int(datetime.strptime(filters['end_date'], '%Y-%m-%d').timestamp() * 1000) + (24 * 60 * 60 * 1000) - 1
                query += ' AND bd.timestamp <= ?'
                params.append(end_timestamp)
            
            query += ' ORDER BY bd.timestamp DESC'
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            
            # CSV formatı
            csv_content = "ZAMAN,KOL,BATARYA ADRESİ,VERİ TÜRÜ,VERİ,DURUM\n"
            
            for row in rows:
                timestamp = datetime.fromtimestamp(row[4] / 1000).strftime('%Y-%m-%d %H:%M:%S')
                status = 'Başarılı' if row[3] > 0 else 'Hata' if row[3] <= 0 else 'Uyarı'
                
                csv_content += f"{timestamp},{row[0]},{row[1]},{row[5]},{row[3]},{status}\n"
            
            return csv_content