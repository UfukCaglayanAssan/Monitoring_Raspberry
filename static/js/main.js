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
            console.log('🔗 Event listener\'lar bağlanıyor...');
            
            // Ana menü linkleri
        document.querySelectorAll('.nav-link').forEach(link => {
            link.addEventListener('click', (e) => {
                e.preventDefault();
                    e.stopPropagation();
                    
                    const timestamp = new Date().toISOString();
                    const page = e.target.getAttribute('data-page');
                    const toggle = e.target.getAttribute('data-toggle');
                    
                    console.log(`🖱️ [${timestamp}] MENÜ TIKLAMA - Ana menü link tıklandı:`, {
                        page: page,
                        toggle: toggle,
                        text: e.target.textContent.trim(),
                        element: e.target.tagName
                    });
                    
                    if (page) {
                        console.log(`📄 [${timestamp}] SAYFA YÜKLEME - Sayfa yükleniyor: ${page}`);
                        this.loadPage(page);
                    } else if (toggle === 'submenu') {
                        console.log(`📂 [${timestamp}] SUBMENU AÇMA - Alt menü açılıyor`);
                        this.toggleSubmenu(e.target);
                    }
                });
            });

            // Submenu linklerini dinle
        document.querySelectorAll('.submenu-link').forEach(link => {
            link.addEventListener('click', (e) => {
                e.preventDefault();
                e.stopPropagation();
                const timestamp = new Date().toISOString();
                
                // Tıklanan elementin kendisi veya parent'ından data-page'i al
                let targetElement = e.target;
                let page = targetElement.getAttribute('data-page');
                
                // Eğer span'a tıklandıysa, parent a elementini bul
                if (!page && targetElement.tagName === 'SPAN') {
                    targetElement = targetElement.closest('.submenu-link');
                    page = targetElement ? targetElement.getAttribute('data-page') : null;
                }
                
                console.log(`🖱️ [${timestamp}] SUBMENU TIKLAMA - Alt menü link tıklandı:`, {
                    page: page,
                    text: e.target.textContent.trim(),
                    targetElement: e.target.tagName,
                    linkElement: targetElement ? targetElement.tagName : 'null'
                });
                
                if (page) {
                    console.log(`📄 [${timestamp}] SAYFA YÜKLEME - Alt menüden sayfa yükleniyor: ${page}`);
                    this.loadPage(page);
                } else {
                    console.warn(`⚠️ [${timestamp}] SUBMENU HATASI - data-page bulunamadı!`);
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
        const timestamp = new Date().toISOString();
        const navItem = link.closest('.nav-item');
        const submenu = navItem.querySelector('.submenu');
        const arrow = navItem.querySelector('.submenu-arrow');
        
        console.log(`📂 [${timestamp}] SUBMENU TOGGLE - Alt menü durumu değiştiriliyor`);
        
        if (submenu) {
            // Toggle submenu visibility
            if (submenu.style.display === 'block') {
                console.log(`📤 [${timestamp}] SUBMENU KAPATILIYOR - Alt menü kapatılıyor`);
                submenu.style.display = 'none';
                arrow.style.transform = 'rotate(0deg)';
            } else {
                console.log(`📥 [${timestamp}] SUBMENU AÇILIYOR - Alt menü açılıyor`);
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
        } else {
            console.warn(`⚠️ [${timestamp}] SUBMENU BULUNAMADI - Alt menü elementi bulunamadı`);
        }
    }

    async loadPage(page) {
        const timestamp = new Date().toISOString();
        
        // Çift yükleme kontrolü
        if (this.currentPage === page && this.isLoading) {
            console.log(`⚠️ [${timestamp}] ÇİFT YÜKLEME ENGELLENDİ - ${page} zaten yükleniyor`);
            return;
        }
        
        this.isLoading = true;
        console.log(`🔄 [${timestamp}] SAYFA YÜKLEME BAŞLADI - Sayfa: ${page}`);
        
        const pageContent = document.getElementById('pageContent');
        const startTime = performance.now();
        
        try {
            // Loading göster
            console.log(`⏳ [${timestamp}] LOADING ANİMASYONU - Loading spinner gösteriliyor`);
            pageContent.innerHTML = `
                <div class="loading">
                    <div class="spinner"></div>
                    Sayfa yükleniyor...
                </div>
            `;

            // Sayfa içeriğini yükle
            console.log(`📡 [${timestamp}] HTTP İSTEĞİ - /pages/${page}.html fetch ediliyor`);
            const response = await fetch(`/pages/${page}.html`);
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            
                const html = await response.text();
            const loadTime = performance.now() - startTime;
            console.log(`📄 [${timestamp}] HTML ALINDI - Uzunluk: ${html.length}, Süre: ${loadTime.toFixed(2)}ms`);
            
                pageContent.innerHTML = html;
            console.log(`✅ [${timestamp}] SAYFA YÜKLENDİ - ${page} başarıyla yüklendi`);
                
            // Aktif menüyü güncelle
            console.log(`🎯 [${timestamp}] MENÜ GÜNCELLEME - Aktif menü güncelleniyor: ${page}`);
            this.updateActiveMenu(page);
            
            // Sayfa özel JavaScript'ini yükle
            this.loadPageScript(page);
            
            this.currentPage = page;
            this.isLoading = false;
            console.log('Page loaded:', page);
            
        } catch (error) {
            console.error('Sayfa yüklenirken hata:', error);
            this.isLoading = false;
            pageContent.innerHTML = `
                <div class="error">
                    <h3>Sayfa yüklenemedi</h3>
                    <p>Lütfen sayfayı yenileyin veya daha sonra tekrar deneyin.</p>
                </div>
            `;
        }
    }

    loadPageScript(page) {
        const timestamp = new Date().toISOString();
        console.log(`📜 [${timestamp}] SCRIPT YÜKLEME BAŞLADI - Sayfa: ${page}`);
        
        // Mevcut script'i kaldır
        const existingScript = document.getElementById('page-script');
        if (existingScript) {
            console.log(`🗑️ [${timestamp}] ESKİ SCRIPT KALDIRILIYOR - Mevcut script temizleniyor`);
            existingScript.remove();
        }

        // Yeni script'i yükle
        const script = document.createElement('script');
        script.id = 'page-script';
        script.src = `/static/js/${page}.js`;
        console.log(`📡 [${timestamp}] SCRIPT FETCH EDİLİYOR - /static/js/${page}.js`);
        
        const scriptStartTime = performance.now();
        
        script.onload = () => {
            const scriptLoadTime = performance.now() - scriptStartTime;
            console.log(`✅ [${timestamp}] SCRIPT YÜKLENDİ - ${page}.js (${scriptLoadTime.toFixed(2)}ms)`);
            // Sayfa özel init fonksiyonunu çağır
            console.log(`🚀 [${timestamp}] INIT FONKSİYONLARI ÇAĞRILIYOR - ${page} için init fonksiyonları`);
            this.initPageSpecificFunctions(page);
        };
        script.onerror = () => {
            console.error(`❌ [${timestamp}] SCRIPT YÜKLEME HATASI - ${page}.js yüklenemedi`);
        };
        document.head.appendChild(script);
    }

    initPageSpecificFunctions(page) {
        const timestamp = new Date().toISOString();
        console.log(`🔧 [${timestamp}] INIT FONKSİYONLARI BAŞLADI - Sayfa: ${page}`);
        
        // Sayfa özel init fonksiyonlarını çağır
        if (page === 'data-retrieval') {
            console.log('🚀 Calling initDataRetrievalPage');
            if (typeof initDataRetrievalPage === 'function') {
                initDataRetrievalPage();
                console.log('✅ initDataRetrievalPage called successfully');
            } else {
                console.warn('⚠️ initDataRetrievalPage function not found');
            }
        } else if (page === 'line-measurements') {
            console.log('🚀 Calling initLineMeasurementsPage');
            if (typeof initLineMeasurementsPage === 'function') {
                initLineMeasurementsPage();
                console.log('✅ initLineMeasurementsPage called successfully');
            } else {
                console.warn('⚠️ initLineMeasurementsPage function not found');
            }
        } else if (page === 'battery-logs') {
            console.log('🚀 Calling initBatteryLogsPage');
            if (typeof initBatteryLogsPage === 'function') {
                initBatteryLogsPage();
                console.log('✅ initBatteryLogsPage called successfully');
            } else {
                console.warn('⚠️ initBatteryLogsPage function not found');
            }
        } else if (page === 'arm-logs') {
            console.log('🚀 Calling initArmLogsPage');
            if (typeof initArmLogsPage === 'function') {
                initArmLogsPage();
                console.log('✅ initArmLogsPage called successfully');
            } else {
                console.warn('⚠️ initArmLogsPage function not found');
            }
        } else if (page === 'alarms') {
            console.log('🚀 Calling initAlarmsPage');
            if (typeof initAlarmsPage === 'function') {
                initAlarmsPage();
                console.log('✅ initAlarmsPage called successfully');
            } else {
                console.warn('⚠️ initAlarmsPage function not found');
            }
        } else if (page === 'summary') {
            console.log('🚀 Calling initSummaryPage');
            if (typeof initSummaryPage === 'function') {
                initSummaryPage();
                console.log('✅ initSummaryPage called successfully');
            } else {
                console.warn('⚠️ initSummaryPage function not found');
            }
        } else if (page === 'batteries') {
            console.log('🚀 Calling initBatteriesPage');
            if (typeof initBatteriesPage === 'function') {
                initBatteriesPage();
                console.log('✅ initBatteriesPage called successfully');
            } else {
                console.warn('⚠️ initBatteriesPage function not found');
            }
        } else if (page === 'configuration') {
            console.log('🚀 Calling initConfigurationPage');
            if (typeof initConfigurationPage === 'function') {
                initConfigurationPage();
                console.log('✅ initConfigurationPage called successfully');
                } else {
                console.warn('⚠️ initConfigurationPage function not found');
            }
                    } else {
            console.log(`❌ No init function found for ${page}`);
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