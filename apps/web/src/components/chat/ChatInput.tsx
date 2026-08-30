"use client";

import React from 'react';

interface ChatInputProps {
  value: string;
  onChange: (value: string) => void;
  onSend: () => void;
  onKeyDown: (e: React.KeyboardEvent) => void;
  disabled: boolean;
}

export const ChatInput: React.FC<ChatInputProps> = ({
  value,
  onChange,
  onSend,
  onKeyDown,
  disabled,
}) => {
  return (
    <div className="border-t p-4">
      <div className="flex gap-2">
        <textarea
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={onKeyDown}
          disabled={disabled}
          placeholder="Type your message here... (Press Enter to send, Shift+Enter for new line)"
          className="flex-1 border rounded-lg p-3 resize-none focus:outline-none focus:ring-2 focus:ring-blue-500 text-white border-gray-600 placeholder-gray-400"
          rows={3}
        />
        <button
          onClick={onSend}
          disabled={disabled || !value.trim()}
          className="bg-blue-500 hover:bg-blue-600 disabled:bg-gray-300 disabled:cursor-not-allowed text-white rounded-lg px-6 py-3 font-medium transition-colors"
        >
          Send
        </button>
      </div>
      <div className="text-xs text-gray-500 mt-2">
        {value.length}/2000 characters
      </div>
    </div>
  );
};