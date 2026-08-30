"use client";

import React, { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Message } from './types';
import { Check, Edit3, RotateCcw, ThumbsUp } from 'lucide-react';

interface PipelineInteractionCardProps {
  message: Message;
  onResume: (userInput: string) => Promise<void>;
  isLoading?: boolean;
}

/**
 * Renders interactive cards for pipeline_suspended messages.
 *
 * Supports two interaction types:
 * - user_choice (selection): Present edit proposal, user confirms or modifies
 * - user_approval (confirm): User reviews storyboard/edit result, continues or finalizes
 */
export const PipelineInteractionCard: React.FC<PipelineInteractionCardProps> = ({
  message,
  onResume,
  isLoading = false,
}) => {
  const [customInput, setCustomInput] = useState('');
  const [showCustomInput, setShowCustomInput] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleAction = async (input: string) => {
    setIsSubmitting(true);
    try {
      await onResume(input);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleCustomSubmit = async () => {
    if (customInput.trim()) {
      await handleAction(customInput.trim());
      setCustomInput('');
      setShowCustomInput(false);
    }
  };

  // ── Selection gate (edit proposal / creative choice) ────────────────

  if (message.interactionType === 'user_choice') {
    const data = (message.interactionData || {}) as Record<string, unknown>;
    const proposals = typeof data.proposals === 'string' ? data.proposals : null;
    const editProposal = typeof data.edit_proposal === 'string' ? data.edit_proposal : null;

    return (
      <div className="mt-3 p-4 bg-white border border-blue-200 rounded-lg shadow-sm">
        <div className="flex items-center gap-2 mb-3">
          <div className="w-6 h-6 bg-blue-100 rounded-full flex items-center justify-center">
            <Edit3 className="h-3.5 w-3.5 text-blue-600" />
          </div>
          <span className="font-semibold text-sm text-blue-800">Edit proposal</span>
        </div>

        {editProposal && (
          <div className="text-sm text-gray-700 mb-3 whitespace-pre-wrap bg-gray-50 p-3 rounded border border-gray-100">
            {editProposal}
          </div>
        )}

        {proposals && (
          <div className="text-sm text-gray-700 mb-3 whitespace-pre-wrap bg-gray-50 p-3 rounded border border-gray-100">
            {proposals.substring(0, 2000)}
          </div>
        )}

        <div className="flex flex-wrap gap-2">
          <Button
            size="sm"
            onClick={() => handleAction('Confirm')}
            disabled={isLoading || isSubmitting}
            className="bg-blue-600 hover:bg-blue-700"
          >
            <Check className="h-3.5 w-3.5 mr-1" />
            Confirm execution
          </Button>
          <Button
            size="sm"
            variant="outline"
            onClick={() => setShowCustomInput(!showCustomInput)}
            disabled={isLoading || isSubmitting}
          >
            <Edit3 className="h-3.5 w-3.5 mr-1" />
            Revise proposal
          </Button>
        </div>

        {showCustomInput && (
          <div className="mt-3 flex gap-2">
            <input
              type="text"
              value={customInput}
              onChange={(e) => setCustomInput(e.target.value)}
              placeholder="Describe what you want to change..."
              className="flex-1 px-3 py-1.5 text-sm border border-gray-300 rounded focus:outline-none focus:ring-1 focus:ring-blue-500"
              onKeyDown={(e) => {
                if (e.key === 'Enter') handleCustomSubmit();
                if (e.key === 'Escape') setShowCustomInput(false);
              }}
              disabled={isSubmitting}
              autoFocus
            />
            <Button
              size="sm"
              onClick={handleCustomSubmit}
              disabled={!customInput.trim() || isSubmitting}
            >
              Send
            </Button>
          </div>
        )}
      </div>
    );
  }

  // ── Approval gate (storyboard confirm / edit review) ────────────────

  if (message.interactionType === 'user_approval') {
    const data = (message.interactionData || {}) as Record<string, unknown>;
    const storyboard = typeof data.storyboard === 'string' ? data.storyboard : null;

    return (
      <div className="mt-3 p-4 bg-white border border-green-200 rounded-lg shadow-sm">
        <div className="flex items-center gap-2 mb-3">
          <div className="w-6 h-6 bg-green-100 rounded-full flex items-center justify-center">
            <ThumbsUp className="h-3.5 w-3.5 text-green-600" />
          </div>
          <span className="font-semibold text-sm text-green-800">Please confirm</span>
        </div>

        <p className="text-sm text-gray-700 mb-3">{message.content}</p>

        {storyboard && (
          <div className="text-xs text-gray-600 mb-3 whitespace-pre-wrap bg-gray-50 p-2 rounded border border-gray-100 max-h-48 overflow-y-auto">
            {storyboard.substring(0, 2000)}
          </div>
        )}

        <div className="flex flex-wrap gap-2">
          <Button
            size="sm"
            onClick={() => handleAction('Confirm')}
            disabled={isLoading || isSubmitting}
            className="bg-green-600 hover:bg-green-700"
          >
            <Check className="h-3.5 w-3.5 mr-1" />
            Confirm
          </Button>
          <Button
            size="sm"
            variant="outline"
            onClick={() => handleAction('Keep revising')}
            disabled={isLoading || isSubmitting}
          >
            <RotateCcw className="h-3.5 w-3.5 mr-1" />
            Keep revising
          </Button>
          <Button
            size="sm"
            variant="link"
            onClick={() => setShowCustomInput(!showCustomInput)}
            disabled={isLoading || isSubmitting}
          >
            Custom reply
          </Button>
        </div>

        {showCustomInput && (
          <div className="mt-3 flex gap-2">
            <input
              type="text"
              value={customInput}
              onChange={(e) => setCustomInput(e.target.value)}
              placeholder="Describe what needs adjustment..."
              className="flex-1 px-3 py-1.5 text-sm border border-gray-300 rounded focus:outline-none focus:ring-1 focus:ring-green-500"
              onKeyDown={(e) => {
                if (e.key === 'Enter') handleCustomSubmit();
                if (e.key === 'Escape') setShowCustomInput(false);
              }}
              disabled={isSubmitting}
              autoFocus
            />
            <Button
              size="sm"
              onClick={handleCustomSubmit}
              disabled={!customInput.trim() || isSubmitting}
            >
              Send
            </Button>
          </div>
        )}
      </div>
    );
  }

  // ── Generic suspended (fallback) ─────────────────────────────────────

  return (
    <div className="mt-3 p-3 bg-white border border-gray-200 rounded-lg">
      <p className="text-sm text-gray-700 mb-2">{message.content}</p>
      <div className="flex gap-2">
        <Button
          size="sm"
          onClick={() => handleAction('Confirm')}
          disabled={isLoading || isSubmitting}
        >
          <Check className="h-3.5 w-3.5 mr-1" />
          Confirm
        </Button>
        <Button
          size="sm"
          variant="outline"
          onClick={() => setShowCustomInput(!showCustomInput)}
          disabled={isLoading || isSubmitting}
        >
          Custom reply
        </Button>
      </div>
      {showCustomInput && (
        <div className="mt-3 flex gap-2">
          <input
            type="text"
            value={customInput}
            onChange={(e) => setCustomInput(e.target.value)}
            placeholder="Enter a reply..."
            className="flex-1 px-3 py-1.5 text-sm border border-gray-300 rounded"
            onKeyDown={(e) => { if (e.key === 'Enter') handleCustomSubmit(); }}
            autoFocus
          />
          <Button size="sm" onClick={handleCustomSubmit} disabled={!customInput.trim()}>Send</Button>
        </div>
      )}
    </div>
  );
};
