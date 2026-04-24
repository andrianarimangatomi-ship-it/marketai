from flask import Blueprint, render_template, request, session, redirect, url_for, flash, abort, current_app, jsonify
from app.extensions import db
from app.models import Item, Order, OrderItem
from app.forms import ItemForm, AdminLoginForm
from app.ia import get_recommendations, update_click_metrics, update_view_metrics, get_ai_insights, get_trending_items, get_global_metrics
from app.similarite import get_similar_items, refresh_similarity
from app.tags_ia import generate_tags_for_item  # <-- AJOUT
from werkzeug.utils import secure_filename
import os
import uuid

main = Blueprint('main', __name__)
admin = Blueprint('admin', __name__)

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

    return render_template('index.html', results=results, pagination=pagination, recommendations=recommendations, query=query, selected_category=category, ai_insights=ai_insights, trending_items=trending_items)

@main.route('/click/<int:item_id>')
def track_click(item_id):
    update_click_metrics(item_id)
    item = Item.query.get_or_404(item_id)
    similaires = get_similar_items(item_id, limit=4)
    return render_template('item_detail.html', item=item, similaires=similaires)

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
            cart_items.append({
                'item': item,
                'quantity': quantity,
                'subtotal': subtotal
            })

    return render_template('cart.html', cart_items=cart_items, total=total)

@main.route('/add-to-cart/<int:item_id>', methods=['POST'])
def add_to_cart(item_id):
    item = Item.query.get_or_404(item_id)
    quantity = request.form.get('quantity', 1, type=int)

    if 'cart' not in session:
        session['cart'] = {}

    item_id_str = str(item_id)
    if item_id_str in session['cart']:
        session['cart'][item_id_str] += quantity
    else:
        session['cart'][item_id_str] = quantity

    session.modified = True
    flash(f'{item.title} ajouté au panier', 'success')
    return redirect(request.referrer or url_for('main.index'))

@main.route('/add-bulk-to-cart', methods=['POST'])
def add_bulk_to_cart():
    """Add multiple selected items to cart"""
    item_ids = request.form.getlist('item_ids')

    if 'cart' not in session:
        session['cart'] = {}

    for item_id in item_ids:
        item_id_str = str(item_id)
        if item_id_str in session['cart']:
            session['cart'][item_id_str] += 1
        else:
            session['cart'][item_id_str] = 1

    session.modified = True
    flash(f'{len(item_ids)} article(s) ajouté(s) au panier', 'success')
    return redirect(request.referrer or url_for('main.index'))

@main.route('/cart/update', methods=['POST'])
def update_cart():
    data = request.get_json()
    item_id = str(data.get('item_id'))
    quantity = int(data.get('quantity', 1))

    if 'cart' not in session:
        session['cart'] = {}

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
    cart = session.get('cart', {})

    if not cart:
        flash('Votre panier est vide', 'warning')
        return redirect(url_for('main.view_cart'))

    if request.method == 'POST':
        customer_name = request.form.get('customer_name')
        customer_email = request.form.get('customer_email')
        customer_phone = request.form.get('customer_phone')
        shipping_address = request.form.get('shipping_address')

        # Calculate total
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

        # Create order
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
        db.session.flush()  # Get order.id without committing

        # Add order items
        for data in order_items_data:
            order_item = OrderItem(
                order_id=order.id,
                item_id=data['item'].id,
                quantity=data['quantity'],
                price_at_time=data['price_at_time']
            )
            db.session.add(order_item)

        db.session.commit()

        # Clear cart
        session.pop('cart', None)
        session.modified = True

        flash('Commande créée avec succès!', 'success')
        return redirect(url_for('main.order_confirmation', order_id=order.id))

    # GET request - show checkout form
    cart_items = []
    total = 0

    for item_id, quantity in cart.items():
        item = Item.query.get(int(item_id))
        if item:
            subtotal = item.price * quantity
            total += subtotal
            cart_items.append({
                'item': item,
                'quantity': quantity,
                'subtotal': subtotal
            })

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

    return render_template('admin_dashboard.html', items=items, pagination=pagination, query=query, categories=categories, selected_category=category, admin_metrics=admin_metrics)

def save_image_file(image):
    if image and image.filename:
        filename = secure_filename(image.filename)
        if filename:
            filename = f"{uuid.uuid4().hex}_{filename}"
            save_path = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
            image.save(save_path)
            return f"/static/uploads/{filename}"
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
            tags=form.tags.data  # <-- AJOUT pour sauvegarder les tags
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
        item.tags = form.tags.data  # <-- AJOUT
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

# ---------- AJOUT : route pour générer des tags automatiquement ----------
@admin.route('/admin/generate_tags', methods=['POST'])
@admin_required
def generate_tags():
    data = request.get_json()
    title = data.get('title', '')
    description = data.get('description', '')
    tags = generate_tags_for_item(title, description, top_n=5)
    return {'tags': tags}

# ---------- Admin Orders ----------
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

    # Top liked items
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