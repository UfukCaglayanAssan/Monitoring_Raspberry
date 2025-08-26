# interface/web_app.py
from flask import Flask, render_template, jsonify, request
from database import BatteryDatabase
import time

app = Flask(__name__)
db = BatteryDatabase()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/data_types')
def get_data_types():
    language = request.args.get('lang', 'tr')  # Varsayılan Türkçe
    data_types = db.get_data_types_by_language(language)
    return jsonify(data_types)

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
    
    data = db.get_recent_data_with_translations(
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
    
    # Bu fonksiyonu da database.py'ye ekleyelim
    data = db.get_data_by_date_range_with_translations(
        start_date, end_date, arm, dtype, language
    )
    return jsonify(data)

@app.route('/api/stats')
def get_stats():
    stats = db.get_stats()
    return jsonify(stats)

if __name__ == '__main__':
    print("Flask web uygulaması başlatılıyor...")
    print(f"Veritabanı boyutu: {db.get_database_size():.2f} MB")
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)