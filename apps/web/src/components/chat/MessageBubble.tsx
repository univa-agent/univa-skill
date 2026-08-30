"use client";

import React from 'react';
import { Message, TodoItem } from './types';
import { FileImportButton } from './FileImportButton';
import { PipelineInteractionCard } from './PipelineInteractionCard';

interface MessageBubbleProps {
  message: Message;
  onResumePipeline?: (userInput: string) => Promise<void>;
  isResuming?: boolean;
}

export const MessageBubble: React.FC<MessageBubbleProps> = ({ message, onResumePipeline, isResuming }) => {
  const isUser = message.role === 'user';

  const formatDate = (timestamp: string) => {
    try {
      const date = new Date(timestamp);
      return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    } catch (e) {
      return timestamp;
    }
  };

  // Render pipeline_suspended as interactive card
  if (message.messageType === 'pipeline_suspended' && onResumePipeline) {
    return (
      <div className="flex justify-start mb-4">
        <div className="max-w-3xl rounded-lg p-4 bg-gray-100 text-gray-800">
          <div className="flex items-center mb-1">
            <span className="font-semibold text-sm">Assistant</span>
            <span className="text-xs opacity-70 ml-2">{formatDate(message.timestamp)}</span>
          </div>
          <div className="whitespace-pre-wrap text-sm">{message.content}</div>
          <PipelineInteractionCard
            message={message}
            onResume={onResumePipeline}
            isLoading={isResuming}
          />
        </div>
      </div>
    );
  }

  // Render pipeline_stage as compact status
  if (message.messageType === 'pipeline_stage') {
    return (
      <div className="flex justify-center mb-2">
        <span className="text-xs text-gray-500 bg-gray-50 px-3 py-1 rounded-full">
          {message.content}
        </span>
      </div>
    );
  }

  // Render budget_update as compact badge
  if (message.messageType === 'budget_update') {
    return (
      <div className="flex justify-end mb-2">
        <span className="text-xs text-gray-500 bg-yellow-50 border border-yellow-100 px-3 py-1 rounded-full">
          {message.content}
        </span>
      </div>
    );
  }
  
  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'} mb-4`}>
      <div
        className={`max-w-3xl rounded-lg p-4 ${
          isUser
            ? 'bg-blue-500 text-white'
            : 'bg-gray-100 text-gray-800'
        }`}
      >
        <div className="flex items-center mb-1">
          <span className="font-semibold text-sm">
            {isUser ? 'You' : 'Assistant'}
          </span>
          <span className="text-xs opacity-70 ml-2">
            {formatDate(message.timestamp)}
          </span>
        </div>
        <div className="whitespace-pre-wrap">
          {message.messageType === 'todo_progress' ? (
            <div>
              {message.overallDescription && (
                <div className="font-semibold mb-2">{message.overallDescription}</div>
              )}
              <div className="space-y-2">
                {message.todoItems?.map((item) => (
                  <div key={item.id} className="flex items-center">
                    <div className={`w-4 h-4 rounded-full mr-2 flex items-center justify-center ${
                      item.status === 'completed' ? 'bg-green-500' :
                      item.status === 'in_progress' ? 'bg-blue-500' : 'bg-gray-300'
                    }`}>
                      {item.status === 'completed' && (
                        <svg className="w-3 h-3 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M5 13l4 4L19 7" />
                        </svg>
                      )}
                      {item.status === 'in_progress' && (
                        <div className="w-2 h-2 bg-white rounded-full animate-pulse" />
                      )}
                    </div>
                    <span className={item.status === 'in_progress' ? 'font-semibold' : ''}>
                      {item.description}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          ) : message.messageType === 'completion' ? (
            <div>
              <div className="font-semibold text-green-600 mb-2">{message.content || '✅ Task completed'}</div>
              {message.overallDescription && (
                <div className="mb-2">{message.overallDescription}</div>
              )}
              <div className="space-y-2">
                {message.todoItems?.map((item) => (
                  <div key={item.id} className="flex items-center">
                    <div className="w-4 h-4 rounded-full mr-2 flex items-center justify-center bg-green-500">
                      <svg className="w-3 h-3 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M5 13l4 4L19 7" />
                      </svg>
                    </div>
                    <span>{item.description}</span>
                  </div>
                ))}
              </div>
            </div>
          ) : message.messageType === 'tool_start' ? (
            <div className="flex items-center">
              <span>{message.content}</span>
              <span className="ml-2 flex space-x-1">
                <span className="w-2 h-2 bg-current rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                <span className="w-2 h-2 bg-current rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                <span className="w-2 h-2 bg-current rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
              </span>
            </div>
          ) : (
            <>
              {message.content}
              {message.isStreaming && (
                <span className="inline-block w-2 h-4 bg-current animate-pulse ml-1" />
              )}
            </>
          )}
        </div>
        
        {/* Show file import button */}
        {!isUser && message.generatedFiles && message.generatedFiles.length > 0 && (
          <div className="mt-3 pt-3 border-t border-gray-200">
            <div className="text-xs text-gray-600 mb-2">
              Detected {message.generatedFiles.length} generated files:
            </div>
            <div className="space-y-1 mb-3">
              {message.generatedFiles.map((file, index) => {
                console.log('DEBUG: Rendering file:', file);
                console.log('DEBUG: File name:', file.name);
                console.log('DEBUG: File path:', file.path);
                return (
                  <div key={index} className="text-xs text-gray-500 flex items-center">
                    <span className="inline-block w-2 h-2 bg-blue-500 rounded-full mr-2" />
                    <span className="font-mono">{file.path}</span>
                    <span className="ml-2 px-1 py-0.5 bg-gray-100 rounded text-xs">
                      {file.type}
                    </span>
                  </div>
                );
              })}
            </div>
            <FileImportButton
              generatedFiles={message.generatedFiles}
              className="w-full"
            />
          </div>
        )}
      </div>
    </div>
  );
};