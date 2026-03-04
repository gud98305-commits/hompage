import { NextResponse } from "next/server";
import sharp from "sharp";
import { generateImages } from "@/lib/generate-image";
import { compositeGrid } from "@/lib/composite";
import { getStyle } from "@/lib/styles";
import { GenerateRequest } from "@/types";

const PLACEHOLDER_SIZE = 1024;

async function createPlaceholder(): Promise<string> {
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
  return buffer.toString("base64");
}

export async function POST(req: Request) {
  try {
    const body: GenerateRequest = await req.json();
    let { styleId, imageBase64, textDescription, outfitDescription } = body;

    if (!styleId) {
      return NextResponse.json(
        { error: "styleId는 필수입니다." },
        { status: 400 }
      );
    }

    if (!imageBase64 && !textDescription) {
      return NextResponse.json(
        { error: "imageBase64 또는 textDescription 중 하나는 필수입니다." },
        { status: 400 }
      );
    }

    // data URL prefix 제거
    if (imageBase64?.includes(",")) {
      imageBase64 = imageBase64.split(",")[1];
    }

    const style = getStyle(styleId);
    if (!style) {
      return NextResponse.json(
        { error: `알 수 없는 스타일: ${styleId}` },
        { status: 400 }
      );
    }

    if (!style.prompts || style.prompts.length < 4) {
      return NextResponse.json(
        { error: `스타일 '${styleId}'의 프롬프트가 설정되지 않았습니다.` },
        { status: 400 }
      );
    }

    // 컨텍스트 조합: 인물 특징 + 의상 설명을 프롬프트 앞에 추가
    const contextParts: string[] = [];
    if (textDescription) contextParts.push(`Person characteristics: ${textDescription}`);
    if (outfitDescription) contextParts.push(`Outfit style: ${outfitDescription}`);
    const context = contextParts.join("\n");
    const prompts = context
      ? style.prompts.map((p) => `${context}\n\n${p}`)
      : style.prompts;

    // 이미지 4장 병렬 생성
    const frameResults = await generateImages(prompts, imageBase64);

    const placeholder = await createPlaceholder();
    const frameImages = frameResults.map((r) =>
      r.success ? r.imageBase64 : placeholder
    );

    // 2×2 그리드 합성 + AX film + 날짜
    const resultImage = await compositeGrid(
      frameImages,
      style.border_color,
      style.display_name
    );

    return NextResponse.json({ resultImage, frames: frameImages });
  } catch (error: unknown) {
    console.error("Generate API error:", error);
    const message =
      error instanceof Error ? error.message : "서버 내부 오류가 발생했습니다.";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
