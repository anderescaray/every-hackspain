import type { Metadata } from "next";
import "./globals.css";
import { AnalysisNavigationProvider } from "@/components/navigation/AnalysisNavigationProvider";

export const metadata: Metadata = {
  title: "Empresa y grupo | X Ray",
  description: "Health Score, tendencia, origen de la caja, tiempo financiado e inteligencia de grupo a partir de análisis preparados.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="es"><body><AnalysisNavigationProvider>{children}</AnalysisNavigationProvider></body></html>;
}
