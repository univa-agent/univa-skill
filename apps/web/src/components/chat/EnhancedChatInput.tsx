"use client";

import React, { useRef, useState, useEffect } from 'react';
import { MediaSelector } from './MediaSelector';
import { MediaReference, MediaSelectorState } from './types';
import { X } from 'lucide-react';

interface EnhancedChatInputProps {
  value: string;
  onChange: (value: string) => void;
  onSend: () => void;
  onKeyDown: (e: React.KeyboardEvent) => void;
  disabled: boolean;
  referencedMedia: MediaReference[];
  onMediaReference: (media: MediaReference) => void;
  onRemoveMediaReference: (mediaId: string) => void;
}

export const EnhancedChatInput: React.FC<EnhancedChatInputProps> = ({
  value,
  onChange,
  onSend,
  onKeyDown,
  disabled,
  referencedMedia = [],
  onMediaReference,
  onRemoveMediaReference,
}) => {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const [mediaSelector, setMediaSelector] = useState<MediaSelectorState>({
    isOpen: false,
    position: { x: 0, y: 0 },
    searchQuery: '',
    selectedIndex: 0,
  });

  // Detect @ symbol and show media selector
  const handleInputChange = (newValue: string) => {
    onChange(newValue);

    // Detect @ symbol
    const textarea = textareaRef.current;
    if (!textarea) return;

    const cursorPosition = textarea.selectionStart;
    const textBeforeCursor = newValue.slice(0, cursorPosition);
    const lastAtIndex = textBeforeCursor.lastIndexOf('@');

    if (lastAtIndex !== -1) {
      // Check if there's a space after @, if so close the selector
      const textAfterAt = textBeforeCursor.slice(lastAtIndex + 1);
      if (textAfterAt.includes(' ')) {
        setMediaSelector(prev => ({ ...prev, isOpen: false }));
        return;
      }

      // Calculate selector position
      const rect = textarea.getBoundingClientRect();
      const position = {
        x: rect.left,
        y: rect.top - 280, // Selector height is about 280px
      };

      setMediaSelector({
        isOpen: true,
        position,
        searchQuery: textAfterAt,
        selectedIndex: 0,
      });
    } else {
      setMediaSelector(prev => ({ ...prev, isOpen: false }));
    }
  };

  // Handle media selection
  const handleMediaSelect = (media: MediaReference) => {
    const textarea = textareaRef.current;
    if (!textarea) return;

    const cursorPosition = textarea.selectionStart;
    const textBeforeCursor = value.slice(0, cursorPosition);
    const textAfterCursor = value.slice(cursorPosition);
    const lastAtIndex = textBeforeCursor.lastIndexOf('@');

    if (lastAtIndex !== -1) {
      // Replace @ query with media reference tag
      const beforeAt = textBeforeCursor.slice(0, lastAtIndex);
      const mediaTag = `@[${media.name}](${media.id})`;
      const newValue = beforeAt + mediaTag + ' ' + textAfterCursor;
      
      onChange(newValue);
      onMediaReference(media);
      
      // Set cursor position after media tag
      setTimeout(() => {
        const newCursorPos = beforeAt.length + mediaTag.length + 1;
        textarea.setSelectionRange(newCursorPos, newCursorPos);
        textarea.focus();
      }, 0);
    }

    setMediaSelector(prev => ({ ...prev, isOpen: false }));
  };

  // Handle keyboard events
  const handleKeyDown = (e: React.KeyboardEvent) => {
    // If selector is open, let selector handle keyboard events
    if (mediaSelector.isOpen) {
      if (['ArrowDown', 'ArrowUp', 'Enter', 'Escape'].includes(e.key)) {
        return; // Let MediaSelector handle these keys
      }
    }

    // Handle other keyboard events
    onKeyDown(e);
  };

  // Close selector
  const closeMediaSelector = () => {
    setMediaSelector(prev => ({ ...prev, isOpen: false }));
  };

  // Update search query
  const updateSearchQuery = (query: string) => {
    setMediaSelector(prev => ({ ...prev, searchQuery: query }));
  };

  // Update selected index
  const updateSelectedIndex = (index: number) => {
    setMediaSelector(prev => ({ ...prev, selectedIndex: index }));
  };

  // Render referenced media tags
  const renderMediaTags = () => {
    if (!referencedMedia || referencedMedia.length === 0) return null;

    return (
      <div className="flex flex-wrap gap-2 mb-2">
        {referencedMedia.map((media) => (
          <div
            key={media.id}
            className="inline-flex items-center gap-2 bg-blue-100 text-blue-800 px-2 py-1 rounded-md text-sm"
          >
            {/* Media preview */}
            <div className="w-4 h-4 bg-blue-200 rounded overflow-hidden flex-shrink-0">
              {media.thumbnailUrl || media.url ? (
                <img
                  src={media.thumbnailUrl || media.url}
                  alt={media.name}
                  className="w-full h-full object-cover"
                />
              ) : (
                <div className="w-full h-full bg-blue-300" />
              )}
            </div>
            
            <span className="truncate max-w-24">{media.name}</span>
            
            <button
              onClick={() => onRemoveMediaReference(media.id)}
              className="text-blue-600 hover:text-blue-800 flex-shrink-0"
              type="button"
            >
              <X className="h-3 w-3" />
            </button>
          </div>
        ))}
      </div>
    );
  };

  return (
    <div className="border-t p-4">
      {/* Referenced media tags */}
      {renderMediaTags()}
      
      <div className="flex gap-2">
        <div className="flex-1 relative">
          <textarea
            ref={textareaRef}
            value={value}
            onChange={(e) => handleInputChange(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={disabled}
            placeholder="Input message... (use @ to select media)"
            className="w-full border rounded-lg p-3 resize-none focus:outline-none focus:ring-2 focus:ring-blue-500 text-white border-gray-600 placeholder-gray-400"
            rows={3}
          />
          
          {/* Media selector */}
          <MediaSelector
            isOpen={mediaSelector.isOpen}
            position={mediaSelector.position}
            searchQuery={mediaSelector.searchQuery}
            selectedIndex={mediaSelector.selectedIndex}
            onSelect={handleMediaSelect}
            onClose={closeMediaSelector}
            onSearchChange={updateSearchQuery}
            onSelectedIndexChange={updateSelectedIndex}
          />
        </div>
        
        <button
          onClick={onSend}
          disabled={disabled || !value.trim()}
          className="bg-blue-500 hover:bg-blue-600 disabled:bg-gray-300 disabled:cursor-not-allowed text-white rounded-lg px-6 py-3 font-medium transition-colors"
        >
          Send
        </button>
      </div>
      
      <div className="text-xs text-gray-500 mt-2 flex justify-between">
        <span>{value.length}/2000 characters</span>
        {referencedMedia.length > 0 && (
          <span>{referencedMedia.length} materials referenced</span>
        )}
      </div>
    </div>
  );
};