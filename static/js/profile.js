// Profile Sayfası JavaScript
class ProfilePage {
    constructor() {
        this.init();
    }

    init() {
        console.log('Profile sayfası başlatıldı');
        this.bindEvents();
        this.loadProfileData();
    }

    bindEvents() {
        // Event listener'lar buraya eklenebilir
        console.log('Profile sayfası event listener\'ları bağlandı');
    }

    loadProfileData() {
        console.log('Profil verileri yükleniyor...');
        // Gerçek uygulamada API'den profil verileri gelecek
    }
}

// Global instance oluştur
window.profilePage = new ProfilePage();



