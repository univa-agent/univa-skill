import { MediaReference } from '../types';

/**
 * Media cache service
 * Responsible for downloading referenced media files and preparing them for backend processing
 */
export class MediaCacheService {
  private cachedFiles: Map<string, { file: File; localPath: string }> = new Map(); // mediaId -> {file, localPath}
  private cacheDir: string;

  constructor(cacheDir: string = '/tmp/media-cache') {
    this.cacheDir = cacheDir;
  }

  /**
   * Get file extension
   */
  private getFileExtension(fileName: string): string {
    const lastDot = fileName.lastIndexOf('.');
    return lastDot !== -1 ? fileName.substring(lastDot) : '.bin';
  }

  /**
   * Generate cache file path
   */
  private getCacheFilePath(mediaId: string, fileName: string): string {
    const ext = this.getFileExtension(fileName);
    const cacheFileName = `${mediaId}${ext}`;
    return `${this.cacheDir}/${cacheFileName}`;
  }

  /**
   * Download media file to cache
   */
  async cacheMediaFile(media: MediaReference): Promise<string> {
    // If already cached, return path directly
    if (this.cachedFiles.has(media.id)) {
      const cached = this.cachedFiles.get(media.id)!;
      return cached.localPath;
    }

    const cacheFilePath = this.getCacheFilePath(media.id, media.name);

    try {
      // If media has URL, download from URL
      if (media.url) {
        const file = await this.downloadFromUrl(media.url, media.name);
        
        // Upload file to server cache
        const serverPath = await this.uploadToServerCache(file, media.id, media.name);
        
        // Record cached file information
        this.cachedFiles.set(media.id, { file, localPath: serverPath });
        return serverPath;
      } else {
        throw new Error(`Media ${media.name} has no URL to download from`);
      }
    } catch (error) {
      console.error(`Failed to cache media file ${media.name}:`, error);
      throw error;
    }
  }

  /**
   * Download file from URL
   */
  private async downloadFromUrl(url: string, fileName: string): Promise<File> {
    try {
      const response = await fetch(url);
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const blob = await response.blob();
      return new File([blob], fileName, { type: blob.type });
    } catch (error) {
      console.error(`Failed to download from URL ${url}:`, error);
      throw error;
    }
  }

  /**
   * Upload file to server cache
   */
  private async uploadToServerCache(file: File, mediaId: string, fileName: string): Promise<string> {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('mediaId', mediaId);
    formData.append('fileName', fileName);

    try {
      const response = await fetch('/api/media/cache', {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) {
        throw new Error(`Upload failed: ${response.status}`);
      }

      const result = await response.json();
      return result.localPath;
    } catch (error) {
      console.error('Failed to upload file to server cache:', error);
      throw error;
    }
  }

  /**
   * Batch cache media files
   */
  async cacheMediaFiles(mediaList: MediaReference[]): Promise<Map<string, string>> {
    const results = new Map<string, string>();
    
    for (const media of mediaList) {
      try {
        const localPath = await this.cacheMediaFile(media);
        results.set(media.id, localPath);
      } catch (error) {
        console.error(`Failed to cache media ${media.name}:`, error);
        // Continue processing other files without interrupting the entire process
      }
    }

    return results;
  }

  /**
   * Get local path of cached file
   */
  getCachedFilePath(mediaId: string): string | null {
    const cached = this.cachedFiles.get(mediaId);
    return cached ? cached.localPath : null;
  }

  /**
   * Clear cache files
   */
  async clearCache(): Promise<void> {
    try {
      // Call server API to clear cache
      await fetch('/api/media/cache', {
        method: 'DELETE',
      });
      this.cachedFiles.clear();
    } catch (error) {
      console.error('Failed to clear cache:', error);
    }
  }

  /**
   * Clear cache for specific media
   */
  async clearMediaCache(mediaId: string): Promise<void> {
    const cached = this.cachedFiles.get(mediaId);
    if (cached) {
      try {
        await fetch(`/api/media/cache/${mediaId}`, {
          method: 'DELETE',
        });
        this.cachedFiles.delete(mediaId);
      } catch (error) {
        console.error(`Failed to clear cache for media ${mediaId}:`, error);
      }
    }
  }

  /**
   * Get cache statistics
   */
  async getCacheStats(): Promise<{ totalFiles: number; totalSize: number; cacheDir: string }> {
    try {
      const response = await fetch('/api/media/cache/stats');
      if (response.ok) {
        return await response.json();
      }
    } catch (error) {
      console.error('Failed to get cache stats:', error);
    }

    return {
      totalFiles: this.cachedFiles.size,
      totalSize: 0,
      cacheDir: this.cacheDir,
    };
  }
}

// Create global cache service instance
export const mediaCacheService = new MediaCacheService();