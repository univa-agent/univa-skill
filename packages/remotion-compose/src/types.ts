export type CaptionCue = {
  text: string;
  startSeconds: number;
  endSeconds: number;
};

export type OverlayKind =
  | "title_card"
  | "lower_third"
  | "callout"
  | "badge"
  | "cta"
  | "stat";

export type OverlayPosition =
  | "top_left"
  | "top_right"
  | "lower_left"
  | "lower_right"
  | "center"
  | "bottom_center";

export type OverlayCue = {
  id?: string;
  type: OverlayKind;
  text: string;
  startSeconds: number;
  endSeconds: number;
  position?: OverlayPosition;
  eyebrow?: string;
  value?: string;
  accentColor?: string;
};

export type BrandConfig = {
  name?: string;
  logoSrc?: string;
  accentColor?: string;
};

export type ComposeTheme = {
  backgroundColor?: string;
  surfaceColor?: string;
  textColor?: string;
  mutedTextColor?: string;
  accentColor?: string;
  captionBackground?: string;
};

export type UniVAComposeProps = {
  videoSrc: string;
  title?: string;
  subtitle?: string;
  durationSeconds?: number;
  captions?: CaptionCue[];
  overlays?: OverlayCue[];
  brand?: BrandConfig;
  theme?: ComposeTheme;
  showProgress?: boolean;
  fit?: "cover" | "contain";
};
