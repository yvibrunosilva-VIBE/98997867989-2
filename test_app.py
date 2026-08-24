import unittest
import json
import database
from app import app

class GymControlTestCase(unittest.TestCase):

    def setUp(self):
        app.config['TESTING'] = True
        app.config['SECRET_KEY'] = 'test_secret_key'
        self.client = app.test_client()

        # Limpar e recriar o banco para cada execução de teste (PostgreSQL)
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute('TRUNCATE movements, role_permissions, users, products, branches, categories RESTART IDENTITY CASCADE')
        conn.commit()
        conn.close()
        database.init_db()

    def login(self, username, password):
        return self.client.post('/api/login', data=json.dumps({
            'username': username,
            'password': password
        }), content_type='application/json')

    def test_01_login_validation(self):
        """ Testar Login Válido e Inválido """
        res = self.login('victor.lyra', 'Lyra1538')
        self.assertEqual(res.status_code, 200)
        data = json.loads(res.data)
        self.assertEqual(data['user']['role'], 'ADMIN')

        res_bad = self.login('victor.lyra', 'senha_errada')
        self.assertEqual(res_bad.status_code, 401)

    def test_02_rbac_product_creation(self):
        """ Testar criação de peças exigindo autenticação e permissão """
        # Sem autenticação deve ser bloqueado
        res_unauth = self.client.post('/api/products', data=json.dumps({
            'code': 'TEST-001',
            'name': 'Peça de Teste',
            'category_id': 1
        }), content_type='application/json')
        self.assertEqual(res_unauth.status_code, 401)

        self.login('victor.lyra', 'Lyra1538')
        res_admin = self.client.post('/api/products', data=json.dumps({
            'code': 'TEST-999',
            'name': 'Cabo de Aço Teste 999',
            'category_id': 1,
            'unit': 'un',
            'current_stock': 10,
            'min_stock': 5,
            'purchase_price': 50.00,
            'sale_price': 80.00
        }), content_type='application/json')
        self.assertEqual(res_admin.status_code, 201)

    def test_03_stock_movement_and_insufficient_stock(self):
        """ Testar validação de estoque insuficiente e lançamento de movimentações """
        self.login('victor.lyra', 'Lyra1538')

        prod_res = self.client.get('/api/products')
        products = json.loads(prod_res.data)
        lona = next((p for p in products if p['code'] == 'EQP-001'), None)
        self.assertIsNotNone(lona)
        stock_before = lona['current_stock']

        res_fail = self.client.post('/api/movements', data=json.dumps({
            'product_id': lona['id'],
            'type': 'SAIDA',
            'quantity': 9999,
            'branch_id': 1
        }), content_type='application/json')
        self.assertEqual(res_fail.status_code, 400)

        res_ok = self.client.post('/api/movements', data=json.dumps({
            'product_id': lona['id'],
            'type': 'SAIDA',
            'quantity': 1,
            'branch_id': 1,
            'destination_equipment': 'Esteira #01'
        }), content_type='application/json')
        self.assertEqual(res_ok.status_code, 201)

    def test_04_category_crud(self):
        """ Testar criação e edição de categorias """
        self.login('victor.lyra', 'Lyra1538')

        res = self.client.post('/api/categories', data=json.dumps({
            'name': 'Suplementos & Hidratação',
            'description': 'Isotônicos e suplementos de vestiário',
            'icon': 'droplet'
        }), content_type='application/json')
        self.assertEqual(res.status_code, 201)
        cat_id = json.loads(res.data)['id']

        res_edit = self.client.put(f'/api/categories/{cat_id}', data=json.dumps({
            'name': 'Suplementos & Bebidas',
            'description': 'Isotônicos atualizados',
            'icon': 'droplet'
        }), content_type='application/json')
        self.assertEqual(res_edit.status_code, 200)

    def test_05_branch_edit_and_delete(self):
        """ Testar edição e exclusão de unidades da academia """
        self.login('victor.lyra', 'Lyra1538')

        res_create = self.client.post('/api/branches', data=json.dumps({
            'name': 'Unidade Teste Alphaville',
            'address': 'Alameda Rio Negro, 100',
            'phone': '(11) 4000-5000'
        }), content_type='application/json')
        self.assertEqual(res_create.status_code, 201)

        branches = json.loads(self.client.get('/api/branches').data)
        test_branch = next(b for b in branches if b['name'] == 'Unidade Teste Alphaville')

        res_edit = self.client.put(f'/api/branches/{test_branch["id"]}', data=json.dumps({
            'name': 'Unidade Alphaville Premium',
            'address': 'Alameda Rio Negro, 500',
            'phone': '(11) 4000-5555'
        }), content_type='application/json')
        self.assertEqual(res_edit.status_code, 200)

        res_del = self.client.delete(f'/api/branches/{test_branch["id"]}')
        self.assertEqual(res_del.status_code, 200)

    def test_06_user_permissions_update(self):
        """ Testar atualização de permissão do usuário """
        self.login('victor.lyra', 'Lyra1538')

        users = json.loads(self.client.get('/api/users').data)
        bruno = next(u for u in users if u['username'] == 'bruno.machado')

        res_update = self.client.put(f'/api/users/{bruno["id"]}', data=json.dumps({
            'name': 'Bruno Machado (Acesso Total)',
            'email': 'bruno.machado@gymfit.com',
            'role': 'ADMIN'
        }), content_type='application/json')
        self.assertEqual(res_update.status_code, 200)

    def test_07_permissions_matrix_crud(self):
        """ Testar atualização dinâmica da Matriz de Permissões por Módulo """
        self.login('victor.lyra', 'Lyra1538')

        # Buscar permissões
        res_get = self.client.get('/api/permissions')
        self.assertEqual(res_get.status_code, 200)
        perms = json.loads(res_get.data)
        self.assertGreaterEqual(len(perms), 3)

        # Dar permissão de visualizar custos para OPERATOR
        res_put = self.client.put('/api/permissions/OPERATOR', data=json.dumps({
            'role_name': 'Técnico com Acesso a Custos',
            'costs_view': True,
            'movements_out': True,
            'products_view': True,
            'dashboard': True
        }), content_type='application/json')
        self.assertEqual(res_put.status_code, 200)

        # Logado como ADMIN (acesso total) deve ver produtos com custos
        self.login('victor.lyra', 'Lyra1538')
        res_prods = self.client.get('/api/products')
        products = json.loads(res_prods.data)
        self.assertIsNotNone(products[0]['purchase_price'])

if __name__ == '__main__':
    unittest.main()
