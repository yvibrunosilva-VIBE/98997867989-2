import os
import database
from flask_socketio import SocketIO
from app import app, socketio

if __name__ == '__main__':
    # Railway injeta a variÃ¡vel PORT automaticamente.
    # Em desenvolvimento local, usa a porta 5000 como padrÃ£o.
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('DEBUG', 'false').lower() == 'true'

    print("-------------------------------------------------------")
    print(" Starting GymControl Inventory Web Server...")
    print(f" Access in browser: http://localhost:{port}")
    print("-------------------------------------------------------")
    database.init_db()
    socketio.run(app, host='0.0.0.0', port=port, debug=debug)
