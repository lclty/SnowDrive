/**
 * SnowDrive - Settings Page JavaScript
 */
(function(){'use strict';
function init(){
    loadProfile();load2FAMethods();loadDirStat();
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
    b=document.getElementById('settings-totp-code');if(b)b.addEventListener('input',function(){this.value=this.value.replace(/[^0-9]/g,'').slice(0,6)});
    b=document.getElementById('delete-verify-code');if(b)b.addEventListener('input',function(){this.value=this.value.replace(/[^0-9]/g,'').slice(0,6)});
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
        if(!r.ok)return;var list=document.getElementById('2fa-methods-list');if(!list)return;list.innerHTML='';
        if(d.methods.length===0){list.innerHTML='<p style="color:var(--text-muted);">No 2FA methods configured.</p>';return}
        d.methods.forEach(function(m){
            var icon=m.type==='totp'?'fa-mobile-screen-button':'fa-fingerprint';
            var label=m.type==='totp'?'Authenticator':'Passkey';
            var div=document.createElement('div');div.className='twofa-method-item';
            div.innerHTML='<div class="twofa-method-info"><i class="fa-solid '+icon+'"></i><div><div class="twofa-method-name">'+escapeHtml(m.name)+'</div><div class="twofa-method-type">'+label+'</div></div></div>'+
                '<button class="btn btn-danger btn-sm delete-2fa-btn" data-id="'+m.id+'"><i class="fa-solid fa-trash"></i></button>';
            list.appendChild(div)
        });
        document.querySelectorAll('.delete-2fa-btn').forEach(function(b){b.addEventListener('click',function(){
            document.getElementById('delete-method-id').value=this.dataset.id;load2FAVerifyMethods(parseInt(this.dataset.id));openModal('modal-delete-2fa')
        })})
    }catch(e){}
}

async function load2FAVerifyMethods(excludeId){
    try{var r=await apiGet('/api/settings/2fa/methods');var d=await r.json();
        var sel=document.getElementById('delete-verify-method');if(!sel)return;sel.innerHTML='';
        d.methods.forEach(function(m){if(m.id!==excludeId&&m.type==='totp'){var o=document.createElement('option');o.value=m.id;o.textContent=m.name+' (Authenticator)';sel.appendChild(o)}});
        if(sel.children.length===0)sel.innerHTML='<option value="">No other TOTP method available</option>'
    }catch(e){}
}

async function confirmDelete2FA(){
    var mid=document.getElementById('delete-method-id').value,pw=document.getElementById('delete-verify-password').value,
        vmid=document.getElementById('delete-verify-method').value,vc=document.getElementById('delete-verify-code').value;
    if(!pw||!vmid||!vc){showToast('Fill all fields','error');return}
    setLoading(document.getElementById('confirm-delete-2fa'),true);
    try{var r=await apiPost('/api/settings/2fa/delete',{method_id:parseInt(mid),password:pw,verify_method_id:parseInt(vmid),verify_code:vc});var d=await r.json();
        if(r.ok){showToast('Deleted','success');closeModal('modal-delete-2fa');load2FAMethods()}else showToast(d.error,'error')
    }catch(e){}finally{setLoading(document.getElementById('confirm-delete-2fa'),false)}
}

// ─── Add TOTP ────────────────────────────────────────────────────
function showAddTOTP(){var p=document.getElementById('add-totp-panel');if(p)p.style.display='block'}
function hideAddTOTP(){var p=document.getElementById('add-totp-panel');if(p)p.style.display='none';resetTOTPPanel()}
function resetTOTPPanel(){
    var q=document.getElementById('settings-totp-qr'),ph=document.getElementById('settings-totp-placeholder'),
        sd=document.getElementById('settings-totp-secret-display'),g=document.getElementById('settings-totp-generate'),
        v=document.getElementById('settings-totp-verify'),c=document.getElementById('settings-totp-code');
    if(q)q.style.display='none';if(ph)ph.style.display='flex';if(sd)sd.style.display='none';
    if(g)g.style.display='inline-block';if(v)v.style.display='none';if(c)c.value=''
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
    if(code.length!==6){showToast('Enter 6-digit code','error');return}
    setLoading(document.getElementById('settings-totp-confirm'),true);
    try{var r=await apiPost('/api/settings/2fa/totp/verify',{code:code});var d=await r.json();
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
function hideAddWebAuthn(){var p=document.getElementById('add-webauthn-panel');if(p)p.style.display='none';var s=document.getElementById('settings-webauthn-status');if(s)s.textContent=''}

async function registerWebAuthn(){
    var statusEl=document.getElementById('settings-webauthn-status');
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
        var vr=await fetch('/api/settings/2fa/webauthn/register-verify',{method:'POST',headers:{'Content-Type':'application/json'},credentials:'same-origin',body:JSON.stringify({credential:credData})});var vd=await vr.json();
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
