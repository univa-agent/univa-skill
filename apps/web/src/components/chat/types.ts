export interface GeneratedFile {
  path: string;
  type: 'video' | 'image' | 'audio';
  name: string;
}

// Task step type
export interface TodoItem {
  id: number;
  description: string;
  status: 'pending' | 'in_progress' | 'completed';
  tool?: any;
  output?: string;
}

export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: string; // Use string instead of Date object
  isStreaming?: boolean;
  generatedFiles?: GeneratedFile[]; // AI generated file information
  // Task execution flow related fields
  messageType?: 'user' | 'assistant' | 'tool_start' | 'tool_end' | 'todo_progress' | 'completion' | 'pipeline_suspended' | 'pipeline_stage' | 'pipeline_complete' | 'budget_update';
  todoItems?: TodoItem[];
  overallDescription?: string;
  // Pipeline interaction fields
  pipelineStage?: string;
  continuationToken?: string;
  interactionType?: 'user_choice' | 'user_approval';
  interactionData?: Record<string, unknown>;
  // Budget fields
  budgetSummary?: Record<string, unknown>;
  // Pipeline delivery
  deliveryReport?: Record<string, unknown>;
}

// Media reference interface
export interface MediaReference {
  id: string;
  name: string;
  type: 'video' | 'image' | 'audio';
  url?: string;
  thumbnailUrl?: string;
}

// Media selector state
export interface MediaSelectorState {
  isOpen: boolean;
  position: { x: number; y: number };
  searchQuery: string;
  selectedIndex: number;
}

export interface ChatState {
  messages: Message[];
  inputText: string;
  isLoading: boolean;
  sessionId: string | null;
  error: string | null;
  mediaSelector: MediaSelectorState;
  referencedMedia: MediaReference[];
  connectionStatus?: 'connected' | 'connecting' | 'reconnecting' | 'disconnected';
  retryCount?: number;
  maxRetries?: number;
  accessCode?: string; // Access code
}