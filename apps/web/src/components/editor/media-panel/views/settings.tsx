"use client";

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  PropertyItem,
  PropertyItemLabel,
  PropertyItemValue,
  PropertyGroup,
} from "../../properties-panel/property-item";
import { FPS_PRESETS } from "@/constants/timeline-constants";
import { useProjectStore } from "@/stores/project-store";
import { useEditorStore } from "@/stores/editor-store";
import { useAspectRatio } from "@/hooks/use-aspect-ratio";
import { useChat } from "@/components/chat/useChat";
import Image from "next/image";
import { cn } from "@/lib/utils";
import { colors } from "@/data/colors/solid";
import { patternCraftGradients } from "@/data/colors/pattern-craft";
import { PipetteIcon, Key, Check, AlertCircle } from "lucide-react";
import { useMemo, memo, useCallback, useState, useEffect } from "react";
import { syntaxUIGradients } from "@/data/colors/syntax-ui";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";

export function SettingsView() {
  return <ProjectSettingsTabs />;
}

function ProjectSettingsTabs() {
  return (
    <div className="h-full flex flex-col">
      <Tabs defaultValue="project-info" className="flex flex-col h-full">
        <div className="px-3 pt-4 pb-0">
          <TabsList>
            <TabsTrigger value="project-info">Project info</TabsTrigger>
            <TabsTrigger value="background">Background</TabsTrigger>
          </TabsList>
        </div>
        <Separator className="my-4" />
        <ScrollArea className="flex-1">
          <TabsContent value="project-info" className="p-5 pt-0 mt-0">
            <ProjectInfoView />
          </TabsContent>
          <TabsContent value="background" className="p-4 pt-0">
            <BackgroundView />
          </TabsContent>
        </ScrollArea>
      </Tabs>
    </div>
  );
}

function ProjectInfoView() {
  const { activeProject, updateProjectFps } = useProjectStore();
  const { canvasPresets, setCanvasSize } = useEditorStore();
  const { getDisplayName } = useAspectRatio();
  const { accessCode, handleAccessCodeChange, fetchAccessCodeStatus } = useChat();
  
  const [inputValue, setInputValue] = useState(accessCode);
  const [showSuccess, setShowSuccess] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [codeStatus, setCodeStatus] = useState<any>(null);
  const [isLoadingStatus, setIsLoadingStatus] = useState(false);

  // Sync inputValue after accessCode is restored from localStorage
  useEffect(() => {
    setInputValue(accessCode);
  }, [accessCode]);

  // Get access code status
  useEffect(() => {
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
  }, [accessCode]);

  const handleAspectRatioChange = (value: string) => {
    const preset = canvasPresets.find((p) => p.name === value);
    if (preset) {
      setCanvasSize({ width: preset.width, height: preset.height });
    }
  };

  const handleFpsChange = (value: string) => {
    const fps = parseFloat(value);
    updateProjectFps(fps);
  };

  const handleSaveAccessCode = () => {
    const trimmedCode = inputValue.trim();
    
    if (!trimmedCode) {
      setError('The access code cannot be empty.');
      return;
    }

    // Validate UUID format
    const uuidRegex = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
    if (!uuidRegex.test(trimmedCode)) {
      setError('The access code format is incorrect; it should be in UUID format.');
      return;
    }

    handleAccessCodeChange(trimmedCode);
    setError(null);
    setShowSuccess(true);
    
    setTimeout(() => {
      setShowSuccess(false);
    }, 2000);
  };

  const handleClearAccessCode = () => {
    setInputValue('');
    handleAccessCodeChange('');
    setError(null);
  };

  return (
    <div className="flex flex-col gap-4">
      <PropertyItem direction="column">
        <PropertyItemLabel>Name</PropertyItemLabel>
        <PropertyItemValue>
          {activeProject?.name || "Untitled project"}
        </PropertyItemValue>
      </PropertyItem>

      <PropertyItem direction="column">
        <PropertyItemLabel>Aspect ratio</PropertyItemLabel>
        <PropertyItemValue>
          <Select
            value={getDisplayName()}
            onValueChange={handleAspectRatioChange}
          >
            <SelectTrigger className="bg-panel-accent">
              <SelectValue placeholder="Select an aspect ratio" />
            </SelectTrigger>
            <SelectContent>
              {canvasPresets.map((preset) => (
                <SelectItem key={preset.name} value={preset.name}>
                  {preset.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </PropertyItemValue>
      </PropertyItem>

      <PropertyItem direction="column">
        <PropertyItemLabel>Frame rate</PropertyItemLabel>
        <PropertyItemValue>
          <Select
            value={(activeProject?.fps || 30).toString()}
            onValueChange={handleFpsChange}
          >
            <SelectTrigger className="bg-panel-accent">
              <SelectValue placeholder="Select a frame rate" />
            </SelectTrigger>
            <SelectContent>
              {FPS_PRESETS.map((preset) => (
                <SelectItem key={preset.value} value={preset.value}>
                  {preset.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </PropertyItemValue>
      </PropertyItem>

      <Separator className="my-2" />

      <PropertyGroup title="Access code" defaultExpanded={true}>
        <div className="flex flex-col gap-3">
          {/* Status */}
          <div className="flex items-center justify-between p-2 bg-muted rounded text-xs">
            <span className="text-muted-foreground">Status</span>
            {accessCode ? (
              <div className="flex items-center gap-1 text-green-600">
                <Check className="w-3 h-3" />
                <span>Configured</span>
              </div>
            ) : (
              <div className="flex items-center gap-1 text-yellow-600">
                <AlertCircle className="w-3 h-3" />
                <span>Not configured</span>
              </div>
            )}
          </div>

          {/* Access Code Status Details */}
          {accessCode && codeStatus && !isLoadingStatus && (
            <div className="flex flex-col gap-2 p-2 bg-blue-50 border border-blue-200 rounded text-xs">
              <div className="flex items-center justify-between">
                <span className="text-gray-700">Enabled</span>
                <span className={codeStatus.enabled ? "text-green-600 font-medium" : "text-red-600 font-medium"}>
                  {codeStatus.enabled ? "Yes" : "No"}
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-gray-700">Total Usage</span>
                <span className="font-medium text-gray-900">{codeStatus.usage_count}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-gray-700">Conversations Used</span>
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
                  <span className="text-gray-700">Limit</span>
                  <span className="font-medium text-green-600">Unlimited</span>
                </div>
              )}
              {codeStatus.last_used && (
                <div className="flex items-center justify-between">
                  <span className="text-gray-700">Last Used</span>
                  <span className="text-[10px] text-gray-900">
                    {new Date(codeStatus.last_used).toLocaleString()}
                  </span>
                </div>
              )}
            </div>
          )}

          {/* Loading Status */}
          {accessCode && isLoadingStatus && (
            <div className="flex items-center justify-center p-2 bg-muted rounded text-xs">
              <span className="text-muted-foreground">Loading status...</span>
            </div>
          )}

          {/* Input */}
          <div className="space-y-2">
            <Input
              type="text"
              value={inputValue}
              onChange={(e) => {
                setInputValue(e.target.value);
                setError(null);
              }}
              placeholder="Please input the access code (UUID format)"
              className="text-xs h-8"
            />
            <p className="text-[10px] text-muted-foreground">
              Format: 550e8400-e29b-41d4-a716-446655440000
            </p>
          </div>

          {/* Error Message */}
          {error && (
            <div className="flex items-start gap-2 p-2 bg-red-50 border border-red-200 rounded text-xs">
              <AlertCircle className="w-3 h-3 text-red-600 flex-shrink-0 mt-0.5" />
              <p className="text-red-600">{error}</p>
            </div>
          )}

          {/* Success Message */}
          {showSuccess && (
            <div className="flex items-center gap-2 p-2 bg-green-50 border border-green-200 rounded text-xs">
              <Check className="w-3 h-3 text-green-600" />
              <p className="text-green-600">Access code saved</p>
            </div>
          )}

          {/* Info */}
          <div className="p-2 bg-blue-50 border border-blue-200 rounded text-[10px] text-blue-700">
            💡 The access code is used to verify your identity. Please keep it safe.
          </div>

          {/* Actions */}
          <div className="flex gap-2">
            <Button
              onClick={handleClearAccessCode}
              variant="outline"
              className="flex-1 h-7 text-xs"
              size="sm"
            >
              clear
            </Button>
            <Button
              onClick={handleSaveAccessCode}
              disabled={!inputValue.trim()}
              className="flex-1 h-7 text-xs"
              size="sm"
            >
              save
            </Button>
          </div>
        </div>
      </PropertyGroup>
    </div>
  );
}

const BlurPreview = memo(
  ({
    blur,
    isSelected,
    onSelect,
  }: {
    blur: { label: string; value: number };
    isSelected: boolean;
    onSelect: () => void;
  }) => (
    <div
      className={cn(
        "w-full aspect-square rounded-sm cursor-pointer border border-foreground/15 hover:border-primary relative overflow-hidden",
        isSelected && "border-2 border-primary"
      )}
      onClick={onSelect}
    >
      <Image
        src="https://images.unsplash.com/photo-1501785888041-af3ef285b470?q=80&w=1470&auto=format&fit=crop&ixlib=rb-4.1.0&ixid=M3wxMjA3fDB8MHxwaG90by1wYWdlfHx8fGVufDB8fHx8fA%3D%3D"
        alt={`Blur preview ${blur.label}`}
        fill
        className="object-cover"
        style={{ filter: `blur(${blur.value}px)` }}
        loading="eager"
      />
      <div className="absolute bottom-1 left-1 right-1 text-center">
        <span className="text-xs text-white bg-black/50 px-1 rounded">
          {blur.label}
        </span>
      </div>
    </div>
  )
);

BlurPreview.displayName = "BlurPreview";

const BackgroundPreviews = memo(
  ({
    backgrounds,
    currentBackgroundColor,
    isColorBackground,
    handleColorSelect,
    useBackgroundColor = false,
  }: {
    backgrounds: string[];
    currentBackgroundColor: string;
    isColorBackground: boolean;
    handleColorSelect: (bg: string) => void;
    useBackgroundColor?: boolean;
  }) => {
    return useMemo(
      () =>
        backgrounds.map((bg) => (
          <div
            key={bg}
            className={cn(
              "w-full aspect-square rounded-sm cursor-pointer border border-foreground/15 hover:border-primary",
              isColorBackground &&
                bg === currentBackgroundColor &&
                "border-2 border-primary"
            )}
            style={
              useBackgroundColor
                ? { backgroundColor: bg }
                : {
                    background: bg,
                    backgroundSize: "cover",
                    backgroundPosition: "center",
                    backgroundRepeat: "no-repeat",
                  }
            }
            onClick={() => handleColorSelect(bg)}
          />
        )),
      [
        backgrounds,
        isColorBackground,
        currentBackgroundColor,
        handleColorSelect,
        useBackgroundColor,
      ]
    );
  }
);

BackgroundPreviews.displayName = "BackgroundPreviews";

function BackgroundView() {
  const { activeProject, updateBackgroundType } = useProjectStore();

  const blurLevels = useMemo(
    () => [
      { label: "Light", value: 4 },
      { label: "Medium", value: 8 },
      { label: "Heavy", value: 18 },
    ],
    []
  );

  const handleBlurSelect = useCallback(
    async (blurIntensity: number) => {
      await updateBackgroundType("blur", { blurIntensity });
    },
    [updateBackgroundType]
  );

  const handleColorSelect = useCallback(
    async (color: string) => {
      await updateBackgroundType("color", { backgroundColor: color });
    },
    [updateBackgroundType]
  );

  const currentBlurIntensity = activeProject?.blurIntensity || 8;
  const isBlurBackground = activeProject?.backgroundType === "blur";
  const currentBackgroundColor = activeProject?.backgroundColor || "#000000";
  const isColorBackground = activeProject?.backgroundType === "color";

  const blurPreviews = useMemo(
    () =>
      blurLevels.map((blur) => (
        <BlurPreview
          key={blur.value}
          blur={blur}
          isSelected={isBlurBackground && currentBlurIntensity === blur.value}
          onSelect={() => handleBlurSelect(blur.value)}
        />
      )),
    [blurLevels, isBlurBackground, currentBlurIntensity, handleBlurSelect]
  );

  return (
    <div className="flex flex-col gap-5">
      <PropertyGroup title="Blur" defaultExpanded={false}>
        <div className="grid grid-cols-4 gap-2 w-full">{blurPreviews}</div>
      </PropertyGroup>

      <PropertyGroup title="Colors" defaultExpanded={false}>
        <div className="grid grid-cols-4 gap-2 w-full">
          <div className="w-full aspect-square rounded-sm cursor-pointer border border-foreground/15 hover:border-primary flex items-center justify-center">
            <PipetteIcon className="size-4" />
          </div>
          <BackgroundPreviews
            backgrounds={colors}
            currentBackgroundColor={currentBackgroundColor}
            isColorBackground={isColorBackground}
            handleColorSelect={handleColorSelect}
            useBackgroundColor={true}
          />
        </div>
      </PropertyGroup>

      <PropertyGroup title="Pattern Craft" defaultExpanded={false}>
        <div className="grid grid-cols-4 gap-2 w-full">
          <BackgroundPreviews
            backgrounds={patternCraftGradients}
            currentBackgroundColor={currentBackgroundColor}
            isColorBackground={isColorBackground}
            handleColorSelect={handleColorSelect}
          />
        </div>
      </PropertyGroup>

      <PropertyGroup title="Syntax UI" defaultExpanded={false}>
        <div className="grid grid-cols-4 gap-2 w-full">
          <BackgroundPreviews
            backgrounds={syntaxUIGradients}
            currentBackgroundColor={currentBackgroundColor}
            isColorBackground={isColorBackground}
            handleColorSelect={handleColorSelect}
          />
        </div>
      </PropertyGroup>
    </div>
  );
}
