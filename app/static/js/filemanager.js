/**
 * SnowDrive - File Manager JavaScript (Demo Mode - Cookie-based VFS)
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

    // ─── Initialize ───────────────────────────────────────────────
    function init() {
        loadFiles();

        // Disabled operation buttons (show toast)
        document.getElementById('btn-new-folder').addEventListener('click', () => {
            showToast('Demo 无法修改服务器内容，请自行部署查看', 'error');
        });
        document.getElementById('btn-new-file').addEventListener('click', () => {
            showToast('Demo 无法修改服务器内容，请自行部署查看', 'error');
        });
        document.getElementById('btn-upload').addEventListener('click', () => {
            showToast('Demo 无法修改服务器内容，请自行部署查看', 'error');
        });
        document.getElementById('btn-remote-download').addEventListener('click', () => {
            showToast('Demo 无法修改服务器内容，请自行部署查看', 'error');
        });
        document.getElementById('btn-download-selected').addEventListener('click', downloadSelected);
        document.getElementById('btn-delete-selected').addEventListener('click', () => {
            updateDeleteMessage();
            openModal('modal-delete');
        });

        // Confirm buttons
        document.getElementById('confirm-rename').addEventListener('click', confirmRename);
        document.getElementById('confirm-delete').addEventListener('click', confirmDelete);

        // Rename input enter key
        document.getElementById('rename-input').addEventListener('keydown', e => { if (e.key === 'Enter') confirmRename(); });

        // Select toggle button
        const selectToggleBtn = document.getElementById('btn-select-toggle');
        if (selectToggleBtn) {
            selectToggleBtn.addEventListener('click', selectAll);
        }

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

        const savedView = localStorage.getItem('snowdrive-view') || 'list';
        currentView = savedView;
        fileList.className = 'file-list ' + (savedView === 'grid' ? 'grid-view' : 'list-view');
        document.querySelectorAll('.view-btn').forEach(b => {
            b.classList.toggle('active', b.dataset.view === savedView);
        });

        // Keyboard shortcuts
        document.addEventListener('keydown', handleKeyboard);

        // Select all with Ctrl+A
        document.addEventListener('keydown', function(e) {
            if ((e.ctrlKey || e.metaKey) && e.key === 'a') {
                if (document.activeElement === document.body || document.activeElement === fileList) {
                    e.preventDefault();
                    selectAll();
                }
            }
        });

        // Disable drag and drop (demo mode)
        document.addEventListener('dragover', (e) => e.preventDefault());
        document.addEventListener('drop', (e) => e.preventDefault());
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
            if (!silent) selectedFiles.clear();
            updateSelectionUI();
            renderBreadcrumbs(data.breadcrumbs);
            renderFiles();
            updateInfoBar(data);

            if (filesData.length === 0) {
                showEmpty();
            }

            updateStorageInfo();
        } catch (err) {
            if (!silent) showError('Error: ' + (err.message || 'Failed to load'));
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

    // ─── Navigation ───────────────────────────────────────────────
    function navigateTo(path) {
        currentPath = path;
        searchInput.value = '';
        loadFiles();
    }

    // ─── Selection ────────────────────────────────────────────────
    function toggleSelect(path) {
        if (selectedFiles.has(path)) selectedFiles.delete(path);
        else selectedFiles.add(path);
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
        const delBtn = document.getElementById('btn-delete-selected');

        if (count > 0) {
            if (selInfo) { selInfo.style.display = 'inline'; selInfo.textContent = '已选择 ' + count + ' 项'; }
            if (dlBtn) dlBtn.disabled = false;
            if (delBtn) delBtn.disabled = false;
        } else {
            if (selInfo) selInfo.style.display = 'none';
            if (dlBtn) dlBtn.disabled = true;
            if (delBtn) delBtn.disabled = true;
        }
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

    function downloadFile(path) {
        const a = document.createElement('a');
        a.href = `/api/files/download?path=${encodeURIComponent(path)}`;
        a.click();
    }

    function downloadSelected() {
        if (selectedFiles.size === 0) return;
        if (selectedFiles.size === 1) {
            downloadFile([...selectedFiles][0]);
        } else {
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
                showToast('下载已开始', 'success');
            } else {
                const data = await resp.json();
                showToast(data.error || '下载失败', 'error');
            }
        } catch (e) { /* ignore */ }
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
        } catch (e) { /* ignore */ }
        finally { setLoading(document.getElementById('confirm-rename'), false); }
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
        const paths = [...selectedFiles];
        if (paths.length === 0) return;

        setLoading(document.getElementById('confirm-delete'), true);
        try {
            const resp = await apiPost('/api/files/delete', { paths });
            const data = await resp.json();
            if (resp.ok) {
                showToast('删除成功。', 'success');
                closeModal('modal-delete');
                selectedFiles.clear();
                loadFiles();
            } else {
                showToast(data.error || '删除失败。', 'error');
            }
        } catch (e) { /* ignore */ }
        finally { setLoading(document.getElementById('confirm-delete'), false); }
    }

    // ─── Keyboard Shortcuts ────────────────────────────────────────
    function handleKeyboard(e) {
        if (e.key === 'Delete' && selectedFiles.size > 0) {
            if (document.activeElement === document.body || document.activeElement === fileList) {
                e.preventDefault();
                updateDeleteMessage();
                openModal('modal-delete');
            }
        }
        if (e.key === 'F2' && selectedFiles.size === 1) {
            const path = [...selectedFiles][0];
            const name = path.split('/').pop();
            openRenameModal(path, name);
        }
        if (e.key === 'F5') {
            e.preventDefault();
            loadFiles();
        }
    }

    // ─── Start ─────────────────────────────────────────────────────
    init();
})();
