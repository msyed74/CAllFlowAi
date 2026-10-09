"""0001_initial_schema

Revision ID: 0001_initial_schema
Revises: 
Create Date: 2026-10-09 12:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '0001_initial_schema'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Organizations
    op.create_table(
        'organizations',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('slug', sa.String(length=100), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('twilio_account_sid', sa.String(length=255), nullable=True),
        sa.Column('twilio_auth_token_encrypted', sa.Text(), nullable=True),
        sa.Column('twilio_phone_number', sa.String(length=50), nullable=True),
        sa.Column('openai_api_key_encrypted', sa.Text(), nullable=True),
        sa.Column('default_voice_id', sa.String(length=50), nullable=False),
        sa.Column('default_language', sa.String(length=10), nullable=False),
        sa.Column('max_concurrent_calls', sa.Integer(), nullable=False),
        sa.Column('monthly_call_minutes_limit', sa.Integer(), nullable=False),
        sa.Column('current_month_minutes_used', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('slug')
    )
    op.create_index(op.f('ix_organizations_slug'), 'organizations', ['slug'], unique=True)
    op.create_index(op.f('ix_organizations_status'), 'organizations', ['status'], unique=False)

    # 2. Roles
    op.create_table(
        'roles',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('organization_id', sa.String(length=36), nullable=False),
        sa.Column('name', sa.String(length=50), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('permissions', sa.JSON(), nullable=False),
        sa.Column('is_system_role', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('organization_id', 'name', name='uq_roles_org_name')
    )
    op.create_index(op.f('ix_roles_organization_id'), 'roles', ['organization_id'], unique=False)

    # 3. Users
    op.create_table(
        'users',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('organization_id', sa.String(length=36), nullable=False),
        sa.Column('role_id', sa.String(length=36), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('password_hash', sa.String(length=255), nullable=False),
        sa.Column('first_name', sa.String(length=100), nullable=False),
        sa.Column('last_name', sa.String(length=100), nullable=False),
        sa.Column('phone_number', sa.String(length=50), nullable=True),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['role_id'], ['roles.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('email')
    )
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)
    op.create_index(op.f('ix_users_organization_id'), 'users', ['organization_id'], unique=False)
    op.create_index(op.f('ix_users_role_id'), 'users', ['role_id'], unique=False)

    # 4. Leads
    op.create_table(
        'leads',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('organization_id', sa.String(length=36), nullable=False),
        sa.Column('assigned_user_id', sa.String(length=36), nullable=True),
        sa.Column('first_name', sa.String(length=100), nullable=True),
        sa.Column('last_name', sa.String(length=100), nullable=True),
        sa.Column('email', sa.String(length=255), nullable=True),
        sa.Column('phone_number', sa.String(length=50), nullable=False),
        sa.Column('company_name', sa.String(length=255), nullable=True),
        sa.Column('job_title', sa.String(length=150), nullable=True),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('lead_source', sa.String(length=100), nullable=False),
        sa.Column('timezone', sa.String(length=50), nullable=False),
        sa.Column('custom_fields', sa.JSON(), nullable=False),
        sa.Column('last_called_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('call_attempts', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['assigned_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('organization_id', 'phone_number', name='uq_leads_org_phone')
    )
    op.create_index(op.f('ix_leads_assigned_user_id'), 'leads', ['assigned_user_id'], unique=False)
    op.create_index(op.f('ix_leads_organization_id'), 'leads', ['organization_id'], unique=False)
    op.create_index(op.f('ix_leads_phone_number'), 'leads', ['phone_number'], unique=False)
    op.create_index(op.f('ix_leads_status'), 'leads', ['status'], unique=False)

    # 5. Customers
    op.create_table(
        'customers',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('organization_id', sa.String(length=36), nullable=False),
        sa.Column('lead_id', sa.String(length=36), nullable=True),
        sa.Column('external_crm_id', sa.String(length=255), nullable=True),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=True),
        sa.Column('phone_number', sa.String(length=50), nullable=False),
        sa.Column('account_status', sa.String(length=50), nullable=False),
        sa.Column('metadata_json', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['lead_id'], ['leads.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_customers_external_crm_id'), 'customers', ['external_crm_id'], unique=False)
    op.create_index(op.f('ix_customers_lead_id'), 'customers', ['lead_id'], unique=False)
    op.create_index(op.f('ix_customers_organization_id'), 'customers', ['organization_id'], unique=False)

    # 6. Campaigns
    op.create_table(
        'campaigns',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('organization_id', sa.String(length=36), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('voice_agent_prompt', sa.Text(), nullable=False),
        sa.Column('caller_phone_number', sa.String(length=50), nullable=False),
        sa.Column('daily_start_time', sa.String(length=10), nullable=False),
        sa.Column('daily_end_time', sa.String(length=10), nullable=False),
        sa.Column('allowed_days', sa.JSON(), nullable=False),
        sa.Column('max_retries_per_lead', sa.Integer(), nullable=False),
        sa.Column('retry_delay_hours', sa.Integer(), nullable=False),
        sa.Column('concurrent_calls_limit', sa.Integer(), nullable=False),
        sa.Column('total_leads_count', sa.Integer(), nullable=False),
        sa.Column('completed_calls_count', sa.Integer(), nullable=False),
        sa.Column('successful_bookings_count', sa.Integer(), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('ended_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_campaigns_organization_id'), 'campaigns', ['organization_id'], unique=False)
    op.create_index(op.f('ix_campaigns_status'), 'campaigns', ['status'], unique=False)

    # 7. Calls
    op.create_table(
        'calls',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('organization_id', sa.String(length=36), nullable=False),
        sa.Column('campaign_id', sa.String(length=36), nullable=True),
        sa.Column('lead_id', sa.String(length=36), nullable=True),
        sa.Column('customer_id', sa.String(length=36), nullable=True),
        sa.Column('twilio_call_sid', sa.String(length=100), nullable=False),
        sa.Column('direction', sa.String(length=20), nullable=False),
        sa.Column('from_number', sa.String(length=50), nullable=False),
        sa.Column('to_number', sa.String(length=50), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('termination_reason', sa.String(length=100), nullable=True),
        sa.Column('duration_seconds', sa.Integer(), nullable=False),
        sa.Column('billed_seconds', sa.Integer(), nullable=False),
        sa.Column('audio_recording_url', sa.Text(), nullable=True),
        sa.Column('initiated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('answered_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('ended_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['campaign_id'], ['campaigns.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['customer_id'], ['customers.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['lead_id'], ['leads.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('twilio_call_sid')
    )
    op.create_index(op.f('ix_calls_campaign_id'), 'calls', ['campaign_id'], unique=False)
    op.create_index(op.f('ix_calls_customer_id'), 'calls', ['customer_id'], unique=False)
    op.create_index(op.f('ix_calls_lead_id'), 'calls', ['lead_id'], unique=False)
    op.create_index(op.f('ix_calls_organization_id'), 'calls', ['organization_id'], unique=False)
    op.create_index(op.f('ix_calls_status'), 'calls', ['status'], unique=False)
    op.create_index(op.f('ix_calls_twilio_call_sid'), 'calls', ['twilio_call_sid'], unique=True)

    # 8. Call Events
    op.create_table(
        'call_events',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('call_id', sa.String(length=36), nullable=False),
        sa.Column('event_type', sa.String(length=100), nullable=False),
        sa.Column('payload', sa.JSON(), nullable=False),
        sa.Column('timestamp_ms', sa.BigInteger(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['call_id'], ['calls.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_call_events_call_id'), 'call_events', ['call_id'], unique=False)

    # 9. Call Transcripts
    op.create_table(
        'call_transcripts',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('call_id', sa.String(length=36), nullable=False),
        sa.Column('speaker_role', sa.String(length=20), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('start_time_ms', sa.Integer(), nullable=False),
        sa.Column('end_time_ms', sa.Integer(), nullable=False),
        sa.Column('speech_confidence', sa.Float(), nullable=True),
        sa.Column('is_interrupted', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['call_id'], ['calls.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_call_transcripts_call_id'), 'call_transcripts', ['call_id'], unique=False)

    # 10. Call Summaries
    op.create_table(
        'call_summaries',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('call_id', sa.String(length=36), nullable=False),
        sa.Column('organization_id', sa.String(length=36), nullable=False),
        sa.Column('executive_summary', sa.Text(), nullable=False),
        sa.Column('sentiment_overall', sa.String(length=30), nullable=True),
        sa.Column('primary_intent', sa.String(length=100), nullable=True),
        sa.Column('qualification_status', sa.String(length=50), nullable=True),
        sa.Column('pain_points', sa.JSON(), nullable=False),
        sa.Column('objections_raised', sa.JSON(), nullable=False),
        sa.Column('action_items', sa.JSON(), nullable=False),
        sa.Column('recommended_follow_up', sa.Text(), nullable=True),
        sa.Column('raw_llm_response', sa.JSON(), nullable=True),
        sa.Column('generated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['call_id'], ['calls.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('call_id')
    )
    op.create_index(op.f('ix_call_summaries_call_id'), 'call_summaries', ['call_id'], unique=True)
    op.create_index(op.f('ix_call_summaries_organization_id'), 'call_summaries', ['organization_id'], unique=False)

    # 11. Appointments
    op.create_table(
        'appointments',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('organization_id', sa.String(length=36), nullable=False),
        sa.Column('call_id', sa.String(length=36), nullable=True),
        sa.Column('lead_id', sa.String(length=36), nullable=False),
        sa.Column('assigned_user_id', sa.String(length=36), nullable=True),
        sa.Column('start_time', sa.DateTime(timezone=True), nullable=False),
        sa.Column('end_time', sa.DateTime(timezone=True), nullable=False),
        sa.Column('timezone', sa.String(length=50), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('meeting_title', sa.String(length=255), nullable=False),
        sa.Column('meeting_url', sa.Text(), nullable=True),
        sa.Column('calendar_event_id', sa.String(length=255), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['assigned_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['call_id'], ['calls.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['lead_id'], ['leads.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_appointments_call_id'), 'appointments', ['call_id'], unique=False)
    op.create_index(op.f('ix_appointments_lead_id'), 'appointments', ['lead_id'], unique=False)
    op.create_index(op.f('ix_appointments_organization_id'), 'appointments', ['organization_id'], unique=False)
    op.create_index(op.f('ix_appointments_start_time'), 'appointments', ['start_time'], unique=False)

    # 12. Embeddings Metadata
    op.create_table(
        'embeddings_metadata',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('model_name', sa.String(length=100), nullable=False),
        sa.Column('dimension', sa.Integer(), nullable=False),
        sa.Column('distance_metric', sa.String(length=30), nullable=False),
        sa.Column('qdrant_collection_name', sa.String(length=100), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )

    # 13. Knowledge Documents
    op.create_table(
        'knowledge_documents',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('organization_id', sa.String(length=36), nullable=False),
        sa.Column('embeddings_metadata_id', sa.String(length=36), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('source_type', sa.String(length=50), nullable=False),
        sa.Column('file_s3_url', sa.Text(), nullable=True),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('total_chunks', sa.Integer(), nullable=False),
        sa.Column('metadata_json', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['embeddings_metadata_id'], ['embeddings_metadata.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_knowledge_documents_organization_id'), 'knowledge_documents', ['organization_id'], unique=False)

    # 14. Knowledge Chunks
    op.create_table(
        'knowledge_chunks',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('document_id', sa.String(length=36), nullable=False),
        sa.Column('chunk_index', sa.Integer(), nullable=False),
        sa.Column('chunk_text', sa.Text(), nullable=False),
        sa.Column('token_count', sa.Integer(), nullable=False),
        sa.Column('qdrant_point_id', sa.String(length=36), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['document_id'], ['knowledge_documents.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_knowledge_chunks_document_id'), 'knowledge_chunks', ['document_id'], unique=False)
    op.create_index(op.f('ix_knowledge_chunks_qdrant_point_id'), 'knowledge_chunks', ['qdrant_point_id'], unique=False)

    # 15. Agent Sessions
    op.create_table(
        'agent_sessions',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('call_id', sa.String(length=36), nullable=False),
        sa.Column('openai_session_id', sa.String(length=255), nullable=True),
        sa.Column('system_prompt_snapshot', sa.Text(), nullable=False),
        sa.Column('voice_persona', sa.String(length=50), nullable=False),
        sa.Column('active_tools', sa.JSON(), nullable=False),
        sa.Column('temperature', sa.Float(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['call_id'], ['calls.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('call_id')
    )
    op.create_index(op.f('ix_agent_sessions_call_id'), 'agent_sessions', ['call_id'], unique=True)

    # 16. Agent Tool Calls
    op.create_table(
        'agent_tool_calls',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('agent_session_id', sa.String(length=36), nullable=False),
        sa.Column('call_id', sa.String(length=36), nullable=False),
        sa.Column('tool_name', sa.String(length=100), nullable=False),
        sa.Column('tool_call_id', sa.String(length=100), nullable=False),
        sa.Column('arguments', sa.JSON(), nullable=False),
        sa.Column('response', sa.JSON(), nullable=True),
        sa.Column('execution_time_ms', sa.Integer(), nullable=False),
        sa.Column('is_successful', sa.Boolean(), nullable=False),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['agent_session_id'], ['agent_sessions.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['call_id'], ['calls.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_agent_tool_calls_agent_session_id'), 'agent_tool_calls', ['agent_session_id'], unique=False)
    op.create_index(op.f('ix_agent_tool_calls_call_id'), 'agent_tool_calls', ['call_id'], unique=False)
    op.create_index(op.f('ix_agent_tool_calls_tool_name'), 'agent_tool_calls', ['tool_name'], unique=False)

    # 17. Lead Scores
    op.create_table(
        'lead_scores',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('call_id', sa.String(length=36), nullable=False),
        sa.Column('lead_id', sa.String(length=36), nullable=False),
        sa.Column('organization_id', sa.String(length=36), nullable=False),
        sa.Column('composite_score', sa.Integer(), nullable=False),
        sa.Column('budget_score', sa.Integer(), nullable=True),
        sa.Column('authority_score', sa.Integer(), nullable=True),
        sa.Column('need_score', sa.Integer(), nullable=True),
        sa.Column('timeline_score', sa.Integer(), nullable=True),
        sa.Column('score_breakdown', sa.JSON(), nullable=False),
        sa.Column('reasoning', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['call_id'], ['calls.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['lead_id'], ['leads.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_lead_scores_call_id'), 'lead_scores', ['call_id'], unique=False)
    op.create_index(op.f('ix_lead_scores_composite_score'), 'lead_scores', ['composite_score'], unique=False)
    op.create_index(op.f('ix_lead_scores_lead_id'), 'lead_scores', ['lead_id'], unique=False)
    op.create_index(op.f('ix_lead_scores_organization_id'), 'lead_scores', ['organization_id'], unique=False)

    # 18. Automation Jobs
    op.create_table(
        'automation_jobs',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('organization_id', sa.String(length=36), nullable=False),
        sa.Column('call_id', sa.String(length=36), nullable=True),
        sa.Column('workflow_name', sa.String(length=100), nullable=False),
        sa.Column('target_endpoint', sa.Text(), nullable=False),
        sa.Column('payload', sa.JSON(), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('retry_count', sa.Integer(), nullable=False),
        sa.Column('max_retries', sa.Integer(), nullable=False),
        sa.Column('response_code', sa.Integer(), nullable=True),
        sa.Column('response_body', sa.Text(), nullable=True),
        sa.Column('next_retry_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['call_id'], ['calls.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_automation_jobs_call_id'), 'automation_jobs', ['call_id'], unique=False)
    op.create_index(op.f('ix_automation_jobs_next_retry_at'), 'automation_jobs', ['next_retry_at'], unique=False)
    op.create_index(op.f('ix_automation_jobs_organization_id'), 'automation_jobs', ['organization_id'], unique=False)
    op.create_index(op.f('ix_automation_jobs_status'), 'automation_jobs', ['status'], unique=False)

    # 19. Messages
    op.create_table(
        'messages',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('organization_id', sa.String(length=36), nullable=False),
        sa.Column('lead_id', sa.String(length=36), nullable=True),
        sa.Column('call_id', sa.String(length=36), nullable=True),
        sa.Column('channel', sa.String(length=20), nullable=False),
        sa.Column('direction', sa.String(length=20), nullable=False),
        sa.Column('sender', sa.String(length=100), nullable=False),
        sa.Column('recipient', sa.String(length=100), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('external_provider_id', sa.String(length=255), nullable=True),
        sa.Column('delivery_status', sa.String(length=50), nullable=False),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['call_id'], ['calls.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['lead_id'], ['leads.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_messages_call_id'), 'messages', ['call_id'], unique=False)
    op.create_index(op.f('ix_messages_lead_id'), 'messages', ['lead_id'], unique=False)
    op.create_index(op.f('ix_messages_organization_id'), 'messages', ['organization_id'], unique=False)

    # 20. Audit Logs
    op.create_table(
        'audit_logs',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('organization_id', sa.String(length=36), nullable=False),
        sa.Column('user_id', sa.String(length=36), nullable=True),
        sa.Column('action', sa.String(length=100), nullable=False),
        sa.Column('resource_type', sa.String(length=100), nullable=False),
        sa.Column('resource_id', sa.String(length=36), nullable=False),
        sa.Column('diff_json', sa.JSON(), nullable=True),
        sa.Column('ip_address', sa.String(length=50), nullable=True),
        sa.Column('user_agent', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_audit_logs_created_at'), 'audit_logs', ['created_at'], unique=False)
    op.create_index(op.f('ix_audit_logs_organization_id'), 'audit_logs', ['organization_id'], unique=False)
    op.create_index(op.f('ix_audit_logs_resource_type'), 'audit_logs', ['resource_type'], unique=False)


def downgrade() -> None:
    op.drop_table('audit_logs')
    op.drop_table('messages')
    op.drop_table('automation_jobs')
    op.drop_table('lead_scores')
    op.drop_table('agent_tool_calls')
    op.drop_table('agent_sessions')
    op.drop_table('knowledge_chunks')
    op.drop_table('knowledge_documents')
    op.drop_table('embeddings_metadata')
    op.drop_table('appointments')
    op.drop_table('call_summaries')
    op.drop_table('call_transcripts')
    op.drop_table('call_events')
    op.drop_table('calls')
    op.drop_table('campaigns')
    op.drop_table('customers')
    op.drop_table('leads')
    op.drop_table('users')
    op.drop_table('roles')
    op.drop_table('organizations')
