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
    // Chat state
    chatOpen: false,
    chatHistory: [],
    chatStreaming: false,
    chatAbortController: null,
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

function computeFinalPrice(deal) {
    const memberPrice = deal.productPrice;
    const offerPrice = getDealPrice(deal);
    if (!memberPrice || !offerPrice) return null;

    // Dollar OFF: "$2.00 OFF" → subtract from member price
    const offMatch = offerPrice.match(/\$(\d+(?:\.\d+)?)\s*OFF/i);
    if (offMatch) {
        const discount = parseFloat(offMatch[1]);
        const final = memberPrice - discount;
        return final > 0 ? final : 0;
    }

    // FREE
    if (/FREE/i.test(offerPrice)) return 0;

    // Fixed price: "$4.99" (no OFF, no other keywords)
    const fixedMatch = offerPrice.match(/^\$(\d+(?:\.\d+)?)$/);
    if (fixedMatch) return parseFloat(fixedMatch[1]);

    return null;
}

function priceBlock(deal) {
    const memberPrice = deal.productPrice;
    const regPrice = deal.productBasePrice;
    if (!memberPrice && !regPrice) return '';

    const hasMemberDiscount = regPrice && memberPrice && regPrice > memberPrice;
    const finalPrice = computeFinalPrice(deal);

    let html = '<div class="card-prices">';

    // Regular price (crossed out if member discount exists)
    if (hasMemberDiscount) {
        html += `<span class="price-label">Reg</span><span class="price-reg">$${Number(regPrice).toFixed(2)}</span>`;
        html += `<span class="price-label">Member</span><span class="price-member">$${Number(memberPrice).toFixed(2)}</span>`;
    } else if (memberPrice) {
        html += `<span class="price-label">Price</span><span class="price-current">$${Number(memberPrice).toFixed(2)}</span>`;
    }

    // Final price after coupon
    if (finalPrice !== null) {
        html += `<span class="price-label price-label-final">Final</span><span class="price-final">$${Number(finalPrice).toFixed(2)}</span>`;
    }

    html += '</div>';
    return html;
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
    if (val.length === 0) {
        exitSearchMode();
        return;
    }
    if (val.trim().length < 2) return;
    state.debounceTimer = setTimeout(() => {
        startSearch(val);
    }, 600);
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

/* ===== Chat ===== */

const chatToggle = $('#chat-toggle');
const chatOverlay = $('#chat-overlay');
const chatPanel = $('#chat-panel');
const chatClose = $('#chat-close');
const chatMessages = $('#chat-messages');
const chatWelcome = $('#chat-welcome');
const chatInput = $('#chat-input');
const chatSend = $('#chat-send');
const chatClear = $('#chat-clear');

function clearChat() {
    state.chatHistory = [];
    chatMessages.innerHTML = '';
    chatMessages.appendChild(chatWelcome);
    chatWelcome.style.display = '';
    if (state.chatAbortController) {
        state.chatAbortController.abort();
        state.chatAbortController = null;
    }
    state.chatStreaming = false;
    chatSend.disabled = false;
}

chatClear.addEventListener('click', clearChat);

function openChat() {
    state.chatOpen = true;
    chatPanel.classList.add('open');
    chatOverlay.classList.add('visible');
    chatToggle.classList.add('hidden');
    chatInput.focus();
}

function closeChat() {
    state.chatOpen = false;
    chatPanel.classList.remove('open');
    chatOverlay.classList.remove('visible');
    chatToggle.classList.remove('hidden');
}

chatToggle.addEventListener('click', openChat);
chatClose.addEventListener('click', closeChat);
chatOverlay.addEventListener('click', closeChat);

/* Example prompt buttons */
chatWelcome.querySelectorAll('.chat-example-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        const prompt = btn.dataset.prompt;
        sendChatMessage(prompt);
    });
});

/* Auto-resize textarea */
chatInput.addEventListener('input', () => {
    chatInput.style.height = 'auto';
    chatInput.style.height = Math.min(chatInput.scrollHeight, 120) + 'px';
});

/* Enter to send, Shift+Enter for newline */
chatInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        const msg = chatInput.value.trim();
        if (msg && !state.chatStreaming) sendChatMessage(msg);
    }
});

chatSend.addEventListener('click', () => {
    const msg = chatInput.value.trim();
    if (msg && !state.chatStreaming) sendChatMessage(msg);
});

function addChatMessage(role, content) {
    // Hide welcome screen
    if (chatWelcome) chatWelcome.style.display = 'none';

    const msg = document.createElement('div');
    msg.className = `chat-msg ${role}`;

    const avatar = document.createElement('div');
    avatar.className = 'chat-msg-avatar';
    avatar.textContent = role === 'assistant' ? 'S' : 'U';

    const bubble = document.createElement('div');
    bubble.className = 'chat-msg-bubble';
    bubble.textContent = content || '';

    msg.appendChild(avatar);
    msg.appendChild(bubble);
    chatMessages.appendChild(msg);
    chatMessages.scrollTop = chatMessages.scrollHeight;
    return bubble;
}

function addThinkingIndicator() {
    const el = document.createElement('div');
    el.className = 'chat-thinking';
    el.id = 'chat-thinking';
    el.innerHTML = `
        <div class="chat-thinking-dots"><span></span><span></span><span></span></div>
        <span>Searching deals...</span>
    `;
    chatMessages.appendChild(el);
    chatMessages.scrollTop = chatMessages.scrollHeight;
    return el;
}

function removeThinkingIndicator() {
    const el = document.getElementById('chat-thinking');
    if (el) el.remove();
}

function chatPriceBlock(deal) {
    const memberPrice = deal.productPrice;
    const regPrice = deal.productBasePrice;
    if (!memberPrice && !regPrice) return '';

    const hasMemberDiscount = regPrice && memberPrice && regPrice > memberPrice;
    const finalPrice = computeFinalPrice(deal);

    let html = '<div class="chat-deal-final-price">';

    if (hasMemberDiscount) {
        html += `<span class="chat-price-reg">$${Number(regPrice).toFixed(2)}</span>`;
        html += `<span class="chat-price-member">$${Number(memberPrice).toFixed(2)}</span>`;
    } else if (memberPrice) {
        html += `<span class="chat-price-current">$${Number(memberPrice).toFixed(2)}</span>`;
    }

    if (finalPrice !== null) {
        html += `<span class="chat-price-final">$${Number(finalPrice).toFixed(2)}</span>`;
    }

    html += '</div>';
    return html;
}

function createMiniDealCard(deal) {
    const card = document.createElement('div');
    card.className = 'chat-deal-card';

    const imgUrl = deal.productImageUrl || deal.dealImageUrl || '';
    const name = deal.offer_name || deal.name || '';
    const price = deal.offer_price || deal.offerPrice || '';

    card.innerHTML = `
        ${imgUrl ? `<img class="chat-deal-img" src="${imgUrl}" alt="" onerror="this.style.display='none'">` : ''}
        <div class="chat-deal-info">
            <div class="chat-deal-name" title="${name}">${name}</div>
            <div class="chat-deal-price">${price}</div>
            ${chatPriceBlock(deal)}
        </div>
        <button class="chat-deal-cta">Clip</button>
    `;

    const cta = card.querySelector('.chat-deal-cta');
    cta.addEventListener('click', (e) => {
        e.stopPropagation();
        cta.textContent = 'Clipped!';
        cta.classList.add('clipped');
    });

    return card;
}

function addDealCards(deals) {
    const container = document.createElement('div');
    container.className = 'chat-deals';
    const shown = deals.slice(0, 8);
    shown.forEach(deal => {
        container.appendChild(createMiniDealCard(deal));
    });
    if (deals.length > 8) {
        const more = document.createElement('div');
        more.style.cssText = 'font-size:0.78rem;color:var(--text-light);padding:4px 0;';
        more.textContent = `+ ${deals.length - 8} more deals`;
        container.appendChild(more);
    }
    chatMessages.appendChild(container);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

function addSuggestionChips(suggestions) {
    if (!suggestions || suggestions.length === 0) return;
    const container = document.createElement('div');
    container.className = 'chat-suggestions';
    suggestions.forEach(text => {
        const chip = document.createElement('button');
        chip.className = 'chat-suggestion-chip';
        chip.textContent = text;
        chip.addEventListener('click', () => {
            container.remove();
            sendChatMessage(text);
        });
        container.appendChild(chip);
    });
    chatMessages.appendChild(container);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

async function sendChatMessage(message) {
    if (state.chatStreaming) return;
    state.chatStreaming = true;
    chatSend.disabled = true;

    // Show user message
    addChatMessage('user', message);
    chatInput.value = '';
    chatInput.style.height = 'auto';

    // Build history for server (exclude system — server injects it)
    const historyForServer = state.chatHistory.map(h => ({
        role: h.role,
        content: h.content,
    }));

    // Add to local history
    state.chatHistory.push({ role: 'user', content: message });

    // Create assistant bubble for streaming
    let assistantBubble = null;
    let fullResponse = '';
    let thinkingEl = null;

    try {
        state.chatAbortController = new AbortController();
        const resp = await fetch('/api/chat/stream', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message, history: historyForServer }),
            signal: state.chatAbortController.signal,
        });

        const reader = resp.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop();

            for (const line of lines) {
                if (!line.startsWith('data:')) continue;
                const payload = line.slice(5).trim();
                if (payload === '[END]') continue;

                let event;
                try { event = JSON.parse(payload); } catch { continue; }

                switch (event.type) {
                    case 'thinking':
                        thinkingEl = addThinkingIndicator();
                        break;

                    case 'guardrail':
                        assistantBubble = addChatMessage('assistant', event.message);
                        break;

                    case 'deals':
                        removeThinkingIndicator();
                        if (event.deals && event.deals.length > 0) {
                            addDealCards(event.deals);
                        }
                        break;

                    case 'token':
                        removeThinkingIndicator();
                        if (!assistantBubble) {
                            assistantBubble = addChatMessage('assistant', '');
                            assistantBubble.classList.add('streaming');
                        }
                        fullResponse += event.content;
                        assistantBubble.textContent = fullResponse;
                        chatMessages.scrollTop = chatMessages.scrollHeight;
                        break;

                    case 'done':
                        removeThinkingIndicator();
                        if (assistantBubble) {
                            assistantBubble.classList.remove('streaming');
                            // Clean suggestion line from displayed text
                            const text = assistantBubble.textContent;
                            const sugIdx = text.indexOf('SUGGESTIONS:');
                            if (sugIdx > -1) {
                                assistantBubble.textContent = text.substring(0, sugIdx).trim();
                            }
                        }
                        if (event.full_response) {
                            state.chatHistory.push({
                                role: 'assistant',
                                content: event.full_response,
                            });
                        }
                        if (event.suggestions && event.suggestions.length > 0) {
                            addSuggestionChips(event.suggestions);
                        }
                        break;
                }
            }
        }
    } catch (err) {
        if (err.name !== 'AbortError') {
            removeThinkingIndicator();
            addChatMessage('assistant', 'Something went wrong. Please try again.');
        }
    } finally {
        state.chatStreaming = false;
        chatSend.disabled = false;
        state.chatAbortController = null;
    }
}

/* ===== Init ===== */

async function init() {
    initDesignPicker();
    await fetchCategories();
    await fetchDeals();
    saveExampleDeal(state.cardStyle);
}

init();
