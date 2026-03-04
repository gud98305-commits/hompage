import { NextResponse } from "next/server";
import sharp from "sharp";
import { analyzeFace } from "@/lib/analyze";
import { buildPrompts } from "@/lib/prompt-builder";
import { generateImages } from "@/lib/generate-image";
import { compositeGrid } from "@/lib/composite";
import { getPreset } from "@/lib/presets";
import { GenerateRequest } from "@/types";

export const maxDuration = 60;

const PLACEHOLDER_SIZE = 1024;

let cachedPlaceholder: string | null = null;

async function getPlaceholder(): Promise<string> {
  if (cachedPlaceholder) return cachedPlaceholder;
  const buffer = await sharp({
    create: {
      width: PLACEHOLDER_SIZE,
      height: PLACEHOLDER_SIZE,
      channels: 3,
      background: { r: 200, g: 200, b: 200 },
    },
  })
    .jpeg({ quality: 80 })
    .toBuffer();
  cachedPlaceholder = buffer.toString("base64");
  return cachedPlaceholder;
}

export async function POST(req: Request) {
  try {
    const body: GenerateRequest = await req.json();
    let { imageBase64, styleId } = body;

    if (!imageBase64 || !styleId) {
      return NextResponse.json(
        { error: "imageBase64와 styleId는 필수입니다." },
        { status: 400 }
      );
    }

    if (imageBase64.includes(",")) {
      imageBase64 = imageBase64.split(",")[1];
    }

    const preset = getPreset(styleId);
    if (!preset) {
      return NextResponse.json(
        { error: `알 수 없는 스타일: ${styleId}` },
        { status: 400 }
      );
    }

    const faceDescription = await analyzeFace(imageBase64);
    const prompts = buildPrompts(faceDescription, preset);
    const frameResults = await generateImages(prompts, imageBase64);

    const placeholder = await getPlaceholder();
    const frameImages = frameResults.map((r) =>
      r.success ? r.imageBase64 : placeholder
    );

    const resultImage = await compositeGrid(
      frameImages,
      preset.border_color,
      preset.display_name
    );

    return NextResponse.json({ resultImage });
  } catch (error: unknown) {
    console.error("Generate API error:", error);
    const message =
      error instanceof Error ? error.message : "서버 내부 오류가 발생했습니다.";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
