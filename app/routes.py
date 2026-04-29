from flask import Blueprint, render_template, request, session, redirect, url_for, flash, abort, current_app, jsonify
from app.extensions import db
from app.models import Item, Order, OrderItem
from app.forms import ItemForm, AdminLoginForm
from app.ia import get_recommendations, update_click_metrics, update_view_metrics, get_ai_insights, get_trending_items, get_global_metrics
from app.similarite import get_similar_items, refresh_similarity
from app.tags_ia import generate_tags_for_item
from werkzeug.utils import secure_filename
from sklearn.metrics.pairwise import cosine_similarity
from datetime import datetime, timedelta
from sqlalchemy import func
import cloudinary
import cloudinary.uploader
from google import genai  # NOUVEAU SDK
import numpy as np
import os
import uuid

main = Blueprint('main', __name__)
admin = Blueprint('admin', __name__)

# ---------- Configuration Cloudinary ----------
cloudinary.config(
    cloud_name=os.getenv('CLOUDINARY_CLOUD_NAME'),
    api_key=os.getenv('CLOUDINARY_API_KEY'),
    api_secret=os.getenv('CLOUDINARY_API_SECRET'),
    secure=True
)

# ---------- Configuration Gemini (nouveau SDK) ----------
client = genai.Client(api_key=os.getenv('GEMINI_API_KEY'))

# ---------- Recherche sémantique ----------
def semantic_search(query, limit=12):
    """Recherche sémantique basée sur la similarité cosinus (TF-IDF)."""
    from app.similarite import build_similarity_matrix, _vectorizer
    if _vectorizer is None:
        build_similarity_matrix()
    if _vectorizer is None:
        return []
    items = Item.query.all()
    if not items:
        return []
    texts = [f"{item.title} {item.description}" for item in items]
    query_vec = _vectorizer.transform([query])
    item_tfidf = _vectorizer.transform(texts)
    similarities = cosine_similarity(query_vec, item_tfidf)[0]
    indices = np.argsort(similarities)[::-1][:limit]
    return [items[i] for i in indices if similarities[i] > 0]

# ---------- Route de test Cloudinary ----------
@main.route('/test-cloudinary')
def test_cloudinary():
    try:
        result = cloudinary.uploader.upload("https://res.cloudinary.com/demo/image/upload/sample.jpg", folder="marketai_test")
        return f"Succès : {result['secure_url']}"
    except Exception as e:
        return f"Erreur : {repr(e)}"

# ---------- Chatbot IA (nouvelle version) ----------
@main.route('/chatbot', methods=['POST'])
def chatbot():
    data = request.get_json()
    user_message = data.get('message', '').strip()
    if not user_message:
        return jsonify({'reply': "Bonjour ! Posez-moi une question sur nos produits."})
    
    try:
        products = Item.query.order_by(Item.created_at.desc()).limit(20).all()
        product_info = "\n".join([f"- {p.title} : {p.description[:100]}... (prix: {p.price} Ar, likes: {p.likes})" for p in products])
        
        prompt = f"""Tu es un assistant shopping pour le site MarketAI (vente à Madagascar).
Voici quelques produits disponibles :
{product_info}

L'utilisateur demande : {user_message}
Réponds de manière utile, précise et courte (max 2 phrases). Si la question ne concerne pas les produits de la liste, dis poliment que tu ne peux pas répondre."""
        
        # Utilisation du nouveau SDK
        response = client.models.generate_content(
            model="gemini-2.0-flash",  # ou "gemini-2.0-flash-lite"
            contents=prompt
        )
        reply = response.text.strip()
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        print(f"=== ERREUR GEMINI ===\n{error_details}\n===================")
        reply = "Désolé, je rencontre un problème technique. Veuillez réessayer plus tard."
    
    return jsonify({'reply': reply})

# ---------- Public ----------
@main.route('/')
def index():
    categories = ['voitures', 'motos', 'guitares', 'vêtements', 'autres']
    featured = Item.query.order_by(Item.created_at.desc()).limit(6).all()
    ai_insights = get_ai_insights(session.get('search_history', []))
    trending_items = get_trending_items(limit=4)
    return render_template('index.html', categories=categories, featured=featured, ai_insights=ai_insights, trending_items=trending_items)

@main.route('/search')
def search():
    query = request.args.get('q', '')
    category = request.args.get('category', '')
    page = request.args.get('page', 1, type=int)

    semantic_search_used = False
    if query and (not category or category == 'tous'):
        results = semantic_search(query, limit=12)
        pagination = None
        semantic_search_used = True
    else:
        items_query = Item.query
        if query:
            items_query = items_query.filter(Item.title.contains(query) | Item.description.contains(query))
        if category and category != 'tous':
            items_query = items_query.filter_by(category=category)
        pagination = items_query.order_by(Item.created_at.desc()).paginate(page=page, per_page=8, error_out=False)
        results = pagination.items

    if 'search_history' not in session:
        session['search_history'] = []
    if category and category != 'tous':
        session['search_history'].append(category)
    elif query:
        guess_cat = None
        for cat in ['voitures', 'motos', 'guitares', 'vêtements']:
            if cat in query.lower():
                guess_cat = cat
                break
        if guess_cat:
            session['search_history'].append(guess_cat)
    if len(session['search_history']) > 10:
        session['search_history'] = session['search_history'][-10:]
    session.modified = True

    if results:
        update_view_metrics([item.id for item in results])

    recommendations = get_recommendations(session.get('search_history', []), limit=4)
    ai_insights = get_ai_insights(session.get('search_history', []))
    trending_items = get_trending_items(limit=4)

    return render_template('index.html', results=results, pagination=pagination,
                           recommendations=recommendations, query=query,
                           selected_category=category, ai_insights=ai_insights,
                           trending_items=trending_items,
                           semantic_search_used=semantic_search_used)

@main.route('/click/<int:item_id>')
def track_click(item_id):
    update_click_metrics(item_id)
    item = Item.query.get_or_404(item_id)
    similaires = get_similar_items(item_id, limit=4)
    top_liked = Item.query.order_by(Item.likes.desc()).limit(5).all()
    return render_template('item_detail.html', item=item, similaires=similaires, top_liked=top_liked)

# ---------- Cart Routes ----------
@main.route('/cart')
def view_cart():
    cart = session.get('cart', {})
    cart_items = []
    total = 0
    for item_id, quantity in cart.items():
        item = Item.query.get(int(item_id))
        if item:
            subtotal = item.price * quantity
            total += subtotal
            cart_items.append({'item': item, 'quantity': quantity, 'subtotal': subtotal})
    return render_template('cart.html', cart_items=cart_items, total=total)

@main.route('/add-to-cart/<int:item_id>', methods=['POST'])
def add_to_cart(item_id):
    item = Item.query.get_or_404(item_id)
    quantity = request.form.get('quantity', 1, type=int)
    if 'cart' not in session:
        session['cart'] = {}
    item_id_str = str(item_id)
    session['cart'][item_id_str] = session['cart'].get(item_id_str, 0) + quantity
    session.modified = True
    flash(f'{item.title} ajouté au panier', 'success')
    return redirect(request.referrer or url_for('main.index'))

@main.route('/add-bulk-to-cart', methods=['POST'])
def add_bulk_to_cart():
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'Invalid request'}), 400
    item_ids = data.get('item_ids', [])
    if not item_ids:
        return jsonify({'success': False, 'error': 'No items selected'}), 400
    if 'cart' not in session:
        session['cart'] = {}
    for item_id in item_ids:
        id_str = str(item_id)
        session['cart'][id_str] = session['cart'].get(id_str, 0) + 1
    session.modified = True
    return jsonify({'success': True, 'count': len(item_ids)})

@main.route('/cart/update', methods=['POST'])
def update_cart():
    data = request.get_json()
    item_id = str(data.get('item_id'))
    quantity = int(data.get('quantity', 1))
    if 'cart' not in session:
        return jsonify({'success': False})
    if quantity <= 0:
        session['cart'].pop(item_id, None)
    else:
        session['cart'][item_id] = quantity
    session.modified = True
    return jsonify({'success': True})

@main.route('/cart/remove', methods=['POST'])
def remove_from_cart():
    data = request.get_json()
    item_ids = data.get('item_ids', [])
    if 'cart' not in session:
        session['cart'] = {}
    for item_id in item_ids:
        session['cart'].pop(str(item_id), None)
    session.modified = True
    return jsonify({'success': True})

@main.route('/cart/clear', methods=['POST'])
def clear_cart():
    session.pop('cart', None)
    session.modified = True
    flash('Panier vidé', 'info')
    return redirect(url_for('main.view_cart'))

# ---------- Checkout & Order Routes ----------
@main.route('/checkout', methods=['GET', 'POST'])
def checkout():
    direct_item_id = request.args.get('item_id')
    if direct_item_id and not session.get('cart'):
        session['cart'] = {str(direct_item_id): 1}
        session.modified = True

    cart = session.get('cart', {})
    if not cart:
        flash('Votre panier est vide', 'warning')
        return redirect(url_for('main.view_cart'))

    if request.method == 'POST':
        customer_name = request.form.get('customer_name')
        customer_email = request.form.get('customer_email')
        customer_phone = request.form.get('customer_phone')
        shipping_address = request.form.get('shipping_address')
        total = 0
        order_items_data = []
        for item_id, quantity in cart.items():
            item = Item.query.get(int(item_id))
            if item:
                subtotal = item.price * quantity
                total += subtotal
                order_items_data.append({
                    'item': item,
                    'quantity': quantity,
                    'price_at_time': item.price
                })
        order = Order(
            customer_name=customer_name,
            customer_email=customer_email,
            customer_phone=customer_phone,
            shipping_address=shipping_address,
            total_price=total,
            status='paid',
            session_id=request.cookies.get('session', '')
        )
        db.session.add(order)
        db.session.flush()
        for data in order_items_data:
            order_item = OrderItem(
                order_id=order.id,
                item_id=data['item'].id,
                quantity=data['quantity'],
                price_at_time=data['price_at_time']
            )
            db.session.add(order_item)
        db.session.commit()
        session.pop('cart', None)
        session.modified = True
        flash('Commande créée avec succès!', 'success')
        return redirect(url_for('main.order_confirmation', order_id=order.id))

    cart_items = []
    total = 0
    for item_id, quantity in cart.items():
        item = Item.query.get(int(item_id))
        if item:
            subtotal = item.price * quantity
            total += subtotal
            cart_items.append({'item': item, 'quantity': quantity, 'subtotal': subtotal})
    return render_template('checkout.html', cart_items=cart_items, total=total)

@main.route('/order/<int:order_id>')
def order_confirmation(order_id):
    order = Order.query.get_or_404(order_id)
    return render_template('order_confirmation.html', order=order)

# ---------- Like/Unlike Routes ----------
@main.route('/like/<int:item_id>', methods=['POST'])
def like_item(item_id):
    item = Item.query.get_or_404(item_id)
    item.likes += 1
    db.session.commit()
    return jsonify({'success': True, 'likes': item.likes})

@main.route('/unlike/<int:item_id>', methods=['POST'])
def unlike_item(item_id):
    item = Item.query.get_or_404(item_id)
    if item.likes > 0:
        item.likes -= 1
    db.session.commit()
    return jsonify({'success': True, 'likes': item.likes})

# ---------- Admin ----------
@admin.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    form = AdminLoginForm()
    if form.validate_on_submit():
        if form.password.data == os.getenv('ADMIN_PASSWORD', 'admin123'):
            session['admin_logged_in'] = True
            flash('Connecté admin', 'success')
            return redirect(url_for('admin.admin_dashboard'))
        else:
            flash('Mot de passe incorrect', 'danger')
    return render_template('admin_login.html', form=form)

@admin.route('/admin/logout')
def admin_logout():
    session.pop('admin_logged_in', None)
    flash('Déconnecté', 'info')
    return redirect(url_for('main.index'))

def admin_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('admin_logged_in'):
            abort(401)
        return f(*args, **kwargs)
    return decorated

@admin.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    categories = ['voitures', 'motos', 'guitares', 'vêtements', 'autres']
    query = request.args.get('q', '')
    category = request.args.get('category', '')
    page = request.args.get('page', 1, type=int)
    items_query = Item.query
    if query:
        items_query = items_query.filter(Item.title.contains(query) | Item.description.contains(query))
    if category and category != 'tous':
        items_query = items_query.filter_by(category=category)
    pagination = items_query.order_by(Item.created_at.desc()).paginate(page=page, per_page=10, error_out=False)
    items = pagination.items
    admin_metrics = get_global_metrics()

    # --- Statistiques commandes ---
    recent_orders = Order.query.order_by(Order.created_at.desc()).limit(5).all()
    pending_orders_count = Order.query.filter(Order.status == 'paid').count()
    
    today = datetime.utcnow().date()
    start_of_week = today - timedelta(days=today.weekday())
    start_of_month = today.replace(day=1)
    
    ca_today = db.session.query(func.sum(Order.total_price)).filter(func.date(Order.created_at) == today).scalar() or 0
    ca_week = db.session.query(func.sum(Order.total_price)).filter(Order.created_at >= start_of_week).scalar() or 0
    ca_month = db.session.query(func.sum(Order.total_price)).filter(Order.created_at >= start_of_month).scalar() or 0

    return render_template('admin_dashboard.html',
                           items=items,
                           pagination=pagination,
                           query=query,
                           categories=categories,
                           selected_category=category,
                           admin_metrics=admin_metrics,
                           recent_orders=recent_orders,
                           pending_orders_count=pending_orders_count,
                           ca_today=float(ca_today),
                           ca_week=float(ca_week),
                           ca_month=float(ca_month))

def save_image_file(image):
    """Upload l'image sur Cloudinary et retourne l'URL sécurisée."""
    if image and image.filename:
        try:
            print(f"Tentative d'upload de {image.filename} vers Cloudinary")
            upload_result = cloudinary.uploader.upload(image, folder="marketai")
            print(f"Upload réussi : {upload_result['secure_url']}")
            return upload_result['secure_url']
        except Exception as e:
            print(f"Erreur Cloudinary détaillée : {repr(e)}")
            flash(f"Erreur Cloudinary : {e}", "danger")
            return None
    return None

@admin.route('/admin/item/new', methods=['GET', 'POST'])
@admin_required
def new_item():
    form = ItemForm()
    if form.validate_on_submit():
        image_file = request.files.get('image')
        image_url = save_image_file(image_file)
        item = Item(
            title=form.title.data,
            description=form.description.data,
            price=form.price.data,
            category=form.category.data,
            image_url=image_url,
            tags=form.tags.data
        )
        db.session.add(item)
        db.session.commit()
        refresh_similarity()
        flash('Article ajouté', 'success')
        return redirect(url_for('admin.admin_dashboard'))
    return render_template('admin_item_form.html', form=form, legend='Nouvel article')

@admin.route('/admin/item/<int:item_id>/edit', methods=['GET', 'POST'])
@admin_required
def edit_item(item_id):
    item = Item.query.get_or_404(item_id)
    form = ItemForm(obj=item)
    if form.validate_on_submit():
        image_file = request.files.get('image')
        image_url = save_image_file(image_file)
        item.title = form.title.data
        item.description = form.description.data
        item.price = form.price.data
        item.category = form.category.data
        item.tags = form.tags.data
        if image_url:
            item.image_url = image_url
        db.session.commit()
        refresh_similarity()
        flash('Article modifié', 'success')
        return redirect(url_for('admin.admin_dashboard'))
    return render_template('admin_item_form.html', form=form, legend='Modifier article')

@admin.route('/admin/item/<int:item_id>/delete', methods=['POST'])
@admin_required
def delete_item(item_id):
    item = Item.query.get_or_404(item_id)
    db.session.delete(item)
    db.session.commit()
    refresh_similarity()
    flash('Article supprimé', 'success')
    return redirect(url_for('admin.admin_dashboard'))

@admin.route('/admin/generate_tags', methods=['POST'])
@admin_required
def generate_tags():
    data = request.get_json()
    title = data.get('title', '')
    description = data.get('description', '')
    tags = generate_tags_for_item(title, description, top_n=5)
    return {'tags': tags}

@admin.route('/admin/orders')
@admin_required
def admin_orders():
    page = request.args.get('page', 1, type=int)
    status_filter = request.args.get('status', '')
    query = Order.query
    if status_filter:
        query = query.filter_by(status=status_filter)
    pagination = query.order_by(Order.created_at.desc()).paginate(page=page, per_page=10, error_out=False)
    orders = pagination.items
    top_liked = Item.query.order_by(Item.likes.desc()).limit(10).all()
    return render_template('admin_orders.html', orders=orders, pagination=pagination, status_filter=status_filter, top_liked=top_liked)

@admin.route('/admin/order/<int:order_id>/status', methods=['POST'])
@admin_required
def update_order_status(order_id):
    order = Order.query.get_or_404(order_id)
    new_status = request.form.get('status')
    if new_status in ['paid', 'shipped', 'cancelled']:
        order.status = new_status
        db.session.commit()
        flash(f'Statut de la commande mis à jour: {new_status}', 'success')
    return redirect(url_for('admin.admin_orders'))

@admin.route('/admin/order/<int:order_id>/cancel', methods=['POST'])
@admin_required
def cancel_order(order_id):
    order = Order.query.get_or_404(order_id)
    order.status = 'cancelled'
    db.session.commit()
    flash('Commande annulée', 'success')
    return redirect(url_for('admin.admin_orders'))