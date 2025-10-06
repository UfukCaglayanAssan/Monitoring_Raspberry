class DataRetrievalManager {
    constructor() {
        this.operations = [];
        this.isLoading = false;
        
        this.init();
    }

    init() {
        console.log('🔍 DataRetrievalManager başlatılıyor...');
        this.setupEventListeners();
        this.loadOperations();
    }
    
    setupEventListeners() {
        // Toplu işlem butonları
        document.getElementById('readAllBtn')?.addEventListener('click', () => {
            this.handleReadAll();
        });
        
        document.getElementById('resetAllBtn')?.addEventListener('click', () => {
            this.handleResetAll();
        });
        
        // Veri alma butonu
        document.getElementById('getDataBtn')?.addEventListener('click', () => {
            this.handleGetData();
        });
        
        // Form validasyonu
        document.getElementById('armSelect')?.addEventListener('change', () => {
            this.validateForm();
        });
        
        document.getElementById('addressInput')?.addEventListener('input', () => {
            this.validateForm();
        });
        
        document.getElementById('dataTypeSelect')?.addEventListener('change', () => {
            this.validateForm();
        });
    }
    
    async handleReadAll() {
        const armSelect = document.getElementById('batchArmSelect');
        const selectedArm = armSelect.value;
        
        if (!selectedArm) {
            this.showToast('Lütfen bir kol seçiniz', 'error');
            return;
        }
        
        const armValue = selectedArm === '5' ? 5 : parseInt(selectedArm);
        
        try {
            this.showLoading(true);
            
            const response = await fetch('/api/data-retrieval/read-all', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    arm: armValue
                })
            });
            
            const result = await response.json();
            
            if (result.success) {
                this.addOperation({
                    type: 'read',
                    title: 'Tümünü Oku',
                    description: `Kol ${armValue === 5 ? 'Tümü' : armValue} için tüm veriler okundu`,
                    timestamp: new Date()
                });
                this.showToast('Tüm veriler başarıyla okundu', 'success');
            } else {
                throw new Error(result.message || 'Veri okuma hatası');
            }
            
        } catch (error) {
            console.error('Read all error:', error);
            this.showToast('Veri okuma hatası: ' + error.message, 'error');
        } finally {
            this.showLoading(false);
        }
    }
    
    async handleResetAll() {
        const armSelect = document.getElementById('batchArmSelect');
        const selectedArm = armSelect.value;
        
        if (!selectedArm) {
            this.showToast('Lütfen bir kol seçiniz', 'error');
            return;
        }
        
        const armValue = selectedArm === '5' ? 5 : parseInt(selectedArm);
        
        try {
            this.showLoading(true);
            
            const response = await fetch('/api/data-retrieval/reset-all', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    arm: armValue
                })
            });
            
            const result = await response.json();
            
            if (result.success) {
                this.addOperation({
                    type: 'reset',
                    title: 'Tümünü Sıfırla',
                    description: `Kol ${armValue === 5 ? 'Tümü' : armValue} için tüm veriler sıfırlandı`,
                    timestamp: new Date()
                });
                this.showToast('Tüm veriler başarıyla sıfırlandı', 'success');
            } else {
                throw new Error(result.message || 'Veri sıfırlama hatası');
            }
            
        } catch (error) {
            console.error('Reset all error:', error);
            this.showToast('Veri sıfırlama hatası: ' + error.message, 'error');
        } finally {
            this.showLoading(false);
        }
    }
    
    async handleGetData() {
        const armSelect = document.getElementById('armSelect');
        const addressInput = document.getElementById('addressInput');
        const dataTypeSelect = document.getElementById('dataTypeSelect');
        
        const arm = armSelect.value;
        const address = addressInput.value;
        const dataType = dataTypeSelect.value;
        const dataTypeOption = dataTypeSelect.selectedOptions[0];
        const dtype = dataTypeOption?.getAttribute('data-dtype');
        
        if (!arm || !address || !dataType) {
            this.showToast('Lütfen tüm alanları doldurunuz', 'error');
            return;
        }
        
        try {
            this.showLoading(true);
            
            const response = await fetch('/api/data-retrieval/get-data', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    arm: parseInt(arm),
                    address: parseInt(address),
                    dataType: dataType,
                    dtype: parseInt(dtype)
                })
            });
            
            const result = await response.json();
            
            if (result.success) {
                this.addOperation({
                    type: 'data',
                    title: 'Veri Al',
                    description: `Kol ${arm}, Adres ${address} - ${dataTypeOption.textContent} verisi alındı`,
                    timestamp: new Date()
                });
                this.showToast('Veri başarıyla alındı', 'success');
            } else {
                throw new Error(result.message || 'Veri alma hatası');
            }
            
        } catch (error) {
            console.error('Get data error:', error);
            this.showToast('Veri alma hatası: ' + error.message, 'error');
        } finally {
            this.showLoading(false);
        }
    }
    
    validateForm() {
        const armSelect = document.getElementById('armSelect');
        const addressInput = document.getElementById('addressInput');
        const dataTypeSelect = document.getElementById('dataTypeSelect');
        const getDataBtn = document.getElementById('getDataBtn');
        
        const isValid = armSelect.value && addressInput.value && dataTypeSelect.value;
        getDataBtn.disabled = !isValid;
        
        if (isValid) {
            getDataBtn.classList.add('btn-primary');
            getDataBtn.classList.remove('btn-secondary');
        } else {
            getDataBtn.classList.add('btn-secondary');
            getDataBtn.classList.remove('btn-primary');
        }
    }
    
    addOperation(operation) {
        this.operations.unshift(operation);
        
        // Maksimum 10 işlem tut
        if (this.operations.length > 10) {
            this.operations = this.operations.slice(0, 10);
        }
        
        this.saveOperations();
        this.renderOperations();
    }
    
    loadOperations() {
        const saved = localStorage.getItem('dataRetrievalOperations');
        if (saved) {
            try {
                this.operations = JSON.parse(saved).map(op => ({
                    ...op,
                    timestamp: new Date(op.timestamp)
                }));
                this.renderOperations();
            } catch (error) {
                console.error('Operations yükleme hatası:', error);
                this.operations = [];
            }
        }
    }
    
    saveOperations() {
        localStorage.setItem('dataRetrievalOperations', JSON.stringify(this.operations));
    }
    
    renderOperations() {
        const operationsList = document.getElementById('operationsList');
        
        if (this.operations.length === 0) {
            operationsList.innerHTML = `
                <div class="no-operations">
                    <i class="fas fa-info-circle"></i>
                    <p>Henüz işlem yapılmadı</p>
                </div>
            `;
            return;
        }
        
        operationsList.innerHTML = this.operations.map(operation => `
            <div class="operation-item">
                <div class="operation-info">
                    <div class="operation-icon ${operation.type}">
                        <i class="fas fa-${this.getOperationIcon(operation.type)}"></i>
                    </div>
                    <div class="operation-details">
                        <h4>${operation.title}</h4>
                        <p>${operation.description}</p>
                    </div>
                </div>
                <div class="operation-time">
                    ${this.formatTime(operation.timestamp)}
                </div>
            </div>
        `).join('');
    }
    
    getOperationIcon(type) {
        const icons = {
            'read': 'play',
            'reset': 'undo',
            'data': 'download'
        };
        return icons[type] || 'info';
    }
    
    formatTime(timestamp) {
        const now = new Date();
        const diff = now - timestamp;
        
        if (diff < 60000) { // 1 dakikadan az
            return 'Az önce';
        } else if (diff < 3600000) { // 1 saatten az
            const minutes = Math.floor(diff / 60000);
            return `${minutes} dakika önce`;
        } else if (diff < 86400000) { // 1 günden az
            const hours = Math.floor(diff / 3600000);
            return `${hours} saat önce`;
    } else {
            return timestamp.toLocaleDateString('tr-TR');
        }
    }
    
    showLoading(show) {
        this.isLoading = show;
        const overlay = document.getElementById('loadingOverlay');
        if (overlay) {
            overlay.style.display = show ? 'flex' : 'none';
        }
    }
    
    showToast(message, type = 'success') {
        const toast = document.getElementById('toast');
        if (!toast) return;
        
        const icon = toast.querySelector('.toast-icon');
        const messageEl = toast.querySelector('.toast-message');
        
        // Toast class'larını temizle
        toast.className = 'toast';
        
        // Type'a göre class ekle
        toast.classList.add(type);
        
        // İkon ayarla
        icon.innerHTML = type === 'success' ? '✓' : '✕';
        
        // Mesaj ayarla
        messageEl.textContent = message;
        
        // Toast'ı göster
        toast.style.display = 'block';
        
        // 3 saniye sonra gizle
        setTimeout(() => {
            toast.style.display = 'none';
        }, 3000);
    }
    
    onLanguageChanged(language) {
        // Dil değişikliği için gerekli işlemler
        console.log('DataRetrievalManager dil değişti:', language);
    }
}

// Sayfa yüklendiğinde başlat
document.addEventListener('DOMContentLoaded', () => {
    if (document.querySelector('.data-retrieval-page')) {
        window.dataRetrievalManager = new DataRetrievalManager();
    }
});