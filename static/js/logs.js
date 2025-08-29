// Logs sayfası JavaScript
class LogsPage {
    constructor() {
        this.currentPage = 1;
        this.pageSize = 50;
        this.totalPages = 1;
        this.filters = {
            arm: '',
            battery: '',
            dataType: '',
            status: '',
            startDate: '',
            endDate: ''
        };
        this.logs = [];
    }

    init() {
        this.bindEvents();
        this.setDefaultDates();  // Önce tarihleri ayarla
        this.loadLogs();         // Sonra verileri yükle
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

        document.getElementById('batteryFilter').addEventListener('input', (e) => {
            this.filters.battery = e.target.value;
        });

        document.getElementById('dataTypeFilter').addEventListener('change', (e) => {
            this.filters.dataType = e.target.value;
        });

        document.getElementById('statusFilter').addEventListener('change', (e) => {
            this.filters.status = e.target.value;
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
        // Dil değiştiğinde UI metinlerini güncelle
        console.log('Logs: Dil değişti:', language);
        this.updateLogsTexts(language);
    }

    updateLogsTexts(language) {
        // Tüm data-tr ve data-en attribute'larına sahip elementleri güncelle
        const elements = document.querySelectorAll('[data-tr][data-en]');
        elements.forEach(element => {
            const newText = element.getAttribute(`data-${language}`) || element.textContent;
            element.textContent = newText;
        });

        // Select option'ları güncelle
        const dataTypeSelect = document.getElementById('dataTypeFilter');
        if (dataTypeSelect) {
            Array.from(dataTypeSelect.options).forEach(option => {
                if (option.hasAttribute('data-tr') && option.hasAttribute('data-en')) {
                    option.textContent = option.getAttribute(`data-${language}`) || option.textContent;
                }
            });
        }

        const statusSelect = document.getElementById('statusFilter');
        if (statusSelect) {
            Array.from(statusSelect.options).forEach(option => {
                if (option.hasAttribute('data-tr') && option.hasAttribute('data-en')) {
                    option.textContent = option.getAttribute(`data-${language}`) || option.textContent;
                }
            });
        }
    }

    async loadLogs() {
        const tableBody = document.getElementById('logsTableBody');
        
        try {
            // Loading göster
            this.showLoading(tableBody);

            // API'den log verilerini al
            const response = await fetch('/api/logs', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
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
                
                // Loglar oluşturulduktan sonra çeviri yap
                const currentLanguage = localStorage.getItem('language') || 'tr';
                this.updateLogsTexts(currentLanguage);
            } else {
                throw new Error('Log verileri alınamadı');
            }
        } catch (error) {
            console.error('Log yükleme hatası:', error);
            this.showError(tableBody, 'Log verileri yüklenirken bir hata oluştu.');
        }
    }

    renderLogs() {
        const tableBody = document.getElementById('logsTableBody');
        
        if (this.logs.length === 0) {
            tableBody.innerHTML = `
                <tr>
                    <td colspan="6">
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
            // k değerine göre veri tipi ismini belirle
            let dataTypeName = log.name || (currentLanguage === 'en' ? 'Unknown' : 'Bilinmeyen');
            const unit = log.unit || '';
            
            // Mevcut dili al
            const currentLanguage = localStorage.getItem('language') || 'tr';
            
            if (log.batteryAddress === 2) {
                // Arm verisi (k=2)
                if (log.dtype === 10) dataTypeName = currentLanguage === 'en' ? 'Current' : 'Akım';
                else if (log.dtype === 11) dataTypeName = currentLanguage === 'en' ? 'Humidity' : 'Nem';
                else if (log.dtype === 12) dataTypeName = currentLanguage === 'en' ? 'Temperature' : 'Sıcaklık';
            } else {
                // Battery verisi (k!=2)
                if (log.dtype === 10) dataTypeName = currentLanguage === 'en' ? 'Voltage' : 'Gerilim';
                else if (log.dtype === 11) dataTypeName = currentLanguage === 'en' ? 'Charge Status' : 'Şarj Durumu';
                else if (log.dtype === 12) dataTypeName = currentLanguage === 'en' ? 'Module Temperature' : 'Modül Sıcaklığı';
                else if (log.dtype === 13) dataTypeName = currentLanguage === 'en' ? 'Positive Terminal Temperature' : 'Pozitif Kutup Başı Sıcaklığı';
                else if (log.dtype === 14) dataTypeName = currentLanguage === 'en' ? 'Negative Terminal Temperature' : 'Negatif Kutup Başı Sıcaklığı';
                else if (log.dtype === 126) dataTypeName = currentLanguage === 'en' ? 'Health Status' : 'Sağlık Durumu';
            }
            
            return `
                <tr>
                    <td>${this.formatDate(log.timestamp)}</td>
                    <td>${log.arm}</td>
                    <td>${log.batteryAddress}</td>
                    <td>${dataTypeName} ${unit ? `(${unit})` : ''}</td>
                    <td>${this.formatNumber(log.data)} ${unit || ''}</td>
                    <td>
                        <span class="status-badge status-success">
                            ${currentLanguage === 'en' ? 'SUCCESS' : 'BAŞARILI'}
                        </span>
                    </td>
                </tr>
            `;
        }).join('');
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

    formatNumber(number) {
        return parseFloat(number).toFixed(3);
    }

    getStatusText(status) {
        const statusMap = {
            'success': 'Başarılı',
            'error': 'Hata',
            'warning': 'Uyarı'
        };
        return statusMap[status] || status;
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
        this.currentPage = 1; // İlk sayfaya dön
        this.loadLogs();
    }

    clearFilters() {
        // Filtreleri temizle
        document.getElementById('armFilter').value = '';
        document.getElementById('batteryFilter').value = '';
        document.getElementById('dataTypeFilter').value = '';
        document.getElementById('statusFilter').value = '';
        
        this.setDefaultDates();
        
        // Filtre objesini temizle
        this.filters = {
            arm: '',
            battery: '',
            dataType: '',
            status: '',
            startDate: this.filters.startDate,
            endDate: this.filters.endDate
        };
        
        // Logları yeniden yükle
        this.currentPage = 1;
        this.loadLogs();
    }

    async exportLogs() {
        try {
            const response = await fetch('/api/logs/export', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    filters: this.filters
                })
            });

            if (response.ok) {
                const blob = await response.blob();
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = `logs_${new Date().toISOString().split('T')[0]}.csv`;
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                window.URL.revokeObjectURL(url);
                
                utils.showToast('Log verileri başarıyla dışa aktarıldı.', 'success');
            } else {
                throw new Error('Dışa aktarma başarısız');
            }
        } catch (error) {
            console.error('Dışa aktarma hatası:', error);
            utils.showToast('Dışa aktarma sırasında bir hata oluştu.', 'error');
        }
    }

    showLoading(element) {
        element.innerHTML = `
            <tr>
                <td colspan="6">
                    <div class="loading">
                        <div class="spinner"></div>
                        Log verileri yükleniyor...
                    </div>
                </td>
            </tr>
        `;
    }

    showError(element, message) {
        element.innerHTML = `
            <tr>
                <td colspan="6">
                    <div class="empty-state">
                        <i class="fas fa-exclamation-triangle"></i>
                        <h4>Hata Oluştu</h4>
                        <p>${message}</p>
                    </div>
                </td>
            </tr>
        `;
    }


}

// Global instance oluştur
window.logsPage = new LogsPage();
