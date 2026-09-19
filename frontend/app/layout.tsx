import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Company insights | Embat Pulse",
  description: "Explainable company trajectories, cash sources and payment timing. HackSpain 2026 mock demonstration.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}
