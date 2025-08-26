// Alarms Sayfası JavaScript
class AlarmsPage {
    constructor() {
        this.init();
    }

    init() {
        console.log('Alarms sayfası başlatıldı');
        this.bindEvents();
        this.loadAlarmsData();
    }

    bindEvents() {
        // Event listener'lar buraya eklenebilir
        console.log('Alarms sayfası event listener\'ları bağlandı');
    }

    loadAlarmsData() {
        console.log('Alarm verileri yükleniyor...');
        // Gerçek uygulamada API'den alarm verileri gelecek
    }
}

// Global instance oluştur
window.alarmsPage = new AlarmsPage();
