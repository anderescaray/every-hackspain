import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Análisis de empresa | Embat Pulse",
  description: "Health Score, trayectoria financiera, origen de la caja y tiempo financiado. Demostración con datos de ejemplo para HackSpain 2026.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="es"><body>{children}</body></html>;
}
