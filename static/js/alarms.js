// Alarms Sayfası JavaScript
// Class'ın zaten tanımlanıp tanımlanmadığını kontrol et
if (typeof window.AlarmsPage === 'undefined') {
    window.AlarmsPage = class AlarmsPage {
    constructor() {
        this.alarms = [];
        this.showResolved = false; // Varsayılan olarak sadece aktif alarmları göster
        this.currentPage = 1;
        this.pageSize = 50;
        this.totalPages = 1;
        this.isLoading = false; // Yükleme durumu flag'i
        this.eventsBound = false; // Event listener'ların bağlanıp bağlanmadığını kontrol et
        this.init();
    }

    init() {
        console.log('🔧 AlarmsPage init() başladı');
        this.bindEvents();
        
        // Sadece sayfa aktifse veri yükle
        if (this.isPageActive()) {
            this.loadAlarms(); // Hemen veri yükle
            this.startAutoRefresh(); // Otomatik yenileme başlat
        } else {
            console.log('⚠️ Sayfa aktif değil, init iptal edildi');
        }
    }

    // Her seferinde aktif alarmlara sıfırla
    resetToActiveAlarms() {
        this.showResolved = false; // Aktif alarmlar modu
        this.currentPage = 1; // Sayfa sıfırla
        this.loadAlarms();
        this.updateButtonText();
        
        // Alarm geçmişi container'ını gizle
        const alarmHistoryContainer = document.getElementById('alarmHistoryContainer');
        if (alarmHistoryContainer) {
            alarmHistoryContainer.style.display = 'none';
        }
    }

    bindEvents() {
        // Event listener'ları sadece bir kez ekle
        if (this.eventsBound) {
            console.log('⚠️ Event listener\'lar zaten bağlı, atlanıyor');
            return;
        }
        
        // Alarm geçmişi toggle butonu
        const toggleBtn = document.getElementById('toggleAlarmHistory');
        if (toggleBtn) {
            toggleBtn.addEventListener('click', () => {
                this.toggleAlarmHistory();
            });
        }

        // Sayfalama butonları
        document.getElementById('prevPage')?.addEventListener('click', () => {
            this.previousPage();
        });

        document.getElementById('nextPage')?.addEventListener('click', () => {
            this.nextPage();
        });
        
        this.eventsBound = true;
        console.log('✅ Event listener\'lar bağlandı');
    }

    // Alarm geçmişi toggle fonksiyonu
    toggleAlarmHistory() {
        const alarmHistoryContainer = document.getElementById('alarmHistoryContainer');
        const alarmsTable = document.getElementById('alarmsTable');
        const noDataMessage = document.getElementById('noDataMessage');
        const pagination = document.getElementById('pagination');
        
        if (alarmHistoryContainer && alarmsTable) {
            if (alarmHistoryContainer.style.display === 'none' || 
                alarmHistoryContainer.style.display === '') {
                // Alarm geçmişini göster
                alarmHistoryContainer.style.display = 'block';
                alarmsTable.style.display = 'none';
                if (noDataMessage) noDataMessage.style.display = 'none';
                if (pagination) pagination.style.display = 'none';
                this.showResolved = true; // Geçmiş moduna geç
                this.loadAlarmHistory(); // Alarm geçmişi için loadAlarmHistory() çağır
            } else {
                // Aktif alarmları göster
                alarmHistoryContainer.style.display = 'none';
                alarmsTable.style.display = 'table';
                this.showResolved = false; // Aktif moduna geç
                this.loadAlarms(); // Aktif alarmları yeniden yükle
            }
            this.updateButtonText(); // Buton metnini güncelle
        }
    }

    // Buton metnini güncelle
    updateButtonText() {
        const buttonText = document.getElementById('toggleButtonText');
        if (buttonText) {
            if (this.showResolved) {
                buttonText.textContent = 'Aktif Alarmlar';
            } else {
                buttonText.textContent = 'Alarm Geçmişi';
            }
        }
    }

    async loadAlarmHistory() {
        console.log('Alarm geçmişi yükleniyor...');
        
        // Çift yükleme kontrolü
        if (this.isLoading) {
            console.log('⏳ Zaten yükleme devam ediyor, iptal edildi');
            return;
        }
        
        this.isLoading = true;
        try {
            // Loading göster
            this.showAlarmHistoryLoading();
            
            // Tüm alarmları (aktif + düzelen) getir
            const response = await fetch(`/api/alarms?show_resolved=true&page=1&pageSize=100`, {
                method: 'GET',
                headers: {
                    'Content-Type': 'application/json'
                }
            });

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const data = await response.json();
            
            if (data.success) {
                // Alarm geçmişi için showResolved'ı true yap
                this.showResolved = true;
                this.renderAlarmHistory(data.alarms);
            } else {
                console.error('Alarm geçmişi yüklenirken hata:', data.message);
                this.showAlarmHistoryNoData();
            }
        } catch (error) {
            console.error('Alarm geçmişi yüklenirken hata:', error);
            this.showAlarmHistoryNoData();
        } finally {
            this.isLoading = false;
        }
    }

    renderAlarmHistory(alarms) {
        const container = document.getElementById('alarmHistoryContainer');
        if (!container) return;

        if (alarms.length === 0) {
            container.innerHTML = `
                <div class="no-data-message">
                    <i class="fas fa-check-circle"></i>
                    <h3>Alarm Geçmişi Yok</h3>
                    <p>Henüz alarm geçmişi bulunmuyor.</p>
                </div>
            `;
            return;
        }

        // Alarm geçmişi tablosu oluştur
        container.innerHTML = `
            <div class="alarm-history-content">
                <h4>Alarm Geçmişi</h4>
                <div class="table-container">
                    <table class="alarms-table">
                        <thead>
                            <tr>
                                <th>Zaman</th>
                                <th>Kol</th>
                                <th>Batarya</th>
                                <th>Açıklama</th>
                                <th>Durum</th>
                                <th>Çözüm Zamanı</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${alarms.map(alarm => `
                                <tr>
                                    <td>${this.formatTimestamp(alarm.timestamp)}</td>
                                    <td>${alarm.arm}</td>
                                    <td>${alarm.battery || 'Kol Alarmı'}</td>
                                    <td>${alarm.description}</td>
                                    <td>
                                        <span class="status-badge ${this.getStatusClass(alarm.status)}">
                                            ${alarm.status === 'resolved' || alarm.status === 'Düzeldi' ? 'Düzeldi' : 'Aktif'}
                                        </span>
                                    </td>
                                    <td>${alarm.resolved_at ? this.formatTimestamp(alarm.resolved_at) : '-'}</td>
                                </tr>
                            `).join('')}
                        </tbody>
                    </table>
                </div>
            </div>
        `;
    }

    updatePagination() {
        const pagination = document.getElementById('pagination');
        if (this.totalPages > 1) {
            pagination.style.display = 'flex';
            
            document.getElementById('currentPage').textContent = this.currentPage;
            document.getElementById('totalPages').textContent = this.totalPages;
            
            document.getElementById('prevPage').disabled = this.currentPage <= 1;
            document.getElementById('nextPage').disabled = this.currentPage >= this.totalPages;
        } else {
            pagination.style.display = 'none';
        }
    }

    previousPage() {
        if (this.currentPage > 1) {
            this.currentPage--;
            this.loadAlarms();
        }
    }

    nextPage() {
        if (this.currentPage < this.totalPages) {
            this.currentPage++;
            this.loadAlarms();
        }
    }

    async loadAlarms() {
        console.log('🔔 loadAlarms() başladı');
        
        // Çift yükleme kontrolü
        if (this.isLoading) {
            console.log('⏳ Zaten yükleme devam ediyor, iptal edildi');
            return;
        }
        
        // Sayfa kontrolü
        if (!this.isPageActive()) {
            console.log('⚠️ Sayfa aktif değil, loadAlarms iptal edildi');
            return;
        }
        
        this.isLoading = true;
        try {
            this.showLoading();
            
            console.log('🌐 API isteği gönderiliyor: /api/alarms');
            const response = await fetch(`/api/alarms?show_resolved=${this.showResolved}&page=${this.currentPage}&pageSize=${this.pageSize}`, {
                method: 'GET',
                headers: {
                    'Content-Type': 'application/json'
                }
            });

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            console.log('✅ API yanıtı alındı');
            const data = await response.json();
            console.log('📊 Gelen veri:', data);
            
            if (data.success) {
                this.alarms = data.alarms || [];
                this.totalPages = data.totalPages || 1;
                console.log('📋 Alarm sayısı:', this.alarms.length);
                this.renderAlarms();
                this.updatePagination();
            } else {
                console.error('Alarm verileri yüklenirken hata:', data.message);
                this.showNoData();
            }
        } catch (error) {
            console.error('Alarm verileri yüklenirken hata:', error);
            this.showNoData();
        } finally {
            this.isLoading = false;
            this.hideLoading();
        }
    }

    renderAlarms() {
        const tbody = document.getElementById('alarmsTableBody');
        if (!tbody) return;

        if (this.alarms.length === 0) {
            this.showNoData();
            return;
        }

        tbody.innerHTML = '';
        
        this.alarms.forEach(alarm => {
            const row = this.createActiveAlarmRow(alarm);
            tbody.appendChild(row);
        });

        // Tabloyu göster ve no-data mesajını gizle
        const table = document.getElementById('alarmsTable');
        const noData = document.getElementById('noDataMessage');
        
        if (table) table.style.display = 'table';
        if (noData) noData.style.display = 'none';
    }

    createActiveAlarmRow(alarm) {
        const row = document.createElement('tr');
        
        // Zaman
        const timeCell = document.createElement('td');
        timeCell.textContent = this.formatTimestamp(alarm.timestamp);
        row.appendChild(timeCell);
        
        // Kol
        const armCell = document.createElement('td');
        armCell.textContent = alarm.arm;
        row.appendChild(armCell);
        
        // Batarya
        const batteryCell = document.createElement('td');
        batteryCell.textContent = alarm.battery || 'Kol Alarmı';
        row.appendChild(batteryCell);
        
        // Açıklama
        const descriptionCell = document.createElement('td');
        descriptionCell.textContent = alarm.description;
        row.appendChild(descriptionCell);
        
        // Durum (aktif alarmlar için her zaman "Aktif")
        const statusCell = document.createElement('td');
        const statusBadge = document.createElement('span');
        statusBadge.className = 'status-badge status-error';
        statusBadge.textContent = 'Aktif';
        statusCell.appendChild(statusBadge);
        row.appendChild(statusCell);
        
        return row;
    }

    createAlarmRow(alarm) {
        const row = document.createElement('tr');
        
        // Zaman
        const timeCell = document.createElement('td');
        timeCell.textContent = this.formatTimestamp(alarm.timestamp);
        row.appendChild(timeCell);
        
        // Kol
        const armCell = document.createElement('td');
        armCell.textContent = alarm.arm;
        row.appendChild(armCell);
        
        // Batarya
        const batteryCell = document.createElement('td');
        batteryCell.textContent = alarm.battery || 'Kol Alarmı';
        row.appendChild(batteryCell);
        
        // Açıklama
        const descriptionCell = document.createElement('td');
        descriptionCell.textContent = alarm.description;
        row.appendChild(descriptionCell);
        
        // Durum
        const statusCell = document.createElement('td');
        const statusBadge = document.createElement('span');
        let statusText;
        
        // Alarm geçmişinde durum mantığı
        if (this.showResolved) {
            // Alarm geçmişi görünüyorsa - çözüm zamanı varsa "Düzeldi", yoksa "Aktif"
            if (alarm.resolved_at && alarm.resolved_at !== '') {
                statusText = 'Düzeldi';
            } else {
                statusText = 'Aktif';
            }
        } else {
            // Aktif alarmlar görünüyorsa - sadece aktif olanlar
            statusText = 'Aktif';
        }
        
        statusBadge.className = `status-badge ${this.getStatusClass(statusText)}`;
        statusBadge.textContent = statusText;
        statusCell.appendChild(statusBadge);
        row.appendChild(statusCell);
        
        // Çözüm Zamanı (sadece alarm geçmişinde)
        if (this.showResolved) {
            const resolvedCell = document.createElement('td');
            if (alarm.resolved_at) {
                resolvedCell.textContent = this.formatTimestamp(alarm.resolved_at);
            } else {
                resolvedCell.textContent = '-';
            }
            row.appendChild(resolvedCell);
        }
        
        return row;
    }

    formatTimestamp(timestamp) {
        const date = new Date(timestamp);
        return date.toLocaleString('tr-TR', {
            day: '2-digit',
            month: '2-digit',
            year: 'numeric',
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit'
        });
    }

    getStatusClass(status) {
        // Durum metnine göre sınıf döndür
        if (status === 'Düzeldi' || status === 'resolved') {
            return 'status-success';
        } else if (status === 'Aktif' || status === 'active') {
            return 'status-error';
        } else {
            return 'status-default';
        }
    }

    showLoading() {
        const loading = document.getElementById('loadingSpinner');
        const table = document.getElementById('alarmsTable');
        const noData = document.getElementById('noDataMessage');
        
        if (loading) loading.style.display = 'flex';
        if (table) table.style.display = 'none';
        if (noData) noData.style.display = 'none';
    }

    hideLoading() {
        const loading = document.getElementById('loadingSpinner');
        const table = document.getElementById('alarmsTable');
        const noData = document.getElementById('noDataMessage');
        
        if (loading) loading.style.display = 'none';
        
        // Eğer veri varsa tabloyu göster, yoksa no-data mesajını göster
        if (this.alarms && this.alarms.length > 0) {
            if (table) table.style.display = 'table';
            if (noData) noData.style.display = 'none';
        } else {
            if (table) table.style.display = 'none';
            if (noData) noData.style.display = 'block';
        }
    }

    showNoData() {
        console.log('🔍 showNoData() çağrıldı');
        const noData = document.getElementById('noDataMessage');
        const table = document.getElementById('alarmsTable');
        const loading = document.getElementById('loadingSpinner');
        
        console.log('📋 Elementler:', { noData, table, loading });
        
        if (noData) {
            noData.style.display = 'block';
            console.log('✅ noDataMessage gösterildi');
        } else {
            console.error('❌ noDataMessage bulunamadı!');
        }
        
        if (table) {
            table.style.display = 'none';
            console.log('✅ alarmsTable gizlendi');
        }
        
        if (loading) {
            loading.style.display = 'none';
            console.log('✅ loadingSpinner gizlendi');
        }
    }

    startAutoRefresh() {
        // Her 30 saniyede bir otomatik yenile
        setInterval(() => {
            if (this.isPageActive() && !this.isLoading) {
                console.log('🔄 Otomatik yenileme çalışıyor...');
                this.loadAlarms();
            }
        }, 30000); // 30 saniyede bir yenile
    }

    isPageActive() {
        return document.querySelector('.alarms-page') !== null;
    }
    
    showAlarmHistoryLoading() {
        const container = document.getElementById('alarmHistoryContainer');
        if (container) {
            container.innerHTML = `
                <div class="loading-spinner" style="display: flex;">
                    <div class="spinner"></div>
                    <p>Alarm geçmişi yükleniyor...</p>
                </div>
            `;
        }
    }
    
    showAlarmHistoryNoData() {
        const container = document.getElementById('alarmHistoryContainer');
        if (container) {
            container.innerHTML = `
                <div class="no-data-message">
                    <i class="fas fa-check-circle"></i>
                    <h3>Alarm Geçmişi Yok</h3>
                    <p>Henüz alarm geçmişi bulunmuyor.</p>
                </div>
            `;
        }
    }
    };
}

// Sayfa yüklendiğinde başlat
function initAlarmsPage() {
    console.log('🔧 initAlarmsPage() çağrıldı');
    if (!window.alarmsPage) {
        console.log('🆕 Yeni AlarmsPage instance oluşturuluyor');
        window.alarmsPage = new window.AlarmsPage();
    } else {
        console.log('🔄 Mevcut AlarmsPage instance yeniden başlatılıyor');
        // Sadece sayfa aktifse yeniden başlat
        if (window.alarmsPage.isPageActive()) {
            window.alarmsPage.init();
        } else {
            console.log('⚠️ Sayfa aktif değil, yeniden başlatma atlanıyor');
        }
    }
}

// Global olarak erişilebilir yap
window.initAlarmsPage = initAlarmsPage;

// Script yüklendiğinde otomatik init
console.log('🔧 Alarms.js yüklendi, otomatik init başlatılıyor...');
initAlarmsPage();



