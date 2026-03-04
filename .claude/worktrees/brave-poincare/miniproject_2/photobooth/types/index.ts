export interface Style {
  style_id: string;
  display_name: string;
  border_color: string;
  gallery_image: string;
  prompts: string[];          // 4 direct prompts for gpt-image-1
}

export interface GenerateRequest {
  styleId: string;
  imageBase64?: string;       // selfie → images.edit()
  textDescription?: string;   // text only → images.generate()
  outfitDescription?: string; // optional outfit → prepended to all prompts
}

export interface GenerateResponse {
  resultImage: string;
  frames: string[];
}

export type FrameResult =
  | { success: true; imageBase64: string }
  | { success: false; error: string };
