"use client";

import React, { useState, useEffect } from 'react';
import { X, Key, Check, AlertCircle } from 'lucide-react';

interface AccessCodeSettingsProps {
  accessCode: string;
  onAccessCodeChange: (code: string) => void;
  onClose?: () => void;
  isOpen?: boolean;
}

export const AccessCodeSettings: React.FC<AccessCodeSettingsProps> = ({
  accessCode,
  onAccessCodeChange,
  onClose,
  isOpen = true,
}) => {
  const [inputValue, setInputValue] = useState(accessCode);
  const [showSuccess, setShowSuccess] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setInputValue(accessCode);
  }, [accessCode]);

  const handleSave = () => {
    const trimmedCode = inputValue.trim();
    
    if (!trimmedCode) {
      setError('Access code cannot be empty');
      return;
    }

    // Validate UUID format (optional)
    const uuidRegex = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
    if (!uuidRegex.test(trimmedCode)) {
      setError('Invalid access code format, should be UUID format');
      return;
    }

    onAccessCodeChange(trimmedCode);
    setError(null);
    setShowSuccess(true);
    
    setTimeout(() => {
      setShowSuccess(false);
      if (onClose) {
        onClose();
      }
    }, 1500);
  };

  const handleClear = () => {
    setInputValue('');
    onAccessCodeChange('');
    setError(null);
  };

  if (!isOpen) {
    return null;
  }

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-gray-800 rounded-lg shadow-xl max-w-md w-full mx-4">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-gray-700">
          <div className="flex items-center gap-2">
            <Key className="w-5 h-5 text-blue-400" />
            <h2 className="text-lg font-semibold text-white">Access Code Settings</h2>
          </div>
          {onClose && (
            <button
              onClick={onClose}
              className="text-gray-400 hover:text-white transition-colors"
            >
              <X className="w-5 h-5" />
            </button>
          )}
        </div>

        {/* Content */}
        <div className="p-4 space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-2">
              Access Code
            </label>
            <input
              type="text"
              value={inputValue}
              onChange={(e) => {
                setInputValue(e.target.value);
                setError(null);
              }}
              placeholder="Please enter access code (UUID format)"
              className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-lg text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            />
            <p className="mt-2 text-xs text-gray-400">
              Format example: 550e8400-e29b-41d4-a716-446655440000
            </p>
          </div>

          {/* Error message */}
          {error && (
            <div className="flex items-start gap-2 p-3 bg-red-900 bg-opacity-50 border border-red-700 rounded-lg">
              <AlertCircle className="w-5 h-5 text-red-400 flex-shrink-0 mt-0.5" />
              <p className="text-sm text-red-200">{error}</p>
            </div>
          )}

          {/* Success message */}
          {showSuccess && (
            <div className="flex items-center gap-2 p-3 bg-green-900 bg-opacity-50 border border-green-700 rounded-lg">
              <Check className="w-5 h-5 text-green-400" />
              <p className="text-sm text-green-200">Access code saved</p>
            </div>
          )}

          {/* Info */}
          <div className="p-3 bg-blue-900 bg-opacity-30 border border-blue-700 rounded-lg">
            <p className="text-sm text-blue-200">
              💡 Access code is used to verify your identity. Please keep it safe and do not share with others.
            </p>
          </div>
        </div>

        {/* Footer */}
        <div className="flex gap-2 p-4 border-t border-gray-700">
          <button
            onClick={handleClear}
            className="flex-1 px-4 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded-lg transition-colors"
          >
            Clear
          </button>
          <button
            onClick={handleSave}
            disabled={!inputValue.trim()}
            className="flex-1 px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-600 disabled:cursor-not-allowed text-white rounded-lg transition-colors font-medium"
          >
            Save
          </button>
        </div>
      </div>
    </div>
  );
};

// Simplified access code input component (for embedding in other interfaces)
export const AccessCodeInput: React.FC<{
  accessCode: string;
  onAccessCodeChange: (code: string) => void;
}> = ({ accessCode, onAccessCodeChange }) => {
  const [isExpanded, setIsExpanded] = useState(!accessCode);

  return (
    <div className="border border-gray-700 rounded-lg p-3 bg-gray-800">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <Key className="w-4 h-4 text-blue-400" />
          <span className="text-sm font-medium text-gray-300">Access Code</span>
        </div>
        <button
          onClick={() => setIsExpanded(!isExpanded)}
          className="text-xs text-blue-400 hover:text-blue-300"
        >
          {isExpanded ? 'Collapse' : 'Expand'}
        </button>
      </div>

      {isExpanded && (
        <div className="space-y-2">
          <input
            type="text"
            value={accessCode}
            onChange={(e) => onAccessCodeChange(e.target.value)}
            placeholder="Please enter access code"
            className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded text-white text-sm placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          {accessCode && (
            <div className="flex items-center gap-1 text-xs text-green-400">
              <Check className="w-3 h-3" />
              <span>Set</span>
            </div>
          )}
        </div>
      )}

      {!isExpanded && accessCode && (
        <div className="flex items-center gap-1 text-xs text-green-400">
          <Check className="w-3 h-3" />
          <span>Configured</span>
        </div>
      )}
    </div>
  );
};