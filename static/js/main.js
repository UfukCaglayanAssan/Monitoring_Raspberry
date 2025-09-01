// Ana JavaScript dosyası
class App {
    constructor() {
        this.currentPage = 'summary';
        this.currentLanguage = 'tr';
        this.init();
    }

    init() {
        this.bindEvents();
        this.loadPage('summary'); // İlk sayfa olarak özet'i yükle
        this.setLanguage(this.currentLanguage);
    }

    bindEvents() {
        // Menü navigasyonu
        document.querySelectorAll('.nav-link').forEach(link => {
            link.addEventListener('click', (e) => {
                e.preventDefault();
                const page = e.currentTarget.dataset.page;
                
                // Eğer sub menü varsa, önce sub menüyü aç/kapat
                const navItem = e.currentTarget.closest('.nav-item');
                if (navItem && navItem.classList.contains('has-submenu')) {
                    this.toggleSubmenu(navItem);
                    return; // Sayfa değiştirme, sadece sub menüyü aç/kapat
                }
                
                this.navigateToPage(page);
            });
        });

        // Sub menü navigasyonu
        document.querySelectorAll('.submenu-link').forEach(link => {
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

    toggleSubmenu(navItem) {
        // Diğer tüm sub menüleri kapat
        document.querySelectorAll('.nav-item.has-submenu').forEach(item => {
            if (item !== navItem) {
                item.classList.remove('expanded');
            }
        });
        
        // Bu sub menüyü aç/kapat
        navItem.classList.toggle('expanded');
    }

    navigateToPage(page) {
        console.log('Navigating to page:', page);
        
        // Aktif menü öğesini güncelle
        document.querySelectorAll('.nav-link').forEach(link => {
            link.classList.remove('active');
        });
        
        const activeLink = document.querySelector(`[data-page="${page}"]`);
        if (activeLink) {
            activeLink.classList.add('active');
        }
        
        // Sayfa içeriğini yükle
        this.loadPage(page);
        this.currentPage = page;
    }

    async loadPage(page) {
        console.log('Loading page:', page);
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
            console.log('Response status:', response.status);
            
            if (response.ok) {
                const html = await response.text();
                console.log('HTML loaded, length:', html.length);
                pageContent.innerHTML = html;
                
                // Sayfa özel script'lerini yükle
                this.loadPageScripts(page);
            } else {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
        } catch (error) {
            console.error('Sayfa yükleme hatası:', error);
            pageContent.innerHTML = `
                <div class="empty-state">
                    <i class="fas fa-exclamation-triangle"></i>
                    <h4>Hata Oluştu</h4>
                    <p>Sayfa yüklenirken bir hata oluştu: ${error.message}</p>
                    <p>Lütfen tekrar deneyin.</p>
                </div>
            `;
        }
    }

    loadPageScripts(page) {
        console.log('Loading scripts for page:', page);
        
        // Sayfa özel script'lerini yükle
        const scriptMap = {
            'battery-logs': '/static/js/battery-logs.js',
            'arm-logs': '/static/js/arm-logs.js',
            'summary': '/static/js/summary.js',
            'alarms': '/static/js/alarms.js',
            'batteries': '/static/js/batteries.js',
            'configuration': '/static/js/configuration.js',
            'profile': '/static/js/profile.js'
        };

        if (scriptMap[page]) {
            // Script zaten yüklenmiş mi kontrol et
            if (document.querySelector(`script[src="${scriptMap[page]}"]`)) {
                console.log('Script already loaded:', page);
                // Script zaten var, sadece başlat
                if (window[`${page}Page`]) {
                    window[`${page}Page`].init();
                }
                return;
            }

            console.log('Loading script:', scriptMap[page]);
            const script = document.createElement('script');
            script.src = scriptMap[page];
            script.onload = () => {
                console.log('Script loaded:', page);
                // Script yüklendi, sayfa başlat
                if (window[`${page}Page`]) {
                    window[`${page}Page`].init();
                } else if (window[`init${page.charAt(0).toUpperCase() + page.slice(1).replace('-', '')}Page`]) {
                    // Özel init fonksiyonu varsa çağır
                    const initFunctionName = `init${page.charAt(0).toUpperCase() + page.slice(1).replace('-', '')}Page`;
                    window[initFunctionName]();
                }
            };
            script.onerror = () => {
                console.error('Script load error:', scriptMap[page]);
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
        
        // Dil değişikliği event'ini tetikle
        window.dispatchEvent(new CustomEvent('languageChanged', { detail: { language: lang } }));
    }

    updatePageTexts(lang) {
        // Dil çevirileri
        const translations = {
            tr: {
                'mainTitle': 'Akü İzleme Sistemi',
                'menu': 'MENÜ',
                'summary': 'Özet',
                'alarms': 'Alarmlar',
                'batteries': 'Bataryalar',
                'logs': 'Loglar',
                'configuration': 'Konfigürasyon',
                'profile': 'Profil',
                'logout': 'Çıkış'
            },
            en: {
                'mainTitle': 'Battery Monitoring System',
                'menu': 'MENU',
                'summary': 'Summary',
                'alarms': 'Alarms',
                'batteries': 'Batteries',
                'logs': 'Logs',
                'configuration': 'Configuration',
                'profile': 'Profile',
                'logout': 'Logout'
            }
        };

        const texts = translations[lang] || translations.tr;
        
        // Ana başlık
        const mainTitle = document.querySelector('.main-title');
        if (mainTitle) {
            mainTitle.textContent = texts.mainTitle;
        }

        // Menü başlığı
        const menuHeader = document.querySelector('.sidebar-header h3');
        if (menuHeader) {
            menuHeader.textContent = texts.menu;
        }

        // Menü öğeleri
        const menuItems = {
            'summary': texts.summary,
            'alarms': texts.alarms,
            'batteries': texts.batteries,
            'logs': texts.logs,
            'configuration': texts.configuration,
            'profile': texts.profile,
            'logout': texts.logout
        };

        Object.entries(menuItems).forEach(([page, text]) => {
            const menuLink = document.querySelector(`[data-page="${page}"] span`);
            if (menuLink) {
                menuLink.textContent = text;
            }
        });
    }

    showNotifications() {
        // Bildirimler modal'ını göster
        console.log('Bildirimler gösteriliyor...');
        alert('Bildirimler özelliği henüz eklenmedi.');
    }

    logout() {
        // Çıkış işlemi
        if (confirm('Çıkış yapmak istediğinizden emin misiniz?')) {
            console.log('Çıkış yapılıyor...');
            alert('Çıkış özelliği henüz eklenmedi.');
        }
    }
}

// Uygulama başlat
document.addEventListener('DOMContentLoaded', () => {
    console.log('App starting...');
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
        toast.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            background: #333;
            color: white;
            padding: 1rem;
            border-radius: 8px;
            z-index: 10000;
        `;
        
        document.body.appendChild(toast);
        
        setTimeout(() => {
            toast.remove();
        }, 3000);
    }
};
