import { NextRequest, NextResponse } from 'next/server';

const AGENT_API_URL = process.env.AGENT_API_URL || 'http://127.0.0.1:8000';

/**
 * GET /api/admin/access-codes/export/json - Export access codes as JSON (admin only)
 */
export async function GET(req: NextRequest) {
  try {
    const adminCode = req.headers.get('X-Access-Code');

    if (!adminCode) {
      return NextResponse.json(
        { error: 'Admin access code is required' },
        { status: 401 }
      );
    }

    const targetUrl = `${AGENT_API_URL}/admin/access-codes/export/json`;
    
    const response = await fetch(targetUrl, {
      method: 'GET',
      headers: {
        'X-Access-Code': adminCode,
      },
    });

    if (!response.ok) {
      const errorText = await response.text();
      console.error('Agent API error:', errorText);
      return NextResponse.json(
        { error: `Agent API error: ${errorText}` },
        { status: response.status }
      );
    }

    // Get the JSON data and headers from the backend
    const data = await response.json();
    const contentDisposition = response.headers.get('Content-Disposition');
    
    // Return with the same Content-Disposition header for download
    return NextResponse.json(data, {
      headers: contentDisposition 
        ? { 'Content-Disposition': contentDisposition }
        : {}
    });
    
  } catch (error) {
    console.error('Export access codes API error:', error);
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 }
    );
  }
}