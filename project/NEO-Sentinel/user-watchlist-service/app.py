from flask import Flask, jsonify, request
from sqlalchemy import create_engine, Column, String, Float, DateTime, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime, timezone
import os
import logging

# app.py - user-watchlist-service

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Database setup
DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://user:password@localhost:5432/neo_sentinel"
)

try:
    engine = create_engine(DATABASE_URL, echo=False)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
except Exception as e:
    logger.error(f"Failed to connect to database: {str(e)}")
    SessionLocal = None

Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    id = Column(String, primary_key=True, index=True)
    name = Column(String, index=True)
    risk_threshold_km = Column(Float)
    watchlist_entries = relationship("WatchlistEntry", back_populates="user", cascade="all, delete-orphan")

class WatchlistEntry(Base):
    __tablename__ = "watchlist_entries"
    id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey("users.id"), primary_key=True)
    date = Column(DateTime, index=True)
    miss_distance_km = Column(Float)
    user = relationship("User", back_populates="watchlist_entries")

# Create tables
if engine:
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("Database tables initialized")
    except Exception as e:
        logger.error(f"Failed to create tables: {str(e)}")

def seed_default_users():
    if not SessionLocal: return
    db = SessionLocal()
    try:
        existing = db.query(User).filter(User.id.in_(["1", "2"])).count()
        if existing == 0:
            users = [
                User(id="1", name="Professor", risk_threshold_km=1000000.0), # Updated for realistic NASA distances
                User(id="2", name="Student", risk_threshold_km=5000000.0),
            ]
            db.add_all(users)
            db.commit()
            logger.info("Default users seeded")
    except Exception as e:
        logger.warning(f"Could not seed users: {str(e)}")
    finally:
        db.close()

seed_default_users()

def _parse_date(d):
    try:
        return datetime.fromisoformat(d.replace("Z", "+00:00"))
    except Exception:
        return None

@app.route("/users/<user_id>", methods=["GET"])
def get_user(user_id):
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if user:
            return jsonify({
                "id": user.id,
                "name": user.name,
                "risk_threshold_km": user.risk_threshold_km,
            }), 200
        return jsonify({"error": "User not found"}), 404
    finally:
        db.close()

@app.route("/users/<user_id>/watchlist", methods=["GET"])
def get_watchlist(user_id):
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return jsonify({"error": "User not found"}), 404

        query = db.query(WatchlistEntry).filter(WatchlistEntry.user_id == user_id)
        
        # Filtering
        id_exact = request.args.get("id")
        if id_exact:
            query = query.filter(WatchlistEntry.id == id_exact)
        
        entries = query.all()
        result = [{
            "id": e.id,
            "date": e.date.isoformat() + "Z" if e.date else None,
            "miss_distance_km": e.miss_distance_km,
        } for e in entries]

        # In-memory sorting for demonstration, though SQL ORDER BY is preferred
        sort_by = request.args.get("sort_by")
        order = request.args.get("order", "asc").lower()
        if sort_by:
            result.sort(key=lambda x: x.get(sort_by) or 0, reverse=(order == "desc"))

        return jsonify({"user_id": user_id, "watchlist": result}), 200
    finally:
        db.close()

@app.route("/users/<user_id>/watchlist", methods=["POST"])
def add_to_watchlist(user_id):
    data = request.get_json()
    if not data or "id" not in data:
        return jsonify({"error": "Missing asteroid id"}), 400

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return jsonify({"error": "User not found"}), 404

        entry = WatchlistEntry(
            id=data["id"],
            user_id=user_id,
            date=_parse_date(data.get("date")) or datetime.now(timezone.utc),
            miss_distance_km=float(data.get("miss_distance_km", 0)),
        )
        db.merge(entry) # Use merge to handle duplicates (UPSERT)
        db.commit()
        return jsonify({"message": "Watchlist updated", "asteroid_id": data["id"]}), 201
    except Exception as e:
        logger.error(f"Database error: {str(e)}")
        return jsonify({"error": "Failed to save entry"}), 500
    finally:
        db.close()

@app.route("/health", methods=["GET"])
def health_check():
    try:
        db = SessionLocal()
        db.execute("SELECT 1")
        return jsonify({"status": "healthy", "service": "user-service", "database": "connected"}), 200
    except Exception:
        return jsonify({"status": "degraded", "service": "user-service", "database": "disconnected"}), 503
    finally:
        db.close()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5002)