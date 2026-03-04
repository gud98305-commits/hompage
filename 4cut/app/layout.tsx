import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "인생네컷 AI 생성기",
  description: "셀카를 업로드하면 캐릭터 포즈로 인생네컷을 만들어드립니다",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="ko">
      <body>{children}</body>
    </html>
  );
}
