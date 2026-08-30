import React from 'react';
import { ChatState } from './types';

interface ConnectionStatusProps {
  connectionStatus: ChatState['connectionStatus'];
  retryCount?: number;
  maxRetries?: number;
  isLoading: boolean;
}

export const ConnectionStatus: React.FC<ConnectionStatusProps> = ({
  connectionStatus,
  retryCount = 0,
  maxRetries = 3,
  isLoading,
}) => {
  if (!isLoading && connectionStatus === 'disconnected') {
    return null;
  }

  const getStatusColor = () => {
    switch (connectionStatus) {
      case 'connected':
        return 'text-green-500';
      case 'connecting':
        return 'text-blue-500';
      case 'reconnecting':
        return 'text-yellow-500';
      case 'disconnected':
        return 'text-red-500';
      default:
        return 'text-gray-500';
    }
  };

  const getStatusText = () => {
    switch (connectionStatus) {
      case 'connected':
        return 'Connected';
      case 'connecting':
        return 'Connecting...';
      case 'reconnecting':
        return `Reconnecting... (${retryCount}/${maxRetries})`;
      case 'disconnected':
        return 'Disconnected';
      default:
        return 'Unknown status';
    }
  };

  const getStatusIcon = () => {
    switch (connectionStatus) {
      case 'connected':
        return (
          <div className="w-2 h-2 bg-green-500 rounded-full animate-pulse" />
        );
      case 'connecting':
      case 'reconnecting':
        return (
          <div className="w-2 h-2 bg-blue-500 rounded-full animate-spin border border-blue-300 border-t-transparent" />
        );
      case 'disconnected':
        return (
          <div className="w-2 h-2 bg-red-500 rounded-full" />
        );
      default:
        return (
          <div className="w-2 h-2 bg-gray-500 rounded-full" />
        );
    }
  };

  return (
    <div className="flex items-center gap-2 text-sm px-3 py-1 bg-gray-50 dark:bg-gray-800 rounded-full border">
      {getStatusIcon()}
      <span className={`${getStatusColor()} font-medium`}>
        {getStatusText()}
      </span>
    </div>
  );
};