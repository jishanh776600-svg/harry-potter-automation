import React from "react";

export const SafeZoneOverlay: React.FC = () => {
  return (
    <div className="hp-safe-zone-overlay">
      {/* Top UI safe zone header: 0 - 200px */}
      <div
        style={{
          position: "absolute",
          top: 0,
          left: 0,
          right: 0,
          height: 200,
          backgroundColor: "rgba(255, 0, 0, 0.05)",
          borderBottom: "1px dashed rgba(255, 0, 0, 0.3)",
        }}
      />
      {/* Bottom UI safe zone: 1550 - 1920px */}
      <div
        style={{
          position: "absolute",
          bottom: 0,
          left: 0,
          right: 0,
          height: 370,
          backgroundColor: "rgba(255, 0, 0, 0.05)",
          borderTop: "1px dashed rgba(255, 0, 0, 0.3)",
        }}
      />
      {/* Right side interaction buttons safe zone: 940 - 1080px */}
      <div
        style={{
          position: "absolute",
          top: 400,
          bottom: 370,
          right: 0,
          width: 140,
          backgroundColor: "rgba(255, 0, 0, 0.05)",
          borderLeft: "1px dashed rgba(255, 0, 0, 0.3)",
        }}
      />
    </div>
  );
};
