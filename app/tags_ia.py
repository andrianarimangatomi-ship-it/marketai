# app/tags_ia.py
import re
import nltk
from nltk.corpus import stopwords
from sklearn.feature_extraction.text import TfidfVectorizer

# Télécharger les stop words français (une seule fois)
try:
    nltk.data.find('corpora/stopwords.zip')
except LookupError:
    nltk.download('stopwords', quiet=True)

STOP_WORDS = set(stopwords.words('french'))
# Ajouter des mots personnalisés à exclure
CUSTOM_STOP = {'cet', 'ces', 'cette', 'ces', 'leur', 'leurs', 'être', 'avoir', 'faire', 'mettre', 'vendre', 'acheter', 'prix', 'article'}
STOP_WORDS.update(CUSTOM_STOP)

def extract_keywords(text, top_n=5):
    """
    Extrait les mots-clés les plus importants d'un texte.
    Utilise TF-IDF sur un document unique.
    """
    if not text or len(text.strip()) < 10:
        return []
    
    # Prétraitement : minuscules, suppression des chiffres et caractères spéciaux
    text = re.sub(r'[^a-zA-Zàâçéèêëîïôûùüÿñæœ\s]', '', text.lower())
    
    # Tokenisation manuelle
    words = text.split()
    # Filtrer les stop words et les mots trop courts
    filtered_words = [w for w in words if w not in STOP_WORDS and len(w) > 2]
    if not filtered_words:
        return []
    
    cleaned_text = ' '.join(filtered_words)
    
    # TF-IDF sur ce seul document
    vectorizer = TfidfVectorizer(ngram_range=(1, 2), max_features=top_n*2)
    try:
        tfidf_matrix = vectorizer.fit_transform([cleaned_text])
        feature_names = vectorizer.get_feature_names_out()
        scores = tfidf_matrix.toarray()[0]
        scored = sorted(zip(feature_names, scores), key=lambda x: x[1], reverse=True)
        keywords = []
        seen = set()
        for kw, score in scored:
            if score > 0 and kw not in seen:
                keywords.append(kw)
                seen.add(kw)
            if len(keywords) >= top_n:
                break
        return keywords
    except:
        return []

def generate_tags_for_item(title, description, top_n=5):
    """Génère des tags à partir du titre et de la description."""
    full_text = f"{title} {description}"
    return extract_keywords(full_text, top_n)