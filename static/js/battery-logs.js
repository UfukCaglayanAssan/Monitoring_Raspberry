// Batarya Logları Sayfası JavaScript
// Class'ın zaten tanımlanıp tanımlanmadığını kontrol et
if (typeof window.BatteryLogsPage === 'undefined') {
    window.BatteryLogsPage = class BatteryLogsPage {
    constructor() {
        this.currentPage = 1;
        this.pageSize = 50;
        this.totalPages = 1;
        this.filters = {
            arm: '',
            battery: '',
            startDate: '',
            endDate: ''
        };
        this.logs = [];
        
        this.init();
    }

    init() {
        console.log('🚀 BatteryLogsPage init() çağrıldı');
        this.bindEvents();
        this.setDefaultDates();
        this.initSelect2();
        this.loadArmOptions();
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
            console.log('Export butonu tıklandı!');
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
            this.updateBatteryOptions(e.target.value);
        });

        // Select2 için jQuery event kullan
        $('#batteryFilter').on('change', (e) => {
            this.filters.battery = $(e.target).val();
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
        // Varsayılan tarih filtresi uygulanmaz - tüm veriler gösterilir
        document.getElementById('startDate').value = '';
        document.getElementById('endDate').value = '';
        
        this.filters.startDate = '';
        this.filters.endDate = '';
    }

    formatDateForInput(date) {
        return date.toISOString().split('T')[0];
    }

    onLanguageChanged(language) {
        console.log('BatteryLogs: Dil değişti:', language);
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
        console.log('🔍 loadLogs() çağrıldı');
        const tableBody = document.getElementById('batteryLogsTableBody');
        
        try {
            console.log('📊 API çağrısı yapılıyor...');
            this.showLoading(tableBody);

            const currentLanguage = localStorage.getItem('language') || 'tr';
            
            const response = await fetch('/api/battery-logs', {
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
                console.log('Battery logs API response:', data);
                this.logs = data.logs || [];
                this.totalPages = data.totalPages || 1;
                
                console.log('Logs loaded:', this.logs.length, 'items');
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
        const tableBody = document.getElementById('batteryLogsTableBody');
        
        if (this.logs.length === 0) {
            const currentLanguage = localStorage.getItem('language') || 'tr';
            tableBody.innerHTML = `
                <tr>
                    <td colspan="9">
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

        // DOM element kontrolü
        if (!tableBody) {
            console.error('❌ tableBody element bulunamadı!');
            return;
        }
        
        tableBody.innerHTML = this.logs.map(log => {
            return `
                <tr>
                    <td>${this.formatDate(log.timestamp)}</td>
                    <td>${log.arm}</td>
                    <td>${log.batteryAddress}</td>
                    <td>${this.formatValue(log.voltage, 'V')}</td>
                    <td>${this.formatValue(log.charge_status, '%')}</td>
                    <td>${this.formatValue(log.temperature, '°C')}</td>
                    <td>${this.formatValue(log.positive_pole_temp, '°C')}</td>
                    <td>${this.formatValue(log.negative_pole_temp, '°C')}</td>
                    <td>${this.formatValue(log.health_status, '%')}</td>
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
                <td colspan="9" class="text-center">
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
                <td colspan="9" class="text-center text-danger">
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
        // Filtre değerlerini güncelle
        this.filters.arm = document.getElementById('armFilter').value;
        this.filters.battery = $('#batteryFilter').val();
        this.filters.startDate = document.getElementById('startDate').value;
        this.filters.endDate = document.getElementById('endDate').value;
        
        console.log('🔍 Filtreler uygulandı:', this.filters);
        
        this.currentPage = 1;
        this.loadLogs();
    }

    clearFilters() {
        console.log('🧹 clearFilters() çağrıldı');
        this.filters = {
            arm: '',
            battery: '',
            startDate: '',
            endDate: ''
        };
        
        document.getElementById('armFilter').value = '';
        $('#batteryFilter').val('').trigger('change');
        this.setDefaultDates();
        
        // Batarya seçeneklerini sıfırla
        this.updateBatteryOptions('');
        
        this.currentPage = 1;
        this.loadLogs();
        console.log('✅ Filtreler temizlendi');
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
                    
                    // Event listener'ı kaldır (yeniden bağlanacak)
                    const oldArmFilter = armFilter.cloneNode(false);
                    
                    // Kol seçeneklerini güncelle
                    armFilter.innerHTML = '<option value="">Tüm Kollar</option>';
                    data.activeArms.forEach(arm => {
                        if (arm.slave_count > 0) {
                            const option = document.createElement('option');
                            option.value = arm.arm;
                            option.textContent = `Kol ${arm.arm}`;
                            armFilter.appendChild(option);
                        }
                    });
                    
                    // Event listener'ı yeniden bağla
                    armFilter.addEventListener('change', (e) => {
                        this.filters.arm = e.target.value;
                        this.updateBatteryOptions(e.target.value);
                    });
                    
                    // Eğer daha önce bir kol seçilmişse, onu geri yükle ve batarya seçeneklerini güncelle
                    if (currentArmValue) {
                        armFilter.value = currentArmValue;
                        this.filters.arm = currentArmValue;
                        
                        // Batarya seçimini de sakla
                        const currentBatteryValue = this.filters.battery || $('#batteryFilter').val();
                        
                        await this.updateBatteryOptions(currentArmValue);
                        
                        // Batarya seçimini geri yükle
                        if (currentBatteryValue) {
                            $('#batteryFilter').val(currentBatteryValue).trigger('change');
                            this.filters.battery = currentBatteryValue;
                        }
                    } else {
                        // Kol seçilmemişse batarya seçeneğini devre dışı bırak
                        await this.updateBatteryOptions('');
                    }
                }
            }
        } catch (error) {
            console.error('❌ Kol seçenekleri yükleme hatası:', error);
        }
    }
    
    initSelect2() {
        // Batarya select2'yi başlat
        $('#batteryFilter').select2({
            placeholder: 'Önce kol seçiniz',
            allowClear: true,
            width: '100%'
        });
    }

    async updateBatteryOptions(selectedArm) {
        const batteryFilter = document.getElementById('batteryFilter');
        
        if (!selectedArm) {
            $('#batteryFilter').empty();
            $('#batteryFilter').append('<option value="">Önce kol seçiniz</option>');
            $('#batteryFilter').select2({
                placeholder: 'Önce kol seçiniz',
                allowClear: true,
                width: '100%'
            });
            batteryFilter.disabled = true;
            return;
        }
        
        try {
            const response = await fetch('/api/active-arms');
            const data = await response.json();
            
            if (data.success && data.activeArms) {
                const selectedArmData = data.activeArms.find(arm => arm.arm == selectedArm);
                const batteryCount = selectedArmData ? selectedArmData.slave_count : 0;
                
                if (batteryCount > 0) {
                    // Select2'yi temizle
                    $('#batteryFilter').empty();
                    
                    // Tüm Bataryalar seçeneği ekle
                    $('#batteryFilter').append('<option value="">Tüm Bataryalar</option>');
                    
                    // Batarya seçeneklerini ekle (1'den başla)
                    for (let i = 1; i <= batteryCount; i++) {
                        $('#batteryFilter').append(`<option value="${i}">Batarya ${i}</option>`);
                    }
                    
                    // Select2'yi yeniden başlat
                    $('#batteryFilter').select2({
                        placeholder: 'Batarya seçiniz',
                        allowClear: true,
                        width: '100%'
                    });
                    
                    batteryFilter.disabled = false;
                } else {
                    $('#batteryFilter').empty();
                    $('#batteryFilter').append('<option value="">Bu kolda batarya yok</option>');
                    $('#batteryFilter').select2({
                        placeholder: 'Bu kolda batarya yok',
                        allowClear: true,
                        width: '100%'
                    });
                    batteryFilter.disabled = true;
                }
            }
        } catch (error) {
            console.error('Batarya seçenekleri yükleme hatası:', error);
            $('#batteryFilter').empty();
            $('#batteryFilter').append('<option value="">Hata oluştu</option>');
            $('#batteryFilter').select2({
                placeholder: 'Hata oluştu',
                allowClear: true,
                width: '100%'
            });
            batteryFilter.disabled = true;
        }
    }

    exportLogs() {
        // CSV export işlemi
        console.log('Export işlemi başlatıldı');
        console.log('Filtreler:', this.filters);
        
        try {
            // Filtreleri hazırla
            const exportFilters = {
                arm: this.filters.arm || '',
                battery: this.filters.battery || '',
                start_date: this.filters.startDate || '',
                end_date: this.filters.endDate || ''
            };
            
            // API'ye export isteği gönder
            fetch('/api/battery-logs/export', {
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
                a.download = `battery_logs_export_${new Date().toISOString().split('T')[0]}.csv`;
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
    }; // Class kapanış süslü parantezi
} // if statement kapanış süslü parantezi

// Sayfa yüklendiğinde başlat
function initBatteryLogsPage() {
    console.log('🔧 initBatteryLogsPage() çağrıldı');
    if (!window.batteryLogsPage) {
        console.log('🆕 Yeni BatteryLogsPage instance oluşturuluyor');
        window.batteryLogsPage = new BatteryLogsPage();
    } else {
        // Mevcut instance varsa kol seçeneklerini yenile ve veri yükle
        console.log('🔄 Mevcut BatteryLogsPage instance kullanılıyor, kol seçenekleri yenileniyor');
        // Kol seçeneklerini yenile
        window.batteryLogsPage.loadArmOptions();
        // Veri yükle
        window.batteryLogsPage.loadLogs();
    }
}

// Global olarak erişilebilir yap
window.initBatteryLogsPage = initBatteryLogsPage;

// Script yüklendiğinde otomatik init
console.log('🔧 Battery-logs.js yüklendi, otomatik init başlatılıyor...');
initBatteryLogsPage();