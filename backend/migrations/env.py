from alembic import context
from sqlalchemy import create_engine
from app.domain import Base
from app.settings import Settings

config = context.config
target_metadata = Base.metadata
engine = create_engine(Settings.local().database_url)
with engine.connect() as connection:
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()
