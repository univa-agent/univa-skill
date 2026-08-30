import { NextApiRequest, NextApiResponse } from 'next';
import fs from 'fs';
import path from 'path';

// Cache directory
const CACHE_DIR = path.join(process.cwd(), '.media-cache');

export default async function handler(
  req: NextApiRequest,
  res: NextApiResponse
) {
  if (req.method === 'GET') {
    // Get cache statistics
    try {
      let totalFiles = 0;
      let totalSize = 0;

      if (fs.existsSync(CACHE_DIR)) {
        const files = fs.readdirSync(CACHE_DIR);
        totalFiles = files.length;
        
        for (const file of files) {
          const filePath = path.join(CACHE_DIR, file);
          if (fs.existsSync(filePath)) {
            const stats = fs.statSync(filePath);
            totalSize += stats.size;
          }
        }
      }

      res.status(200).json({
        totalFiles,
        totalSize,
        cacheDir: CACHE_DIR,
      });
    } catch (error) {
      console.error('Get cache stats error:', error);
      res.status(500).json({ error: 'Failed to get stats' });
    }
  } else {
    res.setHeader('Allow', ['GET']);
    res.status(405).end(`Method ${req.method} Not Allowed`);
  }
}