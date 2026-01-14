from app import app, db
from sqlalchemy import text
with app.app_context():
    with db.engine.connect() as conn:
        conn.execute(text("ALTER TABLE habit ADD COLUMN description TEXT"))
        conn.commit()