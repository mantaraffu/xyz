/* ====================================================
   KB Manager JavaScript — Casa di Quartiere Tuturano
   ==================================================== */

// --- Sidebar Toggle ---
function toggleSidebar() {
    const sidebar = document.getElementById('sidebar');
    sidebar.classList.toggle('open');
}

// --- Toggle Add Form ---
function toggleAddForm() {
    const body = document.getElementById('add-form-body');
    body.style.display = body.style.display === 'none' ? 'block' : 'none';
}

// --- Add Entry ---
async function addEntry(event) {
    event.preventDefault();

    const form = document.getElementById('add-entry-form');
    const feedback = document.getElementById('add-feedback');
    const formData = new FormData(form);

    feedback.classList.remove('hidden', 'success', 'error');
    feedback.textContent = 'Salvataggio in corso...';
    feedback.classList.add('success');
    feedback.classList.remove('hidden');

    try {
        const response = await fetch('/api/kb', {
            method: 'POST',
            body: formData,
        });

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }

        const data = await response.json();

        feedback.classList.add('success');
        feedback.textContent = `✅ Entry salvata con successo! ID: ${data.entry_id}`;

        // Reset form
        form.reset();

        // Reload page after short delay
        setTimeout(() => {
            window.location.reload();
        }, 1500);

    } catch (err) {
        feedback.classList.add('error');
        feedback.textContent = `❌ Errore: ${err.message}`;
    }
}

// --- Delete Entry ---
async function deleteEntry(entryId) {
    if (!confirm(`Sei sicuro di voler eliminare l'entry "${entryId}"?`)) {
        return;
    }

    try {
        const response = await fetch(`/api/kb/${entryId}`, {
            method: 'DELETE',
        });

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }

        // Remove from DOM with animation
        const cards = document.querySelectorAll('.entry-card');
        for (const card of cards) {
            const metaId = card.querySelector('.meta-id');
            if (metaId && metaId.textContent.includes(entryId)) {
                card.style.transition = 'all 0.3s ease';
                card.style.opacity = '0';
                card.style.transform = 'translateX(-20px)';
                setTimeout(() => card.remove(), 300);
                break;
            }
        }

    } catch (err) {
        alert(`Errore eliminazione: ${err.message}`);
    }
}

// --- Filter Entries ---
function filterEntries() {
    const searchTerm = document.getElementById('search-entries').value.toLowerCase();
    const categoryFilter = document.getElementById('filter-category').value;
    const entries = document.querySelectorAll('.entry-card');

    entries.forEach(entry => {
        const text = entry.getAttribute('data-text') || '';
        const category = entry.getAttribute('data-category') || '';

        const matchesSearch = !searchTerm || text.includes(searchTerm);
        const matchesCategory = !categoryFilter || category === categoryFilter;

        entry.style.display = (matchesSearch && matchesCategory) ? '' : 'none';
    });
}

// --- Filter by Category (from summary cards) ---
function filterByCategory(category) {
    const filterSelect = document.getElementById('filter-category');
    if (filterSelect) {
        filterSelect.value = category;
        filterEntries();

        // Scroll to entries
        const entriesList = document.getElementById('entries-list');
        if (entriesList) {
            entriesList.scrollIntoView({ behavior: 'smooth' });
        }
    }
}

// --- Initialize ---
document.addEventListener('DOMContentLoaded', () => {
    // Animate entry cards
    const entryCards = document.querySelectorAll('.entry-card');
    entryCards.forEach((card, index) => {
        card.style.opacity = '0';
        card.style.transform = 'translateY(8px)';
        setTimeout(() => {
            card.style.transition = 'all 0.3s ease';
            card.style.opacity = '1';
            card.style.transform = 'translateY(0)';
        }, 50 + index * 30);
    });

    // Animate summary cards
    const summaryCards = document.querySelectorAll('.category-summary-card');
    summaryCards.forEach((card, index) => {
        card.style.opacity = '0';
        card.style.transform = 'scale(0.95)';
        setTimeout(() => {
            card.style.transition = 'all 0.4s ease';
            card.style.opacity = '1';
            card.style.transform = 'scale(1)';
        }, 80 + index * 60);
    });
});
