// Ana JavaScript dosyası
class App {
    constructor() {
        // localStorage'dan son sayfayı oku, yoksa summary
        this.currentPage = localStorage.getItem('lastPage') || 'summary';
        this.currentLanguage = 'tr';
        this.alarmCountInterval = null; // Interval referansı
        
        // F5 ile yenileme kontrolü
        window.addEventListener('pageshow', function(e) {
            console.log(' PAGESHOW EVENT TETİKLENDİ:', {
                persisted: e.persisted,
                currentPage: this.currentPage,
                lastPage: localStorage.getItem('lastPage')
            });
            
            if (!e.persisted) {
                // Sayfa yeniden yüklendi (F5, Ctrl+R, adres çubuğu)
                console.log(' Sayfa yeniden yüklendi, sayfa yeniden yükleniyor');
                const lastPage = localStorage.getItem('lastPage') || 'summary';
                this.currentPage = null; // ← BUNU EKLE
                this.loadPage(lastPage); // ← BUNU EKLE
            } else {
                console.log(' Sayfa cache\'den yüklendi (geri/ileri butonları)');
            }
        }.bind(this));
        
        // Sayfa kapatıldığında localStorage'ı sıfırla
        window.addEventListener('beforeunload', function() {
            localStorage.removeItem('lastPage');
        });
        
        this.init();
    }

    init() {
        this.bindEvents();
        this.loadPage(this.currentPage); // localStorage'dan gelen sayfa veya summary
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
                
                // Tıklanan element A ise direkt al, değilse parent A'yı bul
                let targetElement = e.target;
                if (targetElement.tagName !== 'A') {
                    targetElement = targetElement.closest('a');
                }
                
                const page = targetElement ? targetElement.getAttribute('data-page') : null;
                const toggle = targetElement ? targetElement.getAttribute('data-toggle') : null;
                
                console.log(`🖱️ [${timestamp}] MENÜ TIKLAMA - Ana menü link tıklandı:`, {
                    page: page,
                    toggle: toggle,
                    text: e.target.textContent.trim(),
                    element: e.target.tagName,
                    targetElement: targetElement ? targetElement.tagName : 'null'
                });
                
                if (page) {
                    console.log(`📄 [${timestamp}] SAYFA YÜKLEME - Sayfa yükleniyor: ${page}`);
                    this.loadPage(page);
                } else if (toggle === 'submenu') {
                    console.log(`📂 [${timestamp}] SUBMENU AÇMA - Alt menü açılıyor`);
                    this.toggleSubmenu(targetElement || e.target);
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

        if (this.currentPage === page && !this.isLoading) {
            console.log(`⚠️ [${timestamp}] AYNI SAYFA - ${page} zaten açık, iptal edildi`);
            return;
        }
        
        this.isLoading = true;
        console.log(`🔄 [${timestamp}] SAYFA YÜKLEME BAŞLADI - Sayfa: ${page}`);
        
        const pageContent = document.getElementById('pageContent');
        const startTime = performance.now();
        
        try {
            // Loading animasyonu kaldırıldı - sayfa kendi loading'ini gösterir

            // Sayfa içeriğini yükle
            let pageUrl;
            if (page === 'mail-management') {
                pageUrl = '/mail-management';
            } else {
                pageUrl = `/pages/${page}.html`;
            }
            
            console.log(`📡 [${timestamp}] HTTP İSTEĞİ - ${pageUrl} fetch ediliyor`);
            const response = await fetch(pageUrl);
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
            
            // Son sayfayı localStorage'a kaydet
            localStorage.setItem('lastPage', page);
            
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
            // Script yüklendikten sonra otomatik init yapılacak (script içinde)
            console.log(`🎯 [${timestamp}] SCRIPT YÜKLENDİ - Otomatik init bekleniyor...`);
            };
            script.onerror = () => {
            console.error(`❌ [${timestamp}] SCRIPT YÜKLEME HATASI - ${page}.js yüklenemedi`);
            };
            document.head.appendChild(script);
    }

    // initPageSpecificFunctions kaldırıldı - script'ler otomatik init yapıyor

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
        // Önceki interval'ı temizle
        if (this.alarmCountInterval) {
            clearInterval(this.alarmCountInterval);
            console.log('🧹 Önceki alarm count interval temizlendi');
        }
        
        // İlk yükleme
        this.updateAlarmCount();
        
        // Her 30 saniyede bir güncelle
        this.alarmCountInterval = setInterval(() => {
            this.updateAlarmCount();
        }, 30000);
        
        console.log('⏰ Yeni alarm count interval başlatıldı (30s)');
    }
}

// Uygulamayı başlat
document.addEventListener('DOMContentLoaded', () => {
    window.app = new App();
});