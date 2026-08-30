import { MediaReference } from '../types';

/**
 * Parse media reference tags in messages
 * Format: @[media name](media ID)
 */
export function parseMediaReferences(text: string): {
  cleanText: string;
  mediaReferences: { id: string; name: string; position: number }[];
} {
  const mediaReferences: { id: string; name: string; position: number }[] = [];
  const mediaReferenceRegex = /@\[([^\]]+)\]\(([^)]+)\)/g;
  let match;
  let cleanText = text;
  let offset = 0;

  while ((match = mediaReferenceRegex.exec(text)) !== null) {
    const [fullMatch, name, id] = match;
    const position = match.index - offset;
    
    mediaReferences.push({
      id,
      name,
      position,
    });

    // Replace media reference tag with simplified display text
    cleanText = cleanText.replace(fullMatch, `@${name}`);
    offset += fullMatch.length - `@${name}`.length;
  }

  return {
    cleanText,
    mediaReferences,
  };
}

/**
 * Add media reference information to message text
 */
export function addMediaReferencesToText(
  text: string,
  mediaReferences: MediaReference[]
): string {
  let result = text;
  
  // Add media reference information at the end of message
  if (mediaReferences.length > 0) {
    result += '\n\nReferenced materials:\n';
    mediaReferences.forEach((media, index) => {
      result += `${index + 1}. ${media.name} (${media.type})\n`;
    });
  }
  
  return result;
}

/**
 * Validate if media references are valid
 */
export function validateMediaReferences(
  text: string,
  availableMedia: MediaReference[]
): {
  isValid: boolean;
  invalidReferences: string[];
} {
  const { mediaReferences } = parseMediaReferences(text);
  const availableMediaIds = new Set(availableMedia.map(m => m.id));
  const invalidReferences: string[] = [];

  mediaReferences.forEach(ref => {
    if (!availableMediaIds.has(ref.id)) {
      invalidReferences.push(ref.name);
    }
  });

  return {
    isValid: invalidReferences.length === 0,
    invalidReferences,
  };
}

/**
 * Extract all media IDs from text
 */
export function extractMediaIds(text: string): string[] {
  const { mediaReferences } = parseMediaReferences(text);
  return mediaReferences.map(ref => ref.id);
}