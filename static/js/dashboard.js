/* ====================================================
   Dashboard JavaScript — Casa di Quartiere Tuturano
   ==================================================== */

// --- Sidebar Toggle ---
function toggleSidebar() {
    const sidebar = document.getElementById('sidebar');
    sidebar.classList.toggle('open');
}

// --- Scroll to Test Section ---
function scrollToTest() {
    const section = document.getElementById('test-section');
    if (section) {
        section.scrollIntoView({ behavior: 'smooth' });
    }
}

// --- Test Bot ---
async function sendTest() {
    const input = document.getElementById('test-input');
    const resultDiv = document.getElementById('test-result');
    const responseDiv = document.getElementById('test-response');
    const timeDiv = document.getElementById('test-time');
    const docsDiv = document.getElementById('test-docs');
    const sourcesDiv = document.getElementById('test-sources');

    const question = input.value.trim();
    if (!question) return;

    // Show loading state
    resultDiv.classList.remove('hidden');
    responseDiv.textContent = 'Elaborazione in corso...';
    resultDiv.classList.add('loading');
    timeDiv.textContent = '⏱️ ...';
    docsDiv.textContent = '📄 ...';
    sourcesDiv.innerHTML = '';

    try {
        const formData = new FormData();
        formData.append('q', question);

        const response = await fetch('/api/test', {
            method: 'POST',
            body: formData,
        });

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }

        const data = await response.json();

        resultDiv.classList.remove('loading');
        responseDiv.textContent = data.risposta || 'Nessuna risposta';
        timeDiv.textContent = `⏱️ ${data.tempo_risposta_ms}ms`;
        docsDiv.textContent = `📄 ${data.documenti_trovati} documenti`;

        // Show sources
        if (data.fonti && data.fonti.length > 0) {
            let sourcesHtml = '<div style="margin-top: 8px;"><strong>Fonti utilizzate:</strong></div>';
            data.fonti.forEach((fonte, i) => {
                sourcesHtml += `
                    <div style="margin-top: 4px; padding: 4px 8px; background: rgba(255,255,255,0.03); border-radius: 6px;">
                        <span class="tag">${fonte.categoria}</span>
                        <span style="font-size: 12px; color: #9da3b4;">${fonte.domanda_fonte}</span>
                        <span class="similarity-badge ${fonte.similarita > 0.7 ? 'high' : fonte.similarita > 0.4 ? 'medium' : 'low'}">${Math.round(fonte.similarita * 100)}%</span>
                    </div>
                `;
            });
            sourcesDiv.innerHTML = sourcesHtml;
        }
    } catch (err) {
        resultDiv.classList.remove('loading');
        responseDiv.textContent = `Errore: ${err.message}. Verifica che Ollama sia attivo.`;
    }
}

// --- Auto-refresh stats (every 30 seconds) ---
let refreshInterval = null;

function startAutoRefresh() {
    refreshInterval = setInterval(async () => {
        try {
            const response = await fetch('/api/stats');
            if (response.ok) {
                // Stats are available — page will show updated data on manual refresh
                console.log('Stats refreshed');
            }
        } catch (e) {
            console.warn('Auto-refresh failed:', e);
        }
    }, 30000);
}

// --- Initialize ---
document.addEventListener('DOMContentLoaded', () => {
    // Focus test input on page load
    const testInput = document.getElementById('test-input');
    if (testInput) {
        testInput.addEventListener('focus', () => {
            testInput.parentElement.style.boxShadow = '0 0 0 3px rgba(78, 140, 255, 0.1)';
        });
        testInput.addEventListener('blur', () => {
            testInput.parentElement.style.boxShadow = 'none';
        });
    }

    // Animate stat cards on load
    const statCards = document.querySelectorAll('.stat-card');
    statCards.forEach((card, index) => {
        card.style.opacity = '0';
        card.style.transform = 'translateY(10px)';
        setTimeout(() => {
            card.style.transition = 'all 0.4s ease';
            card.style.opacity = '1';
            card.style.transform = 'translateY(0)';
        }, 100 + index * 80);
    });

    startAutoRefresh();
});
