// Line Measurements Sayfası JavaScript
class LineMeasurementsPage {
    constructor() {
        this.init();
    }

    init() {
        console.log('Line Measurements sayfası başlatıldı');
        this.bindEvents();
        this.loadMeasurementsData();
    }

    bindEvents() {
        // Event listener'lar buraya eklenebilir
        console.log('Line Measurements sayfası event listener\'ları bağlandı');
    }

    loadMeasurementsData() {
        console.log('Hat ölçüm verileri yükleniyor...');
        // Gerçek uygulamada API'den ölçüm verileri gelecek
    }
}

// Global instance oluştur
window.lineMeasurementsPage = new LineMeasurementsPage();

// Global init fonksiyonu
function initLineMeasurementsPage() {
    console.log('🔧 initLineMeasurementsPage() çağrıldı');
    if (!window.lineMeasurementsPage) {
        window.lineMeasurementsPage = new LineMeasurementsPage();
    } else {
        console.log('🔄 Mevcut LineMeasurementsPage instance yeniden başlatılıyor');
        window.lineMeasurementsPage.init();
    }
}

// Global olarak erişilebilir yap
window.initLineMeasurementsPage = initLineMeasurementsPage;

// Script yüklendiğinde otomatik init
console.log('🔧 Line-measurements.js yüklendi, otomatik init başlatılıyor...');
initLineMeasurementsPage();



