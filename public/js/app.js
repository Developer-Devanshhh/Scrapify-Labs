document.addEventListener('DOMContentLoaded', () => {
    // Elements
    const form = document.getElementById('scrape-form');
    const submitBtn = document.getElementById('submit-btn');
    const feedContainer = document.getElementById('results-feed');
    const refreshBtn = document.getElementById('refresh-db-btn');
    const filterSelect = document.getElementById('filter-platform');

    let allResults = [];

    // Helper: Initial Load
    fetchResults();

    // Form Submission: Trigger Scrape
    form.addEventListener('submit', async (e) => {
        e.preventDefault();

        // Gather data
        const keywordsInput = document.getElementById('keywords').value;
        const keywords = keywordsInput.split(',').map(k => k.trim()).filter(k => k);
        const maxResults = parseInt(document.getElementById('max_results').value, 10);

        const platforms = Array.from(document.querySelectorAll('input[name="platforms"]:checked'))
            .map(cb => cb.value);

        if (platforms.length === 0) {
            showToast('error', 'Please select at least one platform.');
            return;
        }

        const payload = { keywords, platforms, max_results: maxResults };

        // UI Feedback
        setLoadingState(true);
        showToast('info', 'Scraping initiated. This may take a minute...');

        try {
            const res = await fetch('/api/scrape', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });

            if (!res.ok) throw new Error('Failed to start scrape job');

            const data = await res.json();
            showToast('success', `Scrape complete! Fetched ${data.total_results || 0} hits.`);

            // Reload feed
            await fetchResults();

        } catch (error) {
            console.error(error);
            showToast('error', error.message);
        } finally {
            setLoadingState(false);
        }
    });

    // Refresh Feed
    refreshBtn.addEventListener('click', async () => {
        refreshBtn.style.animation = 'spin 1s linear';
        await fetchResults();
        setTimeout(() => refreshBtn.style.animation = '', 1000);
        showToast('info', 'Database synchronized.');
    });

    // Handle Filters
    filterSelect.addEventListener('change', () => {
        renderFeed(allResults);
    });

    // API: Fetch Results from SQLite
    async function fetchResults() {
        try {
            feedContainer.innerHTML = `
                <div class="empty-state">
                    <div class="loader-ring"></div>
                    <p>Loading intelligence data...</p>
                </div>
            `;
            const res = await fetch('/api/results?page_size=100');
            const data = await res.json();

            allResults = data.results || [];
            renderFeed(allResults);
        } catch (e) {
            console.error("Failed to fetch results", e);
            feedContainer.innerHTML = `
                <div class="empty-state">
                    <i class="fa-solid fa-triangle-exclamation" style="font-size: 2rem; color: var(--danger)"></i>
                    <p>Failed to load database.</p>
                </div>
            `;
        }
    }

    // Render Data to UI
    function renderFeed(dataList) {
        const filterVal = filterSelect.value;
        const filtered = filterVal === 'all' ? dataList : dataList.filter(item => item.platform === filterVal);

        feedContainer.innerHTML = '';

        if (filtered.length === 0) {
            feedContainer.innerHTML = `
                <div class="empty-state">
                    <i class="fa-solid fa-satellite" style="font-size: 2rem; opacity: 0.5;"></i>
                    <p>No records found in database.</p>
                </div>
            `;
            return;
        }

        filtered.forEach(item => {
            const dateStr = new Date(item.timestamp || item.scraped_at).toLocaleString();

            // Icons matching
            const icons = {
                'twitter': 'fa-x-twitter',
                'instagram': 'fa-instagram',
                'civic': 'fa-building-columns',
                'youtube': 'fa-youtube',
                'facebook': 'fa-facebook-f',
                'threads': 'fa-threads',
                'reddit': 'fa-reddit-alien',
                'google_maps': 'fa-map-location-dot'
            };
            // Use fa-solid for civic and google_maps (they're not brand icons)
            const solidIcons = ['civic', 'google_maps'];
            const iconPrefix = solidIcons.includes(item.platform) ? 'fa-solid' : 'fa-brands';
            const icon = icons[item.platform] || 'fa-globe';

            // Build structured data section if LLM has enriched it
            let structuredHtml = '';
            const sd = item.structured_data;
            if (sd) {
                const urgencyColors = {
                    'critical': '#ef4444',
                    'high': '#f97316',
                    'medium': '#eab308',
                    'low': '#22c55e'
                };
                const urgColor = urgencyColors[sd.urgency] || '#94a3b8';
                structuredHtml = `
                    <div class="structured-tags">
                        ${sd.category ? `<span class="category-badge">${escapeHtml(sd.category)}</span>` : ''}
                        ${sd.urgency ? `<span class="urgency-badge" style="background:${urgColor}20; color:${urgColor}; border-color:${urgColor}40">${sd.urgency.toUpperCase()}</span>` : ''}
                        ${sd.sentiment ? `<span class="sentiment-badge">${sd.sentiment}</span>` : ''}
                    </div>
                    ${sd.summary ? `<div class="llm-summary"><i class="fa-solid fa-brain"></i> ${escapeHtml(sd.summary)}</div>` : ''}
                `;
            }

            // Location & geo
            let locationHtml = '';
            if (item.location) {
                locationHtml = `<span class="location-tag"><i class="fa-solid fa-location-dot"></i> ${escapeHtml(item.location)}</span>`;
            }

            const card = document.createElement('div');
            card.className = 'result-card';
            card.innerHTML = `
                <div class="card-header">
                    <div class="platform-badge ${item.platform}">
                        <i class="${iconPrefix} ${icon}"></i> 
                        ${item.platform.replace('_', ' ')}
                    </div>
                    <span class="timestamp">${dateStr}</span>
                </div>
                ${structuredHtml}
                <div class="card-author">@${item.author || 'Unknown'} ${locationHtml}</div>
                <div class="card-body">
                    ${escapeHtml(item.content)}
                </div>
                <div class="card-footer">
                    <div class="engagement">
                        <span title="Rating"><i class="fa-solid fa-star"></i> ${item.metadata?.rating || item.metadata?.likes || '—'}</span>
                        <span title="Comments"><i class="fa-regular fa-comment"></i> ${item.metadata?.comments || item.metadata?.replies || 0}</span>
                    </div>
                    ${item.source_url ? `<a href="${item.source_url}" target="_blank" class="icon-btn" style="display:flex; align-items:center; justify-content:center; text-decoration:none;"><i class="fa-solid fa-arrow-up-right-from-square"></i></a>` : ''}
                </div>
            `;
            feedContainer.appendChild(card);
        });
    }

    // Utilities
    function setLoadingState(isLoading) {
        const span = submitBtn.querySelector('span');
        const icon = submitBtn.querySelector('i');

        if (isLoading) {
            submitBtn.disabled = true;
            span.innerText = 'Scraping...';
            icon.className = 'fa-solid fa-circle-notch fa-spin';
        } else {
            submitBtn.disabled = false;
            span.innerText = 'Initialize Scrape';
            icon.className = 'fa-solid fa-rocket';
        }
    }

    function showToast(type, message) {
        const container = document.getElementById('toast-container');
        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;

        let icon = 'fa-circle-info';
        if (type === 'success') icon = 'fa-circle-check';
        if (type === 'error') icon = 'fa-triangle-exclamation';

        toast.innerHTML = `<i class="fa-solid ${icon}"></i> <span>${escapeHtml(message)}</span>`;
        container.appendChild(toast);

        setTimeout(() => {
            toast.style.opacity = '0';
            setTimeout(() => toast.remove(), 300);
        }, 4000);
    }

    function escapeHtml(unsafe) {
        if (!unsafe) return '';
        return unsafe
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }
});
