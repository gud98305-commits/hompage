import OpenAI from "openai";
import fs from "fs";
import path from "path";

// .env.local에서 OPENAI_API_KEY 로드
const envPath = path.join(process.cwd(), ".env.local");
if (fs.existsSync(envPath)) {
  const envContent = fs.readFileSync(envPath, "utf-8");
  for (const line of envContent.split("\n")) {
    const [key, ...vals] = line.split("=");
    if (key?.trim()) process.env[key.trim()] = vals.join("=").trim();
  }
}

const openai = new OpenAI();

const PRESETS_PATH = path.join(process.cwd(), "data", "pose_presets.json");
const REF_DIR = path.join(process.cwd(), "public", "references");

const SYSTEM_PROMPT = `You are an expert at describing character poses and expressions from images for use in AI image generation prompts.

Analyze the provided character reference image and describe the character's pose, expression, body position, hand placement, and overall mood in extreme detail.

Focus on:
- Exact body posture and angle
- Hand/arm positions and gestures
- Facial expression details (eyes, mouth, eyebrows)
- Head tilt and direction of gaze
- Overall energy/mood of the pose

Do NOT mention the character's name, identity, or the source material.
Do NOT describe colors, clothing style, or art style.
ONLY describe the physical pose and expression as if instructing a real person to replicate it.

Return a JSON object with this structure:
{
  "frames": [
    {
      "frame_index": 0,
      "detailed_pose_description": "very detailed description of pose and expression for frame 0"
    }
  ]
}

If the image shows a single character in one pose, describe that pose for all context.
If the image shows multiple poses/panels, describe each one separately as different frames (up to 4).`;

async function analyzeReference(styleId, imagePath) {
  const imageBuffer = fs.readFileSync(imagePath);
  const base64 = imageBuffer.toString("base64");

  console.log(`\n분석 중: ${styleId} (${imagePath})`);

  const response = await openai.chat.completions.create({
    model: "gpt-4o",
    response_format: { type: "json_object" },
    max_tokens: 1500,
    messages: [
      { role: "system", content: SYSTEM_PROMPT },
      {
        role: "user",
        content: [
          {
            type: "image_url",
            image_url: {
              url: `data:image/jpeg;base64,${base64}`,
              detail: "high",
            },
          },
          {
            type: "text",
            text: "Analyze this character reference image. Describe the pose and expression in extreme detail for each visible frame/panel. Return JSON.",
          },
        ],
      },
    ],
  });

  const content = response.choices[0].message.content;
  if (!content) throw new Error(`Empty response for ${styleId}`);

  const parsed = JSON.parse(content);
  console.log(`  → ${parsed.frames?.length || 0}개 프레임 분석 완료`);
  return parsed;
}

async function main() {
  const presets = JSON.parse(fs.readFileSync(PRESETS_PATH, "utf-8"));

  for (const preset of presets) {
    const imagePath = path.join(REF_DIR, `${preset.style_id}.jpg`);

    if (!fs.existsSync(imagePath)) {
      console.log(`⚠ 이미지 없음: ${imagePath}`);
      continue;
    }

    const analysis = await analyzeReference(preset.style_id, imagePath);

    // 각 프레임에 detailed_pose_description 추가
    if (analysis.frames) {
      preset.frames.forEach((frame, i) => {
        const analyzed = analysis.frames.find((f) => f.frame_index === i) || analysis.frames[i];
        if (analyzed) {
          frame.detailed_pose_description = analyzed.detailed_pose_description;
        }
      });
    }
  }

  // 업데이트된 프리셋 저장
  fs.writeFileSync(PRESETS_PATH, JSON.stringify(presets, null, 2), "utf-8");
  console.log(`\n프리셋 업데이트 완료: ${PRESETS_PATH}`);
}

main().catch(console.error);
