from flask import Flask
from dotenv import load_dotenv
import os

load_dotenv()

def create_app():
    app = Flask(__name__)
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-key')

    database_url = os.getenv('DATABASE_URL')
    if database_url:
        # Force l'utilisation du driver psycopg (version 3) au lieu de psycopg2
        database_url = database_url.replace('postgres://', 'postgresql+psycopg://')
        database_url = database_url.replace('postgresql://', 'postgresql+psycopg://')
        app.config['SQLALCHEMY_DATABASE_URI'] = database_url
    else:
        os.makedirs(app.instance_path, exist_ok=True)
        app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{os.path.join(app.instance_path, 'site.db')}"

    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SESSION_PERMANENT'] = False

    upload_folder = os.path.join(app.root_path, 'static', 'uploads')
    os.makedirs(upload_folder, exist_ok=True)
    app.config['UPLOAD_FOLDER'] = upload_folder
    app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

    from app.extensions import db
    db.init_app(app)

    from app.routes import main, admin
    app.register_blueprint(main)
    app.register_blueprint(admin)

    with app.app_context():
        db.create_all()

    return app