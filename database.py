# interface/database.py
import sqlite3
import threading
import os
from datetime import datetime, timedelta
import time
import queue
from contextlib import contextmanager

class BatteryDatabase:
    def __init__(self, db_path="battery_data.db", max_connections=20):
        self.db_path = db_path
        self.lock = threading.Lock()
        self.connection_pool = queue.Queue(maxsize=max_connections)
        self.max_connections = max_connections
        self._create_connections()
        # Veritabanı yoksa oluştur, varsa sadece bağlan
        if not os.path.exists(self.db_path):
            self.init_database()
        else:
            print(f"Veritabanı zaten mevcut: {self.db_path}")
            # Mevcut veritabanında default değerleri kontrol et
            self.check_default_arm_slave_counts()
    
    def _create_connections(self):
        """Connection pool oluştur - thread-safe ve performanslı"""
        for _ in range(self.max_connections):
            conn = sqlite3.connect(
                self.db_path, 
                timeout=60.0,  # Daha uzun timeout
                check_same_thread=False  # Thread-safe için
            )
            # Performans ve concurrency optimizasyonları
            conn.execute("PRAGMA journal_mode=WAL")  # WAL mode for better concurrency
            conn.execute("PRAGMA synchronous=NORMAL")  # Faster writes
            conn.execute("PRAGMA cache_size=50000")  # Çok daha büyük cache
            conn.execute("PRAGMA temp_store=MEMORY")  # Temp tabloları memory'de
            conn.execute("PRAGMA mmap_size=268435456")  # 256MB mmap
            conn.execute("PRAGMA page_size=4096")  # 4KB page size
            conn.execute("PRAGMA auto_vacuum=INCREMENTAL")  # Incremental vacuum
            conn.execute("PRAGMA foreign_keys=ON")  # Foreign key constraints
            conn.execute("PRAGMA busy_timeout=30000")  # 30 saniye busy timeout
            self.connection_pool.put(conn)
    
    @contextmanager
    def get_connection(self):
        """Connection pool'dan connection al - thread-safe ve güçlü"""
        conn = None
        retry_count = 0
        max_retries = 3
        
        while retry_count < max_retries:
            try:
                with self.lock:  # Thread-safe access
                    conn = self.connection_pool.get(timeout=10.0)  # Daha uzun timeout
                yield conn
                break
            except queue.Empty:
                retry_count += 1
                if retry_count >= max_retries:
                    print(f"❌ Connection pool timeout after {max_retries} retries")
                    # Yeni connection oluştur
                    conn = sqlite3.connect(
                        self.db_path, 
                        timeout=30.0,
                        check_same_thread=False
                    )
                    conn.execute("PRAGMA journal_mode=WAL")
                    conn.execute("PRAGMA synchronous=NORMAL")
                    conn.execute("PRAGMA cache_size=50000")
                    yield conn
                else:
                    print(f"⚠️ Connection pool timeout, retry {retry_count}/{max_retries}")
                    time.sleep(0.1)  # Kısa bekleme
            finally:
                if conn:
                    try:
                        with self.lock:  # Thread-safe return
                            self.connection_pool.put(conn)
                    except queue.Full:
                        # Pool dolu, connection'ı kapat
                        conn.close()
    
    def init_database(self):
        with self.lock:
            print(f"Yeni veritabanı oluşturuluyor: {self.db_path}")
            
            with sqlite3.connect(self.db_path, check_same_thread=False) as conn:
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
                
                # Veri tipi tablosu (sadece dtype ile)
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS data_types (
                        dtype INTEGER PRIMARY KEY,
                        name TEXT,
                        unit TEXT,
                        description TEXT
                    )
                ''')
                print("✓ data_types tablosu oluşturuldu")
                
                # Veri tipi çevirileri
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS data_type_translations (
                        dtype INTEGER,
                        language_code TEXT,
                        name TEXT,
                        description TEXT,
                        PRIMARY KEY (dtype, language_code),
                        FOREIGN KEY (language_code) REFERENCES languages(language_code)
                    )
                ''')
                print("✓ data_type_translations tablosu oluşturuldu")
                
                # Alarm tablosu
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS alarms (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        arm INTEGER,
                        battery INTEGER,
                        error_code_msb INTEGER,
                        error_code_lsb INTEGER,
                        timestamp INTEGER,
                        status TEXT DEFAULT 'active',
                        resolved_at DATETIME,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                print("✓ alarms tablosu oluşturuldu")
                
                # Mail alıcıları tablosu
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS mail_recipients (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT NOT NULL,
                        email TEXT NOT NULL UNIQUE,
                        is_active BOOLEAN DEFAULT 1,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                print("✓ mail_recipients tablosu oluşturuldu")
                
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
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                print("✓ arm_slave_counts tablosu oluşturuldu")
                
                # Default arm_slave_counts değerlerini ekle
                cursor.execute('''
                    INSERT INTO arm_slave_counts (arm, slave_count) 
                    VALUES 
                        (1, 0),
                        (2, 0), 
                        (3, 7),
                        (4, 0)
                ''')
                print("✓ Default arm_slave_counts değerleri eklendi: Kol 1=0, Kol 2=0, Kol 3=7, Kol 4=0")
                
                # Dilleri ekle
                cursor.execute('''
                    INSERT OR IGNORE INTO languages (language_code, language_name, is_active, is_default)
                    VALUES 
                        ('tr', 'Türkçe', TRUE, TRUE),
                        ('en', 'English', TRUE, FALSE),
                        ('de', 'Deutsch', TRUE, FALSE)
                ''')
                print("✓ Diller eklendi")
                
                # Veri tiplerini ekle (sadece dtype ile)
                cursor.execute('''
                    INSERT OR IGNORE INTO data_types (dtype, name, unit, description)
                    VALUES 
                        (10, 'Gerilim', 'V', 'Batarya gerilim değeri'),
                        (11, 'Şarj Durumu', '%', 'Batarya şarj yüzdesi'),
                        (12, 'Sıcaklık', '°C', 'Batarya sıcaklık değeri'),
                        (13, 'Nem', '%', 'Ortam nem değeri'),
                        (14, 'Akım', 'A', 'Akım değeri'),
                        (126, 'Sağlık Durumu', '%', 'Batarya sağlık yüzdesi')
                ''')
                print("✓ Veri tipleri eklendi")
                
                # Türkçe çevirileri ekle
                cursor.execute('''
                    INSERT OR IGNORE INTO data_type_translations (dtype, language_code, name, description)
                    VALUES 
                        (10, 'tr', 'Gerilim', 'Batarya gerilim değeri'),
                        (11, 'tr', 'Şarj Durumu', 'Batarya şarj yüzdesi'),
                        (12, 'tr', 'Sıcaklık', 'Batarya sıcaklık değeri'),
                        (13, 'tr', 'Nem', 'Ortam nem değeri'),
                        (14, 'tr', 'Akım', 'Akım değeri'),
                        (126, 'tr', 'Sağlık Durumu', 'Batarya sağlık yüzdesi')
                ''')
                print("✓ Türkçe çeviriler eklendi")
                
                # İngilizce çevirileri ekle
                cursor.execute('''
                    INSERT OR IGNORE INTO data_type_translations (dtype, language_code, name, description)
                    VALUES 
                        (10, 'en', 'Voltage', 'Battery voltage value'),
                        (11, 'en', 'Charge Status', '%', 'Battery charge percentage'),
                        (12, 'en', 'Temperature', '°C', 'Battery temperature value'),
                        (13, 'en', 'Humidity', '%', 'Ambient humidity value'),
                        (14, 'en', 'Current', 'A', 'Current value'),
                        (126, 'en', 'Health Status', '%', 'Battery health percentage')
                ''')
                print("✓ İngilizce çeviriler eklendi")
                
                # Almanca çevirileri ekle
                cursor.execute('''
                    INSERT OR IGNORE INTO data_type_translations (dtype, language_code, name, description)
                    VALUES 
                        (10, 'de', 'Datentyp 10', 'Allgemeiner Datentyp 10'),
                        (11, 'de', 'Datentyp 11', 'Allgemeiner Datentyp 11'),
                        (12, 'de', 'Datentyp 12', 'Allgemeiner Datentyp 12'),
                        (13, 'de', 'Datentyp 13', 'Allgemeiner Datentyp 13'),
                        (14, 'de', 'Datentyp 14', 'Allgemeiner Datentyp 14'),
                        (126, 'de', 'Datentyp 126', 'Allgemeiner Datentyp 126')
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
    
    # get_connection metodu yukarıda connection pool ile tanımlandı
    
    def execute_query(self, query, params=None):
        """Özel SQL sorgusu çalıştır"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                if params:
                    cursor.execute(query, params)
                else:
                    cursor.execute(query)
                conn.commit()
                return cursor
        except Exception as e:
            print(f"execute_query hatası: {e}")
            raise e
    
    def insert_battery_data(self, arm, k, dtype, data, timestamp):
        """Veri ekle (arm ve battery için tek tablo)"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO battery_data (arm, k, dtype, data, timestamp)
                VALUES (?, ?, ?, ?, ?)
            ''', (arm, k, dtype, data, timestamp))
            conn.commit()
    
    def insert_battery_data_batch(self, batch):
        """Batch olarak veri ekle - optimize edilmiş"""
        if not batch:
            return
            
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Transaction başlat
            cursor.execute("BEGIN IMMEDIATE")
            
            try:
                # Batch insert
                cursor.executemany('''
                    INSERT INTO battery_data (arm, k, dtype, data, timestamp)
                    VALUES (?, ?, ?, ?, ?)
                ''', [(record['Arm'], record['k'], record['Dtype'], record['data'], record['timestamp']) for record in batch])
                
                # Commit
                conn.commit()
                print(f"✅ {len(batch)} veri batch olarak eklendi")
                
            except Exception as e:
                # Rollback on error
                conn.rollback()
                print(f"❌ Batch insert hatası: {e}")
                raise
    
    def insert_alarm(self, arm, battery, error_code_msb, error_code_lsb, timestamp):
        """Alarm verisi ekle"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO alarms (arm, battery, error_code_msb, error_code_lsb, timestamp)
                VALUES (?, ?, ?, ?, ?)
            ''', (arm, battery, error_code_msb, error_code_lsb, timestamp))
            conn.commit()
    
    def resolve_alarm(self, arm, battery):
        """Belirli bir batarya için aktif alarmı düzelt"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE alarms 
                SET status = 'resolved', resolved_at = CURRENT_TIMESTAMP
                WHERE arm = ? AND battery = ? AND status = 'active'
            ''', (arm, battery))
            conn.commit()
            return cursor.rowcount > 0

    def get_all_alarms(self, show_resolved=True):
        """Tüm alarmları getir"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                if show_resolved:
                    # Tüm alarmları getir (aktif + düzelen)
                    cursor.execute('''
                        SELECT id, arm, battery, error_code_msb, error_code_lsb, timestamp, status, resolved_at, created_at
                        FROM alarms 
                        ORDER BY timestamp DESC
                    ''')
                else:
                    # Sadece aktif alarmları getir
                    cursor.execute('''
                        SELECT id, arm, battery, error_code_msb, error_code_lsb, timestamp, status, resolved_at, created_at
                        FROM alarms 
                        WHERE status = 'active'
                        ORDER BY timestamp DESC
                    ''')
                
                rows = cursor.fetchall()
                return rows
        except Exception as e:
            print(f"get_all_alarms hatası: {e}")
            return []

    def get_paginated_alarms(self, show_resolved=True, page=1, page_size=50):
        """Sayfalanmış alarmları getir"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Toplam alarm sayısını hesapla
                if show_resolved:
                    count_query = 'SELECT COUNT(*) FROM alarms'
                    cursor.execute(count_query)
                else:
                    count_query = 'SELECT COUNT(*) FROM alarms WHERE status = "active"'
                    cursor.execute(count_query)
                
                total_count = cursor.fetchone()[0]
                
                # Sayfalama hesapla
                offset = (page - 1) * page_size
                total_pages = (total_count + page_size - 1) // page_size
                
                # Sayfalanmış verileri getir
                if show_resolved:
                    cursor.execute('''
                        SELECT id, arm, battery, error_code_msb, error_code_lsb, timestamp, status, resolved_at, created_at
                        FROM alarms 
                        ORDER BY timestamp DESC
                        LIMIT ? OFFSET ?
                    ''', (page_size, offset))
                else:
                    cursor.execute('''
                        SELECT id, arm, battery, error_code_msb, error_code_lsb, timestamp, status, resolved_at, created_at
                        FROM alarms 
                        WHERE status = 'active'
                        ORDER BY timestamp DESC
                        LIMIT ? OFFSET ?
                    ''', (page_size, offset))
                
                rows = cursor.fetchall()
                
                return {
                    'alarms': rows,
                    'totalCount': total_count,
                    'totalPages': total_pages,
                    'currentPage': page
                }
        except Exception as e:
            print(f"get_paginated_alarms hatası: {e}")
            return {
                'alarms': [],
                'totalCount': 0,
                'totalPages': 1,
                'currentPage': 1
            }
    
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

    def update_or_insert_passive_balance(self, arm, slave, status, timestamp):
        """Passive balance verisini güncelle veya ekle"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Mevcut kaydı kontrol et
            cursor.execute('''
                SELECT id FROM passive_balance 
                WHERE arm = ? AND slave = ?
                ORDER BY timestamp DESC LIMIT 1
            ''', (arm, slave))
            
            existing_record = cursor.fetchone()
            
            if existing_record:
                # Güncelle
                cursor.execute('''
                    UPDATE passive_balance 
                    SET status = ?, timestamp = ?, created_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                ''', (status, timestamp, existing_record[0]))
                print(f"✓ Passive balance güncellendi: Kol {arm}, Batarya {slave}, Status: {status}")
            else:
                # Yeni kayıt ekle
                cursor.execute('''
                    INSERT INTO passive_balance (arm, slave, status, timestamp)
                    VALUES (?, ?, ?, ?)
                ''', (arm, slave, status, timestamp))
                print(f"✓ Passive balance eklendi: Kol {arm}, Batarya {slave}, Status: {status}")
            
            conn.commit()
    
    def insert_arm_slave_counts(self, arm, slave_count):
        """Arm slave count verisi ekle/güncelle (UPSERT)"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Önce mevcut kaydı kontrol et
            cursor.execute('''
                SELECT id FROM arm_slave_counts 
                WHERE arm = ? 
                ORDER BY created_at DESC 
                LIMIT 1
            ''', (arm,))
            
            existing_record = cursor.fetchone()
            
            if existing_record:
                # Mevcut kaydı güncelle
                cursor.execute('''
                    UPDATE arm_slave_counts 
                    SET slave_count = ?, created_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                ''', (slave_count, existing_record[0]))
                print(f"🔄 Arm {arm} slave_count güncellendi: {slave_count}")
            else:
                # Yeni kayıt ekle
                cursor.execute('''
                    INSERT INTO arm_slave_counts (arm, slave_count)
                    VALUES (?, ?)
                ''', (arm, slave_count))
                print(f"➕ Arm {arm} slave_count eklendi: {slave_count}")
            
            conn.commit()
    
    def check_default_arm_slave_counts(self):
        """Mevcut veritabanında default arm_slave_counts değerlerini kontrol et"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Her kol için kayıt var mı kontrol et
                for arm in [1, 2, 3, 4]:
                    cursor.execute('''
                        SELECT COUNT(*) FROM arm_slave_counts WHERE arm = ?
                    ''', (arm,))
                    
                    count = cursor.fetchone()[0]
                    
                    if count == 0:
                        # Bu kol için kayıt yok, default değer ekle
                        if arm == 3:
                            slave_count = 7  # Kol 3'te 7 batarya
                        else:
                            slave_count = 0  # Diğer kollarda 0 batarya
                        
                        cursor.execute('''
                            INSERT INTO arm_slave_counts (arm, slave_count) 
                            VALUES (?, ?)
                        ''', (arm, slave_count))
                        
                        print(f"✓ Kol {arm} için default değer eklendi: {slave_count} batarya")
                
                conn.commit()
                print("✅ Default arm_slave_counts değerleri kontrol edildi")
                
        except Exception as e:
            print(f"❌ Default arm_slave_counts kontrolü hatası: {e}")
    
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
                LEFT JOIN data_types dt ON bd.dtype = dt.dtype
                LEFT JOIN data_type_translations dtt ON dt.dtype = dtt.dtype 
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
                    COALESCE(dtt.name, dt.name) as name,
                    dt.unit,
                    COALESCE(dtt.description, dt.description) as description
                FROM data_types dt
                LEFT JOIN data_type_translations dtt ON dt.dtype = dtt.dtype 
                    AND dtt.language_code = ?
                ORDER BY dt.dtype
            ''', (language,))
            
            rows = cursor.fetchall()
            return [{
                'dtype': row[0],
                'name': row[1],
                'unit': row[2],
                'description': row[3]
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
                LEFT JOIN data_types dt ON bd.dtype = dt.dtype
                LEFT JOIN data_type_translations dtt ON dt.dtype = dtt.dtype 
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
    
    def get_logs_with_filters(self, page=1, page_size=50, filters=None, language='tr'):
        """Filtrelenmiş log verilerini getir"""
        if filters is None:
            filters = {}
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Temel sorgu - JOIN'de k koşulunu kaldırdık ve çeviri ekle
            query = '''
                SELECT 
                    bd.arm,
                    bd.k as batteryAddress,
                    bd.dtype,
                    bd.data,
                    bd.timestamp,
                    COALESCE(dtt.name, dt.name) as name,
                    dt.unit
                FROM battery_data bd
                LEFT JOIN data_types dt ON bd.dtype = dt.dtype
                LEFT JOIN data_type_translations dtt ON dt.dtype = dtt.dtype AND dtt.language_code = ?
                WHERE 1=1
            '''
            
            params = [language]  # Dil parametresi ilk sırada
            
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
                logs.append({
                    'arm': row[0],
                    'batteryAddress': row[1],
                    'dtype': row[2],
                    'data': row[3],
                    'timestamp': row[4],
                    'name': row[5],
                    'unit': row[6],
                    'status': 'success'  # Tüm veriler başarılı
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
            
            # Basit SQL ile gruplandırılmış verileri getir
            query = '''
                SELECT 
                    timestamp,
                    arm,
                    k as batteryAddress,
                    MAX(CASE WHEN dtype = 10 THEN data END) as voltage,
                    MAX(CASE WHEN dtype = 11 THEN data END) as charge_status,
                    MAX(CASE WHEN dtype = 12 THEN data END) as temperature,
                    MAX(CASE WHEN dtype = 13 THEN data END) as positive_pole_temp,
                    MAX(CASE WHEN dtype = 14 THEN data END) as negative_pole_temp,
                    MAX(CASE WHEN dtype = 126 THEN data END) as health_status
                FROM battery_data 
                WHERE k > 2
            '''
            
            params = []
            
            # Filtreler
            if filters.get('arm'):
                query += ' AND arm = ?'
                params.append(filters['arm'])
            
            if filters.get('battery'):
                query += ' AND k = ?'
                params.append(filters['battery'])
            
            if filters.get('start_date'):
                start_timestamp = int(datetime.strptime(filters['start_date'], '%Y-%m-%d').timestamp() * 1000)
                query += ' AND timestamp >= ?'
                params.append(start_timestamp)
            
            if filters.get('end_date'):
                end_timestamp = int(datetime.strptime(filters['end_date'], '%Y-%m-%d').timestamp() * 1000) + (24 * 60 * 60 * 1000) - 1
                query += ' AND timestamp <= ?'
                params.append(end_timestamp)
            
            query += ' GROUP BY timestamp, arm, k ORDER BY timestamp DESC, k ASC'
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            
            # CSV formatı - Gruplandırılmış veriler için
            csv_content = "ZAMAN,KOL,BATARYA ADRESİ,GERİLİM,ŞARJ DURUMU,MODÜL SICAKLIĞI,POZİTİF KUTUP SICAKLIĞI,NEGATİF KUTUP SICAKLIĞI,SAĞLIK DURUMU\n"
            
            for row in rows:
                timestamp = datetime.fromtimestamp(row[0] / 1000).strftime('%Y-%m-%d %H:%M:%S')
                battery_address = row[2] - 2  # k - 2 olarak göster
                
                csv_content += f"{timestamp},{row[1]},{battery_address},{row[3] or '-'},{row[4] or '-'},{row[5] or '-'},{row[6] or '-'},{row[7] or '-'},{row[8] or '-'}\n"
            
            return csv_content
    
    def export_arm_logs_to_csv(self, filters=None):
        """Kol log verilerini CSV formatında export et"""
        if filters is None:
            filters = {}
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Basit SQL ile sadece gerekli verileri getir
            query = '''
                SELECT 
                    timestamp,
                    arm,
                    MAX(CASE WHEN dtype = 10 THEN data END) as current,
                    MAX(CASE WHEN dtype = 11 THEN data END) as humidity,
                    MAX(CASE WHEN dtype = 12 THEN data END) as ambient_temperature
                FROM battery_data 
                WHERE k = 2
            '''
            
            params = []
            
            # Filtreler
            if filters.get('arm'):
                query += ' AND arm = ?'
                params.append(filters['arm'])
            
            if filters.get('start_date'):
                start_timestamp = int(datetime.strptime(filters['start_date'], '%Y-%m-%d').timestamp() * 1000)
                query += ' AND timestamp >= ?'
                params.append(start_timestamp)
            
            if filters.get('end_date'):
                end_timestamp = int(datetime.strptime(filters['end_date'], '%Y-%m-%d').timestamp() * 1000) + (24 * 60 * 60 * 1000) - 1
                query += ' AND timestamp <= ?'
                params.append(end_timestamp)
            
            query += ' GROUP BY timestamp, arm, k ORDER BY timestamp DESC, arm ASC'
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            
            # CSV formatı - Sadece gerekli alanlar
            csv_content = "KOL,ZAMAN,AKIM,NEM,SICAKLIK\n"
            
            for row in rows:
                timestamp = datetime.fromtimestamp(row[0] / 1000).strftime('%Y-%m-%d %H:%M:%S')
                
                csv_content += f"{row[1]},{timestamp},{row[2] or '-'},{row[3] or '-'},{row[4] or '-'}\n"
            
            return csv_content

    def get_batteries_for_display(self, page=1, page_size=30, selected_arm=0, language='tr'):
        """Batteries sayfası için batarya verilerini getir"""
        
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Arm filtresi ekle (her zaman bir kol seçilmeli)
                arm_filter = f"AND bd.arm = {selected_arm}"
                
                # arm_slave_counts tablosundan seçili kolun batarya sayısını al
                cursor.execute('''
                    SELECT slave_count FROM arm_slave_counts 
                    WHERE arm = ?
                ''', (selected_arm,))
                
                slave_count_result = cursor.fetchone()
                if not slave_count_result:
                    print(f"Kol {selected_arm} için slave_count bulunamadı!")
                    return {
                        'batteries': [],
                        'totalPages': 1,
                        'currentPage': 1
                    }
                
                slave_count = slave_count_result[0]
                print(f"Kol {selected_arm} için slave_count: {slave_count}")
                
                # Sadece mevcut batarya sayısı kadar batarya getir
                # k değerleri 3'ten başlar (arm verisi k=2), slave_count kadar olmalı
                # Örnek: slave_count=7 ise k=3,4,5,6,7,8,9 (7 adet)
                cursor.execute(f'''
                    SELECT 
                        bd.arm,
                        bd.k as batteryAddress,
                        MAX(bd.timestamp) as latest_timestamp
                    FROM battery_data bd
                    WHERE bd.k != 2 AND bd.k >= 3 AND bd.k < (3 + ?) {arm_filter}
                    GROUP BY bd.arm, bd.k
                    ORDER BY bd.arm, bd.k
                ''', (slave_count,))
                
                all_batteries = cursor.fetchall()
                print(f"Bulunan batarya sayısı: {len(all_batteries)}")
                print(f"Batarya listesi: {all_batteries}")
                
                if not all_batteries:
                    print("Hiç batarya bulunamadı!")
                    return {
                        'batteries': [],
                        'totalPages': 1,
                        'currentPage': 1
                    }
                
                # Sayfalama
                start_idx = (page - 1) * page_size
                end_idx = start_idx + page_size
                page_batteries = all_batteries[start_idx:end_idx]
                
                batteries = []
                
                for arm, battery_address, latest_timestamp in page_batteries:
                    # Her batarya için sadece en son verileri getir
                    battery_data = self.get_latest_battery_data(arm, battery_address, language)
                    
                    if battery_data:
                        batteries.append(battery_data)
                
                return {
                    'batteries': batteries,
                    'totalPages': (len(all_batteries) + page_size - 1) // page_size,
                    'currentPage': 1
                }
        except Exception as e:
            print(f"get_batteries_for_display hatası: {e}")
            raise e
    
    def get_latest_battery_data(self, arm, battery_address, language='tr'):
        """Belirli bir batarya için son verileri getir"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # En son veri zamanını bul
                cursor.execute('''
                    SELECT MAX(timestamp) FROM battery_data 
                    WHERE arm = ? AND k = ?
                ''', (arm, battery_address))
                
                latest_timestamp = cursor.fetchone()[0]
                
                if not latest_timestamp:
                    return None
                
                # Debug: Dil parametresini yazdır
                print(f"DEBUG: Dil parametresi: {language}")
                
                # Sadece en son verileri getir (en son timestamp'teki tüm dtype'lar)
                cursor.execute('''
                    SELECT bd.dtype, bd.data, dt.name, dt.unit,
                           COALESCE(dtt.name, dt.name) as translated_name
                    FROM battery_data bd
                    LEFT JOIN data_types dt ON bd.dtype = dt.dtype
                    LEFT JOIN data_type_translations dtt ON dt.dtype = dtt.dtype 
                        AND dtt.language_code = ?
                    WHERE bd.arm = ? AND bd.k = ? AND bd.timestamp = ?
                    ORDER BY bd.dtype
                ''', (language, arm, battery_address, latest_timestamp))
                
                data_rows = cursor.fetchall()
                
                # Debug: Veri satırlarını yazdır
                print(f"DEBUG: Veri satırları: {data_rows}")
                
                # Veri tiplerine göre organize et
                battery_data = {
                    'arm': arm,
                    'batteryAddress': battery_address,
                    'timestamp': latest_timestamp,
                    'voltage': None,
                    'temperature': None,
                    'health': None,
                    'charge': None,
                    'isActive': True
                }
                
                # Sadece en son verileri kullan
                for dtype, data, name, unit, translated_name in data_rows:
                    print(f"DEBUG: dtype={dtype}, name={name}, translated_name={translated_name}")
                    if dtype == 10:  # Gerilim
                        battery_data['voltage'] = data
                        battery_data['voltage_name'] = translated_name or name
                    elif dtype == 11:  # Şarj durumu
                        battery_data['charge'] = data
                        battery_data['charge_name'] = translated_name or name
                    elif dtype == 12:  # Sıcaklık
                        battery_data['temperature'] = data
                        battery_data['temperature_name'] = translated_name or name
                    elif dtype == 126:  # Sağlık durumu
                        battery_data['health'] = data
                        battery_data['health_name'] = translated_name or name
                
                return battery_data
        except Exception as e:
            print(f"get_latest_battery_data hatası (arm: {arm}, battery: {battery_address}): {e}")
            return None
    
    def export_batteries_to_csv(self):
        """Batarya verilerini CSV formatında export et"""
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Her batarya için en son veri zamanını bul
            base_query = '''
                SELECT 
                    bd.arm,
                    bd.k as batteryAddress,
                    MAX(bd.timestamp) as latest_timestamp
                FROM battery_data bd
                WHERE bd.k != 2
                GROUP BY bd.arm, bd.k 
                ORDER BY bd.arm, bd.k
            '''
            
            cursor.execute(base_query)
            battery_groups = cursor.fetchall()
            
            # CSV formatı
            csv_content = "KOL,BATARYA ADRESİ,SON GÜNCELLEME,GERİLİM (V),SICAKLIK (°C),SAĞLIK DURUMU (%),ŞARJ DURUMU (%)\n"
            
            for group in battery_groups:
                arm, battery_address, latest_timestamp = group
                
                # Her batarya için sadece en son verileri getir
                battery_data = self.get_latest_battery_data(arm, battery_address)
                
                if battery_data:
                    timestamp = datetime.fromtimestamp(latest_timestamp / 1000).strftime('%Y-%m-%d %H:%M:%S')
                    
                    csv_content += f"{arm},{battery_address},{timestamp},"
                    csv_content += f"{battery_data['voltage'] or '--'},"
                    csv_content += f"{battery_data['temperature'] or '--'},"
                    csv_content += f"{battery_data['charge'] or '--'},"
                    csv_content += f"{battery_data['health'] or '--'}\n"
            
            return csv_content
    
    def get_database_size(self):
        """Veritabanı boyutunu MB cinsinden döndür"""
        if os.path.exists(self.db_path):
            size_mb = os.path.getsize(self.db_path) / (1024 * 1024)
            return size_mb
        return 0
    
    def get_summary_data(self):
        """Özet sayfası için veri getir - son 10 dakikada verisi gelen kollar"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Son 10 dakikada verisi gelen kolları bul
                ten_minutes_ago = int((datetime.now() - timedelta(minutes=10)).timestamp() * 1000)
                
                # Sadece armslavecount tablosunda veri olan kolları getir
                cursor.execute('''
                    SELECT bd.arm, MAX(bd.timestamp) as latest_timestamp
                    FROM battery_data bd
                    INNER JOIN arm_slave_counts asc ON bd.arm = asc.arm
                    WHERE bd.timestamp >= ? AND asc.slave_count > 0
                    GROUP BY bd.arm
                    ORDER BY bd.arm
                ''', (ten_minutes_ago,))
                
                active_arms = cursor.fetchall()
                summary_data = []
                
                for arm, latest_timestamp in active_arms:
                    if not latest_timestamp:
                        continue
                    
                    # Bu kol için nem ve sıcaklık bilgisini al (k=2)
                    cursor.execute('''
                        SELECT bd.dtype, bd.data, dt.name, dt.unit
                        FROM battery_data bd
                        LEFT JOIN data_types dt ON bd.dtype = dt.dtype
                        WHERE bd.arm = ? AND bd.k = 2 AND bd.timestamp = ?
                        ORDER BY bd.dtype
                    ''', (arm, latest_timestamp))
                    
                    arm_data = cursor.fetchall()
                    
                    print(f"Kol {arm} için k=2 verileri: {arm_data}")
                    
                    # Nem ve sıcaklık değerlerini al
                    humidity = None
                    temperature = None
                    
                    for dtype, data, name, unit in arm_data:
                        print(f"  dtype={dtype}, data={data}, name={name}, unit={unit}")
                        if dtype == 13:  # Nem
                            humidity = data
                            print(f"    Nem bulundu: {humidity}")
                        elif dtype == 12:  # Sıcaklık
                            temperature = data
                            print(f"    Sıcaklık bulundu: {temperature}")
                    
                    # Bu kol için armslavecounts tablosundan batarya sayısını al
                    cursor.execute('''
                        SELECT slave_count FROM arm_slave_counts 
                        WHERE arm = ?
                        ORDER BY created_at DESC 
                        LIMIT 1
                    ''', (arm,))
                    
                    slave_count_result = cursor.fetchone()
                    battery_count = slave_count_result[0] if slave_count_result else 0
                    
                    # Ortalama değerleri hesapla
                    cursor.execute('''
                        SELECT 
                            AVG(CASE WHEN bd.dtype = 10 THEN bd.data END) as avg_voltage,
                            AVG(CASE WHEN bd.dtype = 11 THEN bd.data END) as avg_charge,
                            AVG(CASE WHEN bd.dtype = 126 THEN bd.data END) as avg_health
                        FROM battery_data bd
                        WHERE bd.arm = ? AND bd.k != 2 AND bd.timestamp = ?
                    ''', (arm, latest_timestamp))
                    
                    battery_stats = cursor.fetchone()
                    
                    if battery_stats:
                        avg_voltage, avg_charge, avg_health = battery_stats
                        
                        summary_data.append({
                            'arm': arm,
                            'timestamp': latest_timestamp,
                            'humidity': humidity,
                            'temperature': temperature,
                            'battery_count': battery_count or 0,
                            'avg_voltage': round(avg_voltage, 3) if avg_voltage else None,
                            'avg_charge': round(avg_charge, 3) if avg_charge else None,
                            'avg_health': round(avg_health, 3) if avg_health else None
                        })
                
                return summary_data
                
        except Exception as e:
            print(f"get_summary_data hatası: {e}")
            return []
    
    def get_mail_recipients(self):
        """Aktif mail alıcılarını getir"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT id, name, email, is_active, created_at
                    FROM mail_recipients 
                    WHERE is_active = 1
                    ORDER BY created_at
                ''')
                
                rows = cursor.fetchall()
                recipients = []
                
                for row in rows:
                    recipients.append({
                        'id': row[0],
                        'name': row[1],
                        'email': row[2],
                        'is_active': bool(row[3]),
                        'created_at': row[4]
                    })
                
                return recipients
        except Exception as e:
            print(f"Mail alıcıları getirilirken hata: {e}")
            return []
    
    def add_mail_recipient(self, name, email):
        """Yeni mail alıcısı ekle"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Maksimum 8 alıcı kontrolü
                cursor.execute('SELECT COUNT(*) FROM mail_recipients WHERE is_active = 1')
                count = cursor.fetchone()[0]
                
                if count >= 8:
                    return {'success': False, 'message': 'Maksimum 8 mail alıcısı eklenebilir'}
                
                # Email benzersizlik kontrolü
                cursor.execute('SELECT id FROM mail_recipients WHERE email = ?', (email,))
                if cursor.fetchone():
                    return {'success': False, 'message': 'Bu email adresi zaten kayıtlı'}
                
                cursor.execute('''
                    INSERT INTO mail_recipients (name, email)
                    VALUES (?, ?)
                ''', (name, email))
                
                conn.commit()
                return {'success': True, 'message': 'Mail alıcısı başarıyla eklendi'}
        except Exception as e:
            print(f"Mail alıcısı eklenirken hata: {e}")
            return {'success': False, 'message': str(e)}
    
    def update_mail_recipient(self, recipient_id, name, email):
        """Mail alıcısını güncelle"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Email benzersizlik kontrolü (kendi ID'si hariç)
                cursor.execute('SELECT id FROM mail_recipients WHERE email = ? AND id != ?', (email, recipient_id))
                if cursor.fetchone():
                    return {'success': False, 'message': 'Bu email adresi zaten başka bir alıcı tarafından kullanılıyor'}
                
                cursor.execute('''
                    UPDATE mail_recipients 
                    SET name = ?, email = ?
                    WHERE id = ?
                ''', (name, email, recipient_id))
                
                conn.commit()
                return {'success': True, 'message': 'Mail alıcısı başarıyla güncellendi'}
        except Exception as e:
            print(f"Mail alıcısı güncellenirken hata: {e}")
            return {'success': False, 'message': str(e)}
    
    def delete_mail_recipient(self, recipient_id):
        """Mail alıcısını sil (soft delete)"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE mail_recipients 
                    SET is_active = 0
                    WHERE id = ?
                ''', (recipient_id,))
                
                conn.commit()
                return {'success': True, 'message': 'Mail alıcısı başarıyla silindi'}
        except Exception as e:
            print(f"Mail alıcısı silinirken hata: {e}")
            return {'success': False, 'message': str(e)}
    
    def batch_insert_alarms(self, alarms):
        """Alarmları toplu olarak kaydet"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Alarm verilerini hazırla
                alarm_data = []
                for alarm in alarms:
                    alarm_data.append((
                        alarm['arm'],
                        alarm['battery'],
                        alarm['error_code_msb'],
                        alarm['error_code_lsb'],
                        alarm['timestamp']
                    ))
                
                # Toplu insert
                cursor.executemany('''
                    INSERT INTO alarms (arm, battery, error_code_msb, error_code_lsb, timestamp)
                    VALUES (?, ?, ?, ?, ?)
                ''', alarm_data)
                
                conn.commit()
                print(f"✅ {len(alarms)} alarm toplu olarak kaydedildi")
                return True
                
        except Exception as e:
            print(f"❌ Alarm toplu kayıt hatası: {e}")
            return False
    
    def batch_resolve_alarms(self, alarm_ids):
        """Alarmları toplu olarak düzelt"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                
                # Toplu update
                cursor.executemany('''
                    UPDATE alarms 
                    SET status = 'resolved', resolved_at = ?
                    WHERE id = ? AND status = 'active'
                ''', [(current_time, alarm_id) for alarm_id in alarm_ids])
                
                conn.commit()
                print(f"✅ {len(alarm_ids)} alarm toplu olarak düzeltildi")
                return True
                
        except Exception as e:
            print(f"❌ Alarm toplu düzeltme hatası: {e}")
            return False

    def get_batconfigs(self):
        """Tüm batarya konfigürasyonlarını getir"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT armValue, Vmin, Vmax, Vnom, Rintnom, Tempmin_D, Tempmax_D, 
                           Tempmin_PN, Tempmax_PN, Socmin, Sohmin, time, created_at
                    FROM batconfigs 
                    ORDER BY armValue
                ''')
                
                rows = cursor.fetchall()
                configs = []
                
                for row in rows:
                    config = {
                        'armValue': row[0],
                        'Vmin': row[1],
                        'Vmax': row[2],
                        'Vnom': row[3],
                        'Rintnom': row[4],
                        'Tempmin_D': row[5],
                        'Tempmax_D': row[6],
                        'Tempmin_PN': row[7],
                        'Tempmax_PN': row[8],
                        'Socmin': row[9],
                        'Sohmin': row[10],
                        'time': row[11],
                        'created_at': row[12]
                    }
                    configs.append(config)
                
                return configs
        except Exception as e:
            print(f"get_batconfigs hatası: {e}")
            return []
    
    def get_armconfigs(self):
        """Tüm kol konfigürasyonlarını getir"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT armValue, akimKats, akimMax, nemMax, nemMin, tempMax, tempMin, time, created_at
                    FROM armconfigs 
                    ORDER BY armValue
                ''')
                
                rows = cursor.fetchall()
                configs = []
                
                for row in rows:
                    config = {
                        'armValue': row[0],
                        'akimKats': row[1],
                        'akimMax': row[2],
                        'nemMax': row[3],
                        'nemMin': row[4],
                        'tempMax': row[5],
                        'tempMin': row[6],
                        'time': row[7],
                        'created_at': row[8]
                    }
                    configs.append(config)
                
                return configs
        except Exception as e:
            print(f"get_armconfigs hatası: {e}")
            return []
    
    def get_grouped_battery_logs(self, page=1, page_size=50, filters=None, language='tr'):
        """Gruplandırılmış batarya log verilerini getir"""
        print(f"DEBUG database.py: get_grouped_battery_logs çağrıldı - page={page}, page_size={page_size}, filters={filters}, language={language}")
        if filters is None:
            filters = {}
        
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Basit SQL ile tüm verileri getir
                query = '''
                    SELECT 
                        timestamp,
                        arm,
                        k as batteryAddress,
                        MAX(CASE WHEN dtype = 10 THEN data END) as voltage,
                        MAX(CASE WHEN dtype = 11 THEN data END) as charge_status,
                        MAX(CASE WHEN dtype = 12 THEN data END) as temperature,
                        MAX(CASE WHEN dtype = 13 THEN data END) as positive_pole_temp,
                        MAX(CASE WHEN dtype = 14 THEN data END) as negative_pole_temp,
                        MAX(CASE WHEN dtype = 126 THEN data END) as health_status
                    FROM battery_data 
                    WHERE k > 2
                '''
                
                params = []
                
                if filters.get('arm'):
                    query += ' AND arm = ?'
                    params.append(filters['arm'])
                
                if filters.get('battery'):
                    query += ' AND k = ?'
                    params.append(filters['battery'])
                
                if filters.get('startDate'):
                    start_timestamp = int(datetime.strptime(filters['startDate'], '%Y-%m-%d').timestamp() * 1000)
                    query += ' AND timestamp >= ?'
                    params.append(start_timestamp)
                
                if filters.get('endDate'):
                    end_timestamp = int(datetime.strptime(filters['endDate'], '%Y-%m-%d').timestamp() * 1000) + (24 * 60 * 60 * 1000) - 1
                    query += ' AND timestamp <= ?'
                    params.append(end_timestamp)
                
                query += ' GROUP BY timestamp, arm, k ORDER BY timestamp DESC, k ASC LIMIT ? OFFSET ?'
                params.extend([page_size, (page - 1) * page_size])
                
                print(f"DEBUG database.py: Query: {query}")
                print(f"DEBUG database.py: Params: {params}")
                
                cursor.execute(query, params)
                rows = cursor.fetchall()
                
                # Verileri formatla
                logs = []
                for row in rows:
                    logs.append({
                        'timestamp': row[0],
                        'arm': row[1],
                        'batteryAddress': row[2] - 2,  # k - 2 olarak göster
                        'voltage': row[3],
                        'charge_status': row[4],
                        'temperature': row[5],
                        'positive_pole_temp': row[6],
                        'negative_pole_temp': row[7],
                        'health_status': row[8]
                    })
                
                # Toplam sayfa sayısını hesapla
                count_query = '''
                    SELECT COUNT(*)
                    FROM (
                        SELECT DISTINCT timestamp, arm, k
                        FROM battery_data
                        WHERE k > 2
                    ) AS subquery
                '''
                
                cursor.execute(count_query)
                total_count = cursor.fetchone()[0]
                
                total_pages = (total_count + page_size - 1) // page_size
                
                print(f"DEBUG database.py: {len(logs)} log verisi döndürüldü, toplam: {total_count}, sayfa: {total_pages}")
                
                return {
                    'logs': logs,
                    'totalCount': total_count,
                    'totalPages': total_pages,
                    'currentPage': page
                }
        except Exception as e:
            print(f"DEBUG database.py: Hata oluştu: {e}")
            import traceback
            traceback.print_exc()
            raise e
    
    def get_grouped_arm_logs(self, page=1, page_size=50, filters=None, language='tr'):
        """Gruplandırılmış kol log verilerini getir"""
        print(f"DEBUG database.py: get_grouped_arm_logs çağrıldı - page={page}, page_size={page_size}, filters={filters}, language={language}")
        if filters is None:
            filters = {}
        
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Basit SQL ile tüm verileri getir
                query = '''
                    SELECT 
                        timestamp,
                        arm,
                        MAX(CASE WHEN dtype = 10 THEN data END) as current,
                        MAX(CASE WHEN dtype = 11 THEN data END) as humidity,
                        MAX(CASE WHEN dtype = 12 THEN data END) as ambient_temperature
                    FROM battery_data 
                    WHERE k = 2
                '''
                
                params = []
                
                if filters.get('arm'):
                    query += ' AND arm = ?'
                    params.append(filters['arm'])
                
                if filters.get('startDate'):
                    start_timestamp = int(datetime.strptime(filters['startDate'], '%Y-%m-%d').timestamp() * 1000)
                    query += ' AND timestamp >= ?'
                    params.append(start_timestamp)
                
                if filters.get('endDate'):
                    end_timestamp = int(datetime.strptime(filters['endDate'], '%Y-%m-%d').timestamp() * 1000) + (24 * 60 * 60 * 1000) - 1
                    query += ' AND timestamp <= ?'
                    params.append(end_timestamp)
                
                query += ' GROUP BY timestamp, arm, k ORDER BY timestamp DESC, arm ASC LIMIT ? OFFSET ?'
                params.extend([page_size, (page - 1) * page_size])
                
                print(f"DEBUG database.py: Arm query: {query}")
                print(f"DEBUG database.py: Arm params: {params}")
                
                cursor.execute(query, params)
                rows = cursor.fetchall()
                
                # Verileri formatla
                logs = []
                for row in rows:
                    logs.append({
                        'timestamp': row[0],
                        'arm': row[1],
                        'current': row[2],
                        'humidity': row[3],
                        'ambient_temperature': row[4]
                    })
                
                # Toplam sayfa sayısını hesapla
                count_query = '''
                    SELECT COUNT(*)
                    FROM (
                        SELECT DISTINCT timestamp, arm, k
                        FROM battery_data
                        WHERE k = 2
                    ) AS subquery
                '''
                
                cursor.execute(count_query)
                total_count = cursor.fetchone()[0]
                
                total_pages = (total_count + page_size - 1) // page_size
                
                print(f"DEBUG database.py: {len(logs)} arm log verisi döndürüldü, toplam: {total_count}, sayfa: {total_pages}")
                
                return {
                    'logs': logs,
                    'totalCount': total_count,
                    'totalPages': total_pages,
                    'currentPage': page
                }
        except Exception as e:
            print(f"DEBUG database.py: Arm logs hatası oluştu: {e}")
            import traceback
            traceback.print_exc()
            raise e

    def get_passive_balance(self, arm=None):
        """Passive balance verilerini getir"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                if arm:
                    # Belirli kol için
                    cursor.execute('''
                        SELECT arm, slave, status, timestamp, created_at
                        FROM passive_balance
                        WHERE arm = ?
                        ORDER BY timestamp DESC
                    ''', (arm,))
                else:
                    # Tüm kollar için
                    cursor.execute('''
                        SELECT arm, slave, status, timestamp, created_at
                        FROM passive_balance
                        ORDER BY arm, slave, timestamp DESC
                    ''')
                
                balance_data = []
                for row in cursor.fetchall():
                    balance_data.append({
                        'arm': row[0],
                        'slave': row[1],
                        'status': row[2],
                        'timestamp': row[3],
                        'created_at': row[4]
                    })
                
                return balance_data
                
        except Exception as e:
            print(f"Passive balance verileri getirilirken hata: {e}")
            return []

    def get_active_arms(self):
        """Tüm kolları getir - arm_slave_counts tablosundan"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Her kol için en son slave_count'u al
                cursor.execute('''
                    SELECT arm, slave_count, created_at
                    FROM arm_slave_counts
                    WHERE id IN (
                        SELECT MAX(id) 
                        FROM arm_slave_counts 
                        GROUP BY arm
                    )
                    ORDER BY arm
                ''')
                
                active_arms = []
                for row in cursor.fetchall():
                    active_arms.append({
                        'arm': row[0],
                        'slave_count': row[1],
                        'created_at': row[2]
                    })
                
                return active_arms
                
        except Exception as e:
            print(f"Aktif kollar getirilirken hata: {e}")
            return []

    def get_active_alarm_count(self):
        """Aktif alarm sayısını getir"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT COUNT(*) FROM alarms 
                WHERE status = 'active'
            ''')
            return cursor.fetchone()[0]
    
    def create_missing_tables(self):
        """Eksik tabloları oluştur (migration)"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # mail_recipients tablosu oluştur
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS mail_recipients (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT NOT NULL,
                        email TEXT NOT NULL UNIQUE,
                        is_active BOOLEAN DEFAULT 1,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                print("✓ mail_recipients tablosu oluşturuldu (migration)")
                
                conn.commit()
                print("✅ Eksik tablolar başarıyla oluşturuldu")
                
        except Exception as e:
            print(f"❌ Eksik tablolar oluşturulurken hata: {e}")
            raise e
    
    def save_battery_config(self, arm, vmin, vmax, vnom, rintnom, tempmin_d, tempmax_d, tempmin_pn, tempmax_pn, socmin, sohmin):
        """Batarya konfigürasyonunu kaydet"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Önce tabloyu oluştur (eğer yoksa)
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS batconfigs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        armValue INTEGER NOT NULL,
                        Vmin REAL NOT NULL,
                        Vmax REAL NOT NULL,
                        Vnom REAL NOT NULL,
                        Rintnom INTEGER NOT NULL,
                        Tempmin_D INTEGER NOT NULL,
                        Tempmax_D INTEGER NOT NULL,
                        Tempmin_PN INTEGER NOT NULL,
                        Tempmax_PN INTEGER NOT NULL,
                        Socmin INTEGER NOT NULL,
                        Sohmin INTEGER NOT NULL,
                        time INTEGER NOT NULL,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                
                # Mevcut konfigürasyonu güncelle veya yeni ekle
                cursor.execute('''
                    INSERT OR REPLACE INTO batconfigs 
                    (armValue, Vmin, Vmax, Vnom, Rintnom, Tempmin_D, Tempmax_D, Tempmin_PN, Tempmax_PN, Socmin, Sohmin, time)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    arm, vmin, vmax, vnom, rintnom, tempmin_d, tempmax_d, 
                    tempmin_pn, tempmax_pn, socmin, sohmin, 
                    int(time.time() * 1000)
                ))
                
                conn.commit()
                print(f"Batarya konfigürasyonu kaydedildi: Kol {arm}")
                
        except Exception as e:
            print(f"Batarya konfigürasyonu kaydedilirken hata: {e}")
            raise e
    
    def save_arm_config(self, arm, akim_kats, akim_max, nem_max, nem_min, temp_max, temp_min):
        """Kol konfigürasyonunu kaydet"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Önce tabloyu oluştur (eğer yoksa)
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS armconfigs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        armValue INTEGER NOT NULL,
                        akimKats INTEGER NOT NULL,
                        akimMax INTEGER NOT NULL,
                        nemMax INTEGER NOT NULL,
                        nemMin INTEGER NOT NULL,
                        tempMax INTEGER NOT NULL,
                        tempMin INTEGER NOT NULL,
                        time INTEGER NOT NULL,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                
                # Mevcut konfigürasyonu güncelle veya yeni ekle
                cursor.execute('''
                    INSERT OR REPLACE INTO armconfigs 
                    (armValue, akimKats, akimMax, nemMax, nemMin, tempMax, tempMin, time)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    arm, akim_kats, akim_max, nem_max, nem_min, 
                    temp_max, temp_min, int(time.time() * 1000)
                ))
                
                conn.commit()
                print(f"Kol konfigürasyonu kaydedildi: Kol {arm}")
                
        except Exception as e:
            print(f"Kol konfigürasyonu kaydedilirken hata: {e}")
            raise e
    
    def insert_batconfig(self, arm, vmin, vmax, vnom, rintnom, tempmin_d, tempmax_d, tempmin_pn, tempmax_pn, socmin, sohmin):
        """Batarya konfigürasyonunu kaydet (main.py ile uyumlu interface)"""
        try:
            self.save_battery_config(arm, vmin, vmax, vnom, rintnom, tempmin_d, tempmax_d, tempmin_pn, tempmax_pn, socmin, sohmin)
        except Exception as e:
            print(f"insert_batconfig hatası: {e}")
            raise e
    
    def insert_armconfig(self, arm, nem_max, nem_min, temp_max, temp_min):
        """Kol konfigürasyonunu kaydet (main.py ile uyumlu interface)"""
        try:
            # Varsayılan değerlerle save_arm_config çağır
            self.save_arm_config(arm, 150, 1000, nem_max, nem_min, temp_max, temp_min)
        except Exception as e:
            print(f"insert_armconfig hatası: {e}")
            raise e