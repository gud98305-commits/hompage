import { NextResponse } from "next/server";
import { getAllStyles } from "@/lib/styles";

export async function GET() {
  try {
    const styles = getAllStyles();
    return NextResponse.json(styles);
  } catch (error) {
    console.error("Styles API error:", error);
    return NextResponse.json(
      { error: "스타일 목록을 불러오지 못했습니다." },
      { status: 500 }
    );
  }
}
