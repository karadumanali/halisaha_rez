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

/* ══════════════════════════════════════════
   FORM ONAY DİYALOĞU — data-msg bazlı
   inline onclick YOK → CSP uyumlu
══════════════════════════════════════════ */
function bindConfirmForms() {
    document.querySelectorAll('.confirm-form').forEach(function(form) {
        form.addEventListener('submit', function(e) {
            var msg = form.dataset.msg || 'Devam etmek istiyor musunuz?';
            if (!confirm(msg)) {
                e.preventDefault();
            }
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
            alert('Oturumunuzun süresi doldu.');
            window.location.href = '/logout';
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
    updateSummary();
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
    if (selPitches.length === 0) { alert('En az 1 saha seçin!'); return; }
    if (selDates.length === 0)   { alert('En az 1 tarih seçin!'); return; }
    if (selSlots.length === 0)   { alert('En az 1 saat dilimi seçin!'); return; }
    var total = selPitches.length * selDates.length * selSlots.length;
    if (!confirm(total + ' slot kilitlenecek. Devam etmek istiyor musunuz?')) return;
    var container = document.getElementById('blockHiddenInputs');
    container.innerHTML = '';
    function addInput(name, val) {
        var inp = document.createElement('input'); inp.type='hidden'; inp.name=name; inp.value=val; container.appendChild(inp);
    }
    selPitches.forEach(function(p){ addInput('pitch_ids', p); });
    selDates.forEach(function(d){   addInput('dates', d); });
    selSlots.forEach(function(s){   addInput('time_slots', s); });
    document.getElementById('blockForm').submit();
}

/* Karakter sayacı */
function bindCharCounter() {
    var ta = document.getElementById('bReason');
    var counter = document.getElementById('charCount');
    if (ta && counter) {
        ta.addEventListener('input', function(){ counter.textContent = ta.value.length; });
    }
}

/* Çıkış onayı */
function bindLogout() {
    var btn = document.getElementById('logoutBtn');
    if (btn) {
        btn.addEventListener('click', function(e) {
            if (!confirm('Oturumu kapatmak istiyor musunuz?')) e.preventDefault();
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
        var checked = document.querySelectorAll('.block-check:checked').length;
        if (checked === 0) { e.preventDefault(); return; }
        if (!confirm('Seçili ' + checked + ' slot kilidini kaldırmak istiyor musunuz?\n\nBu işlem geri alınamaz.')) {
            e.preventDefault();
        }
    });
}

/* ══ DOMContentLoaded — tüm bağlamalar burada ══ */
document.addEventListener('DOMContentLoaded', function() {
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

    /* Kilitle butonu */
    var btnBlock = document.getElementById('btnSubmitBlock');
    if (btnBlock) btnBlock.addEventListener('click', submitBlock);

    /* Toplu kilit kaldırma */
    initBulkUnblock();
});