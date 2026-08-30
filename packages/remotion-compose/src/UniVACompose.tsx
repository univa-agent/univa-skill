import type React from "react";
import {
  AbsoluteFill,
  Img,
  OffthreadVideo,
  Sequence,
  interpolate,
  spring,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import type {
  CaptionCue,
  ComposeTheme,
  OverlayCue,
  OverlayPosition,
  UniVAComposeProps,
} from "./types";

const DEFAULT_THEME: Required<ComposeTheme> = {
  backgroundColor: "#101820",
  surfaceColor: "rgba(16, 24, 32, 0.78)",
  textColor: "#F7FAFC",
  mutedTextColor: "#D7DEE8",
  accentColor: "#2EC4B6",
  captionBackground: "rgba(7, 12, 18, 0.72)",
};

const positionStyle = (
  position: OverlayPosition | undefined,
): React.CSSProperties => {
  const base: React.CSSProperties = { position: "absolute" };
  switch (position) {
    case "top_left":
      return { ...base, top: 72, left: 72, maxWidth: 760 };
    case "top_right":
      return { ...base, top: 72, right: 72, maxWidth: 760 };
    case "lower_right":
      return { ...base, right: 72, bottom: 190, maxWidth: 760 };
    case "center":
      return {
        ...base,
        left: "50%",
        top: "50%",
        transform: "translate(-50%, -50%)",
        width: "min(1120px, 78%)",
      };
    case "bottom_center":
      return {
        ...base,
        left: "50%",
        bottom: 150,
        transform: "translateX(-50%)",
        width: "min(1120px, 78%)",
      };
    case "lower_left":
    default:
      return { ...base, left: 72, bottom: 190, maxWidth: 760 };
  }
};

const secondsToFrame = (seconds: number, fps: number) =>
  Math.max(0, Math.round(seconds * fps));

const fitStyle = (fit: "cover" | "contain" | undefined): React.CSSProperties => ({
  width: "100%",
  height: "100%",
  objectFit: fit || "cover",
});

const activeCaption = (
  captions: CaptionCue[] | undefined,
  second: number,
): CaptionCue | undefined =>
  (captions || []).find(
    (caption) => second >= caption.startSeconds && second < caption.endSeconds,
  );

const CaptionLayer: React.FC<{
  captions?: CaptionCue[];
  theme: Required<ComposeTheme>;
}> = ({ captions, theme }) => {
  const frame = useCurrentFrame();
  const { fps, width } = useVideoConfig();
  const cue = activeCaption(captions, frame / fps);
  if (!cue) {
    return null;
  }

  return (
    <div
      style={{
        position: "absolute",
        left: "50%",
        bottom: 48,
        transform: "translateX(-50%)",
        maxWidth: Math.min(width * 0.82, 1280),
        padding: "22px 34px",
        borderRadius: 8,
        color: theme.textColor,
        background: theme.captionBackground,
        border: `2px solid ${theme.accentColor}`,
        boxShadow: "0 18px 48px rgba(0, 0, 0, 0.3)",
        fontFamily: "Inter, Arial, sans-serif",
        fontSize: 42,
        fontWeight: 750,
        lineHeight: 1.18,
        textAlign: "center",
        textWrap: "balance",
      }}
    >
      {cue.text}
    </div>
  );
};

const OverlayCard: React.FC<{
  overlay: OverlayCue;
  theme: Required<ComposeTheme>;
}> = ({ overlay, theme }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const entrance = spring({
    frame,
    fps,
    config: { damping: 22, stiffness: 150, mass: 0.9 },
  });
  const opacity = interpolate(frame, [0, 8], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const accent = overlay.accentColor || theme.accentColor;
  const isTitle = overlay.type === "title_card";
  const isBadge = overlay.type === "badge";

  return (
    <div
      style={{
        ...positionStyle(overlay.position),
        opacity,
        transform: `${positionStyle(overlay.position).transform || ""} translateY(${(1 - entrance) * 22}px)`,
        padding: isBadge ? "14px 22px" : isTitle ? "34px 42px" : "24px 30px",
        borderRadius: 8,
        background: isTitle ? "rgba(9, 16, 24, 0.5)" : theme.surfaceColor,
        borderLeft: `8px solid ${accent}`,
        boxShadow: "0 18px 60px rgba(0, 0, 0, 0.34)",
        fontFamily: "Inter, Arial, sans-serif",
      }}
    >
      {overlay.eyebrow ? (
        <div
          style={{
            color: accent,
            fontSize: 24,
            fontWeight: 800,
            letterSpacing: 0,
            marginBottom: 10,
            textTransform: "uppercase",
          }}
        >
          {overlay.eyebrow}
        </div>
      ) : null}
      {overlay.value ? (
        <div
          style={{
            color: accent,
            fontSize: 68,
            fontWeight: 850,
            lineHeight: 0.98,
            marginBottom: 8,
          }}
        >
          {overlay.value}
        </div>
      ) : null}
      <div
        style={{
          color: theme.textColor,
          fontSize: isTitle ? 68 : isBadge ? 28 : 38,
          fontWeight: isTitle ? 850 : 760,
          lineHeight: 1.06,
          textWrap: "balance",
        }}
      >
        {overlay.text}
      </div>
    </div>
  );
};

const IntroTitle: React.FC<{
  title?: string;
  subtitle?: string;
  theme: Required<ComposeTheme>;
}> = ({ title, subtitle, theme }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  if (!title) {
    return null;
  }
  const opacity = interpolate(frame, [0, 12, fps * 3.2, fps * 4], [0, 1, 1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const y = interpolate(frame, [0, 18], [24, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return (
    <div
      style={{
        position: "absolute",
        left: 72,
        top: 82,
        width: "min(1180px, 72%)",
        opacity,
        transform: `translateY(${y}px)`,
        fontFamily: "Inter, Arial, sans-serif",
        color: theme.textColor,
      }}
    >
      <div
        style={{
          width: 112,
          height: 8,
          borderRadius: 999,
          background: theme.accentColor,
          marginBottom: 26,
        }}
      />
      <div style={{ fontSize: 82, fontWeight: 880, lineHeight: 0.98 }}>
        {title}
      </div>
      {subtitle ? (
        <div
          style={{
            marginTop: 18,
            maxWidth: 860,
            color: theme.mutedTextColor,
            fontSize: 34,
            fontWeight: 620,
            lineHeight: 1.2,
          }}
        >
          {subtitle}
        </div>
      ) : null}
    </div>
  );
};

const BrandBug: React.FC<{
  brand?: UniVAComposeProps["brand"];
  theme: Required<ComposeTheme>;
}> = ({ brand, theme }) => {
  if (!brand?.name && !brand?.logoSrc) {
    return null;
  }
  return (
    <div
      style={{
        position: "absolute",
        right: 46,
        top: 38,
        display: "flex",
        alignItems: "center",
        gap: 14,
        padding: "12px 16px",
        borderRadius: 8,
        color: theme.textColor,
        background: "rgba(6, 10, 15, 0.46)",
        fontFamily: "Inter, Arial, sans-serif",
        fontSize: 24,
        fontWeight: 760,
      }}
    >
      {brand.logoSrc ? (
        <Img
          src={staticFile(brand.logoSrc)}
          style={{ width: 40, height: 40, objectFit: "contain" }}
        />
      ) : null}
      {brand.name ? <span>{brand.name}</span> : null}
    </div>
  );
};

const ProgressBar: React.FC<{ color: string }> = ({ color }) => {
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();
  const progress = durationInFrames > 0 ? frame / durationInFrames : 0;
  return (
    <div
      style={{
        position: "absolute",
        left: 0,
        right: 0,
        bottom: 0,
        height: 8,
        background: "rgba(255, 255, 255, 0.16)",
      }}
    >
      <div
        style={{
          width: `${Math.min(100, Math.max(0, progress * 100))}%`,
          height: "100%",
          background: color,
        }}
      />
    </div>
  );
};

export const UniVACompose: React.FC<UniVAComposeProps> = ({
  videoSrc,
  title,
  subtitle,
  captions,
  overlays,
  brand,
  theme,
  showProgress = true,
  fit = "cover",
}) => {
  const { fps } = useVideoConfig();
  const resolvedTheme = { ...DEFAULT_THEME, ...(theme || {}) };

  return (
    <AbsoluteFill style={{ background: resolvedTheme.backgroundColor }}>
      {videoSrc ? (
        <OffthreadVideo src={staticFile(videoSrc)} style={fitStyle(fit)} />
      ) : null}
      <AbsoluteFill
        style={{
          background:
            "linear-gradient(180deg, rgba(0, 0, 0, 0.35), rgba(0, 0, 0, 0) 32%, rgba(0, 0, 0, 0.45))",
        }}
      />
      <IntroTitle title={title} subtitle={subtitle} theme={resolvedTheme} />
      {(overlays || []).map((overlay, index) => {
        const start = secondsToFrame(overlay.startSeconds, fps);
        const end = secondsToFrame(overlay.endSeconds, fps);
        return (
          <Sequence
            key={overlay.id || `${overlay.type}-${index}`}
            from={start}
            durationInFrames={Math.max(1, end - start)}
          >
            <OverlayCard overlay={overlay} theme={resolvedTheme} />
          </Sequence>
        );
      })}
      <CaptionLayer captions={captions} theme={resolvedTheme} />
      <BrandBug brand={brand} theme={resolvedTheme} />
      {showProgress ? <ProgressBar color={resolvedTheme.accentColor} /> : null}
    </AbsoluteFill>
  );
};
