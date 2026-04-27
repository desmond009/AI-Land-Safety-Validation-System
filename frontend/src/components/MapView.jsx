import { useEffect } from 'react';
import L from 'leaflet';
import { GeoJSON, MapContainer, Marker, Popup, TileLayer, useMap } from 'react-leaflet';
import markerIcon2x from 'leaflet/dist/images/marker-icon-2x.png';
import markerIcon from 'leaflet/dist/images/marker-icon.png';
import markerShadow from 'leaflet/dist/images/marker-shadow.png';

delete L.Icon.Default.prototype._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: markerIcon2x,
  iconUrl: markerIcon,
  shadowUrl: markerShadow,
});

const layerStyles = {
  water: { color: '#2f95dc', fillColor: '#2f95dc', fillOpacity: 0.28, weight: 2 },
  forest: { color: '#2f9347', fillColor: '#2f9347', fillOpacity: 0.3, weight: 2 },
  restricted: { color: '#d93025', fillColor: '#d93025', fillOpacity: 0.28, weight: 2 },
};

const layerLabels = {
  water: 'Water Body',
  forest: 'Forest / Eco-sensitive Zone',
  restricted: 'Government / Restricted Land',
};

// Mirror the backend field-priority logic so popup names stay consistent.
const KGIS_NAME_FIELDS = {
  water:      ['Lake_Pondname', 'WBNAME', 'name', 'NAME'],
  forest:     ['ForestName', 'RangeName', 'Forest_type', 'name', 'NAME'],
  restricted: ['FOREST_NAM', 'FL_STATUS', 'name', 'NAME'],
};

function getFeatureDisplayName(properties, layerType) {
  const fields = KGIS_NAME_FIELDS[layerType] ?? ['name', 'NAME'];
  for (const field of fields) {
    const val = properties?.[field];
    if (val && String(val).trim() && String(val).trim().toLowerCase() !== 'null') {
      return String(val).trim();
    }
  }
  const id = properties?.OBJECTID ?? properties?.OBJECTID_1 ?? properties?.KGISLake_PondID;
  return id != null ? `Feature #${id}` : 'Unnamed feature';
}

function buildPopupHtml(feature, layerType) {
  const label = layerLabels[layerType] ?? layerType;
  const name  = getFeatureDisplayName(feature.properties, layerType);
  return `<div style="font-family:sans-serif;font-size:13px;line-height:1.5">
    <b style="color:#1e293b">${label}</b><br/>${name}
  </div>`;
}

function RecenterMap({ position }) {
  const map = useMap();

  useEffect(() => {
    map.setView(position, map.getZoom(), { animate: true });
  }, [map, position]);

  return null;
}

export default function MapView({ latitude, longitude, layers, hasPin }) {
  const position = [latitude, longitude];

  return (
    <div className="relative h-[460px] overflow-hidden rounded-2xl border border-cyan-100/20 shadow-panel">
      <MapContainer center={position} zoom={14} className="h-full w-full" scrollWheelZoom>
        <RecenterMap position={position} />
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        {hasPin && (
          <Marker position={position}>
            <Popup>Selected location</Popup>
          </Marker>
        )}

        {Object.entries(layers).map(([name, geojson]) => (
          <GeoJSON
            key={name}
            data={geojson}
            style={layerStyles[name]}
            onEachFeature={(feature, leafletLayer) => {
              leafletLayer.bindPopup(buildPopupHtml(feature, name));
              leafletLayer.on('mouseover', () => leafletLayer.openPopup());
              leafletLayer.on('mouseout',  () => leafletLayer.closePopup());
            }}
          />
        ))}
      </MapContainer>

      <div className="pointer-events-none absolute bottom-3 left-3 z-[500] rounded-lg border border-slate-100/20 bg-slate-950/85 px-3 py-2 text-xs text-slate-100 backdrop-blur-sm">
        <p className="mb-1 font-semibold uppercase tracking-[0.08em] text-slate-300">Layer Legend</p>
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <span className="h-2.5 w-2.5 rounded-full bg-[#2f95dc]" />
            <span>Water bodies</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="h-2.5 w-2.5 rounded-full bg-[#2f9347]" />
            <span>Forest / eco-sensitive</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="h-2.5 w-2.5 rounded-full bg-[#d93025]" />
            <span>Government / restricted</span>
          </div>
        </div>
      </div>
    </div>
  );
}
