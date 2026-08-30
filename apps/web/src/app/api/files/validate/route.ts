import { NextRequest, NextResponse } from 'next/server';
import { existsSync, statSync } from 'fs';
import path from 'path';
import { getFileSearchPaths } from '@/lib/config';


const SEARCH_PATHS = getFileSearchPaths();

function findFile(fileName: string): string | null {
  if (path.isAbsolute(fileName) && existsSync(fileName)) {
    return fileName;
  }

  for (const searchPath of SEARCH_PATHS) {
    const fullPath = path.join(searchPath, fileName);
    if (existsSync(fullPath)) {
      return fullPath;
    }
  }

  return null;
}

export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);
    const filePath = searchParams.get('path');

    if (!filePath) {
      return NextResponse.json(
        { error: 'File path is required' },
        { status: 400 }
      );
    }

    if (filePath.includes('..') || filePath.includes('~')) {
      return NextResponse.json(
        { error: 'Invalid file path' },
        { status: 400 }
      );
    }

    const actualFilePath = findFile(filePath);
    
    if (!actualFilePath) {
      return NextResponse.json(
        { valid: false, error: 'File not found' },
        { status: 200 }
      );
    }

    try {
      const stats = statSync(actualFilePath);
      
      if (!stats.isFile()) {
        return NextResponse.json(
          { valid: false, error: 'Path is not a file' },
          { status: 200 }
        );
      }

      const maxSize = 100 * 1024 * 1024; // 100MB
      if (stats.size > maxSize) {
        return NextResponse.json(
          { valid: false, error: 'File too large (max 100MB)' },
          { status: 200 }
        );
      }

      const ext = path.extname(actualFilePath).toLowerCase();
      const supportedExtensions = [
        '.mp4', '.avi', '.mov', '.mkv', '.webm',
        '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp',
        '.wav', '.mp3', '.aac', '.ogg', '.flac',
      ];

      if (!supportedExtensions.includes(ext)) {
        return NextResponse.json(
          { valid: false, error: 'Unsupported file type' },
          { status: 200 }
        );
      }

      return NextResponse.json({
        valid: true,
        fileInfo: {
          name: path.basename(actualFilePath),
          size: stats.size,
          extension: ext,
          lastModified: stats.mtime.toISOString(),
          actualPath: actualFilePath,
        },
      });

    } catch (statError) {
      console.error('Error getting file stats:', statError);
      return NextResponse.json(
        { valid: false, error: 'Failed to access file' },
        { status: 200 }
      );
    }
  } catch (error) {
    console.error('API error:', error);
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 }
    );
  }
}