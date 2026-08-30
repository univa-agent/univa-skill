"use client";

import React, { useRef, useEffect } from 'react';
import { Message } from './types';
import { MessageBubble } from './MessageBubble';

interface ChatMessagesProps {
  messages: Message[];
  onResumePipeline?: (userInput: string) => Promise<void>;
  isResuming?: boolean;
}

export const ChatMessages: React.FC<ChatMessagesProps> = ({ messages, onResumePipeline, isResuming }) => {
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  return (
    <div className="flex-1 overflow-y-auto p-4 space-y-4">
      {messages.length === 0 ? (
        <div className="flex items-center justify-center h-full">
          <div className="text-center text-gray-500">
            <p className="text-lg">Welcome to the chat!</p>
            <p className="text-sm">Start a conversation by sending a message.</p>
          </div>
        </div>
      ) : (
        <>
          {messages.map((message) => (
            <MessageBubble
              key={message.id}
              message={message}
              onResumePipeline={onResumePipeline}
              isResuming={isResuming}
            />
          ))}
          <div ref={messagesEndRef} />
        </>
      )}
    </div>
  );
};