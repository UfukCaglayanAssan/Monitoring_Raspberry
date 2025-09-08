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
        this.startAlarmCountRefresh(); // Alarm sayısı güncellemeyi başlat
    }

    bindEvents() {
        // Menü navigasyonu
        document.querySelectorAll('.nav-link').forEach(link => {
            link.addEventListener('click', (e) => {
                e.preventDefault();
                const page = e.target.getAttribute('data-page');
                if (page) {
                    this.loadPage(page);
                }
            });
        });

        // Dil değiştirme
        document.querySelectorAll('.language-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.preventDefault();
                const lang = e.target.getAttribute('data-lang');
                if (lang) {
                    this.setLanguage(lang);
                }
            });
        });
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
            const response = await fetch(`/pages/${page}.html`);
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            
            const html = await response.text();
            pageContent.innerHTML = html;
            
            // Aktif menüyü güncelle
            this.updateActiveMenu(page);
            
            // Sayfa özel JavaScript'ini yükle
            this.loadPageScript(page);
            
            this.currentPage = page;
            console.log('Page loaded:', page);
            
        } catch (error) {
            console.error('Sayfa yüklenirken hata:', error);
            pageContent.innerHTML = `
                <div class="error">
                    <h3>Sayfa yüklenemedi</h3>
                    <p>Lütfen sayfayı yenileyin veya daha sonra tekrar deneyin.</p>
                </div>
            `;
        }
    }

    loadPageScript(page) {
        // Mevcut script'i kaldır
        const existingScript = document.getElementById('page-script');
        if (existingScript) {
            existingScript.remove();
        }

        // Yeni script'i yükle
        const script = document.createElement('script');
        script.id = 'page-script';
        script.src = `/static/js/${page}.js`;
        script.onload = () => {
            console.log(`Script loaded: ${page}.js`);
            // Sayfa özel init fonksiyonunu çağır
            this.initPageSpecificFunctions(page);
        };
        script.onerror = () => {
            console.error(`Script load failed: ${page}.js`);
        };
        document.head.appendChild(script);
    }

    initPageSpecificFunctions(page) {
        // Sayfa özel init fonksiyonlarını çağır
        if (page === 'data-retrieval' && window.initDataRetrievalPage) {
            console.log('Calling initDataRetrievalPage');
            window.initDataRetrievalPage();
        } else if (page === 'line-measurements' && window.initLineMeasurementsPage) {
            console.log('Calling initLineMeasurementsPage');
            window.initLineMeasurementsPage();
        } else if (page === 'battery-logs' && window.initBatteryLogsPage) {
            console.log('Calling initBatteryLogsPage');
            window.initBatteryLogsPage();
        } else if (page === 'arm-logs' && window.initArmLogsPage) {
            console.log('Calling initArmLogsPage');
            window.initArmLogsPage();
        } else if (page === 'alarms' && window.initAlarmsPage) {
            console.log('Calling initAlarmsPage');
            if (document.querySelector('.alarms-page')) {
                window.initAlarmsPage();
            } else {
                console.log('Alarms page element not found, retrying...');
                setTimeout(() => {
                    if (document.querySelector('.alarms-page')) {
                        window.initAlarmsPage();
                    }
                }, 50);
            }
        } else if (page === 'summary' && window.initSummaryPage) {
            console.log('Calling initSummaryPage');
            if (document.querySelector('.summary-page')) {
                window.initSummaryPage();
            } else {
                console.log('Summary page element not found, retrying...');
                setTimeout(() => {
                    if (document.querySelector('.summary-page')) {
                        window.initSummaryPage();
                    }
                }, 50);
            }
        } else if (page === 'batteries' && window.initBatteriesPage) {
            console.log('Calling initBatteriesPage');
            if (document.querySelector('.batteries-page')) {
                window.initBatteriesPage();
            } else {
                console.log('Batteries page element not found, retrying...');
                setTimeout(() => {
                    if (document.querySelector('.batteries-page')) {
                        window.initBatteriesPage();
                    }
                }, 50);
            }
        } else if (page === 'configuration' && window.initConfigurationPage) {
            console.log('Calling initConfigurationPage');
            if (document.querySelector('.configuration-page')) {
                window.initConfigurationPage();
            } else {
                console.log('Configuration page element not found, retrying...');
                setTimeout(() => {
                    if (document.querySelector('.configuration-page')) {
                        window.initConfigurationPage();
                    }
                }, 50);
            }
        } else {
            console.log(`No init function found for ${page}`);
        }
    }

    updateActiveMenu(page) {
        // Tüm menü linklerini pasif yap
        document.querySelectorAll('.nav-link').forEach(link => {
            link.classList.remove('active');
        });
        
        // Aktif sayfa linkini aktif yap
        const activeLink = document.querySelector(`[data-page="${page}"]`);
        if (activeLink) {
            activeLink.classList.add('active');
        }
    }

    setLanguage(lang) {
        this.currentLanguage = lang;
        
        // Dil butonlarını güncelle
        document.querySelectorAll('.language-btn').forEach(btn => {
            btn.classList.remove('active');
            if (btn.getAttribute('data-lang') === lang) {
                btn.classList.add('active');
            }
        });
        
        // Sayfa içeriğini yeniden yükle
        this.loadPage(this.currentPage);
    }

    showToast(message, type = 'info') {
        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        toast.textContent = message;
        
        document.body.appendChild(toast);
        
        // Animasyon için kısa gecikme
        setTimeout(() => {
            toast.classList.add('show');
        }, 100);
        
        // 3 saniye sonra kaldır
        setTimeout(() => {
            toast.classList.remove('show');
            setTimeout(() => {
                toast.remove();
            }, 300);
        }, 3000);
    }

    // Alarm sayısı güncelleme
    async updateAlarmCount() {
        try {
            const response = await fetch('/api/alarms?show_resolved=false&page=1&pageSize=1', {
                method: 'GET',
                headers: {
                    'Content-Type': 'application/json'
                }
            });

            if (response.ok) {
                const data = await response.json();
                const alarmCount = data.totalCount || 0;
                this.displayAlarmCount(alarmCount);
            } else {
                console.error('Alarm sayısı alınamadı:', response.status);
            }
        } catch (error) {
            console.error('Alarm sayısı güncellenirken hata:', error);
        }
    }

    displayAlarmCount(count) {
        const badge = document.getElementById('alarmCount');
        if (badge) {
            if (count > 0) {
                badge.textContent = count;
                badge.style.display = 'inline';
            } else {
                badge.style.display = 'none';
            }
        }
    }

    startAlarmCountRefresh() {
        // İlk yükleme
        this.updateAlarmCount();
        
        // Her 30 saniyede bir güncelle
        setInterval(() => {
            this.updateAlarmCount();
        }, 30000);
    }
}

// Uygulamayı başlat
document.addEventListener('DOMContentLoaded', () => {
    window.app = new App();
});