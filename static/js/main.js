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
        // Menü navigasyonu - sadece bir kez ekle
        if (!this.eventsBound) {
        document.querySelectorAll('.nav-link').forEach(link => {
            link.addEventListener('click', (e) => {
                e.preventDefault();
                    const page = e.target.getAttribute('data-page');
                    const toggle = e.target.getAttribute('data-toggle');
                    
                    if (page) {
                        this.loadPage(page);
                    } else if (toggle === 'submenu') {
                        this.toggleSubmenu(e.target);
                    }
                });
            });

            // Submenu linklerini dinle
        document.querySelectorAll('.submenu-link').forEach(link => {
            link.addEventListener('click', (e) => {
                e.preventDefault();
                    const page = e.target.getAttribute('data-page');
                    if (page) {
                        this.loadPage(page);
                    }
                });
            });
            
            this.eventsBound = true;
        }

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

    toggleSubmenu(link) {
        const navItem = link.closest('.nav-item');
        const submenu = navItem.querySelector('.submenu');
        const arrow = navItem.querySelector('.submenu-arrow');
        
        if (submenu) {
            // Toggle submenu visibility
            if (submenu.style.display === 'block') {
                submenu.style.display = 'none';
                arrow.style.transform = 'rotate(0deg)';
            } else {
                // Close other submenus first
                document.querySelectorAll('.submenu').forEach(menu => {
                    menu.style.display = 'none';
                });
                document.querySelectorAll('.submenu-arrow').forEach(arr => {
                    arr.style.transform = 'rotate(0deg)';
                });
                
                // Open current submenu
                submenu.style.display = 'block';
                arrow.style.transform = 'rotate(180deg)';
            }
        }
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
        if (page === 'data-retrieval') {
            console.log('Calling initDataRetrievalPage');
            if (!window.dataRetrievalPageInitialized) {
                // Direkt fonksiyon çağrısı
                if (typeof initDataRetrievalPage === 'function') {
                    initDataRetrievalPage();
                    window.dataRetrievalPageInitialized = true;
                }
            }
        } else if (page === 'line-measurements') {
            console.log('Calling initLineMeasurementsPage');
            if (!window.lineMeasurementsPageInitialized) {
                // Direkt fonksiyon çağrısı
                if (typeof initLineMeasurementsPage === 'function') {
                    initLineMeasurementsPage();
                    window.lineMeasurementsPageInitialized = true;
                }
            }
        } else if (page === 'battery-logs') {
                        console.log('Calling initBatteryLogsPage');
                        if (!window.batteryLogsPageInitialized) {
                            // Direkt fonksiyon çağrısı
                            if (typeof initBatteryLogsPage === 'function') {
                                initBatteryLogsPage();
                                window.batteryLogsPageInitialized = true;
                            }
                        }
                    } else if (page === 'arm-logs') {
                        console.log('Calling initArmLogsPage');
                        if (!window.armLogsPageInitialized) {
                            // Direkt fonksiyon çağrısı
                            if (typeof initArmLogsPage === 'function') {
                                initArmLogsPage();
                                window.armLogsPageInitialized = true;
                            }
                        }
        } else if (page === 'alarms') {
            console.log('Calling initAlarmsPage');
            // Sadece bir kez çağır
            if (!window.alarmsPageInitialized) {
                // Direkt fonksiyon çağrısı
                if (typeof initAlarmsPage === 'function') {
                    initAlarmsPage();
                    window.alarmsPageInitialized = true;
                }
            }
        } else if (page === 'summary') {
            console.log('Calling initSummaryPage');
            // Sadece bir kez çağır
            if (!window.summaryPageInitialized) {
                // Direkt fonksiyon çağrısı
                if (typeof initSummaryPage === 'function') {
                    initSummaryPage();
                    window.summaryPageInitialized = true;
                }
            }
        } else if (page === 'batteries') {
            console.log('Calling initBatteriesPage');
            // Sadece bir kez çağır
            if (!window.batteriesPageInitialized) {
                // Direkt fonksiyon çağrısı
                if (typeof initBatteriesPage === 'function') {
                    initBatteriesPage();
                    window.batteriesPageInitialized = true;
                }
            }
        } else if (page === 'configuration') {
            console.log('Calling initConfigurationPage');
            // Sadece bir kez çağır
            if (!window.configurationPageInitialized) {
                // Direkt fonksiyon çağrısı
                if (typeof initConfigurationPage === 'function') {
                    initConfigurationPage();
                    window.configurationPageInitialized = true;
                }
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
            const response = await fetch('/api/alarm_count', {
                method: 'GET',
                headers: {
                    'Content-Type': 'application/json'
                }
            });

            if (response.ok) {
                const data = await response.json();
                const alarmCount = data.count || 0;
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