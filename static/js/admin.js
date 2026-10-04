/* ══════════════════════════════════════════
   TAB SİSTEMİ — data-tab attribute bazlı
   inline onclick YOK → CSP uyumlu
══════════════════════════════════════════ */
function switchTab(name) {
    document.querySelectorAll('.tab-panel').forEach(function(p){
        p.classList.remove('active');
    });
    document.querySelectorAll('.sidebar-nav-item').forEach(function(b){
        b.classList.remove('active');
    });
    var panel = document.getElementById('tab-' + name);
    if (panel) panel.classList.add('active');
    var activeBtn = document.querySelector('.sidebar-nav-item[data-tab="' + name + '"]');
    if (activeBtn) activeBtn.classList.add('active');
}

/* ══════════════════════════════════════════════════════════════════
   ÖZEL MODAL SİSTEMİ — tarayıcı confirm/alert yerine
   ──────────────────────────────────────────────────────────────
   sysConfirm(opts)  → Promise<boolean>  (Tamam=true, Vazgeç=false)
   sysAlert(opts)    → Promise<void>     (sadece Tamam butonu)
══════════════════════════════════════════════════════════════════ */
var _sysModalEl, _sysIconEl, _sysTitleEl, _sysBodyEl, _sysCancelBtn, _sysConfirmBtn, _sysActionsEl;
var _sysResolve = null;

function _initSysModal() {
    _sysModalEl   = document.getElementById('sysModal');
    _sysIconEl    = document.getElementById('sysModalIcon');
    _sysTitleEl   = document.getElementById('sysModalTitle');
    _sysBodyEl    = document.getElementById('sysModalBody');
    _sysCancelBtn = document.getElementById('sysModalCancel');
    _sysConfirmBtn= document.getElementById('sysModalConfirm');
    _sysActionsEl = _sysConfirmBtn.parentElement;

    /* Vazgeç */
    _sysCancelBtn.addEventListener('click', function() { _closeSysModal(false); });
    /* Tamam */
    _sysConfirmBtn.addEventListener('click', function() { _closeSysModal(true); });
    /* Overlay tıklama */
    _sysModalEl.addEventListener('click', function(e) {
        if (e.target === _sysModalEl) _closeSysModal(false);
    });
    /* ESC tuşu */
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape' && _sysModalEl.classList.contains('open')) _closeSysModal(false);
    });
}

function _closeSysModal(result) {
    _sysModalEl.classList.remove('open');
    document.body.style.overflow = '';
    if (_sysResolve) { _sysResolve(result); _sysResolve = null; }
}

/**
 * Özel onay modalı göster
 * @param {Object} opts
 * @param {string} opts.title        — Modal başlığı (varsayılan: "Onay")
 * @param {string} opts.body         — Mesaj metni
 * @param {string} opts.icon         — İkon tipi: confirm|warning|danger|info|success
 * @param {string} opts.iconClass    — FontAwesome ikon sınıfı (varsayılan: fa-question-circle)
 * @param {string} opts.confirmText  — Onay butonu metni (varsayılan: "Tamam")
 * @param {string} opts.cancelText   — İptal butonu metni (varsayılan: "Vazgeç")
 * @param {string} opts.confirmStyle — Buton stili: ''|'btn-danger'|'btn-warning'
 * @returns {Promise<boolean>}
 */
function sysConfirm(opts) {
    opts = opts || {};
    _sysTitleEl.textContent = opts.title || 'Onay';
    _sysBodyEl.textContent  = opts.body  || 'Devam etmek istiyor musunuz?';

    var iconType = opts.icon || 'confirm';
    _sysIconEl.className = 'sys-modal-icon icon-' + iconType;
    _sysIconEl.innerHTML = '<i class="fas ' + (opts.iconClass || 'fa-question-circle') + '"></i>';

    _sysConfirmBtn.textContent = opts.confirmText || 'Tamam';
    _sysCancelBtn.textContent  = opts.cancelText  || 'Vazgeç';

    _sysConfirmBtn.className = 'sys-modal-btn sys-btn-confirm';
    if (opts.confirmStyle) _sysConfirmBtn.classList.add(opts.confirmStyle);

    _sysActionsEl.classList.remove('single-btn');
    _sysModalEl.classList.add('open');
    document.body.style.overflow = 'hidden';

    /* Tamam butonuna odaklan */
    _sysConfirmBtn.focus();

    return new Promise(function(resolve) { _sysResolve = resolve; });
}

/**
 * Özel bilgilendirme/uyarı modalı (tek buton)
 * @param {Object} opts — sysConfirm ile aynı, cancelText yok
 * @returns {Promise<void>}
 */
function sysAlert(opts) {
    opts = opts || {};
    _sysTitleEl.textContent = opts.title || 'Bilgi';
    _sysBodyEl.textContent  = opts.body  || '';

    var iconType = opts.icon || 'info';
    _sysIconEl.className = 'sys-modal-icon icon-' + iconType;
    _sysIconEl.innerHTML = '<i class="fas ' + (opts.iconClass || 'fa-info-circle') + '"></i>';

    _sysConfirmBtn.textContent = opts.confirmText || 'Tamam';
    _sysConfirmBtn.className = 'sys-modal-btn sys-btn-confirm';
    if (opts.confirmStyle) _sysConfirmBtn.classList.add(opts.confirmStyle);

    _sysActionsEl.classList.add('single-btn');
    _sysModalEl.classList.add('open');
    document.body.style.overflow = 'hidden';

    _sysConfirmBtn.focus();

    return new Promise(function(resolve) {
        _sysResolve = function() { resolve(); };
    });
}

/* ══════════════════════════════════════════
   BUTON LOADING STATE
   setButtonLoading(btn, text) → eski içeriği döner
   clearButtonLoading(btn, oldHTML)
══════════════════════════════════════════ */
function setButtonLoading(btn, loadingText) {
    if (!btn) return '';
    var oldHTML = btn.innerHTML;
    btn.classList.add('btn-loading');
    btn.disabled = true;
    btn.innerHTML = '<span class="btn-spinner"></span> ' + (loadingText || 'İşleniyor...');
    return oldHTML;
}

/* ══════════════════════════════════════════
   FORM ONAY DİYALOĞU — data-msg bazlı
   → Özel modal ile, loading state ile
══════════════════════════════════════════ */
function bindConfirmForms() {
    document.querySelectorAll('.confirm-form').forEach(function(form) {
        form.addEventListener('submit', function(e) {
            e.preventDefault();
            var msg         = form.dataset.msg || 'Devam etmek istiyor musunuz?';
            var submitBtn   = form.querySelector('button[type="submit"]');
            var loadingText = submitBtn ? (submitBtn.dataset.loadingText || 'İşleniyor...') : 'İşleniyor...';

            /* İkon ve stil: reddet formları için danger, diğerleri için confirm */
            var isReject = form.action && form.action.indexOf('/reject') !== -1;
            var isDelete = form.action && form.action.indexOf('/delete') !== -1;
            var isDanger = isReject || isDelete;

            sysConfirm({
                title: isDanger ? 'Dikkat' : 'Onay',
                body: msg.replace(/&#10;/g, '\n'),
                icon: isDanger ? 'danger' : 'confirm',
                iconClass: isDanger ? 'fa-exclamation-triangle' : 'fa-question-circle',
                confirmText: isDelete ? 'Evet, Sil' : (isReject ? 'Evet, Reddet' : 'Evet, Onayla'),
                confirmStyle: isDanger ? 'btn-danger' : ''
            }).then(function(ok) {
                if (ok) {
                    setButtonLoading(submitBtn, loadingText);
                    form.submit();
                }
            });
        });
    });
}

/* ══════════════════════════════════════════
   REZERVASYON FİLTRESİ — data-filter bazlı
══════════════════════════════════════════ */
function bindFilterBtns() {
    document.querySelectorAll('.filter-btn').forEach(function(btn) {
        btn.addEventListener('click', function() {
            var status = btn.dataset.filter;
            document.querySelectorAll('.filter-btn').forEach(function(b){ b.classList.remove('active'); });
            btn.classList.add('active');
            document.querySelectorAll('.res-card').forEach(function(card){
                card.style.display = (status === 'all' || card.dataset.status === status) ? '' : 'none';
            });
        });
    });
}

/* ══════════════════════════════════════════
   OTURUM GERİ SAYIMI
══════════════════════════════════════════ */
function initSessionTimer() {
    var TOTAL = 30 * 60, remaining = TOTAL;
    var valEl  = document.getElementById('sessionTimerVal');
    var fillEl = document.getElementById('sessionProgressFill');
    var warnEl = document.getElementById('sessionWarnMsg');
    function tick() {
        remaining--;
        if (remaining <= 0) {
            sysAlert({
                title: 'Oturum Süresi Doldu',
                body: 'Oturumunuzun süresi doldu. Giriş sayfasına yönlendirileceksiniz.',
                icon: 'warning',
                iconClass: 'fa-clock',
                confirmText: 'Tamam'
            }).then(function() {
                window.location.href = '/logout';
            });
            return;
        }
        var m = Math.floor(remaining / 60), s = remaining % 60;
        valEl.textContent  = String(m).padStart(2,'0') + ':' + String(s).padStart(2,'0');
        fillEl.style.width = ((remaining / TOTAL) * 100) + '%';
        if      (remaining <= 120) { fillEl.style.background = '#f87171'; warnEl.style.display = 'inline'; valEl.style.color = '#f87171'; }
        else if (remaining <= 300) { fillEl.style.background = '#fbbf24'; }
        setTimeout(tick, 1000);
    }
    setTimeout(tick, 1000);
}

/* ══════════════════════════════════════════
   KİLİTLEME FORMU
══════════════════════════════════════════ */
var selPitches = [], selDates = [], selSlots = [];

function bindPickItems() {
    document.querySelectorAll('.multi-pick-item[data-pick-type]').forEach(function(el) {
        el.addEventListener('click', function() { togglePick(el); });
    });
}

function togglePick(el) {
    var val  = el.dataset.val;
    var type = el.dataset.pickType;
    var arr  = type === 'pitch' ? selPitches : selSlots;
    var idx  = arr.indexOf(val);
    if (idx === -1) { arr.push(val);    el.classList.add('selected'); }
    else            { arr.splice(idx,1); el.classList.remove('selected'); }
    // Saha seçimi değiştiğinde slot listesini güncelle
    if (type === 'pitch') { loadSlotsForSelectedPitches(); }
    updateSummary();
}

/* Seçili sahaların ortak saat dilimlerini yükle */
function loadSlotsForSelectedPitches() {
    var picker = document.getElementById('slotPicker');
    var emptyEl = document.getElementById('slotPickerEmpty');
    selSlots = []; // seçili slotları sıfırla

    if (selPitches.length === 0) {
        picker.innerHTML = '<div id="slotPickerEmpty" style="padding:12px;color:var(--gray-400);font-size:0.85rem;">Önce bir saha seçin.</div>';
        updateSummary();
        return;
    }

    picker.innerHTML = '<div style="padding:12px;color:var(--gray-400);font-size:0.85rem;">Yükleniyor...</div>';

    // Tüm seçili sahaların slotlarını çek, sonra ortak olanları göster
    var promises = selPitches.map(function(pid) {
        return fetch('/admin/api/pitch/' + pid + '/time_slots')
            .then(function(r) { return r.ok ? r.json() : { slots: [] }; })
            .then(function(d) { return d.slots.map(function(s) { return s.label; }); });
    });

    Promise.all(promises).then(function(results) {
        // Tüm seçili sahaların ortak slotlarını bul
        var commonSlots;
        if (results.length === 1) {
            commonSlots = results[0];
        } else {
            commonSlots = results[0].filter(function(slot) {
                return results.every(function(r) { return r.indexOf(slot) !== -1; });
            });
        }

        picker.innerHTML = '';
        if (commonSlots.length === 0) {
            picker.innerHTML = '<div style="padding:12px;color:var(--gray-400);font-size:0.85rem;">Seçili sahalar için ortak saat dilimi bulunamadı.</div>';
            updateSummary();
            return;
        }

        commonSlots.forEach(function(slotLabel) {
            var div = document.createElement('div');
            div.className = 'multi-pick-item';
            div.dataset.val = slotLabel;
            div.dataset.pickType = 'slot';
            div.innerHTML = '<i class="fas fa-clock"></i> ' + slotLabel + ' <i class="fas fa-check pick-check"></i>';
            div.addEventListener('click', function() { togglePick(div); });
            picker.appendChild(div);
        });
        updateSummary();
    }).catch(function() {
        picker.innerHTML = '<div style="padding:12px;color:#ef4444;font-size:0.85rem;">Slotlar yüklenirken hata oluştu.</div>';
    });
}

/* TAKVİM */
var calYear, calMonth;
var MONTHS_TR = ['Ocak','Şubat','Mart','Nisan','Mayıs','Haziran','Temmuz','Ağustos','Eylül','Ekim','Kasım','Aralık'];
var DAYS_TR   = ['Pt','Sa','Ca','Pe','Cu','Ct','Pz'];

function initCal() {
    var now = new Date();
    calYear = now.getFullYear(); calMonth = now.getMonth();
    renderCal();
    document.getElementById('calPrev').addEventListener('click', function(){
        calMonth--; if(calMonth < 0){ calMonth = 11; calYear--; } renderCal();
    });
    document.getElementById('calNext').addEventListener('click', function(){
        calMonth++; if(calMonth > 11){ calMonth = 0; calYear++; } renderCal();
    });
}

function renderCal() {
    document.getElementById('calMonthLabel').textContent = MONTHS_TR[calMonth] + ' ' + calYear;
    var grid = document.getElementById('calGrid');
    grid.innerHTML = '';
    DAYS_TR.forEach(function(d){
        var el = document.createElement('div'); el.className = 'cal-day-name'; el.textContent = d; grid.appendChild(el);
    });
    var firstDay   = new Date(calYear, calMonth, 1);
    var startOffset = (firstDay.getDay() + 6) % 7;
    var daysInMonth = new Date(calYear, calMonth+1, 0).getDate();
    var today = new Date(); today.setHours(0,0,0,0);
    for (var i = 0; i < startOffset; i++) {
        var emp = document.createElement('div'); emp.className = 'cal-day cal-empty'; grid.appendChild(emp);
    }
    for (var d = 1; d <= daysInMonth; d++) {
        var dayEl   = document.createElement('div');
        var dayDate = new Date(calYear, calMonth, d);
        var dateStr = calYear + '-' + String(calMonth+1).padStart(2,'0') + '-' + String(d).padStart(2,'0');
        dayEl.className = 'cal-day'; dayEl.textContent = d; dayEl.dataset.date = dateStr;
        if (dayDate < today) {
            dayEl.classList.add('cal-disabled');
        } else {
            if (dayDate.toDateString() === today.toDateString()) dayEl.classList.add('cal-today');
            if (selDates.indexOf(dateStr) !== -1) dayEl.classList.add('cal-selected');
            (function(el, ds){ el.addEventListener('click', function(){ toggleDate(el, ds); }); })(dayEl, dateStr);
        }
        grid.appendChild(dayEl);
    }
    renderDateTags();
}

function toggleDate(el, dateStr) {
    var idx = selDates.indexOf(dateStr);
    if (idx === -1) { selDates.push(dateStr);    el.classList.add('cal-selected'); }
    else            { selDates.splice(idx, 1);   el.classList.remove('cal-selected'); }
    renderDateTags(); updateSummary();
}

function removeDate(dateStr) {
    var idx = selDates.indexOf(dateStr);
    if (idx !== -1) selDates.splice(idx, 1);
    document.querySelectorAll('.cal-day[data-date="'+dateStr+'"]').forEach(function(c){ c.classList.remove('cal-selected'); });
    renderDateTags(); updateSummary();
}

function renderDateTags() {
    var container = document.getElementById('calSelectedTags');
    container.innerHTML = '';
    if (selDates.length === 0) {
        var hint = document.createElement('div'); hint.className = 'cal-no-selection'; hint.textContent = 'Tarih seçilmedi';
        container.appendChild(hint); return;
    }
    selDates.slice().sort().forEach(function(ds){
        var parts = ds.split('-');
        var tag   = document.createElement('div'); tag.className = 'cal-tag';
        tag.textContent = parts[2]+'.'+parts[1]+'.'+parts[0]+' ';
        var icon = document.createElement('i'); icon.className = 'fas fa-times';
        tag.appendChild(icon);
        (function(d){ tag.addEventListener('click', function(){ removeDate(d); }); })(ds);
        container.appendChild(tag);
    });
}

function updateSummary() {
    var sumEl  = document.getElementById('blockSummary');
    var sumTxt = document.getElementById('blockSummaryText');
    var total  = selPitches.length * selDates.length * selSlots.length;
    if (total > 0) {
        sumEl.style.display = 'flex';
        sumTxt.textContent  = selPitches.length+' saha × '+selDates.length+' tarih × '+selSlots.length+' saat = '+total+' slot kilitlenecek';
    } else {
        sumEl.style.display = 'none';
    }
}

function submitBlock() {
    if (selPitches.length === 0) {
        sysAlert({ title: 'Eksik Seçim', body: 'En az 1 saha seçin!', icon: 'warning', iconClass: 'fa-exclamation-circle' });
        return;
    }
    if (selDates.length === 0) {
        sysAlert({ title: 'Eksik Seçim', body: 'En az 1 tarih seçin!', icon: 'warning', iconClass: 'fa-exclamation-circle' });
        return;
    }
    if (selSlots.length === 0) {
        sysAlert({ title: 'Eksik Seçim', body: 'En az 1 saat dilimi seçin!', icon: 'warning', iconClass: 'fa-exclamation-circle' });
        return;
    }
    var total = selPitches.length * selDates.length * selSlots.length;
    sysConfirm({
        title: 'Slot Kilitleme',
        body: total + ' slot kilitlenecek.\nDevam etmek istiyor musunuz?',
        icon: 'warning',
        iconClass: 'fa-lock',
        confirmText: 'Kilitle',
        confirmStyle: 'btn-warning'
    }).then(function(ok) {
        if (!ok) return;
        var container = document.getElementById('blockHiddenInputs');
        container.innerHTML = '';
        function addInput(name, val) {
            var inp = document.createElement('input'); inp.type='hidden'; inp.name=name; inp.value=val; container.appendChild(inp);
        }
        selPitches.forEach(function(p){ addInput('pitch_ids', p); });
        selDates.forEach(function(d){   addInput('dates', d); });
        selSlots.forEach(function(s){   addInput('time_slots', s); });
        /* Loading state */
        var btn = document.getElementById('btnSubmitBlock');
        setButtonLoading(btn, 'Kilitleniyor...');
        document.getElementById('blockForm').submit();
    });
}

/* Karakter sayacı */
function bindCharCounter() {
    var ta = document.getElementById('bReason');
    var counter = document.getElementById('charCount');
    if (ta && counter) {
        ta.addEventListener('input', function(){ counter.textContent = ta.value.length; });
    }
}

/* Çıkış onayı → özel modal */
function bindLogout() {
    var btn = document.getElementById('logoutBtn');
    if (btn) {
        btn.addEventListener('click', function(e) {
            e.preventDefault();
            sysConfirm({
                title: 'Çıkış',
                body: 'Oturumu kapatmak istiyor musunuz?',
                icon: 'warning',
                iconClass: 'fa-sign-out-alt',
                confirmText: 'Çıkış Yap',
                confirmStyle: 'btn-danger'
            }).then(function(ok) {
                if (ok) window.location.href = btn.href || '/logout';
            });
        });
    }
}

/* ══════════════════════════════════════════════════════════════════
   ŞİFRE DEĞİŞTİR MODAL — CANLI POLİTİKA DOĞRULAMASI
   ──────────────────────────────────────────────────────────────
   Submit butonu ancak TÜM şifre politikası kuralları sağlanıp
   şifreler eşleştiğinde aktif olur.
   Zayıf şifre ile form ASLA gönderilemez.
══════════════════════════════════════════════════════════════════ */
function bindPasswordModal() {
    var modal        = document.getElementById('pwModal');
    var btnOpen      = document.getElementById('btnChangePw');
    var btnClose     = document.getElementById('btnClosePwModal');
    var btnCancel    = document.getElementById('btnCancelPw');
    var newPwInput   = document.getElementById('newPwInput');
    var confirmInput = document.getElementById('confirmPwInput');
    var submitBtn    = document.getElementById('btnPwSubmit');
    var matchMsg     = document.getElementById('pwMatchMsg');
    var strengthFill = document.getElementById('pwStrengthFill');
    var strengthText = document.getElementById('pwStrengthText');

    /* Canlı politika kontrol elemanları */
    var chkLen     = document.getElementById('chkLen');
    var chkUpper   = document.getElementById('chkUpper');
    var chkLower   = document.getElementById('chkLower');
    var chkDigit   = document.getElementById('chkDigit');
    var chkSpecial = document.getElementById('chkSpecial');

    if (!modal) return;

    function openModal()  {
        modal.classList.add('open');
        document.body.style.overflow = 'hidden'; /* arka plan scroll'u engelle */
    }
    function closeModal() {
        modal.classList.remove('open');
        document.body.style.overflow = '';
        document.getElementById('pwForm').reset();
        strengthFill.style.width     = '0';
        strengthFill.style.background = '';
        strengthText.textContent     = '';
        matchMsg.style.display       = 'none';
        submitBtn.disabled           = true;
        /* Kontrol listesini sıfırla */
        [chkLen, chkUpper, chkLower, chkDigit, chkSpecial].forEach(function(el) {
            if (el) { el.className = ''; el.querySelector('i').className = 'fas fa-circle'; }
        });
    }

    btnOpen.addEventListener('click',   openModal);
    btnClose.addEventListener('click',  closeModal);
    btnCancel.addEventListener('click', closeModal);
    modal.addEventListener('click', function(e) {
        if (e.target === modal) closeModal(); /* overlay'e tıklayınca kapat */
    });
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape' && modal.classList.contains('open')) closeModal();
    });

    /* ── Şifre politikası kontrolleri — backend ile BİREBİR AYNI kurallar ── */
    function checkPolicy(pw) {
        var rules = [
            { el: chkLen,     pass: pw.length >= 10 },
            { el: chkUpper,   pass: /[A-Z]/.test(pw) },
            { el: chkLower,   pass: /[a-z]/.test(pw) },
            { el: chkDigit,   pass: /\d/.test(pw) },
            { el: chkSpecial, pass: /[!@#$%^&*()\-_=+\[\]{};:,./<>?\\|`~]/.test(pw) }
        ];
        var allPass = true;
        rules.forEach(function(r) {
            if (!r.el) return;
            var icon = r.el.querySelector('i');
            if (pw.length === 0) {
                r.el.className = '';
                icon.className = 'fas fa-circle';
            } else if (r.pass) {
                r.el.className = 'pass';
                icon.className = 'fas fa-check-circle';
            } else {
                r.el.className = 'fail';
                icon.className = 'fas fa-times-circle';
                allPass = false;
            }
        });
        return pw.length > 0 && allPass;
    }

    /* Submit butonu durumu — politika + eşleşme ikisi de ZORUNLU */
    function updateSubmitState() {
        var pw      = newPwInput.value;
        var cf      = confirmInput.value;
        var policyOk = checkPolicy(pw);
        var matchOk  = pw.length > 0 && pw === cf;
        submitBtn.disabled = !(policyOk && matchOk);
    }

    /* Şifre güç göstergesi */
    newPwInput.addEventListener('input', function() {
        var pw    = newPwInput.value;
        checkPolicy(pw);
        var score = 0;
        if (pw.length >= 10) score++;
        if (pw.length >= 14) score++;
        if (/[A-Z]/.test(pw)) score++;
        if (/[a-z]/.test(pw)) score++;
        if (/\d/.test(pw)) score++;
        if (/[!@#$%^&*()\-_=+\[\]{};:'",.<>?\/\|`~]/.test(pw)) score++;
        var pct   = Math.min((score / 6) * 100, 100);
        var color, label;
        if      (score <= 2) { color = '#ef4444'; label = 'Çok Zayıf'; }
        else if (score <= 3) { color = '#f97316'; label = 'Zayıf'; }
        else if (score <= 4) { color = '#eab308'; label = 'Orta'; }
        else if (score <= 5) { color = '#22c55e'; label = 'Güçlü'; }
        else                  { color = '#16a34a'; label = 'Çok Güçlü'; }
        strengthFill.style.width     = pct + '%';
        strengthFill.style.background = color;
        strengthText.textContent      = pw.length > 0 ? label : '';
        strengthText.style.color      = color;
        updateSubmitState();
    });

    confirmInput.addEventListener('input', function() {
        var pw      = newPwInput.value;
        var confirm = confirmInput.value;
        if (!confirm) { matchMsg.style.display = 'none'; updateSubmitState(); return; }
        matchMsg.style.display = 'block';
        if (pw === confirm) {
            matchMsg.textContent = '✓ Şifreler eşleşiyor';
            matchMsg.style.color = 'var(--teal-dk)';
        } else {
            matchMsg.textContent = '✗ Şifreler eşleşmiyor';
            matchMsg.style.color = 'var(--danger)';
        }
        updateSubmitState();
    });
}

/* ══════════════════════════════════════════
   DENETİM KAYITLARI ARAMA
══════════════════════════════════════════ */
function bindAuditSearch() {
    var input = document.getElementById('auditSearch');
    if (!input) return;
    input.addEventListener('input', function() {
        var q = input.value.toLowerCase().trim();
        document.querySelectorAll('#auditList .audit-item').forEach(function(row) {
            var text = (row.dataset.search || '').toLowerCase();
            row.style.display = (!q || text.includes(q)) ? '' : 'none';
        });
    });
}

/* ══════════════════════════════════════════
   PDF RAPOR FORM DOĞRULAMASI
══════════════════════════════════════════ */
function bindReportForm() {
    var dateInput  = document.getElementById('reportDate');
    var pitchInput = document.getElementById('reportPitch');
    var submitBtn  = document.getElementById('btnDownloadPdf');
    var hintEl     = document.getElementById('reportHint');
    var warnBox    = document.getElementById('reportDateWarn');
    var warnText   = document.getElementById('reportDateWarnText');

    if (!dateInput || !pitchInput || !submitBtn) return;

    /* Tarih limiti: maks 1 ay ilerisi */
    var maxDate = new Date();
    maxDate.setMonth(maxDate.getMonth() + 1);
    dateInput.max = maxDate.toISOString().split('T')[0];

    function checkReportForm() {
        var dateOk = false;

        if (dateInput.value) {
            var sel = new Date(dateInput.value + 'T00:00:00');
            if (sel > maxDate) {
                warnBox.classList.add('visible');
                var maxStr = maxDate.getDate().toString().padStart(2,'0') + '.'
                           + (maxDate.getMonth()+1).toString().padStart(2,'0') + '.'
                           + maxDate.getFullYear();
                warnText.textContent = 'En fazla 1 ay ilerisine rapor oluşturulabilir. (' + maxStr + ' tarihine kadar)';
                dateInput.value = '';
            } else {
                warnBox.classList.remove('visible');
                dateOk = true;
            }
        } else {
            warnBox.classList.remove('visible');
        }

        var ok = dateOk && pitchInput.value;
        submitBtn.disabled = !ok;
        if (ok) {
            hintEl.innerHTML = '<i class="fas fa-check-circle"></i> <span>Rapor indirmeye hazır.</span>';
            hintEl.classList.add('ready');
        } else {
            hintEl.innerHTML = '<i class="fas fa-info-circle"></i> <span>Tarih ve saha seçerek rapor oluşturabilirsiniz.</span>';
            hintEl.classList.remove('ready');
        }
    }

    dateInput.addEventListener('change', checkReportForm);
    pitchInput.addEventListener('change', checkReportForm);
}

/* ══ Toplu kilit kaldırma ══ */
function initBulkUnblock() {
    var selectAll = document.getElementById('selectAllBlocks');
    var checks    = document.querySelectorAll('.block-check');
    var countEl   = document.getElementById('bulkBlockCount');
    var btnBulk   = document.getElementById('btnBulkUnblock');
    var form      = document.getElementById('bulkUnblockForm');

    if (!selectAll || !checks.length) return;

    function updateCount() {
        var checked = document.querySelectorAll('.block-check:checked').length;
        countEl.textContent = checked + ' kilit seçili';
        btnBulk.disabled = (checked === 0);
        selectAll.checked = (checked === checks.length);
        selectAll.indeterminate = (checked > 0 && checked < checks.length);
    }

    selectAll.addEventListener('change', function() {
        checks.forEach(function(cb) { cb.checked = selectAll.checked; });
        updateCount();
    });

    checks.forEach(function(cb) {
        cb.addEventListener('change', updateCount);
    });

    form.addEventListener('submit', function(e) {
        e.preventDefault();
        var checked = document.querySelectorAll('.block-check:checked').length;
        if (checked === 0) return;
        sysConfirm({
            title: 'Toplu Kilit Kaldırma',
            body: 'Seçili ' + checked + ' slot kilidini kaldırmak istiyor musunuz?\n\nBu işlem geri alınamaz.',
            icon: 'danger',
            iconClass: 'fa-unlock',
            confirmText: 'Kilitleri Kaldır',
            confirmStyle: 'btn-danger'
        }).then(function(ok) {
            if (ok) {
                setButtonLoading(btnBulk, 'Kaldırılıyor...');
                form.submit();
            }
        });
    });
}

/* ══════════════════════════════════════════════════════════════════
   SAAT SEÇİCİ (hour-picker) — saha ekleme sihirbazı & düzenleme modalı
   ──────────────────────────────────────────────────────────────
   Her çip bir checkbox (name="slot_hours"); seçim → .selected
   Değişiklikte picker üzerinde 'hp:change' olayı tetiklenir.
══════════════════════════════════════════════════════════════════ */
function _pad2(n) { return (n < 10 ? '0' : '') + n; }

function hpSelectedHours(picker) {
    return Array.prototype.map.call(
        picker.querySelectorAll('input[name="slot_hours"]:checked'),
        function(inp) { return parseInt(inp.value, 10); }
    ).sort(function(a, b) { return a - b; });
}

/* [9,10,11,17,18] → ['09:00–12:00', '17:00–19:00'] */
function hpRanges(hours) {
    var ranges = [], start = null, prev = null;
    hours.forEach(function(h) {
        if (start !== null && h === prev + 1) { prev = h; return; }
        if (start !== null) ranges.push(_pad2(start) + ':00–' + _pad2(prev + 1) + ':00');
        start = prev = h;
    });
    if (start !== null) ranges.push(_pad2(start) + ':00–' + _pad2(prev + 1) + ':00');
    return ranges;
}

function hpRefresh(picker) {
    picker.querySelectorAll('.hour-chip').forEach(function(chip) {
        chip.classList.toggle('selected', chip.querySelector('input').checked);
    });
    picker.querySelectorAll('.hp-group').forEach(function(group) {
        var inputs = group.querySelectorAll('input[name="slot_hours"]');
        var allOn  = Array.prototype.every.call(inputs, function(i) { return i.checked; });
        var btn    = group.querySelector('.hp-group-toggle');
        btn.textContent = allOn ? 'Kaldır' : 'Tümünü seç';
        btn.classList.toggle('on', allOn);
    });
    var hours = hpSelectedHours(picker);
    picker.querySelector('.hp-count-num').textContent = hours.length;
    picker.querySelector('.hp-count').classList.toggle('zero', hours.length === 0);
    picker.querySelector('.hp-summary').classList.toggle('empty', hours.length === 0);
    picker.querySelector('.hp-summary-text').textContent = hours.length
        ? 'Açık saatler: ' + hpRanges(hours).join('  ·  ')
        : 'Henüz saat seçilmedi';
    picker.dispatchEvent(new CustomEvent('hp:change', { detail: { count: hours.length } }));
}

function hpSetHours(picker, hours) {
    picker.querySelectorAll('input[name="slot_hours"]').forEach(function(inp) {
        inp.checked = hours.indexOf(parseInt(inp.value, 10)) !== -1;
    });
    hpRefresh(picker);
}

function initHourPickers() {
    document.querySelectorAll('.hour-picker').forEach(function(picker) {
        picker.addEventListener('change', function(e) {
            if (e.target.name === 'slot_hours') hpRefresh(picker);
        });
        picker.querySelectorAll('[data-hp-action]').forEach(function(btn) {
            btn.addEventListener('click', function() {
                var on = btn.dataset.hpAction === 'all';
                picker.querySelectorAll('input[name="slot_hours"]').forEach(function(i) { i.checked = on; });
                hpRefresh(picker);
            });
        });
        picker.querySelectorAll('.hp-group').forEach(function(group) {
            group.querySelector('.hp-group-toggle').addEventListener('click', function() {
                var inputs = group.querySelectorAll('input[name="slot_hours"]');
                var allOn  = Array.prototype.every.call(inputs, function(i) { return i.checked; });
                inputs.forEach(function(i) { i.checked = !allOn; });
                hpRefresh(picker);
            });
        });
        hpRefresh(picker);
    });
}

/* ══ Müşteri tipi bazlı ücret alanları (price_<tip_id>) ══
   Boş alan = tip o sahada kapalı. En az bir ücret zorunlu. */
function tpInputs(prefix) {
    var list = document.getElementById(prefix + 'List');
    return list ? Array.prototype.slice.call(list.querySelectorAll('input[type="number"]')) : [];
}

/* Geçerliyse true; değilse hatayı gösterir */
function tpValidate(prefix) {
    var inputs = tpInputs(prefix);
    var errEl  = document.getElementById(prefix + 'Error');
    if (!inputs.length) return false;
    for (var i = 0; i < inputs.length; i++) {
        if (!inputs[i].reportValidity()) return false;
    }
    var filled = inputs.some(function(inp) { return inp.value.trim() !== ''; });
    if (errEl) errEl.classList.toggle('visible', !filled);
    if (!filled) inputs[0].focus();
    return filled;
}

function tpSetPrices(prefix, prices) {
    tpInputs(prefix).forEach(function(inp) {
        var p = prices[inp.dataset.ctypeId];
        inp.value = (p === undefined || p === null) ? '' : p;
    });
    var errEl = document.getElementById(prefix + 'Error');
    if (errEl) errEl.classList.remove('visible');
}

function tpBindErrorReset(prefix) {
    var errEl = document.getElementById(prefix + 'Error');
    tpInputs(prefix).forEach(function(inp) {
        inp.addEventListener('input', function() { if (errEl) errEl.classList.remove('visible'); });
    });
}

/* ══ Saha ekleme sihirbazı: 1) ad + tip ücretleri → 2) saat aralıkları ══ */
function initPitchWizard() {
    var form = document.getElementById('addPitchForm');
    if (!form) return;
    var nameInp   = document.getElementById('pitchName');
    var picker    = document.getElementById('addPitchPicker');
    var nextBtn   = document.getElementById('wzNext');
    var submitBtn = document.getElementById('wzSubmit');
    tpBindErrorReset('pitchPrice');

    function goStep(n) {
        form.querySelectorAll('.wz-panel').forEach(function(p) {
            p.classList.toggle('active', p.dataset.step === String(n));
        });
        document.querySelectorAll('#pitchWizard .wz-step').forEach(function(s) {
            var i = parseInt(s.dataset.stepInd, 10);
            s.classList.toggle('active', i === n);
            s.classList.toggle('done', i < n);
        });
    }

    function renderRecap() {
        document.getElementById('wzRecapName').textContent = nameInp.value;
        var box = document.getElementById('wzRecapPrices');
        box.innerHTML = '';
        tpInputs('pitchPrice').forEach(function(inp) {
            if (inp.value.trim() === '') return;
            var span = document.createElement('span');
            span.textContent = inp.dataset.ctypeName + ' ';
            var strong = document.createElement('strong');
            strong.textContent = inp.value + ' TL';
            span.appendChild(strong);
            box.appendChild(span);
        });
    }

    nextBtn.addEventListener('click', function() {
        nameInp.value = nameInp.value.trim();
        if (!nameInp.reportValidity() || !tpValidate('pitchPrice')) return;
        renderRecap();
        goStep(2);
    });
    /* 1. adımda Enter → formu göndermek yerine ilerle */
    [nameInp].concat(tpInputs('pitchPrice')).forEach(function(inp) {
        inp.addEventListener('keydown', function(e) {
            if (e.key === 'Enter') { e.preventDefault(); nextBtn.click(); }
        });
    });
    document.getElementById('wzBack').addEventListener('click', function() { goStep(1); });
    document.getElementById('wzEdit').addEventListener('click', function() { goStep(1); nameInp.focus(); });

    picker.addEventListener('hp:change', function(e) { submitBtn.disabled = e.detail.count === 0; });
    submitBtn.disabled = hpSelectedHours(picker).length === 0;

    form.addEventListener('submit', function(e) {
        if (hpSelectedHours(picker).length === 0) { e.preventDefault(); return; }
        setButtonLoading(submitBtn, 'Oluşturuluyor...');
    });
}

/* ══ Saha düzenleme modalı: tip ücretleri + saat aralıkları ══ */
function initPitchEditModal() {
    var modal = document.getElementById('pitchEditModal');
    if (!modal) return;
    var form    = document.getElementById('pitchEditForm');
    var picker  = document.getElementById('pitchEditPicker');
    var saveBtn = document.getElementById('btnSavePitchEdit');
    tpBindErrorReset('pitchEditPrice');

    function openModal(btn) {
        form.action = '/admin/update_pitch/' + btn.dataset.pitchId;
        document.getElementById('pitchEditName').textContent = btn.dataset.pitchName;
        tpSetPrices('pitchEditPrice', JSON.parse(btn.dataset.pitchPrices || '{}'));
        var hours = (btn.dataset.pitchHours || '').split(',').filter(Boolean).map(Number);
        hpSetHours(picker, hours);
        modal.querySelector('.pe-modal-body').scrollTop = 0;
        modal.classList.add('open');
        document.body.style.overflow = 'hidden';
    }
    function closeModal() {
        modal.classList.remove('open');
        document.body.style.overflow = '';
    }

    document.querySelectorAll('.btn-edit-pitch').forEach(function(btn) {
        btn.addEventListener('click', function() { openModal(btn); });
    });
    document.getElementById('btnClosePitchEdit').addEventListener('click', closeModal);
    document.getElementById('btnCancelPitchEdit').addEventListener('click', closeModal);
    modal.addEventListener('click', function(e) { if (e.target === modal) closeModal(); });
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape' && modal.classList.contains('open')) closeModal();
    });

    picker.addEventListener('hp:change', function(e) { saveBtn.disabled = e.detail.count === 0; });

    form.addEventListener('submit', function(e) {
        if (!tpValidate('pitchEditPrice') || hpSelectedHours(picker).length === 0) {
            e.preventDefault();
            return;
        }
        setButtonLoading(saveBtn, 'Kaydediliyor...');
    });
}

/* ══ Müşteri tipleri: ekleme formu + yeniden adlandırma modalı ══ */
function initCustomerTypes() {
    var addForm = document.getElementById('addCtypeForm');
    if (addForm) {
        addForm.addEventListener('submit', function(e) {
            var nameInp = document.getElementById('ctName');
            nameInp.value = nameInp.value.trim();
            if (!addForm.checkValidity()) { e.preventDefault(); addForm.reportValidity(); return; }
            var btn = addForm.querySelector('button[type="submit"]');
            setButtonLoading(btn, btn.dataset.loadingText);
        });
    }

    var modal = document.getElementById('ctypeEditModal');
    if (!modal) return;
    var form    = document.getElementById('ctypeEditForm');
    var nameInp = document.getElementById('ctypeEditName');

    function closeModal() {
        modal.classList.remove('open');
        document.body.style.overflow = '';
    }
    document.querySelectorAll('.btn-edit-ctype').forEach(function(btn) {
        btn.addEventListener('click', function() {
            form.action   = '/admin/customer_types/' + btn.dataset.ctypeId + '/update';
            nameInp.value = btn.dataset.ctypeName;
            modal.classList.add('open');
            document.body.style.overflow = 'hidden';
            nameInp.focus();
            nameInp.select();
        });
    });
    document.getElementById('btnCloseCtypeEdit').addEventListener('click', closeModal);
    document.getElementById('btnCancelCtypeEdit').addEventListener('click', closeModal);
    modal.addEventListener('click', function(e) { if (e.target === modal) closeModal(); });
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape' && modal.classList.contains('open')) closeModal();
    });
    form.addEventListener('submit', function(e) {
        nameInp.value = nameInp.value.trim();
        if (!form.checkValidity()) { e.preventDefault(); form.reportValidity(); return; }
        setButtonLoading(document.getElementById('btnSaveCtypeEdit'), 'Kaydediliyor...');
    });
}

/* ══ DOMContentLoaded — tüm bağlamalar burada ══ */
document.addEventListener('DOMContentLoaded', function() {
    /* Özel modal sistemi başlat */
    _initSysModal();

    /* ── Geri tuşuyla public sayfaya dönüşü engelle ── */
    history.replaceState(null, '', location.href);
    window.addEventListener('popstate', function() {
        history.pushState(null, '', location.href);
    });

    /* Tab navigasyon */
    document.querySelectorAll('.sidebar-nav-item[data-tab]').forEach(function(el) {
        el.addEventListener('click',   function(){ switchTab(el.dataset.tab); });
        el.addEventListener('keydown', function(e){ if(e.key==='Enter'||e.key===' ') switchTab(el.dataset.tab); });
    });

    bindConfirmForms();
    bindFilterBtns();
    initSessionTimer();
    bindPickItems();
    initCal();
    bindCharCounter();
    bindLogout();
    bindAuditSearch();
    bindPasswordModal();
    bindReportForm();

    /* Sahalar: saat seçici, ekleme sihirbazı, düzenleme modalı */
    initHourPickers();
    initPitchWizard();
    initPitchEditModal();
    initCustomerTypes();

    /* Sekmeler arası kısayol butonları (data-goto-tab) */
    document.querySelectorAll('[data-goto-tab]').forEach(function(el) {
        el.addEventListener('click', function() { switchTab(el.dataset.gotoTab); });
    });

    /* İşlem sonrası doğru sekmeye dön: /admin/?tab=sahalar */
    var initialTab = new URLSearchParams(location.search).get('tab');
    if (initialTab && document.getElementById('tab-' + initialTab)) switchTab(initialTab);

    /* Kilitle butonu */
    var btnBlock = document.getElementById('btnSubmitBlock');
    if (btnBlock) btnBlock.addEventListener('click', submitBlock);

    /* Toplu kilit kaldırma */
    initBulkUnblock();
});
