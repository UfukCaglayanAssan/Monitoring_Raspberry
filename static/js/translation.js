// Translation Manager - i18next benzeri basit bir çözüm
class TranslationManager {
    constructor() {
        this.currentLanguage = localStorage.getItem('language') || 'tr';
        this.translations = {};
        this.initialized = false;
    }

    async init() {
        if (this.initialized) return;
        
        try {
            // Çeviri dosyalarını yükle
            const [trData, enData] = await Promise.all([
                fetch('/static/locales/tr.json').then(r => r.json()),
                fetch('/static/locales/en.json').then(r => r.json())
            ]);
            
            this.translations = {
                tr: trData,
                en: enData
            };
            
            this.initialized = true;
            console.log('✅ TranslationManager başlatıldı');
        } catch (error) {
            console.error('❌ Çeviri dosyaları yüklenirken hata:', error);
            // Hata durumunda boş obje kullan
            this.translations = { tr: {}, en: {} };
        }
    }

    // Çeviri anahtarından değer al (örn: 'menu.summary' -> 'Özet')
    t(key, params = {}) {
        if (!this.initialized) {
            console.warn('TranslationManager henüz başlatılmadı, key:', key);
            return key;
        }

        const keys = key.split('.');
        let value = this.translations[this.currentLanguage];
        
        for (const k of keys) {
            if (value && typeof value === 'object') {
                value = value[k];
            } else {
                console.warn(`Çeviri bulunamadı: ${key}`);
                return key;
            }
        }
        
        // Parametreleri değiştir (örn: {name: 'John'} -> "Hello {name}" -> "Hello John")
        if (typeof value === 'string' && params) {
            return value.replace(/\{(\w+)\}/g, (match, paramKey) => {
                return params[paramKey] !== undefined ? params[paramKey] : match;
            });
        }
        
        return value || key;
    }

    // Dil değiştir
    async setLanguage(language) {
        if (!this.initialized) {
            await this.init();
        }
        
        this.currentLanguage = language;
        localStorage.setItem('language', language);
        
        // Tüm data-i18n attribute'larına sahip elementleri güncelle
        this.updateAllElements();
        
        // languageChanged event'ini tetikle
        window.dispatchEvent(new CustomEvent('languageChanged', {
            detail: { language: language }
        }));
    }

    // Tüm data-i18n attribute'larına sahip elementleri güncelle
    updateAllElements() {
        // Text content için
        const elements = document.querySelectorAll('[data-i18n]');
        elements.forEach(element => {
            const key = element.getAttribute('data-i18n');
            if (key) {
                element.textContent = this.t(key);
            }
        });
        
        // Placeholder için
        const placeholderElements = document.querySelectorAll('[data-i18n-placeholder]');
        placeholderElements.forEach(element => {
            const key = element.getAttribute('data-i18n-placeholder');
            if (key) {
                element.placeholder = this.t(key);
            }
        });
    }

    // Belirli bir elementi güncelle
    updateElement(selector, key) {
        const element = document.querySelector(selector);
        if (element) {
            element.textContent = this.t(key);
        }
    }

    // Mevcut dili al
    getLanguage() {
        return this.currentLanguage;
    }
}

// Global instance
window.translationManager = new TranslationManager();

// Sayfa yüklendiğinde otomatik başlat
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        window.translationManager.init();
    });
} else {
    window.translationManager.init();
}

