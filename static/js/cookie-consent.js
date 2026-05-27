(function() {
    var CONSENT_COOKIE = 'cookie_consent';
    var VALID_VALUES = ['essential', 'all'];

    function getCookie(name) {
        var match = document.cookie.match('(^|;)\\s*' + name + '\\s*=\\s*([^;]+)');
        return match ? match.pop() : null;
    }

    function setConsentCookie(value) {
        var parts = [
            CONSENT_COOKIE + '=' + value,
            'path=/',
            'SameSite=Lax'
        ];
        if (window.location.protocol === 'https:') {
            parts.push('Secure');
        }
        document.cookie = parts.join('; ');
    }

    function hasValidConsent() {
        var value = getCookie(CONSENT_COOKIE);
        if (!value) return false;
        for (var i = 0; i < VALID_VALUES.length; i++) {
            if (value === VALID_VALUES[i]) return true;
        }
        return false;
    }

    function showBanner() {
        var banner = document.getElementById('cookie-banner');
        if (banner) banner.style.display = '';
    }

    function hideBanner() {
        var banner = document.getElementById('cookie-banner');
        if (banner) banner.style.display = 'none';
    }

    function showOptions() {
        var overlay = document.getElementById('cookie-options-overlay');
        if (overlay) {
            overlay.style.display = '';
            overlay.classList.add('active');
        }
    }

    function hideOptions() {
        var overlay = document.getElementById('cookie-options-overlay');
        if (overlay) {
            overlay.classList.remove('active');
            overlay.style.display = 'none';
        }
    }

    document.addEventListener('DOMContentLoaded', function() {
        if (!hasValidConsent()) {
            showBanner();
        }

        var essentialBtn = document.getElementById('cookie-essential-only');
        if (essentialBtn) {
            essentialBtn.addEventListener('click', function() {
                setConsentCookie('essential');
                hideBanner();
            });
        }

        var optionsBtn = document.getElementById('cookie-options-btn');
        if (optionsBtn) {
            optionsBtn.addEventListener('click', function() {
                showOptions();
            });
        }

        var closeBtn = document.getElementById('cookie-options-close');
        if (closeBtn) {
            closeBtn.addEventListener('click', function() {
                hideOptions();
            });
        }

        var saveBtn = document.getElementById('cookie-save-prefs');
        if (saveBtn) {
            saveBtn.addEventListener('click', function() {
                setConsentCookie('essential');
                hideOptions();
                hideBanner();
            });
        }

        var acceptAllBtn = document.getElementById('cookie-accept-all');
        if (acceptAllBtn) {
            acceptAllBtn.addEventListener('click', function() {
                setConsentCookie('all');
                hideOptions();
                hideBanner();
            });
        }

        var overlay = document.getElementById('cookie-options-overlay');
        if (overlay) {
            overlay.addEventListener('click', function(e) {
                if (e.target === overlay) {
                    hideOptions();
                }
            });
        }
    });
})();
