from flask import Blueprint, render_template, request, session, redirect, url_for, flash, abort, current_app
from app.extensions import db
from app.models import Item
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