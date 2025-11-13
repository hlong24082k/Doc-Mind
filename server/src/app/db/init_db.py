from src.app.db.session import SessionLocal



# =========================================================
# Init database
# =========================================================
def init_db():
    db = SessionLocal()
    
    try:
        pass
                
    finally:
        db.close()

