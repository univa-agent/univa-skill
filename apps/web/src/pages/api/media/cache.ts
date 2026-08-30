import { NextApiRequest, NextApiResponse } from 'next';
import fs from 'fs';
import path from 'path';
import formidable from 'formidable';
import { v4 as uuidv4 } from 'uuid';

// Cache directory
const CACHE_DIR = path.join(process.cwd(), '.media-cache');

// Ensure cache directory exists
function ensureCacheDir() {
  if (!fs.existsSync(CACHE_DIR)) {
    fs.mkdirSync(CACHE_DIR, { recursive: true });
  }
}

export const config = {
  api: {
    bodyParser: false,
  },
};

export default async function handler(
  req: NextApiRequest,
  res: NextApiResponse
) {
  ensureCacheDir();

  if (req.method === 'POST') {
    // Upload file to cache
    try {
      const form = formidable({
        uploadDir: CACHE_DIR,
        keepExtensions: true,
        maxFileSize: 100 * 1024 * 1024, // 100MB
      });

      const [fields, files] = await form.parse(req);
      const mediaId = Array.isArray(fields.mediaId) ? fields.mediaId[0] : fields.mediaId;
      const fileName = Array.isArray(fields.fileName) ? fields.fileName[0] : fields.fileName;
      
      if (!mediaId || !fileName) {
        return res.status(400).json({ error: 'Missing mediaId or fileName' });
      }

      const uploadedFile = Array.isArray(files.file) ? files.file[0] : files.file;
      if (!uploadedFile) {
        return res.status(400).json({ error: 'No file uploaded' });
      }

      // Generate new file name
      const fileExtension = path.extname(fileName);
      const newFileName = `${mediaId}_${uuidv4()}${fileExtension}`;
      const newFilePath = path.join(CACHE_DIR, newFileName);

      // Move file to final location
      fs.renameSync(uploadedFile.filepath, newFilePath);

      res.status(200).json({
        success: true,
        localPath: newFilePath,
        fileName: newFileName,
      });
    } catch (error) {
      console.error('Upload error:', error);
      res.status(500).json({ error: 'Upload failed' });
    }
  } else if (req.method === 'DELETE') {
    // Clear all cache
    try {
      const files = fs.readdirSync(CACHE_DIR);
      for (const file of files) {
        fs.unlinkSync(path.join(CACHE_DIR, file));
      }
      res.status(200).json({ success: true });
    } catch (error) {
      console.error('Clear cache error:', error);
      res.status(500).json({ error: 'Clear cache failed' });
    }
  } else {
    res.setHeader('Allow', ['POST', 'DELETE']);
    res.status(405).end(`Method ${req.method} Not Allowed`);
  }
}