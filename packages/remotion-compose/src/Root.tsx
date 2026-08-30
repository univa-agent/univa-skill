import { Composition, type CalculateMetadataFunction } from "remotion";
import { UniVACompose } from "./UniVACompose";
import type { UniVAComposeProps } from "./types";

const calculateMetadata: CalculateMetadataFunction<UniVAComposeProps> = async ({
  props,
}) => {
  const explicitDuration = Number(props.durationSeconds || 0);
  const captionEnd = Math.max(
    0,
    ...(props.captions || []).map((caption) => Number(caption.endSeconds || 0)),
  );
  const overlayEnd = Math.max(
    0,
    ...(props.overlays || []).map((overlay) => Number(overlay.endSeconds || 0)),
  );
  const durationSeconds = Math.max(explicitDuration, captionEnd, overlayEnd, 1);

  return {
    durationInFrames: Math.ceil(durationSeconds * 30),
  };
};

export const Root: React.FC = () => {
  return (
    <Composition
      id="UniVACompose"
      component={UniVACompose}
      durationInFrames={30 * 60}
      fps={30}
      width={1920}
      height={1080}
      defaultProps={{
        videoSrc: "",
        captions: [],
        overlays: [],
        showProgress: true,
        fit: "cover",
      }}
      calculateMetadata={calculateMetadata}
    />
  );
};
