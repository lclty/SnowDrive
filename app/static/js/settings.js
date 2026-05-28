/**
 * SnowDrive - Settings Page JavaScript (Demo Mode - Cookie-based)
 */
(function(){'use strict';

function init(){
    loadSiteSettings();
    loadDirStat();
    var saveSiteBtn = document.getElementById('save-site-settings');
    if (saveSiteBtn) saveSiteBtn.addEventListener('click', saveSiteSettings);
}

async function loadSiteSettings(){
    try{
        var r = await apiGet('/api/settings/site');
        var d = await r.json();
        if (!r.ok) return;
        if (d.site_title) document.getElementById('site-title-input').value = d.site_title;
        if (d.icp_enabled) { document.getElementById('icp-enabled').checked = true; document.getElementById('icp-number').value = d.icp_number || ''; }
    }catch(e){}
}

async function saveSiteSettings(){
    var title = document.getElementById('site-title-input').value.trim();
    var icp_enabled = !!document.getElementById('icp-enabled').checked;
    var icp_number = document.getElementById('icp-number').value.trim();
    try{
        var r = await apiPost('/api/settings/site', { site_title: title, icp_enabled: icp_enabled, icp_number: icp_number });
        var d = await r.json();
        if (r.ok){ showToast('保存成功（Cookie）','success'); } else showToast(d.error||'保存失败','error');
    }catch(e){ showToast('Error','error') }
}

// ─── Dir Stat ──────────────────────────────────────────────────
async function loadDirStat(){
    var card = document.getElementById('dirstat-card');
    if(!card) return;
    try{
        var r = await apiGet('/api/files/dirstat');
        var d = await r.json();
        if(r.ok){
            card.innerHTML = '<div class="dirstat-grid"><div class="dirstat-item"><div class="dirstat-value">'+d.total_files+'</div><div class="dirstat-label">文件</div></div><div class="dirstat-item"><div class="dirstat-value">'+d.total_dirs+'</div><div class="dirstat-label">文件夹</div></div><div class="dirstat-item"><div class="dirstat-value">'+d.total_size_display+'</div><div class="dirstat-label">总计</div></div></div><div style="margin-top:0.75rem;font-size:0.8rem;color:var(--text-muted)">演示虚拟文件系统 | Cookie 存储</div>';
        } else card.innerHTML = '<div class="loading-placeholder"><i class="fa-solid fa-triangle-exclamation"></i> 加载失败</div>';
    }catch(e){ card.innerHTML = '<div class="loading-placeholder"><i class="fa-solid fa-triangle-exclamation"></i> 加载失败</div>'; }
}

init();
})();
