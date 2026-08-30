"use client";

import React, { useEffect, useRef } from 'react';
import { useMediaStore, type MediaItem } from '@/stores/media-store';
import { MediaReference } from './types';
import { Search, Video, Image, Music } from 'lucide-react';
import { ScrollArea } from '@/components/ui/scroll-area';

interface MediaSelectorProps {
  isOpen: boolean;
  position: { x: number; y: number };
  searchQuery: string;
  selectedIndex: number;
  onSelect: (media: MediaReference) => void;
  onClose: () => void;
  onSearchChange: (query: string) => void;
  onSelectedIndexChange: (index: number) => void;
}

export const MediaSelector: React.FC<MediaSelectorProps> = ({
  isOpen,
  position,
  searchQuery,
  selectedIndex,
  onSelect,
  onClose,
  onSearchChange,
  onSelectedIndexChange,
}) => {
  const selectorRef = useRef<HTMLDivElement>(null);
  const { mediaItems } = useMediaStore();

  // Filter media items
  const filteredMedia = mediaItems.filter(item =>
    item.name.toLowerCase().includes(searchQuery.toLowerCase())
  );

  // Handle keyboard navigation
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (!isOpen) return;

      switch (e.key) {
        case 'ArrowDown':
          e.preventDefault();
          onSelectedIndexChange(Math.min(selectedIndex + 1, filteredMedia.length - 1));
          break;
        case 'ArrowUp':
          e.preventDefault();
          onSelectedIndexChange(Math.max(selectedIndex - 1, 0));
          break;
        case 'Enter':
          e.preventDefault();
          if (filteredMedia[selectedIndex]) {
            handleSelect(filteredMedia[selectedIndex]);
          }
          break;
        case 'Escape':
          e.preventDefault();
          onClose();
          break;
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, selectedIndex, filteredMedia, onSelectedIndexChange, onClose]);

  // Close on outside click
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (selectorRef.current && !selectorRef.current.contains(e.target as Node)) {
        onClose();
      }
    };

    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside);
      return () => document.removeEventListener('mousedown', handleClickOutside);
    }
  }, [isOpen, onClose]);

  const handleSelect = (item: MediaItem) => {
    const mediaRef: MediaReference = {
      id: item.id,
      name: item.name,
      type: item.type,
      url: item.url,
      thumbnailUrl: item.thumbnailUrl,
    };
    onSelect(mediaRef);
  };

  const getMediaIcon = (type: string) => {
    switch (type) {
      case 'video':
        return <Video className="h-4 w-4" />;
      case 'image':
        return <Image className="h-4 w-4" />;
      case 'audio':
        return <Music className="h-4 w-4" />;
      default:
        return <Video className="h-4 w-4" />;
    }
  };

  if (!isOpen) return null;

  return (
    <div
      ref={selectorRef}
      className="fixed z-50 bg-white border border-gray-200 rounded-lg shadow-lg w-80 max-h-64"
      style={{
        left: position.x,
        top: position.y,
      }}
    >
      {/* Search box */}
      <div className="p-3 border-b border-gray-100">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-gray-400" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => onSearchChange(e.target.value)}
            placeholder="Search Media..."
            className="w-full pl-10 pr-3 py-2 text-sm border border-gray-200 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent text-gray-800"
            autoFocus
          />
        </div>
      </div>

      {/* Media list */}
      <ScrollArea className="max-h-48">
        {filteredMedia.length === 0 ? (
          <div className="p-4 text-center text-gray-500 text-sm">
            {searchQuery ? 'No match found' : 'No media in library'}
          </div>
        ) : (
          <div className="p-1">
            {filteredMedia.map((item, index) => (
              <div
                key={item.id}
                className={`flex items-center gap-3 p-2 rounded-md cursor-pointer transition-colors ${
                  index === selectedIndex
                    ? 'bg-blue-50 border border-blue-200'
                    : 'hover:bg-gray-50'
                }`}
                onClick={() => handleSelect(item)}
              >
                {/* Media preview */}
                <div className="flex-shrink-0 w-10 h-10 bg-gray-100 rounded-md flex items-center justify-center overflow-hidden">
                  {item.thumbnailUrl || item.url ? (
                    <img
                      src={item.thumbnailUrl || item.url}
                      alt={item.name}
                      className="w-full h-full object-cover"
                    />
                  ) : (
                    <div className="text-gray-400">
                      {getMediaIcon(item.type)}
                    </div>
                  )}
                </div>

                {/* Media information */}
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-medium text-gray-900 truncate">
                    {item.name}
                  </div>
                  <div className="text-xs text-gray-500 capitalize">
                    {item.type}
                    {item.duration && (
                      <span className="ml-1">
                        • {Math.round(item.duration)}s
                      </span>
                    )}
                  </div>
                </div>

                {/* Type icon */}
                <div className="flex-shrink-0 text-gray-400">
                  {getMediaIcon(item.type)}
                </div>
              </div>
            ))}
          </div>
        )}
      </ScrollArea>

      {/* Hint information */}
      <div className="p-2 border-t border-gray-100 text-xs text-gray-500">
        <div className="flex justify-between">
          <span>↑↓ Navi</span>
          <span>Enter Sel</span>
          <span>Esc Close</span>
        </div>
      </div>
    </div>
  );
};