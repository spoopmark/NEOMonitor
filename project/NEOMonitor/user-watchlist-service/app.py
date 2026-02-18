import os
import logging
from flask import Flask, jsonify, request
from sqlalchemy import create_engine, Column, Integer, String, Float, ForeignKey
from sqlalchemy.orm import sessionmaker, declarative_base, relationship

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Database Config
DATABASE_URL = os.environ.get('DATABASE_URL')
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# --- Models ---
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    risk_threshold_km = Column(Float, default=1000000.0)

class Watchlist(Base):
    __tablename__ = "watchlist_entries"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    asteroid_id = Column(String)
    name = Column(String)
    miss_distance_km = Column(Float)

# --- Startup Logic (Create Tables & Seed Data) ---
def init_db():
    try:
        # Create Tables
        Base.metadata.create_all(bind=engine)
        logger.info("Database tables verified/created.")
        
        # Seed Default Users
        db = SessionLocal()
        if not db.query(User).filter_by(name="Professor").first():
            db.add(User(name="Professor", risk_threshold_km=500000.0)) # Strict threshold
            db.add(User(name="Student", risk_threshold_km=2000000.0))  # Loose threshold
            db.commit()
            logger.info("Default users (Professor, Student) seeded.")
        db.close()
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")

# Run initialization once on import
init_db()

@app.route('/users/<int:user_id>', methods=['GET'])
def get_user(user_id):
    db = SessionLocal()
    user = db.query(User).filter(User.id == user_id).first()
    db.close()
    if not user:
        return jsonify({"error": "User not found"}), 404
    return jsonify({
        "id": user.id,
        "name": user.name,
        "risk_threshold_km": user.risk_threshold_km
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5002)