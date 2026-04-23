import random
from collections import Counter
from app.models import Item
from app.extensions import db


DEFAULT_CATEGORIES = ['voitures', 'motos', 'guitares', 'vêtements', 'autres']


def get_recommendations(session_history, limit=4):
    if not session_history:
        items = Item.query.order_by(Item.created_at.desc()).limit(limit * 2).all()
        if len(items) < limit:
            items = Item.query.all()
        random.shuffle(items)
        return items[:limit]

    counts = Counter(session_history)
    total = sum(counts.values())
    top_categories = [cat for cat, _ in counts.most_common(2)]
    exploration = 0.25 if len(counts) < 3 else 0.15

    candidates = []
    for category in top_categories:
        items_cat = Item.query.filter_by(category=category).all()
        if not items_cat:
            continue
        category_weight = counts[category] / total
        for item in items_cat:
            score = item.reinforcement_score() * 0.6
            score += item.score_popularite() * 0.25
            score += category_weight * 0.15
            score += random.uniform(0, exploration)
            candidates.append((score, item))

    candidates.sort(reverse=True, key=lambda x: x[0])
    recommended = [item for _, item in candidates[:limit]]

    if len(recommended) < limit:
        others = Item.query.filter(Item.category.notin_(top_categories)).all()
        random.shuffle(others)
        recommended += others[:limit - len(recommended)]

    return recommended


def get_category_rewards(session_history, limit=3):
    counts = Counter(session_history)
    if not counts:
        return []

    total = sum(counts.values())
    rewards = []
    for category, count in counts.most_common(limit):
        items_cat = Item.query.filter_by(category=category).all()
        avg_ctr = 0.0
        if items_cat:
            avg_ctr = sum(item.score_popularite() for item in items_cat) / len(items_cat)
        rewards.append({
            'name': category,
            'weight': count / total,
            'avg_ctr': avg_ctr
        })
    return rewards


def get_ai_insights(session_history):
    top_categories = get_category_rewards(session_history, limit=3)
    if not top_categories:
        recent = Item.query.order_by(Item.created_at.desc()).limit(3).all()
        return {
            'top_categories': [{'name': item.category, 'weight': 0, 'avg_ctr': item.score_popularite()} for item in recent],
            'reason': "L'IA explore encore les premières données et favorise les nouvelles entrées.",
            'exploration_rate': 0.6,
            'exploitation_rate': 0.4
        }

    exploration_rate = max(0.12, 0.45 - len(session_history) * 0.02)
    if exploration_rate > 0.5:
        exploration_rate = 0.5

    return {
        'top_categories': top_categories,
        'reason': "",
        'exploration_rate': exploration_rate,
        'exploitation_rate': 1 - exploration_rate
    }


def get_trending_items(limit=4):
    items = Item.query.all()
    if not items:
        return []
    sorted_items = sorted(items, key=lambda item: item.reinforcement_score(), reverse=True)
    return sorted_items[:limit]


def get_global_metrics():
    items = Item.query.all()
    total_views = sum(item.views for item in items)
    total_clicks = sum(item.clicks for item in items)
    avg_ctr = (total_clicks / total_views) if total_views else 0.0

    category_stats = {}
    for item in items:
        stats = category_stats.setdefault(item.category, {'views': 0, 'clicks': 0})
        stats['views'] += item.views
        stats['clicks'] += item.clicks

    top_categories = []
    for category, stats in category_stats.items():
        ctr = (stats['clicks'] / stats['views']) if stats['views'] else 0.0
        top_categories.append({
            'category': category,
            'views': stats['views'],
            'clicks': stats['clicks'],
            'ctr': ctr
        })
    top_categories.sort(key=lambda item: item['ctr'], reverse=True)

    top_items = sorted(items, key=lambda item: item.reinforcement_score(), reverse=True)[:3]

    return {
        'total_items': len(items),
        'total_views': total_views,
        'total_clicks': total_clicks,
        'avg_ctr': avg_ctr,
        'top_categories': top_categories[:3],
        'top_items': top_items
    }

def update_click_metrics(item_id):
    item = Item.query.get(item_id)
    if item:
        item.clicks += 1
        db.session.commit()

def update_view_metrics(item_ids):
    for item_id in item_ids:
        item = Item.query.get(item_id)
        if item:
            item.views += 1
    db.session.commit()