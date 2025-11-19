# app.py
from flask import Flask
from routes import register_routes

app = Flask(__name__)
app.secret_key = "secret_key_123"

# Register routes from routes.py
register_routes(app)

if __name__ == "__main__":
    app.run(debug=True)
