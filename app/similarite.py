# app/similarite.py
from app.models import Item
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from app.extensions import db

_similarity_matrix = None
_vectorizer = None
_item_ids = None

def build_similarity_matrix():
    global _similarity_matrix, _vectorizer, _item_ids
    try:
        items = Item.query.all()
    except Exception as e:
        # La table peut ne pas exister ou la colonne tags peut manquer
        print(f"Erreur lors de l'accès à la base : {e}. La matrice ne sera pas construite pour l'instant.")
        _similarity_matrix = None
        _vectorizer = None
        _item_ids = []
        return

    if not items:
        _similarity_matrix = None
        _vectorizer = None
        _item_ids = []
        return
    
    texts = [f"{item.title} {item.description}" for item in items]
    _item_ids = [item.id for item in items]
    
    _vectorizer = TfidfVectorizer(stop_words=None, min_df=1, max_df=0.9)
    tfidf_matrix = _vectorizer.fit_transform(texts)
    _similarity_matrix = cosine_similarity(tfidf_matrix, tfidf_matrix)

def get_similar_items(item_id, limit=4):
    global _similarity_matrix, _item_ids
    if _similarity_matrix is None or _item_ids is None:
        build_similarity_matrix()
    
    if _similarity_matrix is None:
        return []
    
    try:
        idx = _item_ids.index(item_id)
    except ValueError:
        return []
    
    sim_scores = list(enumerate(_similarity_matrix[idx]))
    sim_scores = sorted(sim_scores, key=lambda x: x[1], reverse=True)
    sim_scores = [s for s in sim_scores if s[0] != idx][:limit]
    
    similar_items = []
    for i, score in sim_scores:
        item = Item.query.get(_item_ids[i])
        if item:
            similar_items.append((item, score))
    return similar_items

def refresh_similarity():
    build_similarity_matrix()