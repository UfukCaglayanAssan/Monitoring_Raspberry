// Alarms Sayfası JavaScript
class AlarmsPage {
    constructor() {
        this.alarms = [];
        this.showResolved = false; // Varsayılan olarak sadece aktif alarmları göster
        this.currentPage = 1;
        this.pageSize = 50;
        this.totalPages = 1;
        this.init();
    }

    init() {
        this.bindEvents();
        this.loadAlarms();
        this.startAutoRefresh();
    }

    bindEvents() {
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
    }

    // Alarm geçmişi toggle fonksiyonu
    toggleAlarmHistory() {
        const alarmHistoryContainer = document.getElementById('alarmHistoryContainer');
        if (alarmHistoryContainer) {
            if (alarmHistoryContainer.style.display === 'none' || 
                alarmHistoryContainer.style.display === '') {
                alarmHistoryContainer.style.display = 'block';
                this.loadAlarmHistory();
            } else {
                alarmHistoryContainer.style.display = 'none';
            }
        }
    }

    loadAlarmHistory() {
        console.log('Alarm geçmişi yükleniyor...');
        // Burada alarm geçmişi API'den çekilecek
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
        try {
            this.showLoading();
            
            const response = await fetch(`/api/alarms?show_resolved=${this.showResolved}&page=${this.currentPage}&pageSize=${this.pageSize}`, {
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
                this.alarms = data.alarms || [];
                this.totalPages = data.totalPages || 1;
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
            const row = this.createAlarmRow(alarm);
            tbody.appendChild(row);
        });

        // Tabloyu göster
        const table = document.getElementById('alarmsTable');
        if (table) table.style.display = 'table';
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
        if (alarm.status === 'resolved') {
            statusText = 'Düzeldi';
        } else if (alarm.status === 'Düzeldi') {
            statusText = 'Düzeldi';
        } else {
            statusText = 'Aktif';
        }
        statusBadge.className = `status-badge ${this.getStatusClass(alarm.status)}`;
        statusBadge.textContent = statusText;
        statusCell.appendChild(statusBadge);
        row.appendChild(statusCell);
        

        
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
        switch (status) {
            case 'resolved':
            case 'Düzeldi':
                return 'status-success';
            case 'active':
            case 'Devam Ediyor':
                return 'status-error';
            default:
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
        if (loading) loading.style.display = 'none';
    }

    showNoData() {
        const noData = document.getElementById('noDataMessage');
        const table = document.getElementById('alarmsTable');
        const loading = document.getElementById('loadingSpinner');
        
        if (noData) noData.style.display = 'block';
        if (table) table.style.display = 'none';
        if (loading) loading.style.display = 'none';
    }

    startAutoRefresh() {
        setInterval(() => {
            if (this.isPageActive()) {
                this.loadAlarms();
            }
        }, 30000); // 30 saniyede bir yenile
    }

    isPageActive() {
        return document.querySelector('.alarms-page') !== null;
    }
}

// Sayfa yüklendiğinde başlat
function initAlarmsPage() {
    console.log('🔧 initAlarmsPage() çağrıldı');
    if (!window.alarmsPage) {
        window.alarmsPage = new AlarmsPage();
    }
}

// Hem DOMContentLoaded hem de manuel çağrı için
document.addEventListener('DOMContentLoaded', initAlarmsPage);

// Global olarak erişilebilir yap
window.initAlarmsPage = initAlarmsPage;



