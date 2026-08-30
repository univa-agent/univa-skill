import React from 'react';
import { ChatContainer } from '@/components/chat';
import { ChatSettings } from '@/components/chat-settings';

export default function ChatPage() {
  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white shadow">
        <div className="max-w-7xl mx-auto py-6 px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-3xl font-bold text-gray-900">AI Chat</h1>
              <p className="mt-1 text-sm text-gray-500">
                Chat with our AI assistant powered by univa
              </p>
            </div>
            <ChatSettings />
          </div>
        </div>
      </header>
      <main>
        <div className="max-w-7xl mx-auto py-6 sm:px-6 lg:px-8">
          <div className="px-4 py-6 sm:px-0">
            <div className="rounded-lg h-[calc(100vh-200px)] bg-white shadow">
              <ChatContainer />
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}