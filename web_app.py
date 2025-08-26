from flask import Flask, render_template, jsonify, request
from database import BatteryDatabase
import threading
import time
from datetime import datetime, timedelta

app = Flask(__name__)
db = BatteryDatabase()

# Otomatik temizlik thread'i
def cleanup_thread():
    while True:
        try:
            db.cleanup_old_data(days=7)  # 7 günlük veriyi tut
            time.sleep(3600)  # Her saat temizlik
        except Exception as e:
            print(f"Temizlik hatası: {e}")
            time.sleep(3600)

# Temizlik thread'ini başlat
cleanup_thread = threading.Thread(target=cleanup_thread, daemon=True)
cleanup_thread.start()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/recent_data')
def get_recent_data():
    """Son 5 dakikanın verilerini getir (tarih seçimi yapılmadığında)"""
    arm = request.args.get('arm', type=int)
    dtype = request.args.get('dtype', type=int)
    minutes = request.args.get('minutes', 5, type=int)
    limit = request.args.get('limit', 50, type=int)
    
    data = db.get_recent_data(minutes, arm, dtype, limit)
    return jsonify(data)

@app.route('/api/data_by_date')
def get_data_by_date():
    """Tarih aralığına göre veri getir (sayfalama ile)"""
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    arm = request.args.get('arm', type=int)
    dtype = request.args.get('dtype', type=int)
    page = request.args.get('page', 1, type=int)
    page_size = request.args.get('page_size', 50, type=int)
    
    if not start_date or not end_date:
        return jsonify({'error': 'start_date ve end_date gerekli'}), 400
    
    result = db.get_data_by_date_range(start_date, end_date, arm, dtype, page, page_size)
    return jsonify(result)

@app.route('/api/latest_data')
def get_latest_data():
    arm = request.args.get('arm', type=int)
    dtype = request.args.get('dtype', type=int)
    limit = request.args.get('limit', 100, type=int)
    
    data = db.get_latest_data(arm, dtype, limit)
    return jsonify(data)

@app.route('/api/formatted_data')
def get_formatted_data():
    arm = request.args.get('arm', type=int)
    k = request.args.get('k', type=int)
    limit = request.args.get('limit', 100, type=int)
    
    data = db.get_formatted_data(arm, k, limit)
    return jsonify(data)

@app.route('/api/chart_data')
def get_chart_data():
    arm = request.args.get('arm', 1, type=int)
    dtype = request.args.get('dtype', 10, type=int)
    hours = request.args.get('hours', 24, type=int)
    
    # Son X saatlik veriyi al
    end_time = int(time.time() * 1000)
    start_time = end_time - (hours * 3600 * 1000)
    
    with db.lock:
        with sqlite3.connect(db.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT timestamp, data FROM battery_data 
                WHERE arm = ? AND dtype = ? AND timestamp BETWEEN ? AND ?
                ORDER BY timestamp ASC
            ''', (arm, dtype, start_time, end_time))
            
            data = cursor.fetchall()
    
    return jsonify(data)

@app.route('/api/stats')
def get_stats():
    """Veritabanı istatistikleri"""
    stats = db.get_stats()
    return jsonify(stats)

if __name__ == '__main__':
    print("Flask web uygulaması başlatılıyor...")
    print("Veritabanı boyutu:", round(db.get_database_size(), 2), "MB")
    app.run(host='127.0.0.1', port=5000, debug=False, threaded=True)