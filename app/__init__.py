from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv
import os

load_dotenv()

db = SQLAlchemy()

def create_app():
    app = Flask(__name__)
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-key')
    
    # Configuration base de données : PostgreSQL sur Render, SQLite en local
    database_url = os.getenv('DATABASE_URL')
    if database_url:
        # Render utilise postgres://, SQLAlchemy veut postgresql://
        database_url = database_url.replace('postgres://', 'postgresql://')
        app.config['SQLALCHEMY_DATABASE_URI'] = database_url
    else:
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///site.db'
    
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    # Dossier uploads
    upload_folder = os.path.join(app.root_path, 'static', 'uploads')
    os.makedirs(upload_folder, exist_ok=True)
    app.config['UPLOAD_FOLDER'] = upload_folder
    app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

    db.init_app(app)

    from app.routes import main, admin
    app.register_blueprint(main)
    app.register_blueprint(admin)

    with app.app_context():
        db.create_all()
        # Initialiser la matrice de similarité
        try:
            from app.similarite import build_similarity_matrix
            build_similarity_matrix()
        except Exception as e:
            print(f"Erreur similarité: {e}")

    return app