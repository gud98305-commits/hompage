export interface FaceDescription {
  appearance: {
    ethnicity_vibe: string;
    age_range: string;
    skin: string;
    build: string;
  };
  hair: {
    description: string;
  };
  face: {
    eyes: string;
    makeup: string;
  };
  outfit: {
    description: string;
    accessories: string;
  };
}

export interface FramePreset {
  frame_index: number;
  expression: string;
  pose: string;
  pose_description_ko: string;
  detailed_pose_description?: string;
}

export interface BasePrompt {
  background: string;
  lighting: string;
  color_grading: string;
  shot_type: string;
}

export interface StylePreset {
  style_id: string;
  display_name: string;
  border_color: string;
  backdrop_color: string;
  base_prompt: BasePrompt;
  frames: FramePreset[];
}

export interface GenerateRequest {
  imageBase64: string;
  styleId: string;
}

export interface GenerateResponse {
  resultImage: string;
}

export type FrameResult =
  | { success: true; imageBase64: string }
  | { success: false; error: string };
