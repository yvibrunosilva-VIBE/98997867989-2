import os
import psycopg2
import psycopg2.extras
from werkzeug.security import generate_password_hash


def _get_database_url():
    """Lê e valida a DATABASE_URL do ambiente.
    - Exige que a variável esteja definida (falha com mensagem clara caso não esteja).
    - Corrige o prefixo 'postgres://' para 'postgresql://', pois o Railway
      às vezes usa o formato antigo que o psycopg2 não aceita.
    """
    url = os.environ.get('DATABASE_URL', '')
    if not url:
        raise RuntimeError(
            "DATABASE_URL não está definida. "
            "No Railway: vá em Variables do serviço Flask e adicione "
            "DATABASE_URL = ${{Postgres.DATABASE_URL}}"
        )
    # psycopg2 exige 'postgresql://', mas o Railway pode enviar 'postgres://'
    if url.startswith('postgres://'):
        url = url.replace('postgres://', 'postgresql://', 1)
    return url


def get_db_connection():
    """Retorna uma conexão com o banco PostgreSQL usando DictCursor.
    DictCursor permite acesso por nome de coluna (row['col']) E por índice (row[0]).
    """
    conn = psycopg2.connect(_get_database_url(), cursor_factory=psycopg2.extras.DictCursor)
    return conn


def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()

    # Tabela de Usuarios
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            name TEXT NOT NULL,
            email TEXT,
            role TEXT NOT NULL,
            active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Tabela de Matriz de Permissoes por Perfil (RBAC Customizavel)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS role_permissions (
            role TEXT PRIMARY KEY,
            role_name TEXT NOT NULL,
            dashboard INTEGER DEFAULT 1,
            products_view INTEGER DEFAULT 1,
            products_manage INTEGER DEFAULT 0,
            costs_view INTEGER DEFAULT 0,
            categories_manage INTEGER DEFAULT 0,
            movements_in INTEGER DEFAULT 0,
            movements_out INTEGER DEFAULT 1,
            alerts_view INTEGER DEFAULT 1,
            branches_manage INTEGER DEFAULT 0,
            users_manage INTEGER DEFAULT 0,
            reports_export INTEGER DEFAULT 0
        )
    ''')

    # Tabela de Categorias
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS categories (
            id SERIAL PRIMARY KEY,
            name TEXT UNIQUE NOT NULL,
            description TEXT,
            icon TEXT DEFAULT 'folder'
        )
    ''')

    # Tabela de Unidades da Academia
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS branches (
            id SERIAL PRIMARY KEY,
            name TEXT UNIQUE NOT NULL,
            address TEXT,
            phone TEXT
        )
    ''')

    # Tabela de Produtos / Pecas
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS products (
            id SERIAL PRIMARY KEY,
            code TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            category_id INTEGER NOT NULL,
            unit TEXT DEFAULT 'un',
            current_stock INTEGER DEFAULT 0,
            min_stock INTEGER DEFAULT 0,
            purchase_price REAL DEFAULT 0.0,
            sale_price REAL DEFAULT 0.0,
            location TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (category_id) REFERENCES categories(id)
        )
    ''')

    # Tabela de Movimentacoes (Entrada / Saida)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS movements (
            id SERIAL PRIMARY KEY,
            product_id INTEGER NOT NULL,
            type TEXT NOT NULL CHECK(type IN ('ENTRADA', 'SAIDA')),
            quantity INTEGER NOT NULL,
            unit_price REAL NOT NULL,
            total_price REAL NOT NULL,
            branch_id INTEGER,
            destination_equipment TEXT,
            notes TEXT,
            user_id INTEGER NOT NULL,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (product_id) REFERENCES products(id),
            FOREIGN KEY (branch_id) REFERENCES branches(id),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')

    conn.commit()
    seed_initial_data(conn)
    conn.close()


def seed_initial_data(conn):
    cursor = conn.cursor()

    # Matriz Inicial de Permissoes
    cursor.execute('SELECT COUNT(*) FROM role_permissions')
    if cursor.fetchone()[0] == 0:
        permissions_data = [
            # role, role_name, dashboard, prod_view, prod_manage, costs_view, cat_manage, mov_in, mov_out, alerts_view, branches_manage, users_manage, reports_export
            ('ADMIN', 'Administrador Geral', 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1),
            ('MANAGER', 'Gerente de Manutencao', 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 1),
            ('OPERATOR', 'Tecnico de Campo / Operador', 1, 1, 0, 0, 0, 0, 1, 1, 0, 0, 0)
        ]
        cursor.executemany('''
            INSERT INTO role_permissions
            (role, role_name, dashboard, products_view, products_manage, costs_view, categories_manage, movements_in, movements_out, alerts_view, branches_manage, users_manage, reports_export)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ''', permissions_data)

    # Garantir que os 2 usuários de login existam sempre, com a senha correta (upsert).
    seed_users = [
        ('victor.lyra', 'Lyra1538', 'Victor Lyra', 'victor.lyra@gymfit.com', 'ADMIN'),
        ('bruno.machado', 'Bsm1536', 'Bruno Machado', 'bruno.machado@gymfit.com', 'ADMIN')
    ]
    for username, plain_password, name, email, role in seed_users:
                cursor.execute(
            '''
            INSERT INTO users (username, password_hash, name, email, role, active)
            VALUES (%s, %s, %s, %s, %s, 1)
            ON CONFLICT (username) DO UPDATE SET
                password_hash = EXCLUDED.password_hash,
                name = EXCLUDED.name,
                email = EXCLUDED.email,
                role = EXCLUDED.role,
                active = 1
            ''',
            (username, generate_password_hash(plain_password), name, email, role)
        )

    # Verificar se ja existem categorias
    cursor.execute('SELECT COUNT(*) FROM categories')
    if cursor.fetchone()[0] == 0:
        categories_data = [
            ('Equipamentos e Musculacao', 'Pecas para esteiras, bicicletas, cabos e roldanas', 'dumbbell'),
            ('Eletrica e Iluminacao', 'Lampadas, disjuntores, fiacao e conectores', 'zap'),
            ('Escritorio e TI', 'Papelaria, cartuchos, cabos e perifericos', 'file-text'),
            ('Hidraulica e Climatizacao', 'Reparos, filtros de ar-condicionado e conexoes', 'droplet'),
            ('Limpeza e Utilidades', 'Mops, dispensadores e panos de microfibra', 'sparkles')
        ]
        cursor.executemany(
            'INSERT INTO categories (name, description, icon) VALUES (%s, %s, %s)',
            categories_data
        )

    # Verificar se ja existem unidades
    cursor.execute('SELECT COUNT(*) FROM branches')
    if cursor.fetchone()[0] == 0:
        branches_data = [
            ('Unidade Central - Paulista', 'Av. Paulista, 1000 - Bela Vista', '(11) 3200-1000'),
            ('Unidade Moema - Zona Sul', 'Rua das Palmeiras, 450 - Moema', '(11) 5050-2000'),
            ('Unidade Santana - Zona Norte', 'Av. Santana, 1200 - Santana', '(11) 2970-3000')
        ]
        cursor.executemany(
            'INSERT INTO branches (name, address, phone) VALUES (%s, %s, %s)',
            branches_data
        )

    # Verificar se ja existem produtos
    cursor.execute('SELECT COUNT(*) FROM products')
    if cursor.fetchone()[0] == 0:
        products_data = [
            ('EQP-001', 'Lona para Esteira Ergometrica Movement LX160', 1, 'un', 4, 5, 220.00, 350.00, 'Prateleira A1'),
            ('EQP-002', 'Cabo de Aco Flexivel 3/16 Revestido (Metro)', 1, 'm', 45, 20, 12.50, 22.00, 'Rolo A2'),
            ('EQP-003', 'Roldana de Aluminio 90mm c/ Rolamento', 1, 'un', 12, 10, 38.00, 65.00, 'Caixa A3'),
            ('EQP-004', 'Sensor de Frequencia Cardiaca / Hand Grip', 1, 'un', 2, 4, 85.00, 140.00, 'Gaveta B1'),
            ('ELE-001', 'Lampada Tubular LED 18W 120cm Bivolt', 2, 'un', 28, 15, 14.00, 25.00, 'Prateleira C1'),
            ('ELE-002', 'Disjuntor Bipolar 32A DIN 3KA', 2, 'un', 6, 5, 32.00, 55.00, 'Prateleira C2'),
            ('ELE-003', 'Reator Eletronico para Lampada Fluo', 2, 'un', 1, 3, 45.00, 75.00, 'Prateleira C3'),
            ('ESC-001', 'Toner para Impressora HP LaserJet M404 (Black)', 3, 'un', 3, 2, 140.00, 210.00, 'Armario D1'),
            ('ESC-002', 'Papel Sulfite A4 75g (Caixa c/ 10 pacotes)', 3, 'cx', 8, 4, 185.00, 240.00, 'Armario D2'),
            ('HID-001', 'Reparador de Valvula de Descarga Docol 1.1/2', 4, 'un', 5, 3, 28.00, 48.00, 'Gaveta E1'),
            ('HID-002', 'Filtro Lavavel para Ar Condicionado Split 24k BTUs', 4, 'un', 7, 6, 35.00, 60.00, 'Prateleira E2')
        ]
        cursor.executemany(
            '''INSERT INTO products
               (code, name, category_id, unit, current_stock, min_stock, purchase_price, sale_price, location)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)''',
            products_data
        )

    # Adicionar movimentacoes iniciais se nao houver nenhuma
    cursor.execute('SELECT COUNT(*) FROM movements')
    if cursor.fetchone()[0] == 0:
        movements_data = [
            (1, 'ENTRADA', 5, 220.00, 1100.00, 1, 'Estoque Inicial', 'Compra Lote Fornecedor Movement', 1),
            (1, 'SAIDA', 1, 350.00, 350.00, 2, 'Esteira #03 - Moema', 'Troca por desgaste natural', 2),
            (2, 'ENTRADA', 50, 12.50, 625.00, 1, 'Estoque Inicial', 'Rolo de 50 metros', 1),
            (2, 'SAIDA', 5, 22.00, 110.00, 3, 'Puxador Crossover #01 - Santana', 'Manutencao preventiva cabo partido', 1),
            (5, 'ENTRADA', 30, 14.00, 420.00, 1, 'Estoque Inicial', 'Iluminacao Geral', 1),
            (5, 'SAIDA', 2, 25.00, 50.00, 1, 'Vestiario Masculino Central', 'Substituicao lampadas queimadas', 1)
        ]
        cursor.executemany(
            '''INSERT INTO movements
               (product_id, type, quantity, unit_price, total_price, branch_id, destination_equipment, notes, user_id)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)''',
            movements_data
        )

    conn.commit()


if __name__ == '__main__':
    init_db()
    print("Banco de dados PostgreSQL com tabela de permissoes inicializado!")