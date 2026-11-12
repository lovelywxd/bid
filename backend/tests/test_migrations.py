import importlib.util

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import MetaData, create_engine

from app.domain import Base
from app.settings import ROOT


def test_frozen_migration_empty_database_roundtrip(business, tmp_path):
    # PostgreSQL uses the fixture's already isolated temporary schema.
    if business.store.engine.dialect.name == "postgresql":
        engine = business.store.engine
        Base.metadata.drop_all(engine)
    else:
        engine = create_engine(f"sqlite:///{tmp_path / 'migration.db'}")
    path = ROOT / "backend/migrations/versions/0001_foundation.py"
    spec = importlib.util.spec_from_file_location("foundation", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    with engine.begin() as conn:
        context = MigrationContext.configure(conn, opts={"compare_type": True})
        with Operations.context(context):
            migration.upgrade()
            assert compare_metadata(context, Base.metadata) == []
            migration.downgrade()
            assert compare_metadata(context, MetaData()) == []
            migration.upgrade()
            assert compare_metadata(context, Base.metadata) == []
