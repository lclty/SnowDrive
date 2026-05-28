/**
 * SnowDrive - Common Application JavaScript
 * Provides: Toast notifications, Modal management, Theme toggle, API helpers
 */

// ─── Toast Notifications ──────────────────────────────────────────

function showToast(message, type = 'info', duration = 4000) {
    const container = document.getElementById('toast-container');
    if (!container) return;

    const icons = {
        success: 'fa-circle-check',
        error: 'fa-circle-xmark',
        info: 'fa-circle-info'
    };

    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.innerHTML = `
        <i class="fa-solid ${icons[type] || icons.info}"></i>
        <span>${escapeHtml(message)}</span>
    `;

    container.appendChild(toast);

    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateX(100%)';
        toast.style.transition = 'all 0.3s ease';
        setTimeout(() => toast.remove(), 300);
    }, duration);
}


// ─── Modal Management ─────────────────────────────────────────────

function openModal(modalId) {
    const modal = document.getElementById(modalId);
    if (!modal) return;
    modal.classList.add('active');
    // Focus first input
    const firstInput = modal.querySelector('input[type="text"], input[type="password"], input[type="url"]');
    if (firstInput) setTimeout(() => firstInput.focus(), 100);
}

function closeModal(modalId) {
    const modal = document.getElementById(modalId);
    if (!modal) return;
    modal.classList.remove('active');
}

function closeAllModals() {
    document.querySelectorAll('.modal').forEach(m => m.classList.remove('active'));
}

// Hook up all modal close buttons
document.addEventListener('click', function(e) {
    // Close button
    if (e.target.closest('.modal-close')) {
        const modal = e.target.closest('.modal');
        if (modal) modal.classList.remove('active');
    }
    // Cancel button
    if (e.target.closest('.modal-cancel')) {
        const modal = e.target.closest('.modal');
        if (modal) modal.classList.remove('active');
    }
    // Backdrop click
    if (e.target.classList.contains('modal') && e.target.classList.contains('active')) {
        e.target.classList.remove('active');
    }
});

// Escape key to close modals
document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') {
        const activeModals = document.querySelectorAll('.modal.active');
        if (activeModals.length > 0) {
            activeModals[activeModals.length - 1].classList.remove('active');
        }
    }
});


// ─── Theme Management ─────────────────────────────────────────────

function initTheme() {
    const savedTheme = localStorage.getItem('snowdrive-theme') || 'light';
    document.documentElement.setAttribute('data-theme', savedTheme);
    updateThemeIcon(savedTheme);
}

function toggleTheme() {
    const current = document.documentElement.getAttribute('data-theme');
    const next = current === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', next);
    localStorage.setItem('snowdrive-theme', next);
    updateThemeIcon(next);
}

function updateThemeIcon(theme) {
    const toggles = document.querySelectorAll('#theme-toggle, .theme-toggle-btn, .theme-toggle-btn-inline');
    toggles.forEach(btn => {
        const icon = btn.querySelector('i');
        if (icon) {
            icon.className = theme === 'dark' ? 'fa-solid fa-sun' : 'fa-solid fa-moon';
        }
    });
}

// Hook up theme toggle buttons
document.addEventListener('DOMContentLoaded', () => {
    initTheme();
    document.querySelectorAll('#theme-toggle, .theme-toggle-btn, .theme-toggle-btn-inline').forEach(btn => {
        btn.addEventListener('click', toggleTheme);
    });
});


// ─── Sidebar ──────────────────────────────────────────────────────

function initSidebar() {
    const sidebar = document.getElementById('sidebar');
    if (!sidebar) return;

    const toggleBtn = document.getElementById('sidebar-toggle');
    const mobileToggle = document.getElementById('mobile-sidebar-toggle');

    // Desktop sidebar toggle
    if (toggleBtn) {
        toggleBtn.addEventListener('click', () => {
            sidebar.classList.toggle('collapsed');
            localStorage.setItem('snowdrive-sidebar-collapsed', sidebar.classList.contains('collapsed'));
        });
    }

    // Restore sidebar state
    const savedCollapsed = localStorage.getItem('snowdrive-sidebar-collapsed') === 'true';
    if (savedCollapsed && window.innerWidth > 768) {
        sidebar.classList.add('collapsed');
    }

    // Mobile sidebar
    if (mobileToggle) {
        mobileToggle.addEventListener('click', () => {
            sidebar.classList.toggle('mobile-open');
            toggleSidebarOverlay();
        });
    }

    // Close sidebar when clicking outside on mobile
    document.addEventListener('click', (e) => {
        if (window.innerWidth <= 768 &&
            sidebar.classList.contains('mobile-open') &&
            !sidebar.contains(e.target) &&
            !e.target.closest('#mobile-sidebar-toggle')) {
            sidebar.classList.remove('mobile-open');
            toggleSidebarOverlay();
        }
    });
}

function toggleSidebarOverlay() {
    let overlay = document.querySelector('.sidebar-overlay');
    const sidebar = document.getElementById('sidebar');
    if (!sidebar || !sidebar.classList.contains('mobile-open')) {
        if (overlay) overlay.remove();
        return;
    }
    if (!overlay) {
        overlay = document.createElement('div');
        overlay.className = 'sidebar-overlay active';
        overlay.addEventListener('click', () => {
            sidebar.classList.remove('mobile-open');
            overlay.remove();
        });
        document.body.appendChild(overlay);
    }
}

document.addEventListener('DOMContentLoaded', initSidebar);


// ─── API Helpers ──────────────────────────────────────────────────

async function apiFetch(url, options = {}) {
    try {
        const resp = await fetch(url, {
            credentials: 'same-origin',
            ...options,
            headers: {
                'Content-Type': 'application/json',
                ...options.headers,
            },
        });

        // Handle 401 - redirect to login
        if (resp.status === 401) {
            window.location.href = '/login';
            throw new Error('Authentication required');
        }

        return resp;
    } catch (err) {
        if (err.message === 'Authentication required') throw err;
        showToast('网络连接错误，请检查网络后重试。', 'error');
        throw err;
    }
}

async function apiPost(url, data = {}) {
    return apiFetch(url, {
        method: 'POST',
        body: JSON.stringify(data),
    });
}

async function apiGet(url) {
    return apiFetch(url, { method: 'GET' });
}

async function apiPut(url, data = {}) {
    return apiFetch(url, {
        method: 'PUT',
        body: JSON.stringify(data),
    });
}

async function apiDelete(url) {
    return apiFetch(url, { method: 'DELETE' });
}


// ─── Utility Functions ────────────────────────────────────────────

function escapeHtml(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

function debounce(func, wait) {
    let timeout;
    return function(...args) {
        clearTimeout(timeout);
        timeout = setTimeout(() => func.apply(this, args), wait);
    };
}

function formatFileSize(bytes) {
    if (bytes === 0 || bytes == null) return '—';
    const units = ['B', 'KB', 'MB', 'GB', 'TB'];
    let i = 0;
    let size = bytes;
    while (size >= 1024 && i < units.length - 1) {
        size /= 1024;
        i++;
    }
    return i === 0 ? `${size} B` : `${size.toFixed(1)} ${units[i]}`;
}

function formatDate(isoString) {
    if (!isoString) return '—';
    try {
        const d = new Date(isoString);
        return d.toLocaleString('zh-CN', {
            year: 'numeric',
            month: '2-digit',
            day: '2-digit',
            hour: '2-digit',
            minute: '2-digit',
        });
    } catch {
        return isoString;
    }
}

function setLoading(el, loading) {
    if (!el) return;
    if (loading) {
        el.disabled = true;
        el.dataset.originalHtml = el.innerHTML;
        el.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> 请稍候...';
    } else {
        el.disabled = false;
        if (el.dataset.originalHtml) {
            el.innerHTML = el.dataset.originalHtml;
            delete el.dataset.originalHtml;
        }
    }
}

// ─── Logout ───────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
    const logoutBtn = document.getElementById('logout-btn');
    if (logoutBtn) {
        logoutBtn.addEventListener('click', async () => {
            try {
                await apiPost('/api/auth/logout');
            } catch (e) {
                // ignore
            }
            window.location.href = '/login';
        });
    }
});
