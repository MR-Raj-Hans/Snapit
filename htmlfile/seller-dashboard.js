const API_BASE = window.SNAPIT_API_BASE || localStorage.getItem("snapit_api_base") || "http://localhost:5000";

document.addEventListener("DOMContentLoaded", () => {
  const user = getUser();
  hydrateProfile(user);
  bindControls(user);
  fetchProducts(user);
  fetchNotices(user);
});

function getUser() {
  try {
    return JSON.parse(localStorage.getItem("snapit_user") || "null");
  } catch (e) {
    return null;
  }
}

function getSellerId(user) {
  return user?.id || user?._id || user?.seller_id || user?.sellerId || null;
}

function hydrateProfile(user) {
  if (!user || !user.sellerDetails) return;
  const d = user.sellerDetails;
  setText("storeName", d.shop || "—");
  setText("ownerName", d.owner || "—");
  setText("whatsapp", d.whatsapp || "—");
  setText("storeEmail", d.sellerEmail || user.email || "—");
  setText("storeAddress", d.address || "—");
  setText("ownerMini", d.owner || "—");
  setText("waMini", d.whatsapp || "—");
  setText("phoneMini", d.phone || "—");
  setText("emailMini", d.sellerEmail || user.email || "—");
}

function showModal({ title, body, onSubmit, submitLabel = "Save" }) {
  const backdrop = document.createElement("div");
  backdrop.className = "modal-backdrop";

  const modal = document.createElement("div");
  modal.className = "modal";

  const header = document.createElement("div");
  header.className = "modal-head";
  header.innerHTML = `<h3>${title}</h3><button class="ghost close-btn" aria-label="Close">✕</button>`;

  const content = document.createElement("div");
  content.className = "modal-body";
  content.appendChild(body);

  const footer = document.createElement("div");
  footer.className = "modal-foot";
  const submit = document.createElement("button");
  submit.className = "primary";
  submit.textContent = submitLabel;
  footer.appendChild(submit);

  modal.appendChild(header);
  modal.appendChild(content);
  modal.appendChild(footer);
  backdrop.appendChild(modal);
  document.body.appendChild(backdrop);

  const close = () => backdrop.remove();
  header.querySelector(".close-btn")?.addEventListener("click", close);
  backdrop.addEventListener("click", (e) => {
    if (e.target === backdrop) close();
  });

  submit.addEventListener("click", async () => {
    try {
      const ok = await onSubmit();
      if (ok !== false) close();
    } catch (err) {
      console.error(err);
    }
  });
}

function bindControls(user) {
  document.getElementById("logoutBtn")?.addEventListener("click", () => {
    localStorage.clear();
    window.location.href = "sign in.html";
  });

  document.getElementById("refreshBtn")?.addEventListener("click", () => {
    window.location.reload();
  });

  document.getElementById("addProductBtn")?.addEventListener("click", () => {
    addProductFlow(user);
  });

  document.getElementById("bulkUploadBtn")?.addEventListener("click", () => {
    alert("Bulk upload coming soon. For now, add products one by one.");
  });

  document.getElementById("priceHistoryBtn")?.addEventListener("click", () => {
    alert("Price history view is not wired yet.");
  });

  document.getElementById("ordersAllBtn")?.addEventListener("click", () => {
    alert("Orders list is not wired yet.");
  });

  document.getElementById("ratingsBtn")?.addEventListener("click", () => {
    alert("Feedback list is not wired yet.");
  });

  document.getElementById("addNoticeBtn")?.addEventListener("click", () => {
    addNoticeFlow(user);
  });

  document.getElementById("editProfileBtn")?.addEventListener("click", () => editProfileFlow(user));
  document.getElementById("updateContactBtn")?.addEventListener("click", () => editContactFlow(user));
  document.getElementById("editOwnerBtn")?.addEventListener("click", () => editOwnerFlow(user));
  document.getElementById("priceHistoryBtn")?.addEventListener("click", () => viewHistory(user));
  document.getElementById("ordersAllBtn")?.addEventListener("click", () => viewHistory(user));
  document.getElementById("ratingsBtn")?.addEventListener("click", () => viewHistory(user));
}

async function fetchProducts(user) {
  const table = document.getElementById("productsTable");
  if (!table) return;
  const sellerId = getSellerId(user);
  if (!sellerId) {
    table.innerHTML = `<div class="row"><div class="empty">Login again to load products.</div></div>`;
    return;
  }

  table.innerHTML = `<div class="row"><div class="empty">Loading products...</div></div>`;
  try {
    const resp = await fetch(`${API_BASE}/seller/products?seller_id=${encodeURIComponent(sellerId)}&include_contact=1`);
    if (!resp.ok) throw new Error("Failed to load products");
    const data = await resp.json();
    renderProducts(data.items || []);
  } catch (err) {
    table.innerHTML = `<div class="row"><div class="empty">Could not load products.</div></div>`;
    console.error(err);
  }
}

function renderProducts(items) {
  const table = document.getElementById("productsTable");
  if (!table) return;

  if (!items.length) {
    table.innerHTML = `<div class="row"><div class="empty">No products yet.</div></div>`;
    return;
  }

  const head = `<div class="row head"><div>Name</div><div>Category</div><div>Price</div><div>Stock</div><div>Status</div></div>`;
  const rows = items.map((p) => {
    const contact = p.seller_contact?.whatsapp || p.seller_contact?.phone;
    const waLink = contact ? `<a href="https://wa.me/${encodeURIComponent(contact)}?text=Hi%20I%20want%20to%20order%20${encodeURIComponent(p.name || "product")}" target="_blank" rel="noreferrer">WhatsApp</a>` : "—";
    return `<div class="row">
      <div>${escapeHtml(p.name || "—")}<div class="meta">${waLink}</div><div class="meta">Expiry: ${escapeHtml(p.expiry_date || "-")}</div><div class="meta">Quality: ${escapeHtml(p.quality_condition || "-")}</div></div>
      <div>${escapeHtml(p.category || "-")}</div>
      <div>${p.price ?? "-"}</div>
      <div>${p.stock ?? "-"}</div>
      <div>${p.status || "Live"}</div>
    </div>`;
  }).join("");

  table.innerHTML = head + rows;
}

async function addProductFlow(user) {
  const sellerId = getSellerId(user);
  if (!sellerId) {
    alert("Please login again.");
    return;
  }
  const mount = document.getElementById("productInlineEditor");
  if (!mount) return;

  const nameInput = mount.querySelector("#pName");
  const categoryInput = mount.querySelector("#pCategory");
  const priceInput = mount.querySelector("#pPrice");
  const stockInput = mount.querySelector("#pStock");
  const statusSelect = mount.querySelector("#pStatus");
  const expiryInput = mount.querySelector("#pExpiry");
  const qualityInput = mount.querySelector("#pQuality");
  const descInput = mount.querySelector("#pDesc");

  const close = () => mount.classList.add("hidden");
  const reset = () => {
    if (nameInput) nameInput.value = "";
    if (categoryInput) categoryInput.value = "";
    if (priceInput) priceInput.value = "";
    if (stockInput) stockInput.value = "";
    if (statusSelect) statusSelect.value = "Live";
    if (expiryInput) expiryInput.value = "";
    if (qualityInput) qualityInput.value = "";
    if (descInput) descInput.value = "";
  };

  if (!mount.dataset.wired) {
    mount.querySelector("#prodCloseBtn")?.addEventListener("click", close);
    mount.querySelector("#prodCancelBtn")?.addEventListener("click", close);

    mount.querySelector("#prodSaveBtn")?.addEventListener("click", async () => {
      const name = nameInput?.value.trim() || "";
      const category = categoryInput?.value.trim() || "";
      const priceVal = priceInput?.value;
      const stockVal = stockInput?.value;
      const status = statusSelect?.value || "Live";
      const expiry_date = expiryInput?.value || "";
      const quality_condition = qualityInput?.value.trim() || "";
      const description = descInput?.value.trim() || "";

      if (!name) {
        alert("Product name is required.");
        return;
      }

      const price = priceVal ? Number(priceVal) : undefined;
      const stock = stockVal ? Number(stockVal) : undefined;

      try {
        const resp = await fetch(`${API_BASE}/seller/products`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            seller_id: sellerId,
            name,
            price: Number.isFinite(price) ? price : undefined,
            stock: Number.isFinite(stock) ? stock : undefined,
            description,
            expiry_date,
            quality_condition,
            category,
            status,
          }),
        });
        if (!resp.ok) throw new Error("Add failed");
        await fetchProducts(user);
        close();
      } catch (err) {
        console.error(err);
        alert("Could not add product.");
      }
    });

    mount.dataset.wired = "1";
  }

  reset();
  mount.classList.remove("hidden");
}

async function editProfileFlow(user) {
  if (!user?.id) return alert("Please login again.");
  const mount = document.getElementById("profileInlineEditor");
  if (!mount) return;

  const close = () => mount.classList.add("hidden");

  mount.innerHTML = `
    <div class="inline-card">
      <div class="inline-head">
        <h4>Edit store profile</h4>
        <button class="ghost" id="inlineCloseBtn" type="button">✕</button>
      </div>
      <div class="form-grid">
        <label>Store name<input id="shopInput" type="text" value="${escapeHtml(user.sellerDetails?.shop || "")}"></label>
        <label>Store address<textarea id="addrInput" rows="3">${escapeHtml(user.sellerDetails?.address || "")}</textarea></label>
        <label>GST (optional)<input id="gstInput" type="text" value="${escapeHtml(user.sellerDetails?.gst || "")}"></label>
      </div>
      <div class="inline-actions">
        <button class="ghost" id="inlineCancelBtn" type="button">Cancel</button>
        <button class="primary" id="inlineSaveBtn" type="button">Save changes</button>
      </div>
    </div>
  `;

  mount.classList.remove("hidden");

  mount.querySelector("#inlineCloseBtn")?.addEventListener("click", close);
  mount.querySelector("#inlineCancelBtn")?.addEventListener("click", close);

  mount.querySelector("#inlineSaveBtn")?.addEventListener("click", async () => {
    const shop = mount.querySelector("#shopInput")?.value.trim() || "";
    const address = mount.querySelector("#addrInput")?.value.trim() || "";
    const gst = mount.querySelector("#gstInput")?.value.trim() || "";
    await updateProfile(user, { ...user.sellerDetails, shop, address, gst });
    close();
  });
}

async function editContactFlow(user) {
  if (!getSellerId(user)) return alert("Please login again.");
  let otpCode = null;
  const mount = document.getElementById("contactInlineEditor");
  if (!mount) return;

  const close = () => mount.classList.add("hidden");

  mount.innerHTML = `
    <div class="inline-card">
      <div class="inline-head">
        <h4>Update contacts</h4>
        <button class="ghost" id="contactCloseBtn" type="button">✕</button>
      </div>
      <div class="form-grid">
        <label>Email<input id="emailInput" type="email" value="${escapeHtml(user.sellerDetails?.sellerEmail || user.email || "")}"></label>
        <label>WhatsApp<input id="waInput" type="tel" value="${escapeHtml(user.sellerDetails?.whatsapp || "")}" placeholder="Include country code"></label>
        <label>Phone<input id="phoneInput" type="tel" value="${escapeHtml(user.sellerDetails?.phone || "")}"></label>
        <div class="otp-row">
          <div>
            <label>OTP<input id="otpInput" type="text" placeholder="Enter OTP" maxlength="6"></label>
          </div>
          <button class="ghost" id="sendOtpBtn" type="button">Send OTP</button>
        </div>
        <div class="hint">For demo, OTP is shown after you click Send OTP.</div>
      </div>
      <div class="inline-actions">
        <button class="ghost" id="contactCancelBtn" type="button">Cancel</button>
        <button class="primary" id="contactSaveBtn" type="button">Verify & Save</button>
      </div>
    </div>
  `;

  mount.classList.remove("hidden");

  mount.querySelector("#contactCloseBtn")?.addEventListener("click", close);
  mount.querySelector("#contactCancelBtn")?.addEventListener("click", close);

  mount.querySelector("#sendOtpBtn")?.addEventListener("click", () => {
    otpCode = String(Math.floor(100000 + Math.random() * 900000));
    alert(`OTP sent (demo): ${otpCode}`);
  });

  mount.querySelector("#contactSaveBtn")?.addEventListener("click", async () => {
    const sellerEmail = mount.querySelector("#emailInput")?.value.trim() || "";
    const whatsapp = mount.querySelector("#waInput")?.value.trim() || "";
    const phone = mount.querySelector("#phoneInput")?.value.trim() || "";
    const enteredOtp = mount.querySelector("#otpInput")?.value.trim();
    if (!otpCode) {
      alert("Send OTP first.");
      return;
    }
    if (enteredOtp !== otpCode) {
      alert("Invalid OTP.");
      return;
    }
    await updateProfile(user, { ...user.sellerDetails, sellerEmail, whatsapp, phone });
    close();
  });
}

async function editOwnerFlow(user) {
  if (!getSellerId(user)) return alert("Please login again.");
  const owner = prompt("Owner name?", user.sellerDetails?.owner || "") || "";
  await updateProfile(user, { ...user.sellerDetails, owner });
}

async function updateProfile(user, sellerDetails) {
  try {
    const resp = await fetch(`${API_BASE}/seller/profile/update`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ seller_id: getSellerId(user), sellerDetails }),
    });
    if (!resp.ok) throw new Error("Update failed");
    const newUser = { ...user, sellerDetails };
    localStorage.setItem("snapit_user", JSON.stringify(newUser));
    hydrateProfile(newUser);
    alert("Profile updated.");
  } catch (err) {
    console.error(err);
    alert("Could not update profile.");
  }
}

async function addNoticeFlow(user) {
  const sellerId = getSellerId(user);
  if (!sellerId) return alert("Please login again.");
  const title = prompt("Notice title?") || "";
  if (!title) return;
  const message = prompt("Notice message?") || "";
  try {
    const resp = await fetch(`${API_BASE}/seller/notices`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ seller_id: sellerId, title, message }),
    });
    if (!resp.ok) throw new Error("Add failed");
    await fetchNotices(user);
  } catch (err) {
    console.error(err);
    alert("Could not add notice.");
  }
}

async function fetchNotices(user) {
  const list = document.getElementById("updatesList");
  if (!list) return;
  const sellerId = getSellerId(user);
  if (!sellerId) {
    list.innerHTML = `<div class="empty">Login again to load notices.</div>`;
    return;
  }
  list.innerHTML = `<div class="empty">Loading notices...</div>`;
  try {
    const resp = await fetch(`${API_BASE}/seller/notices?seller_id=${encodeURIComponent(sellerId)}`);
    if (!resp.ok) throw new Error("Load failed");
    const data = await resp.json();
    const items = data.items || [];
    if (!items.length) {
      list.innerHTML = `<div class="empty">No notices yet.</div>`;
      return;
    }
    list.innerHTML = items.map(n => `<div class="item"><div class="title">${escapeHtml(n.title || "")}</div><div class="meta">${escapeHtml(n.message || "")}</div></div>`).join("");
  } catch (err) {
    console.error(err);
    list.innerHTML = `<div class="empty">Could not load notices.</div>`;
  }
}

async function viewHistory(user) {
  const sellerId = getSellerId(user);
  if (!sellerId) return alert("Please login again.");
  try {
    const resp = await fetch(`${API_BASE}/seller/history?seller_id=${encodeURIComponent(sellerId)}`);
    if (!resp.ok) throw new Error("Load failed");
    const data = await resp.json();
    const lines = (data.items || []).map(h => `${h.created_at || ""} • ${h.action || ""}`);
    alert(lines.slice(0, 20).join("\n") || "No history yet.");
  } catch (err) {
    console.error(err);
    alert("Could not load history.");
  }
}

function setText(id, value) {
  const el = document.getElementById(id);
  if (el) el.textContent = value;
}

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}
