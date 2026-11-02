from alembic import context
from sqlalchemy import create_engine

from app import models
from app.core import DB_URL

target_metadata = models.Base.metadata


def run_migrations_online():
    engine = create_engine(DB_URL)
    with engine.connect() as conn:
        context.configure(connection=conn, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()


run_migrations_online()
