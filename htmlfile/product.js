document.addEventListener('DOMContentLoaded', () => {

    // 1. Staggered Entrance Animation for Products
    const grid = document.getElementById('productsGrid');
    const statusMessage = document.getElementById('statusMessage');
    const loadLatestBtn = document.getElementById('loadLatestBtn');
    const userNameEl = document.getElementById('userName');
    const userSinceEl = document.getElementById('userSince');
    const userAvatarEl = document.getElementById('userAvatar');
    const signOutBtn = document.getElementById('signOutBtn');

    const staggerIn = () => {
        const products = document.querySelectorAll('.product-card');
        products.forEach((product, index) => {
            product.style.opacity = '0';
            product.style.transform = 'translateY(20px)';
            setTimeout(() => {
                product.style.transition = 'all 0.6s cubic-bezier(0.2, 0.8, 0.2, 1)';
                product.style.opacity = '1';
                product.style.transform = 'translateY(0)';
            }, 80 * index);
        });
    };

    const loadUserProfile = () => {
        const raw = localStorage.getItem('snapit_user');
        if (!raw) return;
        try {
            const user = JSON.parse(raw);
            if (userNameEl && user.name) userNameEl.textContent = user.name;
            if (userSinceEl && user.created_at) {
                const year = new Date(user.created_at).getFullYear();
                if (!Number.isNaN(year)) userSinceEl.textContent = `Member since ${year}`;
            }
            if (userAvatarEl && user.name) userAvatarEl.textContent = user.name.trim()[0].toUpperCase();
        } catch (e) {
            console.error(e);
        }
    };

    // 2. Search Filter Logic & Expandable Bar
    const searchBar = document.getElementById('searchBar');
    const searchInput = document.getElementById('searchInput');
    const retryTimers = [];

    const clearRetries = () => {
        while (retryTimers.length) {
            const t = retryTimers.pop();
            clearTimeout(t);
        }
    };

    async function runSearch(term, attempt = 1, maxAttempts = 3) {
        try {
            setStatus(`Attempt ${attempt}/${maxAttempts} for "${term}" ...`);

            // First try existing data
            const preExisting = await fetchCombined(term, { silentIfEmpty: true });
            if (preExisting && preExisting.length) {
                renderProducts(preExisting, term);
                setStatus(`Showing ${preExisting.length} saved results for "${term}"`);
            }

            // Trigger scrapes
            setStatus(`Scraping "${term}" (attempt ${attempt}/${maxAttempts}) ...`);
            await scrapeBoth(term);

            // Reload combined after scrape
            const fresh = await fetchCombined(term, { silentIfEmpty: true });
            if (fresh && fresh.length) {
                renderProducts(fresh, term);
                setStatus(`Showing ${fresh.length} scraped results for "${term}"`);
            }

            if (attempt < maxAttempts) {
                setStatus(`Scheduling attempt ${attempt + 1}/${maxAttempts} in 20s ...`);
                const t = setTimeout(() => runSearch(term, attempt + 1, maxAttempts), 20000);
                retryTimers.push(t);
            } else {
                setStatus('Finished 3 attempts.');
            }
        } catch (err) {
            console.error(err);
            setStatus('Could not complete search.');
        }
    }

    if (searchBar && searchInput) {
        // Expand on click
        searchBar.addEventListener('click', () => {
            searchBar.classList.add('active');
            searchInput.focus();
        });

        // Collapse on blur if empty (optional, but good UX)
        searchInput.addEventListener('blur', () => {
            if (searchInput.value === '') {
                searchBar.classList.remove('active');
            }
        });

        // On Enter, send term to backend scraper then fetch results
        searchInput.addEventListener('keydown', async (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                const term = searchInput.value.trim();
                if (!term) return;
                clearRetries();
                runSearch(term, 1, 3);
            }
        });
    }

    if (signOutBtn) {
        signOutBtn.addEventListener('click', () => {
            localStorage.removeItem('snapit_user');
            window.location.href = 'sign in.html';
        });
    }

    // Allow loading latest scrape without typing
    if (loadLatestBtn) {
        loadLatestBtn.addEventListener('click', async () => {
            await fetchLatestCombined();
        });
    }

    // 3. Hover 3D Tilt Effect
    const attachTilt = () => {
        const products = document.querySelectorAll('.product-card');
        products.forEach(product => {
            product.addEventListener('mousemove', (e) => {
                const rect = product.getBoundingClientRect();
                const x = e.clientX - rect.left;
                const y = e.clientY - rect.top;

                const centerX = rect.width / 2;
                const centerY = rect.height / 2;

                const rotateX = ((y - centerY) / centerY) * -5;
                const rotateY = ((x - centerX) / centerX) * 5;

                product.style.transform = `perspective(1000px) rotateX(${rotateX}deg) rotateY(${rotateY}deg) scale(1.02)`;
            });

            product.addEventListener('mouseleave', () => {
                product.style.transform = 'perspective(1000px) rotateX(0) rotateY(0) scale(1)';
            });
        });
    };

    function setStatus(msg) {
        if (statusMessage) statusMessage.textContent = msg;
    }

    function platformBadge(platform) {
        if (!platform) return { label: '•', cls: 'offline' };
        const p = platform.toLowerCase();
        if (p.includes('blink')) return { label: 'B', cls: 'blinkit' };
        if (p.includes('zept')) return { label: 'Z', cls: 'zepto' };
        if (p.includes('insta')) return { label: 'I', cls: 'instamart' };
        if (p.includes('amazon')) return { label: 'A', cls: 'amazon' };
        if (p.includes('flip')) return { label: 'F', cls: 'flipkart' };
        return { label: platform[0].toUpperCase(), cls: 'offline' };
    }

    const normalizeName = (str = '') => str.toLowerCase().replace(/[^a-z0-9\s]/g, ' ').replace(/\s+/g, ' ').trim();

    const dedupeByKey = (rows) => {
        const seen = new Set();
        const out = [];
        rows.forEach((r) => {
            const key = [r.platform || '', r.product_name || '', r.price || '', r.quantity || '', r.url || ''].join('|');
            if (!seen.has(key)) {
                seen.add(key);
                out.push(r);
            }
        });
        return out;
    };

    function renderProducts(items, priorityTerm = null) {
        if (!grid) return;
        grid.innerHTML = '';
        if (!items || items.length === 0) {
            setStatus('No results yet.');
            return;
        }

        const groups = new Map();
        items.forEach((item) => {
            const name = item.product_name || item.search_term || 'Unknown';
            const norm = normalizeName(name);
            if (!groups.has(norm)) {
                groups.set(norm, { name, term: item.search_term || '', zepto: [], blinkit: [], other: [] });
            }
            const bucket = groups.get(norm);
            // prefer the longest/most descriptive name for display
            if ((item.product_name || '').length > bucket.name.length) bucket.name = item.product_name;
            if (!bucket.term && item.search_term) bucket.term = item.search_term;
            const plat = (item.platform || '').toLowerCase();
            if (plat.includes('zept')) bucket.zepto.push(item);
            else if (plat.includes('blink')) bucket.blinkit.push(item);
            else bucket.other.push(item);
        });

        // dedupe within each source
        groups.forEach((g) => {
            g.zepto = dedupeByKey(g.zepto);
            g.blinkit = dedupeByKey(g.blinkit);
            g.other = dedupeByKey(g.other);
        });

        const orderedEntries = Array.from(groups.entries()).sort((a, b) => {
            const aTerm = (a[1].term || '').toLowerCase();
            const bTerm = (b[1].term || '').toLowerCase();
            const p = (priorityTerm || '').toLowerCase();
            if (p) {
                if (aTerm === p && bTerm !== p) return -1;
                if (bTerm === p && aTerm !== p) return 1;
            }
            return 0;
        });

        orderedEntries.forEach(([, group]) => {
            const name = group.name;
            const term = group.term;
            const zRow = group.zepto[0] || null;
            const bRow = group.blinkit[0] || null;

            const card = document.createElement('div');
            card.className = 'product-card';
            card.innerHTML = `
                <div class="card-header">
                    <h3>${name}</h3>
                    <div class="subtitle">${term || ''}</div>
                </div>
                <div class="card-body">
                    <div class="product-preview">🛍️</div>
                    <div class="compare-grid"></div>
                </div>
            `;

            const gridEl = card.querySelector('.compare-grid');

            const buildCol = (labelTxt, row) => {
                const hasRow = !!row;
                const { label, cls } = platformBadge(labelTxt);
                const price = row?.price || '—';
                const qty = row?.quantity || row?.raw_text || '';
                const url = row?.url || '';
                const col = document.createElement('div');
                col.className = 'compare-col';
                col.innerHTML = `
                    <div class="store-head">
                        <div class="store-badge ${cls}">${label}</div>
                        <div class="store-name">${labelTxt}</div>
                    </div>
                    <div class="compare-price">${price}</div>
                    <div class="compare-qty">${qty || 'Not available'}</div>
                `;
                if (hasRow && url && url !== '#') {
                    col.style.cursor = 'pointer';
                    col.addEventListener('click', () => window.open(url, '_blank'));
                }
                return col;
            };

            const rowWrap = document.createElement('div');
            rowWrap.className = 'compare-row';
            rowWrap.appendChild(buildCol('Zepto', zRow));
            rowWrap.appendChild(buildCol('Blinkit', bRow));

            gridEl.appendChild(rowWrap);

            grid.appendChild(card);
        });

        setStatus('');
        staggerIn();
        attachTilt();
    }

    async function fetchAndRender(term, opts = {}) {
        try {
            setStatus(`Loading results for "${term}" ...`);

            const [zepRes, blkRes] = await Promise.allSettled([
                fetch(`http://localhost:5000/results?term=${encodeURIComponent(term)}`),
                fetch(`http://localhost:5001/results?term=${encodeURIComponent(term)}`)
            ]);

            let items = [];
            let hadError = false;

            if (zepRes.status === 'fulfilled') {
                try {
                    const resp = zepRes.value;
                    const body = await resp.json();
                    if (resp.ok) {
                        items = items.concat(body.items || []);
                    } else {
                        hadError = true;
                    }
                } catch (e) {
                    hadError = true;
                }
            } else {
                hadError = true;
            }

            if (blkRes.status === 'fulfilled') {
                try {
                    const resp = blkRes.value;
                    const body = await resp.json();
                    if (resp.ok) {
                        items = items.concat(body.items || []);
                    } else {
                        hadError = true;
                    }
                } catch (e) {
                    hadError = true;
                }
            } else {
                hadError = true;
            }

            if (!items.length && opts.silentIfEmpty) {
                setStatus('');
                return [];
            }

            if (!items.length) {
                setStatus(hadError ? 'Could not load results.' : 'No results yet.');
                return [];
            }

            renderProducts(items, term);
            setStatus('');
            return items;
        } catch (err) {
            console.error(err);
            setStatus('Could not load results.');
            return [];
        }
    }

    async function fetchLatestCombined() {
        try {
            setStatus('Loading latest Zepto + Blinkit results ...');
            const [zepRes, blkRes] = await Promise.allSettled([
                fetch('http://localhost:5000/latest'),
                fetch('http://localhost:5001/latest')
            ]);

            let items = [];
            let hadError = false;
            let lastTerm = null;

            if (zepRes.status === 'fulfilled') {
                try {
                    const resp = zepRes.value;
                    const body = await resp.json();
                    if (resp.ok) {
                        items = items.concat(body.items || []);
                        lastTerm = lastTerm || body.last_term || null;
                    } else {
                        hadError = true;
                    }
                } catch (e) {
                    hadError = true;
                }
            } else {
                hadError = true;
            }

            if (blkRes.status === 'fulfilled') {
                try {
                    const resp = blkRes.value;
                    const body = await resp.json();
                    if (resp.ok) {
                        items = items.concat(body.items || []);
                        lastTerm = lastTerm || body.last_term || null;
                    } else {
                        hadError = true;
                    }
                } catch (e) {
                    hadError = true;
                }
            } else {
                hadError = true;
            }

            if (!items.length) {
                setStatus(hadError ? 'Could not load latest results.' : 'No scraped results yet.');
                return;
            }

            setStatus('Showing latest Zepto + Blinkit results');
            renderProducts(items, lastTerm);
        } catch (err) {
            console.error(err);
            setStatus('Could not load latest results.');
        }
    }

    async function fetchCombined(term, opts = {}) {
        // convenience wrapper for fetchAndRender signature compatibility
        return fetchAndRender(term, opts);
    }

    async function scrapeBoth(term) {
        const errors = [];
        const responses = await Promise.allSettled([
            fetch('http://localhost:5000/scrape', {
                method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ product: term })
            }),
            fetch('http://localhost:5001/scrape', {
                method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ product: term })
            })
        ]);

        for (const res of responses) {
            if (res.status === 'fulfilled') {
                const ok = res.value.ok;
                const body = await res.value.json();
                if (!ok || body.status === 'error') {
                    errors.push(body.error || body.stderr || 'Scrape error');
                }
            } else {
                errors.push(res.reason?.message || 'Scrape request failed');
            }
        }
        return errors;
    }

    // Auto-load latest on page open so user sees freshly scraped data without typing.
    fetchLatestCombined();
    loadUserProfile();

    // 4. Location Dropdown Logic
    const locationPill = document.getElementById('locationPill');
    const locationDropdown = document.getElementById('locationDropdown');
    const locationText = document.getElementById('locationText');

    if (locationPill && locationDropdown) {
        // Toggle
        locationPill.addEventListener('click', (e) => {
            e.stopPropagation();
            locationDropdown.classList.toggle('active');
            // Close profile if open
            if (profileDropdown) profileDropdown.classList.remove('active');
        });
    }

    // 5. PROFILE DROPDOWN LOGIC (NEW)
    const profileBtn = document.getElementById('profileBtn');
    const profileDropdown = document.getElementById('profileDropdown');

    if (profileBtn && profileDropdown) {
        profileBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            profileDropdown.classList.toggle('active');
            // Close location if open
            if (locationDropdown) locationDropdown.classList.remove('active');
        });
    }

    // Global Click Listener to Close Dropdowns
    document.addEventListener('click', (e) => {
        // Close Location Dropdown
        if (locationDropdown && locationPill &&
            !locationDropdown.contains(e.target) &&
            !locationPill.contains(e.target)) {
            locationDropdown.classList.remove('active');
        }

        // Close Profile Dropdown
        if (profileDropdown && profileBtn &&
            !profileDropdown.contains(e.target) &&
            !profileBtn.contains(e.target)) {
            profileDropdown.classList.remove('active');
        }

        // Close Search Bar (if not clicking inside)
        if (searchBar && !searchBar.contains(e.target) && searchInput.value === '') {
            searchBar.classList.remove('active');
        }
    });

    // 6. Use Current Location (Real Geolocation API)
    const currentLocBtn = document.getElementById('currentLocationBtn');
    if (currentLocBtn) {
        currentLocBtn.addEventListener('click', () => {
            if (!navigator.geolocation) {
                alert("Geolocation is not supported by your browser.");
                return;
            }

            if (locationText) locationText.innerText = "Detecting...";

            navigator.geolocation.getCurrentPosition((position) => {
                // Success
                setTimeout(() => {
                    if (locationText) locationText.innerText = "Indiranagar, Bangalore";
                    if (locationDropdown) locationDropdown.classList.remove('active');

                    // Optional fill
                    const areaField = document.getElementById('addrArea');
                    const roadField = document.getElementById('addrRoad');
                    if (areaField) areaField.value = "Indiranagar";
                    if (roadField) roadField.value = "100 Feet Road";
                }, 800);

            }, (error) => {
                // Error
                console.error("Error getting location:", error);
                let msg = "Location error.";
                switch (error.code) {
                    case error.PERMISSION_DENIED: msg = "Permission denied."; break;
                    case error.POSITION_UNAVAILABLE: msg = "Position unavailable."; break;
                    case error.TIMEOUT: msg = "Request timed out."; break;
                }
                if (locationText) locationText.innerText = msg;
            }, {
                enableHighAccuracy: true,
                timeout: 5000,
                maximumAge: 0
            });
        });
    }

    // Helper to capitalize
    const capitalize = (str) => {
        return str.replace(/\b\w/g, l => l.toUpperCase());
    };

    // 7. Save Manual Address
    const saveAddrBtn = document.getElementById('saveAddrBtn');
    if (saveAddrBtn) {
        saveAddrBtn.addEventListener('click', () => {
            const area = document.getElementById('addrArea').value.trim();
            const pin = document.getElementById('addrPin').value.trim();
            const road = document.getElementById('addrRoad').value.trim();

            if (area && pin) {
                const formattedArea = capitalize(area);
                const formattedRoad = road ? capitalize(road) : "";

                const displayLoc = formattedRoad ? `${formattedArea}, ${formattedRoad}` : `${formattedArea}, ${pin}`;

                if (locationText) locationText.innerText = displayLoc;
                if (locationDropdown) locationDropdown.classList.remove('active');
            } else {
                alert("Please enter at least Area and Pincode");
            }
        });
    }

});
