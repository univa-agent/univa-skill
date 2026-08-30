import { NextRequest, NextResponse } from 'next/server';
import { readFile } from 'fs/promises';
import { existsSync } from 'fs';
import path from 'path';
import { getFileSearchPaths } from '@/lib/config';

function findFile(fileName: string): string | null {
  if (path.isAbsolute(fileName) && existsSync(fileName)) {
    return fileName;
  }

  const searchPaths = getFileSearchPaths();
  console.log('[File Read] Search paths:', searchPaths);
  console.log('[File Read] Looking for file:', fileName);

  for (const searchPath of searchPaths) {
    const fullPath = path.join(searchPath, fileName);
    console.log('[File Read] Trying path:', fullPath, 'exists:', existsSync(fullPath));
    if (existsSync(fullPath)) {
      console.log('[File Read] Found file at:', fullPath);
      return fullPath;
    }
  }

  console.log('[File Read] File not found in any search path');
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
        { error: 'File not found' },
        { status: 404 }
      );
    }

    try {
      const fileBuffer = await readFile(actualFilePath);
      
      const ext = path.extname(actualFilePath).toLowerCase();
      const mimeTypes: Record<string, string> = {
        '.mp4': 'video/mp4',
        '.avi': 'video/x-msvideo',
        '.mov': 'video/quicktime',
        '.mkv': 'video/x-matroska',
        '.webm': 'video/webm',
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.png': 'image/png',
        '.gif': 'image/gif',
        '.bmp': 'image/bmp',
        '.webp': 'image/webp',
        '.wav': 'audio/wav',
        '.mp3': 'audio/mpeg',
        '.aac': 'audio/aac',
        '.ogg': 'audio/ogg',
        '.flac': 'audio/flac',
      };

      const contentType = mimeTypes[ext] || 'application/octet-stream';

      return new NextResponse(new Uint8Array(fileBuffer), {
        status: 200,
        headers: {
          'Content-Type': contentType,
          'Content-Length': fileBuffer.length.toString(),
          'Cache-Control': 'public, max-age=31536000',
        },
      });
    } catch (readError) {
      console.error('Error reading file:', readError);
      return NextResponse.json(
        { error: 'Failed to read file' },
        { status: 500 }
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