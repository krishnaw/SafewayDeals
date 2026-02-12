/* Safeway Deals SPA */

const state = {
    searchMode: false,
    currentPage: 1,
    perPage: 20,
    totalPages: 1,
    total: 0,
    category: '',
    offerPgm: '',
    dealType: '',
    expiry: '',
    hasProducts: false,
    deals: [],
    searchQuery: '',
    searchEventSource: null,
    debounceTimer: null,
    allSearchResults: [],
    cardStyle: 1,
    votes: {},
};

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);
const grid = $('#deals-grid');
const loading = $('#loading');
const pagination = $('#pagination');
const prevBtn = $('#prev-btn');
const nextBtn = $('#next-btn');
const pageInfo = $('#page-info');
const searchInput = $('#search-input');
const searchClear = $('#search-clear');
const filterCategory = $('#filter-category');
const filterType = $('#filter-type');
const filterDealType = $('#filter-deal-type');
const filterExpiry = $('#filter-expiry');
const filterHasProducts = $('#filter-has-products');
const resultsInfo = $('#results-info');

/* ===== Offer Type Labels ===== */
const OFFER_TYPE_LABELS = {
    MF: 'Manufacturer',
    PD: 'Personalized',
    SC: 'Store Coupon',
    LO: 'Loyalty',
};

function offerTypeLabel(pgm) {
    return OFFER_TYPE_LABELS[pgm] || pgm;
}

/* ===== Card Helpers ===== */

function getImageUrl(deal) {
    return deal.productImageUrl || deal.dealImageUrl || '';
}

function imgTag(url, cls, fallbackHtml) {
    if (url) {
        return `<img src="${url}" alt="" class="${cls}" loading="lazy" onerror="this.style.display='none';this.nextElementSibling&&(this.nextElementSibling.style.display='flex')">
                <div class="no-image ${cls}" style="display:none">${fallbackHtml || 'No image'}</div>`;
    }
    return `<div class="no-image ${cls}">${fallbackHtml || 'No image'}</div>`;
}

function escHtml(str) {
    if (!str) return '';
    return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function getDealName(deal) { return deal.name || deal.offer_name || ''; }
function getDealPrice(deal) { return deal.offerPrice || deal.offer_price || ''; }
function getDealDesc(deal) { return deal.description || deal.offer_description || ''; }
function getDealCategory(deal) { return deal.category || deal.offer_category || ''; }
function getDealPgm(deal) { return deal.offerPgm || deal.offer_pgm || ''; }

function priceBlock(deal) {
    const salePrice = deal.productPrice;
    const regPrice = deal.productBasePrice;
    if (!salePrice && !regPrice) return '';
    const hasSale = regPrice && salePrice && regPrice > salePrice;
    if (hasSale) {
        return `<div class="card-prices">
            <span class="price-sale">$${Number(salePrice).toFixed(2)}</span>
            <span class="price-reg">$${Number(regPrice).toFixed(2)}</span>
        </div>`;
    }
    const p = salePrice || regPrice;
    return `<div class="card-prices"><span class="price-current">$${Number(p).toFixed(2)}</span></div>`;
}

function parseLimit(deal) {
    const desc = getDealDesc(deal);
    const m = desc.match(/[Ll]imit\s+(\d+)/);
    return m ? parseInt(m[1], 10) : null;
}

function daysUntilExpiry(deal) {
    const endDate = deal.endDate;
    if (!endDate) return null;
    const endMs = parseInt(endDate, 10);
    if (isNaN(endMs)) return null;
    const now = Date.now();
    const diff = Math.ceil((endMs - now) / (1000 * 60 * 60 * 24));
    return diff >= 0 ? diff : 0;
}

function metaBadges(deal) {
    const limit = parseLimit(deal);
    const days = daysUntilExpiry(deal);
    const prodCount = deal.productCount || 0;
    const hasBadge = limit !== null || (days !== null && days <= 7) || prodCount > 0;
    if (!hasBadge) return '';

    let html = '<div class="card-badges">';
    if (days !== null && days <= 7) {
        const cls = days <= 3 ? 'badge-urgent' : 'badge-soon';
        html += `<span class="badge ${cls}">${days === 0 ? 'Expires today' : days === 1 ? '1 day left' : days + ' days left'}</span>`;
    }
    if (limit !== null) {
        html += `<span class="badge badge-limit">Limit ${limit}</span>`;
    }
    if (prodCount > 0) {
        html += `<span class="badge badge-products">${prodCount} product${prodCount !== 1 ? 's' : ''}</span>`;
    }
    html += '</div>';
    return html;
}

/* ===== 10 Card Designs ===== */

function cardStyle1(deal) { // Classic Coupon
    const name = escHtml(getDealName(deal));
    const price = escHtml(getDealPrice(deal));
    const desc = escHtml(getDealDesc(deal));
    const imgUrl = getImageUrl(deal);
    return `
        ${metaBadges(deal)}
        <div class="card-image-wrap">
            ${imgTag(imgUrl, 'card-image', '&#9986;')}
        </div>
        <div class="card-body">
            <div class="card-price">${price}</div>
            <div class="card-title">${name}</div>
            ${priceBlock(deal)}
            <div class="card-desc">${desc}</div>
            <div class="card-footer">
                <button class="cta-btn cta-clip">Clip Coupon</button>
            </div>
        </div>`;
}

function cardStyle2(deal) { // Modern Minimal
    const name = escHtml(getDealName(deal));
    const price = escHtml(getDealPrice(deal));
    const desc = escHtml(getDealDesc(deal));
    const imgUrl = getImageUrl(deal);
    return `
        ${metaBadges(deal)}
        <div class="card-image-wrap">
            ${imgTag(imgUrl, 'card-image', '&#128722;')}
        </div>
        <div class="card-title">${name}</div>
        <div class="card-price">${price}</div>
        ${priceBlock(deal)}
        <div class="card-desc">${desc}</div>
        <button class="cta-btn cta-add">+ Add to List</button>`;
}

function cardStyle3(deal) { // Split Feature
    const name = escHtml(getDealName(deal));
    const price = escHtml(getDealPrice(deal));
    const desc = escHtml(getDealDesc(deal));
    const imgUrl = getImageUrl(deal);
    return `
        ${metaBadges(deal)}
        <div class="card-image-top">
            ${imgTag(imgUrl, 'card-image', '&#127991;')}
        </div>
        <div class="card-accent-bar"></div>
        <div class="card-body">
            <div class="card-title">${name}</div>
            <div class="card-price">${price}</div>
            ${priceBlock(deal)}
            <div class="card-desc">${desc}</div>
            <button class="cta-btn cta-details">View Details &rarr;</button>
        </div>`;
}

function cardStyle4(deal) { // Stacked Badge
    const name = escHtml(getDealName(deal));
    const price = escHtml(getDealPrice(deal));
    const desc = escHtml(getDealDesc(deal));
    const imgUrl = getImageUrl(deal);
    return `
        ${metaBadges(deal)}
        <div class="card-savings-badge">${price}</div>
        <div class="card-image-wrap">
            ${imgTag(imgUrl, 'card-image', '&#9733;')}
        </div>
        <div class="card-body">
            <div class="card-title">${name}</div>
            ${priceBlock(deal)}
            <div class="card-desc">${desc}</div>
            <button class="cta-btn cta-save">Save Now</button>
        </div>`;
}

function cardStyle5(deal) { // Compact Horizontal
    const name = escHtml(getDealName(deal));
    const price = escHtml(getDealPrice(deal));
    const desc = escHtml(getDealDesc(deal));
    const imgUrl = getImageUrl(deal);
    return `
        ${metaBadges(deal)}
        <div class="card-image-side">
            ${imgTag(imgUrl, 'card-image', '&#128722;')}
        </div>
        <div class="card-body">
            <div class="card-title">${name}</div>
            <div class="card-price">${price}</div>
            ${priceBlock(deal)}
            <div class="card-desc">${desc}</div>
            <div class="card-meta">
                <button class="cta-btn cta-grab">Grab Deal</button>
            </div>
        </div>`;
}

function cardStyle6(deal) { // Glass Card
    const name = escHtml(getDealName(deal));
    const price = escHtml(getDealPrice(deal));
    const desc = escHtml(getDealDesc(deal));
    const imgUrl = getImageUrl(deal);
    return `
        ${metaBadges(deal)}
        <div class="card-image-wrap">
            ${imgTag(imgUrl, 'card-image', '&#9830;')}
        </div>
        <div class="card-title">${name}</div>
        <div class="card-price">${price}</div>
        ${priceBlock(deal)}
        <div class="card-desc">${desc}</div>
        <button class="cta-btn cta-unlock">Unlock Offer</button>`;
}

function cardStyle7(deal) { // Magazine Editorial
    const name = escHtml(getDealName(deal));
    const price = escHtml(getDealPrice(deal));
    const desc = escHtml(getDealDesc(deal));
    const imgUrl = getImageUrl(deal);
    return `
        ${metaBadges(deal)}
        <div class="card-image-wrap">
            ${imgTag(imgUrl, 'card-image', '&#9998;')}
        </div>
        <div class="card-eyebrow">FEATURED DEAL</div>
        <div class="card-title">${name}</div>
        <div class="card-price">${price}</div>
        ${priceBlock(deal)}
        <div class="card-desc">${desc}</div>
        <button class="cta-btn cta-shop">Shop This Deal</button>`;
}

function cardStyle8(deal) { // Dark Mode
    const name = escHtml(getDealName(deal));
    const price = escHtml(getDealPrice(deal));
    const desc = escHtml(getDealDesc(deal));
    const imgUrl = getImageUrl(deal);
    return `
        ${metaBadges(deal)}
        <div class="card-image-wrap">
            ${imgTag(imgUrl, 'card-image', '&#9790;')}
        </div>
        <div class="card-title">${name}</div>
        <div class="card-price">${price}</div>
        ${priceBlock(deal)}
        <div class="card-desc">${desc}</div>
        <button class="cta-btn cta-neon">Get It Now</button>`;
}

function cardStyle9(deal) { // Price Focus
    const name = escHtml(getDealName(deal));
    const price = escHtml(getDealPrice(deal));
    const desc = escHtml(getDealDesc(deal));
    const imgUrl = getImageUrl(deal);
    return `
        ${metaBadges(deal)}
        <div class="card-hero-price">${price}</div>
        <div class="card-image-wrap">
            ${imgTag(imgUrl, 'card-image', '&#9041;')}
        </div>
        <div class="card-title">${name}</div>
        ${priceBlock(deal)}
        <div class="card-desc">${desc}</div>
        <button class="cta-btn cta-redeem">Redeem Coupon</button>`;
}

function cardStyle10(deal) { // Grocery List
    const name = escHtml(getDealName(deal));
    const price = escHtml(getDealPrice(deal));
    const desc = escHtml(getDealDesc(deal));
    const imgUrl = getImageUrl(deal);
    return `
        ${metaBadges(deal)}
        <div class="card-image-wrap">
            ${imgTag(imgUrl, 'card-image', '&#128722;')}
        </div>
        <div class="card-body">
            <div class="card-list-header">
                <div class="card-checkbox">&#9744;</div>
                <div class="card-title">${name}</div>
            </div>
            <div class="card-price">${price}</div>
            ${priceBlock(deal)}
            <div class="card-desc">${desc}</div>
            <button class="cta-btn cta-cart">Add to Cart</button>
        </div>`;
}

const CARD_RENDERERS = [null, cardStyle1, cardStyle2, cardStyle3, cardStyle4, cardStyle5,
    cardStyle6, cardStyle7, cardStyle8, cardStyle9, cardStyle10];

function createDealCard(deal) {
    const renderer = CARD_RENDERERS[state.cardStyle] || cardStyle1;
    const div = document.createElement('div');
    div.className = 'deal-card';
    div.dataset.cardStyle = state.cardStyle;
    div.innerHTML = renderer(deal);
    return div;
}

/* ===== API Calls ===== */

async function fetchCategories() {
    const res = await fetch('/api/categories');
    const data = await res.json();

    data.categories.forEach(cat => {
        const opt = document.createElement('option');
        opt.value = cat;
        opt.textContent = cat;
        filterCategory.appendChild(opt);
    });

    data.offerTypes.forEach(t => {
        const opt = document.createElement('option');
        opt.value = t;
        opt.textContent = `${t} - ${offerTypeLabel(t)}`;
        filterType.appendChild(opt);
    });

    (data.dealTypes || []).forEach(dt => {
        const opt = document.createElement('option');
        opt.value = dt;
        opt.textContent = dt;
        filterDealType.appendChild(opt);
    });
}

async function fetchDeals() {
    showLoading(true);
    const params = new URLSearchParams({
        page: state.currentPage,
        per_page: state.perPage,
    });
    if (state.category) params.set('category', state.category);
    if (state.offerPgm) params.set('offer_pgm', state.offerPgm);
    if (state.dealType) params.set('deal_type', state.dealType);
    if (state.expiry) params.set('expiry', state.expiry);
    if (state.hasProducts) params.set('has_products', 'yes');

    const res = await fetch(`/api/deals?${params}`);
    const data = await res.json();

    state.deals = data.deals;
    state.totalPages = data.total_pages;
    state.total = data.total;
    state.currentPage = data.page;

    renderDeals(state.deals);
    updatePagination();
    showLoading(false);
    resultsInfo.textContent = `${data.total} deal${data.total !== 1 ? 's' : ''}`;
}

/* ===== SSE Search ===== */

function startSearch(query) {
    if (state.searchEventSource) {
        state.searchEventSource.close();
        state.searchEventSource = null;
    }

    if (!query.trim()) {
        exitSearchMode();
        return;
    }

    state.searchMode = true;
    state.searchQuery = query;
    state.allSearchResults = [];
    grid.innerHTML = '';
    showLoading(true);
    pagination.classList.add('hidden');
    const expandedEl = $('#search-expanded');
    if (expandedEl) expandedEl.textContent = '';

    const params = new URLSearchParams({ q: query, top_k: 40 });
    const es = new EventSource(`/api/search/stream?${params}`);
    state.searchEventSource = es;

    let totalRendered = 0;

    es.onmessage = (event) => {
        const raw = event.data;

        if (raw === '[END]') {
            es.close();
            state.searchEventSource = null;
            showLoading(false);
            applyClientFilters();
            return;
        }

        try {
            const parsed = JSON.parse(raw);

            // Handle query expansion event
            if (parsed.type === 'expanded') {
                const el = $('#search-expanded');
                if (el) el.textContent = `Interpreted as: ${parsed.expanded}`;
                return;
            }

            const batch = parsed;
            state.allSearchResults.push(...batch);

            batch.forEach((deal) => {
                if (matchesFilters(deal)) {
                    grid.appendChild(createDealCard(deal));
                    totalRendered++;
                }
            });

            resultsInfo.textContent = `${state.allSearchResults.length} result${state.allSearchResults.length !== 1 ? 's' : ''} for "${escHtml(query)}"`;
        } catch (e) {
            console.error('SSE parse error:', e);
        }
    };

    es.onerror = () => {
        es.close();
        state.searchEventSource = null;
        showLoading(false);
        if (state.allSearchResults.length === 0) {
            grid.innerHTML = `<div class="empty-state"><div class="empty-icon">&#128269;</div><p>No results found for "${escHtml(query)}"</p></div>`;
        }
    };
}

function getDealType(deal) { return deal.dealType || ''; }

function matchesFilters(deal) {
    if (state.category) {
        const cat = getDealCategory(deal);
        if (cat !== state.category) return false;
    }
    if (state.offerPgm) {
        const pgm = getDealPgm(deal);
        if (pgm !== state.offerPgm) return false;
    }
    if (state.dealType) {
        if (getDealType(deal) !== state.dealType) return false;
    }
    if (state.expiry) {
        const days = daysUntilExpiry(deal);
        const maxDays = { today: 0, week: 7, month: 30 }[state.expiry];
        if (days === null || maxDays === undefined || days > maxDays) return false;
    }
    if (state.hasProducts) {
        if (!(deal.productCount > 0)) return false;
    }
    return true;
}

function applyClientFilters() {
    if (!state.searchMode) return;

    const filtered = state.allSearchResults.filter(matchesFilters);
    grid.innerHTML = '';
    filtered.forEach((deal) => {
        grid.appendChild(createDealCard(deal));
    });

    const query = escHtml(state.searchQuery);
    if (filtered.length === 0) {
        grid.innerHTML = `<div class="empty-state"><div class="empty-icon">&#128269;</div><p>No results match your filters for "${query}"</p></div>`;
    }
    resultsInfo.textContent = `${filtered.length} of ${state.allSearchResults.length} result${state.allSearchResults.length !== 1 ? 's' : ''} for "${query}"`;
}

function exitSearchMode() {
    if (state.searchEventSource) {
        state.searchEventSource.close();
        state.searchEventSource = null;
    }
    state.searchMode = false;
    state.searchQuery = '';
    state.allSearchResults = [];
    state.currentPage = 1;
    pagination.classList.remove('hidden');
    const expandedEl = $('#search-expanded');
    if (expandedEl) expandedEl.textContent = '';
    fetchDeals();
}

/* ===== Rendering Helpers ===== */

function renderDeals(deals) {
    grid.innerHTML = '';
    if (!deals.length) {
        grid.innerHTML = `<div class="empty-state"><div class="empty-icon">&#128722;</div><p>No deals found</p></div>`;
        return;
    }
    deals.forEach((deal) => {
        grid.appendChild(createDealCard(deal));
    });
}

function reRenderAll() {
    if (state.searchMode) {
        applyClientFilters();
    } else {
        renderDeals(state.deals);
    }
}

function updatePagination() {
    if (state.searchMode) {
        pagination.classList.add('hidden');
        return;
    }
    pagination.classList.remove('hidden');
    prevBtn.disabled = state.currentPage <= 1;
    nextBtn.disabled = state.currentPage >= state.totalPages;
    pageInfo.textContent = `Page ${state.currentPage} of ${state.totalPages}`;
}

function showLoading(show) {
    loading.classList.toggle('active', show);
}

/* ===== Design Picker & Voting ===== */

function loadVotes() {
    try {
        const raw = localStorage.getItem('cardStyleVotes');
        if (raw) state.votes = JSON.parse(raw);
    } catch (_) {}
    if (!state.votes || typeof state.votes !== 'object') state.votes = {};

    const saved = localStorage.getItem('cardStyle');
    if (saved) {
        const n = parseInt(saved, 10);
        if (n >= 1 && n <= 10) state.cardStyle = n;
    }
}

function saveVotes() {
    localStorage.setItem('cardStyleVotes', JSON.stringify(state.votes));
    localStorage.setItem('cardStyle', String(state.cardStyle));
}

function saveExampleDeal(styleNum) {
    const deals = state.searchMode ? state.allSearchResults : state.deals;
    if (!deals || !deals.length) return;
    if (!state.votes[styleNum]) state.votes[styleNum] = { vote: null, exampleDeal: null };
    state.votes[styleNum].exampleDeal = {
        name: getDealName(deals[0]),
        offerPrice: getDealPrice(deals[0]),
        category: getDealCategory(deals[0]),
    };
    saveVotes();
}

function getVisiblePickerBtns() {
    return Array.from($$('.picker-btn')).filter(b => !b.classList.contains('downvoted'));
}

function applyVoteVisuals() {
    let hasDownvoted = false;
    $$('.picker-btn').forEach(btn => {
        const style = btn.dataset.style;
        const entry = state.votes[style];
        const vote = entry ? entry.vote : null;

        btn.classList.remove('upvoted', 'downvoted');
        const upBtn = btn.querySelector('.vote-up');
        if (upBtn) upBtn.classList.remove('voted');

        if (vote === 'up') {
            btn.classList.add('upvoted');
            if (upBtn) upBtn.classList.add('voted');
        } else if (vote === 'down') {
            btn.classList.add('downvoted');
            hasDownvoted = true;
        }
    });

    const resetBtn = $('#reset-votes');
    if (resetBtn) resetBtn.classList.toggle('visible', hasDownvoted);
}

function initDesignPicker() {
    loadVotes();

    const buttons = $$('.picker-btn');

    // Apply persisted vote visuals & hide downvoted
    applyVoteVisuals();

    // If persisted style is downvoted, switch to first visible
    const activeStyle = state.cardStyle;
    const activeEntry = state.votes[activeStyle];
    if (activeEntry && activeEntry.vote === 'down') {
        const visible = getVisiblePickerBtns();
        if (visible.length) {
            state.cardStyle = parseInt(visible[0].dataset.style, 10);
            saveVotes();
        }
    }

    // Set active button from persisted style
    buttons.forEach(b => b.classList.remove('active'));
    const activeBtn = document.querySelector(`.picker-btn[data-style="${state.cardStyle}"]`);
    if (activeBtn) activeBtn.classList.add('active');

    // Style-switch click handler
    buttons.forEach(btn => {
        btn.addEventListener('click', (e) => {
            // Don't switch style if a vote button was clicked
            if (e.target.closest('.vote-btn')) return;

            const style = parseInt(btn.dataset.style, 10);
            state.cardStyle = style;
            buttons.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            saveExampleDeal(style);
            saveVotes();
            reRenderAll();
        });
    });

    // Vote click handlers
    $$('.vote-btn').forEach(voteBtn => {
        voteBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            const pickerBtn = voteBtn.closest('.picker-btn');
            const style = pickerBtn.dataset.style;
            const voteType = voteBtn.dataset.vote;

            if (!state.votes[style]) state.votes[style] = { vote: null, exampleDeal: null };

            if (voteType === 'up') {
                // Toggle: if already up, clear it
                state.votes[style].vote = state.votes[style].vote === 'up' ? null : 'up';
                applyVoteVisuals();
                saveVotes();
            } else if (voteType === 'down') {
                // Can't downvote the last visible style
                const visible = getVisiblePickerBtns();
                if (visible.length <= 1) {
                    alert('You must keep at least one card style visible.');
                    return;
                }

                state.votes[style].vote = 'down';
                applyVoteVisuals();

                // If this was the active style, switch to next visible
                if (parseInt(style, 10) === state.cardStyle) {
                    const nextVisible = getVisiblePickerBtns();
                    if (nextVisible.length) {
                        const nextStyle = parseInt(nextVisible[0].dataset.style, 10);
                        state.cardStyle = nextStyle;
                        buttons.forEach(b => b.classList.remove('active'));
                        nextVisible[0].classList.add('active');
                        reRenderAll();
                    }
                }
                saveVotes();
            }
        });
    });

    // Reset hidden styles button
    const resetBtn = $('#reset-votes');
    if (resetBtn) {
        resetBtn.addEventListener('click', () => {
            Object.keys(state.votes).forEach(key => {
                if (state.votes[key] && state.votes[key].vote === 'down') {
                    state.votes[key].vote = null;
                }
            });
            applyVoteVisuals();
            saveVotes();
        });
    }
}

/* ===== CTA Click Handler ===== */
const CTA_DONE_LABELS = {
    'cta-clip':   'Clipped \u2713',
    'cta-add':    'Added \u2713',
    'cta-details':'Viewed \u2713',
    'cta-save':   'Saved \u2713',
    'cta-grab':   'Grabbed \u2713',
    'cta-unlock': 'Unlocked \u2713',
    'cta-shop':   'Saved \u2713',
    'cta-neon':   'Got It \u2713',
    'cta-redeem': 'Redeemed \u2713',
    'cta-cart':   'In Cart \u2713',
};

grid.addEventListener('click', (e) => {
    const btn = e.target.closest('.cta-btn');
    if (!btn || btn.classList.contains('cta-clicked')) return;
    btn.classList.add('cta-clicked');
    for (const [cls, label] of Object.entries(CTA_DONE_LABELS)) {
        if (btn.classList.contains(cls)) {
            btn.textContent = label;
            break;
        }
    }
});

/* ===== Event Listeners ===== */

searchInput.addEventListener('input', () => {
    const val = searchInput.value;
    searchClear.classList.toggle('visible', val.length > 0);

    clearTimeout(state.debounceTimer);
    state.debounceTimer = setTimeout(() => {
        startSearch(val);
    }, 300);
});

searchClear.addEventListener('click', () => {
    searchInput.value = '';
    searchClear.classList.remove('visible');
    exitSearchMode();
});

filterCategory.addEventListener('change', () => {
    state.category = filterCategory.value;
    if (state.searchMode) {
        applyClientFilters();
    } else {
        state.currentPage = 1;
        fetchDeals();
    }
});

filterType.addEventListener('change', () => {
    state.offerPgm = filterType.value;
    if (state.searchMode) {
        applyClientFilters();
    } else {
        state.currentPage = 1;
        fetchDeals();
    }
});

filterDealType.addEventListener('change', () => {
    state.dealType = filterDealType.value;
    if (state.searchMode) {
        applyClientFilters();
    } else {
        state.currentPage = 1;
        fetchDeals();
    }
});

filterExpiry.addEventListener('change', () => {
    state.expiry = filterExpiry.value;
    if (state.searchMode) {
        applyClientFilters();
    } else {
        state.currentPage = 1;
        fetchDeals();
    }
});

filterHasProducts.addEventListener('change', () => {
    state.hasProducts = filterHasProducts.checked;
    if (state.searchMode) {
        applyClientFilters();
    } else {
        state.currentPage = 1;
        fetchDeals();
    }
});

prevBtn.addEventListener('click', () => {
    if (state.currentPage > 1) {
        state.currentPage--;
        fetchDeals();
        window.scrollTo({ top: 0, behavior: 'smooth' });
    }
});

nextBtn.addEventListener('click', () => {
    if (state.currentPage < state.totalPages) {
        state.currentPage++;
        fetchDeals();
        window.scrollTo({ top: 0, behavior: 'smooth' });
    }
});

/* ===== Init ===== */

async function init() {
    initDesignPicker();
    await fetchCategories();
    await fetchDeals();
    saveExampleDeal(state.cardStyle);
}

init();
