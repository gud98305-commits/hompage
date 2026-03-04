import fs from "fs";
import path from "path";

const IMAGE_PATH = "C:/Users/user/Desktop/myphoto.jpg";
const API_URL = "http://localhost:3000/api/generate";
const VALID_STYLES = ["sailor_moon", "kuromi", "psyduck", "bobby_hill", "spongebob"];
const STYLE_ID = process.argv[2] || "sailor_moon";

if (!VALID_STYLES.includes(STYLE_ID)) {
  console.error(`잘못된 스타일: ${STYLE_ID}`);
  console.error(`사용 가능: ${VALID_STYLES.join(", ")}`);
  process.exit(1);
}

async function main() {
  // 1. 이미지를 base64로 변환
  const imageBuffer = fs.readFileSync(IMAGE_PATH);
  const imageBase64 = imageBuffer.toString("base64");
  console.log(`셀카 로드 완료: ${IMAGE_PATH} (${(imageBuffer.length / 1024).toFixed(1)}KB)`);

  // 2. API 호출
  console.log(`\nAPI 호출 중... (스타일: ${STYLE_ID})`);
  console.log("이미지 생성에 약 20~30초 소요됩니다...\n");

  const startTime = Date.now();

  const response = await fetch(API_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ imageBase64, styleId: STYLE_ID }),
  });

  const elapsed = ((Date.now() - startTime) / 1000).toFixed(1);

  if (!response.ok) {
    const error = await response.json();
    console.error(`에러 (${response.status}):`, error);
    return;
  }

  const data = await response.json();
  console.log(`완료! (${elapsed}초 소요)`);

  // 3. 결과 저장
  const outputDir = path.join(".", "test-output");
  if (!fs.existsSync(outputDir)) fs.mkdirSync(outputDir);

  // 개별 프레임 저장
  data.frames.forEach((frame, i) => {
    const framePath = path.join(outputDir, `frame_${i}.jpg`);
    fs.writeFileSync(framePath, Buffer.from(frame, "base64"));
    console.log(`프레임 ${i} 저장: ${framePath}`);
  });

  // 그리드 이미지 저장
  const gridPath = path.join(outputDir, "grid_result.jpg");
  fs.writeFileSync(gridPath, Buffer.from(data.resultImage, "base64"));
  console.log(`\n그리드 결과 저장: ${gridPath}`);
  console.log("\ntest-output/ 폴더에서 결과를 확인하세요!");
}

main().catch(console.error);
