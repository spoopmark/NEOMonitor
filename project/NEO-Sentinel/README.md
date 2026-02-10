"# NEO-Sentinel" 


# NEO-Sentinel: Microservice Asteroid Risk Tracker

## System Overview
NEO-Sentinel is a distributed system designed to monitor Near-Earth Objects (NEOs) and assess potential risks based on individual user profiles. It demonstrates core microservice principles, including service isolation, RESTful communication, and containerization.

### Architecture Diagram


1. **Asteroid Data Service (Port 5001):** Consumes the NASA NeoWS API, filters the raw data, and normalizes it into a standard JSON format.
2. **User Watchlist Service (Port 5002):** Manages user records and their specific risk thresholds (e.g., alert me if an asteroid is > 0.5km).
3. **Risk Analysis Service (Port 5003):** The "Orchestrator." It fetches data from the other two services, applies the user's logic, and generates a final risk report.

## Setup & Installation

### Prerequisites
- Docker Desktop installed and running
- A free NASA API key (get one from https://api.nasa.gov/)

### Quick Start

1. **Clone the repository:**
   ```bash
   git clone <repo-url>
   cd NEO-Sentinel/project/NEO-Sentinel
   ```

2. **Start all services:**
   ```bash
   docker-compose up --build
   ```

   The system will start:
   - **API Gateway** on http://localhost:8000
   - **Asteroid Service** on http://localhost:5001
   - **User Service** on http://localhost:5002 (with PostgreSQL)
   - **Risk Analysis Service** on http://localhost:5003
   - **Redis cache** on localhost:6379


### Verify Services Are Running

```bash
# Check all services healthy
curl http://localhost:8000/health

# Or check each individually
curl http://localhost:5001/health  # Asteroid Service
curl http://localhost:5002/health  # User Service
curl http://localhost:5003/health  # Risk Service
```

## Example API Calls
* **Generate Report:** `GET http://localhost:5003/report/1`
* **Health Check:** `GET http://localhost:5001/health`
