import os
import database
from app import app

if __name__ == '__main__':
    # Railway injeta a variável PORT automaticamente.
    # Em desenvolvimento local, usa a porta 5000 como padrão.
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('DEBUG', 'false').lower() == 'true'

    print("-------------------------------------------------------")
    print(" Starting GymControl Inventory Web Server...")
    print(f" Access in browser: http://localhost:{port}")
    print("-------------------------------------------------------")
    database.init_db()
    app.run(host='0.0.0.0', port=port, debug=debug)
