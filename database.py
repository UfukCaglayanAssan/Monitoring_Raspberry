# interface/database.py
import sqlite3
import threading
import os
from datetime import datetime, timedelta
import time
import queue
from contextlib import contextmanager

# Migration'ın sadece bir kez çalışması için modül seviyesi kontrol
_migration_lock = threading.Lock()
_migrated_databases = set()  # Migration'dan geçen veritabanları

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
            # Migration'ın sadece bir kez çalışmasını garanti et
            with _migration_lock:
                # Veritabanının tam yolunu al (normalize et)
                db_abs_path = os.path.abspath(self.db_path)
                
                if db_abs_path not in _migrated_databases:
                    print(f"Veritabanı zaten mevcut: {self.db_path}")
                    # Mevcut veritabanında eksik tabloları kontrol et ve oluştur
                    self.check_and_create_missing_tables()
                    # Mevcut veritabanında default değerleri kontrol et
                    self.check_default_arm_slave_counts()
                    
                    # Default kullanıcıları kontrol et
                    self.check_default_users()
                    
                    # Mevcut düz şifreleri bcrypt formatına dönüştür
                    self.migrate_existing_passwords_to_bcrypt()
                    
                    # Migration tamamlandı, işaretle
                    _migrated_databases.add(db_abs_path)
                else:
                    # Migration zaten yapılmış, sadece bağlan
                    pass  # Sessizce devam et
    
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
                
                # Ana veri tablosu (tüm veriler için)
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
                
                # Mail sunucu konfigürasyon tablosu
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS mail_server_config (
                        id INTEGER PRIMARY KEY DEFAULT 1,
                        smtp_server TEXT,
                        smtp_port INTEGER,
                        smtp_username TEXT,
                        smtp_password TEXT,
                        use_tls BOOLEAN DEFAULT 1,
                        is_active BOOLEAN DEFAULT 0,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        CONSTRAINT single_config CHECK (id = 1)
                    )
                ''')
                print("✓ mail_server_config tablosu oluşturuldu")
                
                # Reset system tarihi tablosu
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS reset_system_log (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        reset_timestamp INTEGER,
                        reason TEXT,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                print("✓ reset_system_log tablosu oluşturuldu")
                
                # IP konfigürasyon tablosu
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS ip_config (
                        id INTEGER PRIMARY KEY DEFAULT 1,
                        ip_address TEXT,
                        subnet_mask TEXT,
                        gateway TEXT,
                        dns_servers TEXT,
                        is_assigned BOOLEAN DEFAULT 0,
                        is_active BOOLEAN DEFAULT 0,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        CONSTRAINT single_ip_config CHECK (id = 1)
                    )
                ''')
                print("✓ ip_config tablosu oluşturuldu")
                
                # Batarya konfigürasyon tablosu
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
                print("✓ batconfigs tablosu oluşturuldu")
                
                # Kol konfigürasyon tablosu
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS armconfigs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        armValue INTEGER NOT NULL,
                        akimKats REAL NOT NULL,
                        akimMax REAL NOT NULL,
                        nemMax REAL NOT NULL,
                        nemMin REAL NOT NULL,
                        tempMax REAL NOT NULL,
                        tempMin REAL NOT NULL,
                        time INTEGER NOT NULL,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                print("✓ armconfigs tablosu oluşturuldu")
                
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
                
                # SFTP konfigürasyon tablosu
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS ftp_config (
                        id INTEGER PRIMARY KEY DEFAULT 1,
                        ftp_host TEXT,
                        ftp_port INTEGER DEFAULT 22,
                        ftp_username TEXT,
                        ftp_password TEXT,
                        is_active BOOLEAN DEFAULT 0,
                        last_sent_at DATETIME,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        CONSTRAINT single_config CHECK (id = 1)
                    )
                ''')
                print("✓ ftp_config tablosu oluşturuldu")
                
                # Trap hedefleri tablosu (trap_settings özellikleri ile birleştirildi)
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS trap_targets (
                        id INTEGER PRIMARY KEY DEFAULT 1,
                        name TEXT NOT NULL DEFAULT 'Trap Target',
                        ip_address TEXT NOT NULL,
                        port INTEGER DEFAULT 162,
                        is_active BOOLEAN DEFAULT 1,
                        trap_enabled BOOLEAN DEFAULT 0,
                        trap_community TEXT DEFAULT 'public',
                        trap_version TEXT DEFAULT '2c',
                        trap_interval INTEGER DEFAULT 30,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        CONSTRAINT single_trap_target CHECK (id = 1)
                    )
                ''')
                print("✓ trap_targets tablosu oluşturuldu")
                
                # Yeni kolonları ekle (migration için)
                try:
                    cursor.execute("ALTER TABLE trap_targets ADD COLUMN trap_enabled BOOLEAN DEFAULT 0")
                    print("✓ trap_enabled kolonu eklendi")
                except:
                    pass  # Kolon zaten varsa
                
                try:
                    cursor.execute("ALTER TABLE trap_targets ADD COLUMN trap_community TEXT DEFAULT 'public'")
                    print("✓ trap_community kolonu eklendi")
                except:
                    pass
                
                try:
                    cursor.execute("ALTER TABLE trap_targets ADD COLUMN trap_version TEXT DEFAULT '2c'")
                    print("✓ trap_version kolonu eklendi")
                except:
                    pass
                
                try:
                    cursor.execute("ALTER TABLE trap_targets ADD COLUMN trap_interval INTEGER DEFAULT 30")
                    print("✓ trap_interval kolonu eklendi")
                except:
                    pass
                
                conn.commit()
                
                # trap_settings tablosu artık kullanılmıyor - trap_targets'e taşındı
                
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
                
                # Index'ler oluştur - sadece kullanılan filtreler için
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_alarm_timestamp ON alarms(timestamp)')
                # Battery logs için: k > 2, arm, timestamp filtreleri
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_k_arm_timestamp ON battery_data(k, arm, timestamp)')
                # Arm logs için: k = 2, arm, timestamp filtreleri  
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_arm_k_timestamp ON battery_data(arm, k, timestamp)')
                # GROUP BY timestamp, arm, k için
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_timestamp_arm_k ON battery_data(timestamp, arm, k)')
                print("✓ Index'ler oluşturuldu")
                
                conn.commit()
                print("✓ Veritabanı başarıyla oluşturuldu!")
                
                # Default konfigürasyon değerlerini kaydet
                self._initialize_default_configs(cursor, arm_count=4)
                
                # Veritabanı boyutunu göster
                db_size = os.path.getsize(self.db_path) / (1024 * 1024)  # MB
                print(f"Veritabanı boyutu: {db_size:.2f} MB")
                
                # Yeni veritabanı oluşturulduğunda migration set'ine ekle
                with _migration_lock:
                    db_abs_path = os.path.abspath(self.db_path)
                    _migrated_databases.add(db_abs_path)
    
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
                # Ana tabloya ekle
                cursor.executemany('''
                    INSERT INTO battery_data (arm, k, dtype, data, timestamp)
                    VALUES (?, ?, ?, ?, ?)
                ''', [(record['Arm'], record['k'], record['Dtype'], record['data'], record['timestamp']) for record in batch])
                
                
                # Commit
                conn.commit()
                
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
                print(f"🔍 get_paginated_alarms: total_count = {total_count}, show_resolved = {show_resolved}")
                
                # Sayfalama hesapla
                offset = (page - 1) * page_size
                total_pages = (total_count + page_size - 1) // page_size
                print(f"🔍 get_paginated_alarms: page = {page}, page_size = {page_size}, offset = {offset}")
                
                # Sayfalanmış verileri getir
                if show_resolved:
                    query = '''
                        SELECT id, arm, battery, error_code_msb, error_code_lsb, timestamp, status, resolved_at, created_at
                        FROM alarms 
                        ORDER BY timestamp DESC
                        LIMIT ? OFFSET ?
                    '''
                    cursor.execute(query, (page_size, offset))
                else:
                    query = '''
                        SELECT id, arm, battery, error_code_msb, error_code_lsb, timestamp, status, resolved_at, created_at
                        FROM alarms 
                        WHERE status = 'active'
                        ORDER BY timestamp DESC
                        LIMIT ? OFFSET ?
                    '''
                    cursor.execute(query, (page_size, offset))
                
                rows = cursor.fetchall()
                print(f"🔍 get_paginated_alarms: rows count = {len(rows)}")
                if len(rows) > 0:
                    print(f"🔍 get_paginated_alarms: first row = {rows[0]}")
                
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
        """Passive balance verisini güncelle veya ekle - Tek kayıt, ne gelirse güncellenir"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Önce güncellemeyi dene (tüm kayıtları günceller)
            cursor.execute('''
                UPDATE passive_balance 
                SET arm = ?, slave = ?, status = ?, timestamp = ?, created_at = CURRENT_TIMESTAMP
            ''', (arm, slave, status, timestamp))
            
            # Eğer hiç kayıt yoksa insert yap
            if cursor.rowcount == 0:
                cursor.execute('''
                    INSERT INTO passive_balance (arm, slave, status, timestamp)
                    VALUES (?, ?, ?, ?)
                ''', (arm, slave, status, timestamp))
                print(f"✓ Pasif balans eklendi: Kol {arm}, Batarya: {slave}, Status: {status}")
            else:
                print(f"✓ Pasif balans güncellendi: Kol {arm}, Batarya: {slave}, Status: {status}")
            
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
    
    def check_and_create_missing_tables(self):
        """Mevcut veritabanında eksik tabloları kontrol et ve oluştur"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Ana veri tablosu (tüm veriler için)
                cursor.execute("""
                    SELECT name FROM sqlite_master 
                    WHERE type='table' AND name='battery_data'
                """)
                
                if not cursor.fetchone():
                    print("🔄 battery_data tablosu eksik, oluşturuluyor...")
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
                    conn.commit()
                    print("✅ battery_data tablosu oluşturuldu")
                    
                    # Index'leri oluştur (battery_data tablosu oluşturulduktan sonra)
                    print("🔍 Index'ler oluşturuluyor...")
                    cursor.execute('CREATE INDEX IF NOT EXISTS idx_alarm_timestamp ON alarms(timestamp)')
                    cursor.execute('CREATE INDEX IF NOT EXISTS idx_k_arm_timestamp ON battery_data(k, arm, timestamp)')
                    cursor.execute('CREATE INDEX IF NOT EXISTS idx_arm_k_timestamp ON battery_data(arm, k, timestamp)')
                    cursor.execute('CREATE INDEX IF NOT EXISTS idx_timestamp_arm_k ON battery_data(timestamp, arm, k)')
                    conn.commit()
                    print("✅ Index'ler oluşturuldu")
                else:
                    print("✅ battery_data tablosu mevcut")
                
                
                # Dil tablosu
                cursor.execute("""
                    SELECT name FROM sqlite_master 
                    WHERE type='table' AND name='languages'
                """)
                
                if not cursor.fetchone():
                    print("🔄 languages tablosu eksik, oluşturuluyor...")
                    cursor.execute('''
                        CREATE TABLE IF NOT EXISTS languages (
                            language_code TEXT PRIMARY KEY,
                            language_name TEXT,
                            is_active BOOLEAN DEFAULT TRUE,
                            is_default BOOLEAN DEFAULT FALSE
                        )
                    ''')
                    conn.commit()
                    print("✅ languages tablosu oluşturuldu")
                else:
                    print("✅ languages tablosu mevcut")
                
                # Veri tipi tablosu (sadece dtype ile)
                cursor.execute("""
                    SELECT name FROM sqlite_master 
                    WHERE type='table' AND name='data_types'
                """)
                
                if not cursor.fetchone():
                    print("🔄 data_types tablosu eksik, oluşturuluyor...")
                    cursor.execute('''
                        CREATE TABLE IF NOT EXISTS data_types (
                            dtype INTEGER PRIMARY KEY,
                            name TEXT,
                            unit TEXT,
                            description TEXT
                        )
                    ''')
                    conn.commit()
                    print("✅ data_types tablosu oluşturuldu")
                else:
                    print("✅ data_types tablosu mevcut")
                
                # Veri tipi çevirileri
                cursor.execute("""
                    SELECT name FROM sqlite_master 
                    WHERE type='table' AND name='data_type_translations'
                """)
                
                if not cursor.fetchone():
                    print("🔄 data_type_translations tablosu eksik, oluşturuluyor...")
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
                    conn.commit()
                    print("✅ data_type_translations tablosu oluşturuldu")
                else:
                    print("✅ data_type_translations tablosu mevcut")
                
                # Alarm tablosu
                cursor.execute("""
                    SELECT name FROM sqlite_master 
                    WHERE type='table' AND name='alarms'
                """)
                
                if not cursor.fetchone():
                    print("🔄 alarms tablosu eksik, oluşturuluyor...")
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
                    conn.commit()
                    print("✅ alarms tablosu oluşturuldu")
                else:
                    print("✅ alarms tablosu mevcut")
                
                # Mail alıcıları tablosu
                cursor.execute("""
                    SELECT name FROM sqlite_master 
                    WHERE type='table' AND name='mail_recipients'
                """)
                
                if not cursor.fetchone():
                    print("🔄 mail_recipients tablosu eksik, oluşturuluyor...")
                    cursor.execute('''
                        CREATE TABLE IF NOT EXISTS mail_recipients (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            name TEXT NOT NULL,
                            email TEXT NOT NULL UNIQUE,
                            is_active BOOLEAN DEFAULT 1,
                            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                        )
                    ''')
                    conn.commit()
                    print("✅ mail_recipients tablosu oluşturuldu")
                else:
                    print("✅ mail_recipients tablosu mevcut")
                
                # Mail sunucu konfigürasyon tablosu
                cursor.execute("""
                    SELECT name FROM sqlite_master 
                    WHERE type='table' AND name='mail_server_config'
                """)
                
                if not cursor.fetchone():
                    print("🔄 mail_server_config tablosu eksik, oluşturuluyor...")
                    cursor.execute('''
                        CREATE TABLE IF NOT EXISTS mail_server_config (
                            id INTEGER PRIMARY KEY DEFAULT 1,
                            smtp_server TEXT,
                            smtp_port INTEGER,
                            smtp_username TEXT,
                            smtp_password TEXT,
                            use_tls BOOLEAN DEFAULT 1,
                            is_active BOOLEAN DEFAULT 0,
                            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                            CONSTRAINT single_config CHECK (id = 1)
                        )
                    ''')
                    conn.commit()
                    print("✅ mail_server_config tablosu oluşturuldu")
                else:
                    print("✅ mail_server_config tablosu mevcut")
                
                # Passive balance tablosu
                cursor.execute("""
                    SELECT name FROM sqlite_master 
                    WHERE type='table' AND name='passive_balance'
                """)
                
                if not cursor.fetchone():
                    print("🔄 passive_balance tablosu eksik, oluşturuluyor...")
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
                    conn.commit()
                    print("✅ passive_balance tablosu oluşturuldu")
                else:
                    print("✅ passive_balance tablosu mevcut")
                
                # Arm slave counts tablosu
                cursor.execute("""
                    SELECT name FROM sqlite_master 
                    WHERE type='table' AND name='arm_slave_counts'
                """)
                
                if not cursor.fetchone():
                    print("🔄 arm_slave_counts tablosu eksik, oluşturuluyor...")
                    cursor.execute('''
                        CREATE TABLE IF NOT EXISTS arm_slave_counts (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            arm INTEGER,
                            slave_count INTEGER,
                            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                        )
                    ''')
                    conn.commit()
                    print("✅ arm_slave_counts tablosu oluşturuldu")
                    
                    # Default değerleri ekle
                    cursor.execute('''
                        INSERT INTO arm_slave_counts (arm, slave_count) 
                        VALUES 
                            (1, 0),
                            (2, 0), 
                            (3, 7),
                            (4, 0)
                    ''')
                    conn.commit()
                    print("✅ Default arm_slave_counts değerleri eklendi")
                else:
                    print("✅ arm_slave_counts tablosu mevcut")
                
                # missing_data tablosu var mı kontrol et
                cursor.execute("""
                    SELECT name FROM sqlite_master 
                    WHERE type='table' AND name='missing_data'
                """)
                
                if not cursor.fetchone():
                    print("🔄 missing_data tablosu eksik, oluşturuluyor...")
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
                    conn.commit()
                    print("✅ missing_data tablosu oluşturuldu")
                else:
                    print("✅ missing_data tablosu mevcut")
                
                # users tablosu var mı kontrol et
                cursor.execute("""
                    SELECT name FROM sqlite_master 
                    WHERE type='table' AND name='users'
                """)
                
                if not cursor.fetchone():
                    print("🔄 users tablosu eksik, oluşturuluyor...")
                    cursor.execute('''
                        CREATE TABLE IF NOT EXISTS users (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            username TEXT UNIQUE NOT NULL,
                            email TEXT UNIQUE NOT NULL,
                            password_hash TEXT NOT NULL,
                            role TEXT NOT NULL DEFAULT 'guest',
                            is_active BOOLEAN DEFAULT 1,
                            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                        )
                    ''')
                    conn.commit()
                    print("✅ users tablosu oluşturuldu")
                else:
                    print("✅ users tablosu mevcut")
                
                # ip_config tablosu var mı kontrol et
                cursor.execute("""
                    SELECT name FROM sqlite_master 
                    WHERE type='table' AND name='ip_config'
                """)
                
                if not cursor.fetchone():
                    print("🔄 ip_config tablosu eksik, oluşturuluyor...")
                    cursor.execute('''
                        CREATE TABLE IF NOT EXISTS ip_config (
                            id INTEGER PRIMARY KEY DEFAULT 1,
                            ip_address TEXT,
                            subnet_mask TEXT,
                            gateway TEXT,
                            dns_servers TEXT,
                            is_assigned BOOLEAN DEFAULT 0,
                            is_active BOOLEAN DEFAULT 0,
                            use_dhcp BOOLEAN DEFAULT 0,
                            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                            CONSTRAINT single_ip_config CHECK (id = 1)
                        )
                    ''')
                    conn.commit()
                    print("✅ ip_config tablosu oluşturuldu")
                else:
                    print("✅ ip_config tablosu mevcut")
                    # use_dhcp sütunu var mı kontrol et
                    cursor.execute("PRAGMA table_info(ip_config)")
                    columns = [column[1] for column in cursor.fetchall()]
                    if 'use_dhcp' not in columns:
                        print("🔄 use_dhcp sütunu eksik, ekleniyor...")
                        cursor.execute("ALTER TABLE ip_config ADD COLUMN use_dhcp BOOLEAN DEFAULT 0")
                        conn.commit()
                        print("✅ use_dhcp sütunu eklendi")
                
                # reset_system_log tablosu var mı kontrol et
                cursor.execute("""
                    SELECT name FROM sqlite_master 
                    WHERE type='table' AND name='reset_system_log'
                """)
                
                if not cursor.fetchone():
                    print("🔄 reset_system_log tablosu eksik, oluşturuluyor...")
                    cursor.execute('''
                        CREATE TABLE IF NOT EXISTS reset_system_log (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            reset_timestamp INTEGER,
                            reason TEXT,
                            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                        )
                    ''')
                    conn.commit()
                    print("✅ reset_system_log tablosu oluşturuldu")
                else:
                    print("✅ reset_system_log tablosu mevcut")
                
                # trap_settings tablosu artık kullanılmıyor - trap_targets'e taşındı
                
                # trap_targets tablosu var mı kontrol et
                cursor.execute("""
                    SELECT name FROM sqlite_master 
                    WHERE type='table' AND name='trap_targets'
                """)
                
                trap_targets_exists = cursor.fetchone()
                if not trap_targets_exists:
                    print("🔄 trap_targets tablosu eksik, oluşturuluyor...")
                    cursor.execute('''
                        CREATE TABLE IF NOT EXISTS trap_targets (
                            id INTEGER PRIMARY KEY DEFAULT 1,
                            name TEXT NOT NULL DEFAULT 'Trap Target',
                            ip_address TEXT NOT NULL,
                            port INTEGER DEFAULT 162,
                            is_active BOOLEAN DEFAULT 1,
                            trap_enabled BOOLEAN DEFAULT 0,
                            trap_community TEXT DEFAULT 'public',
                            trap_version TEXT DEFAULT '2c',
                            trap_interval INTEGER DEFAULT 30,
                            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                            CONSTRAINT single_trap_target CHECK (id = 1)
                        )
                    ''')
                    conn.commit()
                    print("✅ trap_targets tablosu oluşturuldu")
                else:
                    print("✅ trap_targets tablosu mevcut")
                    # Migration: Yeni kolonları ekle (yoksa)
                    try:
                        cursor.execute("ALTER TABLE trap_targets ADD COLUMN trap_enabled BOOLEAN DEFAULT 0")
                        conn.commit()
                        print("✓ trap_enabled kolonu eklendi (migration)")
                    except:
                        pass
                    try:
                        cursor.execute("ALTER TABLE trap_targets ADD COLUMN trap_community TEXT DEFAULT 'public'")
                        conn.commit()
                        print("✓ trap_community kolonu eklendi (migration)")
                    except:
                        pass
                    try:
                        cursor.execute("ALTER TABLE trap_targets ADD COLUMN trap_version TEXT DEFAULT '2c'")
                        conn.commit()
                        print("✓ trap_version kolonu eklendi (migration)")
                    except:
                        pass
                    try:
                        cursor.execute("ALTER TABLE trap_targets ADD COLUMN trap_interval INTEGER DEFAULT 30")
                        conn.commit()
                        print("✓ trap_interval kolonu eklendi (migration)")
                    except:
                        pass
                
                # ftp_config tablosu var mı kontrol et
                cursor.execute("""
                    SELECT name FROM sqlite_master 
                    WHERE type='table' AND name='ftp_config'
                """)
                
                if not cursor.fetchone():
                    print("🔄 ftp_config tablosu eksik, oluşturuluyor...")
                    cursor.execute('''
                        CREATE TABLE IF NOT EXISTS ftp_config (
                            id INTEGER PRIMARY KEY DEFAULT 1,
                            ftp_host TEXT,
                            ftp_port INTEGER DEFAULT 22,
                            ftp_username TEXT,
                            ftp_password TEXT,
                            is_active BOOLEAN DEFAULT 0,
                            last_sent_at DATETIME,
                            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                            CONSTRAINT single_config CHECK (id = 1)
                        )
                    ''')
                    conn.commit()
                    print("✅ ftp_config tablosu oluşturuldu")
                else:
                    print("✅ ftp_config tablosu mevcut")
                
                # batconfigs tablosu var mı kontrol et
                cursor.execute("""
                    SELECT name FROM sqlite_master 
                    WHERE type='table' AND name='batconfigs'
                """)
                
                if not cursor.fetchone():
                    print("🔄 batconfigs tablosu eksik, oluşturuluyor...")
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
                    conn.commit()
                    print("✅ batconfigs tablosu oluşturuldu")
                else:
                    print("✅ batconfigs tablosu mevcut")
                
                # armconfigs tablosu var mı kontrol et
                cursor.execute("""
                    SELECT name FROM sqlite_master 
                    WHERE type='table' AND name='armconfigs'
                """)
                
                if not cursor.fetchone():
                    print("🔄 armconfigs tablosu eksik, oluşturuluyor...")
                    cursor.execute('''
                        CREATE TABLE IF NOT EXISTS armconfigs (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            armValue INTEGER NOT NULL,
                            akimKats REAL NOT NULL,
                            akimMax REAL NOT NULL,
                            nemMax REAL NOT NULL,
                            nemMin REAL NOT NULL,
                            tempMax REAL NOT NULL,
                            tempMin REAL NOT NULL,
                            time INTEGER NOT NULL,
                            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                        )
                    ''')
                    conn.commit()
                    print("✅ armconfigs tablosu oluşturuldu")
                else:
                    print("✅ armconfigs tablosu mevcut")
                
                # Index'leri oluştur (sadece battery_data için)
                print("🔍 Index'ler kontrol ediliyor...")
                
                # battery_data tablosu var mı kontrol et
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='battery_data'")
                if cursor.fetchone():
                    cursor.execute('CREATE INDEX IF NOT EXISTS idx_k_arm_timestamp ON battery_data(k, arm, timestamp)')
                    cursor.execute('CREATE INDEX IF NOT EXISTS idx_arm_k_timestamp ON battery_data(arm, k, timestamp)')
                    cursor.execute('CREATE INDEX IF NOT EXISTS idx_timestamp_arm_k ON battery_data(timestamp, arm, k)')
                    print("✅ battery_data index'leri oluşturuldu")
                
                conn.commit()
                print("✅ Eksik tablolar ve index'ler başarıyla oluşturuldu")
                    
        except Exception as e:
            print(f"⚠️ Eksik tablo kontrol hatası: {e}")

    def get_arm_slave_counts(self):
        """Arm slave counts verilerini al"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT arm, slave_count FROM arm_slave_counts ORDER BY arm
                ''')
                
                results = cursor.fetchall()
                arm_slave_counts = {}
                
                for arm, slave_count in results:
                    arm_slave_counts[arm] = slave_count
                
                return arm_slave_counts
                
        except Exception as e:
            print(f"❌ get_arm_slave_counts hatası: {e}")
            return None

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
    
    def check_default_users(self):
        """Default kullanıcıları kontrol et ve oluştur"""
        try:
            print("🔍 Default kullanıcılar kontrol ediliyor...")
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Admin kullanıcısı var mı kontrol et
                cursor.execute('''
                    SELECT COUNT(*) FROM users WHERE username = 'Tescom Admin'
                ''')
                admin_count = cursor.fetchone()[0]
                print(f"📊 Admin kullanıcısı sayısı: {admin_count}")
                
                if admin_count == 0:
                    print("🔄 Admin kullanıcısı oluşturuluyor...")
                    try:
                        import bcrypt
                        admin_password = 'Tesbms*1980'
                        admin_password_hash = bcrypt.hashpw(admin_password.encode('utf-8'), bcrypt.gensalt())
                        
                        cursor.execute('''
                            INSERT INTO users (username, email, password_hash, role, is_active)
                            VALUES (?, ?, ?, ?, ?)
                        ''', ('Tescom Admin', 'admin@tescombms.com', admin_password_hash.decode('utf-8'), 'admin', 1))
                        
                        print("✅ Admin kullanıcısı oluşturuldu (bcrypt ile şifrelendi)")
                        print(f"   📧 Email: admin@tescombms.com")
                        print(f"   🔑 Şifre: Tesbms*1980")
                        print(f"   👤 Rol: admin")
                    except ImportError:
                        print("⚠️  bcrypt kütüphanesi bulunamadı, düz şifre ile oluşturuluyor...")
                        admin_password = 'Tesbms*1980'
                        cursor.execute('''
                            INSERT INTO users (username, email, password_hash, role, is_active)
                            VALUES (?, ?, ?, ?, ?)
                        ''', ('Tescom Admin', 'admin@tescombms.com', admin_password, 'admin', 1))
                        print("✅ Admin kullanıcısı oluşturuldu (düz şifre)")
                        print(f"   📧 Email: admin@tescombms.com")
                        print(f"   🔑 Şifre: Tesbms*1980")
                        print(f"   👤 Rol: admin")
                else:
                    print("✅ Admin kullanıcısı zaten mevcut")
                
                # Guest kullanıcısı var mı kontrol et
                cursor.execute('''
                    SELECT COUNT(*) FROM users WHERE username = 'Tescom Guest'
                ''')
                guest_count = cursor.fetchone()[0]
                print(f"📊 Guest kullanıcısı sayısı: {guest_count}")
                
                if guest_count == 0:
                    print("🔄 Guest kullanıcısı oluşturuluyor...")
                    try:
                        import bcrypt
                        guest_password = 'Bmsgst*99'
                        guest_password_hash = bcrypt.hashpw(guest_password.encode('utf-8'), bcrypt.gensalt())
                        
                        cursor.execute('''
                            INSERT INTO users (username, email, password_hash, role, is_active)
                            VALUES (?, ?, ?, ?, ?)
                        ''', ('Tescom Guest', 'guest@tescombms.com', guest_password_hash.decode('utf-8'), 'guest', 1))
                        
                        print("✅ Guest kullanıcısı oluşturuldu (bcrypt ile şifrelendi)")
                        print(f"   📧 Email: guest@tescombms.com")
                        print(f"   🔑 Şifre: Bmsgst*99")
                        print(f"   👤 Rol: guest")
                    except ImportError:
                        print("⚠️  bcrypt kütüphanesi bulunamadı, düz şifre ile oluşturuluyor...")
                        guest_password = 'Bmsgst*99'
                        cursor.execute('''
                            INSERT INTO users (username, email, password_hash, role, is_active)
                            VALUES (?, ?, ?, ?, ?)
                        ''', ('Tescom Guest', 'guest@tescombms.com', guest_password, 'guest', 1))
                        print("✅ Guest kullanıcısı oluşturuldu (düz şifre)")
                        print(f"   📧 Email: guest@tescombms.com")
                        print(f"   🔑 Şifre: Bmsgst*99")
                        print(f"   👤 Rol: guest")
                else:
                    print("✅ Guest kullanıcısı zaten mevcut")
                
                conn.commit()
                print("✅ Default kullanıcılar kontrolü tamamlandı")
                
        except Exception as e:
            print(f"❌ Default kullanıcılar kontrolü hatası: {e}")
            import traceback
            traceback.print_exc()
    
    def migrate_existing_passwords_to_bcrypt(self):
        """Mevcut düz şifreleri bcrypt formatına dönüştür"""
        try:
            print("🔄 Mevcut şifreler bcrypt formatına dönüştürülüyor...")
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Tüm kullanıcıları getir
                cursor.execute('''
                    SELECT id, username, email, password_hash, role
                    FROM users WHERE is_active = 1
                ''')
                
                users = cursor.fetchall()
                print(f"📊 {len(users)} aktif kullanıcı bulundu")
                
                migrated_count = 0
                
                for user in users:
                    user_id, username, email, password_hash, role = user
                    
                    # Eğer şifre zaten bcrypt formatındaysa (60 karakter ve $ ile başlıyorsa) atla
                    if len(password_hash) == 60 and password_hash.startswith('$2b$'):
                        print(f"⏭️  {username} - Şifre zaten bcrypt formatında")
                        continue
                    
                    # Düz şifreyi bcrypt ile hash'le
                    try:
                        import bcrypt
                        new_hash = bcrypt.hashpw(password_hash.encode('utf-8'), bcrypt.gensalt())
                        
                        # Veritabanını güncelle
                        cursor.execute('''
                            UPDATE users 
                            SET password_hash = ?, updated_at = CURRENT_TIMESTAMP
                            WHERE id = ?
                        ''', (new_hash.decode('utf-8'), user_id))
                        
                        print(f"✅ {username} - Şifre bcrypt formatına dönüştürüldü")
                        migrated_count += 1
                        
                    except ImportError:
                        print(f"❌ {username} - bcrypt kütüphanesi bulunamadı, şifre dönüştürülemedi")
                    except Exception as e:
                        print(f"❌ {username} - Şifre dönüştürme hatası: {e}")
                
                conn.commit()
                print(f"🎉 Migration tamamlandı! {migrated_count} kullanıcının şifresi dönüştürüldü.")
                
        except Exception as e:
            print(f"❌ Migration hatası: {e}")
            import traceback
            traceback.print_exc()
    
    def authenticate_user(self, username, password):
        """Kullanıcı doğrulama (kullanıcı adı ile)"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT id, username, email, password_hash, role, is_active
                    FROM users WHERE username = ? AND is_active = 1
                ''', (username,))
                
                user = cursor.fetchone()
                if user:
                    import bcrypt
                    if bcrypt.checkpw(password.encode('utf-8'), user[3].encode('utf-8')):
                        return {
                            'id': user[0],
                            'username': user[1],
                            'email': user[2],
                            'role': user[4]
                        }
                return None
        except Exception as e:
            print(f"❌ Kullanıcı doğrulama hatası: {e}")
            return None
    
    def authenticate_user_by_email(self, email, password):
        """Kullanıcı doğrulama (email ile) - bytescript ile"""
        try:
            print(f"🔍 Kullanıcı doğrulama başlatıldı: {email}")
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT id, username, email, password_hash, role, is_active
                    FROM users WHERE email = ? AND is_active = 1
                ''', (email,))
                
                user = cursor.fetchone()
                if user:
                    print(f"👤 Kullanıcı bulundu: {user[1]} ({user[2]})")
                    try:
                        import bcrypt
                        if bcrypt.checkpw(password.encode('utf-8'), user[3].encode('utf-8')):
                            print(f"✅ Şifre doğru: {email}")
                            return {
                                'id': user[0],
                                'username': user[1],
                                'email': user[2],
                                'role': user[4]
                            }
                        else:
                            print(f"❌ Şifre hatalı: {email}")
                    except ImportError:
                        print(f"❌ bcrypt kütüphanesi bulunamadı: {email}")
                    except Exception as bcrypt_error:
                        print(f"❌ bcrypt hatası: {email} - {bcrypt_error}")
                else:
                    print(f"❌ Kullanıcı bulunamadı: {email}")
                return None
        except Exception as e:
            print(f"❌ Email ile kullanıcı doğrulama hatası: {e}")
            return None
    
    def update_user_password(self, user_id, new_password):
        """Kullanıcı şifresini güncelle"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                import bcrypt
                password_hash = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt())
                
                cursor.execute('''
                    UPDATE users SET password_hash = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                ''', (password_hash.decode('utf-8'), user_id))
                
                conn.commit()
                return True
        except Exception as e:
            print(f"❌ Şifre güncelleme hatası: {e}")
            return False
    
    def create_user(self, email, password, username=None, role='guest'):
        """Yeni kullanıcı oluştur"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                import bcrypt
                
                # Username yoksa email'den oluştur
                if not username:
                    username = email.split('@')[0]
                
                # Şifreyi hash'le
                password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
                
                # Email zaten var mı kontrol et
                cursor.execute('SELECT id FROM users WHERE email = ?', (email,))
                if cursor.fetchone():
                    return {'success': False, 'message': 'Bu e-posta adresi zaten kullanılıyor'}
                
                # Kullanıcıyı oluştur
                cursor.execute('''
                    INSERT INTO users (username, email, password_hash, role, is_active)
                    VALUES (?, ?, ?, ?, 1)
                ''', (username, email, password_hash.decode('utf-8'), role))
                
                conn.commit()
                return {'success': True, 'message': 'Kullanıcı başarıyla oluşturuldu', 'user_id': cursor.lastrowid}
        except Exception as e:
            print(f"❌ Kullanıcı oluşturma hatası: {e}")
            return {'success': False, 'message': f'Kullanıcı oluşturulamadı: {str(e)}'}
    
    def get_all_users(self):
        """Tüm kullanıcıları listele"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT id, username, email, role, is_active, created_at, updated_at
                    FROM users
                    ORDER BY created_at DESC
                ''')
                
                users = []
                for row in cursor.fetchall():
                    users.append({
                        'id': row[0],
                        'username': row[1],
                        'email': row[2],
                        'role': row[3],
                        'is_active': bool(row[4]),
                        'created_at': row[5],
                        'updated_at': row[6]
                    })
                
                return users
        except Exception as e:
            print(f"❌ Kullanıcı listeleme hatası: {e}")
            return []
    
    def reset_user_password(self, user_id, new_password='Bms.dfpw*1980'):
        """Kullanıcı şifresini sıfırla (varsayılan: Bms.dfpw*1980)"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                import bcrypt
                password_hash = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt())
                
                cursor.execute('''
                    UPDATE users SET password_hash = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                ''', (password_hash.decode('utf-8'), user_id))
                
                conn.commit()
                return {'success': True, 'message': 'Şifre başarıyla sıfırlandı', 'new_password': new_password}
        except Exception as e:
            print(f"❌ Şifre sıfırlama hatası: {e}")
            return {'success': False, 'message': f'Şifre sıfırlanamadı: {str(e)}'}
    
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
        
        retry_count = 0
        max_retries = 5  # Retry sayısını artır
        
        while retry_count < max_retries:
            try:
                with self.get_connection() as conn:
                    # Read-only mode için optimizasyonlar
                    conn.execute("PRAGMA query_only = ON")
                    conn.execute("PRAGMA read_uncommitted = 1")  # Uncommitted read için (write lock beklemez)
                    cursor = conn.cursor()
                    
                    # Basit SQL ile gruplandırılmış verileri getir
                    query = '''
                        SELECT 
                            timestamp,
                            arm,
                            k as batteryAddress,
                            MAX(CASE WHEN dtype = 10 THEN data END) as voltage,
                            MAX(CASE WHEN dtype = 11 THEN data END) as health_status,
                            MAX(CASE WHEN dtype = 12 THEN data END) as temperature,
                            MAX(CASE WHEN dtype = 13 THEN data END) as positive_pole_temp,
                            MAX(CASE WHEN dtype = 14 THEN data END) as negative_pole_temp,
                            MAX(CASE WHEN dtype = 126 THEN data END) as charge_status
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
                    
                    # CSV formatı - Gruplandırılmış veriler için (UTF-8 BOM ile)
                    csv_content = "\ufeffZAMAN,KOL,BATARYA ADRESİ,GERİLİM,ŞARJ DURUMU,MODÜL SICAKLIĞI,POZİTİF KUTUP SICAKLIĞI,NEGATİF KUTUP SICAKLIĞI,SAĞLIK DURUMU\n"
                    
                    # Chunk olarak işle (memory efficient)
                    while True:
                        rows = cursor.fetchmany(1000)  # 1000 satır chunk
                        if not rows:
                            break
                        
                        for row in rows:
                            timestamp = datetime.fromtimestamp(row[0] / 1000).strftime('%Y-%m-%d %H:%M:%S')
                            battery_address = row[2] - 2  # k - 2 olarak göster
                            
                            # 0.0 değerlerini de göster, sadece None değerleri için - kullan
                            voltage = row[3] if row[3] is not None else '-'
                            health_status = row[4] if row[4] is not None else '-'
                            temperature = row[5] if row[5] is not None else '-'
                            positive_pole_temp = row[6] if row[6] is not None else '-'
                            negative_pole_temp = row[7] if row[7] is not None else '-'
                            charge_status = row[8] if row[8] is not None else '-'
                            
                            csv_content += f"{timestamp},{row[1]},{battery_address},{voltage},{health_status},{temperature},{positive_pole_temp},{negative_pole_temp},{charge_status}\n"
                    
                    # Query-only mode'u kapat
                    conn.execute("PRAGMA query_only = OFF")
                    return csv_content
                    
            except sqlite3.OperationalError as e:
                if "locked" in str(e).lower() and retry_count < max_retries - 1:
                    retry_count += 1
                    wait_time = 0.2 * (2 ** retry_count)  # Exponential backoff: 0.4s, 0.8s, 1.6s, 3.2s
                    print(f"⚠️ Veritabanı kilitli, yeniden deneniyor ({retry_count}/{max_retries}) {wait_time}s sonra...")
                    time.sleep(wait_time)
                else:
                    raise
            except Exception as e:
                print(f"❌ Log export hatası: {e}")
                raise
    
    def export_arm_logs_to_csv(self, filters=None):
        """Kol log verilerini CSV formatında export et"""
        if filters is None:
            filters = {}
        
        retry_count = 0
        max_retries = 5  # Retry sayısını artır
        
        while retry_count < max_retries:
            try:
                with self.get_connection() as conn:
                    # Read-only mode için optimizasyonlar
                    conn.execute("PRAGMA query_only = ON")
                    conn.execute("PRAGMA read_uncommitted = 1")  # Uncommitted read için (write lock beklemez)
                    cursor = conn.cursor()
                    
                    # Basit SQL ile sadece gerekli verileri getir
                    query = '''
                        SELECT 
                            timestamp,
                            arm,
                            MAX(CASE WHEN dtype = 10 THEN data END) as current,
                            MAX(CASE WHEN dtype = 11 THEN data END) as humidity,
                            MAX(CASE WHEN dtype = 12 THEN data END) as module_temperature,
                            MAX(CASE WHEN dtype = 13 THEN data END) as ambient_temperature
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
                    
                    # CSV formatı - Sadece gerekli alanlar (UTF-8 BOM ile)
                    csv_content = "\ufeffKOL,ZAMAN,AKIM,NEM,MODÜL SICAKLIĞI,ORTAM SICAKLIĞI\n"
                    
                    # Chunk olarak işle (memory efficient)
                    while True:
                        rows = cursor.fetchmany(1000)  # 1000 satır chunk
                        if not rows:
                            break
                        
                        for row in rows:
                            timestamp = datetime.fromtimestamp(row[0] / 1000).strftime('%Y-%m-%d %H:%M:%S')
                            
                            # 0.0 değerlerini de göster, sadece None değerleri için - kullan
                            current = row[2] if row[2] is not None else '-'
                            humidity = row[3] if row[3] is not None else '-'
                            module_temp = row[4] if row[4] is not None else '-'
                            ambient_temp = row[5] if row[5] is not None else '-'
                            
                            csv_content += f"{row[1]},{timestamp},{current},{humidity},{module_temp},{ambient_temp}\n"
                    
                    # Query-only mode'u kapat
                    conn.execute("PRAGMA query_only = OFF")
                    return csv_content
                    
            except sqlite3.OperationalError as e:
                if "locked" in str(e).lower() and retry_count < max_retries - 1:
                    retry_count += 1
                    wait_time = 0.2 * (2 ** retry_count)  # Exponential backoff: 0.4s, 0.8s, 1.6s, 3.2s
                    print(f"⚠️ Veritabanı kilitli, yeniden deneniyor ({retry_count}/{max_retries}) {wait_time}s sonra...")
                    time.sleep(wait_time)
                else:
                    raise
            except Exception as e:
                print(f"❌ Arm log export hatası: {e}")
                raise

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
            
                
                # Pasif balans durumunu kontrol et
                passive_balance_status = self.check_passive_balance_status(arm, battery_address)
                
                # Veri tiplerine göre organize et
                battery_data = {
                    'arm': arm,
                    'batteryAddress': battery_address,
                    'timestamp': latest_timestamp,
                    'voltage': None,
                    'temperature': None,
                    'health': None,
                    'charge': None,
                    'isActive': not passive_balance_status,  # Pasif balansta ise aktif değil
                    'passiveBalance': passive_balance_status
                }
                
                # Sadece en son verileri kullan
                for dtype, data, name, unit, translated_name in data_rows:
                    if dtype == 10:  # Gerilim
                        battery_data['voltage'] = data
                        battery_data['voltage_name'] = translated_name or name
                    elif dtype == 11:  # Sağlık durumu (SOH)
                        battery_data['health'] = data
                        battery_data['health_name'] = translated_name or name
                    elif dtype == 12:  # Sıcaklık
                        battery_data['temperature'] = data
                        battery_data['temperature_name'] = translated_name or name
                    elif dtype == 126:  # Şarj durumu (SOC)
                        battery_data['charge'] = data
                        battery_data['charge_name'] = translated_name or name
                
                # Eksik veri alanları için en son veriyi getir
                if battery_data['voltage'] is None:
                    cursor.execute('''
                        SELECT data FROM battery_data 
                        WHERE arm = ? AND k = ? AND dtype = 10 
                        ORDER BY timestamp DESC LIMIT 1
                    ''', (arm, battery_address))
                    result = cursor.fetchone()
                    battery_data['voltage'] = result[0] if result else 0
                
                if battery_data['health'] is None:
                    cursor.execute('''
                        SELECT data FROM battery_data 
                        WHERE arm = ? AND k = ? AND dtype = 11 
                        ORDER BY timestamp DESC LIMIT 1
                    ''', (arm, battery_address))
                    result = cursor.fetchone()
                    battery_data['health'] = result[0] if result else 0
                
                if battery_data['temperature'] is None:
                    cursor.execute('''
                        SELECT data FROM battery_data 
                        WHERE arm = ? AND k = ? AND dtype = 12 
                        ORDER BY timestamp DESC LIMIT 1
                    ''', (arm, battery_address))
                    result = cursor.fetchone()
                    battery_data['temperature'] = result[0] if result else 0
                
                if battery_data['charge'] is None:
                    cursor.execute('''
                        SELECT data FROM battery_data 
                        WHERE arm = ? AND k = ? AND dtype = 126 
                        ORDER BY timestamp DESC LIMIT 1
                    ''', (arm, battery_address))
                    result = cursor.fetchone()
                    battery_data['charge'] = result[0] if result else 0
                
                return battery_data
        except Exception as e:
            print(f"get_latest_battery_data hatası (arm: {arm}, battery: {battery_address}): {e}")
            return None
    
    def check_passive_balance_status(self, arm, battery_address):
        """Bataryanın pasif balansta olup olmadığını kontrol et"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Pasif balans kaydını kontrol et
                cursor.execute('''
                    SELECT slave, status FROM passive_balance 
                    WHERE arm = ?
                    ORDER BY timestamp DESC LIMIT 1
                ''', (arm,))
                
                result = cursor.fetchone()
                if result:
                    slave, status = result
                    # Eğer bu batarya pasif balansta ise (status=0 ve slave=battery_address)
                    return slave == battery_address and status == 0
                
                return False
                
        except Exception as e:
            print(f"Pasif balans durumu kontrol hatası: {e}")
            return False
    
    def export_batteries_to_csv(self):
        """Batarya verilerini CSV formatında export et"""
        
        retry_count = 0
        max_retries = 5  # Retry sayısını artır
        
        while retry_count < max_retries:
            try:
                with self.get_connection() as conn:
                    # Read-only mode için optimizasyonlar
                    conn.execute("PRAGMA query_only = ON")
                    conn.execute("PRAGMA read_uncommitted = 1")  # Uncommitted read için (write lock beklemez)
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
                    
                    # CSV formatı (UTF-8 BOM ile)
                    csv_content = "\ufeffKOL,BATARYA ADRESİ,SON GÜNCELLEME,GERİLİM (V),SICAKLIK (°C),SAĞLIK DURUMU (%),ŞARJ DURUMU (%)\n"
                    
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
                    
                    # Query-only mode'u kapat
                    conn.execute("PRAGMA query_only = OFF")
                    return csv_content
                    
            except sqlite3.OperationalError as e:
                if "locked" in str(e).lower() and retry_count < max_retries - 1:
                    retry_count += 1
                    wait_time = 0.2 * (2 ** retry_count)  # Exponential backoff: 0.4s, 0.8s, 1.6s, 3.2s
                    print(f"⚠️ Veritabanı kilitli, yeniden deneniyor ({retry_count}/{max_retries}) {wait_time}s sonra...")
                    time.sleep(wait_time)
                else:
                    raise
            except Exception as e:
                print(f"❌ Batteries export hatası: {e}")
                raise
    
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
                
                # Sadece arm_slave_counts tablosunda bataryası olan kolları getir
                cursor.execute('''
                    SELECT asc.arm, asc.slave_count
                    FROM arm_slave_counts asc
                    WHERE asc.slave_count > 0
                    ORDER BY asc.arm
                ''')
                
                active_arms = cursor.fetchall()
                summary_data = []
                
                for arm, slave_count in active_arms:
                    # Bu kol için en son veriyi bul
                    cursor.execute('''
                        SELECT MAX(timestamp) as latest_timestamp
                        FROM battery_data
                        WHERE arm = ?
                    ''', (arm,))
                    
                    latest_timestamp = cursor.fetchone()[0]
                    if not latest_timestamp:
                        continue
                    
                    # Bu kol için nem, sıcaklık ve akım bilgisini al (k=2)
                    cursor.execute('''
                        SELECT bd.dtype, bd.data, dt.name, dt.unit
                        FROM battery_data bd
                        LEFT JOIN data_types dt ON bd.dtype = dt.dtype
                        WHERE bd.arm = ? AND bd.k = 2 AND bd.timestamp = ?
                        ORDER BY bd.dtype
                    ''', (arm, latest_timestamp))
                    
                    arm_data = cursor.fetchall()
                    
                    print(f"Kol {arm} için k=2 verileri: {arm_data}")
                    
                    # Nem, sıcaklık ve akım değerlerini al
                    humidity = None
                    temperature = None
                    current = None
                    
                    for dtype, data, name, unit in arm_data:
                        print(f"  dtype={dtype}, data={data}, name={name}, unit={unit}")
                        if dtype == 10 and data is not None:  # Akım (dtype=10, k=2)
                            current = data
                            print(f"    Akım bulundu: {current}")
                        elif dtype == 11 and data is not None:  # Nem (dtype=11, k=2)
                            humidity = data
                            print(f"    Nem bulundu: {humidity}")
                        elif dtype == 12 and data is not None:  # Sıcaklık (dtype=12, k=2)
                            temperature = data
                            print(f"    Sıcaklık bulundu: {temperature}")
                    
                    # Batarya sayısı zaten slave_count'tan geldi
                    battery_count = slave_count
                    
                    # Ortalama değerleri hesapla
                    cursor.execute('''
                        SELECT 
                            AVG(CASE WHEN bd.dtype = 10 THEN bd.data END) as avg_voltage,
                            AVG(CASE WHEN bd.dtype = 11 THEN bd.data END) as avg_health,
                            AVG(CASE WHEN bd.dtype = 126 THEN bd.data END) as avg_charge
                        FROM battery_data bd
                        WHERE bd.arm = ? AND bd.k != 2 AND bd.timestamp = ?
                    ''', (arm, latest_timestamp))
                    
                    battery_stats = cursor.fetchone()
                    
                    if battery_stats:
                        avg_voltage, avg_health, avg_charge = battery_stats
                        
                        # Eksik veri alanları için en son veriyi getir
                        if current is None:
                            cursor.execute('''
                                SELECT data FROM battery_data 
                                WHERE arm = ? AND k = 2 AND dtype = 10 
                                ORDER BY timestamp DESC LIMIT 1
                            ''', (arm,))
                            result = cursor.fetchone()
                            current = result[0] if result else 0
                        
                        if humidity is None:
                            cursor.execute('''
                                SELECT data FROM battery_data 
                                WHERE arm = ? AND k = 2 AND dtype = 11 
                                ORDER BY timestamp DESC LIMIT 1
                            ''', (arm,))
                            result = cursor.fetchone()
                            humidity = result[0] if result else 0
                        
                        if temperature is None:
                            cursor.execute('''
                                SELECT data FROM battery_data 
                                WHERE arm = ? AND k = 2 AND dtype = 12 
                                ORDER BY timestamp DESC LIMIT 1
                            ''', (arm,))
                            result = cursor.fetchone()
                            temperature = result[0] if result else 0
                        
                        if avg_voltage is None:
                            cursor.execute('''
                                SELECT AVG(data) FROM battery_data 
                                WHERE arm = ? AND k > 2 AND dtype = 10 
                                ORDER BY timestamp DESC LIMIT 10
                            ''', (arm,))
                            result = cursor.fetchone()
                            avg_voltage = result[0] if result else 0
                        
                        if avg_health is None:
                            cursor.execute('''
                                SELECT AVG(data) FROM battery_data 
                                WHERE arm = ? AND k > 2 AND dtype = 11 
                                ORDER BY timestamp DESC LIMIT 10
                            ''', (arm,))
                            result = cursor.fetchone()
                            avg_health = result[0] if result else 0
                        
                        if avg_charge is None:
                            cursor.execute('''
                                SELECT AVG(data) FROM battery_data 
                                WHERE arm = ? AND k > 2 AND dtype = 126 
                                ORDER BY timestamp DESC LIMIT 10
                            ''', (arm,))
                            result = cursor.fetchone()
                            avg_charge = result[0] if result else 0
                        
                        summary_data.append({
                            'arm': arm,
                            'timestamp': latest_timestamp,
                            'current': current,
                            'humidity': humidity,
                            'temperature': temperature,
                            'battery_count': battery_count or 0,
                            'avg_voltage': round(avg_voltage, 3) if avg_voltage else 0,
                            'avg_health': round(avg_health, 3) if avg_health else 0,
                            'avg_charge': round(avg_charge, 3) if avg_charge else 0
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
        if filters is None:
            filters = {}
        
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Hızlı SQL - sadece mevcut verileri getir
                query = '''
                    SELECT 
                        timestamp,
                        arm,
                        k as batteryAddress,
                        MAX(CASE WHEN dtype = 10 THEN data END) as voltage,
                        MAX(CASE WHEN dtype = 11 THEN data END) as health_status,
                        MAX(CASE WHEN dtype = 12 THEN data END) as temperature,
                        MAX(CASE WHEN dtype = 13 THEN data END) as positive_pole_temp,
                        MAX(CASE WHEN dtype = 14 THEN data END) as negative_pole_temp,
                        MAX(CASE WHEN dtype = 126 THEN data END) as charge_status
                    FROM battery_data 
                    WHERE k > 2
                '''
                
                params = []
                
                if filters.get('arm'):
                    query += ' AND arm = ?'
                    params.append(filters['arm'])
                
                if filters.get('battery'):
                    query += ' AND k = ?'
                    params.append(int(filters['battery']) + 2)
                
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
                        'health_status': row[4],
                        'temperature': row[5],
                        'positive_pole_temp': row[6],
                        'negative_pole_temp': row[7],
                        'charge_status': row[8]
                    })
                
                # COUNT sorgusu kaldırıldı - performans için
                # Toplam sayfa sayısı gösterilmiyor, sadece sayfalama var
                
                # Eğer gelen kayıt sayısı page_size'dan azsa, son sayfadayız
                has_more = len(logs) == page_size
                
                print(f"DEBUG database.py: {len(logs)} log verisi döndürüldü, sayfa: {page}, daha fazla var: {has_more}")
                
                return {
                    'logs': logs,
                    'currentPage': page,
                    'hasMore': has_more  # Daha fazla kayıt var mı? (COUNT sorgusu yapılmıyor - performans için)
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
                
                # Hızlı SQL - sadece mevcut verileri getir
                query = '''
                    SELECT 
                        timestamp,
                        arm,
                        MAX(CASE WHEN dtype = 10 THEN data END) as current,
                        MAX(CASE WHEN dtype = 11 THEN data END) as humidity,
                        MAX(CASE WHEN dtype = 12 THEN data END) as module_temperature,
                        MAX(CASE WHEN dtype = 13 THEN data END) as ambient_temperature
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
                        'module_temperature': row[4],
                        'ambient_temperature': row[5]
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
        """Passive balance verilerini getir - Tüm kollar için tek kayıt"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Tüm kollar için tek kayıt (arm=0)
                cursor.execute('''
                    SELECT arm, slave, status, timestamp, created_at
                    FROM passive_balance
                    WHERE arm = 0
                    ORDER BY timestamp DESC
                    LIMIT 1
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
        """Aktif alarm sayısını getir (sadece geçerli alarmlar)"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            # Tüm aktif alarmları çek
            cursor.execute('''
                SELECT error_code_msb, error_code_lsb
                FROM alarms 
                WHERE status = 'active'
            ''')
            rows = cursor.fetchall()
            
            # Geçerli alarmları say (is_valid_alarm kontrolü ile)
            # web_app.py'deki is_valid_alarm fonksiyonunu burada da kullan
            valid_count = 0
            for row in rows:
                error_msb = row[0]
                error_lsb = row[1]
                
                # Geçerli alarm kontrolü
                if self._is_valid_alarm(error_msb, error_lsb):
                    valid_count += 1
            
            return valid_count
    
    def _is_valid_alarm(self, error_msb, error_lsb):
        """Alarm geçerli mi kontrol et (web_app.py'deki is_valid_alarm ile aynı mantık)"""
        # Kol alarmı kontrolü
        if error_lsb == 9:
            return self._get_arm_alarm_description(error_msb) is not None
        # Batarya alarmı kontrolü
        else:
            return self._get_battery_alarm_description(error_msb, error_lsb) is not None
    
    def _get_arm_alarm_description(self, error_msb):
        """Kol alarm açıklaması (web_app.py ile uyumlu)"""
        if error_msb == 2:
            return "Yüksek akım alarmı"
        elif error_msb == 4:
            return "Yüksek nem alarmı"
        elif error_msb == 8:
            return "Yüksek ortam sıcaklığı alarmı"
        elif error_msb == 16:
            return "Yüksek kol sıcaklığı alarmı"
        elif error_msb == 266:
            return "Kol verisi gelmiyor"
        else:
            return None
    
    def _get_battery_alarm_description(self, error_msb, error_lsb):
        """Batarya alarm açıklaması (web_app.py ile uyumlu)"""
        # MSB kontrolü (errorCodeLsb !== 1 && errorCodeMsb >= 1)
        if error_lsb != 1 and error_msb >= 1:
            if error_msb == 1:
                return "Pozitif kutup başı alarmı"
            elif error_msb == 2:
                return "Negatif kutup başı sıcaklık alarmı"
        
        # LSB kontrolü (error_msb = 0 olan durumlar da dahil)
        if error_lsb == 4:
            return "Düşük batarya gerilim uyarısı"
        elif error_lsb == 8:
            return "Düşük batarya gerilimi alarmı"
        elif error_lsb == 16:
            return "Yüksek batarya gerilimi uyarısı"
        elif error_lsb == 32:
            return "Yüksek batarya gerilimi alarmı"
        elif error_lsb == 64:
            return "Modül sıcaklık alarmı"
        
        return None
    
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
                
                # mail_recipients tablosuna yeni sütunları ekle (eğer yoksa)
                
                
                # Index'leri oluştur (eğer yoksa)
                print("🔍 Index'ler kontrol ediliyor...")
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_alarm_timestamp ON alarms(timestamp)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_k_arm_timestamp ON battery_data(k, arm, timestamp)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_arm_k_timestamp ON battery_data(arm, k, timestamp)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_timestamp_arm_k ON battery_data(timestamp, arm, k)')
                print("✅ Index'ler oluşturuldu")
                
                conn.commit()
                print("✅ Eksik tablolar ve index'ler başarıyla oluşturuldu")
                
        except Exception as e:
            print(f"❌ Eksik tablolar oluşturulurken hata: {e}")
            raise e
    

    def _initialize_default_configs(self, cursor, arm_count=4):
        """Private: Default konfigürasyon değerlerini kaydet (cursor ile)"""
        try:
            # Her kol için default batarya konfigürasyonu
            for arm in range(1, arm_count + 1):
                cursor.execute('''
                    INSERT OR IGNORE INTO batconfigs 
                    (armValue, Vmin, Vmax, Vnom, Rintnom, Tempmin_D, Tempmax_D, Tempmin_PN, Tempmax_PN, Socmin, Sohmin, time)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    arm, 10, 14, 11.0, 20,  # Rintnom = 20 mΩ
                    15, 55, 15, 30, 30, 30, 
                    int(time.time() * 1000)
                ))
            
            # Her kol için default kol konfigürasyonu
            for arm in range(1, arm_count + 1):
                cursor.execute('''
                    INSERT OR IGNORE INTO armconfigs 
                    (armValue, akimKats, akimMax, nemMax, nemMin, tempMax, tempMin, time)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    arm, 1.0, 999, 80, 20, 50, 10, 
                    int(time.time() * 1000)
                ))
            
            print(f"✅ Default konfigürasyonlar kaydedildi: {arm_count} kol")
            
        except Exception as e:
            print(f"❌ Default konfigürasyon kaydetme hatası: {e}")
            raise e

    def initialize_default_configs(self, arm_count=4):
        """Tüm kollar için default konfigürasyon değerlerini kaydet"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Her kol için default batarya konfigürasyonu
                for arm in range(1, arm_count + 1):
                    cursor.execute('''
                        INSERT OR IGNORE INTO batconfigs 
                        (armValue, Vmin, Vmax, Vnom, Rintnom, Tempmin_D, Tempmax_D, Tempmin_PN, Tempmax_PN, Socmin, Sohmin, time)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        arm, 10.12, 13.95, 11.0, 20,  # Rintnom = 20 mΩ
                        15, 55, 15, 30, 30, 30, 
                        int(time.time() * 1000)
                    ))
                
                # Her kol için default kol konfigürasyonu
                for arm in range(1, arm_count + 1):
                    cursor.execute('''
                        INSERT OR IGNORE INTO armconfigs 
                        (armValue, akimKats, akimMax, nemMax, nemMin, tempMax, tempMin, time)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        arm, 1.0, 100, 80, 20, 50, 10, 
                        int(time.time() * 1000)
                    ))
                
                conn.commit()
                print(f"✅ Default konfigürasyonlar kaydedildi: {arm_count} kol")
                
        except Exception as e:
            print(f"❌ Default konfigürasyon kaydetme hatası: {e}")
            raise e
    
    def save_battery_config(self, arm, vmin, vmax, vnom, rintnom, tempmin_d, tempmax_d, tempmin_pn, tempmax_pn, socmin, sohmin):
        """Batarya konfigürasyonunu kaydet"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                
                # Önce kayıt var mı kontrol et
                cursor.execute('SELECT COUNT(*) FROM batconfigs WHERE armValue = ?', (arm,))
                exists = cursor.fetchone()[0] > 0
                
                if exists:
                    # Kayıt varsa UPDATE yap
                    cursor.execute('''
                        UPDATE batconfigs SET 
                        Vmin = ?, Vmax = ?, Vnom = ?, Rintnom = ?, 
                        Tempmin_D = ?, Tempmax_D = ?, Tempmin_PN = ?, Tempmax_PN = ?, 
                        Socmin = ?, Sohmin = ?, time = ?
                        WHERE armValue = ?
                    ''', (
                        vmin, vmax, vnom, rintnom, tempmin_d, tempmax_d, 
                        tempmin_pn, tempmax_pn, socmin, sohmin, 
                        int(time.time() * 1000), arm
                    ))
                    print(f"Batarya konfigürasyonu güncellendi: Kol {arm}")
                else:
                    # Kayıt yoksa INSERT yap
                    cursor.execute('''
                        INSERT INTO batconfigs 
                        (armValue, Vmin, Vmax, Vnom, Rintnom, Tempmin_D, Tempmax_D, 
                         Tempmin_PN, Tempmax_PN, Socmin, Sohmin, time, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        arm, vmin, vmax, vnom, rintnom, tempmin_d, tempmax_d, 
                        tempmin_pn, tempmax_pn, socmin, sohmin, 
                        int(time.time() * 1000), int(time.time() * 1000)
                    ))
                    print(f"Batarya konfigürasyonu eklendi: Kol {arm}")
                
                conn.commit()
                print(f"✓ Batarya konfigürasyonu veritabanına kaydedildi: Kol {arm}")
                
        except Exception as e:
            print(f"Batarya konfigürasyonu kaydedilirken hata: {e}")
            raise e
    
    def save_arm_config(self, arm, akim_kats, akim_max, nem_max, nem_min, temp_max, temp_min):
        """Kol konfigürasyonunu kaydet"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                
                # Önce kayıt var mı kontrol et
                cursor.execute('SELECT COUNT(*) FROM armconfigs WHERE armValue = ?', (arm,))
                exists = cursor.fetchone()[0] > 0
                
                if exists:
                    # Kayıt varsa UPDATE yap
                    cursor.execute('''
                        UPDATE armconfigs SET 
                        akimKats = ?, akimMax = ?, nemMax = ?, nemMin = ?, 
                        tempMax = ?, tempMin = ?, time = ?
                        WHERE armValue = ?
                    ''', (
                        akim_kats, akim_max, nem_max, nem_min, 
                        temp_max, temp_min, int(time.time() * 1000), arm
                    ))
                    print(f"Kol konfigürasyonu güncellendi: Kol {arm}")
                else:
                    # Kayıt yoksa INSERT yap
                    cursor.execute('''
                        INSERT INTO armconfigs 
                        (armValue, akimKats, akimMax, nemMax, nemMin, tempMax, tempMin, time, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        arm, akim_kats, akim_max, nem_max, nem_min, 
                        temp_max, temp_min, int(time.time() * 1000), int(time.time() * 1000)
                    ))
                    print(f"Kol konfigürasyonu eklendi: Kol {arm}")
                
                conn.commit()
                print(f"✓ Kol konfigürasyonu veritabanına kaydedildi: Kol {arm}")
                
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
    
    def get_mail_server_config(self):
        """Mail sunucu konfigürasyonunu getir"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT smtp_server, smtp_port, smtp_username, smtp_password, use_tls, is_active
                    FROM mail_server_config 
                    WHERE id = 1
                """)
                result = cursor.fetchone()
                if result:
                    return {
                        'smtp_server': result[0],
                        'smtp_port': result[1],
                        'smtp_username': result[2],
                        'smtp_password': result[3],
                        'use_tls': bool(result[4]),
                        'is_active': bool(result[5])
                    }
                return None
        except Exception as e:
            print(f"Mail sunucu konfigürasyonu getirilirken hata: {e}")
            return None
    
    def save_mail_server_config(self, smtp_server, smtp_port, smtp_username, smtp_password, use_tls=True, is_active=True):
        """Mail sunucu konfigürasyonunu kaydet veya güncelle"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Mevcut kayıt var mı kontrol et
                cursor.execute("SELECT id FROM mail_server_config WHERE id = 1")
                exists = cursor.fetchone()
                
                if exists:
                    # Güncelle
                    cursor.execute("""
                        UPDATE mail_server_config 
                        SET smtp_server = ?, smtp_port = ?, smtp_username = ?, 
                            smtp_password = ?, use_tls = ?, is_active = ?, 
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = 1
                    """, (smtp_server, smtp_port, smtp_username, smtp_password, use_tls, is_active))
                else:
                    # Yeni kayıt oluştur
                    cursor.execute("""
                        INSERT INTO mail_server_config 
                        (id, smtp_server, smtp_port, smtp_username, smtp_password, use_tls, is_active)
                        VALUES (1, ?, ?, ?, ?, ?, ?)
                    """, (smtp_server, smtp_port, smtp_username, smtp_password, use_tls, is_active))
                
                conn.commit()
                return True
        except Exception as e:
            print(f"Mail sunucu konfigürasyonu kaydedilirken hata: {e}")
            return False
    
    def get_ip_config(self):
        """IP konfigürasyonunu getir"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT ip_address, subnet_mask, gateway, dns_servers, is_assigned, is_active, use_dhcp
                    FROM ip_config 
                    WHERE id = 1
                """)
                result = cursor.fetchone()
                if result:
                    return {
                        'ip_address': result[0],
                        'subnet_mask': result[1],
                        'gateway': result[2],
                        'dns_servers': result[3],
                        'is_assigned': bool(result[4]),
                        'is_active': bool(result[5]),
                        'use_dhcp': bool(result[6]) if len(result) > 6 else False
                    }
                return None
        except Exception as e:
            print(f"IP konfigürasyonu getirilirken hata: {e}")
            return None
    
    def save_ip_config(self, ip_address, subnet_mask, gateway, dns_servers, is_assigned=False, is_active=True, use_dhcp=False):
        """IP konfigürasyonunu kaydet veya güncelle"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Mevcut kayıt var mı kontrol et
                cursor.execute("SELECT id FROM ip_config WHERE id = 1")
                exists = cursor.fetchone()
                
                if exists:
                    # Güncelle
                    cursor.execute("""
                        UPDATE ip_config 
                        SET ip_address = ?, subnet_mask = ?, gateway = ?, 
                            dns_servers = ?, is_assigned = ?, is_active = ?, 
                            use_dhcp = ?, updated_at = CURRENT_TIMESTAMP
                        WHERE id = 1
                    """, (ip_address, subnet_mask, gateway, dns_servers, is_assigned, is_active, use_dhcp))
                else:
                    # Yeni kayıt oluştur
                    cursor.execute("""
                        INSERT INTO ip_config 
                        (id, ip_address, subnet_mask, gateway, dns_servers, is_assigned, is_active, use_dhcp)
                        VALUES (1, ?, ?, ?, ?, ?, ?, ?)
                    """, (ip_address, subnet_mask, gateway, dns_servers, is_assigned, is_active, use_dhcp))
                
                conn.commit()
                return True
        except Exception as e:
            print(f"IP konfigürasyonu kaydedilirken hata: {e}")
            return False
    
    # ==============================================
    # RESET SYSTEM LOG FUNCTIONS
    # ==============================================
    
    def log_reset_system(self, reason="Missing data period completed"):
        """Reset system gönderimini logla - ilk reset'te insert, sonraki işlemlerde update"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                current_timestamp = int(time.time() * 1000)
                
                # Tablo boş mu kontrol et
                cursor.execute("SELECT COUNT(*) FROM reset_system_log")
                count = cursor.fetchone()[0]
                
                if count == 0:
                    # İlk reset - insert yap
                    cursor.execute("""
                        INSERT INTO reset_system_log (reset_timestamp, reason)
                        VALUES (?, ?)
                    """, (current_timestamp, reason))
                    print("📝 İlk reset system log kaydedildi")
                else:
                    # Sonraki resetler - update yap (en son kaydı güncelle)
                    cursor.execute("""
                        UPDATE reset_system_log 
                        SET reset_timestamp = ?, reason = ?, created_at = CURRENT_TIMESTAMP
                        WHERE id = (SELECT id FROM reset_system_log ORDER BY id DESC LIMIT 1)
                    """, (current_timestamp, reason))
                    print("📝 Reset system log güncellendi")
                
                conn.commit()
                return current_timestamp
        except Exception as e:
            print(f"Reset system log kaydedilirken hata: {e}")
            return None
    
    def get_last_reset_timestamp(self):
        """Son reset system tarihini getir"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT reset_timestamp FROM reset_system_log 
                    ORDER BY reset_timestamp DESC LIMIT 1
                """)
                result = cursor.fetchone()
                return result[0] if result else None
        except Exception as e:
            print(f"Son reset timestamp getirilirken hata: {e}")
            return None
    
    def can_send_reset_system(self, min_interval_hours=1):
        """Reset system gönderilebilir mi kontrol et (minimum 1 saat aralık)"""
        try:
            last_reset = self.get_last_reset_timestamp()
            if last_reset is None:
                # Tablo boş - ilk reset gönderilebilir
                print("🆕 İlk reset system - tablo boş, reset gönderilebilir")
                return True
            
            current_time = int(time.time() * 1000)
            time_diff_ms = current_time - last_reset
            time_diff_hours = time_diff_ms / (1000 * 60 * 60)  # Milisaniyeyi saate çevir
            
            if time_diff_hours >= min_interval_hours:
                print(f"✅ Reset system gönderilebilir - Son reset'ten {time_diff_hours:.2f} saat geçti")
                return True
            else:
                print(f"⏰ Reset system gönderilemez - Son reset'ten sadece {time_diff_hours:.2f} saat geçti (minimum {min_interval_hours} saat gerekli)")
                return False
                
        except Exception as e:
            print(f"Reset system kontrolü yapılırken hata: {e}")
            return False
    
    # ==============================================
    # BATTERY DETAIL CHARTS FUNCTIONS
    # ==============================================
    
    def get_battery_detail_charts(self, arm, battery, hours=7):
        """Batarya detay grafikleri için veri getir (1 saat aralıklarla, en son 7 saat)"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Son 7 saatlik veri için timestamp hesapla
                current_time = int(time.time() * 1000)
                start_time = current_time - (hours * 60 * 60 * 1000)  # 7 saat öncesi
                
                # Dtype'lar ve anlamları
                dtype_mapping = {
                    10: 'gerilim',      # Gerilim (V)
                    11: 'soc',          # SOC (Şarj Durumu) 0-100%
                    12: 'rimt',         # RIMT (Sağlık Durumu) 0-100%
                    126: 'soh',         # SOH (Sağlık Durumu) 0-100%
                    13: 'modul_sicaklik',    # Modül Sıcaklığı (°C)
                    14: 'pozitif_kutup',     # Pozitif Kutup Sıcaklığı (°C)
                    15: 'negatif_kutup'      # Negatif Kutup Sıcaklığı (°C)
                }
                
                charts_data = {}
                
                # Her dtype için veri getir
                for dtype, chart_name in dtype_mapping.items():
                    cursor.execute("""
                        SELECT 
                            data,
                            timestamp,
                            created_at
                        FROM battery_data 
                        WHERE arm = ? AND k = ? AND dtype = ? 
                        AND timestamp >= ?
                        ORDER BY timestamp ASC
                    """, (arm, battery, dtype, start_time))
                    
                    raw_data = cursor.fetchall()
                    
                    if raw_data:
                        # 1 saat aralıklarla veri grupla
                        hourly_data = self._group_data_by_hour(raw_data, hours)
                        charts_data[chart_name] = hourly_data
                    else:
                        # Veri yoksa boş array
                        charts_data[chart_name] = []
                
                return charts_data
                
        except Exception as e:
            print(f"Batarya detay grafik verisi getirilirken hata: {e}")
            return {}
    
    def _group_data_by_hour(self, raw_data, hours):
        """Veriyi 1 saat aralıklarla grupla (maksimum 7 nokta)"""
        if not raw_data:
            return []
        
        # Saatlik gruplar oluştur
        hourly_groups = {}
        current_time = int(time.time() * 1000)
        
        for i in range(hours):
            hour_start = current_time - ((hours - i) * 60 * 60 * 1000)
            hour_end = current_time - ((hours - i - 1) * 60 * 60 * 1000)
            hourly_groups[i] = {
                'timestamp': hour_start,
                'data': None,
                'count': 0
            }
        
        # Verileri saatlik gruplara dağıt
        for data_point in raw_data:
            data_value, timestamp, created_at = data_point
            
            # Hangi saate ait olduğunu bul
            for hour_key, hour_info in hourly_groups.items():
                if hour_info['timestamp'] <= timestamp < hour_info['timestamp'] + (60 * 60 * 1000):
                    if hour_info['data'] is None:
                        hour_info['data'] = data_value
                    else:
                        # Aynı saatte birden fazla veri varsa ortalama al
                        hour_info['data'] = (hour_info['data'] + data_value) / 2
                    hour_info['count'] += 1
                    break
        
        # Sonuç formatına çevir
        result = []
        for hour_key in sorted(hourly_groups.keys()):
            hour_info = hourly_groups[hour_key]
            if hour_info['data'] is not None:
                result.append({
                    'timestamp': hour_info['timestamp'],
                    'value': round(hour_info['data'], 2),
                    'count': hour_info['count'],
                    'time_label': datetime.fromtimestamp(hour_info['timestamp'] / 1000).strftime('%d/%m %H:%M')
                })
        
        return result

    # ==============================================
    # TRAP TARGETS (Trap Hedefleri) FUNCTIONS
    # ==============================================
    
    def get_trap_targets(self):
        """Tüm trap hedeflerini getir"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                # Önce kolonları kontrol et
                cursor.execute("PRAGMA table_info(trap_targets)")
                columns = [col[1] for col in cursor.fetchall()]
                
                # Kolonları dinamik olarak seç
                select_cols = ['id', 'name', 'ip_address', 'port', 'is_active']
                if 'trap_enabled' in columns:
                    select_cols.append('trap_enabled')
                if 'trap_community' in columns:
                    select_cols.append('trap_community')
                if 'trap_version' in columns:
                    select_cols.append('trap_version')
                if 'trap_interval' in columns:
                    select_cols.append('trap_interval')
                select_cols.extend(['created_at', 'updated_at'])
                
                cursor.execute(f"""
                    SELECT {', '.join(select_cols)}
                    FROM trap_targets 
                    ORDER BY created_at ASC
                """)
                results = cursor.fetchall()
                targets = []
                for row in results:
                    target = {
                        'id': row[0],
                        'name': row[1],
                        'ip_address': row[2],
                        'port': row[3],
                        'is_active': bool(row[4]),
                        'created_at': row[-2] if len(row) > 6 else None,
                        'updated_at': row[-1] if len(row) > 6 else None
                    }
                    # Yeni kolonları ekle (varsa)
                    idx = 5
                    if 'trap_enabled' in columns:
                        target['trap_enabled'] = bool(row[idx]) if idx < len(row) else False
                        idx += 1
                    else:
                        target['trap_enabled'] = False
                    
                    if 'trap_community' in columns:
                        target['trap_community'] = row[idx] if idx < len(row) else 'public'
                        idx += 1
                    else:
                        target['trap_community'] = 'public'
                    
                    if 'trap_version' in columns:
                        target['trap_version'] = row[idx] if idx < len(row) else '2c'
                        idx += 1
                    else:
                        target['trap_version'] = '2c'
                    
                    if 'trap_interval' in columns:
                        target['trap_interval'] = row[idx] if idx < len(row) else 30
                        idx += 1
                    else:
                        target['trap_interval'] = 30
                    
                    if 'trap_username' in columns:
                        target['trap_username'] = row[idx] if idx < len(row) else ''
                        idx += 1
                    else:
                        target['trap_username'] = ''
                    
                    if 'trap_auth_password' in columns:
                        target['trap_auth_password'] = row[idx] if idx < len(row) else ''
                        idx += 1
                    else:
                        target['trap_auth_password'] = ''
                    
                    if 'trap_priv_password' in columns:
                        target['trap_priv_password'] = row[idx] if idx < len(row) else ''
                    else:
                        target['trap_priv_password'] = ''
                    
                    targets.append(target)
                return targets
        except Exception as e:
            print(f"Trap hedefleri getirilirken hata: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def save_trap_target(self, name, ip_address, port=162, is_active=True, trap_enabled=False, trap_community='public', trap_version='2c', trap_interval=30, trap_username='', trap_auth_password='', trap_priv_password=''):
        """Tek trap hedefini kaydet veya güncelle (id=1) - trap_settings mantığı"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Migration: Yeni kolonları ekle (yoksa)
                try:
                    cursor.execute("ALTER TABLE trap_targets ADD COLUMN trap_enabled BOOLEAN DEFAULT 0")
                except:
                    pass
                try:
                    cursor.execute("ALTER TABLE trap_targets ADD COLUMN trap_community TEXT DEFAULT 'public'")
                except:
                    pass
                try:
                    cursor.execute("ALTER TABLE trap_targets ADD COLUMN trap_version TEXT DEFAULT '2c'")
                except:
                    pass
                try:
                    cursor.execute("ALTER TABLE trap_targets ADD COLUMN trap_interval INTEGER DEFAULT 30")
                except:
                    pass
                try:
                    cursor.execute("ALTER TABLE trap_targets ADD COLUMN trap_username TEXT DEFAULT ''")
                except:
                    pass
                try:
                    cursor.execute("ALTER TABLE trap_targets ADD COLUMN trap_auth_password TEXT DEFAULT ''")
                except:
                    pass
                try:
                    cursor.execute("ALTER TABLE trap_targets ADD COLUMN trap_priv_password TEXT DEFAULT ''")
                except:
                    pass
                conn.commit()
                
                # Mevcut kayıt var mı kontrol et
                cursor.execute('SELECT id FROM trap_targets WHERE id = 1')
                exists = cursor.fetchone()
                
                is_active_int = 1 if is_active else 0
                # trap_enabled boolean dönüşümü - string kontrolü de ekle
                if isinstance(trap_enabled, str):
                    trap_enabled = trap_enabled.lower() in ('true', '1', 'yes')
                trap_enabled_int = 1 if bool(trap_enabled) else 0
                
                print(f"💾 Trap hedefi kaydediliyor: trap_enabled={trap_enabled} ({type(trap_enabled).__name__}) -> trap_enabled_int={trap_enabled_int}")
                
                if exists:
                    # Kayıt varsa güncelle
                    cursor.execute('''
                        UPDATE trap_targets 
                        SET name = ?, ip_address = ?, port = ?, is_active = ?,
                            trap_enabled = ?, trap_community = ?, trap_version = ?, trap_interval = ?,
                            trap_username = ?, trap_auth_password = ?, trap_priv_password = ?,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = 1
                    ''', (name, ip_address, port, is_active_int, trap_enabled_int, trap_community, trap_version, trap_interval, trap_username, trap_auth_password, trap_priv_password))
                    print("✅ Trap hedefi güncellendi (id=1)")
                else:
                    # Kayıt yoksa ekle
                    cursor.execute('''
                        INSERT INTO trap_targets 
                        (id, name, ip_address, port, is_active, trap_enabled, trap_community, trap_version, trap_interval, trap_username, trap_auth_password, trap_priv_password)
                        VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (name, ip_address, port, is_active_int, trap_enabled_int, trap_community, trap_version, trap_interval, trap_username, trap_auth_password, trap_priv_password))
                    print("✅ Trap hedefi eklendi (id=1)")
                
                conn.commit()
                return {'success': True, 'message': 'Trap hedefi başarıyla kaydedildi'}
        except Exception as e:
            print(f"❌ Trap hedefi kaydedilirken hata: {e}")
            import traceback
            traceback.print_exc()
            return {'success': False, 'message': str(e)}
    
    def get_trap_target(self):
        """Tek trap hedefini getir (id=1)"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                # Önce kolonları kontrol et
                cursor.execute("PRAGMA table_info(trap_targets)")
                columns = [col[1] for col in cursor.fetchall()]
                
                # Kolonları dinamik olarak seç
                select_cols = ['id', 'name', 'ip_address', 'port', 'is_active']
                if 'trap_enabled' in columns:
                    select_cols.append('trap_enabled')
                if 'trap_community' in columns:
                    select_cols.append('trap_community')
                if 'trap_version' in columns:
                    select_cols.append('trap_version')
                if 'trap_interval' in columns:
                    select_cols.append('trap_interval')
                if 'trap_username' in columns:
                    select_cols.append('trap_username')
                if 'trap_auth_password' in columns:
                    select_cols.append('trap_auth_password')
                if 'trap_priv_password' in columns:
                    select_cols.append('trap_priv_password')
                select_cols.extend(['created_at', 'updated_at'])
                
                cursor.execute(f'''
                    SELECT {', '.join(select_cols)}
                    FROM trap_targets WHERE id = 1
                ''')
                row = cursor.fetchone()
                if row:
                    result = {
                        'id': row[0],
                        'name': row[1],
                        'ip_address': row[2],
                        'port': row[3],
                        'is_active': bool(row[4]),
                        'created_at': row[-2] if len(row) > 6 else None,
                        'updated_at': row[-1] if len(row) > 6 else None
                    }
                    # Yeni kolonları ekle (varsa)
                    idx = 5
                    if 'trap_enabled' in columns:
                        result['trap_enabled'] = bool(row[idx]) if idx < len(row) else False
                        idx += 1
                    else:
                        result['trap_enabled'] = False
                    
                    if 'trap_community' in columns:
                        result['trap_community'] = row[idx] if idx < len(row) else 'public'
                        idx += 1
                    else:
                        result['trap_community'] = 'public'
                    
                    if 'trap_version' in columns:
                        result['trap_version'] = row[idx] if idx < len(row) else '2c'
                        idx += 1
                    else:
                        result['trap_version'] = '2c'
                    
                    if 'trap_interval' in columns:
                        result['trap_interval'] = row[idx] if idx < len(row) else 30
                        idx += 1
                    else:
                        result['trap_interval'] = 30
                    
                    if 'trap_username' in columns:
                        result['trap_username'] = row[idx] if idx < len(row) else ''
                        idx += 1
                    else:
                        result['trap_username'] = ''
                    
                    if 'trap_auth_password' in columns:
                        result['trap_auth_password'] = row[idx] if idx < len(row) else ''
                        idx += 1
                    else:
                        result['trap_auth_password'] = ''
                    
                    if 'trap_priv_password' in columns:
                        result['trap_priv_password'] = row[idx] if idx < len(row) else ''
                    else:
                        result['trap_priv_password'] = ''
                    
                    return result
                return None
        except Exception as e:
            print(f"Trap hedefi getirilirken hata: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def add_trap_target(self, name, ip_address, port=162):
        """Yeni trap hedefi ekle (eski fonksiyon - geriye uyumluluk için)"""
        return self.save_trap_target(name, ip_address, port, is_active=True)
    
    def update_trap_target(self, target_id, name, ip_address, port=162):
        """Trap hedefini güncelle (eski fonksiyon - geriye uyumluluk için)"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE trap_targets 
                    SET name = ?, ip_address = ?, port = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (name, ip_address, port, target_id))
                conn.commit()
                return {'success': True, 'message': 'Trap hedefi başarıyla güncellendi'}
        except Exception as e:
            print(f"Trap hedefi güncellenirken hata: {e}")
            return {'success': False, 'message': str(e)}
    
    def delete_trap_target(self, target_id):
        """Trap hedefini sil"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM trap_targets WHERE id = ?", (target_id,))
                conn.commit()
                return {'success': True, 'message': 'Trap hedefi başarıyla silindi'}
        except Exception as e:
            print(f"Trap hedefi silinirken hata: {e}")
            return {'success': False, 'message': str(e)}
    
    # FTP Configuration Methods
    def get_ftp_config(self):
        """FTP konfigürasyonunu getir"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT ftp_host, ftp_port, ftp_username, ftp_password, is_active, last_sent_at
                    FROM ftp_config WHERE id = 1
                ''')
                row = cursor.fetchone()
                if row:
                    return {
                        'ftp_host': row[0],
                        'ftp_port': row[1],
                        'ftp_username': row[2],
                        'ftp_password': row[3],
                        'is_active': bool(row[4]),
                        'last_sent_at': row[5]
                    }
                return None
        except Exception as e:
            print(f"FTP config getirilirken hata: {e}")
            return None
    
    def save_ftp_config(self, ftp_host, ftp_port, ftp_username, ftp_password, is_active):
        """FTP konfigürasyonunu kaydet veya güncelle"""
        try:
            import base64
            # Şifreyi base64 ile encode et (basit güvenlik)
            encoded_password = base64.b64encode(ftp_password.encode()).decode() if ftp_password else None
            
            with self.get_connection() as conn:
                cursor = conn.cursor()
                # Önce var mı kontrol et
                cursor.execute('SELECT id FROM ftp_config WHERE id = 1')
                exists = cursor.fetchone()
                
                if exists:
                    # Güncelle
                    cursor.execute('''
                        UPDATE ftp_config 
                        SET ftp_host = ?, ftp_port = ?, ftp_username = ?, ftp_password = ?, 
                            is_active = ?, updated_at = CURRENT_TIMESTAMP
                        WHERE id = 1
                    ''', (ftp_host, ftp_port, ftp_username, encoded_password, is_active))
                else:
                    # Yeni kayıt
                    cursor.execute('''
                        INSERT INTO ftp_config (id, ftp_host, ftp_port, ftp_username, ftp_password, is_active)
                        VALUES (1, ?, ?, ?, ?, ?)
                    ''', (ftp_host, ftp_port, ftp_username, encoded_password, is_active))
                
                conn.commit()
                return {'success': True, 'message': 'FTP ayarları kaydedildi'}
        except Exception as e:
            print(f"FTP config kaydedilirken hata: {e}")
            return {'success': False, 'message': str(e)}
    
    # Trap Settings Methods
    def get_trap_settings(self):
        """Trap ayarlarını getir"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT trap_enabled, trap_server, trap_port, trap_community, trap_version, trap_interval
                    FROM trap_settings WHERE id = 1
                ''')
                row = cursor.fetchone()
                if row:
                    return {
                        'trapEnabled': bool(row[0]),
                        'trapServer': row[1],
                        'trapPort': row[2],
                        'trapCommunity': row[3],
                        'trapVersion': row[4],
                        'trapInterval': row[5]
                    }
                return None
        except Exception as e:
            print(f"Trap settings getirilirken hata: {e}")
            return None
    
    def save_trap_settings(self, trap_enabled, trap_server, trap_port, trap_community, trap_version, trap_interval):
        """Trap ayarlarını kaydet veya güncelle"""
        try:
            # Boolean değeri integer'a çevir (SQLite için)
            trap_enabled_int = 1 if trap_enabled else 0
            
            print(f"💾 Trap ayarları kaydediliyor: enabled={trap_enabled} ({trap_enabled_int}), server={trap_server}, port={trap_port}, community={trap_community}, version={trap_version}, interval={trap_interval}")
            
            with self.get_connection() as conn:
                cursor = conn.cursor()
                # Önce var mı kontrol et
                cursor.execute('SELECT id FROM trap_settings WHERE id = 1')
                exists = cursor.fetchone()
                
                if exists:
                    # Güncelle
                    cursor.execute('''
                        UPDATE trap_settings 
                        SET trap_enabled = ?, trap_server = ?, trap_port = ?, 
                            trap_community = ?, trap_version = ?, trap_interval = ?,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = 1
                    ''', (trap_enabled_int, trap_server, trap_port, trap_community, trap_version, trap_interval))
                    print("✅ Trap ayarları güncellendi")
                else:
                    # Yeni kayıt
                    cursor.execute('''
                        INSERT INTO trap_settings 
                        (id, trap_enabled, trap_server, trap_port, trap_community, trap_version, trap_interval)
                        VALUES (1, ?, ?, ?, ?, ?, ?)
                    ''', (trap_enabled_int, trap_server, trap_port, trap_community, trap_version, trap_interval))
                    print("✅ Trap ayarları eklendi")
                
                conn.commit()
                
                # Kaydedilen veriyi kontrol et
                cursor.execute('SELECT * FROM trap_settings WHERE id = 1')
                saved = cursor.fetchone()
                print(f"📋 Kaydedilen trap ayarları: {saved}")
                
                return {'success': True, 'message': 'Trap ayarları kaydedildi'}
        except Exception as e:
            print(f"❌ Trap settings kaydedilirken hata: {e}")
            import traceback
            traceback.print_exc()
            return {'success': False, 'message': str(e)}
    
    def update_ftp_last_sent(self):
        """FTP son gönderim zamanını güncelle"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE ftp_config 
                    SET last_sent_at = CURRENT_TIMESTAMP
                    WHERE id = 1
                ''')
                conn.commit()
        except Exception as e:
            print(f"FTP last_sent güncellenirken hata: {e}")
    
    def toggle_trap_target(self, target_id):
        """Trap hedefini aktif/pasif yap"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE trap_targets 
                    SET is_active = NOT is_active, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (target_id,))
                conn.commit()
                return {'success': True, 'message': 'Trap hedefi durumu değiştirildi'}
        except Exception as e:
            print(f"Trap hedefi durumu değiştirilirken hata: {e}")
            return {'success': False, 'message': str(e)}