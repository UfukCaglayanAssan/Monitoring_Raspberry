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
        self.init_database()
    
    def init_database(self):
        with self.lock:
            # Veritabanı dosyasını tamamen sil
            if os.path.exists(self.db_path):
                try:
                    os.remove(self.db_path)
                    print(f"Eski veritabanı silindi: {self.db_path}")
                except Exception as e:
                    print(f"Veritabanı silinirken hata: {e}")
            
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
                        slave INTEGER,
                        arm INTEGER,
                        status INTEGER,
                        updatedAt INTEGER,
                        timestamp INTEGER,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                print("✓ passive_balance tablosu oluşturuldu")
                
                # Armslave counts tablosu
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS arm_slave_counts (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        arm1 INTEGER,
                        arm2 INTEGER,
                        arm3 INTEGER,
                        arm4 INTEGER,
                        updatedAt INTEGER,
                        timestamp INTEGER,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                print("✓ arm_slave_counts tablosu oluşturuldu")
                
                # Dilleri ekle
                cursor.execute('''
                    INSERT OR IGNORE INTO languages VALUES 
                    ('tr', 'Türkçe', TRUE, TRUE),
                    ('en', 'English', TRUE, FALSE),
                    ('de', 'Deutsch', TRUE, FALSE)
                ''')
                print("✓ Diller eklendi")
                
                # Veri tiplerini ekle
                cursor.execute('''
                    INSERT OR IGNORE INTO data_types VALUES 
                    -- Kol veri tipleri (k=2)
                    (10, 2, 'Akım', 'A', 'Kol akım değeri'),
                    (11, 2, 'Nem', '%', 'Kol nem değeri'),
                    (12, 2, 'Sıcaklık', '°C', 'Kol sıcaklık değeri'),
                    
                    -- Batarya veri tipleri (k!=2)
                    (10, 3, 'Gerilim', 'V', 'Batarya gerilim değeri'),
                    (11, 3, 'Şarj Durumu', '%', 'State of Charge (SOC)'),
                    (12, 3, 'Modül Sıcaklığı', '°C', 'Batarya modül sıcaklığı'),
                    (13, 3, 'Pozitif Kutup Sıcaklığı', '°C', 'Pozitif kutup başı sıcaklığı'),
                    (14, 3, 'Negatif Kutup Sıcaklığı', '°C', 'Negatif kutup başı sıcaklığı'),
                    (126, 3, 'Sağlık Durumu', '%', 'State of Health (SOH)')
                ''')
                print("✓ Veri tipleri eklendi")
                
                # Türkçe çevirileri ekle
                cursor.execute('''
                    INSERT OR IGNORE INTO data_type_translations VALUES
                    (10, 2, 'tr', 'Akım', 'Kol akım değeri'),
                    (11, 2, 'tr', 'Nem', 'Kol nem değeri'),
                    (12, 2, 'tr', 'Sıcaklık', 'Kol sıcaklık değeri'),
                    (10, 3, 'tr', 'Gerilim', 'Batarya gerilim değeri'),
                    (11, 3, 'tr', 'Şarj Durumu', 'Batarya şarj durumu'),
                    (12, 3, 'tr', 'Modül Sıcaklığı', 'Batarya modül sıcaklığı'),
                    (13, 3, 'tr', 'Pozitif Kutup Sıcaklığı', 'Pozitif kutup başı sıcaklığı'),
                    (14, 3, 'tr', 'Negatif Kutup Sıcaklığı', 'Negatif kutup başı sıcaklığı'),
                    (126, 3, 'tr', 'Sağlık Durumu', 'Batarya sağlık durumu')
                ''')
                print("✓ Türkçe çeviriler eklendi")
                
                # İngilizce çevirileri ekle
                cursor.execute('''
                    INSERT OR IGNORE INTO data_type_translations VALUES
                    (10, 2, 'en', 'Current', 'Arm current value'),
                    (11, 2, 'en', 'Humidity', 'Arm humidity value'),
                    (12, 2, 'en', 'Temperature', 'Arm temperature value'),
                    (10, 3, 'en', 'Voltage', 'Battery voltage value'),
                    (11, 3, 'en', 'State of Charge', 'Battery charge state'),
                    (12, 3, 'en', 'Module Temperature', 'Battery module temperature'),
                    (13, 3, 'en', 'Positive Terminal Temperature', 'Positive terminal temperature'),
                    (14, 3, 'en', 'Negative Terminal Temperature', 'Negative terminal temperature'),
                    (126, 3, 'en', 'State of Health', 'Battery health state')
                ''')
                print("✓ İngilizce çeviriler eklendi")
                
                # Performans için index'ler
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_k_timestamp ON battery_data(k, timestamp)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_arm_k_dtype ON battery_data(arm, k, dtype)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_alarm_timestamp ON alarms(timestamp)')
                print("✓ Index'ler oluşturuldu")
                
                conn.commit()
                print("✓ Veritabanı başarıyla oluşturuldu!")
    
    def insert_battery_data(self, data_list):
        """Battery data ekle - tek tabloya ekle"""
        with self.lock:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                for item in data_list:
                    cursor.execute('''
                        INSERT INTO battery_data 
                        (arm, k, dtype, data, timestamp)
                        VALUES (?, ?, ?, ?, ?)
                    ''', (
                        item.get('Arm', 0),
                        item.get('k', 0),
                        item.get('Dtype', 0),
                        item.get('data', 0.0),
                        item.get('timestamp', 0)
                    ))
                
                conn.commit()
    
    def get_recent_data_with_translations(self, minutes=5, arm=None, battery=None, 
                                         dtype=None, data_type=None, limit=50, language='tr'):
        """Son X dakikanın verilerini seçilen dilde getir"""
        with self.lock:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cutoff_time = int((time.time() - minutes * 60) * 1000)
                
                query = '''
                    SELECT 
                        bd.arm as Kol,
                        CASE 
                            WHEN bd.k = 2 THEN 'Kol'
                            ELSE 'Batarya ' || bd.k
                        END as Tip,
                        COALESCE(dtt.name, dt.name) as VeriTipi,
                        dt.unit as Birim,
                        bd.data as Deger,
                        datetime(bd.timestamp/1000, 'unixepoch') as Zaman,
                        bd.timestamp as RawTimestamp
                    FROM battery_data bd
                    JOIN data_types dt ON bd.dtype = dt.dtype AND bd.k = dt.k_value
                    LEFT JOIN data_type_translations dtt ON bd.dtype = dtt.dtype 
                        AND bd.k = dtt.k_value AND dtt.language_code = ?
                    WHERE bd.timestamp >= ?
                '''
                
                params = [language, cutoff_time]
                
                if arm is not None:
                    query += " AND bd.arm = ?"
                    params.append(arm)
                if battery is not None:
                    query += " AND bd.k = ?"
                    params.append(battery)
                if dtype is not None:
                    query += " AND bd.dtype = ?"
                    params.append(dtype)
                if data_type == 'arm':
                    query += " AND bd.k = 2"
                elif data_type == 'battery':
                    query += " AND bd.k != 2"
                
                query += " ORDER BY bd.timestamp DESC LIMIT ?"
                params.append(limit)
                
                cursor.execute(query, params)
                return cursor.fetchall()
    
    def get_data_types_by_language(self, language='tr'):
        """Seçilen dilde veri tiplerini getir"""
        with self.lock:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                query = '''
                    SELECT 
                        dt.dtype,
                        dt.k_value,
                        COALESCE(dtt.name, dt.name) as name,
                        dt.unit,
                        COALESCE(dtt.description, dt.description) as description
                    FROM data_types dt
                    LEFT JOIN data_type_translations dtt ON dt.dtype = dtt.dtype 
                        AND dt.k_value = dtt.k_value AND dtt.language_code = ?
                    ORDER BY dt.k_value, dt.dtype
                '''
                
                cursor.execute(query, [language])
                return cursor.fetchall()
    
    def insert_alarm(self, alarm_data):
        """Alarm verisi ekle"""
        with self.lock:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO alarms
                    (arm, error_code_msb, error_code_lsb, timestamp)
                    VALUES (?, ?, ?, ?)
                ''', (alarm_data['Arm'], alarm_data['error_code_msb'], 
                      alarm_data['error_code_lsb'], alarm_data['timestamp']))
                conn.commit()
                print(f"✓ Alarm verisi eklendi: Arm={alarm_data['Arm']}")

    def insert_arm_slave_counts(self, counts_data):
        """Arm slave sayıları verisi ekle"""
        with self.lock:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO arm_slave_counts
                    (arm1, arm2, arm3, arm4, updatedAt, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (counts_data['arm1'], counts_data['arm2'], 
                      counts_data['arm3'], counts_data['arm4'], 
                      counts_data['updatedAt'], counts_data['timestamp']))
                conn.commit()
                print(f"✓ Arm slave sayıları eklendi: arm1={counts_data['arm1']}, arm2={counts_data['arm2']}, arm3={counts_data['arm3']}, arm4={counts_data['arm4']}")

    def insert_missing_data(self, missing_data):
        """Missing data verisi ekle"""
        with self.lock:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO missing_data
                    (arm, slave, status, timestamp)
                    VALUES (?, ?, ?, ?)
                ''', (missing_data['arm'], missing_data['slave'], 
                      missing_data['status'], missing_data['timestamp']))
                conn.commit()
                print(f"✓ Missing data eklendi: Arm={missing_data['arm']}, Slave={missing_data['slave']}, Status={missing_data['status']}")

    def insert_passive_balance(self, balance_data):
        """Pasif balans verisi ekle"""
        with self.lock:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO passive_balance
                    (slave, arm, status, updatedAt, timestamp)
                    VALUES (?, ?, ?, ?, ?)
                ''', (balance_data['slave'], balance_data['arm'], 
                      balance_data['status'], balance_data['updatedAt'], 
                      balance_data['timestamp']))
                conn.commit()
                print(f"✓ Pasif balans eklendi: Arm={balance_data['arm']}, Slave={balance_data['slave']}, Status={balance_data['status']}")

    def get_database_size(self):
        """Veritabanı boyutunu kontrol et"""
        import os
        if os.path.exists(self.db_path):
            size_mb = os.path.getsize(self.db_path) / (1024 * 1024)
            return size_mb
        return 0