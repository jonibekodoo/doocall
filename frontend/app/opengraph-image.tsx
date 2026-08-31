import { ImageResponse } from "next/og";

export const alt = "dooCall — har bir qo'ng'iroq nazorat ostida";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

export default function OpengraphImage() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          justifyContent: "center",
          padding: 80,
          background: "linear-gradient(135deg, #0f1a19 0%, #1c605d 100%)",
          color: "#fff",
          fontSize: 72,
          fontWeight: 700,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 20 }}>
          <div
            style={{
              width: 72,
              height: 72,
              borderRadius: 16,
              background: "#2a9691",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              fontSize: 40,
            }}
          >
            ☎
          </div>
          dooCall
        </div>
        <div
          style={{
            fontSize: 34,
            fontWeight: 400,
            marginTop: 28,
            color: "#b0e4de",
          }}
        >
          Har bir qo&apos;ng&apos;iroq — nazorat ostida
        </div>
      </div>
    ),
    size,
  );
}
