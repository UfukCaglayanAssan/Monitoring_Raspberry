import sqlite3
import threading
from datetime import datetime, timedelta
import time

class BatteryDatabase:
    def __init__(self, db_path="battery_data.db"):
        self.db_path = db_path
        self.lock = threading.Lock()
        self.init_database()
    
    def init_database(self):
        with self.lock:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Mevcut tabloları temizle
                cursor.execute('DROP TABLE IF EXISTS arm_data')
                cursor.execute('DROP TABLE IF EXISTS battery_data')
                cursor.execute('DROP TABLE IF EXISTS arm_data_types')
                cursor.execute('DROP TABLE IF EXISTS battery_data_types')
                cursor.execute('DROP TABLE IF EXISTS alarms')
                cursor.execute('DROP TABLE IF EXISTS missing_data')
                cursor.execute('DROP TABLE IF EXISTS passive_balances')
                cursor.execute('DROP TABLE IF EXISTS arm_slave_counts')
                
                # Kol verileri tablosu (k=2)
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS arm_data (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        arm INTEGER,
                        dtype INTEGER,
                        data REAL,
                        timestamp INTEGER,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                
                # Batarya verileri tablosu (k!=2)
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
                
                # Kol veri tipi tanımlama tablosu
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS arm_data_types (
                        dtype INTEGER PRIMARY KEY,
                        name TEXT,
                        unit TEXT,
                        description TEXT
                    )
                ''')
                
                # Batarya veri tipi tanımlama tablosu
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS battery_data_types (
                        dtype INTEGER PRIMARY KEY,
                        name TEXT,
                        unit TEXT,
                        description TEXT
                    )
                ''')
                
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
                
                # Kol veri tipi tanımlarını ekle (k=2)
                cursor.execute('''
                    INSERT OR IGNORE INTO arm_data_types VALUES 
                    (10, 'Akım', 'A', 'Kol akım değeri'),
                    (11, 'Nem', '%', 'Kol nem değeri'),
                    (12, 'Sıcaklık', '°C', 'Kol sıcaklık değeri')
                ''')
                
                # Batarya veri tipi tanımlarını ekle (k!=2)
                cursor.execute('''
                    INSERT OR IGNORE INTO battery_data_types VALUES 
                    (10, 'Gerilim', 'V', 'Batarya gerilim değeri'),
                    (11, 'Şarj Durumu', '%', 'Batarya şarj durumu'),
                    (12, 'Modül Sıcaklığı', '°C', 'Batarya modül sıcaklığı'),
                    (13, 'Pozitif Kutup Başı Sıcaklığı', '°C', 'Pozitif kutup başı sıcaklığı'),
                    (14, 'Negatif Kutup Başı Sıcaklığı', '°C', 'Negatif kutup başı sıcaklığı'),
                    (126, 'Sağlık Durumu', '%', 'Batarya sağlık durumu (SOH)')
                ''')
                
                # Performans için index'ler
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_arm_dtype ON arm_data(arm, dtype)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_arm_timestamp ON arm_data(timestamp)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_battery_arm_k_dtype ON battery_data(arm, k, dtype)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_battery_timestamp ON battery_data(timestamp)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_alarm_timestamp ON alarms(timestamp)')
                
                conn.commit()
    
    def insert_battery_data(self, data_list):
        """Battery data ekle - k değerine göre farklı tablolara ekle"""
        with self.lock:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                for item in data_list:
                    k_value = item.get('k', 0)
                    dtype = item.get('Dtype', 0)
                    
                    # k=2 ise kol verisi (arm_data tablosuna)
                    if k_value == 2:
                        cursor.execute('''
                            INSERT INTO arm_data 
                            (arm, dtype, data, timestamp)
                            VALUES (?, ?, ?, ?)
                        ''', (
                            item.get('Arm', 0),
                            dtype,
                            item.get('data', 0.0),
                            item.get('timestamp', 0)
                        ))
                    # k!=2 ise batarya verisi (battery_data tablosuna)
                    else:
                        cursor.execute('''
                            INSERT INTO battery_data 
                            (arm, k, dtype, data, timestamp)
                            VALUES (?, ?, ?, ?, ?)
                        ''', (
                            item.get('Arm', 0),
                            k_value,
                            dtype,
                            item.get('data', 0.0),
                            item.get('timestamp', 0)
                        ))
                
                conn.commit()
    
    def get_recent_data(self, minutes=5, arm=None, battery=None, dtype=None, data_type=None, limit=50):
        """Son X dakikanın verilerini getir (tarih seçimi yapılmadığında)"""
        with self.lock:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Son X dakikanın timestamp'i
                cutoff_time = int((time.time() - minutes * 60) * 1000)
                
                all_data = []
                
                # Veri tipi filtresine göre kol verilerini getir
                if data_type in [None, 'all', 'arm']:
                    arm_query = '''
                        SELECT 
                            ad.arm as Kol,
                            'Kol' as Tip,
                            adt.name as VeriTipi,
                            adt.unit as Birim,
                            ad.data as Deger,
                            datetime(ad.timestamp/1000, 'unixepoch') as Zaman,
                            ad.timestamp as RawTimestamp
                        FROM arm_data ad
                        JOIN arm_data_types adt ON ad.dtype = adt.dtype
                        WHERE ad.timestamp >= ?
                    '''
                    
                    arm_params = [cutoff_time]
                    
                    if arm is not None:
                        arm_query += " AND ad.arm = ?"
                        arm_params.append(arm)
                    if dtype is not None:
                        arm_query += " AND ad.dtype = ?"
                        arm_params.append(dtype)
                    
                    arm_query += " ORDER BY ad.timestamp DESC"
                    
                    cursor.execute(arm_query, arm_params)
                    arm_data = cursor.fetchall()
                    all_data.extend(arm_data)
                
                # Veri tipi filtresine göre batarya verilerini getir
                if data_type in [None, 'all', 'battery']:
                    battery_query = '''
                        SELECT 
                            bd.arm as Kol,
                            'Batarya ' || bd.k as Tip,
                            bdt.name as VeriTipi,
                            bdt.unit as Birim,
                            bd.data as Deger,
                            datetime(bd.timestamp/1000, 'unixepoch') as Zaman,
                            bd.timestamp as RawTimestamp
                        FROM battery_data bd
                        JOIN battery_data_types bdt ON bd.dtype = bdt.dtype
                        WHERE bd.timestamp >= ?
                    '''
                    
                    battery_params = [cutoff_time]
                    
                    if arm is not None:
                        battery_query += " AND bd.arm = ?"
                        battery_params.append(arm)
                    if battery is not None:
                        battery_query += " AND bd.k = ?"
                        battery_params.append(battery)
                    if dtype is not None:
                        battery_query += " AND bd.dtype = ?"
                        battery_params.append(dtype)
                    
                    battery_query += " ORDER BY bd.timestamp DESC"
                    
                    cursor.execute(battery_query, battery_params)
                    battery_data = cursor.fetchall()
                    all_data.extend(battery_data)
                
                # Verileri timestamp'e göre sırala
                all_data.sort(key=lambda x: x[6], reverse=True)
                
                return all_data[:limit]
    
    def get_data_by_date_range(self, start_date, end_date, arm=None, dtype=None, page=1, page_size=50):
        """Tarih aralığına göre veri getir (sayfalama ile)"""
        with self.lock:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Tarihleri timestamp'e çevir
                start_timestamp = int(datetime.strptime(start_date, '%Y-%m-%d').timestamp() * 1000)
                end_timestamp = int(datetime.strptime(end_date, '%Y-%m-%d').timestamp() * 1000) + (24 * 60 * 60 * 1000) - 1
                
                # Toplam kayıt sayısını al
                count_query = '''
                    SELECT COUNT(*) FROM battery_data bd
                    WHERE bd.timestamp BETWEEN ? AND ?
                '''
                
                count_params = [start_timestamp, end_timestamp]
                
                if arm is not None:
                    count_query += " AND bd.arm = ?"
                    count_params.append(arm)
                if dtype is not None:
                    count_query += " AND bd.dtype = ?"
                    count_params.append(dtype)
                
                cursor.execute(count_query, count_params)
                total_count = cursor.fetchone()[0]
                
                # Sayfalama hesapla
                offset = (page - 1) * page_size
                total_pages = (total_count + page_size - 1) // page_size
                
                # Veriyi getir
                data_query = '''
                    SELECT 
                        bd.arm as Kol,
                        bd.k as Batarya,
                        dt.name as VeriTipi,
                        dt.unit as Birim,
                        bd.data as Deger,
                        datetime(bd.timestamp/1000, 'unixepoch') as Zaman,
                        bd.timestamp as RawTimestamp
                    FROM battery_data bd
                    JOIN data_types dt ON bd.dtype = dt.dtype
                    WHERE bd.timestamp BETWEEN ? AND ?
                '''
                
                data_params = [start_timestamp, end_timestamp]
                
                if arm is not None:
                    data_query += " AND bd.arm = ?"
                    data_params.append(arm)
                if dtype is not None:
                    data_query += " AND bd.dtype = ?"
                    data_params.append(dtype)
                
                data_query += " ORDER BY bd.timestamp DESC LIMIT ? OFFSET ?"
                data_params.extend([page_size, offset])
                
                cursor.execute(data_query, data_params)
                data = cursor.fetchall()
                
                return {
                    'data': data,
                    'pagination': {
                        'current_page': page,
                        'total_pages': total_pages,
                        'total_count': total_count,
                        'page_size': page_size,
                        'has_next': page < total_pages,
                        'has_prev': page > 1
                    }
                }
    
    def get_latest_data(self, arm=None, dtype=None, limit=100):
        """Son verileri getir"""
        with self.lock:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                query = "SELECT * FROM battery_data"
                params = []
                
                if arm is not None:
                    query += " WHERE arm = ?"
                    params.append(arm)
                    if dtype is not None:
                        query += " AND dtype = ?"
                        params.append(dtype)
                elif dtype is not None:
                    query += " WHERE dtype = ?"
                    params.append(dtype)
                
                query += " ORDER BY timestamp DESC LIMIT ?"
                params.append(limit)
                
                cursor.execute(query, params)
                return cursor.fetchall()
    
    def get_formatted_data(self, arm=None, k=None, limit=100):
        """Formatlanmış veri getir"""
        with self.lock:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                query = '''
                    SELECT 
                        bd.arm as Kol,
                        bd.k as Batarya,
                        CASE 
                            WHEN bd.k = 2 THEN
                                CASE bd.dtype
                                    WHEN 10 THEN 'Akım'
                                    WHEN 11 THEN 'Nem'
                                    WHEN 12 THEN 'Sıcaklık'
                                    ELSE dt.name
                                END
                            ELSE
                                CASE bd.dtype
                                    WHEN 10 THEN 'Gerilim'
                                    WHEN 11 THEN 'Şarj Durumu'
                                    WHEN 12 THEN 'Modül Sıcaklığı'
                                    WHEN 13 THEN 'Pozitif Kutup Başı Sıcaklığı'
                                    WHEN 14 THEN 'Negatif Kutup Başı Sıcaklığı'
                                    WHEN 126 THEN 'Sağlık Durumu'
                                    ELSE dt.name
                                END
                        END as VeriTipi,
                        CASE 
                            WHEN bd.k = 2 THEN
                                CASE bd.dtype
                                    WHEN 10 THEN 'A'
                                    WHEN 11 THEN '%'
                                    WHEN 12 THEN '°C'
                                    ELSE dt.unit
                                END
                            ELSE
                                CASE bd.dtype
                                    WHEN 10 THEN 'V'
                                    WHEN 11 THEN '%'
                                    WHEN 12 THEN '°C'
                                    WHEN 13 THEN '°C'
                                    WHEN 14 THEN '°C'
                                    WHEN 126 THEN '%'
                                    ELSE dt.unit
                                END
                        END as Birim,
                        bd.data as Deger,
                        datetime(bd.timestamp/1000, 'unixepoch') as Zaman
                    FROM battery_data bd
                    JOIN data_types dt ON bd.dtype = dt.dtype
                '''
                
                params = []
                if arm:
                    query += " WHERE bd.arm = ?"
                    params.append(arm)
                    if k:
                        query += " AND bd.k = ?"
                        params.append(k)
                
                query += " ORDER BY bd.timestamp DESC LIMIT ?"
                params.append(limit)
                
                cursor.execute(query, params)
                return cursor.fetchall()
    
    def get_stats(self):
        """İstatistikleri getir"""
        with self.lock:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Toplam kayıt sayısı
                cursor.execute('SELECT COUNT(*) FROM battery_data')
                total_records = cursor.fetchone()[0]
                
                # Son 24 saatteki kayıt sayısı
                end_time = int(time.time() * 1000)
                start_time = end_time - (24 * 3600 * 1000)
                cursor.execute('SELECT COUNT(*) FROM battery_data WHERE timestamp BETWEEN ? AND ?', (start_time, end_time))
                last_24h = cursor.fetchone()[0]
                
                # Veritabanı boyutu
                db_size = self.get_database_size()
                
                return {
                    'total_records': total_records,
                    'last_24h_records': last_24h,
                    'database_size_mb': round(db_size, 2)
                }
    
    def cleanup_old_data(self, days=30):
        """Eski verileri temizle - disk alanı için"""
        with self.lock:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cutoff_time = int((time.time() - days * 24 * 3600) * 1000)
                cursor.execute('DELETE FROM battery_data WHERE timestamp < ?', (cutoff_time,))
                conn.commit()
    
    def get_database_size(self):
        """Veritabanı boyutunu kontrol et"""
        import os
        if os.path.exists(self.db_path):
            size_mb = os.path.getsize(self.db_path) / (1024 * 1024)
            return size_mb
        return 0

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