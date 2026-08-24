let currentUser = null;
let productsList = [];
let categoriesList = [];
let branchesList = [];
let usersList = [];
let categoryChart = null;

document.addEventListener('DOMContentLoaded', async () => {
    lucide.createIcons();
    const isAuth = await checkCurrentUser();
    if (isAuth) {
        await loadInitialMetadata();
        loadDashboard();
    }
});

// --- AUTENTICAÇÃO E PORTA-FECHADURA ---

async function checkCurrentUser() {
    try {
        const res = await fetch('/api/me');
        if (res.ok) {
            const data = await res.json();
            if (data.user) {
                currentUser = data.user;
                updateUserRoleUI(currentUser);
                closeModal('modal-lockscreen');
                return true;
            }
        }
    } catch (err) {
        console.error('Erro ao verificar autenticação:', err);
    }
    showLockScreen();
    return false;
}

function showLockScreen() {
    const lockModal = document.getElementById('modal-lockscreen');
    if (lockModal) lockModal.classList.add('active');
}

async function performLogin(e) {
    e.preventDefault();
    const username = document.getElementById('login-username').value.trim();
    const password = document.getElementById('login-password').value.trim();
    const errorBox = document.getElementById('login-error-msg');

    if (errorBox) errorBox.style.display = 'none';

    try {
        const res = await fetch('/api/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password })
        });
        const data = await res.json();

        if (res.ok) {
            currentUser = data.user;
            updateUserRoleUI(currentUser);
            closeModal('modal-lockscreen');
            showToast(`Sessão iniciada como ${currentUser.name}`, 'success');
            await loadInitialMetadata();
            loadDashboard();
        } else {
            if (errorBox) {
                errorBox.textContent = data.error || 'Usuário ou senha incorretos.';
                errorBox.style.display = 'block';
            }
        }
    } catch (err) {
        if (errorBox) {
            errorBox.textContent = 'Erro ao se comunicar com o servidor de autenticação.';
            errorBox.style.display = 'block';
        }
    }
}

function updateUserRoleUI(user) {
    document.getElementById('current-user-name').textContent = user.name || user.username;
    const roleBadge = document.getElementById('current-user-role');
    roleBadge.textContent = user.role;

    roleBadge.className = 'role-badge';
    if (user.role === 'ADMIN') roleBadge.style.background = 'var(--accent-purple)';
    else if (user.role === 'MANAGER') roleBadge.style.background = 'var(--accent-green)';
    else roleBadge.style.background = 'var(--accent-warning)';

    document.body.className = `role-${user.role.toLowerCase()}`;

    lucide.createIcons();
}

async function logout() {
    await fetch('/api/logout', { method: 'POST' });
    currentUser = null;
    const formLogin = document.getElementById('form-login');
    if (formLogin) formLogin.reset();
    showToast('Sessão encerrada. Fechadura de segurança ativada.', 'warning');
    showLockScreen();
}

// --- METADADOS INICIAIS ---

async function loadInitialMetadata() {
    try {
        const [catRes, branchRes] = await Promise.all([
            fetch('/api/categories'),
            fetch('/api/branches')
        ]);

        categoriesList = await catRes.json();
        branchesList = await branchRes.json();

        // Preencher Select de Categorias (Filtro e Modal)
        populateCategoryDropdowns();

        // Preencher Select de Unidades no Modal de Movimentação
        const modalBranchSelect = document.getElementById('mov-branch-id');
        modalBranchSelect.innerHTML = '<option value="">Selecione a Unidade...</option>';
        branchesList.forEach(b => {
            modalBranchSelect.innerHTML += `<option value="${b.id}">${b.name}</option>`;
        });

    } catch (err) {
        console.error('Erro ao carregar metadados:', err);
    }
}

function populateCategoryDropdowns() {
    const filterCatSelect = document.getElementById('filter-category');
    const modalCatSelect = document.getElementById('prod-category');

    filterCatSelect.innerHTML = '<option value="">Todas as Categorias</option>';
    modalCatSelect.innerHTML = '<option value="">Selecione uma categoria...</option>';

    categoriesList.forEach(c => {
        filterCatSelect.innerHTML += `<option value="${c.id}">${c.name}</option>`;
        modalCatSelect.innerHTML += `<option value="${c.id}">${c.name}</option>`;
    });
}

// --- NAVEGAÇÃO DE ABAS ---

function showTab(tabName) {
    document.querySelectorAll('.nav-item').forEach(item => {
        item.classList.toggle('active', item.dataset.tab === tabName);
    });

    document.querySelectorAll('.tab-content').forEach(content => {
        content.classList.toggle('active', content.id === `tab-${tabName}`);
    });

    if (tabName === 'dashboard') loadDashboard();
    else if (tabName === 'products') loadProducts();
    else if (tabName === 'categories') loadCategories();
    else if (tabName === 'movements') loadMovements();
    else if (tabName === 'alerts') loadAlerts();
    else if (tabName === 'branches') loadBranches();
    else if (tabName === 'settings') loadUsers();

    lucide.createIcons();
}

// --- 1. CARREGAR DASHBOARD ---

async function loadDashboard() {
    try {
        const res = await fetch('/api/dashboard/stats');
        const data = await res.json();

        document.getElementById('kpi-total-skus').textContent = data.total_skus;
        document.getElementById('kpi-total-items').textContent = data.total_items;
        document.getElementById('kpi-low-stock').textContent = data.low_stock_count;
        document.getElementById('alert-badge-count').textContent = data.low_stock_count;

        if (currentUser.role !== 'OPERATOR') {
            document.getElementById('kpi-purchase-value').textContent = formatCurrency(data.purchase_valuation);
            document.getElementById('kpi-sale-value').textContent = formatCurrency(data.sale_valuation);
        }

        renderCategoryChart(data.category_stats);
        renderRecentMovements(data.recent_movements);

    } catch (err) {
        console.error('Erro ao carregar estatísticas do dashboard:', err);
    }
}

function renderCategoryChart(stats) {
    const ctx = document.getElementById('chart-categories').getContext('2d');
    if (categoryChart) categoryChart.destroy();

    const labels = stats.map(s => s.name);
    const dataValues = stats.map(s => s.total_stock || 0);

    categoryChart = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: labels,
            datasets: [{
                data: dataValues,
                backgroundColor: ['#3b82f6', '#10b981', '#f59e0b', '#8b5cf6', '#ef4444', '#06b6d4'],
                borderWidth: 2,
                borderColor: '#1e293b'
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'bottom',
                    labels: { color: '#94a3b8', font: { family: 'Plus Jakarta Sans', size: 11 } }
                }
            }
        }
    });
}

function renderRecentMovements(movements) {
    const container = document.getElementById('recent-movements-list');
    if (!movements || movements.length === 0) {
        container.innerHTML = '<p class="text-muted" style="font-size:0.85rem">Nenhuma movimentação registrada.</p>';
        return;
    }

    container.innerHTML = movements.map(m => `
        <div class="activity-item">
            <div class="activity-info">
                <span class="mov-type-badge ${m.type.toLowerCase()}">${m.type}</span>
                <div class="activity-text">
                    <strong>${m.product_name} (${m.quantity} un)</strong>
                    <span>${m.branch_name || 'Estoque Central'} • ${formatDate(m.timestamp)}</span>
                </div>
            </div>
            <span style="font-size:0.75rem; color:var(--text-muted)">${m.user_name}</span>
        </div>
    `).join('');
}

// --- 2. CARREGAR PRODUTOS / ESTOQUE ---

async function loadProducts() {
    const search = document.getElementById('filter-search').value;
    const category_id = document.getElementById('filter-category').value;
    const status = document.getElementById('filter-status').value;

    const url = `/api/products?search=${encodeURIComponent(search)}&category_id=${category_id}&status=${status}`;

    try {
        const res = await fetch(url);
        productsList = await res.json();

        const tbody = document.getElementById('products-table-body');
        if (productsList.length === 0) {
            tbody.innerHTML = '<tr><td colspan="10" class="text-muted" style="text-align:center">Nenhuma peça encontrada. Clique no botão "+ Cadastrar Novo Produto" para adicionar.</td></tr>';
            return;
        }

        tbody.innerHTML = productsList.map(p => {
            let statusPill = `<span class="status-pill ok"><i data-lucide="check-circle-2"></i> OK</span>`;
            if (p.current_stock === 0) {
                statusPill = `<span class="status-pill out"><i data-lucide="x-circle"></i> Esgotado</span>`;
            } else if (p.current_stock <= p.min_stock) {
                statusPill = `<span class="status-pill low"><i data-lucide="alert-circle"></i> Repor</span>`;
            }

            const purchaseStr = p.purchase_price !== null ? formatCurrency(p.purchase_price) : '-';
            const saleStr = p.sale_price !== null ? formatCurrency(p.sale_price) : '-';

            return `
                <tr>
                    <td><strong>${p.code}</strong></td>
                    <td>
                        <div style="font-weight:600">${p.name}</div>
                        <small class="text-muted">Unidade: ${p.unit}</small>
                    </td>
                    <td>${p.category_name}</td>
                    <td><strong style="font-size:1rem">${p.current_stock}</strong> ${p.unit}</td>
                    <td class="text-muted">${p.min_stock} ${p.unit}</td>
                    <td class="manager-only">${purchaseStr}</td>
                    <td class="manager-only">${saleStr}</td>
                    <td><small>${p.location || 'Não definida'}</small></td>
                    <td>${statusPill}</td>
                    <td class="text-right" style="white-space: nowrap;">
                        <button class="btn btn-secondary manager-only" onclick="openProductModal(${p.id})" title="Editar Peça">
                            <i data-lucide="edit-3"></i> Editar
                        </button>
                        <button class="btn btn-primary" onclick="openQuickMovementModal(${p.id}, 'SAIDA')" title="Lançar Saída de Estoque">
                            <i data-lucide="arrow-up-right"></i> Registrar Saída
                        </button>
                    </td>
                </tr>
            `;
        }).join('');

        lucide.createIcons();

    } catch (err) {
        console.error('Erro ao carregar produtos:', err);
    }
}

// --- 3. CARREGAR CATEGORIAS ---

async function loadCategories() {
    try {
        const res = await fetch('/api/categories');
        categoriesList = await res.json();

        const grid = document.getElementById('categories-grid');
        if (categoriesList.length === 0) {
            grid.innerHTML = '<p class="text-muted">Nenhuma categoria cadastrada.</p>';
            return;
        }

        grid.innerHTML = categoriesList.map(c => `
            <div class="category-card">
                <div class="cat-header">
                    <div class="cat-icon"><i data-lucide="${c.icon || 'folder'}"></i></div>
                    <div class="cat-title">
                        <h3>${c.name}</h3>
                        <span>${c.product_count || 0} produtos cadastrados</span>
                    </div>
                </div>
                <div class="cat-body">
                    <p>${c.description || 'Sem descrição'}</p>
                </div>
                <div class="cat-footer" style="display:flex; gap:0.5rem; justify-flex-end; width:100%;">
                    <button class="btn btn-secondary manager-only" onclick="openCategoryModal(${c.id})">
                        <i data-lucide="edit-3"></i> Editar Categoria
                    </button>
                    <button class="btn btn-danger admin-only" onclick="deleteCategory(${c.id})">
                        <i data-lucide="trash-2"></i> Excluir Categoria
                    </button>
                </div>
            </div>
        `).join('');

        lucide.createIcons();

    } catch (err) {
        console.error('Erro ao carregar categorias:', err);
    }
}

// --- 4. CARREGAR MOVIMENTAÇÕES ---

async function loadMovements() {
    try {
        const res = await fetch('/api/movements');
        const movements = await res.json();

        const tbody = document.getElementById('movements-table-body');
        if (movements.length === 0) {
            tbody.innerHTML = '<tr><td colspan="10" class="text-muted" style="text-align:center">Nenhuma movimentação registrada.</td></tr>';
            return;
        }

        tbody.innerHTML = movements.map(m => `
            <tr>
                <td><small>${formatDate(m.timestamp)}</small></td>
                <td><span class="mov-type-badge ${m.type.toLowerCase()}">${m.type}</span></td>
                <td><strong>${m.product_code}</strong></td>
                <td>${m.product_name}</td>
                <td><strong>${m.quantity}</strong> ${m.product_unit || 'un'}</td>
                <td class="manager-only">${m.unit_price !== null ? formatCurrency(m.unit_price) : '-'}</td>
                <td class="manager-only"><strong>${m.total_price !== null ? formatCurrency(m.total_price) : '-'}</strong></td>
                <td>${m.branch_name || 'Estoque Central'}</td>
                <td><small>${m.destination_equipment || m.notes || '-'}</small></td>
                <td><small>${m.user_name}</small></td>
            </tr>
        `).join('');

    } catch (err) {
        console.error('Erro ao carregar movimentações:', err);
    }
}

// --- 5. CARREGAR ALERTAS ---

async function loadAlerts() {
    try {
        const res = await fetch('/api/products?status=low');
        const alertProducts = await res.json();

        const tbody = document.getElementById('alerts-table-body');
        if (alertProducts.length === 0) {
            tbody.innerHTML = '<tr><td colspan="8" class="text-muted" style="text-align:center; padding:2rem">✨ Excelente! Todas as peças estão com saldo acima do estoque mínimo.</td></tr>';
            return;
        }

        tbody.innerHTML = alertProducts.map(p => {
            const diff = p.min_stock - p.current_stock;
            return `
                <tr>
                    <td><strong>${p.code}</strong></td>
                    <td><strong>${p.name}</strong></td>
                    <td>${p.category_name}</td>
                    <td><span style="color:var(--accent-warning); font-weight:800">${p.current_stock}</span> ${p.unit}</td>
                    <td>${p.min_stock} ${p.unit}</td>
                    <td><span class="status-pill low">+${diff > 0 ? diff : 1} para repor</span></td>
                    <td>${p.location || '-'}</td>
                    <td class="text-right">
                        <button class="btn btn-secondary manager-only" onclick="openQuickMovementModal(${p.id}, 'ENTRADA')">
                            <i data-lucide="plus-circle"></i> Repor Estoque
                        </button>
                    </td>
                </tr>
            `;
        }).join('');

        lucide.createIcons();

    } catch (err) {
        console.error('Erro ao carregar alertas:', err);
    }
}

// --- 6. CARREGAR UNIDADES (COM EDIÇÃO E EXCLUSÃO) ---

async function loadBranches() {
    try {
        const res = await fetch('/api/branches');
        branchesList = await res.json();

        const grid = document.getElementById('branches-grid');
        grid.innerHTML = branchesList.map(b => `
            <div class="branch-card">
                <h3>${b.name}</h3>
                <p><i data-lucide="map-pin"></i> ${b.address || 'Endereço não informado'}</p>
                <p><i data-lucide="phone"></i> ${b.phone || 'Telefone não informado'}</p>
                
                <div class="branch-actions admin-only" style="display:flex; gap:0.5rem; justify-content:flex-end;">
                    <button class="btn btn-secondary" onclick="openBranchModal(${b.id})">
                        <i data-lucide="edit-3"></i> Editar Unidade
                    </button>
                    <button class="btn btn-danger" onclick="deleteBranch(${b.id})">
                        <i data-lucide="trash-2"></i> Excluir Unidade
                    </button>
                </div>
            </div>
        `).join('');

        lucide.createIcons();

    } catch (err) {
        console.error('Erro ao carregar unidades:', err);
    }
}

async function deleteBranch(branchId) {
    if (!confirm('Deseja realmente excluir esta unidade da academia?')) return;

    try {
        const res = await fetch(`/api/branches/${branchId}`, { method: 'DELETE' });
        const data = await res.json();
        if (res.ok) {
            showToast(data.message, 'success');
            loadBranches();
            loadInitialMetadata();
        } else {
            showToast(data.error, 'error');
        }
    } catch (err) {
        showToast('Erro ao excluir unidade', 'error');
    }
}

// --- 7. CARREGAR USUÁRIOS & PERMISSÕES (ADMIN ONLY) ---

async function loadUsers() {
    if (currentUser.role !== 'ADMIN') return;

    try {
        const res = await fetch('/api/users');
        usersList = await res.json();

        const tbody = document.getElementById('users-table-body');
        tbody.innerHTML = usersList.map(u => {
            const isSelf = u.id === currentUser.id;
            const statusBadge = u.active ? '<span class="status-pill ok">Ativo</span>' : '<span class="status-pill out">Inativo</span>';
            
            return `
                <tr>
                    <td>#${u.id}</td>
                    <td><strong>${u.name}</strong></td>
                    <td><code>${u.username}</code></td>
                    <td>${u.email || '-'}</td>
                    <td><span class="role-badge" style="background:${u.role === 'ADMIN' ? 'var(--accent-purple)' : u.role === 'MANAGER' ? 'var(--accent-green)' : 'var(--accent-warning)'}">${u.role}</span></td>
                    <td>${statusBadge}</td>
                    <td class="text-right" style="white-space: nowrap;">
                        <button class="btn btn-secondary" onclick="openUserModal(${u.id})">
                            <i data-lucide="edit-3"></i> Editar Permissão
                        </button>
                        ${!isSelf ? `
                            <button class="btn btn-secondary" onclick="toggleUserActive(${u.id})">
                                <i data-lucide="${u.active ? 'user-x' : 'user-check'}"></i> ${u.active ? 'Desativar' : 'Ativar'}
                            </button>
                        ` : '<small class="text-muted">(Sua conta)</small>'}
                    </td>
                </tr>
            `;
        }).join('');

        lucide.createIcons();

    } catch (err) {
        console.error('Erro ao carregar usuários:', err);
    }
}

// --- SUB-NAVEGAÇÃO & MATRIZ DE PERMISSÕES POR MÓDULO ---

let permissionsList = [];

function showSettingsSubtab(subtabName) {
    document.querySelectorAll('.subnav-item').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.subtab === subtabName);
    });

    document.querySelectorAll('.settings-subtab').forEach(sec => {
        sec.classList.toggle('active', sec.id === `settings-subtab-${subtabName}`);
    });

    if (subtabName === 'users') loadUsers();
    else if (subtabName === 'permissions') loadPermissionsMatrix();

    lucide.createIcons();
}

async function loadPermissionsMatrix() {
    if (currentUser.role !== 'ADMIN') return;

    try {
        const res = await fetch('/api/permissions');
        permissionsList = await res.json();

        const modules = [
            { key: 'dashboard', label: '📊 Dashboard Principal & Métricas', desc: 'Acesso ao painel principal e resumos' },
            { key: 'products_view', label: '📦 Visualizar Catálogo de Peças', desc: 'Consulta de peças e saldos em estoque' },
            { key: 'products_manage', label: '➕ Cadastrar / Editar Peças', desc: 'Criar novas peças e editar informações' },
            { key: 'costs_view', label: '💲 Visualizar Custos & Preços', desc: 'Acesso a valores financeiros de compra e repasse' },
            { key: 'categories_manage', label: '🏷️ Gerenciar Categorias', desc: 'Criar, editar e excluir categorias de peças' },
            { key: 'movements_in', label: '📥 Registrar Entradas (Compras)', desc: 'Lançar novas compras de fornecedores' },
            { key: 'movements_out', label: '📤 Registrar Saídas (Manutenção)', desc: 'Lançar peças utilizadas nas academias' },
            { key: 'alerts_view', label: '⚠️ Visualizar Alertas de Reposição', desc: 'Consultar itens abaixo do estoque mínimo' },
            { key: 'branches_manage', label: '🏢 Gerenciar Unidades da Academia', desc: 'Cadastrar, editar e excluir academias da rede' },
            { key: 'users_manage', label: '⚙️ Configurações & Usuários', desc: 'Gerenciar contas de usuários e regras RBAC' },
            { key: 'reports_export', label: '📄 Gerar & Baixar Relatórios CSV', desc: 'Exportação de relatórios em planilha Excel' }
        ];

        const adminPerms = permissionsList.find(r => r.role === 'ADMIN') || {};
        const managerPerms = permissionsList.find(r => r.role === 'MANAGER') || {};
        const operatorPerms = permissionsList.find(r => r.role === 'OPERATOR') || {};

        const tbody = document.getElementById('permissions-matrix-body');
        tbody.innerHTML = modules.map(m => `
            <tr>
                <td>
                    <strong style="font-size:0.88rem; display:block;">${m.label}</strong>
                    <small class="text-muted">${m.desc}</small>
                </td>
                <td class="text-center">
                    <input type="checkbox" id="perm-ADMIN-${m.key}" ${adminPerms[m.key] ? 'checked' : ''}>
                </td>
                <td class="text-center">
                    <input type="checkbox" id="perm-MANAGER-${m.key}" ${managerPerms[m.key] ? 'checked' : ''}>
                </td>
                <td class="text-center">
                    <input type="checkbox" id="perm-OPERATOR-${m.key}" ${operatorPerms[m.key] ? 'checked' : ''}>
                </td>
            </tr>
        `).join('');

    } catch (err) {
        console.error('Erro ao carregar matriz de permissões:', err);
    }
}

async function savePermissionsMatrix() {
    if (currentUser.role !== 'ADMIN') return;

    const moduleKeys = [
        'dashboard', 'products_view', 'products_manage', 'costs_view', 
        'categories_manage', 'movements_in', 'movements_out', 'alerts_view', 
        'branches_manage', 'users_manage', 'reports_export'
    ];

    const roles = ['ADMIN', 'MANAGER', 'OPERATOR'];

    try {
        for (const r of roles) {
            const body = { role_name: r };
            moduleKeys.forEach(k => {
                const el = document.getElementById(`perm-${r}-${k}`);
                body[k] = el ? el.checked : false;
            });

            await fetch(`/api/permissions/${r}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body)
            });
        }

        showToast('Matriz de permissões atualizada com sucesso!', 'success');
        await checkCurrentUser();

    } catch (err) {
        showToast('Erro ao salvar matriz de permissões', 'error');
    }
}

async function toggleUserActive(userId) {
    try {
        const res = await fetch(`/api/users/${userId}/toggle`, { method: 'PUT' });
        const data = await res.json();
        if (res.ok) {
            showToast(data.message, 'success');
            loadUsers();
        } else {
            showToast(data.error, 'error');
        }
    } catch (err) {
        showToast('Erro ao alterar status do usuário', 'error');
    }
}

// --- MODAIS DE CATEGORIA ---

function openCategoryModal(categoryId = null) {
    const form = document.getElementById('form-category');
    form.reset();
    document.getElementById('cat-id').value = '';

    if (categoryId) {
        const c = categoriesList.find(item => item.id === categoryId);
        if (c) {
            document.getElementById('modal-category-title').textContent = 'Editar Categoria';
            document.getElementById('cat-id').value = c.id;
            document.getElementById('cat-name').value = c.name;
            document.getElementById('cat-description').value = c.description || '';
            document.getElementById('cat-icon').value = c.icon || 'folder';
        }
    } else {
        document.getElementById('modal-category-title').textContent = 'Adicionar Nova Categoria';
    }

    document.getElementById('modal-category').classList.add('active');
}

async function saveCategory(e) {
    e.preventDefault();
    const id = document.getElementById('cat-id').value;
    const body = {
        name: document.getElementById('cat-name').value,
        description: document.getElementById('cat-description').value,
        icon: document.getElementById('cat-icon').value
    };

    const method = id ? 'PUT' : 'POST';
    const url = id ? `/api/categories/${id}` : '/api/categories';

    try {
        const res = await fetch(url, {
            method: method,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        });
        const data = await res.json();

        if (res.ok) {
            showToast(data.message, 'success');
            closeModal('modal-category');
            await loadInitialMetadata();
            loadCategories();
            populateCategoryDropdowns();
        } else {
            showToast(data.error, 'error');
        }
    } catch (err) {
        showToast('Erro ao salvar categoria', 'error');
    }
}

async function deleteCategory(categoryId) {
    if (!confirm('Deseja realmente excluir esta categoria?')) return;

    try {
        const res = await fetch(`/api/categories/${categoryId}`, { method: 'DELETE' });
        const data = await res.json();
        if (res.ok) {
            showToast(data.message, 'success');
            await loadInitialMetadata();
            loadCategories();
            populateCategoryDropdowns();
        } else {
            showToast(data.error, 'error');
        }
    } catch (err) {
        showToast('Erro ao excluir categoria', 'error');
    }
}

// --- MODAIS DE PRODUTO ---

function openProductModal(productId = null) {
    const form = document.getElementById('form-product');
    form.reset();
    document.getElementById('prod-id').value = '';
    
    if (productId) {
        const p = productsList.find(item => item.id === productId);
        if (p) {
            document.getElementById('modal-product-title').textContent = 'Editar Peça de Reposição';
            document.getElementById('prod-id').value = p.id;
            document.getElementById('prod-code').value = p.code;
            document.getElementById('prod-code').disabled = true;
            document.getElementById('prod-name').value = p.name;
            document.getElementById('prod-unit').value = p.unit;
            document.getElementById('prod-category').value = p.category_id;
            document.getElementById('prod-location').value = p.location || '';
            document.getElementById('prod-current-stock').value = p.current_stock;
            document.getElementById('prod-current-stock').disabled = true;
            document.getElementById('prod-min-stock').value = p.min_stock;
            document.getElementById('prod-purchase-price').value = p.purchase_price || 0;
            document.getElementById('prod-sale-price').value = p.sale_price || 0;
        }
    } else {
        document.getElementById('modal-product-title').textContent = 'Cadastrar Nova Peça';
        document.getElementById('prod-code').disabled = false;
        document.getElementById('prod-current-stock').disabled = false;
    }

    document.getElementById('modal-product').classList.add('active');
}

async function saveProduct(e) {
    e.preventDefault();
    const id = document.getElementById('prod-id').value;

    const body = {
        code: document.getElementById('prod-code').value,
        name: document.getElementById('prod-name').value,
        unit: document.getElementById('prod-unit').value,
        category_id: parseInt(document.getElementById('prod-category').value),
        location: document.getElementById('prod-location').value,
        current_stock: parseInt(document.getElementById('prod-current-stock').value || 0),
        min_stock: parseInt(document.getElementById('prod-min-stock').value || 0),
        purchase_price: parseFloat(document.getElementById('prod-purchase-price').value || 0),
        sale_price: parseFloat(document.getElementById('prod-sale-price').value || 0)
    };

    const method = id ? 'PUT' : 'POST';
    const url = id ? `/api/products/${id}` : '/api/products';

    try {
        const res = await fetch(url, {
            method: method,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        });
        const data = await res.json();

        if (res.ok) {
            showToast(data.message, 'success');
            closeModal('modal-product');
            loadProducts();
            loadDashboard();
        } else {
            showToast(data.error, 'error');
        }
    } catch (err) {
        showToast('Erro ao salvar produto', 'error');
    }
}

// --- MODAL MOVIMENTAÇÃO ---
function openMovementModal(type = 'SAIDA') {
    const form = document.getElementById('form-movement');
    form.reset();
    document.getElementById('mov-type').value = type;

    const title = type === 'ENTRADA' ? 'Registrar Entrada / Compra de Peças' : 'Registrar Saída de Peça para Manutenção';
    document.getElementById('modal-movement-title').textContent = title;
    
    const submitBtn = document.getElementById('btn-submit-movement');
    submitBtn.textContent = type === 'ENTRADA' ? 'Confirmar Entrada' : 'Confirmar Saída';
    submitBtn.className = type === 'ENTRADA' ? 'btn btn-primary' : 'btn btn-danger';

    const select = document.getElementById('mov-product-id');
    select.innerHTML = '<option value="">Selecione uma peça...</option>';
    
    fetch('/api/products').then(res => res.json()).then(prods => {
        productsList = prods;
        productsList.forEach(p => {
            select.innerHTML += `<option value="${p.id}">${p.code} - ${p.name} (Saldo: ${p.current_stock} ${p.unit})</option>`;
        });
    });

    document.getElementById('modal-movement').classList.add('active');
}

function openQuickMovementModal(productId, type) {
    openMovementModal(type);
    setTimeout(() => {
        const select = document.getElementById('mov-product-id');
        select.value = productId;
        updateProductStockInfo();
    }, 150);
}

function updateProductStockInfo() {
    const productId = parseInt(document.getElementById('mov-product-id').value);
    const infoBox = document.getElementById('mov-stock-info');
    const stockVal = document.getElementById('mov-current-stock-val');

    const product = productsList.find(p => p.id === productId);
    if (product) {
        stockVal.textContent = `${product.current_stock} ${product.unit}`;
        infoBox.style.display = 'block';
    } else {
        infoBox.style.display = 'none';
    }
}

async function saveMovement(e) {
    e.preventDefault();
    const body = {
        product_id: parseInt(document.getElementById('mov-product-id').value),
        type: document.getElementById('mov-type').value,
        quantity: parseInt(document.getElementById('mov-quantity').value),
        branch_id: document.getElementById('mov-branch-id').value ? parseInt(document.getElementById('mov-branch-id').value) : null,
        destination_equipment: document.getElementById('mov-destination').value,
        notes: document.getElementById('mov-notes').value
    };

    try {
        const res = await fetch('/api/movements', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        });
        const data = await res.json();

        if (res.ok) {
            showToast(data.message, 'success');
            closeModal('modal-movement');
            loadProducts();
            loadMovements();
            loadDashboard();
        } else {
            showToast(data.error, 'error');
        }
    } catch (err) {
        showToast('Erro ao processar movimentação', 'error');
    }
}

// --- MODAL USUÁRIO & PERMISSÕES ---
function openUserModal(userId = null) {
    const form = document.getElementById('form-user');
    form.reset();
    document.getElementById('user-id').value = '';
    
    if (userId) {
        const u = usersList.find(item => item.id === userId);
        if (u) {
            document.getElementById('modal-user-title').textContent = 'Editar Usuário & Permissões';
            document.getElementById('user-id').value = u.id;
            document.getElementById('user-name').value = u.name;
            document.getElementById('user-username').value = u.username;
            document.getElementById('user-username').disabled = true;
            document.getElementById('user-email').value = u.email || '';
            document.getElementById('user-role').value = u.role;
            document.getElementById('user-pass-note').style.display = 'inline';
        }
    } else {
        document.getElementById('modal-user-title').textContent = 'Cadastrar Novo Usuário';
        document.getElementById('user-username').disabled = false;
        document.getElementById('user-pass-note').style.display = 'none';
    }

    document.getElementById('modal-user').classList.add('active');
}

async function saveUser(e) {
    e.preventDefault();
    const id = document.getElementById('user-id').value;
    const body = {
        name: document.getElementById('user-name').value,
        username: document.getElementById('user-username').value,
        password: document.getElementById('user-password').value,
        email: document.getElementById('user-email').value,
        role: document.getElementById('user-role').value
    };

    const method = id ? 'PUT' : 'POST';
    const url = id ? `/api/users/${id}` : '/api/users';

    try {
        const res = await fetch(url, {
            method: method,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        });
        const data = await res.json();

        if (res.ok) {
            showToast(data.message, 'success');
            closeModal('modal-user');
            loadUsers();
        } else {
            showToast(data.error, 'error');
        }
    } catch (err) {
        showToast('Erro ao salvar usuário', 'error');
    }
}

// --- MODAL UNIDADE DA ACADEMIA ---
function openBranchModal(branchId = null) {
    const form = document.getElementById('form-branch');
    form.reset();
    document.getElementById('branch-id').value = '';

    if (branchId) {
        const b = branchesList.find(item => item.id === branchId);
        if (b) {
            document.getElementById('modal-branch-title').textContent = 'Editar Unidade da Academia';
            document.getElementById('branch-id').value = b.id;
            document.getElementById('branch-name').value = b.name;
            document.getElementById('branch-address').value = b.address || '';
            document.getElementById('branch-phone').value = b.phone || '';
        }
    } else {
        document.getElementById('modal-branch-title').textContent = 'Cadastrar Unidade da Academia';
    }

    document.getElementById('modal-branch').classList.add('active');
}

async function saveBranch(e) {
    e.preventDefault();
    const id = document.getElementById('branch-id').value;
    const body = {
        name: document.getElementById('branch-name').value,
        address: document.getElementById('branch-address').value,
        phone: document.getElementById('branch-phone').value
    };

    const method = id ? 'PUT' : 'POST';
    const url = id ? `/api/branches/${id}` : '/api/branches';

    try {
        const res = await fetch(url, {
            method: method,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        });
        const data = await res.json();

        if (res.ok) {
            showToast(data.message, 'success');
            closeModal('modal-branch');
            loadBranches();
            loadInitialMetadata();
        } else {
            showToast(data.error, 'error');
        }
    } catch (err) {
        showToast('Erro ao salvar unidade', 'error');
    }
}

function closeModal(modalId) {
    document.getElementById(modalId).classList.remove('active');
}

// --- UTILITÁRIOS ---

function formatCurrency(val) {
    return new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(val || 0);
}

function formatDate(dateStr) {
    if (!dateStr) return '-';
    const date = new Date(dateStr);
    return date.toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short' });
}

function showToast(message, type = 'success') {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;

    let icon = 'check-circle';
    if (type === 'error') icon = 'alert-triangle';
    if (type === 'warning') icon = 'alert-circle';

    toast.innerHTML = `<i data-lucide="${icon}"></i> <span>${message}</span>`;
    container.appendChild(toast);
    lucide.createIcons();

    setTimeout(() => {
        toast.remove();
    }, 4000);
}
