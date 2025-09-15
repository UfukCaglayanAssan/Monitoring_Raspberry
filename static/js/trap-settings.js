// Trap Settings Page JavaScript
// Class'ın zaten tanımlanıp tanımlanmadığını kontrol et
if (typeof window.TrapSettingsPage === 'undefined') {
    window.TrapSettingsPage = class TrapSettingsPage {
    constructor() {
        this.trapSettings = {};
        this.trapHistory = [];
        this.trapStats = {};
        this.isLoading = false;
        this.eventsBound = false;
        
        this.init();
    }

    init() {
        console.log('🔧 TrapSettingsPage init() başladı');
        
        this.bindEvents();
        console.log('🔗 Event listener\'lar bağlandı');
        
        this.loadTrapSettings();
        this.loadTrapHistory();
        this.loadTrapStats();
    }

    bindEvents() {
        if (!this.eventsBound) {
            // Form submit event
            const form = document.getElementById('trapSettingsForm');
            if (form) {
                form.addEventListener('submit', (e) => {
                    e.preventDefault();
                    this.saveTrapSettings();
                });
            }

            // Test trap button
            const testBtn = document.getElementById('testTrapBtn');
            if (testBtn) {
                testBtn.addEventListener('click', () => {
                    this.sendTestTrap();
                });
            }

            // Reset button
            const resetBtn = document.getElementById('resetTrapBtn');
            if (resetBtn) {
                resetBtn.addEventListener('click', () => {
                    this.resetTrapSettings();
                });
            }

            // Refresh history button
            const refreshBtn = document.getElementById('refreshTrapHistory');
            if (refreshBtn) {
                refreshBtn.addEventListener('click', () => {
                    this.loadTrapHistory();
                });
            }

            // History filter
            const filterSelect = document.getElementById('trapHistoryFilter');
            if (filterSelect) {
                filterSelect.addEventListener('change', () => {
                    this.filterTrapHistory();
                });
            }

            // Dil değişikliği dinleyicisi
            window.addEventListener('languageChanged', (e) => {
                console.log('🌐 Trap Settings sayfası - Dil değişti:', e.detail.language);
                this.onLanguageChanged(e.detail.language);
            });

            this.eventsBound = true;
            console.log('🔗 Trap Settings event listener\'ları bağlandı');
        }
    }

    onLanguageChanged(language) {
        console.log('🌐 Trap Settings sayfası dil güncelleniyor:', language);
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

    async loadTrapSettings() {
        try {
            console.log('🔄 Trap ayarları yükleniyor...');
            this.showLoading(true);
            
            const response = await fetch('/api/trap-settings', {
                method: 'GET',
                headers: {
                    'Content-Type': 'application/json'
                }
            });

            if (response.ok) {
                const data = await response.json();
                if (data.success) {
                    this.trapSettings = data.settings || {};
                    this.populateForm();
                    console.log('✅ Trap ayarları yüklendi:', this.trapSettings);
                } else {
                    console.error('❌ Trap ayarları yüklenirken hata:', data.message);
                    this.showError('Trap ayarları yüklenirken hata oluştu: ' + data.message);
                }
            } else {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
        } catch (error) {
            console.error('💥 Trap ayarları yüklenirken hata:', error);
            this.showError('Trap ayarları yüklenirken hata oluştu: ' + error.message);
        } finally {
            this.showLoading(false);
        }
    }

    populateForm() {
        // Form alanlarını doldur
        const form = document.getElementById('trapSettingsForm');
        if (!form) return;

        // Toggle switch
        const trapEnabled = document.getElementById('trapEnabled');
        if (trapEnabled) {
            trapEnabled.checked = this.trapSettings.enabled || false;
        }

        // Diğer alanlar
        const fields = ['trapServer', 'trapPort', 'trapCommunity', 'trapVersion', 'trapInterval'];
        fields.forEach(field => {
            const element = document.getElementById(field);
            if (element && this.trapSettings[field] !== undefined) {
                element.value = this.trapSettings[field];
            }
        });
    }

    async saveTrapSettings() {
        try {
            console.log('💾 Trap ayarları kaydediliyor...');
            this.showLoading(true);

            const form = document.getElementById('trapSettingsForm');
            const formData = new FormData(form);
            
            const settings = {
                enabled: formData.get('trapEnabled') === 'on',
                trapServer: formData.get('trapServer'),
                trapPort: parseInt(formData.get('trapPort')) || 162,
                trapCommunity: formData.get('trapCommunity'),
                trapVersion: formData.get('trapVersion'),
                trapInterval: parseInt(formData.get('trapInterval')) || 30
            };

            const response = await fetch('/api/trap-settings', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(settings)
            });

            if (response.ok) {
                const data = await response.json();
                if (data.success) {
                    this.trapSettings = settings;
                    this.showSuccess('Trap ayarları başarıyla kaydedildi!');
                    console.log('✅ Trap ayarları kaydedildi:', settings);
                } else {
                    throw new Error(data.message || 'Ayarlar kaydedilemedi');
                }
            } else {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
        } catch (error) {
            console.error('💥 Trap ayarları kaydedilirken hata:', error);
            this.showError('Trap ayarları kaydedilirken hata oluştu: ' + error.message);
        } finally {
            this.showLoading(false);
        }
    }

    async sendTestTrap() {
        try {
            console.log('🧪 Test trap gönderiliyor...');
            this.showLoading(true);

            const response = await fetch('/api/trap-settings/test', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                }
            });

            if (response.ok) {
                const data = await response.json();
                if (data.success) {
                    this.showSuccess('Test trap başarıyla gönderildi!');
                    console.log('✅ Test trap gönderildi');
                    // Geçmişi yenile
                    this.loadTrapHistory();
                } else {
                    throw new Error(data.message || 'Test trap gönderilemedi');
                }
            } else {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
        } catch (error) {
            console.error('💥 Test trap gönderilirken hata:', error);
            this.showError('Test trap gönderilirken hata oluştu: ' + error.message);
        } finally {
            this.showLoading(false);
        }
    }

    resetTrapSettings() {
        if (confirm('Tüm trap ayarlarını sıfırlamak istediğinizden emin misiniz?')) {
            // Form'u varsayılan değerlere sıfırla
            const form = document.getElementById('trapSettingsForm');
            if (form) {
                form.reset();
            }
            console.log('🔄 Trap ayarları sıfırlandı');
        }
    }

    async loadTrapHistory() {
        try {
            console.log('🔄 Trap geçmişi yükleniyor...');
            
            const response = await fetch('/api/trap-settings/history', {
                method: 'GET',
                headers: {
                    'Content-Type': 'application/json'
                }
            });

            if (response.ok) {
                const data = await response.json();
                if (data.success) {
                    this.trapHistory = data.history || [];
                    this.renderTrapHistory();
                    console.log('✅ Trap geçmişi yüklendi:', this.trapHistory.length, 'kayıt');
                } else {
                    console.error('❌ Trap geçmişi yüklenirken hata:', data.message);
                }
            } else {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
        } catch (error) {
            console.error('💥 Trap geçmişi yüklenirken hata:', error);
        }
    }

    renderTrapHistory() {
        const container = document.getElementById('trapHistoryList');
        if (!container) return;

        if (this.trapHistory.length === 0) {
            container.innerHTML = '<div class="no-data-message"><p>Henüz trap geçmişi bulunmuyor.</p></div>';
            return;
        }

        const historyHtml = this.trapHistory.map(entry => `
            <div class="trap-history-item ${entry.status}">
                <div class="history-icon">
                    <i class="fas ${entry.status === 'success' ? 'fa-check-circle' : 'fa-times-circle'}"></i>
                </div>
                <div class="history-content">
                    <div class="history-header">
                        <span class="history-timestamp">${this.formatTimestamp(entry.timestamp)}</span>
                        <span class="history-status">${entry.status === 'success' ? 'Başarılı' : 'Başarısız'}</span>
                    </div>
                    <div class="history-details">
                        <span class="history-server">${entry.server}:${entry.port}</span>
                        <span class="history-message">${entry.message}</span>
                    </div>
                </div>
            </div>
        `).join('');

        container.innerHTML = historyHtml;
    }

    filterTrapHistory() {
        const filter = document.getElementById('trapHistoryFilter').value;
        const items = document.querySelectorAll('.trap-history-item');
        
        items.forEach(item => {
            if (filter === 'all' || item.classList.contains(filter)) {
                item.style.display = 'block';
            } else {
                item.style.display = 'none';
            }
        });
    }

    async loadTrapStats() {
        try {
            console.log('🔄 Trap istatistikleri yükleniyor...');
            
            const response = await fetch('/api/trap-settings/stats', {
                method: 'GET',
                headers: {
                    'Content-Type': 'application/json'
                }
            });

            if (response.ok) {
                const data = await response.json();
                if (data.success) {
                    this.trapStats = data.stats || {};
                    this.renderTrapStats();
                    console.log('✅ Trap istatistikleri yüklendi:', this.trapStats);
                } else {
                    console.error('❌ Trap istatistikleri yüklenirken hata:', data.message);
                }
            } else {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
        } catch (error) {
            console.error('💥 Trap istatistikleri yüklenirken hata:', error);
        }
    }

    renderTrapStats() {
        // İstatistikleri güncelle
        const totalSent = document.getElementById('totalTrapsSent');
        const successful = document.getElementById('successfulTraps');
        const failed = document.getElementById('failedTraps');
        const successRate = document.getElementById('successRate');

        if (totalSent) totalSent.textContent = this.trapStats.totalSent || 0;
        if (successful) successful.textContent = this.trapStats.successful || 0;
        if (failed) failed.textContent = this.trapStats.failed || 0;
        if (successRate) successRate.textContent = (this.trapStats.successRate || 0) + '%';
    }

    formatTimestamp(timestamp) {
        const date = new Date(timestamp);
        return date.toLocaleString('tr-TR', {
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit',
            day: '2-digit',
            month: '2-digit',
            year: 'numeric'
        });
    }

    showLoading(show) {
        const loading = document.getElementById('loadingSpinner');
        if (loading) {
            loading.style.display = show ? 'flex' : 'none';
        }
    }

    showSuccess(message) {
        // Basit success mesajı (toast benzeri)
        const toast = document.createElement('div');
        toast.className = 'toast toast-success';
        toast.innerHTML = `
            <i class="fas fa-check-circle"></i>
            <span>${message}</span>
        `;
        document.body.appendChild(toast);
        
        setTimeout(() => {
            toast.remove();
        }, 3000);
    }

    showError(message) {
        // Basit error mesajı (toast benzeri)
        const toast = document.createElement('div');
        toast.className = 'toast toast-error';
        toast.innerHTML = `
            <i class="fas fa-exclamation-circle"></i>
            <span>${message}</span>
        `;
        document.body.appendChild(toast);
        
        setTimeout(() => {
            toast.remove();
        }, 5000);
    }

    isPageActive() {
        return document.querySelector('.trap-settings-page') !== null;
    }
    };
}

// Sayfa yüklendiğinde başlat
function initTrapSettingsPage() {
    console.log('🔧 initTrapSettingsPage() çağrıldı');
    if (!window.trapSettingsPage) {
        console.log('🆕 Yeni TrapSettingsPage instance oluşturuluyor');
        window.trapSettingsPage = new window.TrapSettingsPage();
    } else {
        console.log('🔄 TrapSettingsPage instance yeniden başlatılıyor');
        window.trapSettingsPage.init();
    }
}

// Global olarak erişilebilir yap
window.initTrapSettingsPage = initTrapSettingsPage;

// Script yüklendiğinde otomatik init
console.log('🔧 Trap-settings.js yüklendi, otomatik init başlatılıyor...');
initTrapSettingsPage();
