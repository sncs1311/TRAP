import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "TRAP",
  description: "Transaction Risk & Anomaly Pipeline: real-time fraud scoring and drift monitoring",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}