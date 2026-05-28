/**
 * SnowDrive - File Manager JavaScript
 */

(function() {
    'use strict';

    // ─── State ────────────────────────────────────────────────────
    let currentPath = '';
    let currentSort = 'name';
    let currentOrder = 'asc';
    let currentView = 'list';
    let selectedFiles = new Set();
    let filesData = [];
    // Upload tasks (client-side tracked)
    let uploadTasks = [];
    let _upload_workers = {}; // id -> {xhr, filename}

    // ─── DOM References ────────────────────────────────────────────
    const fileList = document.getElementById('file-list');
    const breadcrumbs = document.getElementById('breadcrumbs');
    const loadingIndicator = document.getElementById('loading-indicator');
    const emptyState = document.getElementById('empty-state');
    const errorState = document.getElementById('error-state');
    const errorStateMsg = document.getElementById('error-state-message');
    const fileCountInfo = document.getElementById('file-count-info');
    const selectionInfo = document.getElementById('selection-info');
    const searchInput = document.getElementById('search-input');
    const sortSelect = document.getElementById('sort-select');
    const sortOrderBtn = document.getElementById('sort-order-btn');
    const dropOverlay = document.getElementById('drop-overlay');
    const fileInput = document.getElementById('file-input');
    const folderInput = document.getElementById('folder-input');

    // ─── Initialize ───────────────────────────────────────────────
    function init() {
        // Load initial files
        loadFiles();

        // Event listeners
        document.getElementById('btn-new-folder').addEventListener('click', () => openModal('modal-new-folder'));
        document.getElementById('btn-new-file').addEventListener('click', () => openModal('modal-new-file'));
        document.getElementById('btn-upload').addEventListener('click', () => fileInput.click());
        document.getElementById('btn-remote-download').addEventListener('click', () => openModal('modal-remote-download'));
        document.getElementById('btn-download-selected').addEventListener('click', downloadSelected);
        var zipBtn = document.getElementById('btn-zip-selected');
        if (zipBtn) zipBtn.addEventListener('click', zipDownloadSelected);
        document.getElementById('btn-delete-selected').addEventListener('click', () => {
            updateDeleteMessage();
            openModal('modal-delete');
        });

        // Confirm buttons
        document.getElementById('confirm-new-folder').addEventListener('click', createFolder);
        document.getElementById('confirm-new-file').addEventListener('click', createFile);
        document.getElementById('confirm-rename').addEventListener('click', confirmRename);
        document.getElementById('confirm-delete').addEventListener('click', confirmDelete);
        document.getElementById('confirm-remote-download').addEventListener('click', remoteDownload);

        // Select toggle button (toolbar) — toggles between select all and deselect all
        const selectToggleBtn = document.getElementById('btn-select-toggle');
        if (selectToggleBtn) {
            selectToggleBtn.addEventListener('click', () => {
                selectAll();
            });
        }

        // Enter key in modals
        document.getElementById('new-folder-name').addEventListener('keydown', e => { if (e.key === 'Enter') createFolder(); });
        document.getElementById('new-file-name').addEventListener('keydown', e => { if (e.key === 'Enter') createFile(); });
        document.getElementById('rename-input').addEventListener('keydown', e => { if (e.key === 'Enter') confirmRename(); });
        document.getElementById('remote-url').addEventListener('keydown', e => { if (e.key === 'Enter') remoteDownload(); });

        // File input
        fileInput.addEventListener('change', handleFileUpload);
        folderInput.addEventListener('change', handleFileUpload);

        // Sort
        sortSelect.addEventListener('change', () => {
            currentSort = sortSelect.value;
            loadFiles();
        });
        sortOrderBtn.addEventListener('click', () => {
            currentOrder = currentOrder === 'asc' ? 'desc' : 'asc';
            updateSortOrderIcon();
            loadFiles();
        });

        // Search
        searchInput.addEventListener('input', debounce(() => {
            loadFiles();
        }, 300));

        // View toggle
        document.querySelectorAll('.view-btn').forEach(btn => {
            btn.addEventListener('click', function() {
                document.querySelectorAll('.view-btn').forEach(b => b.classList.remove('active'));
                this.classList.add('active');
                currentView = this.dataset.view;
                fileList.className = 'file-list ' + (currentView === 'grid' ? 'grid-view' : 'list-view');
                localStorage.setItem('snowdrive-view', currentView);
                renderFiles();
            });
        });

        // Restore view preference
        const savedView = localStorage.getItem('snowdrive-view') || 'list';
        currentView = savedView;
        fileList.className = 'file-list ' + (savedView === 'grid' ? 'grid-view' : 'list-view');
        document.querySelectorAll('.view-btn').forEach(b => {
            b.classList.toggle('active', b.dataset.view === savedView);
        });

        // Drag and drop
        setupDragAndDrop();

        // Download manager toggle and controls
        let dmRefreshInterval = null;
        const dmToggle = document.getElementById('download-manager-toggle');
        if (dmToggle) {
            dmToggle.addEventListener('click', async () => {
                const dmw = document.getElementById('download-mini-window');
                if (!dmw) return;
                const opened = dmw.classList.toggle('open');
                dmw.classList.remove('minimized');
                if (opened) {
                    // default to uploads tab
                    activateDmwTab('uploads');
                    renderUploadTasks();
                    await loadDownloadTasks();
                    // start periodic refresh for downloads
                    if (dmRefreshInterval) clearInterval(dmRefreshInterval);
                    dmRefreshInterval = setInterval(loadDownloadTasks, 2000);
                } else {
                    if (dmRefreshInterval) { clearInterval(dmRefreshInterval); dmRefreshInterval = null; }
                }
            });
        }

        const dmwMin = document.getElementById('dmw-minimize');
        if (dmwMin) dmwMin.addEventListener('click', () => {
            const dmw = document.getElementById('download-mini-window');
            if (dmw) dmw.classList.toggle('minimized');
        });

        const dmwClose = document.getElementById('dmw-close');
        if (dmwClose) dmwClose.addEventListener('click', () => {
            const dmw = document.getElementById('download-mini-window');
            if (dmw) dmw.classList.remove('open');
        });

        // Tabs inside DMW
        document.addEventListener('click', function(e) {
            const tab = e.target.closest('.dmw-tab');
            if (!tab) return;
            const which = tab.dataset.tab;
            activateDmwTab(which);
            // ensure panel content is refreshed when switching
            if (which === 'uploads') renderUploadTasks();
            if (which === 'downloads') loadDownloadTasks();
        });

        // Keyboard shortcuts
        document.addEventListener('keydown', handleKeyboard);

        // Select all with Ctrl+A
        document.addEventListener('keydown', function(e) {
            if ((e.ctrlKey || e.metaKey) && e.key === 'a') {
                // Only if not in an input
                if (document.activeElement === document.body || document.activeElement === fileList) {
                    e.preventDefault();
                    selectAll();
                }
            }
        });

        // Auto-refresh files list (silent) to reflect external changes
        try {
            const filesAutoRefreshInterval = setInterval(() => { loadFiles(true); }, 3000);
            // Clear on unload
            window.addEventListener('beforeunload', () => clearInterval(filesAutoRefreshInterval));
        } catch (e) { /* ignore */ }
    }

    // ─── Load Files ───────────────────────────────────────────────
    async function loadFiles(silent = false) {
        if (!silent) {
            showLoading(true);
            hideError();
            hideEmpty();
        }

        const params = new URLSearchParams({
            path: currentPath,
            sort: currentSort,
            order: currentOrder,
        });
        const search = searchInput.value.trim();
        if (search) params.set('search', search);

        try {
            const resp = await apiGet('/api/files/list?' + params.toString());
            const data = await resp.json();

            if (!resp.ok) {
                showError(data.error || 'Load failed (HTTP ' + resp.status + ')');
                return;
            }

            filesData = data.files;
            selectedFiles.clear();
            updateSelectionUI();
            renderBreadcrumbs(data.breadcrumbs);
            renderFiles();
            updateInfoBar(data);

            if (filesData.length === 0) {
                showEmpty();
            }

            // Update storage info
            updateStorageInfo();

        } catch (err) {
            if (err.message !== 'Authentication required') {
                if (!silent) showError('Error: ' + (err.message || 'Failed to load'));
            }
        } finally {
            if (!silent) showLoading(false);
        }
    }

    // ─── Render ───────────────────────────────────────────────────
    function renderFiles() {
        fileList.innerHTML = '';

        filesData.forEach((file, index) => {
            const item = createFileItem(file, index);
            fileList.appendChild(item);
        });
    }

    function createFileItem(file, index) {
        const div = document.createElement('div');
        div.className = 'file-item';
        div.dataset.index = index;
        div.dataset.path = file.path;
        div.dataset.isDir = file.is_dir;

        if (selectedFiles.has(file.path)) {
            div.classList.add('selected');
        }

        // Select checkbox
        const checkbox = document.createElement('div');
        checkbox.className = 'select-checkbox';
        checkbox.innerHTML = '<i class="fa-solid fa-check"></i>';
        checkbox.addEventListener('click', (e) => {
            e.stopPropagation();
            toggleSelect(file.path);
        });

        // File icon
        const icon = document.createElement('div');
        icon.className = `file-icon fa-solid ${file.icon}`;

        // File info
        const info = document.createElement('div');
        info.className = 'file-info';

        const nameEl = document.createElement('span');
        nameEl.className = 'file-name';
        nameEl.textContent = file.name;
        nameEl.title = file.name;

        const meta = document.createElement('span');
        meta.className = 'file-meta';
        meta.innerHTML = `
            <span>${file.modified_display}</span>
            <span>${file.is_dir ? '文件夹' : file.file_type}</span>
            ${!file.is_dir ? `<span>${file.size_display}</span>` : ''}
        `;

        const metaMobile = document.createElement('span');
        metaMobile.className = 'file-meta-mobile';
        metaMobile.textContent = file.is_dir ? '文件夹' : `${file.size_display} · ${file.file_type}`;

        info.appendChild(nameEl);
        info.appendChild(meta);
        info.appendChild(metaMobile);

        // Actions
        const actions = document.createElement('div');
        actions.className = 'file-actions';

        if (file.is_dir) {
            // Open folder button
            const openBtn = document.createElement('button');
            openBtn.className = 'btn-icon';
            openBtn.title = '打开';
            openBtn.innerHTML = '<i class="fa-solid fa-folder-open"></i>';
            openBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                navigateTo(file.path);
            });
            actions.appendChild(openBtn);
        } else {
            // Download button
            const dlBtn = document.createElement('button');
            dlBtn.className = 'btn-icon';
            dlBtn.title = '下载';
            dlBtn.innerHTML = '<i class="fa-solid fa-download"></i>';
            dlBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                downloadFile(file.path);
            });
            actions.appendChild(dlBtn);
        }

        // Rename button
        const renameBtn = document.createElement('button');
        renameBtn.className = 'btn-icon';
        renameBtn.title = '重命名';
        renameBtn.innerHTML = '<i class="fa-solid fa-pen-to-square"></i>';
        renameBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            openRenameModal(file.path, file.name);
        });
        actions.appendChild(renameBtn);

        // Delete button
        const deleteBtn = document.createElement('button');
        deleteBtn.className = 'btn-icon';
        deleteBtn.title = '删除';
        deleteBtn.innerHTML = '<i class="fa-solid fa-trash"></i>';
        deleteBtn.style.color = 'var(--danger)';
        deleteBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            selectedFiles.clear();
            selectedFiles.add(file.path);
            updateSelectionUI();
            updateDeleteMessage();
            openModal('modal-delete');
        });
        actions.appendChild(deleteBtn);

        div.appendChild(checkbox);
        div.appendChild(icon);
        div.appendChild(info);
        div.appendChild(actions);

        // Grid view: small rename button shown under item when selected
        const gridRenameBtn = document.createElement('button');
        gridRenameBtn.className = 'btn btn-sm grid-rename-btn';
        gridRenameBtn.innerHTML = '<i class="fa-solid fa-pen-to-square"></i>';
        gridRenameBtn.title = '重命名';
        gridRenameBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            openRenameModal(file.path, file.name);
        });
        if (selectedFiles.has(file.path)) gridRenameBtn.style.display = 'inline-flex';
        div.appendChild(gridRenameBtn);

        // Click to open folder or download file
        div.addEventListener('click', (e) => {
            // Grid view: single click selects (clear other selection), ctrl/cmd+click toggles
            if (currentView === 'grid') {
                if (e.ctrlKey || e.metaKey) {
                    e.stopPropagation();
                    toggleSelect(file.path);
                    return;
                }
                // single select this item
                if (!selectedFiles.has(file.path) || selectedFiles.size !== 1) {
                    selectedFiles.clear();
                    selectedFiles.add(file.path);
                    updateSelectionUI();
                    renderFiles();
                }
                return;
            }

            // List view: existing behavior
            if (e.ctrlKey || e.metaKey) {
                e.preventDefault();
                toggleSelect(file.path);
                return;
            }
            if (file.is_dir) {
                navigateTo(file.path);
            } else {
                downloadFile(file.path);
            }
        });

        // Double click opens folder or downloads file (both views)
        div.addEventListener('dblclick', (e) => {
            e.stopPropagation();
            if (file.is_dir) navigateTo(file.path);
            else downloadFile(file.path);
        });

        // Right-click context menu
        div.addEventListener('contextmenu', (e) => {
            e.preventDefault();
            if (!selectedFiles.has(file.path)) {
                selectedFiles.clear();
                selectedFiles.add(file.path);
                updateSelectionUI();
            }
            // Simple context menu via existing buttons
        });

        return div;
    }

    function renderBreadcrumbs(bcData) {
        breadcrumbs.innerHTML = '';
        bcData.forEach((item, i) => {
            if (i > 0) {
                const sep = document.createElement('span');
                sep.className = 'breadcrumb-sep';
                sep.textContent = '/';
                breadcrumbs.appendChild(sep);
            }
            const span = document.createElement('span');
            span.className = 'breadcrumb-item' + (i === bcData.length - 1 ? ' active' : '');
            // Show friendly root label
            if ((item.name === '/' || item.path === '') && i === 0) span.textContent = '根目录';
            else span.textContent = item.name;
            span.addEventListener('click', () => navigateTo(item.path));
            breadcrumbs.appendChild(span);
        });
    }

    function updateInfoBar(data) {
        const dirs = data.dir_count;
        const files = data.file_count;
        const parts = [];
        if (dirs > 0) parts.push(`${dirs} 个文件夹`);
        if (files > 0) parts.push(`${files} 个文件`);
        fileCountInfo.textContent = parts.length > 0 ? parts.join('，') : '空文件夹';
    }

    function updateSortOrderIcon() {
        const icon = sortOrderBtn.querySelector('i');
        if (currentOrder === 'asc') {
            icon.className = currentSort === 'name' ? 'fa-solid fa-arrow-down-a-z' :
                           currentSort === 'size' ? 'fa-solid fa-arrow-down-1-9' :
                           'fa-solid fa-arrow-down-wide-short';
        } else {
            icon.className = currentSort === 'name' ? 'fa-solid fa-arrow-up-z-a' :
                           currentSort === 'size' ? 'fa-solid fa-arrow-up-9-1' :
                           'fa-solid fa-arrow-up-wide-short';
        }
    }

    async function updateStorageInfo() {
        try {
            const resp = await apiGet('/api/files/dirstat');
            const data = await resp.json();
            if (resp.ok) {
                const storageEl = document.getElementById('storage-info');
                if (storageEl) {
                    storageEl.querySelector('span').textContent = `${data.total_files} 文件 · ${data.total_size_display}`;
                }
            }
        } catch (e) {
            // ignore
        }
    }

    // ─── Download Manager ─────────────────────────────────────
    async function loadDownloadTasks() {
        try {
            const resp = await apiGet('/api/files/download-tasks');
            const data = await resp.json();
            if (!resp.ok) return;
            const list = document.getElementById('dmw-list');
            const dlCountEl = document.getElementById('dmw-downloads-count');
            if (dlCountEl) {
                dlCountEl.textContent = (data.tasks || []).length;
                dlCountEl.style.display = (data.tasks && data.tasks.length) ? 'inline-block' : 'none';
            }
            if (!list) return;
            list.innerHTML = '';
            if (!data.tasks || data.tasks.length === 0) {
                list.innerHTML = '<p class="dmw-empty">暂无下载任务</p>';
                const badge0 = document.getElementById('dm-badge'); if (badge0) badge0.style.display = 'none';
                if (dlCountEl) dlCountEl.style.display = 'none';
                return;
            }
            data.tasks.forEach(task => {
                const item = document.createElement('div');
                item.className = 'dmw-item';
                const downloaded = task.downloaded || 0;
                const total = task.total_size || 0;
                const progress = total > 0 ? Math.floor((downloaded / total) * 100) : 0;
                const name = escapeHtml(task.filename || 'download');
                const status = escapeHtml(task.status || '');
                const err = task.error_message ? ' — ' + escapeHtml(task.error_message) : '';

                item.innerHTML = `
                    <div class="dmw-item-name"><strong>${name}</strong><div class="dmw-item-status">${status}${err}</div></div>
                    <div class="progress-bar-container"><div class="progress-bar" style="width:${progress}%"></div></div>
                    <div class="dmw-actions"><button class="btn btn-icon dmw-remove" data-id="${task.id}" title="删除"><i class="fa-solid fa-trash"></i></button></div>
                `;

                // show textual progress when total unknown
                if (total === 0) {
                    const pbar = item.querySelector('.progress-bar');
                    if (pbar) pbar.style.background = 'linear-gradient(90deg, var(--accent), var(--accent-light))';
                    const statusEl = item.querySelector('.dmw-item-status');
                    if (statusEl) statusEl.textContent = status + (downloaded ? ` — ${formatFileSize(downloaded)}` : '');
                }

                list.appendChild(item);
            });

            // hook up delete buttons
            list.querySelectorAll('.dmw-remove').forEach(btn => {
                btn.addEventListener('click', async () => {
                    const id = btn.dataset.id;
                    try {
                        const r = await apiDelete('/api/files/download-task/' + id);
                        if (r.ok) {
                            btn.closest('.dmw-item').remove();
                            showToast('任务已删除', 'success');
                        } else {
                            const d = await r.json();
                            showToast(d.error || '删除失败', 'error');
                        }
                    } catch (e) {
                        // ignore
                    }
                });
            });

            const activeDownloads = data.tasks.some(t => t.status !== 'completed' && t.status !== 'failed');
            const activeUploads = uploadTasks.some(t => t.status !== 'completed' && t.status !== 'failed');
            const badge = document.getElementById('dm-badge'); if (badge) badge.style.display = (activeDownloads || activeUploads) ? 'inline-block' : 'none';
        } catch (e) {
            // ignore
        }
    }

    // ─── Navigation ───────────────────────────────────────────────
    function navigateTo(path) {
        currentPath = path;
        searchInput.value = '';
        loadFiles();
    }

    // ─── Selection ────────────────────────────────────────────────
    function toggleSelect(path) {
        if (selectedFiles.has(path)) {
            selectedFiles.delete(path);
        } else {
            selectedFiles.add(path);
        }
        updateSelectionUI();
        renderFiles();
    }

    function selectAll() {
        if (selectedFiles.size === filesData.length) {
            selectedFiles.clear();
        } else {
            filesData.forEach(f => selectedFiles.add(f.path));
        }
        updateSelectionUI();
        renderFiles();
    }

    function updateSelectionUI() {
        const count = selectedFiles.size;
        const selInfo = document.getElementById('selection-info');
        const dlBtn = document.getElementById('btn-download-selected');
        const zipBtn = document.getElementById('btn-zip-selected');
        const delBtn = document.getElementById('btn-delete-selected');

        if (count > 0) {
            if (selInfo) { selInfo.style.display = 'inline'; selInfo.textContent = '已选择 ' + count + ' 项'; }
            if (dlBtn) dlBtn.disabled = false;
            if (zipBtn) zipBtn.disabled = false;
            if (delBtn) delBtn.disabled = false;
        } else {
            if (selInfo) selInfo.style.display = 'none';
            if (dlBtn) dlBtn.disabled = true;
            if (zipBtn) zipBtn.disabled = true;
            if (delBtn) delBtn.disabled = true;
        }
        // update select-toggle button label
        updateSelectToggleBtn();
    }

    function updateSelectToggleBtn() {
        const btn = document.getElementById('btn-select-toggle');
        if (!btn) return;
        if (!filesData || filesData.length === 0) {
            btn.disabled = true;
            btn.innerHTML = '<i class="fa-solid fa-square-check"></i> 全选';
            return;
        }
        btn.disabled = false;
        if (selectedFiles.size === filesData.length && filesData.length > 0) {
            btn.innerHTML = '<i class="fa-solid fa-square-xmark"></i> 全不选';
        } else {
            btn.innerHTML = '<i class="fa-solid fa-square-check"></i> 全选';
        }
    }

    // ─── UI State ──────────────────────────────────────────────────
    function showLoading(show) {
        loadingIndicator.style.display = show ? 'flex' : 'none';
        if (show) {
            fileList.innerHTML = '';
            emptyState.style.display = 'none';
            errorState.style.display = 'none';
        }
    }

    function showEmpty() {
        emptyState.style.display = 'flex';
        fileList.innerHTML = '';
    }

    function hideEmpty() {
        emptyState.style.display = 'none';
    }

    function showError(msg) {
        errorState.style.display = 'flex';
        errorStateMsg.textContent = msg;
        fileList.innerHTML = '';
    }

    function hideError() {
        errorState.style.display = 'none';
    }

    // ─── File Operations ──────────────────────────────────────────

    async function createFolder() {
        const name = document.getElementById('new-folder-name').value.trim();
        if (!name) {
            showToast('请输入文件夹名称。', 'error');
            return;
        }

        setLoading(document.getElementById('confirm-new-folder'), true);
        try {
            const resp = await apiPost('/api/files/mkdir', { path: currentPath, name });
            const data = await resp.json();
            if (resp.ok) {
                showToast('文件夹创建成功。', 'success');
                closeModal('modal-new-folder');
                document.getElementById('new-folder-name').value = '';
                loadFiles();
            } else {
                showToast(data.error || '创建失败。', 'error');
            }
        } catch (e) {
            // handled by apiPost
        } finally {
            setLoading(document.getElementById('confirm-new-folder'), false);
        }
    }

    async function createFile() {
        const name = document.getElementById('new-file-name').value.trim();
        if (!name) {
            showToast('请输入文件名。', 'error');
            return;
        }

        setLoading(document.getElementById('confirm-new-file'), true);
        try {
            const resp = await apiPost('/api/files/create-file', { path: currentPath, name, content: '' });
            const data = await resp.json();
            if (resp.ok) {
                showToast('文件创建成功。', 'success');
                closeModal('modal-new-file');
                document.getElementById('new-file-name').value = '';
                loadFiles();
            } else {
                showToast(data.error || '创建失败。', 'error');
            }
        } catch (e) {
            // handled
        } finally {
            setLoading(document.getElementById('confirm-new-file'), false);
        }
    }

    function downloadFile(path) {
        const a = document.createElement('a');
        a.href = `/api/files/download?path=${encodeURIComponent(path)}`;
        a.click();
    }

    function downloadSelected() {
        if (selectedFiles.size === 0) return;
        if (selectedFiles.size === 1) {
            const path = [...selectedFiles][0];
            downloadFile(path);
        } else {
            // Multiple files - use zip
            zipDownloadSelected();
        }
    }

    async function zipDownloadSelected() {
        if (selectedFiles.size === 0) return;

        const paths = [...selectedFiles];
        const zipName = paths.length === 1
            ? paths[0].split('/').pop() + '.zip'
            : 'snowdrive_' + new Date().toISOString().slice(0, 10) + '.zip';

        try {
            const resp = await apiPost('/api/files/download', { paths, zip_name: zipName });
            if (resp.ok) {
                const blob = await resp.blob();
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = zipName;
                a.click();
                URL.revokeObjectURL(url);
                showToast('Download started', 'success');
            } else {
                const data = await resp.json();
                showToast(data.error || 'Failed', 'error');
            }
        } catch (e) {
            // handled
        }
    }

    function openRenameModal(path, currentName) {
        document.getElementById('rename-input').value = currentName;
        document.getElementById('rename-input').dataset.originalPath = path;
        openModal('modal-rename');
    }

    async function confirmRename() {
        const input = document.getElementById('rename-input');
        const newName = input.value.trim();
        const originalPath = input.dataset.originalPath;

        if (!newName) {
            showToast('请输入新名称。', 'error');
            return;
        }

        setLoading(document.getElementById('confirm-rename'), true);
        try {
            const resp = await apiPost('/api/files/rename', { path: originalPath, new_name: newName });
            const data = await resp.json();
            if (resp.ok) {
                showToast('重命名成功。', 'success');
                closeModal('modal-rename');
                loadFiles();
            } else {
                showToast(data.error || '重命名失败。', 'error');
            }
        } catch (e) {
            // handled
        } finally {
            setLoading(document.getElementById('confirm-rename'), false);
        }
    }

    function updateDeleteMessage() {
        const count = selectedFiles.size;
        const msg = document.getElementById('delete-message');
        if (count === 0) {
            msg.textContent = '请先选择要删除的项目。';
        } else if (count === 1) {
            const path = [...selectedFiles][0];
            const name = path.split('/').pop();
            msg.textContent = `确定要删除 "${name}" 吗？此操作不可撤销。`;
        } else {
            msg.textContent = `确定要删除选中的 ${count} 个项目吗？此操作不可撤销。`;
        }
    }

    async function confirmDelete() {
        if (selectedFiles.size === 0) return;

        setLoading(document.getElementById('confirm-delete'), true);
        let successCount = 0;
        let failCount = 0;

        for (const path of selectedFiles) {
            try {
                const resp = await apiPost('/api/files/delete', { path });
                if (resp.ok) successCount++;
                else failCount++;
            } catch (e) {
                failCount++;
            }
        }

        setLoading(document.getElementById('confirm-delete'), false);
        closeModal('modal-delete');
        selectedFiles.clear();
        updateSelectionUI();

        if (failCount === 0) {
            showToast(`成功删除 ${successCount} 个项目。`, 'success');
        } else {
            showToast(`删除完成：${successCount} 成功，${failCount} 失败。`, 'error');
        }
        loadFiles();
    }

    // ─── Upload ────────────────────────────────────────────────────
    function handleFileUpload(e) {
        const files = e.target.files;
        if (!files || files.length === 0) return;

        uploadFiles(files);
        // Reset input
        e.target.value = '';
    }

    async function uploadFiles(files) {
        // Upload each file individually to track per-file progress
        for (const file of files) {
            const taskId = 'u' + Date.now() + '-' + Math.floor(Math.random() * 100000);
            const filename = file.name;
            const task = { id: taskId, filename: filename, uploaded: 0, total_size: file.size || 0, status: 'uploading', error_message: '' };
            uploadTasks.unshift(task);
            renderUploadTasks();

            // Prepare XHR for progress
            try {
                const xhr = new XMLHttpRequest();
                _upload_workers[taskId] = { xhr: xhr, filename: filename };
                xhr.open('POST', '/api/files/upload', true);
                xhr.withCredentials = true;

                xhr.upload.addEventListener('progress', function(e) {
                    if (e.lengthComputable) {
                        task.uploaded = e.loaded;
                        task.total_size = e.total;
                    } else {
                        task.uploaded = e.loaded || task.uploaded;
                    }
                    renderUploadTasks();
                });

                xhr.addEventListener('readystatechange', function() {
                    if (xhr.readyState !== 4) return;
                    delete _upload_workers[taskId];
                    let respJson = null;
                    try { respJson = xhr.responseText ? JSON.parse(xhr.responseText) : null; } catch (e) { respJson = { error: 'Server response parse error' }; }
                    if (xhr.status >= 200 && xhr.status < 300) {
                        task.uploaded = task.total_size || task.uploaded;
                        task.status = 'completed';
                        renderUploadTasks();
                        showToast((respJson && respJson.message) || ('已上传 ' + filename), 'success');
                        // refresh file list and auto-remove task after short delay
                        loadFiles();
                        setTimeout(() => { uploadTasks = uploadTasks.filter(t => t.id !== taskId); renderUploadTasks(); }, 3000);
                    } else {
                        task.status = 'failed';
                        task.error_message = (respJson && respJson.error) || ('HTTP ' + xhr.status);
                        renderUploadTasks();
                        showToast(task.error_message || ('上传失败: ' + filename), 'error');
                    }
                });

                xhr.addEventListener('error', function() {
                    delete _upload_workers[taskId];
                    task.status = 'failed';
                    task.error_message = 'Network error';
                    renderUploadTasks();
                    showToast('Upload error: ' + filename, 'error');
                });

                const fd = new FormData();
                fd.append('path', currentPath);
                fd.append('files', file);
                xhr.send(fd);
            } catch (e) {
                task.status = 'failed';
                task.error_message = e.message || 'Upload error';
                renderUploadTasks();
            }
        }
    }

    // ─── Upload Tasks UI ─────────────────────────────────────────
    function activateDmwTab(which) {
        document.querySelectorAll('.dmw-tab').forEach(t => t.classList.toggle('active', t.dataset.tab === which));
        const up = document.getElementById('dmw-uploads-panel');
        const dl = document.getElementById('dmw-downloads-panel');
        if (up) up.style.display = which === 'uploads' ? 'block' : 'none';
        if (dl) dl.style.display = which === 'downloads' ? 'block' : 'none';
    }

    function renderUploadTasks() {
        const list = document.getElementById('umw-list');
        if (!list) return;
        list.innerHTML = '';
        const upCountEl = document.getElementById('dmw-uploads-count');
        if (upCountEl) {
            upCountEl.textContent = (uploadTasks || []).length;
            upCountEl.style.display = (uploadTasks && uploadTasks.length) ? 'inline-block' : 'none';
        }
        if (!uploadTasks || uploadTasks.length === 0) {
            list.innerHTML = '<p class="umw-empty">暂无上传任务</p>';
            return;
        }
        uploadTasks.forEach(task => {
            const item = document.createElement('div');
            item.className = 'dmw-item';
            const uploaded = task.uploaded || 0;
            const total = task.total_size || 0;
            const progress = total > 0 ? Math.floor((uploaded / total) * 100) : (task.status === 'completed' ? 100 : 0);
            const name = escapeHtml(task.filename || 'upload');
            const status = escapeHtml(task.status || '');
            const err = task.error_message ? ' — ' + escapeHtml(task.error_message) : '';

            item.innerHTML = `
                <div class="dmw-item-name"><strong>${name}</strong><div class="dmw-item-status">${status}${err}</div></div>
                <div class="progress-bar-container"><div class="progress-bar" style="width:${progress}%"></div></div>
                <div class="dmw-actions"><button class="btn btn-icon umw-remove" data-id="${task.id}" title="删除"><i class="fa-solid fa-trash"></i></button></div>
            `;
            if (total === 0) {
                const pbar = item.querySelector('.progress-bar'); if (pbar) pbar.style.background = 'linear-gradient(90deg, var(--accent), var(--accent-light))';
                const statusEl = item.querySelector('.dmw-item-status'); if (statusEl) statusEl.textContent = status + (uploaded ? ` — ${formatFileSize(uploaded)}` : '');
            }
            list.appendChild(item);
        });

        // hook up delete buttons for uploads
        list.querySelectorAll('.umw-remove').forEach(btn => {
            btn.addEventListener('click', async () => {
                const id = btn.dataset.id;
                const task = uploadTasks.find(t => t.id === id);
                if (!task) return;
                // Abort XHR if running
                const worker = _upload_workers[id];
                if (worker && worker.xhr) {
                    try { worker.xhr.abort(); } catch (e) {}
                }
                // Try delete partial file on server (best-effort)
                try {
                    const remotePath = (currentPath ? currentPath + '/' : '') + task.filename;
                    const r = await apiPost('/api/files/delete', { path: remotePath });
                    if (r.ok) showToast('任务已删除', 'success');
                } catch (e) { /* ignore */ }
                // remove from list
                uploadTasks = uploadTasks.filter(t => t.id !== id);
                renderUploadTasks();
            });
        });
    }

    // ─── Remote Download ───────────────────────────────────────────
    async function remoteDownload() {
        const url = document.getElementById('remote-url').value.trim();
        const filename = document.getElementById('remote-filename').value.trim();

        if (!url) {
            showToast('请输入文件 URL。', 'error');
            return;
        }

        setLoading(document.getElementById('confirm-remote-download'), true);
        try {
            const resp = await apiPost('/api/files/remote-download', {
                url,
                path: currentPath,
                filename: filename || undefined,
            });
            const data = await resp.json();
            if (resp.ok) {
                showToast(data.message, 'success');
                closeModal('modal-remote-download');
                document.getElementById('remote-url').value = '';
                document.getElementById('remote-filename').value = '';
                loadFiles();
                try { loadDownloadTasks(); } catch (e) { /* ignore */ }
            } else {
                showToast(data.error || '远程下载失败。', 'error');
            }
        } catch (e) {
            // handled
        } finally {
            setLoading(document.getElementById('confirm-remote-download'), false);
        }
    }

    // ─── Drag & Drop ───────────────────────────────────────────────
    function setupDragAndDrop() {
        let dragCounter = 0;
        if (!dropOverlay) return;

        document.addEventListener('dragenter', (e) => {
            e.preventDefault();
            dragCounter++;
            if (dragCounter === 1) {
                dropOverlay.classList.add('active');
            }
        });

        document.addEventListener('dragleave', (e) => {
            dragCounter--;
            if (dragCounter === 0) {
                dropOverlay.classList.remove('active');
            }
        });

        document.addEventListener('dragover', (e) => {
            e.preventDefault();
        });

        document.addEventListener('drop', (e) => {
            e.preventDefault();
            dragCounter = 0;
            dropOverlay.classList.remove('active');

            const files = e.dataTransfer.files;
            if (files && files.length > 0) {
                uploadFiles(files);
            }
        });
    }

    // ─── Keyboard Shortcuts ────────────────────────────────────────
    function handleKeyboard(e) {
        // Delete key
        if (e.key === 'Delete' && selectedFiles.size > 0) {
            if (document.activeElement === document.body || document.activeElement === fileList) {
                e.preventDefault();
                updateDeleteMessage();
                openModal('modal-delete');
            }
        }
        // F2 for rename
        if (e.key === 'F2' && selectedFiles.size === 1) {
            const path = [...selectedFiles][0];
            const name = path.split('/').pop();
            openRenameModal(path, name);
        }
        // F5 for refresh
        if (e.key === 'F5') {
            e.preventDefault();
            loadFiles();
        }
    }

    // ─── Start ─────────────────────────────────────────────────────
    init();
})();
