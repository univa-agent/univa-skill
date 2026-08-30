import { NextRequest, NextResponse } from 'next/server';

// Python agent server address
const AGENT_API_URL = process.env.AGENT_API_URL || 'http://127.0.0.1:8000';

/**
 * GET /api/admin/access-codes/stats - Get access code statistics (admin only)
 */
export async function GET(req: NextRequest) {
  try {
    // Get admin access code from request header
    const adminCode = req.headers.get('X-Access-Code');

    if (!adminCode) {
      return NextResponse.json(
        { error: 'Admin access code is required' },
        { status: 401 }
      );
    }

    // Forward request to Python agent's admin stats interface
    const targetUrl = `${AGENT_API_URL}/admin/access-codes/stats`;
    
    const response = await fetch(targetUrl, {
      method: 'GET',
      headers: {
        'X-Access-Code': adminCode,
      },
    });

    if (!response.ok) {
      const errorText = await response.text();
      console.error('Agent API error:', errorText);
      
      // Return corresponding error status
      if (response.status === 401) {
        return NextResponse.json(
          { error: 'Unauthorized' },
          { status: 401 }
        );
      }
      
      if (response.status === 403) {
        return NextResponse.json(
          { error: 'Invalid admin access code' },
          { status: 403 }
        );
      }
      
      return NextResponse.json(
        { error: `Agent API error: ${errorText}` },
        { status: response.status }
      );
    }

    // Return statistics data
    const data = await response.json();
    return NextResponse.json(data);
    
  } catch (error) {
    console.error('Admin stats API error:', error);
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 }
    );
  }
}