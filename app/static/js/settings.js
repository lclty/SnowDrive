/**
 * SnowDrive - Settings Page JavaScript
 */
(function(){'use strict';
function init(){
    loadProfile();load2FAMethods();loadDirStat();
    loadSiteSettings();
    document.getElementById('password-form').addEventListener('submit',changePassword);
    var b=document.getElementById('settings-avatar-input');if(b)b.addEventListener('change',uploadAvatar);
    b=document.getElementById('remove-avatar-btn');if(b)b.addEventListener('click',removeAvatar);
    b=document.getElementById('add-totp-btn');if(b)b.addEventListener('click',showAddTOTP);
    b=document.getElementById('add-webauthn-btn');if(b)b.addEventListener('click',showAddWebAuthn);
    b=document.getElementById('cancel-add-totp');if(b)b.addEventListener('click',hideAddTOTP);
    b=document.getElementById('cancel-add-webauthn');if(b)b.addEventListener('click',hideAddWebAuthn);
    b=document.getElementById('settings-totp-generate');if(b)b.addEventListener('click',generateTOTP);
    b=document.getElementById('settings-totp-confirm');if(b)b.addEventListener('click',verifyTOTP);
    b=document.getElementById('settings-copy-totp-secret');if(b)b.addEventListener('click',copyTOTPSecret);
    b=document.getElementById('settings-webauthn-register');if(b)b.addEventListener('click',registerWebAuthn);
    b=document.getElementById('confirm-delete-2fa');if(b)b.addEventListener('click',confirmDelete2FA);
    var sl = document.getElementById('site-logo-input'); if (sl) sl.addEventListener('change', uploadSiteLogo);
    var rsl = document.getElementById('remove-site-logo-btn'); if (rsl) rsl.addEventListener('click', removeSiteLogo);
    var saveSiteBtn = document.getElementById('save-site-settings'); if (saveSiteBtn) saveSiteBtn.addEventListener('click', saveSiteSettings);
    b=document.getElementById('settings-totp-code');if(b)b.addEventListener('input',function(){this.value=this.value.replace(/[^0-9]/g,'').slice(0,6)});
    b=document.getElementById('delete-verify-code');if(b)b.addEventListener('input',function(){this.value=this.value.replace(/[^0-9]/g,'').slice(0,6)});
    // Delete 2FA: show/hide TOTP/WebAuthn verification based on selected method
    b=document.getElementById('delete-verify-method');if(b)b.addEventListener('change',onDeleteVerifyMethodChange);
    // Delete 2FA: WebAuthn verify button
    b=document.getElementById('delete-webauthn-verify');if(b)b.addEventListener('click',deleteWebAuthnVerify);
    // Rename confirm button (might not exist yet when init runs, hook later)
    var renameBtn = document.getElementById('confirm-rename-2fa');
    if (renameBtn) renameBtn.addEventListener('click', confirmRename2FA);
}

async function loadSiteSettings(){
    try{ var r = await apiGet('/api/settings/site'); var d = await r.json(); if (!r.ok) return; 
        if (d.site_title) document.getElementById('site-title-input').value = d.site_title;
        if (d.logo_url) { var img = document.getElementById('site-logo-img'); img.src = d.logo_url + '?_=' + Date.now(); img.style.display = 'block'; }
        if (d.icp_enabled) { document.getElementById('icp-enabled').checked = true; document.getElementById('icp-number').value = d.icp_number || ''; }
    }catch(e){}
}

async function uploadSiteLogo(e){
    var file = e.target.files[0]; if (!file) return; var fd = new FormData(); fd.append('logo', file);
    try{ var resp = await fetch('/api/settings/site/logo', { method: 'POST', credentials: 'same-origin', body: fd }); var d = await resp.json(); if (resp.ok){ showToast('Logo 上传成功','success'); loadSiteSettings(); } else showToast(d.error || '上传失败','error'); }catch(e){ showToast('Error','error') }
    e.target.value = '';
}

async function removeSiteLogo(){
    try{ var r = await fetch('/api/settings/site/logo', { method: 'DELETE', credentials: 'same-origin' }); var d = await r.json(); if (r.ok){ showToast('Logo 已移除','success'); var img = document.getElementById('site-logo-img'); if (img) { img.style.display = 'none'; img.src = ''; } } else showToast(d.error||'失败','error'); }catch(e){ showToast('Error','error') }
}

async function saveSiteSettings(){
    var title = document.getElementById('site-title-input').value.trim();
    var icp_enabled = !!document.getElementById('icp-enabled').checked;
    var icp_number = document.getElementById('icp-number').value.trim();
    try{ var r = await apiPost('/api/settings/site', { site_title: title, icp_enabled: icp_enabled, icp_number: icp_number }); var d = await r.json(); if (r.ok){ showToast('保存成功','success'); } else showToast(d.error||'保存失败','error'); }catch(e){ showToast('Error','error') }
}

async function loadProfile(){
    try{var r=await apiGet('/api/settings/profile');var d=await r.json();
        if(r.ok){var img=document.getElementById('settings-avatar-img');img.src='/api/settings/avatar?'+Date.now()}
    }catch(e){}
}

async function uploadAvatar(e){
    var file=e.target.files[0];if(!file)return;
    var fd=new FormData();fd.append('avatar',file);
    try{var r=await fetch('/api/settings/avatar',{method:'POST',credentials:'same-origin',body:fd});var d=await r.json();
        if(r.ok){showToast('Avatar updated','success');loadProfile();updateSidebarAvatar()}else showToast(d.error,'error')
    }catch(ex){showToast('Error','error')}
    e.target.value=''
}

async function removeAvatar(){
    try{var r=await apiDelete('/api/settings/avatar');if(r.ok){showToast('Removed','success');loadProfile();updateSidebarAvatar()}}catch(e){}
}

function updateSidebarAvatar(){var imgs=document.querySelectorAll('#sidebar-avatar img');imgs.forEach(function(i){i.src='/api/settings/avatar?'+Date.now()})}

async function changePassword(e){
    e.preventDefault();var cp=document.getElementById('current-password').value,np=document.getElementById('new-password').value,cn=document.getElementById('confirm-new-password').value;
    if(!cp||!np||!cn){showToast('Fill all fields','error');return}
    if(np.length<8){showToast('Min 8 chars','error');return}
    if(np!==cn){showToast('Passwords mismatch','error');return}
    var btn=document.querySelector('#password-form button[type=submit]');setLoading(btn,true);
    try{var r=await apiPut('/api/settings/password',{current_password:cp,new_password:np});var d=await r.json();
        if(r.ok){showToast('Password changed','success');document.getElementById('current-password').value='';document.getElementById('new-password').value='';document.getElementById('confirm-new-password').value=''}
        else showToast(d.error,'error')
    }catch(ex){}finally{setLoading(btn,false)}
}

// ─── 2FA Methods List ────────────────────────────────────────────
async function load2FAMethods(){
    try{var r=await apiGet('/api/settings/2fa/methods');var d=await r.json();
        if(!r.ok)return;
        // render into separate TOTP / Passkey lists (preserve container structure)
        var totpList = document.getElementById('twofa-totp-list');
        var passkeyList = document.getElementById('twofa-passkey-list');
        if (!totpList || !passkeyList) return;
        totpList.innerHTML = '';
        passkeyList.innerHTML = '';
        if(d.methods.length===0){
            totpList.innerHTML='<p style="color:var(--text-muted);font-size:0.85rem;">未配置</p>';
            passkeyList.innerHTML='<p style="color:var(--text-muted);font-size:0.85rem;">未配置</p>';
            return;
        }
        // keep global copy for other operations
        window.snowdriveTwoFAMethods = d.methods;
        d.methods.forEach(function(m){
            var icon=m.type==='totp'?'fa-mobile-screen-button':'fa-fingerprint';
            var label=m.type==='totp'?'验证器':'Passkey';
            var div=document.createElement('div');div.className='twofa-method-item';
            // rename + delete buttons
            var renameBtn = '<button class="btn btn-secondary btn-sm rename-2fa-btn" data-id="'+m.id+'" title="重命名"><i class="fa-solid fa-pen-to-square"></i></button>';
            var deleteBtn = '<button class="btn btn-danger btn-sm delete-2fa-btn" data-id="'+m.id+'" title="删除"><i class="fa-solid fa-trash"></i></button>';
            div.innerHTML='<div class="twofa-method-info"><i class="fa-solid '+icon+'"></i><div><div class="twofa-method-name">'+escapeHtml(m.name)+'</div><div class="twofa-method-type">'+label+'</div></div></div>' + renameBtn + deleteBtn;
            if (m.type === 'totp') totpList.appendChild(div); else passkeyList.appendChild(div);
        });
        // Show empty message for categories with no methods
        if (!totpList.children.length) totpList.innerHTML = '<p style="color:var(--text-muted);font-size:0.85rem;">未配置</p>';
        if (!passkeyList.children.length) passkeyList.innerHTML = '<p style="color:var(--text-muted);font-size:0.85rem;">未配置</p>';
        // Hook up rename and delete
        document.querySelectorAll('.rename-2fa-btn').forEach(function(b){ b.addEventListener('click', function(){ document.getElementById('rename-2fa-id').value=this.dataset.id; document.getElementById('rename-2fa-name').value = (window.snowdriveTwoFAMethods||[]).find(x=>x.id==this.dataset.id)?.name || ''; openModal('modal-rename-2fa'); }); });
        document.querySelectorAll('.delete-2fa-btn').forEach(function(b){b.addEventListener('click',function(){
            document.getElementById('delete-method-id').value=this.dataset.id; load2FAVerifyMethods(parseInt(this.dataset.id)); openModal('modal-delete-2fa');
        })})
        // disable delete when only one method exists
        if (d.methods.length === 1) {
            document.querySelectorAll('.delete-2fa-btn').forEach(function(btn){ btn.disabled = true; btn.title = '无法删除最后一个 2FA 方法'; });
        }
    }catch(e){}
}

async function load2FAVerifyMethods(excludeId){
    try{var r=await apiGet('/api/settings/2fa/methods');var d=await r.json();
        var sel=document.getElementById('delete-verify-method');if(!sel)return;sel.innerHTML='';
        // include all existing methods (including the one being deleted) and both TOTP and Passkey
        d.methods.forEach(function(m){
            var o=document.createElement('option');
            o.value=m.id;
            o.dataset.type = m.type;
            var label = m.name + (m.type==='totp' ? ' (验证器)' : ' (Passkey)');
            o.textContent = label;
            sel.appendChild(o);
        });
        if(sel.children.length===0) sel.innerHTML = '<option value="">无可用验证方式</option>';
        onDeleteVerifyMethodChange();
    }catch(e){}
}

function onDeleteVerifyMethodChange(){
    var sel = document.getElementById('delete-verify-method');
    var opt = sel && sel.selectedOptions[0];
    var type = opt ? opt.dataset.type : null;
    var totpGroup = document.getElementById('delete-totp-group');
    var webauthnGroup = document.getElementById('delete-webauthn-group');
    if (totpGroup) totpGroup.style.display = (type === 'totp') ? 'block' : 'none';
    if (webauthnGroup) webauthnGroup.style.display = (type === 'webauthn') ? 'block' : 'none';
    // Clear any stored webauthn credential
    window._deleteWebAuthnCredential = null;
}

var _deleteWebAuthnCredential = null;

async function deleteWebAuthnVerify(){
    var statusEl = document.getElementById('delete-webauthn-status');
    if (statusEl) statusEl.textContent = '正在启动验证...';
    var btn = document.getElementById('delete-webauthn-verify');
    setLoading(btn, true);
    try {
        var br = await fetch('/api/settings/2fa/webauthn/auth-begin', { method: 'POST', credentials: 'same-origin' });
        var bd;
        try { bd = await br.json(); } catch(e) { bd = { error: 'Failed' }; }
        if (!br.ok) { showToast(bd.error || 'WebAuthn 不可用','error'); if (statusEl) statusEl.textContent = ''; setLoading(btn, false); return; }
        var options = bd.options;
        options.challenge = Uint8Array.from(atob(options.challenge.replace(/-/g,'+').replace(/_/g,'/')), function(c){return c.charCodeAt(0)});
        if (options.allowCredentials) options.allowCredentials.forEach(function(c){ c.id = Uint8Array.from(atob(c.id.replace(/-/g,'+').replace(/_/g,'/')), function(ch){ return ch.charCodeAt(0); }); });
        if (statusEl) statusEl.textContent = '请按照浏览器提示操作...';
        var assertion = await navigator.credentials.get({ publicKey: options });
        _deleteWebAuthnCredential = { id: ab2b64(assertion.rawId), rawId: ab2b64(assertion.rawId), response: { authenticatorData: ab2b64(assertion.response.authenticatorData), clientDataJSON: ab2b64(assertion.response.clientDataJSON), signature: ab2b64(assertion.response.signature) }, type: assertion.type };
        if (statusEl) statusEl.textContent = '✓ 验证成功，可以点击删除按钮';
    } catch (e) {
        if (statusEl) statusEl.textContent = '';
        if (e.name !== 'NotAllowedError') showToast('WebAuthn 错误: ' + (e.message||e), 'error');
    } finally { setLoading(btn, false); }
}

async function confirmDelete2FA(){
    var mid = parseInt(document.getElementById('delete-method-id').value, 10);
    var pw = document.getElementById('delete-verify-password').value;
    var vmid = parseInt(document.getElementById('delete-verify-method').value, 10);
    var vc = document.getElementById('delete-verify-code').value;
    if(!pw||!vmid){ showToast('请填写密码并选择验证方式','error'); return }
    setLoading(document.getElementById('confirm-delete-2fa'),true);
    try{
        // find verify method type
        var vm = (window.snowdriveTwoFAMethods || []).find(x => x.id == vmid);
        if (!vm) {
            var rr = await apiGet('/api/settings/2fa/methods'); var dd = await rr.json(); vm = (dd.methods||[]).find(x=>x.id==vmid);
        }
        if (vm && vm.type === 'webauthn') {
            if (!_deleteWebAuthnCredential) { showToast('请先点击 Passkey 验证按钮','error'); setLoading(document.getElementById('confirm-delete-2fa'),false); return; }
            var r = await apiPost('/api/settings/2fa/delete', { method_id: mid, password: pw, verify_method_id: vmid, verify_credential: _deleteWebAuthnCredential });
            var d = await r.json();
            _deleteWebAuthnCredential = null;
            if (r.ok) { showToast('已删除','success'); closeModal('modal-delete-2fa'); load2FAMethods(); }
            else { showToast(d.error || '删除失败','error'); }
        } else {
            if(!vc){ showToast('请输入验证码','error'); setLoading(document.getElementById('confirm-delete-2fa'),false); return }
            var r = await apiPost('/api/settings/2fa/delete', { method_id: mid, password: pw, verify_method_id: vmid, verify_code: vc });
            var d = await r.json();
            if (r.ok) { showToast('已删除','success'); closeModal('modal-delete-2fa'); load2FAMethods(); }
            else { showToast(d.error || '删除失败','error'); }
        }
    }catch(e){ showToast('Error','error') }finally{ setLoading(document.getElementById('confirm-delete-2fa'),false) }
}

// Rename confirm
async function confirmRename2FA(){
    var id = parseInt(document.getElementById('rename-2fa-id').value,10);
    var name = document.getElementById('rename-2fa-name').value.trim();
    if(!id||!name){ showToast('请输入名称','error'); return }
    setLoading(document.getElementById('confirm-rename-2fa'), true);
    try{ var r = await apiPost('/api/settings/2fa/rename', { method_id: id, name: name }); var d = await r.json(); if(r.ok){ showToast('已重命名','success'); closeModal('modal-rename-2fa'); load2FAMethods(); } else showToast(d.error||'失败','error') }catch(e){}finally{ setLoading(document.getElementById('confirm-rename-2fa'), false) }
}

// ─── Add TOTP ────────────────────────────────────────────────────
function showAddTOTP(){var p=document.getElementById('add-totp-panel');if(p)p.style.display='block'}
function hideAddTOTP(){var p=document.getElementById('add-totp-panel');if(p)p.style.display='none';resetTOTPPanel()}
function resetTOTPPanel(){
    var q=document.getElementById('settings-totp-qr'),ph=document.getElementById('settings-totp-placeholder'),
        sd=document.getElementById('settings-totp-secret-display'),g=document.getElementById('settings-totp-generate'),
        v=document.getElementById('settings-totp-verify'),c=document.getElementById('settings-totp-code'),
        n=document.getElementById('settings-totp-name');
    if(q)q.style.display='none';if(ph)ph.style.display='flex';if(sd)sd.style.display='none';
    if(g)g.style.display='inline-block';if(v)v.style.display='none';if(c)c.value='';
    if(n)n.value='';
}

async function generateTOTP(){
    setLoading(document.getElementById('settings-totp-generate'),true);
    try{var r=await apiPost('/api/settings/2fa/totp/generate');var d=await r.json();
        if(r.ok){
            var q=document.getElementById('settings-totp-qr'),ph=document.getElementById('settings-totp-placeholder'),
                sd=document.getElementById('settings-totp-secret-display'),g=document.getElementById('settings-totp-generate'),
                v=document.getElementById('settings-totp-verify'),c=document.getElementById('settings-totp-code');
            if(ph)ph.style.display='none';if(q){q.src=d.qr_code;q.style.display='block'}
            if(sd){document.getElementById('settings-totp-secret').textContent=d.secret;sd.style.display='flex'}
            if(g)g.style.display='none';if(v)v.style.display='block';if(c)c.focus()
        }else showToast(d.error,'error')
    }catch(e){}finally{setLoading(document.getElementById('settings-totp-generate'),false)}
}

async function verifyTOTP(){
    var code=document.getElementById('settings-totp-code').value.trim();
    var name=document.getElementById('settings-totp-name').value.trim() || 'Authenticator';
    if(code.length!==6){showToast('Enter 6-digit code','error');return}
    setLoading(document.getElementById('settings-totp-confirm'),true);
    try{var r=await apiPost('/api/settings/2fa/totp/verify',{code:code, name:name});var d=await r.json();
        if(r.ok){showToast('TOTP added!','success');hideAddTOTP();load2FAMethods()}else showToast(d.error,'error')
    }catch(e){}finally{setLoading(document.getElementById('settings-totp-confirm'),false)}
}

function copyTOTPSecret(){
    var sec=document.getElementById('settings-totp-secret');if(!sec)return;
    navigator.clipboard.writeText(sec.textContent);var b=document.getElementById('settings-copy-totp-secret');
    if(b){b.innerHTML='<i class="fa-solid fa-check"></i>';setTimeout(function(){b.innerHTML='<i class="fa-solid fa-copy"></i>'},2000)}
}

// ─── Add WebAuthn ────────────────────────────────────────────────
function showAddWebAuthn(){var p=document.getElementById('add-webauthn-panel');if(p)p.style.display='block'}
function hideAddWebAuthn(){var p=document.getElementById('add-webauthn-panel');if(p)p.style.display='none';var s=document.getElementById('settings-webauthn-status');if(s)s.textContent='';var n=document.getElementById('settings-webauthn-name');if(n)n.value='';}

async function registerWebAuthn(){
    var statusEl=document.getElementById('settings-webauthn-status');
    var nameEl=document.getElementById('settings-webauthn-name');
    var customName = (nameEl && nameEl.value.trim()) || 'Passkey';
    if(statusEl)statusEl.textContent='Preparing...';
    setLoading(document.getElementById('settings-webauthn-register'),true);
    try{
        var br=await fetch('/api/settings/2fa/webauthn/register-begin',{method:'POST',credentials:'same-origin'});
        var bd;
        try {
            var ct = br.headers.get('content-type') || '';
            if (ct.indexOf('application/json') !== -1) bd = await br.json();
            else bd = { error: await br.text() };
        } catch (err) { bd = { error: 'Failed to parse server response.' }; }
        if(!br.ok){showToast(bd.error,'error');if(statusEl)statusEl.textContent='';setLoading(document.getElementById('settings-webauthn-register'),false);return}
        var options=bd.options;
        options.challenge=Uint8Array.from(atob(options.challenge.replace(/-/g,'+').replace(/_/g,'/')),function(c){return c.charCodeAt(0)});
        options.user.id=Uint8Array.from(atob(options.user.id.replace(/-/g,'+').replace(/_/g,'/')),function(c){return c.charCodeAt(0)});
        if(statusEl)statusEl.textContent='Follow browser prompt...';
        var credential=await navigator.credentials.create({publicKey:options});
        var credData={id:ab2b64(credential.rawId),rawId:ab2b64(credential.rawId),
            response:{attestationObject:ab2b64(credential.response.attestationObject),clientDataJSON:ab2b64(credential.response.clientDataJSON)},type:credential.type};
        var vr=await fetch('/api/settings/2fa/webauthn/register-verify',{method:'POST',headers:{'Content-Type':'application/json'},credentials:'same-origin',body:JSON.stringify({credential:credData, name:customName})});var vd=await vr.json();
        if(vr.ok){showToast('Passkey added!','success');hideAddWebAuthn();load2FAMethods()}else{showToast(vd.error,'error');if(statusEl)statusEl.textContent=''}
    }catch(e){if(statusEl)statusEl.textContent='';if(e.name!=='NotAllowedError')showToast('Error: '+e.message,'error')}
    finally{setLoading(document.getElementById('settings-webauthn-register'),false)}
}

function ab2b64(buf){var bytes=new Uint8Array(buf),bin='';for(var i=0;i<bytes.byteLength;i++)bin+=String.fromCharCode(bytes[i]);return btoa(bin).replace(/\+/g,'-').replace(/\//g,'_').replace(/=+$/,'')}

// ─── Dir Stat ──────────────────────────────────────────────────
async function loadDirStat(){
    var card=document.getElementById('dirstat-card');if(!card)return;
    try{var r=await apiGet('/api/files/dirstat');var d=await r.json();
        if(r.ok){card.innerHTML='<div class="dirstat-grid"><div class="dirstat-item"><div class="dirstat-value">'+d.total_files+'</div><div class="dirstat-label">Files</div></div><div class="dirstat-item"><div class="dirstat-value">'+d.total_dirs+'</div><div class="dirstat-label">Folders</div></div><div class="dirstat-item"><div class="dirstat-value">'+d.total_size_display+'</div><div class="dirstat-label">Total</div></div><div class="dirstat-item"><div class="dirstat-value">'+d.permissions+'</div><div class="dirstat-label">Perms</div></div></div><div style="margin-top:0.75rem;font-size:0.8rem;color:var(--text-muted)">Owner: '+d.owner+' | Path: '+d.path+'</div>'}
        else card.innerHTML='<div class="loading-placeholder"><i class="fa-solid fa-triangle-exclamation"></i> Failed</div>'
    }catch(e){card.innerHTML='<div class="loading-placeholder"><i class="fa-solid fa-triangle-exclamation"></i> Failed</div>'}
}

init();
})();
