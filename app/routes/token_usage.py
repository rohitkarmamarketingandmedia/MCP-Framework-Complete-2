# app/routes/token_usage.py
"""
Token usage & cost reporting API endpoints.
Provides dashboards with per-client, per-feature, per-model cost breakdowns.
"""
import logging
from datetime import datetime, timedelta

from flask import Blueprint, jsonify, request
from sqlalchemy import func, case, extract

from app.database import db
from app.models.db_models import DBTokenUsage

logger = logging.getLogger(__name__)

token_usage_bp = Blueprint('token_usage', __name__)


@token_usage_bp.route('/summary', methods=['GET'])
def get_usage_summary():
    """
    GET /api/usage/summary?days=30
    Returns aggregate token usage and cost for the given period.
    """
    days = request.args.get('days', 30, type=int)
    since = datetime.utcnow() - timedelta(days=days)

    rows = db.session.query(
        func.count(DBTokenUsage.id).label('total_calls'),
        func.coalesce(func.sum(DBTokenUsage.input_tokens), 0).label('total_input_tokens'),
        func.coalesce(func.sum(DBTokenUsage.output_tokens), 0).label('total_output_tokens'),
        func.coalesce(func.sum(DBTokenUsage.total_tokens), 0).label('total_tokens'),
        func.coalesce(func.sum(DBTokenUsage.cost_usd), 0).label('total_cost'),
    ).filter(DBTokenUsage.created_at >= since).first()

    return jsonify({
        'period_days': days,
        'total_calls': rows.total_calls or 0,
        'total_input_tokens': rows.total_input_tokens or 0,
        'total_output_tokens': rows.total_output_tokens or 0,
        'total_tokens': rows.total_tokens or 0,
        'total_cost_usd': round(float(rows.total_cost or 0), 4),
    })


@token_usage_bp.route('/by-feature', methods=['GET'])
def get_usage_by_feature():
    """
    GET /api/usage/by-feature?days=30
    Returns cost breakdown per feature (blog_generation, chatbot, fact_check, etc.)
    """
    days = request.args.get('days', 30, type=int)
    since = datetime.utcnow() - timedelta(days=days)

    rows = db.session.query(
        DBTokenUsage.feature,
        func.count(DBTokenUsage.id).label('calls'),
        func.coalesce(func.sum(DBTokenUsage.total_tokens), 0).label('tokens'),
        func.coalesce(func.sum(DBTokenUsage.cost_usd), 0).label('cost'),
    ).filter(
        DBTokenUsage.created_at >= since
    ).group_by(DBTokenUsage.feature).order_by(func.sum(DBTokenUsage.cost_usd).desc()).all()

    return jsonify({
        'period_days': days,
        'features': [{
            'feature': r.feature,
            'calls': r.calls,
            'total_tokens': r.tokens,
            'cost_usd': round(float(r.cost), 4),
        } for r in rows]
    })


@token_usage_bp.route('/by-client', methods=['GET'])
def get_usage_by_client():
    """
    GET /api/usage/by-client?days=30
    Returns cost breakdown per client.
    """
    days = request.args.get('days', 30, type=int)
    since = datetime.utcnow() - timedelta(days=days)

    rows = db.session.query(
        DBTokenUsage.client_id,
        func.count(DBTokenUsage.id).label('calls'),
        func.coalesce(func.sum(DBTokenUsage.total_tokens), 0).label('tokens'),
        func.coalesce(func.sum(DBTokenUsage.cost_usd), 0).label('cost'),
    ).filter(
        DBTokenUsage.created_at >= since,
        DBTokenUsage.client_id.isnot(None)
    ).group_by(DBTokenUsage.client_id).order_by(func.sum(DBTokenUsage.cost_usd).desc()).all()

    return jsonify({
        'period_days': days,
        'clients': [{
            'client_id': r.client_id,
            'calls': r.calls,
            'total_tokens': r.tokens,
            'cost_usd': round(float(r.cost), 4),
        } for r in rows]
    })


@token_usage_bp.route('/by-model', methods=['GET'])
def get_usage_by_model():
    """
    GET /api/usage/by-model?days=30
    Returns cost breakdown per AI model.
    """
    days = request.args.get('days', 30, type=int)
    since = datetime.utcnow() - timedelta(days=days)

    rows = db.session.query(
        DBTokenUsage.model,
        func.count(DBTokenUsage.id).label('calls'),
        func.coalesce(func.sum(DBTokenUsage.input_tokens), 0).label('input_tokens'),
        func.coalesce(func.sum(DBTokenUsage.output_tokens), 0).label('output_tokens'),
        func.coalesce(func.sum(DBTokenUsage.cost_usd), 0).label('cost'),
    ).filter(
        DBTokenUsage.created_at >= since
    ).group_by(DBTokenUsage.model).order_by(func.sum(DBTokenUsage.cost_usd).desc()).all()

    return jsonify({
        'period_days': days,
        'models': [{
            'model': r.model,
            'calls': r.calls,
            'input_tokens': r.input_tokens,
            'output_tokens': r.output_tokens,
            'cost_usd': round(float(r.cost), 4),
        } for r in rows]
    })


@token_usage_bp.route('/daily', methods=['GET'])
def get_daily_usage():
    """
    GET /api/usage/daily?days=30
    Returns daily cost totals for charting.
    """
    days = request.args.get('days', 30, type=int)
    since = datetime.utcnow() - timedelta(days=days)

    rows = db.session.query(
        func.date(DBTokenUsage.created_at).label('day'),
        func.count(DBTokenUsage.id).label('calls'),
        func.coalesce(func.sum(DBTokenUsage.total_tokens), 0).label('tokens'),
        func.coalesce(func.sum(DBTokenUsage.cost_usd), 0).label('cost'),
    ).filter(
        DBTokenUsage.created_at >= since
    ).group_by(func.date(DBTokenUsage.created_at)).order_by(func.date(DBTokenUsage.created_at)).all()

    return jsonify({
        'period_days': days,
        'daily': [{
            'date': str(r.day),
            'calls': r.calls,
            'total_tokens': r.tokens,
            'cost_usd': round(float(r.cost), 4),
        } for r in rows]
    })


@token_usage_bp.route('/recent', methods=['GET'])
def get_recent_usage():
    """
    GET /api/usage/recent?limit=50
    Returns the most recent token usage records.
    """
    limit = request.args.get('limit', 50, type=int)
    limit = min(limit, 200)

    records = DBTokenUsage.query.order_by(
        DBTokenUsage.created_at.desc()
    ).limit(limit).all()

    return jsonify({
        'records': [r.to_dict() for r in records]
    })
