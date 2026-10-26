"""Alembic environment: how migrations reach the database.

Online (normal): connects with the pipeline's settings from .env (pipeline.db.engine).
Offline (`alembic upgrade head --sql`): prints the SQL instead of running it; needs no database.
"""

from logging.config import fileConfig

from alembic import context

from pipeline.db import engine
from pipeline.models import Base

config = context.config
if config.config_file_name and config.attributes.get("configure_logging", True):
    fileConfig(config.config_file_name)



def run_migrations_offline() -> None:
    # compare_type / compare_server_default: `alembic check` reports any difference between
    # the models and the database, including column types and default values.
    context.configure(url="mysql+pymysql://", literal_binds=True, target_metadata=Base.metadata,
                      compare_type=True, compare_server_default=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    with engine().connect() as connection:
        context.configure(connection=connection, target_metadata=Base.metadata,
                          compare_type=True, compare_server_default=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
