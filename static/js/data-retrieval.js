// Data Retrieval Sayfası JavaScript
class DataRetrievalPage {
    constructor() {
        this.init();
    }

    init() {
        console.log('Data Retrieval sayfası başlatıldı');
        this.bindEvents();
    }

    bindEvents() {
        // Event listener'lar buraya eklenebilir
        console.log('Data Retrieval sayfası event listener\'ları bağlandı');
    }
}

// Global instance oluştur
window.dataRetrievalPage = new DataRetrievalPage();

// Global init fonksiyonu
function initDataRetrievalPage() {
    console.log('🔧 initDataRetrievalPage() çağrıldı');
    if (!window.dataRetrievalPage) {
        window.dataRetrievalPage = new DataRetrievalPage();
    } else {
        console.log('🔄 Mevcut DataRetrievalPage instance yeniden başlatılıyor');
        window.dataRetrievalPage.init();
    }
}

// Global olarak erişilebilir yap
window.initDataRetrievalPage = initDataRetrievalPage;

// Script yüklendiğinde otomatik init
console.log('🔧 Data-retrieval.js yüklendi, otomatik init başlatılıyor...');
initDataRetrievalPage();

