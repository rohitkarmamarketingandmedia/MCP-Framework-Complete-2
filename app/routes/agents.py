"""
Karma Marketing + Media - Agent Routes
API endpoints for managing AI agent configurations
"""
from flask import Blueprint, request, jsonify
from datetime import datetime

from app.routes.auth import token_required, admin_required
from app.services.agent_service import agent_service
from app.services.audit_service import audit_service
from app.models.db_models import DBAgentConfig

agents_bp = Blueprint('agents', __name__)


@agents_bp.route('/', methods=['GET'])
@token_required
def get_agents(current_user):
    """
    Get all agents
    
    GET /api/agents?category=content
    """
    category = request.args.get('category')
    agents = agent_service.get_all_agents(category=category)
    
    return jsonify({
        'agents': [a.to_dict() for a in agents],
        'categories': list(set(a.category for a in agent_service.get_all_agents()))
    })


@agents_bp.route('/<agent_id>', methods=['GET'])
@token_required
def get_agent(current_user, agent_id):
    """
    Get a specific agent
    
    GET /api/agents/<agent_id>
    """
    agent = agent_service.get_agent_by_id(agent_id)
    if not agent:
        return jsonify({'error': 'Agent not found'}), 404
    
    return jsonify({'agent': agent.to_dict()})


@agents_bp.route('/<agent_id>', methods=['PUT'])
@admin_required
def update_agent(current_user, agent_id):
    """
    Update an agent's configuration
    
    PUT /api/agents/<agent_id>
    {
        "system_prompt": "Updated prompt...",
        "temperature": 0.7,
        "model": "gpt-4o-mini",
        "change_note": "Made the tone more friendly"
    }
    """
    data = request.get_json() or {}
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    
    change_note = data.pop('change_note', None)
    
    result = agent_service.update_agent(
        agent_id=agent_id,
        updates=data,
        changed_by=current_user.email,
        change_note=change_note
    )
    
    if result.get('error'):
        return jsonify(result), 400
    
    # Log the update
    audit_service.log_update(
        resource_type='agent',
        resource_id=agent_id,
        resource_name=result['agent']['name'],
        user_id=current_user.id,
        user_email=current_user.email,
        changes=change_note or 'Agent configuration updated'
    )
    
    return jsonify(result)


@agents_bp.route('/<agent_id>/test', methods=['POST'])
@token_required
def test_agent(current_user, agent_id):
    """
    Test an agent with sample input
    
    POST /api/agents/<agent_id>/test
    {
        "input": "Write a blog post about HVAC maintenance in Tampa",
        "variables": {
            "tone": "professional",
            "industry": "HVAC"
        }
    }
    """
    data = request.get_json() or {}
    if not data or not data.get('input'):
        return jsonify({'error': 'input is required'}), 400
    
    result = agent_service.test_agent(
        agent_id=agent_id,
        test_input=data['input'],
        variables=data.get('variables', {})
    )
    
    # Log the test
    audit_service.log(
        action='test',
        resource_type='agent',
        resource_id=agent_id,
        user_id=current_user.id,
        user_email=current_user.email,
        description='Agent test executed',
        status='success' if result.get('success') else 'failure'
    )
    
    return jsonify(result)


@agents_bp.route('/<agent_id>/versions', methods=['GET'])
@token_required
def get_agent_versions(current_user, agent_id):
    """
    Get version history for an agent
    
    GET /api/agents/<agent_id>/versions?limit=10
    """
    agent = agent_service.get_agent_by_id(agent_id)
    if not agent:
        return jsonify({'error': 'Agent not found'}), 404
    
    limit = min(int(request.args.get('limit', 10)), 50)
    versions = agent_service.get_version_history(agent_id, limit=limit)
    
    return jsonify({
        'agent_id': agent_id,
        'current_version': agent.version,
        'versions': [v.to_dict() for v in versions]
    })


@agents_bp.route('/<agent_id>/versions/<int:version_id>/rollback', methods=['POST'])
@admin_required
def rollback_agent(current_user, agent_id, version_id):
    """
    Rollback an agent to a previous version
    
    POST /api/agents/<agent_id>/versions/<version_id>/rollback
    """
    result = agent_service.rollback_to_version(
        agent_id=agent_id,
        version_id=version_id,
        changed_by=current_user.email
    )
    
    if result.get('error'):
        return jsonify(result), 400
    
    # Log the rollback
    audit_service.log(
        action='update',
        resource_type='agent',
        resource_id=agent_id,
        user_id=current_user.id,
        user_email=current_user.email,
        description=f"Rolled back to version {result['rolled_back_to']}"
    )
    
    return jsonify(result)


@agents_bp.route('/<agent_id>/duplicate', methods=['POST'])
@admin_required
def duplicate_agent(current_user, agent_id):
    """
    Create a copy of an agent (for A/B testing)
    
    POST /api/agents/<agent_id>/duplicate
    {
        "name": "content_writer_v2",
        "display_name": "Content Writer V2"
    }
    """
    data = request.get_json() or {}
    if not data or not data.get('name') or not data.get('display_name'):
        return jsonify({'error': 'name and display_name are required'}), 400
    
    result = agent_service.duplicate_agent(
        agent_id=agent_id,
        new_name=data['name'],
        new_display_name=data['display_name']
    )
    
    if result.get('error'):
        return jsonify(result), 400
    
    # Log the duplication
    audit_service.log_create(
        resource_type='agent',
        resource_id=result['agent']['id'],
        resource_name=data['name'],
        user_id=current_user.id,
        user_email=current_user.email
    )
    
    return jsonify(result), 201


@agents_bp.route('/initialize', methods=['POST'])
@admin_required
def initialize_agents(current_user):
    """
    Initialize default agents (creates them if they don't exist)
    
    POST /api/agents/initialize
    """
    try:
        created = agent_service.initialize_default_agents()
        
        if created > 0:
            audit_service.log(
                action='create',
                resource_type='agent',
                description=f'Initialized {created} default agents',
                user_id=current_user.id,
                user_email=current_user.email
            )
        
        return jsonify({
            'message': f'Initialized {created} new agents',
            'created': created
        })
    except Exception as e:
        return jsonify({'error': 'An error occurred. Please try again.'}), 500


@agents_bp.route('/prompt/<agent_name>', methods=['GET'])
@token_required
def get_agent_prompt(current_user, agent_name):
    """
    Get just the system prompt for an agent (for use in other services)
    
    GET /api/agents/prompt/content_writer?tone=professional&industry=HVAC
    """
    # Get variables from query string
    variables = {k: v for k, v in request.args.items()}
    
    prompt = agent_service.get_prompt(agent_name, **variables)
    
    if not prompt:
        return jsonify({'error': f'Agent {agent_name} not found'}), 404
    
    agent = agent_service.get_agent(agent_name)
    
    return jsonify({
        'agent': agent_name,
        'prompt': prompt,
        'model': agent.model,
        'temperature': agent.temperature,
        'max_tokens': agent.max_tokens
    })


@agents_bp.route('/categories', methods=['GET'])
@token_required
def get_categories(current_user):
    """Get list of agent categories"""
    agents = agent_service.get_all_agents()
    categories = {}
    
    for agent in agents:
        if agent.category not in categories:
            categories[agent.category] = []
        categories[agent.category].append({
            'id': agent.id,
            'name': agent.name,
            'display_name': agent.display_name
        })
    
    return jsonify({'categories': categories})
