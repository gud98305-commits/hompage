"use client";

import { useState, useRef, useCallback, useEffect } from "react";
import Image from "next/image";

interface PresetInfo {
  style_id: string;
  display_name: string;
  border_color: string;
}

type AppState = "idle" | "uploaded" | "style_selected" | "generating" | "done" | "error";

const PROGRESS_MESSAGES = [
  { text: "🔍 얼굴을 분석하고 있어요...", delay: 0 },
  { text: "🎨 이미지를 생성하고 있어요...", delay: 3000 },
  { text: "✨ 네컷을 합성하고 있어요...", delay: 18000 },
];

async function resizeImage(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const img = new window.Image();
    img.onload = () => {
      const MAX = 1024;
      let { width, height } = img;
      if (width > MAX || height > MAX) {
        const ratio = Math.min(MAX / width, MAX / height);
        width = Math.round(width * ratio);
        height = Math.round(height * ratio);
      }
      const canvas = document.createElement("canvas");
      canvas.width = width;
      canvas.height = height;
      const ctx = canvas.getContext("2d")!;
      ctx.drawImage(img, 0, 0, width, height);
      const dataUrl = canvas.toDataURL("image/jpeg", 0.9);
      const base64 = dataUrl.split(",")[1];
      resolve(base64);
    };
    img.onerror = () => reject(new Error("이미지를 불러올 수 없습니다."));
    img.src = URL.createObjectURL(file);
  });
}

function downloadBase64(base64: string, filename: string) {
  const byteString = atob(base64);
  const bytes = new Uint8Array(byteString.length);
  for (let i = 0; i < byteString.length; i++) {
    bytes[i] = byteString.charCodeAt(i);
  }
  const blob = new Blob([bytes], { type: "image/jpeg" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export default function PhotoBoothPage() {
  const [appState, setAppState] = useState<AppState>("idle");
  const [presets, setPresets] = useState<PresetInfo[]>([]);
  const [imageBase64, setImageBase64] = useState<string | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [selectedStyle, setSelectedStyle] = useState<string | null>(null);
  const [progressMsg, setProgressMsg] = useState("");
  const [resultImage, setResultImage] = useState<string | null>(null);
  const [errorMsg, setErrorMsg] = useState("");
  const [isDragging, setIsDragging] = useState(false);

  const MAX_REQUESTS = 5;
  const [requestCount, setRequestCount] = useState(0);

  const fileInputRef = useRef<HTMLInputElement>(null);
  const progressTimers = useRef<NodeJS.Timeout[]>([]);

  // 프리셋 로드
  useEffect(() => {
    fetch("/api/presets")
      .then((res) => res.json())
      .then(setPresets)
      .catch(() => {});
  }, []);

  const handleFile = useCallback(async (file: File) => {
    if (!file.type.startsWith("image/")) return;
    if (file.size > 1024 * 1024) {
      setErrorMsg("이미지 용량은 1MB 이하만 가능합니다.");
      setAppState("error");
      return;
    }
    try {
      const base64 = await resizeImage(file);
      setImageBase64(base64);
      setPreviewUrl(`data:image/jpeg;base64,${base64}`);
      setAppState("uploaded");
      setResultImage(null);
      setSelectedStyle(null);
    } catch {
      setErrorMsg("이미지 처리에 실패했습니다.");
      setAppState("error");
    }
  }, []);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setIsDragging(false);
      const file = e.dataTransfer.files[0];
      if (file) handleFile(file);
    },
    [handleFile]
  );

  const handleStyleSelect = (styleId: string) => {
    setSelectedStyle(styleId);
    setAppState("style_selected");
  };

  const clearProgressTimers = () => {
    progressTimers.current.forEach(clearTimeout);
    progressTimers.current = [];
  };

  const handleGenerate = async () => {
    if (!imageBase64 || !selectedStyle) return;

    if (requestCount >= MAX_REQUESTS) {
      setErrorMsg(`요청 횟수가 ${MAX_REQUESTS}회를 초과했습니다. 페이지를 새로고침해주세요.`);
      setAppState("error");
      return;
    }

    setAppState("generating");
    setErrorMsg("");

    // 프로그레스 메시지 타이머
    clearProgressTimers();
    PROGRESS_MESSAGES.forEach(({ text, delay }) => {
      const timer = setTimeout(() => setProgressMsg(text), delay);
      progressTimers.current.push(timer);
    });

    try {
      const res = await fetch("/api/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ imageBase64, styleId: selectedStyle }),
      });

      clearProgressTimers();

      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.error || `서버 오류 (${res.status})`);
      }

      const data = await res.json();
      setResultImage(data.resultImage);
      setRequestCount((c) => c + 1);
      setAppState("done");
    } catch (err) {
      clearProgressTimers();
      setErrorMsg(err instanceof Error ? err.message : "알 수 없는 오류가 발생했습니다.");
      setAppState("error");
    }
  };

  const handleReset = () => {
    setAppState("idle");
    setImageBase64(null);
    setPreviewUrl(null);
    setSelectedStyle(null);
    setResultImage(null);
    setErrorMsg("");
    setProgressMsg("");
    clearProgressTimers();
  };

  const handleRetry = () => {
    setAppState("style_selected");
    setResultImage(null);
    setErrorMsg("");
  };

  const isGenerating = appState === "generating";
  const canGenerate = appState === "style_selected" && imageBase64 && selectedStyle;

  return (
    <main className="min-h-screen bg-gradient-to-b from-gray-50 to-gray-100 py-8 px-4">
      <div className="max-w-lg mx-auto">
        {/* 헤더 */}
        <h1 className="text-center text-2xl font-bold text-gray-800 mb-8">
          📸 인생네컷 AI 생성기
        </h1>

        {/* 결과 화면 */}
        {appState === "done" && resultImage && (
          <div className="space-y-4">
            <div className="rounded-xl overflow-hidden shadow-lg bg-white">
              <img
                src={`data:image/jpeg;base64,${resultImage}`}
                alt="생성 결과"
                className="w-full"
              />
            </div>
            <div className="flex gap-3">
              <button
                onClick={() => downloadBase64(resultImage, "life4cut.jpg")}
                className="flex-1 py-3 rounded-xl bg-gray-800 text-white font-semibold hover:bg-gray-700 transition"
              >
                📥 다운로드
              </button>
              <button
                onClick={handleReset}
                className="flex-1 py-3 rounded-xl bg-white text-gray-800 font-semibold border border-gray-300 hover:bg-gray-50 transition"
              >
                🔄 다시 만들기
              </button>
            </div>
          </div>
        )}

        {/* 로딩 화면 */}
        {isGenerating && (
          <div className="text-center py-20 space-y-6">
            <div className="inline-block w-12 h-12 border-4 border-gray-300 border-t-gray-800 rounded-full animate-spin" />
            <p className="text-lg text-gray-600 animate-pulse">{progressMsg}</p>
          </div>
        )}

        {/* 에러 화면 */}
        {appState === "error" && (
          <div className="text-center py-12 space-y-4">
            <p className="text-red-500 font-medium">{errorMsg}</p>
            <div className="flex gap-3 justify-center">
              {imageBase64 && selectedStyle && (
                <button
                  onClick={handleRetry}
                  className="px-6 py-2 rounded-lg bg-gray-800 text-white font-medium hover:bg-gray-700 transition"
                >
                  다시 시도
                </button>
              )}
              <button
                onClick={handleReset}
                className="px-6 py-2 rounded-lg bg-white text-gray-800 border border-gray-300 font-medium hover:bg-gray-50 transition"
              >
                처음으로
              </button>
            </div>
          </div>
        )}

        {/* 메인 UI (idle ~ style_selected) */}
        {!isGenerating && appState !== "done" && appState !== "error" && (
          <div className="space-y-6">
            {/* 업로드 영역 */}
            <div
              onDragOver={(e) => {
                e.preventDefault();
                setIsDragging(true);
              }}
              onDragLeave={() => setIsDragging(false)}
              onDrop={handleDrop}
              onClick={() => fileInputRef.current?.click()}
              className={`relative border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-colors ${
                isDragging
                  ? "border-blue-400 bg-blue-50"
                  : previewUrl
                  ? "border-gray-200 bg-white"
                  : "border-gray-300 bg-white hover:border-gray-400"
              }`}
            >
              <input
                ref={fileInputRef}
                type="file"
                accept="image/*"
                className="hidden"
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  if (file) handleFile(file);
                }}
              />
              {previewUrl ? (
                <div className="space-y-3">
                  <img
                    src={previewUrl}
                    alt="업로드된 셀카"
                    className="max-h-48 mx-auto rounded-lg object-cover"
                  />
                  <p className="text-sm text-gray-400">클릭하여 다른 사진 선택</p>
                </div>
              ) : (
                <div className="space-y-2 py-4">
                  <p className="text-4xl">📷</p>
                  <p className="text-gray-600 font-medium">셀카를 업로드해주세요</p>
                  <p className="text-sm text-gray-400">드래그 앤 드롭 또는 클릭</p>
                </div>
              )}
            </div>

            {/* 스타일 선택 */}
            {imageBase64 && (
              <div className="space-y-3">
                <p className="text-sm font-medium text-gray-600">스타일을 선택해주세요:</p>
                <div className="grid grid-cols-5 gap-2">
                  {presets.map((preset) => (
                    <button
                      key={preset.style_id}
                      onClick={() => handleStyleSelect(preset.style_id)}
                      className="rounded-xl overflow-hidden transition-all"
                    >
                      <div
                        className="aspect-square relative rounded-xl overflow-hidden transition-all"
                        style={{
                          border:
                            selectedStyle === preset.style_id
                              ? `3px solid ${preset.border_color}`
                              : "2px solid #e5e7eb",
                          transform:
                            selectedStyle === preset.style_id
                              ? "scale(1.05)"
                              : undefined,
                        }}
                      >
                        <Image
                          src={`/references/${preset.style_id}.jpg`}
                          alt={preset.display_name}
                          fill
                          className="object-cover"
                          sizes="80px"
                        />
                      </div>
                      <p className="text-xs text-center mt-1 font-medium text-gray-700 truncate px-1">
                        {preset.display_name.replace(" 네컷", "")}
                      </p>
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* 생성 버튼 */}
            {imageBase64 && (
              <button
                onClick={handleGenerate}
                disabled={!canGenerate}
                className={`w-full py-3 rounded-xl font-semibold text-white transition ${
                  canGenerate
                    ? "bg-gray-800 hover:bg-gray-700"
                    : "bg-gray-300 cursor-not-allowed"
                }`}
              >
                🎬 생성하기
              </button>
            )}
          </div>
        )}
      </div>
    </main>
  );
}
