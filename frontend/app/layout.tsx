import type { Metadata } from "next";
import "./globals.css";
import { AnalysisNavigationProvider } from "@/components/navigation/AnalysisNavigationProvider";

export const metadata: Metadata = {
  title: "Empresa y grupo | Embat Pulse",
  description: "Operating Health, Extended Health, origen de la caja e inteligencia de grupo a partir de análisis preparados.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="es"><body><AnalysisNavigationProvider>{children}</AnalysisNavigationProvider></body></html>;
}
