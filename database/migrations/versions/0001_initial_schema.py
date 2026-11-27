"""Boshlang'ich sxema: barcha asosiy jadvallar.

Migratsiya aniq SQL (DDL) ko'rinishida yozilgan: u ``database/models`` bilan
mos kelishi CI'dagi ``alembic check`` buyrug'i orqali tekshiriladi.
Cheklov va indeks nomlari ``database.base.NAMING_CONVENTION`` ga mos.

Revision ID: 0001
Revises:
Create Date: 2026-11-27
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _check_in(table: str, column: str, constraint: str, values: Sequence[str]) -> str:
    allowed = ", ".join(f"'{value}'" for value in values)
    return f"CONSTRAINT ck_{table}_{constraint} CHECK ({column} IN ({allowed}))"


CHAT_TYPES = ("private", "group", "supergroup", "channel")
FORWARD_MODES = ("native", "copy")
RULE_STATUSES = ("active", "paused", "disabled")
DELIVERY_STATUSES = ("pending", "success", "failed", "skipped")
AUTOPOST_KINDS = ("scheduled", "random")
TASK_STATUSES = ("active", "paused", "completed", "cancelled", "failed")
RECURRENCES = ("once", "daily", "weekly")
POST_STATUSES = ("pending", "sent", "failed", "cancelled")
MEDIA_TYPES = ("photo", "video", "animation", "document", "audio", "voice")
MESSAGE_OPERATIONS = ("send", "edit", "delete")
OPERATION_SOURCES = ("manual", "forward", "autopost", "random_post")
RUN_STATUSES = ("started", "success", "failed", "skipped")

TIMESTAMPS = """
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL"""


UPGRADE_STATEMENTS: tuple[str, ...] = (
    # ---------------------------------------------------------------- settings
    f"""
    CREATE TABLE settings (
        key VARCHAR(100) NOT NULL,
        value JSONB NOT NULL,{TIMESTAMPS},
        CONSTRAINT pk_settings PRIMARY KEY (key)
    )
    """,
    # ----------------------------------------------------------- chat_categories
    f"""
    CREATE TABLE chat_categories (
        id BIGSERIAL NOT NULL,
        name VARCHAR(64) NOT NULL,
        description TEXT,{TIMESTAMPS},
        CONSTRAINT pk_chat_categories PRIMARY KEY (id),
        CONSTRAINT uq_chat_categories_name UNIQUE (name)
    )
    """,
    # --------------------------------------------------------------------- chats
    f"""
    CREATE TABLE chats (
        id BIGSERIAL NOT NULL,
        telegram_id BIGINT NOT NULL,
        chat_type VARCHAR(32) NOT NULL,
        title VARCHAR(255) NOT NULL,
        username VARCHAR(64),
        is_saved BOOLEAN DEFAULT false NOT NULL,
        is_accessible BOOLEAN DEFAULT true NOT NULL,
        members_count INTEGER,
        last_synced_at TIMESTAMP WITH TIME ZONE,{TIMESTAMPS},
        CONSTRAINT pk_chats PRIMARY KEY (id),
        CONSTRAINT uq_chats_telegram_id UNIQUE (telegram_id),
        {_check_in("chats", "chat_type", "chat_type", CHAT_TYPES)}
    )
    """,
    "CREATE INDEX ix_chats_chat_type ON chats (chat_type)",
    "CREATE INDEX ix_chats_username ON chats (username)",
    # -------------------------------------------------------- chat_category_links
    """
    CREATE TABLE chat_category_links (
        chat_id BIGINT NOT NULL,
        category_id BIGINT NOT NULL,
        CONSTRAINT pk_chat_category_links PRIMARY KEY (chat_id, category_id),
        CONSTRAINT fk_chat_category_links_chat_id_chats
            FOREIGN KEY (chat_id) REFERENCES chats (id) ON DELETE CASCADE,
        CONSTRAINT fk_chat_category_links_category_id_chat_categories
            FOREIGN KEY (category_id) REFERENCES chat_categories (id) ON DELETE CASCADE
    )
    """,
    "CREATE INDEX ix_chat_category_links_category_id ON chat_category_links (category_id)",
    # ------------------------------------------------------------- forward_rules
    f"""
    CREATE TABLE forward_rules (
        id BIGSERIAL NOT NULL,
        name VARCHAR(100) NOT NULL,
        mode VARCHAR(32) NOT NULL,
        status VARCHAR(32) DEFAULT 'active' NOT NULL,
        include_keywords JSONB DEFAULT '[]'::jsonb NOT NULL,
        exclude_keywords JSONB DEFAULT '[]'::jsonb NOT NULL,
        media_types JSONB DEFAULT '[]'::jsonb NOT NULL,
        duplicate_detection BOOLEAN DEFAULT false NOT NULL,{TIMESTAMPS},
        CONSTRAINT pk_forward_rules PRIMARY KEY (id),
        CONSTRAINT uq_forward_rules_name UNIQUE (name),
        {_check_in("forward_rules", "mode", "forward_mode", FORWARD_MODES)},
        {_check_in("forward_rules", "status", "rule_status", RULE_STATUSES)}
    )
    """,
    "CREATE INDEX ix_forward_rules_status ON forward_rules (status)",
    # ------------------------------------------------- forward_rule_sources / destinations
    """
    CREATE TABLE forward_rule_sources (
        rule_id BIGINT NOT NULL,
        chat_id BIGINT NOT NULL,
        CONSTRAINT pk_forward_rule_sources PRIMARY KEY (rule_id, chat_id),
        CONSTRAINT fk_forward_rule_sources_rule_id_forward_rules
            FOREIGN KEY (rule_id) REFERENCES forward_rules (id) ON DELETE CASCADE,
        CONSTRAINT fk_forward_rule_sources_chat_id_chats
            FOREIGN KEY (chat_id) REFERENCES chats (id) ON DELETE CASCADE
    )
    """,
    "CREATE INDEX ix_forward_rule_sources_chat_id ON forward_rule_sources (chat_id)",
    """
    CREATE TABLE forward_rule_destinations (
        rule_id BIGINT NOT NULL,
        chat_id BIGINT NOT NULL,
        CONSTRAINT pk_forward_rule_destinations PRIMARY KEY (rule_id, chat_id),
        CONSTRAINT fk_forward_rule_destinations_rule_id_forward_rules
            FOREIGN KEY (rule_id) REFERENCES forward_rules (id) ON DELETE CASCADE,
        CONSTRAINT fk_forward_rule_destinations_chat_id_chats
            FOREIGN KEY (chat_id) REFERENCES chats (id) ON DELETE CASCADE
    )
    """,
    "CREATE INDEX ix_forward_rule_destinations_chat_id ON forward_rule_destinations (chat_id)",
    # -------------------------------------------------------------- forward_logs
    f"""
    CREATE TABLE forward_logs (
        id BIGSERIAL NOT NULL,
        rule_id BIGINT,
        mode VARCHAR(32) NOT NULL,
        source_chat_telegram_id BIGINT NOT NULL,
        source_message_id BIGINT NOT NULL,
        destination_chat_telegram_id BIGINT NOT NULL,
        destination_message_id BIGINT,
        status VARCHAR(32) DEFAULT 'pending' NOT NULL,
        attempts SMALLINT DEFAULT 0 NOT NULL,
        content_hash VARCHAR(64),
        error VARCHAR(1000),{TIMESTAMPS},
        CONSTRAINT pk_forward_logs PRIMARY KEY (id),
        CONSTRAINT uq_forward_logs_delivery UNIQUE (
            rule_id, source_chat_telegram_id, source_message_id, destination_chat_telegram_id
        ),
        CONSTRAINT fk_forward_logs_rule_id_forward_rules
            FOREIGN KEY (rule_id) REFERENCES forward_rules (id) ON DELETE SET NULL,
        CONSTRAINT ck_forward_logs_attempts_non_negative CHECK (attempts >= 0),
        {_check_in("forward_logs", "mode", "forward_mode", FORWARD_MODES)},
        {_check_in("forward_logs", "status", "delivery_status", DELIVERY_STATUSES)}
    )
    """,
    "CREATE INDEX ix_forward_logs_status ON forward_logs (status)",
    "CREATE INDEX ix_forward_logs_created_at ON forward_logs (created_at)",
    "CREATE INDEX ix_forward_logs_destination_hash"
    " ON forward_logs (destination_chat_telegram_id, content_hash)",
    # --------------------------------------------------------------- media_files
    f"""
    CREATE TABLE media_files (
        id BIGSERIAL NOT NULL,
        sha256 VARCHAR(64) NOT NULL,
        storage_path VARCHAR(512) NOT NULL,
        original_name VARCHAR(255),
        mime_type VARCHAR(127) NOT NULL,
        media_type VARCHAR(32) NOT NULL,
        size_bytes BIGINT NOT NULL,
        width INTEGER,
        height INTEGER,
        duration_seconds INTEGER,
        is_missing BOOLEAN DEFAULT false NOT NULL,{TIMESTAMPS},
        CONSTRAINT pk_media_files PRIMARY KEY (id),
        CONSTRAINT uq_media_files_sha256 UNIQUE (sha256),
        CONSTRAINT uq_media_files_storage_path UNIQUE (storage_path),
        CONSTRAINT ck_media_files_size_non_negative CHECK (size_bytes >= 0),
        {_check_in("media_files", "media_type", "media_type", MEDIA_TYPES)}
    )
    """,
    # ------------------------------------------------------------ post_templates
    f"""
    CREATE TABLE post_templates (
        id BIGSERIAL NOT NULL,
        name VARCHAR(100) NOT NULL,
        text TEXT,
        parse_mode VARCHAR(16),{TIMESTAMPS},
        CONSTRAINT pk_post_templates PRIMARY KEY (id),
        CONSTRAINT uq_post_templates_name UNIQUE (name),
        CONSTRAINT ck_post_templates_parse_mode_valid
            CHECK (parse_mode IS NULL OR parse_mode IN ('html', 'markdown'))
    )
    """,
    """
    CREATE TABLE post_template_media (
        template_id BIGINT NOT NULL,
        position SMALLINT NOT NULL,
        media_id BIGINT NOT NULL,
        CONSTRAINT pk_post_template_media PRIMARY KEY (template_id, position),
        CONSTRAINT fk_post_template_media_template_id_post_templates
            FOREIGN KEY (template_id) REFERENCES post_templates (id) ON DELETE CASCADE,
        CONSTRAINT fk_post_template_media_media_id_media_files
            FOREIGN KEY (media_id) REFERENCES media_files (id) ON DELETE RESTRICT,
        CONSTRAINT ck_post_template_media_position_range CHECK (position BETWEEN 0 AND 9)
    )
    """,
    "CREATE INDEX ix_post_template_media_media_id ON post_template_media (media_id)",
    # ------------------------------------------------------------ autopost_tasks
    f"""
    CREATE TABLE autopost_tasks (
        id BIGSERIAL NOT NULL,
        name VARCHAR(100) NOT NULL,
        kind VARCHAR(32) NOT NULL,
        status VARCHAR(32) DEFAULT 'active' NOT NULL,
        recurrence VARCHAR(32),
        run_at TIMESTAMP WITH TIME ZONE,
        time_of_day TIME WITHOUT TIME ZONE,
        weekdays_mask SMALLINT,
        min_interval_seconds INTEGER,
        max_interval_seconds INTEGER,
        active_from TIME WITHOUT TIME ZONE,
        active_to TIME WITHOUT TIME ZONE,
        template_id BIGINT,
        next_run_at TIMESTAMP WITH TIME ZONE,
        last_run_at TIMESTAMP WITH TIME ZONE,
        locked_by VARCHAR(64),
        locked_until TIMESTAMP WITH TIME ZONE,
        consecutive_failures SMALLINT DEFAULT 0 NOT NULL,
        max_retries SMALLINT DEFAULT 3 NOT NULL,{TIMESTAMPS},
        CONSTRAINT pk_autopost_tasks PRIMARY KEY (id),
        CONSTRAINT uq_autopost_tasks_name UNIQUE (name),
        CONSTRAINT fk_autopost_tasks_template_id_post_templates
            FOREIGN KEY (template_id) REFERENCES post_templates (id) ON DELETE SET NULL,
        CONSTRAINT ck_autopost_tasks_weekdays_mask_range
            CHECK (weekdays_mask IS NULL OR weekdays_mask BETWEEN 1 AND 127),
        CONSTRAINT ck_autopost_tasks_interval_order
            CHECK (min_interval_seconds IS NULL OR max_interval_seconds IS NULL
                   OR min_interval_seconds <= max_interval_seconds),
        CONSTRAINT ck_autopost_tasks_random_requires_interval
            CHECK (kind <> 'random' OR (min_interval_seconds IS NOT NULL
                   AND max_interval_seconds IS NOT NULL)),
        CONSTRAINT ck_autopost_tasks_scheduled_requires_recurrence
            CHECK (kind <> 'scheduled' OR recurrence IS NOT NULL),
        CONSTRAINT ck_autopost_tasks_max_retries_non_negative CHECK (max_retries >= 0),
        {_check_in("autopost_tasks", "kind", "autopost_kind", AUTOPOST_KINDS)},
        {_check_in("autopost_tasks", "status", "task_status", TASK_STATUSES)},
        {_check_in("autopost_tasks", "recurrence", "recurrence", RECURRENCES)}
    )
    """,
    "CREATE INDEX ix_autopost_tasks_template_id ON autopost_tasks (template_id)",
    "CREATE INDEX ix_autopost_tasks_due ON autopost_tasks (status, next_run_at)",
    """
    CREATE TABLE autopost_task_destinations (
        task_id BIGINT NOT NULL,
        chat_id BIGINT NOT NULL,
        CONSTRAINT pk_autopost_task_destinations PRIMARY KEY (task_id, chat_id),
        CONSTRAINT fk_autopost_task_destinations_task_id_autopost_tasks
            FOREIGN KEY (task_id) REFERENCES autopost_tasks (id) ON DELETE CASCADE,
        CONSTRAINT fk_autopost_task_destinations_chat_id_chats
            FOREIGN KEY (chat_id) REFERENCES chats (id) ON DELETE CASCADE
    )
    """,
    "CREATE INDEX ix_autopost_task_destinations_chat_id ON autopost_task_destinations (chat_id)",
    # ------------------------------------------------------ autopost_queue_items
    f"""
    CREATE TABLE autopost_queue_items (
        id BIGSERIAL NOT NULL,
        task_id BIGINT NOT NULL,
        template_id BIGINT NOT NULL,
        times_posted INTEGER DEFAULT 0 NOT NULL,
        last_posted_at TIMESTAMP WITH TIME ZONE,{TIMESTAMPS},
        CONSTRAINT pk_autopost_queue_items PRIMARY KEY (id),
        CONSTRAINT uq_autopost_queue_items_task_template UNIQUE (task_id, template_id),
        CONSTRAINT fk_autopost_queue_items_task_id_autopost_tasks
            FOREIGN KEY (task_id) REFERENCES autopost_tasks (id) ON DELETE CASCADE,
        CONSTRAINT fk_autopost_queue_items_template_id_post_templates
            FOREIGN KEY (template_id) REFERENCES post_templates (id) ON DELETE CASCADE
    )
    """,
    "CREATE INDEX ix_autopost_queue_items_template_id ON autopost_queue_items (template_id)",
    # ----------------------------------------------------------- scheduled_posts
    f"""
    CREATE TABLE scheduled_posts (
        id BIGSERIAL NOT NULL,
        task_id BIGINT,
        template_id BIGINT,
        kind VARCHAR(32) NOT NULL,
        destination_chat_telegram_id BIGINT NOT NULL,
        scheduled_for TIMESTAMP WITH TIME ZONE NOT NULL,
        status VARCHAR(32) DEFAULT 'pending' NOT NULL,
        attempts SMALLINT DEFAULT 0 NOT NULL,
        sent_message_id BIGINT,
        sent_at TIMESTAMP WITH TIME ZONE,
        error VARCHAR(1000),{TIMESTAMPS},
        CONSTRAINT pk_scheduled_posts PRIMARY KEY (id),
        CONSTRAINT uq_scheduled_posts_occurrence
            UNIQUE (task_id, destination_chat_telegram_id, scheduled_for),
        CONSTRAINT fk_scheduled_posts_task_id_autopost_tasks
            FOREIGN KEY (task_id) REFERENCES autopost_tasks (id) ON DELETE SET NULL,
        CONSTRAINT fk_scheduled_posts_template_id_post_templates
            FOREIGN KEY (template_id) REFERENCES post_templates (id) ON DELETE SET NULL,
        CONSTRAINT ck_scheduled_posts_attempts_non_negative CHECK (attempts >= 0),
        {_check_in("scheduled_posts", "kind", "autopost_kind", AUTOPOST_KINDS)},
        {_check_in("scheduled_posts", "status", "post_status", POST_STATUSES)}
    )
    """,
    "CREATE INDEX ix_scheduled_posts_status_scheduled_for"
    " ON scheduled_posts (status, scheduled_for)",
    "CREATE INDEX ix_scheduled_posts_created_at ON scheduled_posts (created_at)",
    # -------------------------------------------------------------- message_logs
    f"""
    CREATE TABLE message_logs (
        id BIGSERIAL NOT NULL,
        operation VARCHAR(32) NOT NULL,
        source VARCHAR(32) NOT NULL,
        chat_telegram_id BIGINT NOT NULL,
        message_id BIGINT,
        status VARCHAR(32) NOT NULL,
        error VARCHAR(1000),{TIMESTAMPS},
        CONSTRAINT pk_message_logs PRIMARY KEY (id),
        {_check_in("message_logs", "operation", "message_operation", MESSAGE_OPERATIONS)},
        {_check_in("message_logs", "source", "operation_source", OPERATION_SOURCES)},
        {_check_in("message_logs", "status", "delivery_status", DELIVERY_STATUSES)}
    )
    """,
    "CREATE INDEX ix_message_logs_chat_telegram_id ON message_logs (chat_telegram_id)",
    "CREATE INDEX ix_message_logs_created_at ON message_logs (created_at)",
    # ----------------------------------------------------------------- task_logs
    f"""
    CREATE TABLE task_logs (
        id BIGSERIAL NOT NULL,
        task_id BIGINT,
        task_name VARCHAR(100) NOT NULL,
        status VARCHAR(32) NOT NULL,
        started_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        finished_at TIMESTAMP WITH TIME ZONE,
        error VARCHAR(1000),
        details JSONB DEFAULT '{{}}'::jsonb NOT NULL,
        CONSTRAINT pk_task_logs PRIMARY KEY (id),
        CONSTRAINT fk_task_logs_task_id_autopost_tasks
            FOREIGN KEY (task_id) REFERENCES autopost_tasks (id) ON DELETE SET NULL,
        {_check_in("task_logs", "status", "run_status", RUN_STATUSES)}
    )
    """,
    "CREATE INDEX ix_task_logs_task_id ON task_logs (task_id)",
    "CREATE INDEX ix_task_logs_started_at ON task_logs (started_at)",
    # ------------------------------------------------------------- activity_logs
    """
    CREATE TABLE activity_logs (
        id BIGSERIAL NOT NULL,
        actor_telegram_id BIGINT,
        action VARCHAR(100) NOT NULL,
        details JSONB DEFAULT '{}'::jsonb NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        CONSTRAINT pk_activity_logs PRIMARY KEY (id)
    )
    """,
    "CREATE INDEX ix_activity_logs_action ON activity_logs (action)",
    "CREATE INDEX ix_activity_logs_created_at ON activity_logs (created_at)",
)

# Bog'liqliklarga teskari tartibda.
DROP_ORDER: tuple[str, ...] = (
    "activity_logs",
    "task_logs",
    "message_logs",
    "scheduled_posts",
    "autopost_queue_items",
    "autopost_task_destinations",
    "autopost_tasks",
    "post_template_media",
    "post_templates",
    "media_files",
    "forward_logs",
    "forward_rule_destinations",
    "forward_rule_sources",
    "forward_rules",
    "chat_category_links",
    "chats",
    "chat_categories",
    "settings",
)


def upgrade() -> None:
    for statement in UPGRADE_STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    for table in DROP_ORDER:
        op.execute(f"DROP TABLE IF EXISTS {table}")
