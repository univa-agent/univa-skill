"use client";

import React, { useState } from 'react';
import { Popover, PopoverContent, PopoverTrigger } from "./ui/popover";
import { Button } from "./ui/button";
import { Settings, Key, Check, AlertCircle } from 'lucide-react';
import { cn } from "@/lib/utils";
import { useChat } from './chat/useChat';

type SettingsTab = "access-code" | "general";

export function ChatSettings() {
  const { accessCode, handleAccessCodeChange, fetchAccessCodeStatus } = useChat();
  const [activeTab, setActiveTab] = useState<SettingsTab>("access-code");
  const [inputValue, setInputValue] = useState(accessCode);
  const [showSuccess, setShowSuccess] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [codeStatus, setCodeStatus] = useState<any>(null);
  const [isLoadingStatus, setIsLoadingStatus] = useState(false);

  // Get access code status
  React.useEffect(() => {
    const loadStatus = async () => {
      if (accessCode) {
        setIsLoadingStatus(true);
        try {
          const status = await fetchAccessCodeStatus();
          console.log('Access code status loaded:', status);
          setCodeStatus(status);
        } catch (error) {
          console.error('Failed to load access code status:', error);
          setCodeStatus(null);
        } finally {
          setIsLoadingStatus(false);
        }
      } else {
        setCodeStatus(null);
      }
    };
    
    loadStatus();
  }, [accessCode]); // Remove fetchAccessCodeStatus dependency to avoid infinite loop

  const handleSave = () => {
    const trimmedCode = inputValue.trim();
    
    if (!trimmedCode) {
      setError('Access code cannot be empty');
      return;
    }

    // Validate UUID format
    const uuidRegex = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
    if (!uuidRegex.test(trimmedCode)) {
      setError('Invalid access code format, should be UUID format');
      return;
    }

    handleAccessCodeChange(trimmedCode);
    setError(null);
    setShowSuccess(true);
    
    setTimeout(() => {
      setShowSuccess(false);
    }, 2000);
  };

  const handleClear = () => {
    setInputValue('');
    handleAccessCodeChange('');
    setError(null);
  };

  const tabs = [
    {
      label: "Access Code",
      value: "access-code" as SettingsTab,
      icon: Key,
    },
    // Can add more settings tabs
    // {
    //   label: "General",
    //   value: "general" as SettingsTab,
    //   icon: Settings,
    // },
  ];

  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button
          variant="text"
          size="icon"
          className="size-8"
          title="Settings"
        >
          <Settings className="size-4" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="flex flex-col items-start w-[24rem] overflow-hidden p-0">
        {/* Header */}
        <div className="flex items-center justify-between w-full gap-2 bg-popover p-4 border-b">
          <h2 className="text-sm font-semibold">Chat Settings</h2>
          <div className="flex items-center gap-2 text-xs">
            {tabs.map((tab) => {
              const Icon = tab.icon;
              return (
                <button
                  key={tab.value}
                  onClick={() => setActiveTab(tab.value)}
                  className={cn(
                    "flex items-center gap-1 px-2 py-1 rounded transition-colors",
                    activeTab === tab.value 
                      ? "bg-primary text-primary-foreground" 
                      : "text-muted-foreground hover:text-foreground hover:bg-muted"
                  )}
                >
                  <Icon className="size-3" />
                  <span>{tab.label}</span>
                </button>
              );
            })}
          </div>
        </div>

        {/* Content */}
        <div className="w-full p-4">
          {activeTab === "access-code" && (
            <AccessCodeView
              accessCode={accessCode}
              inputValue={inputValue}
              setInputValue={setInputValue}
              error={error}
              setError={setError}
              showSuccess={showSuccess}
              onSave={handleSave}
              onClear={handleClear}
              codeStatus={codeStatus}
              isLoadingStatus={isLoadingStatus}
            />
          )}
        </div>
      </PopoverContent>
    </Popover>
  );
}

function AccessCodeView({
  accessCode,
  inputValue,
  setInputValue,
  error,
  setError,
  showSuccess,
  onSave,
  onClear,
  codeStatus,
  isLoadingStatus,
}: {
  accessCode: string;
  inputValue: string;
  setInputValue: (value: string) => void;
  error: string | null;
  setError: (error: string | null) => void;
  showSuccess: boolean;
  onSave: () => void;
  onClear: () => void;
  codeStatus: any;
  isLoadingStatus: boolean;
}) {
  return (
    <div className="space-y-4">
      {/* Status */}
      <div className="flex items-center justify-between p-3 bg-muted rounded-lg">
        <span className="text-sm text-muted-foreground">Current Status</span>
        {accessCode ? (
          <div className="flex items-center gap-1 text-sm text-green-600">
            <Check className="w-4 h-4" />
            <span>Configured</span>
          </div>
        ) : (
          <div className="flex items-center gap-1 text-sm text-yellow-600">
            <AlertCircle className="w-4 h-4" />
            <span>Not Configured</span>
          </div>
        )}
      </div>

      {/* Input */}
      <div>
        <label className="block text-sm font-medium mb-2">
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
          className="w-full px-3 py-2 border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary"
        />
        <p className="mt-1 text-xs text-muted-foreground">
          Format example: 550e8400-e29b-41d4-a716-446655440000
        </p>
      </div>

      {/* Error Message */}
      {error && (
        <div className="flex items-start gap-2 p-3 bg-red-50 border border-red-200 rounded-lg">
          <AlertCircle className="w-4 h-4 text-red-600 flex-shrink-0 mt-0.5" />
          <p className="text-sm text-red-600">{error}</p>
        </div>
      )}

      {/* Success Message */}
      {showSuccess && (
        <div className="flex items-center gap-2 p-3 bg-green-50 border border-green-200 rounded-lg">
          <Check className="w-4 h-4 text-green-600" />
          <p className="text-sm text-green-600">Access code saved</p>
        </div>
      )}

      {/* Access Code Status Details */}
      {accessCode && codeStatus && !isLoadingStatus && (
        <div className="flex flex-col gap-2 p-3 bg-blue-50 border border-blue-200 rounded-lg text-sm">
          <div className="font-medium text-blue-900 mb-1">Access Code Status</div>
          <div className="flex items-center justify-between">
            <span className="text-gray-700">Enabled Status</span>
            <span className={codeStatus.enabled ? "text-green-600 font-medium" : "text-red-600 font-medium"}>
              {codeStatus.enabled ? "Enabled" : "Disabled"}
            </span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-gray-700">Total Usage</span>
            <span className="font-medium text-gray-900">{codeStatus.usage_count}</span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-gray-700">Used Conversations</span>
            <span className="font-medium text-gray-900">{codeStatus.conversation_count}</span>
          </div>
          {codeStatus.max_conversations !== null && (
            <>
              <div className="flex items-center justify-between">
                <span className="text-gray-700">Max Conversations</span>
                <span className="font-medium text-gray-900">{codeStatus.max_conversations}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-gray-700">Remaining</span>
                <span className={cn(
                  "font-medium",
                  codeStatus.remaining_conversations === 0 ? "text-red-600" :
                  codeStatus.remaining_conversations && codeStatus.remaining_conversations < 5 ? "text-yellow-600" :
                  "text-green-600"
                )}>
                  {codeStatus.remaining_conversations}
                </span>
              </div>
            </>
          )}
          {codeStatus.max_conversations === null && (
            <div className="flex items-center justify-between">
              <span className="text-gray-700">Usage Limit</span>
              <span className="font-medium text-green-600">Unlimited</span>
            </div>
          )}
          {codeStatus.last_used && (
            <div className="flex items-center justify-between">
              <span className="text-gray-700">Last Used</span>
              <span className="text-xs text-gray-900">
                {new Date(codeStatus.last_used).toLocaleString('zh-CN')}
              </span>
            </div>
          )}
        </div>
      )}

      {/* Loading Status */}
      {accessCode && isLoadingStatus && (
        <div className="flex items-center justify-center p-3 bg-muted rounded-lg text-sm">
          <span className="text-muted-foreground">Loading status...</span>
        </div>
      )}

      {/* Info */}
      <div className="p-3 bg-blue-50 border border-blue-200 rounded-lg">
        <p className="text-sm text-blue-700">
          💡 Access code is used to verify your identity. Please keep it safe and do not share with others.
        </p>
      </div>

      {/* Actions */}
      <div className="flex gap-2">
        <Button
          onClick={onClear}
          variant="outline"
          className="flex-1"
          size="sm"
        >
          Clear
        </Button>
        <Button
          onClick={onSave}
          disabled={!inputValue.trim()}
          className="flex-1"
          size="sm"
        >
          Save
        </Button>
      </div>
    </div>
  );
}