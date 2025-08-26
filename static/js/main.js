// Ana JavaScript dosyası
class App {
    constructor() {
        this.currentPage = 'logs';
        this.currentLanguage = 'tr';
        this.init();
    }

    init() {
        this.bindEvents();
        this.loadPage(this.currentPage);
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

    loadPageScripts(page) {
        // Sayfa özel script'lerini yükle
        const scriptMap = {
            'logs': '/static/js/logs.js',
            'summary': '/static/js/summary.js',
            'alarms': '/static/js/alarms.js',
            'batteries': '/static/js/batteries.js'
        };

        if (scriptMap[page]) {
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
