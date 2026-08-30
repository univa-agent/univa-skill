"use client";

import React, { useState } from 'react';
import { Button } from '@/components/ui/button';
import { GeneratedFile } from './types';
import { mediaImporter } from './utils/mediaImporter';
import { useMediaStore } from '@/stores/media-store';
import { useProjectStore } from '@/stores/project-store';
import { Download, Loader2, CheckCircle, AlertCircle } from 'lucide-react';
import { toast } from 'sonner';

interface FileImportButtonProps {
  generatedFiles: GeneratedFile[];
  className?: string;
}

export const FileImportButton: React.FC<FileImportButtonProps> = ({
  generatedFiles,
  className = '',
}) => {
  const [isImporting, setIsImporting] = useState(false);
  const [importStatus, setImportStatus] = useState<'idle' | 'success' | 'error'>('idle');
  
  const { addMediaItem } = useMediaStore();
  const { activeProject } = useProjectStore();

  const handleImport = async () => {
    if (!activeProject) {
      toast.error('Please create or open a project first');
      return;
    }

    if (generatedFiles.length === 0) {
      toast.error('There are no files to import');
      return;
    }

    setIsImporting(true);
    setImportStatus('idle');

    try {
      const validationResults = await Promise.all(
        generatedFiles.map(file => mediaImporter.validateFile(file))
      );

      const invalidFiles = validationResults
        .map((result, index) => ({ result, file: generatedFiles[index] }))
        .filter(({ result }) => !result.valid);

      if (invalidFiles.length > 0) {
        const errorMessages = invalidFiles.map(
          ({ file, result }) => `${file.name}: ${result.error}`
        );
        toast.error(`File validation failed:\n${errorMessages.join('\n')}`);
        setImportStatus('error');
        return;
      }

      const validFiles = generatedFiles.filter((_, index) => 
        validationResults[index].valid
      );

      const importResult = await mediaImporter.importFiles(
        validFiles,
        addMediaItem,
        activeProject.id
      );

      if (importResult.success.length > 0) {
        toast.success(
          `Successfully imported ${importResult.success.length} files to media library`
        );
        setImportStatus('success');
      }

      if (importResult.failed.length > 0) {
        const failedMessages = importResult.failed.map(
          ({ file, error }) => `${file.name}: ${error}`
        );
        toast.error(`Partially failed to import files:\n${failedMessages.join('\n')}`);
        
        if (importResult.success.length === 0) {
          setImportStatus('error');
        }
      }

    } catch (error) {
      console.error('Import error:', error);
      toast.error('An error occurred during the import process');
      setImportStatus('error');
    } finally {
      setIsImporting(false);
      
      setTimeout(() => {
        setImportStatus('idle');
      }, 3000);
    }
  };

  const getButtonContent = () => {
    if (isImporting) {
      return (
        <>
          <Loader2 className="w-4 h-4 mr-2 animate-spin" />
          Importing...
        </>
      );
    }

    switch (importStatus) {
      case 'success':
        return (
          <>
            <CheckCircle className="w-4 h-4 mr-2 text-green-500" />
            Import successful
          </>
        );
      case 'error':
        return (
          <>
            <AlertCircle className="w-4 h-4 mr-2 text-red-500" />
            Import failed
          </>
        );
      default:
        return (
          <>
            <Download className="w-4 h-4 mr-2" />
            Import to media library ({generatedFiles.length})
          </>
        );
    }
  };

  const getButtonVariant = () => {
    switch (importStatus) {
      case 'success':
        return 'outline' as const;
      case 'error':
        return 'destructive' as const;
      default:
        return 'default' as const;
    }
  };

  return (
    <Button
      onClick={handleImport}
      disabled={isImporting || generatedFiles.length === 0 || !activeProject}
      variant={getButtonVariant()}
      size="sm"
      className={className}
    >
      {getButtonContent()}
    </Button>
  );
};