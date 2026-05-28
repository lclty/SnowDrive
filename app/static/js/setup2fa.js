/**
 * SnowDrive - 2FA Setup Page JavaScript
 */
(function() {
    'use strict';
    var errorEl = document.getElementById('error-message');

    function showError(msg) { errorEl.textContent = msg; errorEl.style.display = 'block'; setTimeout(function() { errorEl.style.display = 'none'; }, 5000); }
    function setLoading(el, loading) {
        if (loading) { el.disabled = true; el.dataset.orig = el.innerHTML; el.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> ...'; }
        else { el.disabled = false; if (el.dataset.orig) el.innerHTML = el.dataset.orig; }
    }
    function arrayBufferToBase64url(buf) {
        var bytes = new Uint8Array(buf), bin = '';
        for (var i = 0; i < bytes.byteLength; i++) bin += String.fromCharCode(bytes[i]);
        return btoa(bin).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
    }

    // Theme handled centrally in app.js

    // Method selection
    document.querySelectorAll('.method-option').forEach(function(btn) {
        btn.addEventListener('click', function() {
            var method = this.dataset.method;
            document.getElementById('method-select').style.display = 'none';
            if (method === 'totp') {
                document.getElementById('totp-setup').style.display = 'block';
            } else {
                document.getElementById('webauthn-setup').style.display = 'block';
            }
        });
    });

    // Back buttons
    document.getElementById('back-to-methods').addEventListener('click', function() {
        document.getElementById('totp-setup').style.display = 'none';
        document.getElementById('method-select').style.display = 'block';
    });
    document.getElementById('back-to-methods-wa').addEventListener('click', function() {
        document.getElementById('webauthn-setup').style.display = 'none';
        document.getElementById('method-select').style.display = 'block';
    });

    // ─── TOTP Setup ──────────────────────────────────────────────
    document.getElementById('totp-generate-btn').addEventListener('click', async function() {
        setLoading(this, true);
        try {
            var resp = await fetch('/api/auth/setup-2fa', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({action: 'totp_generate'}) });
            var data = await resp.json();
            if (resp.ok) {
                document.getElementById('totp-qr-placeholder').style.display = 'none';
                document.getElementById('totp-qr').src = data.qr_code;
                document.getElementById('totp-qr').style.display = 'block';
                document.getElementById('totp-secret-text').textContent = data.secret;
                document.getElementById('totp-secret-display').style.display = 'flex';
                this.style.display = 'none';
                document.getElementById('totp-verify-area').style.display = 'block';
                document.getElementById('totp-code').focus();
            } else { showError(data.error || 'Failed.'); }
        } catch (e) { showError('Network error.'); }
        finally { setLoading(this, false); }
    });

    document.getElementById('copy-secret').addEventListener('click', function() {
        navigator.clipboard.writeText(document.getElementById('totp-secret-text').textContent).then(function() {
            var b = document.getElementById('copy-secret');
            b.innerHTML = '<i class="fa-solid fa-check"></i> Copied';
            setTimeout(function() { b.innerHTML = '<i class="fa-solid fa-copy"></i>'; }, 2000);
        });
    });

    document.getElementById('totp-code').addEventListener('input', function() { this.value = this.value.replace(/[^0-9]/g, '').slice(0, 6); });

    document.getElementById('totp-verify-btn').addEventListener('click', async function() {
        var code = document.getElementById('totp-code').value.trim();
        if (code.length !== 6) { showError('Enter 6-digit code.'); return; }
        setLoading(this, true);
        try {
            var resp = await fetch('/api/auth/setup-2fa', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({action: 'totp_verify', code: code}) });
            var data = await resp.json();
            if (resp.ok) { onSetupComplete(); }
            else { showError(data.error || 'Verification failed.'); }
        } catch (e) { showError('Network error.'); }
        finally { setLoading(this, false); }
    });

    document.getElementById('totp-code').addEventListener('keydown', function(e) { if (e.key === 'Enter') document.getElementById('totp-verify-btn').click(); });

    // ─── WebAuthn Setup ──────────────────────────────────────────
    document.getElementById('webauthn-register-btn').addEventListener('click', async function() {
        var statusEl = document.getElementById('webauthn-status');
        statusEl.textContent = 'Preparing...';
        setLoading(this, true);
        try {
            var beginResp = await fetch('/api/auth/setup-2fa', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({action: 'webauthn_register_begin'}) });
            var beginData;
            try {
                var ct = beginResp.headers.get('content-type') || '';
                if (ct.indexOf('application/json') !== -1) beginData = await beginResp.json();
                else beginData = { error: await beginResp.text() };
            } catch (err) { beginData = { error: 'Failed to parse server response.' }; }
            if (!beginResp.ok) { showError(beginData.error || 'WebAuthn not available.'); statusEl.textContent = ''; setLoading(this, false); return; }

            var options = beginData.options;
            options.challenge = Uint8Array.from(atob(options.challenge.replace(/-/g, '+').replace(/_/g, '/')), function(c) { return c.charCodeAt(0); });
            options.user.id = Uint8Array.from(atob(options.user.id.replace(/-/g, '+').replace(/_/g, '/')), function(c) { return c.charCodeAt(0); });

            statusEl.textContent = 'Follow your browser prompt...';
            var credential = await navigator.credentials.create({ publicKey: options });

            var credData = {
                id: arrayBufferToBase64url(credential.rawId),
                rawId: arrayBufferToBase64url(credential.rawId),
                response: {
                    attestationObject: arrayBufferToBase64url(credential.response.attestationObject),
                    clientDataJSON: arrayBufferToBase64url(credential.response.clientDataJSON),
                },
                type: credential.type
            };

            statusEl.textContent = 'Verifying...';
            var verifyResp = await fetch('/api/auth/setup-2fa', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({action: 'webauthn_register_verify', credential: credData}) });
            var verifyData = await verifyResp.json();
            if (verifyResp.ok) { onSetupComplete(); }
            else { showError(verifyData.error || 'Registration failed.'); statusEl.textContent = ''; }
        } catch (e) {
            statusEl.textContent = '';
            if (e.name !== 'NotAllowedError') showError('WebAuthn error: ' + e.message);
        }
        finally { setLoading(this, false); }
    });

    // ─── Complete Setup ──────────────────────────────────────────
    async function onSetupComplete() {
        document.getElementById('totp-setup').style.display = 'none';
        document.getElementById('webauthn-setup').style.display = 'none';
        document.getElementById('complete-area').style.display = 'block';
    }

    document.getElementById('finish-setup').addEventListener('click', function() {
        window.location.href = '/files';
    });
})();
