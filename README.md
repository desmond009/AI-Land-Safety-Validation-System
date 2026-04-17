# AI Land Safety Validation System

Full-stack GIS risk analysis app with:
- Backend: FastAPI + GeoPandas + Shapely
- Frontend: React + Leaflet + Tailwind CSS

## Project Structure

```text
backend/
  main.py
  requirements.txt
  data/
    water.json
    forest.json
    restricted.json
  services/
    geo_loader.py
    risk_engine.py
  tests/
    test_api.py

frontend/
  package.json
  src/
    App.jsx
    components/
      MapView.jsx
      RiskCard.jsx
```

## Backend Setup

```bash
cd backend
python3 -m pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

API endpoints:
- `POST /analyze-location`
- `GET /layers/water`
- `GET /layers/forest`
- `GET /layers/restricted`
- `GET /health`

Sample request:

```bash
curl -X POST http://localhost:8000/analyze-location \
  -H "Content-Type: application/json" \
  -d '{"latitude":12.9720,"longitude":77.5955}'
```

## Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

Optional API base URL override:

```bash
# frontend/.env
VITE_API_BASE_URL=http://localhost:8000
```

Open `http://localhost:5173`.

## Tests

```bash
cd backend
pytest -q
```

## Risk Model

- Inside water body: `+50`
- Within 100m of water: `+40`
- Inside forest zone: `+50`
- Near restricted land: `+30`

Classification:
- `0-30`: Low
- `31-70`: Medium
- `71+`: High
