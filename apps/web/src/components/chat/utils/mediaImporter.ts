import { GeneratedFile } from '../types';
import { MediaItem, MediaType } from '@/stores/media-store';
import { generateUUID } from '@/lib/utils';

/**
 * media importer
 * used to import generated files into media library
 */
export class MediaImporter {
  /**
   * from file path create File object
   */
  private async createFileFromPath(filePath: string, fileName: string): Promise<File> {
    try {
      const response = await fetch(`/api/files/read?path=${encodeURIComponent(filePath)}`);
      
      if (!response.ok) {
        throw new Error(`Failed to read file: ${response.statusText}`);
      }
      
      const blob = await response.blob();
      const mimeType = this.getMimeType(fileName);
      
      return new File([blob], fileName, { type: mimeType });
    } catch (error) {
      console.error('Error creating file from path:', error);
      throw error;
    }
  }

  /**
   * get mime type from file extension
   */
  private getMimeType(fileName: string): string {
    const ext = fileName.toLowerCase().split('.').pop() || '';
    
    const mimeTypes: Record<string, string> = {
      'mp4': 'video/mp4',
      'avi': 'video/x-msvideo',
      'mov': 'video/quicktime',
      'mkv': 'video/x-matroska',
      'webm': 'video/webm',
      
      'jpg': 'image/jpeg',
      'jpeg': 'image/jpeg',
      'png': 'image/png',
      'gif': 'image/gif',
      'bmp': 'image/bmp',
      'webp': 'image/webp',
      
      'wav': 'audio/wav',
      'mp3': 'audio/mpeg',
      'aac': 'audio/aac',
      'ogg': 'audio/ogg',
      'flac': 'audio/flac',
    };
    
    return mimeTypes[ext] || 'application/octet-stream';
  }

  /**
   * transform GeneratedFile to MediaItem
   */
  private async convertToMediaItem(generatedFile: GeneratedFile): Promise<Omit<MediaItem, 'id'>> {
    const actualFileName = generatedFile.path.split('/').pop() || generatedFile.path;
    const file = await this.createFileFromPath(generatedFile.path, actualFileName);
    
    const mediaItem: Omit<MediaItem, 'id'> = {
      name: generatedFile.name,
      type: generatedFile.type as MediaType,
      file: file,
      url: URL.createObjectURL(file),
    };

    if (generatedFile.type === 'video') {
      try {
        const { duration, width, height, thumbnailUrl } = await this.getVideoMetadata(file);
        mediaItem.duration = duration;
        mediaItem.width = width;
        mediaItem.height = height;
        mediaItem.thumbnailUrl = thumbnailUrl;
      } catch (error) {
        console.warn('Failed to get video metadata:', error);
      }
    } else if (generatedFile.type === 'image') {
      try {
        const { width, height } = await this.getImageDimensions(file);
        mediaItem.width = width;
        mediaItem.height = height;
      } catch (error) {
        console.warn('Failed to get image dimensions:', error);
      }
    } else if (generatedFile.type === 'audio') {
      try {
        const duration = await this.getAudioDuration(file);
        mediaItem.duration = duration;
      } catch (error) {
        console.warn('Failed to get audio duration:', error);
      }
    }

    return mediaItem;
  }

  /**
   * get video metadata like duration, dimensions, thumbnail
   */
  private getVideoMetadata(file: File): Promise<{
    duration: number;
    width: number;
    height: number;
    thumbnailUrl: string;
  }> {
    return new Promise((resolve, reject) => {
      const video = document.createElement('video');
      const canvas = document.createElement('canvas');
      const ctx = canvas.getContext('2d');

      if (!ctx) {
        reject(new Error('Could not get canvas context'));
        return;
      }

      video.addEventListener('loadedmetadata', () => {
        canvas.width = video.videoWidth;
        canvas.height = video.videoHeight;
        video.currentTime = Math.min(1, video.duration * 0.1);
      });

      video.addEventListener('seeked', () => {
        ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
        const thumbnailUrl = canvas.toDataURL('image/jpeg', 0.8);
        
        resolve({
          duration: video.duration,
          width: video.videoWidth,
          height: video.videoHeight,
          thumbnailUrl,
        });

        video.remove();
        canvas.remove();
      });

      video.addEventListener('error', () => {
        reject(new Error('Could not load video'));
        video.remove();
        canvas.remove();
      });

      video.src = URL.createObjectURL(file);
      video.load();
    });
  }


  private getImageDimensions(file: File): Promise<{ width: number; height: number }> {
    return new Promise((resolve, reject) => {
      const img = new Image();

      img.addEventListener('load', () => {
        resolve({
          width: img.naturalWidth,
          height: img.naturalHeight,
        });
        img.remove();
      });

      img.addEventListener('error', () => {
        reject(new Error('Could not load image'));
        img.remove();
      });

      img.src = URL.createObjectURL(file);
    });
  }


  private getAudioDuration(file: File): Promise<number> {
    return new Promise((resolve, reject) => {
      const audio = document.createElement('audio');

      audio.addEventListener('loadedmetadata', () => {
        resolve(audio.duration);
        audio.remove();
      });

      audio.addEventListener('error', () => {
        reject(new Error('Could not load audio'));
        audio.remove();
      });

      audio.src = URL.createObjectURL(file);
      audio.load();
    });
  }


  async importFiles(
    generatedFiles: GeneratedFile[],
    addMediaItem: (projectId: string, item: Omit<MediaItem, 'id'>) => Promise<void>,
    projectId: string
  ): Promise<{ success: MediaItem[]; failed: { file: GeneratedFile; error: string }[] }> {
    const success: MediaItem[] = [];
    const failed: { file: GeneratedFile; error: string }[] = [];

    for (const generatedFile of generatedFiles) {
      try {
        const mediaItem = await this.convertToMediaItem(generatedFile);
        await addMediaItem(projectId, mediaItem);
        
        success.push({
          ...mediaItem,
          id: generateUUID(),
        });
      } catch (error) {
        failed.push({
          file: generatedFile,
          error: error instanceof Error ? error.message : 'Unknown error',
        });
      }
    }

    return { success, failed };
  }


  async validateFile(generatedFile: GeneratedFile): Promise<{ valid: boolean; error?: string }> {
    try {
      if (!generatedFile.path || generatedFile.path.length < 3) {
        return { valid: false, error: 'Invalid file path' };
      }

      const supportedTypes = ['video', 'image', 'audio'];
      if (!supportedTypes.includes(generatedFile.type)) {
        return { valid: false, error: 'Unsupported file type' };
      }

      const response = await fetch(`/api/files/validate?path=${encodeURIComponent(generatedFile.path)}`);
      if (!response.ok) {
        return { valid: false, error: 'File not accessible' };
      }

      return { valid: true };
    } catch (error) {
      return {
        valid: false,
        error: error instanceof Error ? error.message : 'Validation failed',
      };
    }
  }
}

export const mediaImporter = new MediaImporter();