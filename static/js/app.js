(() => {
    "use strict";

    /* ===== State ===== */
    let currentTab = "generate";
    let certType = "standard";
    let generatedCSR = "";
    let generatedKey = "";
    let generatedCN = "";

    /* ===== DOM Refs ===== */
    const $ = (sel, ctx = document) => ctx.querySelector(sel);
    const $$ = (sel, ctx = document) => [...ctx.querySelectorAll(sel)];

    /* ===== Theme Toggle ===== */
    function initTheme() {
        const saved = localStorage.getItem("csrgen-theme");
        const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
        const theme = saved || (prefersDark ? "dark" : "light");
        document.documentElement.setAttribute("data-theme", theme);
    }

    function toggleTheme() {
        const current = document.documentElement.getAttribute("data-theme");
        const next = current === "dark" ? "light" : "dark";
        document.documentElement.setAttribute("data-theme", next);
        localStorage.setItem("csrgen-theme", next);
    }

    /* ===== Toasts ===== */
    function showToast(message, type = "info") {
        const container = $("#toast-container");
        const icons = {
            success: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 11.08V12a10 10 0 11-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>',
            error: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>',
            warning: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>',
            info: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>',
        };

        const toast = document.createElement("div");
        toast.className = `toast toast-${type}`;
        toast.innerHTML = `${icons[type] || icons.info}<span>${escapeHtml(message)}</span>`;
        container.appendChild(toast);

        setTimeout(() => {
            toast.classList.add("toast-out");
            toast.addEventListener("animationend", () => toast.remove());
        }, 4000);
    }

    /* ===== Tab Navigation ===== */
    function switchTab(tabId) {
        currentTab = tabId;
        $$(".nav-tab").forEach(btn => {
            const isActive = btn.dataset.tab === tabId;
            btn.classList.toggle("active", isActive);
            btn.setAttribute("aria-selected", isActive);
        });
        $$(".tab-content").forEach(sec => {
            sec.classList.toggle("hidden", sec.id !== `tab-${tabId}`);
            if (sec.id === `tab-${tabId}`) sec.classList.add("active");
        });
    }

    /* ===== Certificate Type Selection ===== */
    function selectCertType(type) {
        certType = type;
        $$(".cert-type-card").forEach(card => {
            card.classList.toggle("active", card.dataset.type === type);
        });

        const sanSection = $("#san-section");
        const cnHint = $("#cn-hint");
        const cnInput = $("#field-cn");

        if (type === "san") {
            sanSection.classList.remove("hidden");
            cnHint.textContent = "Haupt-Domain (wird automatisch als SAN hinzugefügt)";
            cnInput.placeholder = "www.example.com";
            if ($$("#san-list .san-entry").length === 0) addSanEntry();
        } else {
            sanSection.classList.add("hidden");
            if (type === "wildcard") {
                cnHint.textContent = 'Wildcard-Domain, z.B. *.example.com';
                cnInput.placeholder = "*.example.com";
            } else {
                cnHint.textContent = "Der vollständige Domainname, z.B. www.example.com";
                cnInput.placeholder = "www.example.com";
            }
        }
    }

    /* ===== SAN Management ===== */
    function addSanEntry(value = "") {
        const list = $("#san-list");
        const entry = document.createElement("div");
        entry.className = "san-entry";
        entry.innerHTML = `
            <input type="text" placeholder="mail.example.com" value="${escapeHtml(value)}">
            <button type="button" class="san-remove" title="Entfernen" aria-label="SAN entfernen">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
            </button>
        `;
        entry.querySelector(".san-remove").addEventListener("click", () => {
            entry.remove();
        });
        list.appendChild(entry);
        entry.querySelector("input").focus();
    }

    function getSanNames() {
        return $$("#san-list .san-entry input")
            .map(inp => inp.value.trim())
            .filter(Boolean);
    }

    /* ===== CSR Generation ===== */
    async function generateCSR(event) {
        event.preventDefault();

        const btn = $("#generate-btn");
        const form = $("#csr-form");

        const cn = $("#field-cn").value.trim();
        if (!cn) {
            showToast("Bitte geben Sie einen Common Name (CN) ein.", "warning");
            $("#field-cn").focus();
            return;
        }

        const countryVal = $("#field-c").value.trim().toUpperCase();
        if (countryVal && countryVal.length !== 2) {
            showToast("Der Ländercode muss genau 2 Zeichen lang sein.", "warning");
            $("#field-c").focus();
            return;
        }

        const payload = {
            cn,
            o: $("#field-o").value.trim(),
            ou: $("#field-ou").value.trim(),
            c: countryVal,
            st: $("#field-st").value.trim(),
            l: $("#field-l").value.trim(),
            email: $("#field-email").value.trim(),
            key_size: parseInt($('input[name="key_size"]:checked').value),
            cert_type: certType,
            san_names: certType === "san" ? getSanNames() : [],
        };

        btn.classList.add("loading");
        btn.disabled = true;

        try {
            const res = await fetch("/api/generate", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload),
            });
            const data = await res.json();

            if (!res.ok) {
                showToast(data.error || "Fehler bei der Generierung.", "error");
                return;
            }

            generatedCSR = data.csr;
            generatedKey = data.key;
            generatedCN = data.cn || cn;

            displayResults(data);
            showToast("CSR und Schlüssel erfolgreich erstellt!", "success");
        } catch (err) {
            showToast("Verbindungsfehler. Bitte versuchen Sie es erneut.", "error");
        } finally {
            btn.classList.remove("loading");
            btn.disabled = false;
        }
    }

    function displayResults(data) {
        const section = $("#results-section");
        section.classList.remove("hidden");

        $("#csr-output").textContent = data.csr;

        $("#key-output").textContent = data.key;
        $("#key-output-wrap").classList.add("hidden");
        $("#show-key-toggle").checked = false;

        const tbody = $("#csr-details-table tbody");
        tbody.innerHTML = "";

        if (data.details) {
            const d = data.details;
            if (d.subject) {
                Object.entries(d.subject).forEach(([k, v]) => {
                    addDetailRow(tbody, k, v);
                });
            }
            if (d.sans && d.sans.length) {
                const sanHtml = d.sans.map(s => `<span class="san-tag">${escapeHtml(s)}</span>`).join(" ");
                addDetailRow(tbody, "SANs", sanHtml, true);
            }
            if (d.key_size) addDetailRow(tbody, "Schlüssellänge", `${d.key_size} Bit`);
            if (d.signature_algorithm) addDetailRow(tbody, "Signatur-Algorithmus", d.signature_algorithm);
            if (d.is_valid !== undefined) {
                addDetailRow(tbody, "Signatur gültig", d.is_valid
                    ? '<span class="status-valid">Ja</span>'
                    : '<span class="status-expired">Nein</span>', true);
            }
        }

        section.scrollIntoView({ behavior: "smooth", block: "start" });
    }

    function resetGeneratorState() {
        generatedCSR = "";
        generatedKey = "";
        generatedCN = "";

        const form = $("#csr-form");
        form.reset();

        $("#field-c").value = "";
        $("#san-list").innerHTML = "";
        $("#results-section").classList.add("hidden");
        $("#csr-output").textContent = "";
        $("#key-output").textContent = "";
        $("#key-output-wrap").classList.add("hidden");
        $("#show-key-toggle").checked = false;
        $("#csr-details-table tbody").innerHTML = "";

        selectCertType("standard");
        $("#field-cn").focus();
        showToast("Alles wurde auf Standard zurückgesetzt.", "info");
    }

    /* ===== P12 Conversion ===== */
    async function convertP12(event) {
        event.preventDefault();

        const keyFile = $("#p12-key-file").files[0];
        const certFile = $("#p12-cert-file").files[0];
        const chainFile = $("#p12-chain-file").files[0];
        const targetFormat = $("#target-format").value;
        const password = $("#p12-password").value;
        const keyPassword = $("#p12-key-password").value;

        if (!certFile) {
            showToast("Bitte wählen Sie eine Zertifikatsdatei aus.", "warning");
            return;
        }
        if ((targetFormat === "pfx" || targetFormat === "p12") && !keyFile) {
            showToast("Für PFX/P12 wird eine Schlüsseldatei benötigt.", "warning");
            return;
        }

        const btn = $("#convert-p12-btn");
        btn.classList.add("loading");
        btn.disabled = true;

        try {
            const formData = new FormData();
            formData.append("cert", certFile);
            if (keyFile) formData.append("key", keyFile);
            if (chainFile) formData.append("chain", chainFile);
            formData.append("target_format", targetFormat);
            formData.append("password", password);
            formData.append("key_password", keyPassword);

            const res = await fetch("/api/convert-p12", {
                method: "POST",
                body: formData,
            });

            if (!res.ok) {
                const errData = await res.json().catch(() => ({}));
                showToast(errData.error || "Konvertierungsfehler.", "error");
                return;
            }

            const blob = await res.blob();
            const disposition = res.headers.get("content-disposition") || "";
            const match = disposition.match(/filename="?(.+?)"?$/);
            const filename = match ? match[1] : "certificate.p12";

            downloadBlob(blob, filename);
            showToast(`${filename} erfolgreich erstellt!`, "success");
        } catch (err) {
            showToast("Verbindungsfehler. Bitte versuchen Sie es erneut.", "error");
        } finally {
            btn.classList.remove("loading");
            btn.disabled = false;
        }
    }

    /* ===== Inspect ===== */
    async function inspectPEM() {
        const pem = $("#inspect-pem").value.trim();
        if (!pem) {
            showToast("Bitte fügen Sie einen CSR oder ein Zertifikat ein.", "warning");
            $("#inspect-pem").focus();
            return;
        }

        const btn = $("#inspect-btn");
        btn.classList.add("loading");
        btn.disabled = true;

        try {
            const res = await fetch("/api/inspect", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ pem }),
            });
            const data = await res.json();

            if (!res.ok) {
                showToast(data.error || "Fehler beim Prüfen.", "error");
                return;
            }

            displayInspectResults(data);
        } catch (err) {
            showToast("Verbindungsfehler.", "error");
        } finally {
            btn.classList.remove("loading");
            btn.disabled = false;
        }
    }

    function displayInspectResults(data) {
        const container = $("#inspect-results");
        container.classList.remove("hidden");

        const title = $("#inspect-result-title");
        const badge = $("#inspect-result-badge");
        const tbody = $("#inspect-details-table tbody");
        tbody.innerHTML = "";

        if (data.type === "csr") {
            title.textContent = "Certificate Signing Request (CSR)";
            badge.textContent = "CSR";
            badge.className = "badge badge-info";

            const d = data.details;
            if (d.subject) {
                Object.entries(d.subject).forEach(([k, v]) => addDetailRow(tbody, k, v));
            }
            if (d.sans && d.sans.length) {
                const sanHtml = d.sans.map(s => `<span class="san-tag">${escapeHtml(s)}</span>`).join(" ");
                addDetailRow(tbody, "SANs", sanHtml, true);
            }
            if (d.key_size) addDetailRow(tbody, "Schlüssellänge", `${d.key_size} Bit`);
            if (d.signature_algorithm) addDetailRow(tbody, "Signatur-Algorithmus", d.signature_algorithm);
            if (d.is_valid !== undefined) {
                addDetailRow(tbody, "Signatur gültig", d.is_valid
                    ? '<span class="status-valid">Ja</span>'
                    : '<span class="status-expired">Nein</span>', true);
            }
        } else if (data.type === "certificate") {
            title.textContent = "Zertifikat";
            const d = data.details;
            const isExpired = d.is_expired;
            badge.textContent = isExpired ? "Abgelaufen" : "Gültig";
            badge.className = isExpired ? "badge badge-error" : "badge badge-success";

            if (d.subject) {
                Object.entries(d.subject).forEach(([k, v]) => addDetailRow(tbody, k, `${v}`));
            }
            if (d.issuer) {
                const issuerStr = Object.entries(d.issuer).map(([k, v]) => `${k}: ${v}`).join(", ");
                addDetailRow(tbody, "Aussteller", issuerStr);
            }
            if (d.sans && d.sans.length) {
                const sanHtml = d.sans.map(s => `<span class="san-tag">${escapeHtml(s)}</span>`).join(" ");
                addDetailRow(tbody, "SANs", sanHtml, true);
            }
            if (d.serial) addDetailRow(tbody, "Seriennummer", d.serial);
            if (d.not_before) addDetailRow(tbody, "Gültig ab", d.not_before);
            if (d.not_after) {
                const cls = isExpired ? "status-expired" : "status-valid";
                addDetailRow(tbody, "Gültig bis", `<span class="${cls}">${escapeHtml(d.not_after)}</span>`, true);
            }
            if (d.key_size) addDetailRow(tbody, "Schlüssellänge", `${d.key_size} Bit`);
            if (d.signature_algorithm) addDetailRow(tbody, "Signatur-Algorithmus", d.signature_algorithm);
        }

        container.scrollIntoView({ behavior: "smooth", block: "start" });
    }

    /* ===== Download Helpers ===== */
    function downloadBlob(blob, filename) {
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    }

    function downloadText(text, filename, mimeType = "application/x-pem-file") {
        const blob = new Blob([text], { type: mimeType });
        downloadBlob(blob, filename);
    }

    function copyToClipboard(text) {
        navigator.clipboard.writeText(text).then(
            () => showToast("In die Zwischenablage kopiert!", "success"),
            () => showToast("Kopieren fehlgeschlagen.", "error")
        );
    }

    /* ===== Upload Zone Helpers ===== */
    function setupUploadZone(zoneId, inputId, fileNameId) {
        const zone = $(`#${zoneId}`);
        const input = $(`#${inputId}`);
        const nameEl = $(`#${fileNameId}`);

        ["dragover", "dragenter"].forEach(evt => {
            zone.addEventListener(evt, e => {
                e.preventDefault();
                zone.classList.add("drag-over");
            });
        });

        ["dragleave", "drop"].forEach(evt => {
            zone.addEventListener(evt, e => {
                e.preventDefault();
                zone.classList.remove("drag-over");
            });
        });

        zone.addEventListener("drop", e => {
            if (e.dataTransfer.files.length) {
                input.files = e.dataTransfer.files;
                updateFileName(input, nameEl, zone);
            }
        });

        input.addEventListener("change", () => {
            updateFileName(input, nameEl, zone);
        });
    }

    function updateFileName(input, nameEl, zone) {
        if (input.files.length) {
            nameEl.textContent = input.files[0].name;
            nameEl.classList.remove("hidden");
            zone.classList.add("has-file");
        } else {
            nameEl.classList.add("hidden");
            zone.classList.remove("has-file");
        }
    }

    function setupInspectUploadZone() {
        const zone = $("#inspect-upload-zone");
        const input = $("#inspect-pem-file");
        const fileName = $("#inspect-file-name");
        const textArea = $("#inspect-pem");

        const loadFile = file => {
            if (!file) return;
            const reader = new FileReader();
            reader.onload = () => {
                textArea.value = String(reader.result || "").trim();
                fileName.textContent = file.name;
                fileName.classList.remove("hidden");
                zone.classList.add("has-file");
                showToast("Datei geladen. Jetzt auf \"Prüfen\" klicken.", "success");
            };
            reader.onerror = () => {
                showToast("Datei konnte nicht gelesen werden.", "error");
            };
            reader.readAsText(file);
        };

        ["dragover", "dragenter"].forEach(evt => {
            zone.addEventListener(evt, e => {
                e.preventDefault();
                zone.classList.add("drag-over");
            });
        });

        ["dragleave", "drop"].forEach(evt => {
            zone.addEventListener(evt, e => {
                e.preventDefault();
                zone.classList.remove("drag-over");
            });
        });

        zone.addEventListener("drop", e => {
            const file = e.dataTransfer?.files?.[0];
            if (file) {
                const dt = new DataTransfer();
                dt.items.add(file);
                input.files = dt.files;
                loadFile(file);
            }
        });

        input.addEventListener("change", () => {
            loadFile(input.files[0]);
        });
    }

    /* ===== Helpers ===== */
    function addDetailRow(tbody, label, value, isHtml = false) {
        const tr = document.createElement("tr");
        tr.innerHTML = `<th>${escapeHtml(label)}</th><td>${isHtml ? value : escapeHtml(String(value))}</td>`;
        tbody.appendChild(tr);
    }

    function escapeHtml(str) {
        const div = document.createElement("div");
        div.textContent = str;
        return div.innerHTML;
    }

    function sanitizeFilename(cn) {
        return cn.replace(/[^a-zA-Z0-9._-]/g, "_").replace(/^\.+/, "") || "certificate";
    }

    /* ===== Init ===== */
    function init() {
        initTheme();

        /* Theme toggle */
        $("#theme-toggle").addEventListener("click", toggleTheme);

        /* Tab navigation */
        $$(".nav-tab").forEach(btn => {
            btn.addEventListener("click", () => switchTab(btn.dataset.tab));
        });

        /* Cert type selection */
        $$(".cert-type-card").forEach(card => {
            card.addEventListener("click", () => selectCertType(card.dataset.type));
        });

        /* Add SAN button */
        $("#add-san-btn").addEventListener("click", () => addSanEntry());

        /* CSR form submit */
        $("#csr-form").addEventListener("submit", generateCSR);

        /* Copy CSR */
        $("#copy-csr-btn").addEventListener("click", () => {
            if (generatedCSR) copyToClipboard(generatedCSR);
        });

        /* Download CSR */
        $("#download-csr-btn").addEventListener("click", () => {
            if (generatedCSR) {
                const name = sanitizeFilename(generatedCN);
                downloadText(generatedCSR, `${name}.csr`);
            }
        });

        /* Download KEY */
        $("#download-key-btn").addEventListener("click", () => {
            if (generatedKey) {
                const name = sanitizeFilename(generatedCN);
                downloadText(generatedKey, `${name}.key`);
            }
        });

        /* Reset generator */
        $("#reset-csr-btn").addEventListener("click", resetGeneratorState);

        /* Show/Hide key */
        $("#show-key-toggle").addEventListener("change", function () {
            const wrap = $("#key-output-wrap");
            wrap.classList.toggle("hidden", !this.checked);
        });

        /* P12 form */
        setupUploadZone("key-upload-zone", "p12-key-file", "key-file-name");
        setupUploadZone("cert-upload-zone", "p12-cert-file", "cert-file-name");
        setupUploadZone("chain-upload-zone", "p12-chain-file", "chain-file-name");
        $("#p12-form").addEventListener("submit", convertP12);

        /* P12 password toggle */
        $("#p12-pw-toggle").addEventListener("click", function () {
            const input = $("#p12-password");
            const isPassword = input.type === "password";
            input.type = isPassword ? "text" : "password";
            this.classList.toggle("active", isPassword);
            this.title = isPassword ? "Passwort verbergen" : "Passwort anzeigen";
        });
        $("#p12-key-pw-toggle").addEventListener("click", function () {
            const input = $("#p12-key-password");
            const isPassword = input.type === "password";
            input.type = isPassword ? "text" : "password";
            this.classList.toggle("active", isPassword);
            this.title = isPassword ? "Passwort verbergen" : "Passwort anzeigen";
        });

        /* Inspect */
        setupInspectUploadZone();
        $("#inspect-btn").addEventListener("click", inspectPEM);
        $("#inspect-clear-btn").addEventListener("click", () => {
            $("#inspect-pem").value = "";
            $("#inspect-results").classList.add("hidden");
            $("#inspect-pem-file").value = "";
            $("#inspect-file-name").classList.add("hidden");
            $("#inspect-upload-zone").classList.remove("has-file");
        });
    }

    document.addEventListener("DOMContentLoaded", init);
})();
