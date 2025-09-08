// Kol Logları Sayfası JavaScript
// Class'ın zaten tanımlanıp tanımlanmadığını kontrol et
if (typeof window.ArmLogsPage === 'undefined') {
    window.ArmLogsPage = class ArmLogsPage {
    constructor() {
        this.currentPage = 1;
        this.pageSize = 50;
        this.totalPages = 1;
        this.filters = {
            arm: '',
            startDate: '',
            endDate: ''
        };
        this.logs = [];
    }

    init() {
        this.bindEvents();
        this.setDefaultDates();
        this.loadLogs();
    }

    bindEvents() {
        // Filtre butonları
        document.getElementById('applyFilters').addEventListener('click', () => {
            this.applyFilters();
        });

        document.getElementById('clearFilters').addEventListener('click', () => {
            this.clearFilters();
        });

        // Tablo butonları
        document.getElementById('refreshLogs').addEventListener('click', () => {
            this.loadLogs();
        });

        document.getElementById('exportLogs').addEventListener('click', () => {
            this.exportLogs();
        });

        // Sayfalama
        document.getElementById('prevPage').addEventListener('click', () => {
            this.previousPage();
        });

        document.getElementById('nextPage').addEventListener('click', () => {
            this.nextPage();
        });

        // Filtre input'ları
        document.getElementById('armFilter').addEventListener('input', (e) => {
            this.filters.arm = e.target.value;
        });

        document.getElementById('startDate').addEventListener('change', (e) => {
            this.filters.startDate = e.target.value;
        });

        document.getElementById('endDate').addEventListener('change', (e) => {
            this.filters.endDate = e.target.value;
        });

        // Dil değişikliği dinleyicisi
        window.addEventListener('languageChanged', (e) => {
            this.onLanguageChanged(e.detail.language);
        });
    }

    setDefaultDates() {
        const today = new Date();
        const lastWeek = new Date(today.getTime() - 7 * 24 * 60 * 60 * 1000);
        
        document.getElementById('startDate').value = this.formatDateForInput(lastWeek);
        document.getElementById('endDate').value = this.formatDateForInput(today);
        
        this.filters.startDate = this.formatDateForInput(lastWeek);
        this.filters.endDate = this.formatDateForInput(today);
    }

    formatDateForInput(date) {
        return date.toISOString().split('T')[0];
    }

    onLanguageChanged(language) {
        console.log('ArmLogs: Dil değişti:', language);
        this.updateUITexts(language);
    }

    updateUITexts(language) {
        // UI metinlerini güncelle
        const elements = document.querySelectorAll('[data-tr], [data-en]');
        elements.forEach(element => {
            if (language === 'en' && element.hasAttribute('data-en')) {
                element.textContent = element.getAttribute('data-en');
            } else if (language === 'tr' && element.hasAttribute('data-tr')) {
                element.textContent = element.getAttribute('data-tr');
            }
        });
    }

    async loadLogs() {
        const tableBody = document.getElementById('armLogsTableBody');
        
        try {
            this.showLoading(tableBody);

            const currentLanguage = localStorage.getItem('language') || 'tr';
            
            const response = await fetch('/api/arm-logs', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Language': currentLanguage
                },
                body: JSON.stringify({
                    page: this.currentPage,
                    pageSize: this.pageSize,
                    filters: this.filters
                })
            });

            if (response.ok) {
                const data = await response.json();
                this.logs = data.logs || [];
                this.totalPages = data.totalPages || 1;
                
                this.renderLogs();
                this.updatePagination();
            } else {
                throw new Error('Log verileri alınamadı');
            }
        } catch (error) {
            console.error('Log yükleme hatası:', error);
            this.showError(tableBody, 'Log verileri yüklenirken bir hata oluştu.');
        }
    }

    renderLogs() {
        const tableBody = document.getElementById('armLogsTableBody');
        
        if (this.logs.length === 0) {
            const currentLanguage = localStorage.getItem('language') || 'tr';
            tableBody.innerHTML = `
                <tr>
                    <td colspan="5">
                        <div class="empty-state">
                            <i class="fas fa-inbox"></i>
                            <h4>${currentLanguage === 'en' ? 'No Data Found' : 'Veri Bulunamadı'}</h4>
                            <p>${currentLanguage === 'en' ? 'No log data found matching the selected criteria.' : 'Seçilen kriterlere uygun log verisi bulunamadı.'}</p>
                        </div>
                    </td>
                </tr>
            `;
            return;
        }

        tableBody.innerHTML = this.logs.map(log => {
            return `
                <tr>
                    <td>${log.arm}</td>
                    <td>${this.formatDate(log.timestamp)}</td>
                    <td>${this.formatValue(log.current, 'A')}</td>
                    <td>${this.formatValue(log.humidity, '%')}</td>
                    <td>${this.formatValue(log.ambient_temperature, '°C')}</td>
                </tr>
            `;
        }).join('');
    }

    formatValue(value, unit) {
        if (value === null || value === undefined) {
            return '-';
        }
        return `${parseFloat(value).toFixed(3)} ${unit}`;
    }

    formatDate(timestamp) {
        const date = new Date(timestamp);
        return date.toLocaleDateString('tr-TR', {
            day: '2-digit',
            month: '2-digit',
            year: 'numeric',
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit'
        });
    }

    showLoading(tableBody) {
        tableBody.innerHTML = `
            <tr>
                <td colspan="5" class="text-center">
                    <div class="loading-spinner">
                        <i class="fas fa-spinner fa-spin"></i>
                        <span>Yükleniyor...</span>
                    </div>
                </td>
            </tr>
        `;
    }

    showError(tableBody, message) {
        tableBody.innerHTML = `
            <tr>
                <td colspan="5" class="text-center text-danger">
                    <i class="fas fa-exclamation-triangle"></i>
                    <span>${message}</span>
                </td>
            </tr>
        `;
    }

    updatePagination() {
        document.getElementById('currentPage').textContent = this.currentPage;
        document.getElementById('totalPages').textContent = this.totalPages;
        
        document.getElementById('prevPage').disabled = this.currentPage <= 1;
        document.getElementById('nextPage').disabled = this.currentPage >= this.totalPages;
    }

    previousPage() {
        if (this.currentPage > 1) {
            this.currentPage--;
            this.loadLogs();
        }
    }

    nextPage() {
        if (this.currentPage < this.totalPages) {
            this.currentPage++;
            this.loadLogs();
        }
    }

    applyFilters() {
        this.currentPage = 1;
        this.loadLogs();
    }

    clearFilters() {
        this.filters = {
            arm: '',
            startDate: '',
            endDate: ''
        };
        
        document.getElementById('armFilter').value = '';
        this.setDefaultDates();
        
        this.currentPage = 1;
        this.loadLogs();
    }

    exportLogs() {
        // CSV export işlemi
        console.log('Export işlemi başlatıldı');
        
        try {
            // Filtreleri hazırla
            const exportFilters = {
                arm: this.filters.arm || '',
                start_date: this.filters.startDate || '',
                end_date: this.filters.endDate || ''
            };
            
            // API'ye export isteği gönder
            fetch('/api/arm-logs/export', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    filters: exportFilters
                })
            })
            .then(response => {
                if (response.ok) {
                    return response.blob();
                }
                throw new Error('Export hatası: ' + response.status);
            })
            .then(blob => {
                // CSV dosyasını indir
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = `arm_logs_export_${new Date().toISOString().split('T')[0]}.csv`;
                document.body.appendChild(a);
                a.click();
                window.URL.revokeObjectURL(url);
                document.body.removeChild(a);
                
                console.log('Export başarılı');
            })
            .catch(error => {
                console.error('Export hatası:', error);
                alert('Export sırasında hata oluştu: ' + error.message);
            });
            
        } catch (error) {
            console.error('Export hatası:', error);
            alert('Export sırasında hata oluştu: ' + error.message);
        }
    }
    };
}

// Sayfa yüklendiğinde başlat
function initArmLogsPage() {
    console.log('🔧 initArmLogsPage() çağrıldı');
    if (!window.armLogsPage) {
        window.armLogsPage = new window.ArmLogsPage();
    } else {
        // Mevcut instance'ı yeniden başlat
        console.log('🔄 Mevcut ArmLogsPage instance yeniden başlatılıyor');
        window.armLogsPage.init();
    }
}

// Global olarak erişilebilir yap
// window.initArmLogsPage = initArmLogsPage; // Kaldırıldı - karışıklığa neden oluyor
}
