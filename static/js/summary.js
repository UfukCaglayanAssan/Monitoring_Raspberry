// Summary Sayfası JavaScript
class SummaryPage {
    constructor() {
        this.init();
    }

    init() {
        console.log('Summary sayfası başlatıldı');
        this.bindEvents();
        this.loadSummaryData();
    }

    bindEvents() {
        // Event listener'lar buraya eklenebilir
        console.log('Summary sayfası event listener\'ları bağlandı');
    }

    loadSummaryData() {
        console.log('Özet verileri yükleniyor...');
        
        // Örnek veri - gerçek uygulamada API'den gelecek
        this.updateStats({
            totalBatteries: 24,
            activeAlarms: 2,
            dailyData: 1247
        });
    }

    updateStats(data) {
        // İstatistik kartlarını güncelle
        const statCards = document.querySelectorAll('.stat-value');
        if (statCards.length >= 3) {
            statCards[0].textContent = data.totalBatteries;
            statCards[1].textContent = data.activeAlarms;
            statCards[2].textContent = data.dailyData;
        }
        
        console.log('Özet istatistikleri güncellendi:', data);
    }
}

// Global instance oluştur
window.summaryPage = new SummaryPage();
