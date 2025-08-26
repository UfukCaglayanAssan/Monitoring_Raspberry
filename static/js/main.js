// Ana JavaScript dosyası
class App {
    constructor() {
        this.currentPage = 'summary';
        this.currentLanguage = 'tr';
        this.init();
    }

    init() {
        this.bindEvents();
        this.showSummaryPage(); // Ana sayfa olarak özet'i göster
        this.setLanguage(this.currentLanguage);
    }

    bindEvents() {
        // Menü navigasyonu
        document.querySelectorAll('.nav-link').forEach(link => {
            link.addEventListener('click', (e) => {
                e.preventDefault();
                const page = e.currentTarget.dataset.page;
                this.navigateToPage(page);
            });
        });

        // Dil seçimi
        document.querySelectorAll('.lang-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const lang = e.currentTarget.dataset.lang;
                this.setLanguage(lang);
            });
        });

        // Bildirimler
        document.querySelector('.notifications').addEventListener('click', () => {
            this.showNotifications();
        });

        // Çıkış
        document.querySelector('.logout-btn').addEventListener('click', () => {
            this.logout();
        });
    }

    navigateToPage(page) {
        // Aktif menü öğesini güncelle
        document.querySelectorAll('.nav-link').forEach(link => {
            link.classList.remove('active');
        });
        
        document.querySelector(`[data-page="${page}"]`).classList.add('active');
        
        // Sayfa içeriğini yükle
        this.loadPage(page);
        this.currentPage = page;
    }

    async loadPage(page) {
        const pageContent = document.getElementById('pageContent');
        
        try {
            // Loading göster
            pageContent.innerHTML = `
                <div class="loading">
                    <div class="spinner"></div>
                    Sayfa yükleniyor...
                </div>
            `;

            // Sayfa içeriğini yükle
            const response = await fetch(`/page/${page}`);
            if (response.ok) {
                const html = await response.text();
                pageContent.innerHTML = html;
                
                // Sayfa özel script'lerini yükle
                this.loadPageScripts(page);
            } else {
                throw new Error('Sayfa yüklenemedi');
            }
        } catch (error) {
            console.error('Sayfa yükleme hatası:', error);
            pageContent.innerHTML = `
                <div class="empty-state">
                    <i class="fas fa-exclamation-triangle"></i>
                    <h4>Hata Oluştu</h4>
                    <p>Sayfa yüklenirken bir hata oluştu. Lütfen tekrar deneyin.</p>
                </div>
            `;
        }
    }

    // Sayfa yüklendiğinde otomatik olarak özet sayfasını göster
    showSummaryPage() {
        const pageContent = document.getElementById('pageContent');
        pageContent.innerHTML = `
            <div class="summary-page">
                <div class="welcome-section">
                    <h2>Hoş Geldiniz!</h2>
                    <p>Akü İzleme Sistemine hoş geldiniz. Sol menüden istediğiniz bölümü seçebilirsiniz.</p>
                </div>
                
                <div class="quick-stats">
                    <div class="stat-card">
                        <i class="fas fa-battery-three-quarters"></i>
                        <h3>Toplam Batarya</h3>
                        <p class="stat-value">24</p>
                    </div>
                    <div class="stat-card">
                        <i class="fas fa-exclamation-triangle"></i>
                        <h3>Aktif Alarmlar</h3>
                        <p class="stat-value">2</p>
                    </div>
                    <div class="stat-card">
                        <i class="fas fa-chart-line"></i>
                        <h3>Günlük Veri</h3>
                        <p class="stat-value">1,247</p>
                    </div>
                </div>
            </div>
        `;
    }

    // Logs sayfasını göster
    showLogsPage() {
        const pageContent = document.getElementById('pageContent');
        pageContent.innerHTML = `
            <div class="logs-page">
                <!-- Filtreleme Bölümü -->
                <div class="filters-section">
                    <div class="filters-grid">
                        <div class="filter-group">
                            <label for="armFilter">Kol Numarası</label>
                            <input type="text" id="armFilter" placeholder="Kol numarası giriniz" class="filter-input">
                        </div>
                        
                        <div class="filter-group">
                            <label for="batteryFilter">Batarya Adresi</label>
                            <input type="text" id="batteryFilter" placeholder="Batarya adresi giriniz" class="filter-input">
                        </div>
                        
                        <div class="filter-group">
                            <label for="dataTypeFilter">Veri Türü</label>
                            <select id="dataTypeFilter" class="filter-select">
                                <option value="">Tümü</option>
                                <option value="10">Akım/Gerilim</option>
                                <option value="11">Nem/Şarj Durumu</option>
                                <option value="12">Sıcaklık</option>
                                <option value="13">Pozitif Kutup Sıcaklığı</option>
                                <option value="14">Negatif Kutup Sıcaklığı</option>
                                <option value="126">Sağlık Durumu</option>
                            </select>
                        </div>
                        
                        <div class="filter-group">
                            <label for="statusFilter">Durum</label>
                            <select id="statusFilter" class="filter-select">
                                <option value="">Tümü</option>
                                <option value="success">Başarılı</option>
                                <option value="error">Hata</option>
                                <option value="warning">Uyarı</option>
                            </select>
                        </div>
                        
                        <div class="filter-group">
                            <label for="startDate">Başlangıç</label>
                            <input type="date" id="startDate" class="filter-input">
                        </div>
                        
                        <div class="filter-group">
                            <label for="endDate">Bitiş</label>
                            <input type="date" id="endDate" class="filter-input">
                        </div>
                    </div>
                    
                    <div class="filter-actions">
                        <button class="btn btn-secondary" id="clearFilters">
                            <i class="fas fa-times"></i>
                            Filtreleri Temizle
                        </button>
                        <button class="btn btn-primary" id="applyFilters">
                            <i class="fas fa-filter"></i>
                            Filtrele
                        </button>
                    </div>
                </div>

                <!-- Log Tablosu -->
                <div class="logs-table-container">
                    <div class="table-header">
                        <h3>Sistem Logları</h3>
                        <div class="table-actions">
                            <button class="btn btn-outline" id="refreshLogs">
                                <i class="fas fa-sync-alt"></i>
                                Yenile
                            </button>
                            <button class="btn btn-outline" id="exportLogs">
                                <i class="fas fa-download"></i>
                                Dışa Aktar
                            </button>
                        </div>
                    </div>
                    
                    <div class="table-wrapper">
                        <table class="logs-table">
                            <thead>
                                <tr>
                                    <th>ZAMAN</th>
                                    <th>KOL</th>
                                    <th>BATARYA ADRESİ</th>
                                    <th>VERİ TÜRÜ</th>
                                    <th>VERİ</th>
                                    <th>DURUM</th>
                                </tr>
                            </thead>
                            <tbody id="logsTableBody">
                                <!-- Log verileri JavaScript ile doldurulacak -->
                            </tbody>
                        </table>
                    </div>
                    
                    <!-- Sayfalama -->
                    <div class="pagination">
                        <button class="pagination-btn" id="prevPage" disabled>
                            <i class="fas fa-chevron-left"></i>
                            Önceki
                        </button>
                        <span class="page-info">
                            Sayfa <span id="currentPage">1</span> / <span id="totalPages">1</span>
                        </span>
                        <button class="pagination-btn" id="nextPage">
                            Sonraki
                            <i class="fas fa-chevron-right"></i>
                        </button>
                    </div>
                </div>
            </div>
        `;
        
        // Logs sayfası script'lerini yükle
        this.loadPageScripts('logs');
    }

    loadPageScripts(page) {
        // Sayfa özel script'lerini yükle
        const scriptMap = {
            'logs': '/static/js/logs.js',
            'summary': '/static/js/summary.js',
            'alarms': '/static/js/alarms.js',
            'batteries': '/static/js/batteries.js'
        };

        if (scriptMap[page]) {
            // Script zaten yüklenmiş mi kontrol et
            if (document.querySelector(`script[src="${scriptMap[page]}"]`)) {
                // Script zaten var, sadece başlat
                if (window[`${page}Page`]) {
                    window[`${page}Page`].init();
                }
                return;
            }

            const script = document.createElement('script');
            script.src = scriptMap[page];
            script.onload = () => {
                // Script yüklendi, sayfa başlat
                if (window[`${page}Page`]) {
                    window[`${page}Page`].init();
                }
            };
            document.head.appendChild(script);
        }
    }

    setLanguage(lang) {
        this.currentLanguage = lang;
        
        // Dil butonlarını güncelle
        document.querySelectorAll('.lang-btn').forEach(btn => {
            btn.classList.remove('active');
        });
        document.querySelector(`[data-lang="${lang}"]`).classList.add('active');
        
        // Dil değişikliğini localStorage'a kaydet
        localStorage.setItem('language', lang);
        
        // Sayfa metinlerini güncelle
        this.updatePageTexts(lang);
        
        // Mevcut sayfayı yeniden yükle
        this.loadPage(this.currentPage);
    }

    updatePageTexts(lang) {
        // Dil çevirileri
        const translations = {
            tr: {
                'mainTitle': 'Akü İzleme Sistemi',
                'menu': 'MENÜ',
                'summary': 'Özet',
                'lineMeasurements': 'Hat ölçümleri',
                'alarms': 'Alarmlar',
                'batteries': 'Bataryalar',
                'logs': 'Loglar',
                'configuration': 'Konfigürasyon',
                'dataRetrieval': 'Veri Alma',
                'profile': 'Profil',
                'logout': 'Çıkış'
            },
            en: {
                'mainTitle': 'Battery Monitoring System',
                'menu': 'MENU',
                'summary': 'Summary',
                'lineMeasurements': 'Line Measurements',
                'alarms': 'Alarms',
                'batteries': 'Batteries',
                'logs': 'Logs',
                'configuration': 'Configuration',
                'dataRetrieval': 'Data Retrieval',
                'profile': 'Profile',
                'logout': 'Logout'
            }
        };

        const texts = translations[lang] || translations.tr;
        
        // Ana başlık
        document.querySelector('.main-title').textContent = texts.mainTitle;
        
        // Menü öğeleri
        document.querySelectorAll('.nav-link span').forEach((span, index) => {
            const keys = Object.keys(texts).filter(key => key !== 'mainTitle');
            if (keys[index]) {
                span.textContent = texts[keys[index]];
            }
        });
    }

    showNotifications() {
        // Bildirimler modal'ını göster
        console.log('Bildirimler gösteriliyor...');
        // TODO: Bildirim modal'ı implement et
    }

    logout() {
        // Çıkış işlemi
        if (confirm('Çıkış yapmak istediğinizden emin misiniz?')) {
            console.log('Çıkış yapılıyor...');
            // TODO: Çıkış API'si çağır
            window.location.href = '/logout';
        }
    }

    // Utility fonksiyonlar
    showLoading(element) {
        element.innerHTML = `
            <div class="loading">
                <div class="spinner"></div>
                Yükleniyor...
            </div>
        `;
    }

    showError(element, message) {
        element.innerHTML = `
            <div class="empty-state">
                <i class="fas fa-exclamation-triangle"></i>
                <h4>Hata Oluştu</h4>
                <p>${message}</p>
            </div>
        `;
    }

    formatDate(dateString) {
        const date = new Date(dateString);
        return date.toLocaleDateString('tr-TR', {
            year: 'numeric',
            month: '2-digit',
            day: '2-digit',
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit'
        });
    }

    formatNumber(number, decimals = 3) {
        return parseFloat(number).toFixed(decimals);
    }
}

// Uygulama başlat
document.addEventListener('DOMContentLoaded', () => {
    window.app = new App();
});

// Global utility fonksiyonlar
window.utils = {
    formatDate: (dateString) => {
        const date = new Date(dateString);
        return date.toLocaleDateString('tr-TR', {
            year: 'numeric',
            month: '2-digit',
            day: '2-digit',
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit'
        });
    },
    
    formatNumber: (number, decimals = 3) => {
        return parseFloat(number).toFixed(decimals);
    },
    
    showToast: (message, type = 'info') => {
        // Toast bildirimi göster
        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        toast.textContent = message;
        
        document.body.appendChild(toast);
        
        setTimeout(() => {
            toast.remove();
        }, 3000);
    }
};
