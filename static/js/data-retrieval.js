// Veri Alma Sayfası JavaScript
class DataRetrieval {
    constructor() {
        this.operations = [];
        this.init();
    }

    init() {
        this.bindEvents();
        this.loadOperations();
    }

    bindEvents() {
        // Toplu işlem butonları
        document.getElementById('readAllBtn').addEventListener('click', () => {
            this.handleReadAll();
        });

        document.getElementById('resetAllBtn').addEventListener('click', () => {
            this.handleResetAll();
        });

        // Veri alma butonu
        document.getElementById('getDataBtn').addEventListener('click', () => {
            this.handleGetData();
        });

        // Form validasyonu
        document.getElementById('dataArmSelect').addEventListener('change', () => {
            this.validateForm();
        });

        document.getElementById('dataAddressInput').addEventListener('input', () => {
            this.validateForm();
        });

        document.getElementById('dataValueSelect').addEventListener('change', () => {
            this.validateForm();
        });
    }

    validateForm() {
        const arm = document.getElementById('dataArmSelect').value;
        const address = document.getElementById('dataAddressInput').value;
        const value = document.getElementById('dataValueSelect').value;
        
        const isValid = arm && address && value;
        document.getElementById('getDataBtn').disabled = !isValid;
        
        return isValid;
    }

    async handleReadAll() {
        const armSelect = document.getElementById('batchArmSelect');
        const selectedArm = armSelect.value;
        
        if (!selectedArm) {
            this.showToast('Lütfen bir kol seçiniz', 'error');
            return;
        }

        this.showLoading('Tümünü oku komutu gönderiliyor...');

        try {
            const response = await fetch('/api/commands', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    command: 'readAll',
                    arm: selectedArm === '5' ? 5 : parseInt(selectedArm)
                })
            });

            if (response.ok) {
                this.addOperation('read', `Tümünü Oku - ${selectedArm === '5' ? 'Tüm Kollar' : `Kol ${selectedArm}`}`);
                this.showToast('Tümünü oku komutu başarıyla gönderildi', 'success');
    } else {
                throw new Error('Komut gönderilemedi');
            }
        } catch (error) {
            console.error('ReadAll hatası:', error);
            this.showToast('Komut gönderilirken hata oluştu', 'error');
        } finally {
            this.hideLoading();
        }
    }

    async handleResetAll() {
        const armSelect = document.getElementById('batchArmSelect');
        const selectedArm = armSelect.value;
        
        if (!selectedArm) {
            this.showToast('Lütfen bir kol seçiniz', 'error');
            return;
        }

        this.showLoading('Tümünü sıfırla komutu gönderiliyor...');

        try {
            const response = await fetch('/api/commands', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    command: 'resetAll',
                    arm: selectedArm === '5' ? 5 : parseInt(selectedArm)
                })
            });

            if (response.ok) {
                this.addOperation('reset', `Tümünü Sıfırla - ${selectedArm === '5' ? 'Tüm Kollar' : `Kol ${selectedArm}`}`);
                this.showToast('Tümünü sıfırla komutu başarıyla gönderildi', 'success');
            } else {
                throw new Error('Komut gönderilemedi');
            }
        } catch (error) {
            console.error('ResetAll hatası:', error);
            this.showToast('Komut gönderilirken hata oluştu', 'error');
        } finally {
            this.hideLoading();
        }
    }

    async handleGetData() {
        if (!this.validateForm()) {
            this.showToast('Lütfen tüm alanları doldurunuz', 'error');
            return;
        }

        const arm = document.getElementById('dataArmSelect').value;
        const address = document.getElementById('dataAddressInput').value;
        const value = document.getElementById('dataValueSelect').value;

        this.showLoading('Veri alma komutu gönderiliyor...');

        try {
            const response = await fetch('/api/datagets', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    armValue: parseInt(arm),
                    slaveAddress: parseInt(address),
                    slaveCommand: parseInt(value)
                })
            });

            if (response.ok) {
                const valueText = this.getDataTypeText(value);
                this.addOperation('data', `Veri Al - Kol ${arm}, Adres ${address}, ${valueText}`);
                this.showToast('Veri alma komutu başarıyla gönderildi', 'success');
                
                // Formu temizle
                this.clearForm();
            } else {
                throw new Error('Komut gönderilemedi');
            }
        } catch (error) {
            console.error('GetData hatası:', error);
            this.showToast('Komut gönderilirken hata oluştu', 'error');
        } finally {
            this.hideLoading();
        }
    }

    getDataTypeText(value) {
        const dataTypes = {
            '10': 'Gerilim (V)',
            '11': 'SOH (%)',
            '12': 'Sıcaklık (°C)',
            '13': 'NTC2 (°C)',
            '14': 'NTC3 (°C)',
            '126': 'SOC (%)'
        };
        return dataTypes[value] || `Tip ${value}`;
    }

    addOperation(type, description) {
        const operation = {
            id: Date.now(),
            type: type,
            description: description,
            timestamp: new Date().toLocaleString('tr-TR')
        };

        this.operations.unshift(operation);
        
        // Son 10 işlemi tut
        if (this.operations.length > 10) {
            this.operations = this.operations.slice(0, 10);
        }

        this.saveOperations();
        this.renderOperations();
    }

    loadOperations() {
        const saved = localStorage.getItem('dataRetrievalOperations');
        if (saved) {
            this.operations = JSON.parse(saved);
            this.renderOperations();
        }
    }

    saveOperations() {
        localStorage.setItem('dataRetrievalOperations', JSON.stringify(this.operations));
    }

    renderOperations() {
        const container = document.getElementById('operationsList');
        
        if (this.operations.length === 0) {
            container.innerHTML = `
                <div class="no-operations">
                    <i class="fas fa-inbox"></i>
                    <h4>Henüz işlem yapılmadı</h4>
                    <p>Veri alma işlemleri burada görüntülenecek</p>
                </div>
            `;
            return;
        }

        container.innerHTML = this.operations.map(op => `
            <div class="operation-item">
                <div class="operation-info">
                    <div class="operation-icon ${op.type}">
                        <i class="fas ${this.getOperationIcon(op.type)}"></i>
                    </div>
                    <div class="operation-details">
                        <h4>${op.description}</h4>
                        <p>İşlem tamamlandı</p>
                    </div>
                </div>
                <div class="operation-time">${op.timestamp}</div>
            </div>
        `).join('');
    }

    getOperationIcon(type) {
        const icons = {
            'read': 'fa-download',
            'reset': 'fa-refresh',
            'data': 'fa-database'
        };
        return icons[type] || 'fa-cog';
    }

    clearForm() {
        document.getElementById('dataArmSelect').value = '';
        document.getElementById('dataAddressInput').value = '';
        document.getElementById('dataValueSelect').value = '';
        document.getElementById('getDataBtn').disabled = true;
    }

    showLoading(text) {
        document.getElementById('loadingText').textContent = text;
        document.getElementById('loadingOverlay').style.display = 'flex';
    }

    hideLoading() {
        document.getElementById('loadingOverlay').style.display = 'none';
    }

    showToast(message, type = 'success') {
        const toast = document.getElementById('toast');
        const toastMessage = document.getElementById('toastMessage');
        const toastIcon = toast.querySelector('.toast-icon i');
        
        toastMessage.textContent = message;
        
        if (type === 'error') {
            toastIcon.className = 'fas fa-exclamation-triangle';
            toast.querySelector('.toast-icon').style.background = '#ef4444';
        } else {
            toastIcon.className = 'fas fa-check';
            toast.querySelector('.toast-icon').style.background = '#10b981';
        }
        
        toast.style.display = 'block';
        
        setTimeout(() => {
            toast.style.display = 'none';
        }, 3000);
    }
}

// Sayfa yüklendiğinde başlat
document.addEventListener('DOMContentLoaded', () => {
    new DataRetrieval();
});