import { NextResponse } from "next/server";
import { getAllPresets } from "@/lib/presets";

export async function GET() {
  const presets = getAllPresets();

  const data = presets.map((p) => ({
    style_id: p.style_id,
    display_name: p.display_name,
    border_color: p.border_color,
  }));

  return NextResponse.json(data);
}
