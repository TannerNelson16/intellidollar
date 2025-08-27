import os
import time
from flask import Flask
from flask_wtf.csrf import CSRFProtect
from flask_login import LoginManager
from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker
from .models import Base, User

csrf = CSRFProtect()
login_manager = LoginManager()
login_manager.login_view = "core.login"

def create_app():
    app = Flask(__name__, static_folder="static", template_folder="templates")
    app.config["SECRET_KEY"] = os.getenv("FLASK_SECRET_KEY", "dev-secret")

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        # Fallback for local dev
        database_url = "sqlite:///budget.db"

    # Lazy retry (helps when DB finishes booting a hair after app)
    engine = None
    for _ in range(30):
        try:
            engine = create_engine(database_url, pool_pre_ping=True, future=True)
            with engine.connect() as conn:
                conn.execute("SELECT 1")
            break
        except Exception:
            time.sleep(1)
    if engine is None:
        raise RuntimeError("Could not connect to database.")

    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    db_session = scoped_session(session_factory)

    # Create tables if needed — serialized across workers with a MySQL advisory lock.
    # Falls back gracefully on SQLite/other dialects.
    try:
        with engine.connect() as conn:
            try:
                # Wait up to 30s for the lock; prevents concurrent DDL from multiple workers
                conn.exec_driver_sql("SELECT GET_LOCK('bt_schema_lock', 30)")
                Base.metadata.create_all(engine)
            finally:
                conn.exec_driver_sql("SELECT RELEASE_LOCK('bt_schema_lock')")
    except Exception:
        # If the dialect doesn't support GET_LOCK/RELEASE_LOCK, just attempt create_all
        Base.metadata.create_all(engine)

    # Attach to app
    app.engine = engine
    app.db_session = db_session

    csrf.init_app(app)
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        return db_session.get(User, int(user_id))

    # Register routes
    from .routes import bp
    app.register_blueprint(bp)

    @app.teardown_appcontext
    def shutdown_session(exception=None):
        db_session.remove()

    return app

