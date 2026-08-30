const fontClassName = "";

// Keep the editor font API independent from Google Fonts network fetches.
export const FONT_CLASS_MAP = {
  Inter: fontClassName,
  Roboto: fontClassName,
  "Open Sans": fontClassName,
  "Playfair Display": fontClassName,
  "Comic Neue": fontClassName,
  Arial: fontClassName,
  Helvetica: fontClassName,
  "Times New Roman": fontClassName,
  Georgia: fontClassName,
} as const;

export const fonts = {
  inter: { className: fontClassName },
  roboto: { className: fontClassName },
  openSans: { className: fontClassName },
  playfairDisplay: { className: fontClassName },
  comicNeue: { className: fontClassName },
};

export const defaultFont = fonts.inter;
