from flask import Flask, jsonify, request
from sqlalchemy import create_engine, Column, String, Float, DateTime, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime
import os
import logging

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
    watchlist_entries = relationship("WatchlistEntry", back_populates="user")


class WatchlistEntry(Base):
    __tablename__ = "watchlist_entries"
    id = Column(String, primary_key=True, index=True)
    user_id = Column(String, ForeignKey("users.id"), primary_key=True)
    date = Column(DateTime, index=True)
    miss_distance_km = Column(Float)
    user = relationship("User", back_populates="watchlist_entries")


# Create tables
try:
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables initialized")
except Exception as e:
    logger.error(f"Failed to create tables: {str(e)}")


# Seed default users if not present
def seed_default_users():
    try:
        db = SessionLocal()
        existing = db.query(User).filter(User.id.in_(["1", "2"])).count()
        if existing == 0:
            users = [
                User(id="1", name="Professor", risk_threshold_km=0.1),
                User(id="2", name="Student", risk_threshold_km=0.5),
            ]
            db.add_all(users)
            db.commit()
            logger.info("Default users inserted")
        db.close()
    except Exception as e:
        logger.warning(f"Could not seed users: {str(e)}")


seed_default_users()


def _parse_date(d):
    try:
        return datetime.fromisoformat(d.replace("Z", "+00:00"))
    except Exception:
        return None


@app.route("/users/<user_id>", methods=["GET"])
def get_user(user_id):
    """Get user profile by ID."""
    try:
        db = SessionLocal()
        user = db.query(User).filter(User.id == user_id).first()
        db.close()

        if user:
            return (
                jsonify(
                    {
                        "id": user.id,
                        "name": user.name,
                        "risk_threshold_km": user.risk_threshold_km,
                    }
                ),
                200,
            )
        return jsonify({"error": "User not found"}), 404
    except Exception as e:
        logger.error(f"Error fetching user: {str(e)}")
        return jsonify({"error": "Database error"}), 500


@app.route("/users/<user_id>/watchlist", methods=["GET"])
def get_watchlist(user_id):
    """Return a user's watchlist with optional sorting and ID search.

    Query params:
      - sort_by: 'date' or 'miss_distance'
      - order: 'asc' or 'desc' (default 'asc')
      - id: exact asteroid ID to search for
      - search_id: substring to filter entry IDs (backwards-compatible)
    """
    try:
        db = SessionLocal()

        # Check if user exists
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            db.close()
            return jsonify({"error": "User not found"}), 404

        # Get watchlist entries
        query = db.query(WatchlistEntry).filter(WatchlistEntry.user_id == user_id)

        # exact ID search takes precedence
        id_exact = request.args.get("id")
        if id_exact:
            query = query.filter(WatchlistEntry.id == id_exact)
        else:
            # substring search by id (backwards-compatible)
            search_id = request.args.get("search_id")
            if search_id:
                query = query.filter(WatchlistEntry.id.contains(search_id))

        entries = query.all()

        # Convert to dict for sorting
        entries_dicts = [
            {
                "id": e.id,
                "date": e.date.isoformat() + "Z" if e.date else None,
                "miss_distance_km": e.miss_distance_km,
            }
            for e in entries
        ]

        # sorting
        sort_by = request.args.get("sort_by")
        order = request.args.get("order", "asc").lower()
        reverse = order == "desc"

        if sort_by == "date":
            entries_dicts.sort(
                key=lambda e: _parse_date(e.get("date")) or datetime.min,
                reverse=reverse,
            )
        elif sort_by == "miss_distance":
            entries_dicts.sort(
                key=lambda e: float(e.get("miss_distance_km", float("inf"))),
                reverse=reverse,
            )

        db.close()
        return jsonify({"user_id": user_id, "watchlist": entries_dicts}), 200
    except Exception as e:
        logger.error(f"Error fetching watchlist: {str(e)}")
        return jsonify({"error": "Database error"}), 500


@app.route("/users/<user_id>/watchlist", methods=["POST"])
def add_to_watchlist(user_id):
    """Add an asteroid to a user's watchlist.

    Body:
      {
        "id": "asteroid_id",
        "date": "2026-02-12T12:00:00Z",
        "miss_distance_km": 1000.5
      }
    """
    try:
        data = request.get_json()
        if not data or "id" not in data:
            return jsonify({"error": "Missing required field: id"}), 400

        db = SessionLocal()

        # Check if user exists
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            db.close()
            return jsonify({"error": "User not found"}), 404

        # Add entry
        entry = WatchlistEntry(
            id=data["id"],
            user_id=user_id,
            date=(
                _parse_date(data.get("date")) if data.get("date") else datetime.utcnow()
            ),
            miss_distance_km=float(data.get("miss_distance_km", 0)),
        )
        db.add(entry)
        db.commit()
        db.close()

        logger.info(f"Added asteroid {data['id']} to watchlist for user {user_id}")
        return (
            jsonify({"message": "Added to watchlist", "asteroid_id": data["id"]}),
            201,
        )
    except Exception as e:
        logger.error(f"Error adding to watchlist: {str(e)}")
        return jsonify({"error": "Database error"}), 500


@app.route("/health", methods=["GET"])
def health_check():
    """Health check including database connectivity."""
    try:
        db = SessionLocal()
        db.execute("SELECT 1")
        db.close()
        return (
            jsonify(
                {
                    "status": "healthy",
                    "service": "user-watchlist-service",
                    "database": "connected",
                }
            ),
            200,
        )
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        return (
            jsonify(
                {
                    "status": "degraded",
                    "service": "user-watchlist-service",
                    "database": "disconnected",
                }
            ),
            503,
        )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5002)
