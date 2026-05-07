(function () {
    var banner = document.getElementById('unsaved-banner');
    var form = document.querySelector('[data-unsaved-form]');
    if (!banner || !form) return;

    var saveBtn = banner.querySelector('#unsaved-save-btn');
    var snapshot = {};
    var isDirty = false;
    var submitting = false;

    function takeSnapshot() {
        snapshot = {};
        var els = form.elements;
        for (var i = 0; i < els.length; i++) {
            var el = els[i];
            if (!el.name) continue;
            if (el.type === 'file') {
                snapshot[el.name] = '';
            } else if (el.type === 'checkbox') {
                snapshot[el.name] = el.checked;
            } else if (el.type === 'radio') {
                if (el.checked) {
                    snapshot[el.name] = el.value;
                }
            } else {
                snapshot[el.name] = el.value;
            }
        }
    }

    function checkDirty() {
        var els = form.elements;
        for (var i = 0; i < els.length; i++) {
            var el = els[i];
            if (!el.name) continue;
            if (el.type === 'file') {
                if (el.files && el.files.length > 0) return true;
            } else if (el.type === 'checkbox') {
                if (snapshot[el.name] !== undefined && el.checked !== snapshot[el.name]) return true;
            } else if (el.type === 'radio') {
                if (el.checked && snapshot[el.name] !== undefined && el.value !== snapshot[el.name]) return true;
            } else {
                if (snapshot[el.name] !== undefined && el.value !== snapshot[el.name]) return true;
            }
        }
        return false;
    }

    function updateBanner() {
        var dirty = checkDirty();
        if (dirty && !isDirty) {
            banner.classList.add('active');
            isDirty = true;
        } else if (!dirty && isDirty) {
            banner.classList.remove('active');
            isDirty = false;
        }
    }

    form.addEventListener('input', updateBanner);
    form.addEventListener('change', updateBanner);

    if (saveBtn) {
        saveBtn.addEventListener('click', function (e) {
            e.preventDefault();
            submitting = true;
            form.submit();
        });
    }

    form.addEventListener('submit', function () {
        submitting = true;
    });

    window.addEventListener('beforeunload', function (e) {
        if (isDirty && !submitting) {
            e.preventDefault();
            e.returnValue = '';
        }
    });

    takeSnapshot();
})();
