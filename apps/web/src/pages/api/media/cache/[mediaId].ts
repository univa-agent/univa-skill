import { NextApiRequest, NextApiResponse } from 'next';
import fs from 'fs';
import path from 'path';

// Cache directory
const CACHE_DIR = path.join(process.cwd(), '.media-cache');

export default async function handler(
  req: NextApiRequest,
  res: NextApiResponse
) {
  const { mediaId } = req.query;

  if (typeof mediaId !== 'string') {
    return res.status(400).json({ error: 'Invalid mediaId' });
  }

  if (req.method === 'DELETE') {
    // Delete cache files for specific media
    try {
      if (!fs.existsSync(CACHE_DIR)) {
        return res.status(404).json({ error: 'Cache directory not found' });
      }

      const files = fs.readdirSync(CACHE_DIR);
      const mediaFiles = files.filter(file => file.startsWith(`${mediaId}_`));

      for (const file of mediaFiles) {
        const filePath = path.join(CACHE_DIR, file);
        if (fs.existsSync(filePath)) {
          fs.unlinkSync(filePath);
        }
      }

      res.status(200).json({ 
        success: true, 
        deletedFiles: mediaFiles.length 
      });
    } catch (error) {
      console.error('Delete media cache error:', error);
      res.status(500).json({ error: 'Delete failed' });
    }
  } else {
    res.setHeader('Allow', ['DELETE']);
    res.status(405).end(`Method ${req.method} Not Allowed`);
  }
}