from flask import Flask
from dotenv import load_dotenv
import os

load_dotenv()

# ✅ SUPPRIMER ces deux lignes :
# from flask_sqlalchemy import SQLAlchemy  ← SUPPRIMER
# db = SQLAlchemy()                        ← SUPPRIMER

def create_app():
    app = Flask(__name__)
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-key')

    database_url = os.getenv('DATABASE_URL')
    if database_url:
        database_url = database_url.replace('postgres://', 'postgresql://')
        app.config['SQLALCHEMY_DATABASE_URI'] = database_url
    else:
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///site.db'

    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    upload_folder = os.path.join(app.root_path, 'static', 'uploads')
    os.makedirs(upload_folder, exist_ok=True)
    app.config['UPLOAD_FOLDER'] = upload_folder
    app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

    # ✅ Importer depuis extensions.py — instance unique
    from app.extensions import db
    db.init_app(app)

    from app import cli
    cli.init_app(app)

    from app.routes import main, admin
    app.register_blueprint(main)
    app.register_blueprint(admin)

    with app.app_context():
        db.create_all()
        try:
            from app.similarite import build_similarity_matrix
            build_similarity_matrix()
        except Exception as e:
            print(f"Erreur similarité: {e}")

    return app