from app.extensions import db
from datetime import datetime

class Item(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)
    price = db.Column(db.Float, nullable=False)
    category = db.Column(db.String(50), nullable=False)
    image_url = db.Column(db.String(300), nullable=True)
    views = db.Column(db.Integer, default=0)
    clicks = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    tags = db.Column(db.String(200), nullable=True)  # <-- AJOUT : champ pour les mots-clés

    def score_popularite(self):
        if self.views == 0:
            return 0.0
        return self.clicks / self.views

    def reinforcement_score(self):
        # Score lissé pour que l'IA n'élimine pas les nouveaux articles
        return (self.clicks + 1) / (self.views + 5)

    def ctr_percent(self):
        return self.score_popularite() * 100

    def __repr__(self):
        return f"Item('{self.title}', '{self.category}')"