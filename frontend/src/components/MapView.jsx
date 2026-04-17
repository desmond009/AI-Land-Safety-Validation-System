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

function RecenterMap({ position }) {
  const map = useMap();

  useEffect(() => {
    map.setView(position, map.getZoom(), { animate: true });
  }, [map, position]);

  return null;
}

export default function MapView({ latitude, longitude, layers }) {
  const position = [latitude, longitude];

  return (
    <div className="h-[460px] overflow-hidden rounded-2xl border border-cyan-100/20 shadow-panel">
      <MapContainer center={position} zoom={14} className="h-full w-full" scrollWheelZoom>
        <RecenterMap position={position} />
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        <Marker position={position}>
          <Popup>Selected location</Popup>
        </Marker>

        {Object.entries(layers).map(([name, geojson]) => (
          <GeoJSON key={name} data={geojson} style={layerStyles[name]} />
        ))}
      </MapContainer>
    </div>
  );
}
