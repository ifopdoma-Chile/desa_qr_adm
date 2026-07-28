document.addEventListener('DOMContentLoaded', function () {
    // ─── Sidebar toggle ───
    var toggle = document.getElementById('sidebarToggle');
    var sidebar = document.getElementById('sidebar');
    if (toggle && sidebar) {
        toggle.addEventListener('click', function () {
            sidebar.classList.toggle('open');
        });
        document.addEventListener('click', function (e) {
            if (window.innerWidth <= 768 && sidebar.classList.contains('open') &&
                !sidebar.contains(e.target) && e.target !== toggle) {
                sidebar.classList.remove('open');
            }
        });
    }

    // ─── Flash dismiss ───
    document.querySelectorAll('.alert-close').forEach(function (btn) {
        btn.addEventListener('click', function () {
            this.closest('.alert').remove();
        });
    });
    document.querySelectorAll('.alert').forEach(function (el) {
        setTimeout(function () { el.remove(); }, 6000);
    });

    // ─── QR type tabs ───
    var tabs = document.querySelectorAll('.qr-type-tab');
    var fields = document.querySelectorAll('.qr-type-fields');
    tabs.forEach(function (tab) {
        tab.addEventListener('click', function () {
            var target = this.dataset.target;
            tabs.forEach(function (t) { t.classList.remove('active'); });
            fields.forEach(function (f) { f.classList.remove('active'); });
            this.classList.add('active');
            var targetEl = document.getElementById('fields-' + target);
            if (targetEl) targetEl.classList.add('active');
            var typeInput = document.querySelector('input[name="qr_type"]') ||
                           document.querySelector('select[name="qr_type"]');
            if (typeInput) typeInput.value = target;
        });
    });

    // ─── Activate first tab by default ───
    if (tabs.length > 0 && !document.querySelector('.qr-type-tab.active')) {
        tabs[0].click();
    }

    // ─── QR type select in form ───
    var typeSelect = document.querySelector('select[name="qr_type"]');
    if (typeSelect) {
        typeSelect.addEventListener('change', function () {
            var target = this.value;
            tabs.forEach(function (t) {
                t.classList.toggle('active', t.dataset.target === target);
            });
            fields.forEach(function (f) {
                f.classList.toggle('active', f.id === 'fields-' + target);
            });
        });
    }

    // ─── Confirm dialogs ───
    document.querySelectorAll('[data-confirm]').forEach(function (el) {
        el.addEventListener('click', function (e) {
            if (!confirm(this.dataset.confirm || 'Esta seguro?')) {
                e.preventDefault();
            }
        });
    });

    // ─── Slug auto-generate ───
    var slugInput = document.querySelector('input[name="slug"]');
    var titleInput = document.querySelector('input[name="title"]');
    if (slugInput && titleInput && !slugInput.value) {
        titleInput.addEventListener('blur', function () {
            if (!slugInput.value) {
                slugInput.value = this.value.toLowerCase()
                    .replace(/[^a-z0-9]+/g, '-')
                    .replace(/^-|-$/g, '')
                    .substring(0, 50) || '';
            }
        });
    }

    // ─── Copy to clipboard ───
    document.querySelectorAll('[data-copy]').forEach(function (el) {
        el.addEventListener('click', function () {
            var text = this.dataset.copy;
            if (navigator.clipboard) {
                navigator.clipboard.writeText(text).then(function () {
                    var orig = el.textContent;
                    el.textContent = 'Copiado!';
                    setTimeout(function () { el.textContent = orig; }, 2000);
                });
            }
        });
    });

    // ─── Chart rendering (simple bar charts) ───
    document.querySelectorAll('.chart-canvas').forEach(function (canvas) {
        var labels = JSON.parse(canvas.dataset.labels || '[]');
        var values = JSON.parse(canvas.dataset.values || '[]');
        if (labels.length === 0) return;
        var ctx = canvas.getContext('2d');
        var max = Math.max.apply(null, values);
        var barWidth = Math.max(8, Math.min(40, (canvas.width - 40) / labels.length));
        var padding = 30;

        ctx.clearRect(0, 0, canvas.width, canvas.height);
        ctx.fillStyle = '#2c6b9e';

        values.forEach(function (v, i) {
            var barHeight = max > 0 ? (v / max) * (canvas.height - padding - 10) : 0;
            var x = 20 + i * (barWidth + 4);
            var y = canvas.height - 10 - barHeight;
            ctx.fillRect(x, y, barWidth, barHeight);

            ctx.fillStyle = '#495057';
            ctx.font = '10px sans-serif';
            ctx.textAlign = 'center';
            ctx.fillText(labels[i].substring(5, 10), x + barWidth / 2, canvas.height - 2);
            ctx.fillText(v, x + barWidth / 2, y - 4);
            ctx.fillStyle = '#2c6b9e';
        });
    });
});

function getCookie(name) {
    var match = document.cookie.match(new RegExp('(^| )' + name + '=([^;]+)'));
    return match ? match[2] : null;
}
