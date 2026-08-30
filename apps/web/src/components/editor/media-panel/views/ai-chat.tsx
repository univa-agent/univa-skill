"use client";

import React, { useMemo } from 'react';
import { useChat } from '@/components/chat/useChat';
import { ChatMessages } from '@/components/chat/ChatMessages';
import { EnhancedChatInput } from '@/components/chat/EnhancedChatInput';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Button } from '@/components/ui/button';
import { MessageCircle, Trash2, Film, Image, Music } from 'lucide-react';
import { useMediaStore } from '@/stores/media-store';
import { mediaImporter } from '@/components/chat/utils/mediaImporter';
import { useProjectStore } from '@/stores/project-store';
import type { GeneratedFile } from '@/components/chat/types';
import { toast } from 'sonner';

/**
 * Build media context from the store's serverPath values.
 * Files are uploaded on-add to the media panel, so by the time the user
 * sends a message, serverPath is already populated.
 */
function buildMediaContext(): string {
  const mediaItems = useMediaStore.getState().mediaItems;
  if (mediaItems.length === 0) return '';

  const withPath = mediaItems.filter(m => m.serverPath);
  const lines = [
    '## Available Media Files',
    'The following list is the authoritative frontend media order. When answering questions about current media names, counts, or numbered references, preserve this exact order and numbering.',
  ];
  mediaItems.forEach((item, i) => {
    const icon = item.type === 'video' ? '🎬' : item.type === 'image' ? '🖼️' : '🎵';
    const label = item.name || item.file?.name || `file_${i + 1}`;
    if (item.serverPath) {
      lines.push(`[${i + 1}] ${icon} ${label} (${item.type}${item.duration ? `, ${item.duration.toFixed(1)}s` : ''}) → ${item.serverPath}`);
    } else {
      lines.push(`[${i + 1}] ${icon} ${label} (${item.type}) [uploading...]`);
    }
  });
  lines.push('');
  if (withPath.length === mediaItems.length) {
    lines.push('All files are on the server. Use the absolute paths after → when calling tools. Keep the numbering exactly as listed above.');
  } else {
    lines.push(`${withPath.length}/${mediaItems.length} files on server. Avoid calling tools on files marked [uploading...].`);
  }
  lines.push('');
  return lines.join('\n');
}

export function AiChatView() {
  // Auto-import callback: when the AI generates files, add them to the media library
  const activeProject = useProjectStore((s) => s.activeProject);
  const addMediaItem = useMediaStore((s) => s.addMediaItem);

  const handleFilesGenerated = React.useCallback(async (files: GeneratedFile[]) => {
    if (!activeProject?.id) return;
    try {
      const result = await mediaImporter.importFiles(files, addMediaItem, activeProject.id);
      if (result.success.length > 0) {
        toast.success(`Automatically imported ${result.success.length} files into the media library`);
      }
      if (result.failed.length > 0) {
        console.warn('Some files failed to auto-import:', result.failed);
      }
    } catch (err) {
      console.error('Auto-import failed:', err);
    }
  }, [activeProject?.id, addMediaItem]);

  const {
    messages,
    inputText,
    isLoading,
    error,
    referencedMedia,
    handleInputChange,
    handleSend: originalHandleSend,
    handleKeyDown,
    clearChat,
    handleMediaReference,
    removeMediaReference,
    resumePipeline,
    sendMessage,
  } = useChat({ onFilesGenerated: handleFilesGenerated });

  const [isResuming, setIsResuming] = React.useState(false);

  // Subscribe to media store for the media bar display
  const mediaItems = useMediaStore((s) => s.mediaItems);

  const handleResumePipeline = async (userInput: string) => {
    setIsResuming(true);
    try {
      await resumePipeline(userInput);
    } finally {
      setIsResuming(false);
    }
  };

  // Inject media context (with pre-uploaded server paths from the store)
  const handleSend = () => {
    if (!inputText.trim() || isLoading) return;

    const mediaItems = useMediaStore.getState().mediaItems;
    if (mediaItems.length > 0) {
      const mediaContext = buildMediaContext();
      const enhancedMessage = `${mediaContext}\nUser request: ${inputText.trim()}`;
      sendMessage(enhancedMessage, inputText.trim());
      handleInputChange('');
    } else {
      originalHandleSend();
    }
  };

  // Compact media bar showing available files (for display only)
  const mediaBar = useMemo(() => {
    if (mediaItems.length === 0) return null;

    const iconMap = { video: Film, image: Image, audio: Music };
    return (
      <div className="px-3 py-1.5 bg-gray-50 border-b border-border/30 text-xs text-gray-600 flex items-center gap-3 overflow-x-auto whitespace-nowrap">
        <span className="font-medium text-gray-700 flex-shrink-0">📁 Media ({mediaItems.length}):</span>
        {mediaItems.map((item, i) => {
          const Icon = iconMap[item.type] || Film;
          const label = item.name?.length > 24 ? item.name.slice(0, 22) + '…' : item.name;
          return (
            <span key={item.id} className="inline-flex items-center gap-1 flex-shrink-0">
              <Icon className="h-3 w-3" />
              <span className="text-blue-600 font-mono">[{i + 1}]</span>
              <span>{label}</span>
            </span>
          );
        })}
      </div>
    );
  }, [mediaItems]);

  return (
    <div className="h-full flex flex-col bg-panel">
      {/* Header */}
      <div className="p-3 pb-2 bg-panel border-b border-border/50">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <MessageCircle className="h-4 w-4 text-primary" />
            <span className="text-sm font-medium">AI Assistant</span>
            {mediaItems.length > 0 && (
              <span className="text-xs text-muted-foreground">
                ({mediaItems.length} files)
              </span>
            )}
          </div>
          {messages.length > 0 && (
            <Button
              size="sm"
              variant="outline"
              onClick={clearChat}
              className="h-7 px-2 text-xs"
            >
              <Trash2 className="h-3 w-3 mr-1" />
              Clear
            </Button>
          )}
        </div>
      </div>

      {/* Media bar */}
      {mediaBar}

      {/* Chat area */}
      <div className="flex-1 flex flex-col min-h-0">
        <ScrollArea className="flex-1 px-3">
          {messages.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full text-center py-8">
              <MessageCircle className="h-12 w-12 text-muted-foreground/50 mb-4" />
              <h3 className="text-sm font-medium text-foreground mb-2">
                AI Video Assistant
              </h3>
              <div className="text-xs text-muted-foreground max-w-[240px] leading-relaxed space-y-2">
                {mediaItems.length > 0 ? (
                  <>
                    <p>{mediaItems.length} file(s) loaded and ready.</p>
                    <p className="text-blue-600">
                      Try: "edit video [1]" or "analyze [2]"
                    </p>
                  </>
                ) : (
                  <p>Upload files in the Media tab, then ask me to edit or analyze them.</p>
                )}
              </div>
            </div>
          ) : (
            <div className="py-3">
              <ChatMessages
                messages={messages}
                onResumePipeline={handleResumePipeline}
                isResuming={isResuming}
              />
            </div>
          )}
        </ScrollArea>

        {/* Error message */}
        {error && (
          <div className="mx-3 mb-2 bg-destructive/10 border border-destructive/20 text-destructive px-3 py-2 rounded-md text-xs">
            <div className="flex items-start gap-2">
              <svg className="h-4 w-4 mt-0.5 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
              </svg>
              <div className="flex-1">
                <strong className="font-medium">Error:</strong> {error}
              </div>
            </div>
          </div>
        )}

        {/* Input area */}
        <div className="p-3 pt-2 border-t border-border/50">
          <EnhancedChatInput
            value={inputText}
            onChange={handleInputChange}
            onSend={handleSend}
            onKeyDown={handleKeyDown}
            disabled={isLoading}
            referencedMedia={referencedMedia}
            onMediaReference={handleMediaReference}
            onRemoveMediaReference={removeMediaReference}
          />
        </div>
      </div>
    </div>
  );
}
