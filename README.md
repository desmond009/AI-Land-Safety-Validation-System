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

### External GitHub GeoJSON Sources (KGIS-Reference Mode)

By default, the backend reads local files from `backend/data/`.
To use external GeoJSON files (for example from GitHub raw URLs), set any of these environment variables before starting FastAPI:

- `KGIS_WATER_GEOJSON_URL`
- `KGIS_FOREST_GEOJSON_URL`
- `KGIS_RESTRICTED_GEOJSON_URL`

Example:

```bash
export KGIS_WATER_GEOJSON_URL="https://raw.githubusercontent.com/<owner>/<repo>/<branch>/water.geojson"
export KGIS_FOREST_GEOJSON_URL="https://raw.githubusercontent.com/<owner>/<repo>/<branch>/forest.geojson"
export KGIS_RESTRICTED_GEOJSON_URL="https://raw.githubusercontent.com/<owner>/<repo>/<branch>/restricted.geojson"
uvicorn main:app --reload --port 8000
```

If a URL is unavailable, the loader automatically falls back to local files in `backend/data/`.

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
- `0-30`: LOW
- `31-70`: MEDIUM
- `71+`: HIGH

## Uploaded KGIS Boundary Datasets

Your uploaded zip files are valid KGIS-style boundary references:

- `State_Boundaries.json.zip` (1 feature)
- `District_Boundaries.json.zip` (31 features)
- `Taluk_Boundaries.json.zip` (271 features)
- `AC_Boundaries.json.zip` (224 features)
- `PC_Boundaries.json.zip` (28 features)

These are administrative boundaries and can be used as context/reference layers. The current risk model still requires thematic layers for water, forest, and restricted land.

## Frontend Features

- Interactive map using Leaflet with location marker
- GeoJSON overlays for water, forest, and restricted layers
- Layer legend with KGIS-inspired categories
- Risk dashboard card with score, flags, and explainable text
- Download report as JSON
