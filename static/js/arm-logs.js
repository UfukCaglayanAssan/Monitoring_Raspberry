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
        
        this.init();
    }

    async init() {
        this.bindEvents();
        this.setDefaultDates();
        await this.loadArmOptions();
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
        document.getElementById('armFilter').addEventListener('change', (e) => {
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
        // Tarih filtresini temizle - tüm verileri göster
        document.getElementById('startDate').value = '';
        document.getElementById('endDate').value = '';
        
        this.filters.startDate = '';
        this.filters.endDate = '';
    }

    formatDateForInput(date) {
        return date.toISOString().split('T')[0];
    }

    async onLanguageChanged(language) {
        console.log('ArmLogs: Dil değişti:', language);
        
        // TranslationManager ile çevirileri güncelle
        if (window.translationManager && window.translationManager.initialized) {
            window.translationManager.updateAllElements();
        }
        
        // Dropdown'ı yeniden yükle (çevirileri güncellemek için)
        const currentArmValue = document.getElementById('armFilter')?.value || '';
        await this.loadArmOptions();
        
        // Seçili değeri geri yükle
        if (currentArmValue) {
            document.getElementById('armFilter').value = currentArmValue;
            this.filters.arm = currentArmValue;
        }
        
        // Geriye dönük uyumluluk: data-tr ve data-en attribute'larını da güncelle
        this.updateUITexts(language);
    }

    updateUITexts(language) {
        // UI metinlerini güncelle (geriye dönük uyumluluk için)
        const elements = document.querySelectorAll('[data-tr], [data-en]');
        elements.forEach(element => {
            if (language === 'en' && element.hasAttribute('data-en')) {
                element.textContent = element.getAttribute('data-en');
            } else if (language === 'tr' && element.hasAttribute('data-tr')) {
                element.textContent = element.getAttribute('data-tr');
            }
        });
    }
    
    async loadArmOptions() {
        try {
            const response = await fetch('/api/active-arms', {
                method: 'GET',
                headers: { 'Content-Type': 'application/json' }
            });
            
            if (response.ok) {
                const data = await response.json();
                if (data.success && data.activeArms) {
                    const armFilter = document.getElementById('armFilter');
                    const currentArmValue = this.filters.arm || armFilter.value;
                    
                    // Kol seçeneklerini güncelle
                    const t = window.translationManager && window.translationManager.initialized 
                        ? window.translationManager.t.bind(window.translationManager) 
                        : (key) => key;
                    
                    const allArmsText = t('armLogs.allArms');
                    armFilter.innerHTML = `<option value="" data-i18n="armLogs.allArms">${allArmsText}</option>`;
                    
                    // Tüm kolları ekle - bataryası olmayanları disabled yap
                    for (let arm = 1; arm <= 4; arm++) {
                        const armData = data.activeArms.find(a => a.arm === arm);
                        const hasBatteries = armData && armData.slave_count > 0;
                        const armKey = `common.arm${arm}`;
                        
                        const option = document.createElement('option');
                        option.value = arm;
                        option.textContent = t(armKey);
                        option.setAttribute('data-i18n', armKey);
                        option.disabled = !hasBatteries; // Batarya yoksa tıklanamaz
                        
                        if (!hasBatteries) {
                            option.style.color = '#999';
                            option.style.fontStyle = 'italic';
                        }
                        
                        armFilter.appendChild(option);
                    }
                    
                    // Çevirileri uygula
                    if (window.translationManager && window.translationManager.initialized) {
                        window.translationManager.updateAllElements();
                    }
                    
                    // Seçili değeri geri yükle
                    if (currentArmValue) {
                        armFilter.value = currentArmValue;
                        this.filters.arm = currentArmValue;
                    }
                }
            }
        } catch (error) {
            console.error('❌ Kol seçenekleri yükleme hatası:', error);
        }
    }

    async loadLogs() {
        console.log('🔋 [2025-09-08T11:16:35.221Z] loadLogs() başladı');
        const tableBody = document.getElementById('armLogsTableBody');
        console.log('📋 Table body bulundu:', tableBody);
        
        try {
            console.log('⏳ [2025-09-08T11:16:35.221Z] Loading gösteriliyor');
            this.showLoading(tableBody);

            const currentLanguage = localStorage.getItem('language') || 'tr';
            console.log('🌐 [2025-09-08T11:16:35.221Z] Kullanılan dil:', currentLanguage);
            
            console.log('🌐 [2025-09-08T11:16:35.221Z] API isteği gönderiliyor: /api/arm-logs');
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
                console.log('✅ [2025-09-08T11:16:35.221Z] API yanıtı alındı');
                const data = await response.json();
                console.log('📊 [2025-09-08T11:16:35.221Z] Gelen veri:', data);
                this.logs = data.logs || [];
                this.totalPages = data.totalPages || 1;
                
                console.log('📋 [2025-09-08T11:16:35.221Z] Log sayısı:', this.logs.length);
                this.renderLogs();
                this.updatePagination();
            } else {
                throw new Error('Log verileri alınamadı');
            }
        } catch (error) {
            console.error('❌ [2025-09-08T11:16:35.221Z] Log yükleme hatası:', error);
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
                    <td>${this.formatValue(log.module_temperature, '°C')}</td>
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
async function initArmLogsPage() {
    console.log('🔧 initArmLogsPage() çağrıldı');
    if (!window.armLogsPage) {
        console.log('🆕 Yeni ArmLogsPage instance oluşturuluyor');
        window.armLogsPage = new window.ArmLogsPage();
    } else {
        // Mevcut instance varsa kol seçeneklerini yenile ve veri yükle
        console.log('🔄 Mevcut ArmLogsPage instance kullanılıyor, kol seçenekleri yenileniyor');
        await window.armLogsPage.loadArmOptions();
        window.armLogsPage.loadLogs();
    }
}

// Global olarak erişilebilir yap
window.initArmLogsPage = initArmLogsPage;

// Script yüklendiğinde otomatik init
console.log('🔧 Arm-logs.js yüklendi, otomatik init başlatılıyor...');
initArmLogsPage();
