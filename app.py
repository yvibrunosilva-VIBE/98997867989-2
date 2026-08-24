import os
import csv
import io
import psycopg2
import psycopg2.extras
import psycopg2.errorcodes
from flask import Flask, render_template, request, jsonify, session, Response
from werkzeug.security import check_password_hash, generate_password_hash
from functools import wraps
import database

app = Flask(__name__)
# Em producao (Railway), configure a variavel de ambiente SECRET_KEY.
# O valor abaixo e apenas fallback para desenvolvimento local.
app.secret_key = os.environ.get('SECRET_KEY', 'gymcontrol_super_secret_key_2026')

# Garantir inicializacao do Banco de Dados
with app.app_context():
    database.init_db()

# Funcao auxiliar para verificar permissao dinamica do usuario logado
def check_user_permission(perm_name):
    if 'user_id' not in session:
        return False
    user_role = session.get('role')
    if not user_role:
        return False

    conn = database.get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT * FROM role_permissions WHERE role = %s', (user_role,))
    perm_row = cur.fetchone()
    conn.close()

    if not perm_row:
        return False

    try:
        return bool(perm_row[perm_name])
    except Exception:
        return False

def permission_required(perm_name):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                return jsonify({'error': 'Nao autenticado', 'login_required': True}), 401
            if not check_user_permission(perm_name):
                return jsonify({'error': f'Acesso negado. Sua permissao atual nao autoriza a acao: "{perm_name}".'}), 403
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# Rota Principal (Frontend SPA)
@app.route('/')
def index():
    return render_template('index.html')

# --- APIS DE AUTENTICACAO E PERFIL ---

@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json() or {}
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()

    if not username or not password:
        return jsonify({'error': 'Informe usuario e senha.'}), 400

    conn = database.get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT * FROM users WHERE username = %s AND active = 1', (username,))
    user = cur.fetchone()
    conn.close()

    if user and check_password_hash(user['password_hash'], password):
        session['user_id'] = user['id']
        session['username'] = user['username']
        session['name'] = user['name']
        session['role'] = user['role']

        return jsonify({
            'message': 'Login realizado com sucesso',
            'user': {
                'id': user['id'],
                'username': user['username'],
                'name': user['name'],
                'email': user['email'],
                'role': user['role']
            }
        })

    return jsonify({'error': 'Usuario ou senha incorretos.'}), 401

@app.route('/api/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'message': 'Logout realizado com sucesso.'})

@app.route('/api/me', methods=['GET'])
def get_me():
    if 'user_id' not in session:
        return jsonify({'user': None, 'authenticated': False}), 401

    user_role = session.get('role')
    conn = database.get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT * FROM role_permissions WHERE role = %s', (user_role,))
    perm_row = cur.fetchone()
    conn.close()

    permissions = dict(perm_row) if perm_row else {}

    return jsonify({
        'authenticated': True,
        'user': {
            'id': session.get('user_id'),
            'username': session.get('username'),
            'name': session.get('name'),
            'role': session.get('role'),
            'permissions': permissions
        }
    })

# --- API DASHBOARD & KPIs ---

@app.route('/api/dashboard/stats', methods=['GET'])
@permission_required('dashboard')
def dashboard_stats():
    conn = database.get_db_connection()
    can_view_costs = check_user_permission('costs_view')
    cur = conn.cursor()

    cur.execute('SELECT COUNT(*) FROM products')
    total_skus = cur.fetchone()[0]

    cur.execute('SELECT SUM(current_stock) FROM products')
    total_items = cur.fetchone()[0] or 0

    cur.execute('SELECT COUNT(*) FROM products WHERE current_stock <= min_stock')
    low_stock_count = cur.fetchone()[0]

    if can_view_costs:
        cur.execute('SELECT SUM(current_stock * purchase_price) FROM products')
        purchase_valuation = cur.fetchone()[0] or 0.0
        cur.execute('SELECT SUM(current_stock * sale_price) FROM products')
        sale_valuation = cur.fetchone()[0] or 0.0
    else:
        purchase_valuation = 0.0
        sale_valuation = 0.0

    cur.execute('''
        SELECT c.name, COUNT(p.id) as count, SUM(p.current_stock) as total_stock
        FROM categories c
        LEFT JOIN products p ON c.id = p.category_id
        GROUP BY c.id, c.name
        ORDER BY c.name
    ''')
    category_stats = cur.fetchall()

    cur.execute('''
        SELECT m.*, p.name as product_name, p.code as product_code, u.name as user_name, b.name as branch_name
        FROM movements m
        JOIN products p ON m.product_id = p.id
        JOIN users u ON m.user_id = u.id
        LEFT JOIN branches b ON m.branch_id = b.id
        ORDER BY m.timestamp DESC LIMIT 5
    ''')
    recent_movements = cur.fetchall()

    conn.close()

    return jsonify({
        'total_skus': total_skus,
        'total_items': total_items,
        'low_stock_count': low_stock_count,
        'purchase_valuation': round(purchase_valuation, 2),
        'sale_valuation': round(sale_valuation, 2),
        'category_stats': [dict(row) for row in category_stats],
        'recent_movements': [dict(row) for row in recent_movements]
    })

# --- API DE PRODUTOS / PECAS ---

@app.route('/api/products', methods=['GET'])
@permission_required('products_view')
def get_products():
    search = request.args.get('search', '').strip()
    category_id = request.args.get('category_id', '').strip()
    status = request.args.get('status', '').strip()

    can_view_costs = check_user_permission('costs_view')
    query = '''
        SELECT p.*, c.name as category_name
        FROM products p
        JOIN categories c ON p.category_id = c.id
        WHERE 1=1
    '''
    params = []

    if search:
        # ILIKE = LIKE case-insensitive no PostgreSQL
        query += ' AND (p.name ILIKE %s OR p.code ILIKE %s OR p.location ILIKE %s)'
        params.extend([f'%{search}%', f'%{search}%', f'%{search}%'])

    if category_id:
        query += ' AND p.category_id = %s'
        params.append(category_id)

    if status == 'low':
        query += ' AND p.current_stock <= p.min_stock AND p.current_stock > 0'
    elif status == 'out':
        query += ' AND p.current_stock = 0'
    elif status == 'ok':
        query += ' AND p.current_stock > p.min_stock'

    query += ' ORDER BY p.code ASC'

    conn = database.get_db_connection()
    cur = conn.cursor()
    cur.execute(query, params)
    rows = cur.fetchall()
    conn.close()

    products = []
    for r in rows:
        item = dict(r)
        if not can_view_costs:
            item['purchase_price'] = None
            item['sale_price'] = None
        products.append(item)

    return jsonify(products)

@app.route('/api/products', methods=['POST'])
@permission_required('products_manage')
def create_product():
    data = request.get_json() or {}
    code = data.get('code', '').strip().upper()
    name = data.get('name', '').strip()
    category_id = data.get('category_id')
    unit = data.get('unit', 'un').strip()
    current_stock = int(data.get('current_stock', 0))
    min_stock = int(data.get('min_stock', 0))
    purchase_price = float(data.get('purchase_price', 0.0))
    sale_price = float(data.get('sale_price', 0.0))
    location = data.get('location', '').strip()

    if not code or not name or not category_id:
        return jsonify({'error': 'Codigo SKU, Nome e Categoria sao obrigatorios.'}), 400

    conn = database.get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute('''
            INSERT INTO products (code, name, category_id, unit, current_stock, min_stock, purchase_price, sale_price, location)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        ''', (code, name, category_id, unit, current_stock, min_stock, purchase_price, sale_price, location))
        product_id = cur.fetchone()[0]
        conn.commit()
        conn.close()
        return jsonify({'message': 'Peca cadastrada com sucesso!', 'id': product_id}), 201
    except psycopg2.errors.UniqueViolation:
        conn.rollback()
        conn.close()
        return jsonify({'error': f'Codigo SKU "{code}" ja esta em uso.'}), 400

@app.route('/api/products/<int:product_id>', methods=['PUT'])
@permission_required('products_manage')
def update_product(product_id):
    data = request.get_json() or {}
    name = data.get('name', '').strip()
    category_id = data.get('category_id')
    unit = data.get('unit', 'un').strip()
    min_stock = int(data.get('min_stock', 0))
    purchase_price = float(data.get('purchase_price', 0.0))
    sale_price = float(data.get('sale_price', 0.0))
    location = data.get('location', '').strip()

    if not name or not category_id:
        return jsonify({'error': 'Nome e Categoria sao obrigatorios.'}), 400

    conn = database.get_db_connection()
    cur = conn.cursor()
    cur.execute('''
        UPDATE products
        SET name = %s, category_id = %s, unit = %s, min_stock = %s, purchase_price = %s, sale_price = %s, location = %s
        WHERE id = %s
    ''', (name, category_id, unit, min_stock, purchase_price, sale_price, location, product_id))
    conn.commit()
    conn.close()

    return jsonify({'message': 'Produto atualizado com sucesso.'})

@app.route('/api/products/<int:product_id>', methods=['DELETE'])
@permission_required('products_manage')
def delete_product(product_id):
    conn = database.get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT COUNT(*) FROM movements WHERE product_id = %s', (product_id,))
    mov_count = cur.fetchone()[0]
    if mov_count > 0:
        conn.close()
        return jsonify({'error': 'Nao e possivel excluir produto com historico de movimentacoes.'}), 400

    cur.execute('DELETE FROM products WHERE id = %s', (product_id,))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Produto removido com sucesso.'})

# --- API DE MOVIMENTACOES ---

@app.route('/api/movements', methods=['GET'])
@permission_required('products_view')
def get_movements():
    conn = database.get_db_connection()
    can_view_costs = check_user_permission('costs_view')
    cur = conn.cursor()

    cur.execute('''
        SELECT m.*, p.name as product_name, p.code as product_code, p.unit as product_unit,
               u.name as user_name, b.name as branch_name
        FROM movements m
        JOIN products p ON m.product_id = p.id
        JOIN users u ON m.user_id = u.id
        LEFT JOIN branches b ON m.branch_id = b.id
        ORDER BY m.timestamp DESC
    ''')
    rows = cur.fetchall()
    conn.close()

    movements = []
    for r in rows:
        item = dict(r)
        if not can_view_costs:
            item['unit_price'] = None
            item['total_price'] = None
        movements.append(item)

    return jsonify(movements)

@app.route('/api/movements', methods=['POST'])
def create_movement():
    user_id = session.get('user_id')
    data = request.get_json() or {}

    product_id = data.get('product_id')
    mov_type = data.get('type')
    quantity = int(data.get('quantity', 0))
    branch_id = data.get('branch_id')
    destination_equipment = data.get('destination_equipment', '').strip()
    notes = data.get('notes', '').strip()

    if mov_type == 'ENTRADA' and not check_user_permission('movements_in'):
        return jsonify({'error': 'Sua permissao nao autoriza o lancamento de ENTRADAS.'}), 403

    if mov_type == 'SAIDA' and not check_user_permission('movements_out'):
        return jsonify({'error': 'Sua permissao nao autoriza o lancamento de SAIDAS.'}), 403

    if not product_id or mov_type not in ('ENTRADA', 'SAIDA') or quantity <= 0:
        return jsonify({'error': 'Dados de movimentacao invalidos.'}), 400

    conn = database.get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT * FROM products WHERE id = %s', (product_id,))
    product = cur.fetchone()

    if not product:
        conn.close()
        return jsonify({'error': 'Peca/Produto nao encontrado.'}), 404

    current_stock = product['current_stock']

    if mov_type == 'SAIDA' and quantity > current_stock:
        conn.close()
        return jsonify({
            'error': f'Estoque insuficiente! Solicitado: {quantity} {product["unit"]}, Disponivel: {current_stock} {product["unit"]}.'
        }), 400

    if mov_type == 'ENTRADA':
        unit_price = product['purchase_price']
        new_stock = current_stock + quantity
    else:
        unit_price = product['sale_price']
        new_stock = current_stock - quantity

    total_price = round(unit_price * quantity, 2)

    try:
        cur.execute('''
            INSERT INTO movements (product_id, type, quantity, unit_price, total_price, branch_id, destination_equipment, notes, user_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ''', (product_id, mov_type, quantity, unit_price, total_price, branch_id, destination_equipment, notes, user_id))

        cur.execute('UPDATE products SET current_stock = %s WHERE id = %s', (new_stock, product_id))

        conn.commit()
        conn.close()

        return jsonify({
            'message': f'Movimentacao de {mov_type} concluida com sucesso!',
            'new_stock': new_stock
        }), 201
    except Exception as e:
        conn.rollback()
        conn.close()
        return jsonify({'error': f'Erro ao processar movimentacao: {str(e)}'}), 500

# --- API DE CATEGORIAS ---

@app.route('/api/categories', methods=['GET'])
@permission_required('products_view')
def get_categories():
    conn = database.get_db_connection()
    cur = conn.cursor()
    cur.execute('''
        SELECT c.*, COUNT(p.id) as product_count
        FROM categories c
        LEFT JOIN products p ON c.id = p.category_id
        GROUP BY c.id, c.name, c.description, c.icon
        ORDER BY c.name ASC
    ''')
    categories = cur.fetchall()
    conn.close()
    return jsonify([dict(c) for c in categories])

@app.route('/api/categories', methods=['POST'])
@permission_required('categories_manage')
def create_category():
    data = request.get_json() or {}
    name = data.get('name', '').strip()
    description = data.get('description', '').strip()
    icon = data.get('icon', 'folder').strip()

    if not name:
        return jsonify({'error': 'Nome da categoria e obrigatorio.'}), 400

    conn = database.get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            'INSERT INTO categories (name, description, icon) VALUES (%s, %s, %s) RETURNING id',
            (name, description, icon)
        )
        cat_id = cur.fetchone()[0]
        conn.commit()
        conn.close()
        return jsonify({'message': 'Categoria criada com sucesso!', 'id': cat_id, 'name': name}), 201
    except psycopg2.errors.UniqueViolation:
        conn.rollback()
        conn.close()
        return jsonify({'error': 'Ja existe uma categoria com este nome.'}), 400

@app.route('/api/categories/<int:category_id>', methods=['PUT'])
@permission_required('categories_manage')
def update_category(category_id):
    data = request.get_json() or {}
    name = data.get('name', '').strip()
    description = data.get('description', '').strip()
    icon = data.get('icon', 'folder').strip()

    if not name:
        return jsonify({'error': 'Nome da categoria e obrigatorio.'}), 400

    conn = database.get_db_connection()
    cur = conn.cursor()
    cur.execute(
        'UPDATE categories SET name = %s, description = %s, icon = %s WHERE id = %s',
        (name, description, icon, category_id)
    )
    conn.commit()
    conn.close()
    return jsonify({'message': 'Categoria atualizada com sucesso!'})

@app.route('/api/categories/<int:category_id>', methods=['DELETE'])
@permission_required('categories_manage')
def delete_category(category_id):
    conn = database.get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT COUNT(*) FROM products WHERE category_id = %s', (category_id,))
    prod_count = cur.fetchone()[0]
    if prod_count > 0:
        conn.close()
        return jsonify({'error': 'Nao e possivel excluir categoria associada a produtos.'}), 400

    cur.execute('DELETE FROM categories WHERE id = %s', (category_id,))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Categoria excluida com sucesso!'})

# --- API DE UNIDADES DA ACADEMIA ---

@app.route('/api/branches', methods=['GET'])
@permission_required('products_view')
def get_branches():
    conn = database.get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT * FROM branches ORDER BY name ASC')
    branches = cur.fetchall()
    conn.close()
    return jsonify([dict(b) for b in branches])

@app.route('/api/branches', methods=['POST'])
@permission_required('branches_manage')
def create_branch():
    data = request.get_json() or {}
    name = data.get('name', '').strip()
    address = data.get('address', '').strip()
    phone = data.get('phone', '').strip()

    if not name:
        return jsonify({'error': 'Nome da unidade e obrigatorio.'}), 400

    conn = database.get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            'INSERT INTO branches (name, address, phone) VALUES (%s, %s, %s)',
            (name, address, phone)
        )
        conn.commit()
        conn.close()
        return jsonify({'message': 'Unidade cadastrada com sucesso!'}), 201
    except psycopg2.errors.UniqueViolation:
        conn.rollback()
        conn.close()
        return jsonify({'error': 'Uma unidade com esse nome ja existe.'}), 400

@app.route('/api/branches/<int:branch_id>', methods=['PUT'])
@permission_required('branches_manage')
def update_branch(branch_id):
    data = request.get_json() or {}
    name = data.get('name', '').strip()
    address = data.get('address', '').strip()
    phone = data.get('phone', '').strip()

    if not name:
        return jsonify({'error': 'Nome da unidade e obrigatorio.'}), 400

    conn = database.get_db_connection()
    cur = conn.cursor()
    cur.execute(
        'UPDATE branches SET name = %s, address = %s, phone = %s WHERE id = %s',
        (name, address, phone, branch_id)
    )
    conn.commit()
    conn.close()
    return jsonify({'message': 'Unidade atualizada com sucesso!'})

@app.route('/api/branches/<int:branch_id>', methods=['DELETE'])
@permission_required('branches_manage')
def delete_branch(branch_id):
    conn = database.get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT COUNT(*) FROM movements WHERE branch_id = %s', (branch_id,))
    mov_count = cur.fetchone()[0]
    if mov_count > 0:
        conn.close()
        return jsonify({'error': 'Nao e possivel excluir unidade com historico de movimentacoes.'}), 400

    cur.execute('DELETE FROM branches WHERE id = %s', (branch_id,))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Unidade excluida com sucesso!'})

# --- API DE USUARIOS & PERMISSOES ---

@app.route('/api/users', methods=['GET'])
@permission_required('users_manage')
def get_users():
    conn = database.get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT id, username, name, email, role, active, created_at FROM users ORDER BY name ASC')
    users = cur.fetchall()
    conn.close()
    return jsonify([dict(u) for u in users])

@app.route('/api/users', methods=['POST'])
@permission_required('users_manage')
def create_user():
    data = request.get_json() or {}
    username = data.get('username', '').strip().lower()
    password = data.get('password', '').strip()
    name = data.get('name', '').strip()
    email = data.get('email', '').strip()
    role = data.get('role', 'OPERATOR')

    if not username or not password or not name:
        return jsonify({'error': 'Usuario, senha e nome sao obrigatorios.'}), 400

    conn = database.get_db_connection()
    try:
        pwd_hash = generate_password_hash(password)
        cur = conn.cursor()
        cur.execute(
            'INSERT INTO users (username, password_hash, name, email, role) VALUES (%s, %s, %s, %s, %s)',
            (username, pwd_hash, name, email, role)
        )
        conn.commit()
        conn.close()
        return jsonify({'message': 'Usuario cadastrado com sucesso!'}), 201
    except psycopg2.errors.UniqueViolation:
        conn.rollback()
        conn.close()
        return jsonify({'error': 'Nome de usuario ja esta em uso.'}), 400

@app.route('/api/users/<int:user_id>', methods=['PUT'])
@permission_required('users_manage')
def update_user(user_id):
    data = request.get_json() or {}
    name = data.get('name', '').strip()
    email = data.get('email', '').strip()
    role = data.get('role')
    password = data.get('password', '').strip()

    if not name:
        return jsonify({'error': 'Nome e obrigatorio.'}), 400

    conn = database.get_db_connection()
    cur = conn.cursor()
    if password:
        pwd_hash = generate_password_hash(password)
        cur.execute(
            'UPDATE users SET name = %s, email = %s, role = %s, password_hash = %s WHERE id = %s',
            (name, email, role, pwd_hash, user_id)
        )
    else:
        cur.execute(
            'UPDATE users SET name = %s, email = %s, role = %s WHERE id = %s',
            (name, email, role, user_id)
        )

    conn.commit()
    conn.close()
    return jsonify({'message': 'Usuario e permissoes atualizados com sucesso!'})

@app.route('/api/users/<int:user_id>/toggle', methods=['PUT'])
@permission_required('users_manage')
def toggle_user_active(user_id):
    if user_id == session.get('user_id'):
        return jsonify({'error': 'Voce nao pode desativar seu proprio usuario.'}), 400

    conn = database.get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT active FROM users WHERE id = %s', (user_id,))
    user = cur.fetchone()
    if not user:
        conn.close()
        return jsonify({'error': 'Usuario nao encontrado.'}), 404

    new_status = 0 if user['active'] == 1 else 1
    cur.execute('UPDATE users SET active = %s WHERE id = %s', (new_status, user_id))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Status do usuario alterado com sucesso!', 'new_status': new_status})

# --- API DE GERENCIAMENTO DA MATRIZ DE PERMISSOES ---

@app.route('/api/permissions', methods=['GET'])
@permission_required('users_manage')
def get_permissions():
    conn = database.get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT * FROM role_permissions ORDER BY role ASC')
    roles = cur.fetchall()
    conn.close()
    return jsonify([dict(r) for r in roles])

@app.route('/api/permissions/<role_code>', methods=['PUT'])
@permission_required('users_manage')
def update_role_permissions(role_code):
    data = request.get_json() or {}

    conn = database.get_db_connection()
    cur = conn.cursor()
    cur.execute('''
        UPDATE role_permissions SET
            role_name = %s,
            dashboard = %s,
            products_view = %s,
            products_manage = %s,
            costs_view = %s,
            categories_manage = %s,
            movements_in = %s,
            movements_out = %s,
            alerts_view = %s,
            branches_manage = %s,
            users_manage = %s,
            reports_export = %s
        WHERE role = %s
    ''', (
        data.get('role_name', role_code),
        1 if data.get('dashboard') else 0,
        1 if data.get('products_view') else 0,
        1 if data.get('products_manage') else 0,
        1 if data.get('costs_view') else 0,
        1 if data.get('categories_manage') else 0,
        1 if data.get('movements_in') else 0,
        1 if data.get('movements_out') else 0,
        1 if data.get('alerts_view') else 0,
        1 if data.get('branches_manage') else 0,
        1 if data.get('users_manage') else 0,
        1 if data.get('reports_export') else 0,
        role_code
    ))
    conn.commit()
    conn.close()

    return jsonify({'message': f'Permissoes do perfil "{role_code}" atualizadas com sucesso!'})

# --- EXPORTACAO CSV ---

@app.route('/api/export/csv', methods=['GET'])
@permission_required('reports_export')
def export_csv():
    target = request.args.get('target', 'products')

    conn = database.get_db_connection()
    cur = conn.cursor()
    output = io.StringIO()
    writer = csv.writer(output, delimiter=';')

    if target == 'products':
        cur.execute('''
            SELECT p.code, p.name, c.name as category, p.unit, p.current_stock, p.min_stock,
                   p.purchase_price, p.sale_price, p.location
            FROM products p
            JOIN categories c ON p.category_id = c.id
            ORDER BY p.code ASC
        ''')
        products = cur.fetchall()

        writer.writerow(['SKU', 'Nome da Peca', 'Categoria', 'Unidade', 'Estoque Atual', 'Estoque Minimo', 'Custo Compra (R$)', 'Preco Venda (R$)', 'Localizacao'])
        for p in products:
            writer.writerow([p['code'], p['name'], p['category'], p['unit'], p['current_stock'], p['min_stock'], f"{p['purchase_price']:.2f}", f"{p['sale_price']:.2f}", p['location']])
        filename = "vibe_estoque_pecas.csv"

    else:
        cur.execute('''
            SELECT m.timestamp, m.type, p.code, p.name as product_name, m.quantity, p.unit,
                   m.unit_price, m.total_price, b.name as branch_name, m.destination_equipment, u.name as user_name, m.notes
            FROM movements m
            JOIN products p ON m.product_id = p.id
            JOIN users u ON m.user_id = u.id
            LEFT JOIN branches b ON m.branch_id = b.id
            ORDER BY m.timestamp DESC
        ''')
        movements = cur.fetchall()

        writer.writerow(['Data/Hora', 'Tipo', 'SKU', 'Produto', 'Quantidade', 'Unidade', 'Preco Unitario', 'Preco Total', 'Unidade Academia', 'Equipamento/Destino', 'Usuario', 'Observacoes'])
        for m in movements:
            writer.writerow([m['timestamp'], m['type'], m['code'], m['product_name'], m['quantity'], m['unit'], f"{m['unit_price']:.2f}", f"{m['total_price']:.2f}", m['branch_name'] or '', m['destination_equipment'] or '', m['user_name'], m['notes'] or ''])
        filename = "vibe_estoque_movimentacoes.csv"

    conn.close()

    response = Response(output.getvalue(), mimetype='text/csv')
    response.headers['Content-Disposition'] = f'attachment; filename={filename}'
    return response

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('DEBUG', 'false').lower() == 'true'
    app.run(host='0.0.0.0', port=port, debug=debug)
