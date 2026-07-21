import os
from pathlib import Path

from flask import Flask


def create_app(test_config=None):
    app = Flask(__name__)
    root = Path(__file__).resolve().parent.parent
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("OPSLENS_SECRET_KEY", "dev-only-change-me"),
        DATABASE=os.environ.get("OPSLENS_DATABASE", str(root / "data" / "opslens.db")),
        MAX_CONTENT_LENGTH=10 * 1024 * 1024,
        REJECTED_ROW_SAMPLE_LIMIT=25,
    )
    if test_config:
        app.config.update(test_config)

    from app import db
    db.init_app(app)

    from app.routes import bp
    app.register_blueprint(bp)
    return app


app = create_app()
