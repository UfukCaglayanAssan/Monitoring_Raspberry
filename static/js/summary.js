// Summary Sayfası JavaScript
class SummaryPage {
    constructor() {
        this.summaryData = [];
        this.init();
    }

    init() {
        this.loadSummaryData();
        this.startAutoRefresh();
    }

    async loadSummaryData() {
        try {
            this.showLoading();
            
            const response = await fetch('/api/summary', {
                method: 'GET',
                headers: {
                    'Content-Type': 'application/json'
                }
            });

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const data = await response.json();
            
            if (data.success) {
                this.summaryData = data.summary || [];
                this.renderSummary();
            } else {
                console.error('Özet verileri yüklenirken hata:', data.message);
                this.showNoData();
            }
        } catch (error) {
            console.error('Özet verileri yüklenirken hata:', error);
            this.showNoData();
        } finally {
            this.hideLoading();
        }
    }

    renderSummary() {
        const grid = document.getElementById('activeArmsGrid');
        if (!grid) return;

        if (this.summaryData.length === 0) {
            this.showNoData();
            return;
        }

        grid.innerHTML = '';
        
        this.summaryData.forEach(armData => {
            const card = this.createArmCard(armData);
            grid.appendChild(card);
        });

        // Grid'i göster
        grid.style.display = 'grid';
    }

    createArmCard(armData) {
        const card = document.createElement('div');
        card.className = 'arm-card';
        
        // Ana metrik (Deşarj Akımı - 0 A)
        const mainMetric = this.createMainMetric(armData);
        
        // Detay listesi
        const detailsList = this.createDetailsList(armData);
        
        card.innerHTML = `
            <div class="arm-header">
                <span class="arm-number">Kol ${armData.arm}</span>
                <span class="arm-timestamp">${this.formatTimestamp(armData.timestamp)}</span>
            </div>
            ${mainMetric}
            ${detailsList}
        `;
        
        return card;
    }

    createMainMetric(armData) {
        return `
            <div class="arm-main-metric">
                <div class="metric-icon">
                    <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <rect width="16" height="10" x="2" y="7" rx="2" ry="2"></rect>
                        <line x1="22" x2="22" y1="11" y2="13"></line>
                    </svg>
                </div>
                <div class="metric-value">0 <span class="metric-unit">A</span></div>
                <div class="metric-label">Deşarj Akımı</div>
            </div>
        `;
    }

    createDetailsList(armData) {
        const details = [
            {
                icon: 'battery',
                label: 'Nem:',
                value: armData.humidity ? `${armData.humidity} %` : '--',
                color: 'text-green-400'
            },
            {
                icon: 'thermometer',
                label: 'Sıcaklık:',
                value: armData.temperature ? `${armData.temperature} °C` : '--',
                color: 'text-red-400'
            },
            {
                icon: 'hash',
                label: 'Batarya Sayısı:',
                value: armData.battery_count || 0,
                color: 'text-purple-400'
            },
            {
                icon: 'zap',
                label: 'Ort. Gerilim:',
                value: armData.avg_voltage ? `${armData.avg_voltage} V` : '--',
                color: 'text-yellow-400'
            },
            {
                icon: 'hash',
                label: 'Ort. Şarj Durumu:',
                value: armData.avg_charge ? `${armData.avg_charge} %` : '--',
                color: 'text-purple-400'
            },
            {
                icon: 'battery',
                label: 'Ort. Sağlık Durumu:',
                value: armData.avg_health ? `${armData.avg_health} %` : '--',
                color: 'text-green-400'
            }
        ];

        const detailsHtml = details.map(detail => `
            <div class="detail-item">
                <div class="detail-left">
                    ${this.getIconSvg(detail.icon, detail.color)}
                    <span class="detail-label">${detail.label}</span>
                </div>
                <span class="detail-value">${detail.value}</span>
            </div>
        `).join('');

        return `
            <div class="arm-details">
                ${detailsHtml}
            </div>
        `;
    }

    getIconSvg(iconType, color) {
        const icons = {
            battery: `<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="detail-icon ${color}">
                <rect width="16" height="10" x="2" y="7" rx="2" ry="2"></rect>
                <line x1="22" x2="22" y1="11" y2="13"></line>
            </svg>`,
            thermometer: `<svg stroke="currentColor" fill="none" stroke-width="2" viewBox="0 0 24 24" stroke-linecap="round" stroke-linejoin="round" class="detail-icon ${color}" height="1em" width="1em">
                <path d="M10 13.5a4 4 0 1 0 4 0v-8.5a2 2 0 0 0 -4 0v8.5"></path>
                <path d="M10 9l4 0"></path>
            </svg>`,
            hash: `<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="detail-icon ${color}">
                <line x1="4" x2="20" y1="9" y2="9"></line>
                <line x1="4" x2="20" y1="15" y2="15"></line>
                <line x1="10" x2="8" y1="3" y2="21"></line>
                <line x1="16" x2="14" y1="3" y2="21"></line>
            </svg>`,
            zap: `<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="detail-icon ${color}">
                <path d="M4 14a1 1 0 0 1-.78-1.63l9.9-10.2a.5.5 0 0 1 .86.46l-1.92 6.02A1 1 0 0 0 13 10h7a1 1 0 0 1 .78 1.63l-9.9 10.2a.5.5 0 0 1-.86-.46l1.92-6.02A1 1 0 0 0 11 14z"></path>
            </svg>`
        };
        
        return icons[iconType] || icons.hash;
    }

    formatTimestamp(timestamp) {
        const date = new Date(timestamp);
        return date.toLocaleString('tr-TR', {
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit',
            day: '2-digit',
            month: '2-digit',
            year: 'numeric'
        });
    }

    showLoading() {
        const loading = document.getElementById('loadingSpinner');
        const grid = document.getElementById('activeArmsGrid');
        const noData = document.getElementById('noDataMessage');
        
        if (loading) loading.style.display = 'flex';
        if (grid) grid.style.display = 'none';
        if (noData) noData.style.display = 'none';
    }

    hideLoading() {
        const loading = document.getElementById('loadingSpinner');
        if (loading) loading.style.display = 'none';
    }

    showNoData() {
        const noData = document.getElementById('noDataMessage');
        const grid = document.getElementById('activeArmsGrid');
        const loading = document.getElementById('loadingSpinner');
        
        if (noData) noData.style.display = 'block';
        if (grid) grid.style.display = 'none';
        if (loading) loading.style.display = 'none';
    }

    startAutoRefresh() {
        setInterval(() => {
            if (this.isPageActive()) {
                this.loadSummaryData();
            }
        }, 30000); // 30 saniyede bir yenile
    }

    isPageActive() {
        return document.querySelector('.summary-page') !== null;
    }
}

// Sayfa yüklendiğinde başlat
function initSummaryPage() {
    if (document.querySelector('.summary-page')) {
        new SummaryPage();
    }
}

// DOMContentLoaded event listener
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initSummaryPage);
} else {
    initSummaryPage();
}



