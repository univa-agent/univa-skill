"use client";

import React from 'react';
import { useChat } from './useChat';
import { ChatMessages } from './ChatMessages';
import { EnhancedChatInput } from './EnhancedChatInput';
import { ConnectionStatus } from './ConnectionStatus';

export const ChatContainer: React.FC = () => {
  const {
    messages,
    inputText,
    isLoading,
    error,
    referencedMedia,
    connectionStatus,
    retryCount,
    maxRetries,
    handleInputChange,
    handleSend,
    handleKeyDown,
    handleMediaReference,
    removeMediaReference,
    resumePipeline,
  } = useChat();

  const [isResuming, setIsResuming] = React.useState(false);

  const handleResumePipeline = async (userInput: string) => {
    setIsResuming(true);
    try {
      await resumePipeline(userInput);
    } finally {
      setIsResuming(false);
    }
  };

  return (
    <div className="flex flex-col h-full max-w-4xl mx-auto">
      {/* Connection status */}
      {(isLoading || connectionStatus !== 'disconnected') && (
        <div className="flex justify-center p-2">
          <ConnectionStatus
            connectionStatus={connectionStatus}
            retryCount={retryCount}
            maxRetries={maxRetries}
            isLoading={isLoading}
          />
        </div>
      )}

      <div className="flex-1 flex flex-col">
        <ChatMessages
          messages={messages}
          onResumePipeline={handleResumePipeline}
          isResuming={isResuming}
        />
      </div>
      
      {error && (
        <div className="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded mx-4 mb-4">
          <strong>Error:</strong> {error}
          <button
            onClick={() => window.location.reload()}
            className="ml-4 text-sm underline"
          >
            Reload
          </button>
        </div>
      )}
      
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
  );
};