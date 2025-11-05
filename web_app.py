# interface/web_app.py
from flask import Flask, render_template, jsonify, request, session, redirect, url_for
from database import BatteryDatabase
import time
import json
import threading
import os
from datetime import datetime
from functools import wraps

app = Flask(__name__)
app.secret_key = 'tescom_bms_secret_key_2024'  # Session için secret key

# Thread-safe database erişimi için lock'lar
db_lock = threading.Lock()  # Write işlemleri için
db_read_lock = threading.RLock()  # Read işlemleri için (multiple readers allowed)

# Retry mekanizması için
import time as time_module

# Veri alma periyot başlangıcı
data_retrieval_period_start = None

# Database instance'ını thread-safe yapmak için lazy loading
# main.py'den farklı bir connection pool kullan
def get_db():
    if not hasattr(get_db, 'instance'):
        get_db.instance = BatteryDatabase()
        # Connection pool zaten WAL mode ve timeout ile yapılandırılmış
        # Database instance oluşturuldu
    return get_db.instance

# Authentication decorator'ları
def login_required(f):
    """Giriş yapmış kullanıcı kontrolü"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    """Admin yetkisi kontrolü"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        if session.get('user_role') != 'admin':
            return jsonify({'success': False, 'message': 'Admin yetkisi gerekli'}), 403
        return f(*args, **kwargs)
    return decorated_function

# Database işlemleri için retry wrapper
def db_operation_with_retry(operation, max_retries=3, delay=0.1):
    """Database işlemini retry ile çalıştır"""
    for attempt in range(max_retries):
        try:
            return operation()
        except Exception as e:
            if "database is locked" in str(e).lower() and attempt < max_retries - 1:
                print(f"⚠️ Database locked, retry {attempt + 1}/{max_retries} in {delay}s...")
                time_module.sleep(delay)
                delay *= 2  # Exponential backoff
            else:
                raise e

# Global db referansı (backward compatibility için)
db = None

@app.route('/')
def index():
    # Giriş yapmamışsa login sayfasına yönlendir
    if 'user_id' not in session:
        return redirect(url_for('login'))
    # Ana sayfa olarak layout'u göster
    return render_template('layout.html')

@app.route('/login')
def login():
    # Zaten giriş yapmışsa ana sayfaya yönlendir
    if 'user_id' in session:
        return redirect(url_for('index'))
    return render_template('pages/login.html')

@app.route('/profile')
@login_required
def profile():
    return render_template('pages/profile.html')

@app.route('/api/login', methods=['POST'])
def api_login():
    """Kullanıcı girişi (email ile)"""
    try:
        # Hem JSON hem form data'yı kabul et
        if request.is_json:
            data = request.get_json()
        else:
            data = request.form
        
        email = data.get('email')
        password = data.get('password')
        
        if not email or not password:
            return jsonify({'success': False, 'message': 'E-posta ve şifre gerekli'}), 400
        
        # Kullanıcı doğrulama (email ile)
        db_instance = get_db()
        user = db_instance.authenticate_user_by_email(email, password)
        
        if user:
            # Session'a kullanıcı bilgilerini kaydet
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['user_email'] = user['email']
            session['user_role'] = user['role']
            
            print(f"✅ Başarılı giriş: {email}")
            # Başarılı giriş - ana sayfaya yönlendir
            return redirect(url_for('index'))
        else:
            # Hatalı giriş - login sayfasına geri dön
            print(f"❌ Giriş hatası: {email} - Kullanıcı bulunamadı veya şifre hatalı")
            return redirect(url_for('login'))
            
    except Exception as e:
        print(f"❌ Giriş exception hatası: {email} - {str(e)}")
        return jsonify({'success': False, 'message': f'Giriş hatası: {str(e)}'}), 500

@app.route('/api/logout', methods=['POST'])
def api_logout():
    """Kullanıcı çıkışı"""
    session.clear()
    return jsonify({'success': True, 'message': 'Çıkış başarılı'})

@app.route('/api/change-password', methods=['POST'])
@login_required
def api_change_password():
    """Şifre değiştirme"""
    try:
        data = request.get_json()
        current_password = data.get('currentPassword')
        new_password = data.get('newPassword')
        confirm_password = data.get('confirmPassword')
        
        if not all([current_password, new_password, confirm_password]):
            return jsonify({'success': False, 'message': 'Tüm alanlar gerekli'}), 400
        
        if new_password != confirm_password:
            return jsonify({'success': False, 'message': 'Yeni şifreler eşleşmiyor'}), 400
        
        if len(new_password) < 6:
            return jsonify({'success': False, 'message': 'Şifre en az 6 karakter olmalı'}), 400
        
        # Mevcut şifreyi doğrula
        db_instance = get_db()
        user = db_instance.authenticate_user(session['username'], current_password)
        
        if not user:
            return jsonify({'success': False, 'message': 'Mevcut şifre hatalı'}), 400
        
        # Şifreyi güncelle
        success = db_instance.update_user_password(session['user_id'], new_password)
        
        if success:
            return jsonify({'success': True, 'message': 'Şifre başarıyla değiştirildi'})
        else:
            return jsonify({'success': False, 'message': 'Şifre değiştirilemedi'}), 500
            
    except Exception as e:
        return jsonify({'success': False, 'message': f'Şifre değiştirme hatası: {str(e)}'}), 500

@app.route('/api/user-info')
@login_required
def api_user_info():
    """Kullanıcı bilgilerini getir"""
    return jsonify({
        'success': True,
        'user': {
            'username': session.get('username'),
            'email': session.get('user_email'),
            'role': session.get('user_role')
        }
    })

@app.route('/mail-management')
@login_required
def mail_management():
    return render_template('pages/mail-management.html')

@app.route('/mail-server-config')
@login_required
def mail_server_config():
    return render_template('pages/mail-server-config.html')

@app.route('/interface-ip-settings')
@login_required
def interface_ip_settings():
    return render_template('pages/interface-ip-settings.html')

@app.route('/page/<page_name>')
def get_page(page_name):
    """Sayfa içeriğini döndür"""
    if page_name == 'summary':
        return render_template('pages/summary.html')
    elif page_name == 'alarms':
        return render_template('pages/alarms.html')
    elif page_name == 'batteries':
        return render_template('pages/batteries.html')
    elif page_name == 'battery-logs':
        return render_template('pages/battery-logs.html')
    elif page_name == 'arm-logs':
        return render_template('pages/arm-logs.html')
    elif page_name == 'configuration':
        return render_template('pages/configuration.html')
    elif page_name == 'data-retrieval':
        return render_template('pages/data-retrieval.html')
    elif page_name == 'profile':
        return render_template('pages/profile.html')
    else:
        return render_template('pages/404.html')

@app.route('/pages/<page_name>.html')
def get_page_html(page_name):
    """Sayfa içeriğini HTML olarak döndür (JavaScript için)"""
    if page_name == 'summary':
        return render_template('pages/summary.html')
    elif page_name == 'alarms':
        return render_template('pages/alarms.html')
    elif page_name == 'batteries':
        return render_template('pages/batteries.html')
    elif page_name == 'battery-logs':
        return render_template('pages/battery-logs.html')
    elif page_name == 'arm-logs':
        return render_template('pages/arm-logs.html')
    elif page_name == 'configuration':
        return render_template('pages/configuration.html')
    elif page_name == 'data-retrieval':
        return render_template('pages/data-retrieval.html')
    elif page_name == 'trap-settings':
        return render_template('pages/trap-settings.html')
    elif page_name == 'profile':
        return render_template('pages/profile.html')
    else:
        return render_template('pages/404.html')

@app.route('/api/data_types')
def get_data_types():
    language = request.args.get('lang', 'tr')  # Varsayılan Türkçe
    db_instance = get_db()
    with db_read_lock:
        data_types = db_instance.get_data_types_by_language(language)
    return jsonify(data_types)

@app.route('/api/alarm_count')
def get_alarm_count():
    """Aktif alarm sayısını getir"""
    try:
        db_instance = get_db()
        with db_read_lock:
            count = db_instance.get_active_alarm_count()
        return jsonify({
            'success': True,
            'count': count
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500

@app.route('/api/recent_data')
def get_recent_data():
    minutes = int(request.args.get('minutes', 5))
    arm = request.args.get('arm')
    battery = request.args.get('battery')
    dtype = request.args.get('dtype')
    data_type = request.args.get('data_type')
    limit = int(request.args.get('limit', 50))
    language = request.args.get('lang', 'tr')
    
    if arm:
        arm = int(arm)
    if battery:
        battery = int(battery)
    if dtype:
        dtype = int(dtype)
    
    db_instance = get_db()
    with db_read_lock:
        data = db_instance.get_recent_data_with_translations(
        minutes=minutes, 
        arm=arm, 
        battery=battery, 
        dtype=dtype, 
        data_type=data_type, 
        limit=limit,
        language=language
    )
    return jsonify(data)

@app.route('/api/data_by_date')
def get_data_by_date():
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    arm = request.args.get('arm')
    dtype = request.args.get('dtype')
    language = request.args.get('lang', 'tr')
    
    if arm:
        arm = int(arm)
    if dtype:
        dtype = int(dtype)
    
    db_instance = get_db()
    with db_read_lock:
        data = db_instance.get_data_by_date_range_with_translations(
        start_date, end_date, arm, dtype, language
    )
    return jsonify(data)



@app.route('/api/battery-logs', methods=['POST'])
def get_battery_logs():
    """Gruplandırılmış batarya log verilerini getir"""
    data = request.get_json()
    page = data.get('page', 1)
    page_size = data.get('pageSize', 50)
    filters = data.get('filters', {})
    
    # Mevcut dili al
    language = request.headers.get('X-Language', 'tr')
    
    try:
        # Veritabanından gruplandırılmış batarya log verilerini al
        db_instance = get_db()
        with db_read_lock:
            logs_data = db_instance.get_grouped_battery_logs(
            page=page,
            page_size=page_size,
            filters=filters,
            language=language
        )
        
        return jsonify({
            'success': True,
            'logs': logs_data['logs'],
            'totalCount': logs_data['totalCount'],
            'totalPages': logs_data['totalPages'],
            'currentPage': logs_data['currentPage']
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500

@app.route('/api/battery-detail-charts', methods=['POST'])
def get_battery_detail_charts():
    """Batarya detay grafikleri için veri getir (1 saat aralıklarla, en son 7 saat)"""
    data = request.get_json()
    arm = data.get('arm')
    battery = data.get('battery')
    
    if not arm or not battery:
        return jsonify({
            'success': False,
            'message': 'Arm ve battery parametreleri gerekli'
        }), 400
    
    try:
        db_instance = get_db()
        with db_read_lock:
            # 1 saat aralıklarla en son 7 saatlik veri getir
            charts_data = db_instance.get_battery_detail_charts(arm, battery)
        
        return jsonify({
            'success': True,
            'data': charts_data
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500

@app.route('/api/arm-logs', methods=['POST'])
def get_arm_logs():
    """Gruplandırılmış kol log verilerini getir"""
    data = request.get_json()
    page = data.get('page', 1)
    page_size = data.get('pageSize', 50)
    filters = data.get('filters', {})
    
    # Mevcut dili al
    language = request.headers.get('X-Language', 'tr')
    
    try:
        # Veritabanından gruplandırılmış kol log verilerini al
        db_instance = get_db()
        with db_read_lock:
            logs_data = db_instance.get_grouped_arm_logs(
            page=page,
            page_size=page_size,
            filters=filters,
            language=language
        )
        
        return jsonify({
            'success': True,
            'logs': logs_data['logs'],
            'totalCount': logs_data['totalCount'],
            'totalPages': logs_data['totalPages'],
            'currentPage': logs_data['currentPage']
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500

@app.route('/api/logs/export', methods=['POST'])
def export_logs():
    """Log verilerini CSV olarak export et"""
    try:
        data = request.get_json()
        filters = data.get('filters', {})
        
        db_instance = get_db()
        with db_read_lock:
            csv_content = db_instance.export_logs_to_csv(filters)
        
        response = app.response_class(
            response=csv_content,
            status=200,
            mimetype='text/csv'
        )
        response.headers['Content-Disposition'] = 'attachment; filename=logs_export.csv'
        response.headers['Content-Type'] = 'text/csv; charset=utf-8'
        return response
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/batteries', methods=['POST'])
def get_batteries():
    """Batarya verilerini getir"""
    try:
        data = request.get_json()
        page = data.get('page', 1)
        page_size = data.get('pageSize', 30)
        selected_arm = data.get('selectedArm', 3)  # Varsayılan: Kol 3
        
        # Mevcut dili al (localStorage'dan veya varsayılan olarak 'tr')
        language = request.headers.get('X-Language', 'tr')
        
        # Read-only işlem için read lock kullan (daha hızlı)
        def get_batteries_data():
            db_instance = get_db()
            with db_read_lock:
                return db_instance.get_batteries_for_display(page, page_size, selected_arm, language)
        
        batteries_data = db_operation_with_retry(get_batteries_data)
        
        return jsonify({
            'success': True,
            'batteries': batteries_data['batteries'],
            'totalPages': batteries_data['totalPages'],
            'currentPage': batteries_data['currentPage']
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500

@app.route('/api/active-arms', methods=['GET'])
def get_active_arms():
    """Aktif kolları getir (armslavecount > 0)"""
    try:
        db_instance = get_db()
        with db_read_lock:
            active_arms = db_instance.get_active_arms()
        return jsonify({
            'success': True,
            'activeArms': active_arms
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500

@app.route('/api/passive-balance', methods=['GET'])
def get_passive_balance():
    """Passive balance verilerini getir"""
    try:
        arm = request.args.get('arm')
        if arm:
            arm = int(arm)
        
        db_instance = get_db()
        with db_read_lock:
            balance_data = db_instance.get_passive_balance(arm)
        return jsonify({
            'success': True,
            'balanceData': balance_data
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500

@app.route('/api/batteries/export', methods=['POST'])
def export_batteries():
    """Batarya verilerini CSV olarak export et"""
    try:
        # Lock kullanmadan doğrudan çağır - database.py içinde optimize edilecek
        db_instance = get_db()
        csv_content = db_instance.export_batteries_to_csv()
        
        response = app.response_class(
            response=csv_content,
            status=200,
            mimetype='text/csv'
        )
        response.headers['Content-Disposition'] = 'attachment; filename=batteries_export.csv'
        response.headers['Content-Type'] = 'text/csv; charset=utf-8'
        return response
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/battery-logs/export', methods=['POST'])
def export_battery_logs():
    """Batarya log verilerini CSV olarak export et"""
    try:
        data = request.get_json()
        filters = data.get('filters', {}) if data else {}
        
        # Lock kullanmadan doğrudan çağır - database.py içinde optimize edilmiş
        db_instance = get_db()
        csv_content = db_instance.export_logs_to_csv(filters)
        
        response = app.response_class(
            response=csv_content,
            status=200,
            mimetype='text/csv'
        )
        response.headers['Content-Disposition'] = 'attachment; filename=battery_logs_export.csv'
        response.headers['Content-Type'] = 'text/csv; charset=utf-8'
        return response
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/arm-logs/export', methods=['POST'])
def export_arm_logs():
    """Kol log verilerini CSV olarak export et"""
    try:
        data = request.get_json()
        filters = data.get('filters', {}) if data else {}
        
        # Lock kullanmadan doğrudan çağır - database.py içinde optimize edilmiş
        db_instance = get_db()
        csv_content = db_instance.export_arm_logs_to_csv(filters)
        
        response = app.response_class(
            response=csv_content,
            status=200,
            mimetype='text/csv'
        )
        response.headers['Content-Disposition'] = 'attachment; filename=arm_logs_export.csv'
        response.headers['Content-Type'] = 'text/csv; charset=utf-8'
        return response
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/stats')
def get_stats():
    """İstatistik verilerini getir"""
    try:
        # Basit istatistikler
        stats = {
            'database_size': get_db().get_database_size() if hasattr(get_db, 'instance') else 0,
            'timestamp': int(time.time() * 1000)
        }
        return jsonify(stats)
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500

@app.route('/api/batconfigs', methods=['POST'])
@admin_required
def save_batconfig():
    """Batarya konfigürasyonunu kaydet"""
    try:
        data = request.get_json()
        
        # Veri doğrulama
        required_fields = [
            'armValue', 'Vmin', 'Vmax', 'Vnom', 'Rintnom',
            'Tempmin_D', 'Tempmax_D', 'Tempmin_PN', 'Tempmax_PN',
            'Socmin', 'Sohmin'
        ]
        
        for field in required_fields:
            if field not in data or data[field] is None:
                return jsonify({
                    'success': False,
                    'message': f'Eksik alan: {field}'
                }), 400
        
        # Zaman damgası ekle
        data['time'] = int(time.time() * 1000)
        
        # Konfigürasyonu JSON dosyasına kaydet (main.py için)
        config_data = {
            'type': 'batconfig',
            'data': data,
            'timestamp': data['time']
        }
        
        try:
            # Konfigürasyonu dosyaya kaydet (main.py için)
            with open('pending_config.json', 'w', encoding='utf-8') as f:
                json.dump(config_data, f, indent=2, ensure_ascii=False)
            print(f"Batarya konfigürasyonu dosyaya kaydedildi: {data}")
            
            # Konfigürasyonu veritabanına da kaydet
            db_instance = get_db()
            with db_lock:
                db_instance.save_battery_config(
                    arm=data['armValue'],
                    vmin=data['Vmin'],
                    vmax=data['Vmax'],
                    vnom=data['Vnom'],
                    rintnom=data['Rintnom'],
                    tempmin_d=data['Tempmin_D'],
                    tempmax_d=data['Tempmax_D'],
                    tempmin_pn=data['Tempmin_PN'],
                    tempmax_pn=data['Tempmax_PN'],
                    socmin=data['Socmin'],
                    sohmin=data['Sohmin']
                )
            print(f"Batarya konfigürasyonu veritabanına kaydedildi: Kol {data['armValue']}")
            
        except Exception as e:
            print(f"Konfigürasyon kaydedilirken hata: {e}")
            return jsonify({
                'success': False,
                'message': 'Konfigürasyon kaydedilemedi'
            }), 500
        
        return jsonify({
            'success': True,
            'message': 'Batarya konfigürasyonu başarıyla kaydedildi',
            'data': data
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500

@app.route('/api/armconfigs', methods=['POST'])
@admin_required
def save_armconfig():
    """Kol konfigürasyonunu kaydet"""
    try:
        data = request.get_json()
        
        # Veri doğrulama
        required_fields = [
            'armValue', 'akimKats', 'akimMax', 'nemMax', 'nemMin',
            'tempMax', 'tempMin'
        ]
        
        for field in required_fields:
            if field not in data or data[field] is None:
                return jsonify({
                    'success': False,
                    'message': f'Eksik alan: {field}'
                }), 400
        
        # Maksimum akım kontrolü
        if data['akimMax'] > 999:
            return jsonify({
                'success': False,
                'message': 'Maksimum akım değeri 999\'dan büyük olamaz!'
            }), 400
        
        # Zaman damgası ekle
        data['time'] = int(time.time() * 1000)
        
        # Konfigürasyonu JSON dosyasına kaydet (main.py için)
        config_data = {
            'type': 'armconfig',
            'data': data,
            'timestamp': data['time']
        }
        
        try:
            # Konfigürasyonu dosyaya kaydet (main.py için)
            with open('pending_config.json', 'w', encoding='utf-8') as f:
                json.dump(config_data, f, indent=2, ensure_ascii=False)
            print(f"Kol konfigürasyonu dosyaya kaydedildi: {data}")
            
            # Konfigürasyonu veritabanına da kaydet
            db_instance = get_db()
            with db_lock:
                db_instance.save_arm_config(
                    arm=data['armValue'],
                    akim_kats=data['akimKats'],
                    akim_max=data['akimMax'],
                    nem_max=data['nemMax'],
                    nem_min=data['nemMin'],
                    temp_max=data['tempMax'],
                    temp_min=data['tempMin']
                )
            print(f"Kol konfigürasyonu veritabanına kaydedildi: Kol {data['armValue']}")
            
        except Exception as e:
            print(f"Konfigürasyon kaydedilirken hata: {e}")
            return jsonify({
                'success': False,
                'message': 'Konfigürasyon kaydedilemedi'
            }), 500
        
        return jsonify({
            'success': True,
            'message': 'Kol konfigürasyonu başarıyla kaydedildi',
            'data': data
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500

@app.route('/api/batconfigs', methods=['GET'])
def get_batconfigs():
    """Tüm batarya konfigürasyonlarını getir"""
    try:
        # Veritabanından konfigürasyonları oku
        db_instance = get_db()
        with db_read_lock:
            configs = db_instance.get_batconfigs()
        return jsonify({
            'success': True,
            'data': configs
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500

@app.route('/api/armconfigs', methods=['GET'])
def get_armconfigs():
    """Tüm kol konfigürasyonlarını getir"""
    try:
        # Veritabanından konfigürasyonları oku
        db_instance = get_db()
        with db_read_lock:
            configs = db_instance.get_armconfigs()
        return jsonify({
            'success': True,
            'data': configs
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500

@app.route('/api/alarms', methods=['GET'])
def get_alarms():
    """Sayfalanmış alarmları getir"""
    try:
        # Query parametrelerini al
        show_resolved = request.args.get('show_resolved', 'false').lower() == 'true'
        page = int(request.args.get('page', 1))
        page_size = int(request.args.get('pageSize', 50))
        
        # Veritabanından sayfalanmış alarmları oku
        def get_alarms_data():
            db_instance = get_db()
            with db_read_lock:
                return db_instance.get_paginated_alarms(
                    show_resolved=show_resolved,
                    page=page,
                    page_size=page_size
                )
        
        alarms_data = db_operation_with_retry(get_alarms_data)
        
        # Alarm verilerini işle
        processed_alarms = []
        for alarm in alarms_data['alarms']:
            processed_alarm = process_alarm_data(alarm)
            if processed_alarm:  # Sadece geçerli alarmları ekle
                processed_alarms.append(processed_alarm)
        
        return jsonify({
            'success': True,
            'alarms': processed_alarms,
            'totalCount': alarms_data['totalCount'],
            'totalPages': alarms_data['totalPages'],
            'currentPage': alarms_data['currentPage']
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500

@app.route('/api/alarm-history', methods=['GET'])
def get_alarm_history():
    """Alarm geçmişini getir (sadece çözülmüş alarmlar)"""
    try:
        # Query parametrelerini al
        page = int(request.args.get('page', 1))
        page_size = int(request.args.get('pageSize', 50))
        
        # Veritabanından sadece çözülmüş alarmları oku
        def get_alarm_history_data():
            db_instance = get_db()
            with db_read_lock:
                return db_instance.get_paginated_alarms(
                    show_resolved=True,  # Sadece çözülmüş alarmlar
                    page=page,
                    page_size=page_size
                )
        
        alarms_data = db_operation_with_retry(get_alarm_history_data)
        
        # Alarm verilerini işle
        processed_alarms = []
        for alarm in alarms_data['alarms']:
            processed_alarm = process_alarm_data(alarm)
            if processed_alarm:  # Sadece geçerli alarmları ekle
                processed_alarms.append(processed_alarm)
        
        return jsonify({
            'success': True,
            'alarms': processed_alarms,
            'totalCount': alarms_data['totalCount'],
            'totalPages': alarms_data['totalPages'],
            'currentPage': alarms_data['currentPage']
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500

@app.route('/api/summary', methods=['GET'])
def get_summary():
    """Özet sayfası için veri getir"""
    try:
        # Veritabanından özet verileri oku
        db_instance = get_db()
        with db_read_lock:
            summary_data = db_instance.get_summary_data()
        
        return jsonify({
            'success': True,
            'summary': summary_data
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500

# Mail Yönetimi API'leri
@app.route('/api/mail-recipients', methods=['GET'])
def get_mail_recipients():
    """Mail alıcılarını getir"""
    try:
        db_instance = get_db()
        with db_read_lock:
            recipients = db_instance.get_mail_recipients()
        
        return jsonify({
            'success': True,
            'recipients': recipients
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500

@app.route('/api/mail-recipients', methods=['POST'])
def add_mail_recipient():
    """Yeni mail alıcısı ekle"""
    try:
        data = request.get_json()
        name = data.get('name', '').strip()
        email = data.get('email', '').strip()
        
        if not name or not email:
            return jsonify({
                'success': False,
                'message': 'Ad soyad ve email adresi gereklidir'
            }), 400
        
        db_instance = get_db()
        with db_lock:
            result = db_instance.add_mail_recipient(name, email)
        
        return jsonify(result)
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500

@app.route('/api/mail-recipients', methods=['PUT'])
def update_mail_recipient():
    """Mail alıcısını güncelle"""
    try:
        data = request.get_json()
        recipient_id = data.get('id')
        name = data.get('name', '').strip()
        email = data.get('email', '').strip()
        
        if not recipient_id or not name or not email:
            return jsonify({
                'success': False,
                'message': 'ID, ad soyad ve email adresi gereklidir'
            }), 400
        
        db_instance = get_db()
        with db_lock:
            result = db_instance.update_mail_recipient(recipient_id, name, email)
        
        return jsonify(result)
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500

@app.route('/api/mail-recipients/<int:recipient_id>', methods=['DELETE'])
def delete_mail_recipient(recipient_id):
    """Mail alıcısını sil"""
    try:
        db_instance = get_db()
        with db_lock:
            result = db_instance.delete_mail_recipient(recipient_id)
        
        return jsonify(result)
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500

def process_alarm_data(alarm):
    """Alarm verisini işle ve açıklama oluştur"""
    try:
        arm = alarm[1]  # arm
        battery = alarm[2]  # battery (k değeri)
        error_msb = alarm[3]  # error_code_msb
        error_lsb = alarm[4]  # error_code_lsb
        timestamp = alarm[5]  # timestamp
        status = alarm[6]  # status
        resolved_at = alarm[7] if len(alarm) > 7 else None  # resolved_at
        
        # Ortak alarm kontrol fonksiyonunu kullan
        if not is_valid_alarm(error_msb, error_lsb):
            print(f"⚠️ Geçersiz alarm filtrelendi: arm={arm}, battery={battery}, MSB={error_msb}, LSB={error_lsb}")
            return None
        
        alarm_type = get_alarm_type(error_msb, error_lsb)
        
        if alarm_type == 'arm':  # Kol alarmı
            description = get_arm_alarm_description(error_msb)
            battery_display = "Kol Alarmı"
            battery_key = 0  # JavaScript için kol alarmı key'i
        else:  # Batarya alarmı
            description = get_battery_alarm_description(error_msb, error_lsb)
            # Batarya alarmlarında k değeri varsa göster (2 eksik), yoksa boş bırak
            if battery == 0:
                battery_display = ""
                battery_key = 0
            else:
                battery_display = str(battery - 2)  # k değerinden 2 çıkar (ekranda gösterilecek)
                battery_key = battery  # Orijinal k değeri (JavaScript için)
        
        return {
            'arm': arm,
            'battery': battery_key,  # JavaScript için orijinal k değeri
            'batteryDisplay': battery_display,  # Ekranda gösterilecek değer
            'description': description,
            'status': "Devam Ediyor",
            'timestamp': timestamp,
            'resolved_at': resolved_at
        }
    except Exception as e:
        print(f"Alarm verisi işlenirken hata: {e}")
        return None

def get_battery_alarm_description(error_msb, error_lsb):
    """Batarya alarm açıklaması oluştur"""
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

def get_arm_alarm_description(error_msb):
    """Kol alarm açıklaması oluştur"""
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

def is_valid_alarm(error_msb, error_lsb):
    """Alarm geçerli mi kontrol et - process_alarm_data ile aynı mantık"""
    if error_lsb == 9:  # Kol alarmı
        return get_arm_alarm_description(error_msb) is not None
    else:  # Batarya alarmı
        return get_battery_alarm_description(error_msb, error_lsb) is not None

def get_alarm_type(error_msb, error_lsb):
    """Alarm türünü döndür - 'arm' veya 'battery'"""
    if error_lsb == 9:
        return 'arm'
    else:
        return 'battery'

@app.route('/api/send-config-to-device', methods=['POST'])
@admin_required
def send_config_to_device():
    """Konfigürasyonu cihaza gönder"""
    try:
        data = request.get_json()
        command = data.get('command', '5 5 0x7A')
        
        # Konfigürasyonu JSON dosyasına kaydet (main.py için)
        config_data = {
            'type': 'send_to_device',
            'command': command,
            'timestamp': int(time.time() * 1000)
        }
        
        try:
            with open('pending_config.json', 'w', encoding='utf-8') as f:
                json.dump(config_data, f, indent=2, ensure_ascii=False)
            print(f"Konfigürasyon cihaza gönderilecek: {command}")
        except Exception as e:
            print(f"Konfigürasyon dosyaya kaydedilirken hata: {e}")
            return jsonify({
                'success': False,
                'message': 'Konfigürasyon kaydedilemedi'
            }), 500
        
        return jsonify({
            'success': True,
            'message': f'Konfigürasyon cihaza gönderildi: {command}',
            'command': command
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500

@app.route('/api/mail-server-config', methods=['GET'])
def get_mail_server_config():
    """Mail sunucu konfigürasyonunu getir"""
    try:
        def get_config():
            db_instance = get_db()
            with db_read_lock:
                return db_instance.get_mail_server_config()
        
        config = db_operation_with_retry(get_config)
        
        return jsonify({
            'success': True,
            'config': config
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500

@app.route('/api/mail-server-config', methods=['POST'])
@admin_required
def save_mail_server_config():
    """Mail sunucu konfigürasyonunu kaydet"""
    try:
        data = request.get_json()
        
        # Gerekli alanları kontrol et
        required_fields = ['smtp_server', 'smtp_port']
        for field in required_fields:
            if field not in data or not data[field]:
                return jsonify({
                    'success': False,
                    'message': f'{field} alanı zorunludur'
                }), 400
        
        def save_config():
            db_instance = get_db()
            with db_lock:
                return db_instance.save_mail_server_config(
                    smtp_server=data['smtp_server'],
                    smtp_port=int(data['smtp_port']),
                    smtp_username=data.get('smtp_username', ''),
                    smtp_password=data.get('smtp_password', ''),
                    use_tls=data.get('use_tls', True),
                    is_active=data.get('is_active', True)
                )
        
        success = db_operation_with_retry(save_config)
        
        if success:
            return jsonify({
                'success': True,
                'message': 'Mail sunucu konfigürasyonu başarıyla kaydedildi'
            })
        else:
            return jsonify({
                'success': False,
                'message': 'Mail sunucu konfigürasyonu kaydedilemedi'
            }), 500
            
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500

@app.route('/api/test-mail-connection', methods=['POST'])
@admin_required
def test_mail_connection():
    """Mail sunucu bağlantısını test et"""
    try:
        data = request.get_json()
        
        # SMTP bağlantı testi
        import smtplib
        from email.mime.text import MIMEText
        
        smtp_server = data.get('smtp_server')
        smtp_port = data.get('smtp_port')
        smtp_username = data.get('smtp_username')
        smtp_password = data.get('smtp_password')
        use_tls = data.get('use_tls', True)
        
        if not smtp_server or not smtp_port:
            return jsonify({'success': False, 'message': 'SMTP sunucu adresi ve port gerekli'})
        
        # SMTP bağlantısını test et
        try:
            if use_tls:
                server = smtplib.SMTP(smtp_server, smtp_port)
                server.starttls()
            else:
                server = smtplib.SMTP(smtp_server, smtp_port)
            
            if smtp_username and smtp_password:
                server.login(smtp_username, smtp_password)
            
            server.quit()
            
            return jsonify({'success': True, 'message': 'SMTP bağlantısı başarılı'})
            
        except smtplib.SMTPAuthenticationError:
            return jsonify({'success': False, 'message': 'Kullanıcı adı veya şifre hatalı'})
        except smtplib.SMTPConnectError:
            return jsonify({'success': False, 'message': 'SMTP sunucusuna bağlanılamadı'})
        except smtplib.SMTPException as e:
            return jsonify({'success': False, 'message': f'SMTP hatası: {str(e)}'})
        except Exception as e:
            return jsonify({'success': False, 'message': f'Bağlantı hatası: {str(e)}'})
    
    except Exception as e:
        return jsonify({'success': False, 'message': f'Test hatası: {str(e)}'})

@app.route('/api/current-ip', methods=['GET'])
def get_current_ip():
    """Mevcut IP adresini getir - NetworkManager'dan aktif IP'yi al"""
    try:
        import subprocess
        
        # Önce NetworkManager'dan aktif IP'yi al
        result = subprocess.run(['sudo', 'nmcli', 'device', 'show', 'eth0'], capture_output=True, text=True)
        if result.returncode == 0:
            for line in result.stdout.split('\n'):
                if 'IP4.ADDRESS[1]:' in line:
                    ip = line.split(':')[1].strip().split('/')[0]
                    return jsonify({
                        'success': True,
                        'ip': ip
                    })
        
        # NetworkManager'dan alınamazsa hostname -I kullan
        result = subprocess.run(['hostname', '-I'], capture_output=True, text=True)
        if result.returncode == 0:
            ips = result.stdout.strip().split()
            # Sadece IPv4 adreslerini al (IPv6'ları filtrele)
            ipv4_ips = []
            for ip in ips:
                if '.' in ip and ':' not in ip:  # IPv4 kontrolü
                    ipv4_ips.append(ip)
            
            if ipv4_ips:
                current_ip = ipv4_ips[0]  # İlk IPv4 adresini al
            else:
                current_ip = 'IP Bulunamadı'
        else:
            current_ip = 'Komut Hatası'
        
        return jsonify({
            'success': True,
            'ip': current_ip
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'ip': 'Hata'
        }), 500

@app.route('/api/all-ips', methods=['GET'])
def get_all_ips():
    """Tüm IP adreslerini getir"""
    try:
        import subprocess
        
        # hostname -I ile tüm IP'leri al
        result = subprocess.run(['hostname', '-I'], capture_output=True, text=True)
        if result.returncode == 0:
            all_ips = result.stdout.strip().split()
            # IPv4 ve IPv6'ları ayır
            ipv4_ips = []
            ipv6_ips = []
            
            for ip in all_ips:
                if '.' in ip and ':' not in ip:  # IPv4
                    ipv4_ips.append(ip)
                elif ':' in ip:  # IPv6
                    ipv6_ips.append(ip)
            
            return jsonify({
                'success': True,
                'all_ips': all_ips,
                'ipv4_ips': ipv4_ips,
                'ipv6_ips': ipv6_ips,
                'count': len(all_ips)
            })
        else:
            return jsonify({
                'success': False,
                'message': 'IP adresleri alınamadı'
            }), 500
            
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Hata: {str(e)}'
        }), 500

@app.route('/api/ip-config', methods=['GET'])
def get_ip_config():
    """IP konfigürasyonunu getir"""
    try:
        def get_config():
            db_instance = get_db()
            with db_read_lock:
                return db_instance.get_ip_config()
        
        config = db_operation_with_retry(get_config)
        
        return jsonify({
            'success': True,
            'config': config
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500

@app.route('/api/ip-config', methods=['POST'])
@admin_required
def save_ip_config():
    """IP konfigürasyonunu kaydet"""
    try:
        data = request.get_json()
        
        # IP method kontrolü
        use_dhcp = data.get('use_dhcp', False)
        
        if not use_dhcp:
            # Statik IP için gerekli alanları kontrol et
            required_fields = ['ip_address']
            for field in required_fields:
                if field not in data or not data[field]:
                    return jsonify({
                        'success': False,
                        'message': f'{field} alanı zorunludur'
                    }), 400
        
        def save_config():
            db_instance = get_db()
            with db_lock:
                if use_dhcp:
                    return db_instance.save_ip_config(
                        ip_address=None,
                        subnet_mask=None,
                        gateway=None,
                        dns_servers=None,
                        is_assigned=True,
                        is_active=True,
                        use_dhcp=True
                    )
                else:
                    return db_instance.save_ip_config(
                        ip_address=data['ip_address'],
                        subnet_mask=data.get('subnet_mask', '255.255.255.0'),
                        gateway=data.get('gateway', ''),
                        dns_servers=data.get('dns_servers', '8.8.8.8,8.8.4.4'),
                        is_assigned=True,
                        is_active=True,
                        use_dhcp=False
                    )
        
        success = db_operation_with_retry(save_config)
        
        if success:
            # IP ataması yap
            try:
                from ip_manager import IPManager
                ip_manager = IPManager()
                
                # IP konfigürasyonunu güncelle
                if use_dhcp:
                    update_success = ip_manager.update_ip_config(use_dhcp=True)
                else:
                    update_success = ip_manager.update_ip_config(
                        ip_address=data['ip_address'],
                        subnet_mask=data.get('subnet_mask', '255.255.255.0'),
                        gateway=data.get('gateway', ''),
                        dns_servers=data.get('dns_servers', '8.8.8.8,8.8.4.4'),
                        use_dhcp=False
                    )
                
                if update_success:
                    return jsonify({
                        'success': True,
                        'message': 'IP konfigürasyonu başarıyla kaydedildi ve uygulandı'
                    })
                else:
                    return jsonify({
                        'success': False,
                        'message': 'IP ataması başarısız. Manuel olarak yeniden başlatma gerekebilir.'
                    }), 500
                    
            except Exception as e:
                return jsonify({
                    'success': False,
                    'message': f'IP ataması hatası: {str(e)}. Manuel olarak yeniden başlatma gerekebilir.'
                }), 500
        else:
            return jsonify({
                'success': False,
                'message': 'IP konfigürasyonu kaydedilemedi'
            }), 500
            
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'IP konfigürasyonu kaydedilirken hata: {str(e)}'
        }), 500

@app.route('/api/send-manual-set-command', methods=['POST'])
def send_manual_set_command():
    """Manuel kol set komutu gönder (0x81 0xkol_no 0x78)"""
    try:
        data = request.get_json()
        arm = data.get('arm')
        slave_str = data.get('slave', '0')  # String olarak al
        
        # String'i decimal olarak parse et (14 -> 14)
        try:
            slave = int(slave_str)
        except ValueError:
            slave = 0
        
        if not arm or arm < 1 or arm > 4:
            return jsonify({
                'success': False,
                'message': 'Geçersiz kol numarası (1-4 arası olmalı)'
            }), 400
        
        if slave < 0 or slave > 255:
            return jsonify({
                'success': False,
                'message': 'Geçersiz batarya adresi (0-255 arası olmalı)'
            }), 400
        
        # Manuel set komutu: 0x81 0xkol_no 0xslave 0x78
        manual_set_command = [0x81, arm, slave, 0x78]
        
        # UART gönderimi için main.py'deki mevcut sistemi kullan
        try:
            # pending_config.json dosyasına komutu yaz
            import json
            import os
            
            config_data = {
                "type": "manual_set",
                "arm": arm,
                "slave": slave,
                "command": manual_set_command,
                "timestamp": time.time()
            }
            
            with open("pending_config.json", "w") as f:
                json.dump(config_data, f)
            
            
            return jsonify({
                'success': True,
                'message': f'Kol {arm} manuel set komutu gönderildi'
            })
                
        except Exception as e:
            return jsonify({
                'success': False,
                'message': f'Manuel set komutu gönderilirken hata: {str(e)}'
            }), 500
            
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500

# ==============================================
# TRAP SETTINGS ROUTES
# ==============================================

@app.route('/trap-settings')
@login_required
def trap_settings():
    """Trap ayarları sayfası"""
    return render_template('pages/trap-settings.html')

@app.route('/api/trap-targets', methods=['GET'])
def get_trap_targets():
    """Trap hedeflerini getir"""
    try:
        db = get_db()
        targets = db_operation_with_retry(lambda: db.get_trap_targets())
        return jsonify({
            'success': True,
            'data': targets
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500

@app.route('/api/trap-targets', methods=['POST'])
def add_trap_target():
    """Yeni trap hedefi ekle"""
    try:
        data = request.get_json()
        name = data.get('name')
        ip_address = data.get('ip_address')
        port = data.get('port', 162)
        
        if not name or not ip_address:
            return jsonify({
                'success': False,
                'message': 'Name ve IP address gerekli'
            }), 400
        
        db = get_db()
        result = db_operation_with_retry(lambda: db.add_trap_target(name, ip_address, port))
        
        return jsonify(result)
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500

@app.route('/api/trap-targets/<int:target_id>', methods=['PUT'])
def update_trap_target(target_id):
    """Trap hedefini güncelle"""
    try:
        data = request.get_json()
        name = data.get('name')
        ip_address = data.get('ip_address')
        port = data.get('port', 162)
        
        if not name or not ip_address:
            return jsonify({
                'success': False,
                'message': 'Name ve IP address gerekli'
            }), 400
        
        db = get_db()
        result = db_operation_with_retry(lambda: db.update_trap_target(target_id, name, ip_address, port))
        
        return jsonify(result)
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500

@app.route('/api/trap-targets/<int:target_id>', methods=['DELETE'])
def delete_trap_target(target_id):
    """Trap hedefini sil"""
    try:
        db = get_db()
        result = db_operation_with_retry(lambda: db.delete_trap_target(target_id))
        
        return jsonify(result)
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500

@app.route('/api/trap-targets/<int:target_id>/toggle', methods=['POST'])
def toggle_trap_target(target_id):
    """Trap hedefini aktif/pasif yap"""
    try:
        db = get_db()
        result = db_operation_with_retry(lambda: db.toggle_trap_target(target_id))
        
        return jsonify(result)
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500

# Trap Settings API'leri
@app.route('/api/trap-settings', methods=['GET'])
def get_trap_settings():
    """Trap ayarlarını getir"""
    try:
        db = get_db()
        settings = db_operation_with_retry(lambda: db.get_trap_settings())
        
        return jsonify({
            'success': True,
            'settings': settings
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500

@app.route('/api/trap-settings', methods=['POST'])
def save_trap_settings():
    """Trap ayarlarını kaydet"""
    try:
        data = request.get_json()
        print(f"📥 Trap ayarları POST isteği alındı: {data}")
        db = get_db()
        
        # Parametreleri al
        trap_enabled = data.get('trapEnabled', False)
        trap_server = data.get('trapServer', '')
        trap_port = data.get('trapPort', 162)
        trap_community = data.get('trapCommunity', 'public')
        trap_version = data.get('trapVersion', '2c')
        trap_interval = data.get('trapInterval', 30)
        
        print(f"📊 Trap ayarları parametreleri: enabled={trap_enabled}, server={trap_server}, port={trap_port}, community={trap_community}, version={trap_version}, interval={trap_interval}")
        
        result = db_operation_with_retry(lambda: db.save_trap_settings(
            trap_enabled, trap_server, trap_port, trap_community, trap_version, trap_interval
        ))
        
        print(f"✅ Trap ayarları kayıt sonucu: {result}")
        return jsonify(result)
    except Exception as e:
        print(f"❌ Trap ayarları kaydedilirken hata: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500

@app.route('/api/trap-settings/test', methods=['POST'])
def send_test_trap():
    """Test trap gönder"""
    try:
        db = get_db()
        result = db_operation_with_retry(lambda: db.send_test_trap())
        
        return jsonify(result)
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500

@app.route('/api/trap-settings/history', methods=['GET'])
def get_trap_history():
    """Trap geçmişini getir"""
    try:
        page = int(request.args.get('page', 1))
        page_size = int(request.args.get('pageSize', 50))
        
        db = get_db()
        history = db_operation_with_retry(lambda: db.get_trap_history(page, page_size))
        
        return jsonify({
            'success': True,
            'history': history
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500

@app.route('/api/trap-settings/stats', methods=['GET'])
def get_trap_stats():
    """Trap istatistiklerini getir"""
    try:
        db = get_db()
        stats = db_operation_with_retry(lambda: db.get_trap_stats())
        
        return jsonify({
            'success': True,
            'stats': stats
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500

# ========================================
# FTP AYARLARI API ENDPOINT'LERİ
# ========================================

@app.route('/ftp-settings')
@login_required
def ftp_settings():
    """FTP ayarları sayfası"""
    return render_template('pages/ftp-settings.html')

@app.route('/api/ftp-config', methods=['GET'])
@login_required
def get_ftp_config():
    """FTP konfigürasyonunu getir"""
    try:
        db = get_db()
        config = db_operation_with_retry(lambda: db.get_ftp_config())
        
        # Şifreyi frontend'e gönderme, sadece varlığını belirt
        if config and config.get('ftp_password'):
            config['ftp_password'] = '********'
        
        return jsonify({
            'success': True,
            'config': config
        })
    except Exception as e:
        print(f"FTP config getirme hatası: {e}")
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500

@app.route('/api/ftp-config', methods=['POST'])
@login_required
def save_ftp_config():
    """FTP konfigürasyonunu kaydet"""
    try:
        data = request.get_json()
        ftp_host = data.get('ftp_host')
        ftp_port = data.get('ftp_port', 21)
        ftp_username = data.get('ftp_username')
        ftp_password = data.get('ftp_password')
        is_active = data.get('is_active', False)
        
        if not ftp_host or not ftp_username:
            return jsonify({
                'success': False,
                'message': 'FTP sunucu adresi ve kullanıcı adı gerekli'
            }), 400
        
        # Şifre girilmemişse mevcut şifreyi koru
        db = get_db()
        if not ftp_password:
            existing_config = db_operation_with_retry(lambda: db.get_ftp_config())
            if existing_config:
                ftp_password = existing_config.get('ftp_password')
        
        result = db_operation_with_retry(lambda: db.save_ftp_config(
            ftp_host, ftp_port, ftp_username, ftp_password, is_active
        ))
        
        return jsonify(result)
    except Exception as e:
        print(f"FTP config kaydetme hatası: {e}")
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500

@app.route('/api/ftp-test', methods=['POST'])
@login_required
def test_ftp_connection():
    """SFTP bağlantısını test et"""
    try:
        import paramiko
        
        data = request.get_json()
        sftp_host = data.get('ftp_host')
        sftp_port = data.get('ftp_port', 22)  # SFTP default port 22
        sftp_username = data.get('ftp_username')
        sftp_password = data.get('ftp_password')
        
        # Base64 decode (eğer veritabanından geliyorsa)
        import base64
        try:
            if sftp_password:
                sftp_password = base64.b64decode(sftp_password.encode()).decode()
        except Exception as e:
            print(f"⚠️ Şifre decode hatası: {e}")
            pass  # Zaten düz metin
        
        # SFTP bağlantısı test et
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(
            hostname=sftp_host,
            port=sftp_port,
            username=sftp_username,
            password=sftp_password,
            timeout=10
        )
        ssh.close()
        
        return jsonify({
            'success': True,
            'message': 'SFTP bağlantısı başarılı'
        })
    except Exception as e:
        print(f"SFTP test hatası: {e}")
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500

@app.route('/api/ftp-send-now', methods=['POST'])
@login_required
def send_database_now():
    """Veritabanını şimdi SFTP'ye gönder"""
    try:
        import subprocess
        import pwd
        
        # Gerçek kullanıcı adını al (sudo ile çalışsa bile)
        real_user = os.environ.get('SUDO_USER') or os.environ.get('USER') or 'bms'
        user_home = pwd.getpwnam(real_user).pw_dir
        script_path = os.path.join(user_home, 'Desktop', 'Monitoring_Raspberry', 'ftp_backup.py')
        
        print(f"🚀 SFTP gönderimi başlatılıyor: {script_path}")
        
        # SFTP gönderim script'ini çalıştır
        result = subprocess.run(
            ['python3', script_path],
            capture_output=True,
            text=True,
            timeout=60
        )
        
        print(f"📤 SFTP script çıktısı:\n{result.stdout}")
        print(f"📤 SFTP script stderr:\n{result.stderr}")
        print(f"📤 Return code: {result.returncode}")
        
        if result.returncode == 0:
            return jsonify({
                'success': True,
                'message': 'Veritabanı başarıyla gönderildi'
            })
        else:
            print(f"❌ SFTP hatası:\n{result.stderr}")
            error_msg = result.stderr.strip() if result.stderr else result.stdout.strip()
            if not error_msg:
                error_msg = f"Script başarısız oldu (exit code: {result.returncode})"
            return jsonify({
                'success': False,
                'message': f'Gönderim hatası: {error_msg}'
            }), 500
    except Exception as e:
        print(f"❌ SFTP gönderim hatası: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500

# ========================================
# VERİ ALMA API ENDPOINT'LERİ
# ========================================

@app.route('/api/commands', methods=['POST'])
@login_required
def send_command():
    """Komut gönder (readAll, resetAll)"""
    try:
        data = request.get_json()
        command = data.get('command')
        arm = data.get('arm')
        
        if not command or arm is None:
            return jsonify({'success': False, 'message': 'Eksik parametreler'}), 400
        
        # Komut paketini hazırla
        if command == 'readAll':
            if arm == 5:  # Tüm kollar
                command_packet = [0x81, 5, 0x7A]  # 0x81 0x05 0x7A
            else:  # Belirli kol
                command_packet = [0x81, arm, 0x7A]  # 0x81 0xkol 0x7A
        elif command == 'resetAll':
            if arm == 5:  # Tüm kollar
                command_packet = [0x81, 5, 0x79]  # 0x81 0x05 0x79
            else:  # Belirli kol
                command_packet = [0x81, arm, 0x79]  # 0x81 0xkol 0x79
        else:
            return jsonify({'success': False, 'message': 'Geçersiz komut'}), 400
        
        # pending_config.json dosyasına komutu yaz
        config_data = {
            'type': 'command',
            'command': command,
            'arm': arm,
            'packet': command_packet,
            'timestamp': int(time.time() * 1000)
        }
        
        with open('pending_config.json', 'w', encoding='utf-8') as f:
            json.dump(config_data, f, indent=2, ensure_ascii=False)
        
        
        return jsonify({
            'success': True, 
            'message': f'{command} komutu başarıyla gönderildi',
            'packet': [hex(x) for x in command_packet]
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': 'Komut gönderilemedi'}), 500

@app.route('/api/datagets', methods=['POST'])
@login_required
def send_dataget():
    """Veri alma komutu gönder"""
    try:
        data = request.get_json()
        arm_value = data.get('armValue')
        slave_address = data.get('slaveAddress')
        slave_command = data.get('slaveCommand')
        
        if arm_value is None or slave_address is None or slave_command is None:
            return jsonify({'success': False, 'message': 'Eksik parametreler'}), 400
        
        # Veri alma paketini hazırla: 3 byte (arm, slave+1, command)
        dataget_packet = [arm_value, slave_address + 1, slave_command]
        
        # pending_config.json dosyasına komutu yaz
        config_data = {
            'type': 'dataget',
            'armValue': arm_value,
            'slaveAddress': slave_address,
            'slaveCommand': slave_command,
            'packet': dataget_packet,
            'timestamp': int(time.time() * 1000)
        }
        
        with open('pending_config.json', 'w', encoding='utf-8') as f:
            json.dump(config_data, f, indent=2, ensure_ascii=False)
        
        
        return jsonify({
            'success': True, 
            'message': 'Veri alma komutu başarıyla gönderildi',
            'packet': [hex(x) for x in dataget_packet]
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': 'Veri alma komutu gönderilemedi'}), 500

@app.route('/api/start-data-retrieval', methods=['POST'])
@login_required
def start_data_retrieval():
    """Veri alma modunu başlat"""
    try:
        data = request.get_json()
        arm = data.get('arm')
        address = data.get('address')
        value = data.get('value')
        value_text = data.get('valueText')
        
        if arm is None or address is None or value is None or value_text is None:
            return jsonify({'success': False, 'message': 'Eksik parametreler'}), 400
        
        # Veri alma modunu başlat
        config = {
            'arm': arm,
            'address': address,
            'value': value,
            'valueText': value_text
        }
        
        # main.py'ye JSON dosyası üzerinden iletişim kur (import etmeden)
        try:
            config_file = "pending_config.json"
            config_data = {
                'type': 'data_retrieval_start',
                'config': config
            }
            with open(config_file, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, indent=2, ensure_ascii=False)
            print(f"✓ Veri alma modu başlatma isteği JSON dosyasına yazıldı: {config_file}")
        except Exception as je:
            raise Exception(f"JSON dosyası yazılırken hata: {str(je)}")
        
        # Web app tarafında da periyot başlangıcını kaydet
        global data_retrieval_period_start
        data_retrieval_period_start = int(time.time() * 1000)  # Milisaniye
        
        return jsonify({
            'success': True,
            'message': 'Veri alma modu başlatıldı',
            'config': config
        })
        
    except Exception as e:
        print(f"❌ Veri alma modu başlatma hatası: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'message': f'Veri alma modu başlatılamadı: {str(e)}'}), 500

@app.route('/api/stop-data-retrieval', methods=['POST'])
@login_required
def stop_data_retrieval():
    """Veri alma modunu durdur"""
    try:
        # main.py'ye JSON dosyası üzerinden iletişim kur (import etmeden)
        config_file = "pending_config.json"
        config_data = {
            'type': 'data_retrieval_stop'
        }
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(config_data, f, indent=2, ensure_ascii=False)
        print(f"✓ Veri alma modu durdurma isteği JSON dosyasına yazıldı: {config_file}")
        
        # Web app tarafında periyot başlangıcını temizle
        global data_retrieval_period_start
        data_retrieval_period_start = None
        
        return jsonify({
            'success': True,
            'message': 'Veri alma modu durduruldu'
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': 'Veri alma modu durdurulamadı'}), 500

@app.route('/api/get-retrieved-data', methods=['GET'])
@login_required
def get_retrieved_data():
    """Yakalanan verileri al"""
    try:
        # Web app'teki timestamp'ı kullan
        global data_retrieval_period_start
        start_timestamp = data_retrieval_period_start
        if not start_timestamp:
            return jsonify({'success': True, 'data': []})
        
        # Veritabanından timestamp'a göre veri çek
        db = get_db()
        with db_read_lock:
            # Timestamp'ı milisaniye cinsinden kullan (veritabanındaki format)
            # Önce toplam veri sayısını kontrol et
            count_query = "SELECT COUNT(*) FROM battery_data"
            count_cursor = db.execute_query(count_query)
            total_count = count_cursor.fetchone()[0]
            
            # Bu tarihten sonraki verileri al (gruplama ile) - sadece batarya verileri (k > 2)
            query = """
                SELECT 
                    timestamp,
                    arm,
                    (k - 2) as address,
                    MAX(CASE WHEN dtype = 10 THEN data END) as voltage,
                    MAX(CASE WHEN dtype = 11 THEN data END) as health_status,
                    MAX(CASE WHEN dtype = 12 THEN data END) as temperature,
                    MAX(CASE WHEN dtype = 13 THEN data END) as positive_pole_temp,
                    MAX(CASE WHEN dtype = 14 THEN data END) as negative_pole_temp,
                    MAX(CASE WHEN dtype = 15 THEN data END) as ntc3_temp,
                    MAX(CASE WHEN dtype = 126 THEN data END) as charge_status
                FROM battery_data 
                WHERE timestamp >= ? AND k > 2
                GROUP BY timestamp, arm, k
                ORDER BY timestamp ASC, arm ASC, k ASC
            """
            
            # SQL sorgusu logları kaldırıldı
            
            data_cursor = db.execute_query(query, (start_timestamp,))
            data = data_cursor.fetchall()
            
            # Verileri formatla (gruplama ile)
            retrieved_data = []
            for row in data:
                # Timestamp'ı çevir
                timestamp_ms = row[0]
                timestamp_dt = datetime.fromtimestamp(timestamp_ms / 1000)
                formatted_time = timestamp_dt.strftime("%Y-%m-%d %H:%M:%S")
                
                # Veri satırı oluştur
                data_row = {
                    'timestamp': formatted_time,
                    'arm': row[1],
                    'address': row[2],
                    'voltage': row[3],
                    'health_status': row[4],
                    'temperature': row[5],
                    'positive_pole_temp': row[6],
                    'negative_pole_temp': row[7],
                    'ntc3_temp': row[8],
                    'charge_status': row[9]
                }
                retrieved_data.append(data_row)
            
            return jsonify({
                'success': True,
                'data': retrieved_data
            })
            
    except Exception as e:
        return jsonify({'success': False, 'message': 'Veriler alınamadı'}), 500

@app.route('/api/data-retrieval-status', methods=['GET'])
@login_required
def get_data_retrieval_status():
    """Veri alma modu durumunu kontrol et"""
    try:
        # JSON dosyasından doğrudan oku (import main etmeden)
        status_file = 'data_retrieval_status.json'
        is_active = False
        
        if os.path.exists(status_file):
            try:
                with open(status_file, 'r', encoding='utf-8') as f:
                    status = json.load(f)
                    is_active = status.get('data_retrieval_mode', False)
            except Exception as e:
                print(f"⚠️ JSON dosyası okunurken hata: {e}")
                is_active = False
        
        return jsonify({
            'success': True,
            'is_active': is_active
        })
        
    except Exception as e:
        print(f"❌ Veri alma durumu kontrol hatası: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'message': f'Durum kontrol edilemedi: {str(e)}'}), 500

if __name__ == '__main__':
    import sys
    
    # IP ataması kontrolü - Manuel yapılacak, otomatik atama devre dışı
    # try:
    #     from ip_manager import IPManager
    #     ip_manager = IPManager()
    #     ip_manager.initialize_default_ip()
    # except Exception as e:
    #     # IP ataması kontrol hatası
    #     pass
    
    # Port parametresini al (varsayılan: 80)
    port = 80
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            # Geçersiz port numarası, varsayılan port 80 kullanılıyor
            pass
    
    try:
        # Flask logging'i tamamen devre dışı bırak
        import logging
        import sys
        
        # Werkzeug logger'ı kapat
        werkzeug_logger = logging.getLogger('werkzeug')
        werkzeug_logger.setLevel(logging.ERROR)
        werkzeug_logger.disabled = True
        
        # Flask logger'ı kapat
        flask_logger = logging.getLogger('flask')
        flask_logger.setLevel(logging.ERROR)
        flask_logger.disabled = True
        
        # stdout'u geçici olarak kapat
        original_stdout = sys.stdout
        sys.stdout = open('/dev/null', 'w')
        
        try:
            app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
        finally:
            # stdout'u geri aç
            sys.stdout.close()
            sys.stdout = original_stdout
    except OSError as e:
        if "Address already in use" in str(e):
            # Port zaten kullanımda
            pass
        else:
            # Hata oluştu
            pass
